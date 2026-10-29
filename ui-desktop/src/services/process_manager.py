"""Non-blocking QProcess Manager for `gfn-forge` CLI and `forge test` commands."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal


class LocalProcessManager(QObject):
    """Manages local `gfn-forge` and `forge` child processes asynchronously via QProcess."""

    stdout_received = Signal(str)
    stderr_received = Signal(str)
    process_started = Signal(str, list)  # program, args
    process_finished = Signal(int, QProcess.ExitStatus)
    process_error = Signal(str)
    daemon_ready = Signal(str)  # base_url

    def __init__(self, workspace_root: Optional[Path] = None, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.workspace_root = workspace_root or self._detect_workspace_root()
        self._active_process: Optional[QProcess] = None
        self._daemon_process: Optional[QProcess] = None
        self._is_paused: bool = False

    @staticmethod
    def _detect_workspace_root() -> Path:
        current = Path(__file__).resolve()
        # ui-desktop/src/services/process_manager.py -> repo root is 3 levels up
        for candidate in [current.parents[3], current.parents[2], Path.cwd()]:
            if (candidate / "Cargo.toml").exists() or (candidate / "configs").exists():
                return candidate
        return Path.cwd()

    def resolve_gfn_forge_binary(self) -> Optional[str]:
        """Locate `gfn-forge` executable in target/release, target/debug, or PATH."""
        exe_name = "gfn-forge.exe" if os.name == "nt" else "gfn-forge"
        candidates = [
            self.workspace_root / "target" / "release" / exe_name,
            self.workspace_root / "target" / "debug" / exe_name,
        ]
        for c in candidates:
            if c.exists() and c.is_file():
                return str(c)
        which_bin = shutil.which("gfn-forge")
        if which_bin:
            return which_bin
        return None

    def format_cli_command(self, subcommand: str, args: List[str]) -> str:
        """Return a reproducible CLI invocation string."""
        quoted = [f'"{a}"' if " " in a else a for a in args]
        return f"gfn-forge {subcommand} " + " ".join(quoted)

    def build_audit_args(
        self,
        project_path: str,
        config_path: str,
        setup_contract: str,
        setup_function: str,
        max_trajectories: int,
        output_dir: str = "audit_out",
        seed: int = 42,
    ) -> List[str]:
        return [
            "audit",
            "--project",
            project_path,
            "--config",
            config_path,
            "--setup-contract",
            setup_contract,
            "--setup-function",
            setup_function,
            "--max-trajectories",
            str(max_trajectories),
            "--output-dir",
            output_dir,
            "--seed",
            str(seed),
        ]

    def build_training_args(
        self,
        phase: int,
        config_path: str,
        corpus_dir: str,
        checkpoint_out: str,
        epochs: int = 10,
        pretrained_weights: Optional[str] = None,
        anchor_checkpoint: Optional[str] = None,
        lambda_ewc: float = 400.0,
    ) -> List[str]:
        if phase == 1:
            return [
                "pretrain",
                "--config",
                config_path,
                "--corpus-dir",
                corpus_dir,
                "--checkpoint-out",
                checkpoint_out,
                "--epochs",
                str(epochs),
            ]
        if phase == 2:
            args = [
                "train",
                "--config",
                config_path,
                "--corpus-dir",
                corpus_dir,
                "--checkpoint-out",
                checkpoint_out,
            ]
            if pretrained_weights:
                args.extend(["--pretrained-weights", pretrained_weights])
            return args
        # Phase 3: Continual Learning with EWC
        args = [
            "train-continual",
            "--config",
            config_path,
            "--lambda-ewc",
            str(lambda_ewc),
        ]
        if anchor_checkpoint:
            args.extend(["--anchor-checkpoint", anchor_checkpoint])
        return args

    def start_command(self, args: List[str], working_dir: Optional[str] = None) -> bool:
        """Spawn `gfn-forge` with the given arguments asynchronously."""
        if self.is_running():
            self.process_error.emit("A gfn-forge task is already running.")
            return False

        proc = QProcess(self)
        proc.setWorkingDirectory(working_dir or str(self.workspace_root))
        env = QProcessEnvironment.systemEnvironment()
        env.insert("RUST_LOG", "info")
        proc.setProcessEnvironment(env)

        proc.readyReadStandardOutput.connect(lambda: self._on_stdout(proc))
        proc.readyReadStandardError.connect(lambda: self._on_stderr(proc))
        proc.finished.connect(self._on_finished)
        proc.errorOccurred.connect(self._on_error)

        binary = self.resolve_gfn_forge_binary()
        if binary:
            program = binary
            cmd_args = args
        else:
            cargo = shutil.which("cargo")
            if not cargo:
                self.process_error.emit("Neither `gfn-forge` binary nor `cargo` found on PATH.")
                return False
            program = cargo
            cmd_args = ["run", "--bin", "gfn-forge", "--"] + args

        self._active_process = proc
        self._is_paused = False
        proc.start(program, cmd_args)
        self.process_started.emit(program, cmd_args)
        return True

    def start_daemon(
        self,
        host: str = "127.0.0.1",
        port: int = 8080,
        metrics_port: int = 9090,
        config_path: str = "configs/default_audit.toml",
    ) -> bool:
        """Start `gfn-forge serve` background microservice daemon if not already running."""
        if self.is_daemon_running():
            self.daemon_ready.emit(f"http://{host}:{port}")
            return True

        proc = QProcess(self)
        proc.setWorkingDirectory(str(self.workspace_root))
        args = [
            "serve",
            "--host",
            host,
            "--port",
            str(port),
            "--metrics-port",
            str(metrics_port),
            "--config",
            config_path,
        ]
        proc.readyReadStandardOutput.connect(lambda: self._on_stdout(proc))
        proc.readyReadStandardError.connect(lambda: self._on_stderr(proc))

        binary = self.resolve_gfn_forge_binary()
        if binary:
            proc.start(binary, args)
        else:
            cargo = shutil.which("cargo")
            if not cargo:
                self.process_error.emit("Cannot launch daemon: `gfn-forge` binary not found.")
                return False
            proc.start(cargo, ["run", "--bin", "gfn-forge", "--"] + args)

        self._daemon_process = proc
        self.daemon_ready.emit(f"http://{host}:{port}")
        return True

    def run_forge_test(self, poc_path: str, project_root: str) -> bool:
        """Execute `forge test -vvvv --offline --match-path <poc_path>`."""
        forge_bin = shutil.which("forge")
        if not forge_bin:
            self.process_error.emit("Foundry `forge` binary not found in PATH.")
            return False

        proc = QProcess(self)
        proc.setWorkingDirectory(project_root)
        args = ["test", "-vvvv", "--offline", "--match-path", poc_path]
        proc.readyReadStandardOutput.connect(lambda: self._on_stdout(proc))
        proc.readyReadStandardError.connect(lambda: self._on_stderr(proc))
        proc.finished.connect(self._on_finished)
        proc.errorOccurred.connect(self._on_error)

        self._active_process = proc
        proc.start(forge_bin, args)
        self.process_started.emit(forge_bin, args)
        return True

    def is_running(self) -> bool:
        return (
            self._active_process is not None
            and self._active_process.state() != QProcess.ProcessState.NotRunning
        )

    def is_daemon_running(self) -> bool:
        return (
            self._daemon_process is not None
            and self._daemon_process.state() != QProcess.ProcessState.NotRunning
        )

    def stop_active_process(self, graceful: bool = True) -> None:
        if not self.is_running() or self._active_process is None:
            return
        if graceful:
            self._active_process.terminate()
            if not self._active_process.waitForFinished(1500):
                self._active_process.kill()
        else:
            self._active_process.kill()

    def stop_daemon(self) -> None:
        if not self.is_daemon_running() or self._daemon_process is None:
            return
        self._daemon_process.terminate()
        if not self._daemon_process.waitForFinished(1500):
            self._daemon_process.kill()

    def _on_stdout(self, proc: QProcess) -> None:
        data = proc.readAllStandardOutput().data().decode("utf-8", errors="replace")
        for line in data.splitlines():
            if line.strip():
                self.stdout_received.emit(line)

    def _on_stderr(self, proc: QProcess) -> None:
        data = proc.readAllStandardError().data().decode("utf-8", errors="replace")
        for line in data.splitlines():
            if line.strip():
                self.stderr_received.emit(line)

    def _on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        self.process_finished.emit(exit_code, exit_status)

    def _on_error(self, error: QProcess.ProcessError) -> None:
        self.process_error.emit(f"Process error occurred: {error.name}")
