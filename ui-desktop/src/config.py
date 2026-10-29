"""TOML Configuration Loader, Validator, and Preset Manager for GFlowNet-Prover UI."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import tomllib as tomli  # Python 3.11+ built-in
except ImportError:
    import tomli  # type: ignore

try:
    import tomli_w
except ImportError:
    tomli_w = None  # type: ignore


@dataclass
class ProjectSourceConfig:
    workspace_path: str = "."
    setup_contract: str = "ExploitHarnessTest"
    setup_function: str = "setUp"
    target_contracts: List[str] = field(default_factory=list)


@dataclass
class FoundryProfileConfig:
    solc_version: str = "0.8.24"
    evm_version: str = "cancun"
    fork_block_number: Optional[int] = 18_000_000


@dataclass
class SearchBudgetConfig:
    max_trajectories: int = 100_000
    max_depth: int = 15
    batch_size: int = 64
    wall_clock_timeout_sec: int = 900
    smt_timeout_ms: int = 5000
    enable_online_adaptation: bool = True


@dataclass
class RewardConfig:
    alpha_boundary: float = 1.0
    beta_novelty: float = 0.5
    gamma_exploit: float = 100.0
    m_unsat_penalty: float = 1e-3
    r_min: float = 1e-6
    lambda_boundary: float = 5.0


@dataclass
class SymbolicConfig:
    boundary_trigger: float = 0.85
    max_smt_workers: int = 6
    enable_unsat_cache: bool = True
    lmdb_cache_path: str = "/var/cache/gfn-prover/lmdb"
    smt_timeout_ms: int = 5000


@dataclass
class AuditConfig:
    project_source: ProjectSourceConfig = field(default_factory=ProjectSourceConfig)
    foundry_profile: FoundryProfileConfig = field(default_factory=FoundryProfileConfig)
    search_budget: SearchBudgetConfig = field(default_factory=SearchBudgetConfig)
    reward: RewardConfig = field(default_factory=RewardConfig)
    symbolic: SymbolicConfig = field(default_factory=SymbolicConfig)
    seed: int = 42

    def to_submission_payload(self) -> Dict[str, Any]:
        """Convert to JSON payload matching Rust `AuditSubmissionRequest` (`POST /v1/audits`)."""
        project_src: Dict[str, Any] = {
            "workspace_path": self.project_source.workspace_path,
            "setup_contract": self.project_source.setup_contract,
            "setup_function": self.project_source.setup_function,
        }
        if self.project_source.target_contracts:
            project_src["target_contracts"] = self.project_source.target_contracts

        return {
            "project_source": project_src,
            "foundry_profile": {
                "solc_version": self.foundry_profile.solc_version,
                "evm_version": self.foundry_profile.evm_version,
                "fork_block_number": self.foundry_profile.fork_block_number,
            },
            "search_budget": {
                "max_trajectories": self.search_budget.max_trajectories,
                "max_depth": self.search_budget.max_depth,
                "batch_size": self.search_budget.batch_size,
                "wall_clock_timeout_sec": self.search_budget.wall_clock_timeout_sec,
                "smt_timeout_ms": self.search_budget.smt_timeout_ms,
                "enable_online_adaptation": self.search_budget.enable_online_adaptation,
            },
        }

    def to_toml_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if d["foundry_profile"]["fork_block_number"] is None:
            del d["foundry_profile"]["fork_block_number"]
        return d


@dataclass
class TrainingHyperparameters:
    phase: int = 2  # 1: MSTM Pre-train, 2: Curriculum TB, 3: Continual EWC
    preset_name: str = "Production DeFi Tuning"
    corpus_dir: str = "data/corpus"
    checkpoint_out: str = "checkpoints/curriculum_tb.safetensors"
    anchor_checkpoint: str = "checkpoints/pretrained_mstm.safetensors"
    compute_device: str = "CUDA GPU 0 (Kind::BFloat16)"
    worker_threads: int = 16
    epochs: int = 10
    mask_ratio: float = 0.30
    lr_policy: float = 3e-4
    lr_log_z: float = 5e-3
    lr_warmup_steps: int = 2000
    huber_delta: float = 10.0
    alpha_boundary: float = 1.0
    beta_novelty: float = 0.5
    gamma_exploit: float = 100.0
    m_unsat_penalty: float = 1e-3
    boundary_trigger: float = 0.85
    lambda_ewc: float = 400.0
    replay_capacity: int = 100_000
    batch_size: int = 64
    max_steps: int = 15
    rgat_hidden_dim: int = 512
    rgat_num_layers: int = 6
    rgat_heads: int = 8
    clip_grad_norm: float = 1.0
    ema_decay: float = 0.95
    logit_clip_bound: float = 30.0
    entropy_reg_coeff: float = 0.01
    target_entropy_nats: float = 0.35
    enable_grad_spike_guard: bool = True
    max_residual_clip: float = 100.0

    def to_toml_dict(self) -> Dict[str, Any]:
        return {
            "model": {
                "rgat_hidden_dim": self.rgat_hidden_dim,
                "rgat_num_layers": self.rgat_num_layers,
                "rgat_heads": self.rgat_heads,
                "hgt_hidden_dim": 512,
                "hgt_num_layers": 4,
                "hgt_heads": 8,
            },
            "optim": {
                "lr_policy": self.lr_policy,
                "lr_log_z": self.lr_log_z,
                "lr_warmup_steps": self.lr_warmup_steps,
                "lr_min": 1e-5,
                "weight_decay": 1e-4,
                "clip_grad_norm": self.clip_grad_norm,
            },
            "reward": {
                "alpha_boundary": self.alpha_boundary,
                "beta_novelty": self.beta_novelty,
                "gamma_exploit": self.gamma_exploit,
                "m_unsat_penalty": self.m_unsat_penalty,
                "r_min": 1e-6,
                "lambda_boundary": 5.0,
            },
            "rollout": {
                "max_steps": self.max_steps,
                "batch_size": self.batch_size,
                "temperature": 1.0,
                "epsilon_uniform": 0.05,
                "num_workers": self.worker_threads,
            },
            "replay_buffer": {
                "capacity": self.replay_capacity,
                "alpha_per": 0.6,
                "beta_per": 0.4,
                "eps_per": 1e-5,
            },
            "tb_loss": {
                "huber_delta": self.huber_delta,
                "reward_min": 1e-6,
                "max_residual_clip": self.max_residual_clip,
            },
            "stability": {
                "ema_decay": self.ema_decay,
                "logit_clip_bound": self.logit_clip_bound,
                "entropy_reg_coeff": self.entropy_reg_coeff,
                "target_entropy_nats": self.target_entropy_nats,
                "enable_grad_spike_guard": self.enable_grad_spike_guard,
            },
            "symbolic": {
                "boundary_trigger": self.boundary_trigger,
                "smt_timeout_ms": 5000,
            },
            "continual": {
                "lambda_ewc": self.lambda_ewc,
                "anchor_checkpoint": self.anchor_checkpoint,
            },
        }


TRAINING_PRESETS: Dict[str, Dict[str, Any]] = {
    "Smoke Test": {
        "lr_policy": 5e-4,
        "lr_log_z": 1e-2,
        "lr_warmup_steps": 100,
        "clip_grad_norm": 1.0,
        "ema_decay": 0.90,
        "enable_grad_spike_guard": True,
        "huber_delta": 10.0,
        "alpha_boundary": 1.0,
        "beta_novelty": 0.25,
        "gamma_exploit": 50.0,
        "boundary_trigger": 0.85,
        "lambda_ewc": 400.0,
        "replay_capacity": 10_000,
        "worker_threads": 4,
        "epochs": 2,
        "batch_size": 16,
    },
    "Production DeFi Tuning": {
        "lr_policy": 3e-4,
        "lr_log_z": 5e-3,
        "lr_warmup_steps": 2000,
        "clip_grad_norm": 1.0,
        "ema_decay": 0.95,
        "enable_grad_spike_guard": True,
        "huber_delta": 10.0,
        "alpha_boundary": 1.0,
        "beta_novelty": 0.50,
        "gamma_exploit": 100.0,
        "boundary_trigger": 0.85,
        "lambda_ewc": 400.0,
        "replay_capacity": 100_000,
        "worker_threads": 16,
        "epochs": 10,
        "batch_size": 64,
    },
    "Deep Exploit Search": {
        "lr_policy": 1.5e-4,
        "lr_log_z": 5e-3,
        "lr_warmup_steps": 4000,
        "clip_grad_norm": 0.75,
        "ema_decay": 0.98,
        "enable_grad_spike_guard": True,
        "huber_delta": 10.0,
        "alpha_boundary": 1.25,
        "beta_novelty": 1.50,
        "gamma_exploit": 250.0,
        "boundary_trigger": 0.78,
        "lambda_ewc": 400.0,
        "replay_capacity": 250_000,
        "worker_threads": 32,
        "epochs": 25,
        "batch_size": 64,
    },
}


def _dump_toml_fallback(data: Dict[str, Any]) -> str:
    """Deterministic TOML serializer if tomli_w is unavailable."""
    if tomli_w is not None:
        return tomli_w.dumps(data)
    lines: List[str] = []
    # Top-level scalars first
    for k, v in data.items():
        if not isinstance(v, dict):
            lines.append(f"{k} = {_format_toml_val(v)}")
    for section, values in data.items():
        if isinstance(values, dict):
            lines.append(f"\n[{section}]")
            for k, v in values.items():
                if v is not None:
                    lines.append(f"{k} = {_format_toml_val(v)}")
    return "\n".join(lines).strip() + "\n"


def _format_toml_val(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        escaped = v.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(v, list):
        inner = ", ".join(_format_toml_val(x) for x in v)
        return f"[{inner}]"
    return str(v)


class ConfigManager:
    """Loads and saves GFlowNet-Prover TOML configurations."""

    @staticmethod
    def load_audit_config(path: str | Path) -> AuditConfig:
        p = Path(path)
        if not p.exists():
            return AuditConfig()
        raw = tomli.loads(p.read_text(encoding="utf-8"))
        ps = raw.get("project_source", {})
        fp = raw.get("foundry_profile", {})
        sb = raw.get("search_budget", {})
        rw = raw.get("reward", {})
        sym = raw.get("symbolic", {})
        return AuditConfig(
            project_source=ProjectSourceConfig(
                workspace_path=ps.get("workspace_path", "."),
                setup_contract=ps.get("setup_contract", "ExploitHarnessTest"),
                setup_function=ps.get("setup_function", "setUp"),
                target_contracts=ps.get("target_contracts", []),
            ),
            foundry_profile=FoundryProfileConfig(
                solc_version=fp.get("solc_version", "0.8.24"),
                evm_version=fp.get("evm_version", "cancun"),
                fork_block_number=fp.get("fork_block_number", 18_000_000),
            ),
            search_budget=SearchBudgetConfig(
                max_trajectories=int(sb.get("max_trajectories", 100_000)),
                max_depth=int(sb.get("max_depth", 15)),
                batch_size=int(sb.get("batch_size", 64)),
                wall_clock_timeout_sec=int(sb.get("wall_clock_timeout_sec", 900)),
                smt_timeout_ms=int(sb.get("smt_timeout_ms", 5000)),
                enable_online_adaptation=bool(sb.get("enable_online_adaptation", True)),
            ),
            reward=RewardConfig(
                alpha_boundary=float(rw.get("alpha_boundary", 1.0)),
                beta_novelty=float(rw.get("beta_novelty", 0.5)),
                gamma_exploit=float(rw.get("gamma_exploit", 100.0)),
                m_unsat_penalty=float(rw.get("m_unsat_penalty", 1e-3)),
                r_min=float(rw.get("r_min", 1e-6)),
                lambda_boundary=float(rw.get("lambda_boundary", 5.0)),
            ),
            symbolic=SymbolicConfig(
                boundary_trigger=float(sym.get("boundary_trigger", 0.85)),
                max_smt_workers=int(sym.get("max_smt_workers", 6)),
                enable_unsat_cache=bool(sym.get("enable_unsat_cache", True)),
                lmdb_cache_path=str(sym.get("lmdb_cache_path", "/var/cache/gfn-prover/lmdb")),
                smt_timeout_ms=int(sym.get("smt_timeout_ms", sb.get("smt_timeout_ms", 5000))),
            ),
            seed=int(raw.get("seed", 42)),
        )

    @staticmethod
    def save_audit_config(config: AuditConfig, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        content = _dump_toml_fallback(config.to_toml_dict())
        p.write_text(content, encoding="utf-8")
        return p

    @staticmethod
    def load_training_config(path: str | Path) -> TrainingHyperparameters:
        p = Path(path)
        if not p.exists():
            return TrainingHyperparameters()
        raw = tomli.loads(p.read_text(encoding="utf-8"))
        hp = TrainingHyperparameters()
        if "training" in raw:
            hp.phase = 1
            tr = raw["training"]
            hp.corpus_dir = tr.get("dataset_path", hp.corpus_dir)
            hp.batch_size = int(tr.get("batch_size", hp.batch_size))
            hp.epochs = int(tr.get("num_epochs", hp.epochs))
            hp.mask_ratio = float(tr.get("mask_ratio", hp.mask_ratio))
        if "optim" in raw:
            opt = raw["optim"]
            hp.lr_policy = float(opt.get("lr_policy", opt.get("lr", hp.lr_policy)))
            hp.lr_log_z = float(opt.get("lr_log_z", hp.lr_log_z))
            hp.lr_warmup_steps = int(opt.get("lr_warmup_steps", hp.lr_warmup_steps))
            hp.clip_grad_norm = float(opt.get("clip_grad_norm", hp.clip_grad_norm))
        if "reward" in raw:
            rw = raw["reward"]
            hp.alpha_boundary = float(rw.get("alpha_boundary", hp.alpha_boundary))
            hp.beta_novelty = float(rw.get("beta_novelty", hp.beta_novelty))
            hp.gamma_exploit = float(rw.get("gamma_exploit", hp.gamma_exploit))
            hp.m_unsat_penalty = float(rw.get("m_unsat_penalty", hp.m_unsat_penalty))
        if "loss" in raw:
            ls = raw["loss"]
            hp.huber_delta = float(ls.get("huber_delta", hp.huber_delta))
        if "tb_loss" in raw:
            tb = raw["tb_loss"]
            hp.huber_delta = float(tb.get("huber_delta", hp.huber_delta))
            hp.max_residual_clip = float(tb.get("max_residual_clip", hp.max_residual_clip))
        if "stability" in raw:
            stab = raw["stability"]
            hp.ema_decay = float(stab.get("ema_decay", hp.ema_decay))
            hp.logit_clip_bound = float(stab.get("logit_clip_bound", hp.logit_clip_bound))
            hp.entropy_reg_coeff = float(stab.get("entropy_reg_coeff", hp.entropy_reg_coeff))
            hp.target_entropy_nats = float(stab.get("target_entropy_nats", hp.target_entropy_nats))
            hp.enable_grad_spike_guard = bool(
                stab.get("enable_grad_spike_guard", hp.enable_grad_spike_guard)
            )
        if "symbolic" in raw:
            sym = raw["symbolic"]
            hp.boundary_trigger = float(sym.get("boundary_trigger", hp.boundary_trigger))
        if "replay_buffer" in raw:
            rb = raw["replay_buffer"]
            hp.replay_capacity = int(rb.get("capacity", hp.replay_capacity))
        if "continual" in raw:
            cont = raw["continual"]
            hp.lambda_ewc = float(cont.get("lambda_ewc", hp.lambda_ewc))
            hp.anchor_checkpoint = str(cont.get("anchor_checkpoint", hp.anchor_checkpoint))
        return hp

    @staticmethod
    def save_training_config(hp: TrainingHyperparameters, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        content = _dump_toml_fallback(hp.to_toml_dict())
        p.write_text(content, encoding="utf-8")
        return p
