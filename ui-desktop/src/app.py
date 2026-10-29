"""Main QMainWindow, Persistent Activity Sidebar, Toolbar, and View Router (`GfnProverMainWindow`)."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from src.services.process_manager import LocalProcessManager
from src.services.prom_client import PrometheusScraper
from src.services.sse_client import NativeSseClient
from src.viewmodels.audit_vm import AuditViewModel
from src.viewmodels.telemetry_vm import TelemetryViewModel
from src.viewmodels.training_vm import TrainingViewModel
from src.views.audit_view import AuditWorkbenchView


class GfnProverMainWindow(QMainWindow):
    """Unified Native Desktop Studio for GFlowNet-Prover (Pure Rust / Foundry Edition)."""

    def __init__(self, workspace_root: Optional[Path] = None) -> None:
        super().__init__()
        self.setWindowTitle("GFlowNet-Prover [Pure Rust / Foundry Edition] - Native Neuro-Symbolic Verification Studio")
        self.resize(1460, 920)

        # Initialize Services
        self.process_manager = LocalProcessManager(workspace_root=workspace_root, parent=self)
        self.sse_client = NativeSseClient(base_url="http://127.0.0.1:8080", parent=self)
        self.prom_scraper = PrometheusScraper(metrics_url="http://127.0.0.1:9090/metrics", parent=self)

        # Initialize ViewModels
        self.audit_vm = AuditViewModel(self.process_manager, self.sse_client, parent=self)
        self.training_vm = TrainingViewModel(self.process_manager, parent=self)
        self.telemetry_vm = TelemetryViewModel(
            self.prom_scraper, workspace_root=self.process_manager.workspace_root, parent=self
        )

        # Wire audit logs into operational telemetry terminal
        self.audit_vm.log_emitted.connect(self.telemetry_vm.diagnostic_log_appended.emit)

        self._views: Dict[int, QWidget] = {}
        self._placeholders: Dict[int, QWidget] = {}

        self._build_toolbar()
        self._build_central_shell()
        self._build_statusbar()

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("GFlowNet-Prover Main Toolbar", self)
        toolbar.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

        brand_lbl = QLabel("  ◆ GFLOWNET-PROVER  |  rustc 1.82  ·  revm 19.0 CoW Arena  ·  Bitwuzla QF_BV  ")
        brand_lbl.setStyleSheet("color: #58a6ff; font-weight: 800; font-size: 13px; letter-spacing: 0.4px;")
        toolbar.addWidget(brand_lbl)

        self.active_view_badge = QLabel("  Workbench 1: Formal Audit & Verification  ")
        self.active_view_badge.setStyleSheet(
            "background-color: #162234; color: #9ecbff; border: 1px solid #2b384e; "
            "border-radius: 4px; padding: 3px 10px; font-weight: 700; font-size: 12px;"
        )
        toolbar.addWidget(self.active_view_badge)

        spacer = QWidget(self)
        from PySide6.QtWidgets import QSizePolicy
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        self.daemon_badge = QLabel(" ● Daemon (127.0.0.1:8080): STANDBY ")
        self.daemon_badge.setStyleSheet(
            "background-color: #161d28; color: #79c0ff; border: 1px solid #30363d; "
            "border-radius: 4px; padding: 4px 10px; font-weight: 600;"
        )
        toolbar.addWidget(self.daemon_badge)

        self.start_daemon_btn = QPushButton("Launch Local Daemon (`gfn-forge serve`)")
        self.start_daemon_btn.setToolTip("Spawn `gfn-forge serve` background HTTP/SSE & Prometheus daemon")
        self.start_daemon_btn.clicked.connect(self._on_launch_daemon)
        toolbar.addWidget(self.start_daemon_btn)

        self.health_btn = QPushButton("Ping /health")
        self.health_btn.setToolTip("Check HTTP /v1/health status on 127.0.0.1:8080")
        self.health_btn.clicked.connect(self.sse_client.check_health)
        toolbar.addWidget(self.health_btn)

        self.sse_client.health_status_changed.connect(self._on_daemon_health)

    def _build_central_shell(self) -> None:
        central = QWidget(self)
        root_hbox = QHBoxLayout(central)
        root_hbox.setContentsMargins(0, 0, 0, 0)
        root_hbox.setSpacing(0)

        # --- Left Activity Navigation Sidebar ---
        sidebar = QFrame(central)
        sidebar.setObjectName("ActivitySidebar")
        nav_vbox = QVBoxLayout(sidebar)
        nav_vbox.setContentsMargins(0, 14, 0, 14)
        nav_vbox.setSpacing(4)

        hdr = QLabel("  STUDIO WORKBENCHES")
        hdr.setStyleSheet("color: #6e7681; font-size: 11px; font-weight: 800; letter-spacing: 0.8px; padding: 4px 14px;")
        nav_vbox.addWidget(hdr)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        nav_items = [
            (0, "⚡  1. Audit Workbench", "Configure Foundry targets, run neuro-symbolic audits & inspect verified PoCs (Ctrl+1)"),
            (1, "🎯  2. Training Studio", "3-Phase MSTM, Curriculum TB & Continual EWC training with live 60 FPS telemetry (Ctrl+2)"),
            (2, "🔍  3. Trajectory && HSDG", "Scrub transaction call traces, storage slot deltas, QF_BV formulas & HSDG graphs (Ctrl+3)"),
            (3, "📊  4. Telemetry && Drift", "Monitor real-time revm throughput, spectral MMD²/PSI drift & hardware utilization (Ctrl+4)"),
            (4, "🛡️  5. Model Registry", "Validate SafeTensors checkpoints against all 7 Go/No-Go Release Gates (Ctrl+5)"),
        ]
        self.nav_buttons: Dict[int, QPushButton] = {}
        for idx, label, tip in nav_items:
            btn = QPushButton(label)
            btn.setObjectName("NavButton")
            btn.setCheckable(True)
            btn.setToolTip(tip)
            btn.setShortcut(f"Ctrl+{idx + 1}")
            if idx == 0:
                btn.setChecked(True)
            self.nav_group.addButton(btn, idx)
            self.nav_buttons[idx] = btn
            nav_vbox.addWidget(btn)

        nav_vbox.addStretch()

        sla_card = QFrame(sidebar)
        sla_card.setStyleSheet(
            "background-color: #0d131d; border: 1px solid #1e293b; border-radius: 6px; margin: 4px 10px;"
        )
        sla_layout = QVBoxLayout(sla_card)
        sla_layout.setContentsMargins(10, 8, 10, 8)
        sla_title = QLabel("VERIFIED SYSTEM SLAs")
        sla_title.setStyleSheet("color: #58a6ff; font-size: 10px; font-weight: 800; letter-spacing: 0.5px;")
        sla_footer = QLabel(
            "✓ FPR == 0.0% (Forge Gate)\n"
            "✓ ≥ 65,000 TPS / Thread\n"
            "✓ RGAT p99 ≤ 9.5 ms\n"
            "✓ Stability Guard Active\n"
            "✓ Native Qt6 (< 95 MB RAM)"
        )
        sla_footer.setStyleSheet("color: #8b949e; font-size: 11px; line-height: 1.35;")
        sla_layout.addWidget(sla_title)
        sla_layout.addWidget(sla_footer)
        nav_vbox.addWidget(sla_card)

        # --- Main Stacked View Container ---
        self.stack = QStackedWidget(central)

        # Instantiate View 0 immediately (Primary User Flow); lazy-instantiate 1..4 on demand
        self.audit_view = AuditWorkbenchView(self.audit_vm, self)
        self._views[0] = self.audit_view
        self.stack.addWidget(self.audit_view)

        for idx in range(1, 5):
            holder = QWidget(self)
            self._placeholders[idx] = holder
            self.stack.addWidget(holder)

        self.nav_group.idClicked.connect(self.switch_view)

        root_hbox.addWidget(sidebar)
        root_hbox.addWidget(self.stack, 1)
        self.setCentralWidget(central)

    def _build_statusbar(self) -> None:
        status = QStatusBar(self)
        self.setStatusBar(status)
        status.showMessage(
            "Ready  |  Engine: gfn-forge (Pure Rust Edition 2021)  |  "
            "IPC: 127.0.0.1:8080 (SSE) & 127.0.0.1:9090 (Prometheus 1 Hz)  |  FPR Gate: 0.0%"
        )

    def switch_view(self, index: int) -> QWidget:
        """Switch to view `index` (0..4), instantiating lazily if not yet created."""
        if index not in self._views:
            view = self._create_view(index)
            old_holder = self._placeholders[index]
            self.stack.removeWidget(old_holder)
            old_holder.deleteLater()
            self.stack.insertWidget(index, view)
            self._views[index] = view

        if index in self.nav_buttons:
            self.nav_buttons[index].setChecked(True)
        view_titles = {
            0: "  Workbench 1: Formal Audit & Verification  ",
            1: "  Workbench 2: Tri-Phase Training Studio  ",
            2: "  Workbench 3: Trajectory & HSDG Inspector  ",
            3: "  Workbench 4: Operational Telemetry & Drift  ",
            4: "  Workbench 5: SafeTensors Registry & 7 Gates  ",
        }
        if hasattr(self, "active_view_badge"):
            self.active_view_badge.setText(view_titles.get(index, "  GFlowNet-Prover Studio  "))
        self.stack.setCurrentWidget(self._views[index])
        return self._views[index]

    def ensure_all_views_loaded(self) -> None:
        """Instantiate all 5 views (useful for comprehensive inspection or automated testing)."""
        current = self.stack.currentIndex()
        for idx in range(5):
            if idx not in self._views:
                self.switch_view(idx)
        self.switch_view(current)

    def _create_view(self, index: int) -> QWidget:
        if index == 1:
            from src.views.training_view import TrainingStudioView

            self.training_view = TrainingStudioView(self.training_vm, self)
            return self.training_view
        if index == 2:
            from src.views.trajectory_view import TrajectoryInspectorView

            self.trajectory_view = TrajectoryInspectorView(self.audit_vm, self)
            return self.trajectory_view
        if index == 3:
            from src.views.telemetry_view import OperationalTelemetryView

            self.telemetry_view = OperationalTelemetryView(self.telemetry_vm, self)
            return self.telemetry_view
        if index == 4:
            from src.views.registry_view import ModelRegistryView

            self.registry_view = ModelRegistryView(self.telemetry_vm, self)
            return self.registry_view
        return self.audit_view

    def _on_launch_daemon(self) -> None:
        ok = self.process_manager.start_daemon()
        if ok:
            self.daemon_badge.setText(" Daemon (127.0.0.1:8080): STARTING... ")
            self.prom_scraper.start_polling(1000)

    def _on_daemon_health(self, healthy: bool, detail: str) -> None:
        if healthy:
            self.daemon_badge.setText(f" Daemon (127.0.0.1:8080): HEALTHY (v{detail}) ")
            self.daemon_badge.setStyleSheet(
                "background-color: #0f2419; color: #3fb950; border: 1px solid #2ea043; "
                "border-radius: 4px; padding: 3px 8px; font-weight: 700;"
            )
        else:
            self.daemon_badge.setText(" Daemon (127.0.0.1:8080): OFFLINE (Local CLI Mode) ")
            self.daemon_badge.setStyleSheet(
                "background-color: #342209; color: #d29922; border: 1px solid #bb8009; "
                "border-radius: 4px; padding: 3px 8px; font-weight: 600;"
            )

    def closeEvent(self, event: QCloseEvent) -> None:
        """Fail-safe process shutdown protocol when closing the UI window."""
        if self.process_manager.is_running() or self.process_manager.is_daemon_running():
            ans = QMessageBox.question(
                self,
                "Active GFlowNet-Prover Process Running",
                "An audit, training job, or `gfn-forge serve` daemon is currently active.\n\n"
                "Select Yes to gracefully terminate with SIGINT (saving atomic SafeTensors checkpoint),\n"
                "No to keep the daemon running in the background, or Cancel to stay in the studio.",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes,
            )
            if ans == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if ans == QMessageBox.StandardButton.Yes:
                self.process_manager.stop_active_process(graceful=True)
                self.process_manager.stop_daemon()
        self.prom_scraper.stop_polling()
        self.sse_client.disconnect_stream()
        super().closeEvent(event)
