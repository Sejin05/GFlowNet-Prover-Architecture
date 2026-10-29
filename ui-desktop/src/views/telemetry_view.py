"""View 4: Operational Telemetry & Drift Monitor (`OperationalTelemetryView`)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.viewmodels.telemetry_vm import TelemetryViewModel
from src.views.widgets.metric_card import MetricCardWidget

pg.setConfigOptions(antialias=True, background="#090c10", foreground="#8b949e")


class OperationalTelemetryView(QWidget):
    """Data & Structural Drift, Concept Drift, 60 FPS PyQtGraph Trends, Hardware Gauges & Logs."""

    def __init__(self, vm: TelemetryViewModel, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.vm = vm
        self._build_ui()
        self._bind_viewmodel()
        self.vm._emit_all_snapshots()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(8)

        # --- Top Row: Structural & Data Drift Dashboard | Concept Drift & Alignment ---
        top_row = QHBoxLayout()

        # 1. Data & Structural Drift Dashboard
        struct_group = QGroupBox("1. Data & Structural Drift Dashboard (gfn-monitor)")
        struct_grid = QGridLayout(struct_group)

        self.card_mmd = MetricCardWidget(
            "GRAPH TOPOLOGY SHIFT (Spectral MMD²)",
            "0.0420",
            "Threshold: MMD² < 0.08",
            "#3fb950",
        )
        self.card_psi = MetricCardWidget(
            "OPCODE HISTOGRAM SHIFT (PSI)",
            "0.0910",
            "Threshold: PSI < 0.15 (Cancun TLOAD/TSTORE)",
            "#58a6ff",
        )
        self.card_js = MetricCardWidget(
            "STORAGE SLOT PACKING SHIFT (D_JS)",
            "0.0380",
            "Threshold: Jensen-Shannon D_JS < 0.10",
            "#79c0ff",
        )
        self.card_ks = MetricCardWidget(
            "RND NOVELTY SATURATION (2-Sample D_KS)",
            "0.1120",
            "Threshold: Kolmogorov-Smirnov D_KS < 0.18",
            "#d2a8ff",
        )

        struct_grid.addWidget(self.card_mmd, 0, 0)
        struct_grid.addWidget(self.card_psi, 0, 1)
        struct_grid.addWidget(self.card_js, 1, 0)
        struct_grid.addWidget(self.card_ks, 1, 1)

        # 2. Concept Drift & Neuro-Symbolic Alignment Gauges
        concept_group = QGroupBox("2. Concept Drift & Neuro-Symbolic Alignment Gauges")
        concept_grid = QGridLayout(concept_group)

        self.card_tb_res = MetricCardWidget(
            "MEDIAN TB RESIDUAL |Δ_TB|",
            "0.380",
            "Alert Threshold: |Δ_TB| > 2.5",
            "#3fb950",
        )
        self.card_smt_eff = MetricCardWidget(
            "SMT HANDOVER EFFICACY (SAT / Total)",
            "14.2%",
            "Narrow Branch Trigger > 0.85",
            "#58a6ff",
        )
        self.card_mismatch = MetricCardWidget(
            "REVM-TO-FORGE REJECTION COUNTER",
            "0 (0.000%)",
            "Strict Zero Tolerance (> 0 triggers P1 Alert)",
            "#3fb950",
        )
        self.card_align_rho = MetricCardWidget(
            "FLOW-REWARD ALIGNMENT (ρ_TB / H_PF)",
            "ρ=0.864 | H=1.44",
            "Target ρ ≥ 0.82 | Entropy ≥ 1.0 nats",
            "#d2a8ff",
        )

        concept_grid.addWidget(self.card_tb_res, 0, 0)
        concept_grid.addWidget(self.card_smt_eff, 0, 1)
        concept_grid.addWidget(self.card_mismatch, 1, 0)
        concept_grid.addWidget(self.card_align_rho, 1, 1)

        top_row.addWidget(struct_group, 1)
        top_row.addWidget(concept_group, 1)

        # --- Middle Row: Live PyQtGraph Operational Telemetry Charts & Hardware Gauges ---
        mid_row = QHBoxLayout()

        charts_group = QGroupBox("3. Real-Time Operational & Drift Time-Series (PyQtGraph 60 FPS)")
        charts_hbox = QHBoxLayout(charts_group)

        self.plot_tps = pg.PlotWidget(title="In-Memory Revm Throughput (TPS / Thread)")
        self.plot_tps.showGrid(x=True, y=True, alpha=0.25)
        self.plot_tps.setYRange(60_000, 82_000)
        self.curve_tps = self.plot_tps.plot(pen=pg.mkPen("#3fb950", width=2.2))
        self.sla_tps_line = pg.InfiniteLine(
            pos=65_000,
            angle=0,
            pen=pg.mkPen("#d29922", width=1.5, style=Qt.PenStyle.DashLine),
            label="SLA ≥ 65K TPS",
            labelOpts={"position": 0.7, "color": "#d29922"},
        )
        self.plot_tps.addItem(self.sla_tps_line)

        self.plot_drift = pg.PlotWidget(title="Structural Drift (MMD² & Opcode PSI)")
        self.plot_drift.showGrid(x=True, y=True, alpha=0.25)
        self.plot_drift.setYRange(0.0, 0.18)
        self.plot_drift.addLegend(offset=(8, 8))
        self.curve_mmd = self.plot_drift.plot(pen=pg.mkPen("#58a6ff", width=2.2), name="Spectral MMD²")
        self.curve_psi = self.plot_drift.plot(pen=pg.mkPen("#d2a8ff", width=2.0), name="Opcode PSI")
        self.mmd_limit_line = pg.InfiniteLine(
            pos=0.08,
            angle=0,
            pen=pg.mkPen("#f85149", width=1.4, style=Qt.PenStyle.DotLine),
            label="MMD² Max 0.08",
            labelOpts={"position": 0.22, "color": "#f85149", "anchors": [(0.5, 0.0), (0.5, 0.0)]},
        )
        self.plot_drift.addItem(self.mmd_limit_line)

        charts_hbox.addWidget(self.plot_tps, 1)
        charts_hbox.addWidget(self.plot_drift, 1)

        # Hardware & System Resource Gauges (:9090/metrics @ 1 Hz)
        hw_group = QGroupBox(
            "4. Hardware & Cache Resource Gauges (Prometheus 127.0.0.1:9090/metrics @ 1 Hz)"
        )
        hw_grid = QGridLayout(hw_group)

        self.vram_bar = QProgressBar()
        self.vram_bar.setRange(0, 240)
        self.vram_bar.setValue(78)
        self.vram_bar.setFormat("GPU VRAM Allocation: 7.8 / 24.0 GB (32.5%)")

        self.cuda_bar = QProgressBar()
        self.cuda_bar.setRange(0, 100)
        self.cuda_bar.setValue(54)
        self.cuda_bar.setFormat("CUDA Core & Tensor Core Utilization: 54.2%")

        self.cpu_bar = QProgressBar()
        self.cpu_bar.setRange(0, 100)
        self.cpu_bar.setValue(68)
        self.cpu_bar.setFormat("CPU Thread Pool Load (revm Rayon Workers): 68.5%")

        self.lmdb_bar = QProgressBar()
        self.lmdb_bar.setRange(0, 320)
        self.lmdb_bar.setValue(14)
        self.lmdb_bar.setFormat("L2 LMDB Persistent Cache Size (heed): 1.4 / 32.0 GB")

        self.l1_cache_bar = QProgressBar()
        self.l1_cache_bar.setRange(0, 100)
        self.l1_cache_bar.setValue(78)
        self.l1_cache_bar.setFormat("L1 DashMap UNSAT Core Cache Hit Ratio: 78.4% (< 0.01ms Fast-Path)")

        self.tps_gauge_lbl = QLabel("In-Memory Revm Arena Throughput: 74,210 TPS / Thread (SLA >= 65,000)")
        self.tps_gauge_lbl.setStyleSheet(
            "color: #3fb950; font-family: 'Cascadia Code', monospace; font-weight: 700; padding: 4px;"
        )

        hw_grid.addWidget(self.vram_bar, 0, 0)
        hw_grid.addWidget(self.cuda_bar, 0, 1)
        hw_grid.addWidget(self.cpu_bar, 1, 0)
        hw_grid.addWidget(self.lmdb_bar, 1, 1)
        hw_grid.addWidget(self.l1_cache_bar, 2, 0)
        hw_grid.addWidget(self.tps_gauge_lbl, 2, 1)

        mid_row.addWidget(charts_group, 5)
        mid_row.addWidget(hw_group, 5)

        # --- Bottom Panel: Self-Healing & Diagnostic Logging Terminal ---
        log_group = QGroupBox("5. Diagnostic Logging Terminal & Self-Healing Event Stream")
        log_layout = QVBoxLayout(log_group)

        log_toolbar = QHBoxLayout()
        self.poll_status_lbl = QLabel("Prometheus Scraper: ACTIVE (127.0.0.1:9090/metrics @ 1.0 Hz)")
        self.poll_status_lbl.setStyleSheet("color: #58a6ff; font-weight: 600;")
        self.clear_log_btn = QPushButton("Clear Diagnostic Terminal")
        log_toolbar.addWidget(self.poll_status_lbl)
        log_toolbar.addStretch()
        log_toolbar.addWidget(self.clear_log_btn)

        self.log_terminal = QPlainTextEdit()
        self.log_terminal.setReadOnly(True)
        self.clear_log_btn.clicked.connect(self.log_terminal.clear)

        initial_logs = [
            "[20:14:02] [INFO] [gfn-monitor] Prometheus exporter initialized at http://127.0.0.1:9090/metrics (1 Hz).",
            "[20:14:05] [INFO] [gfn-symbolic] L1 DashMap Unsat cache hit on xxh3_128(0x4a9b...): SmtStatus::Unsat returned in 0.008 ms.",
            "[20:15:44] [INFO] [gfn-evm] Step 2 candidate branch boundary proximity = 0.891 (> 0.85). Dispatched to Bitwuzla 0.6.0 QF_BV pool.",
            "[20:15:45] [INFO] [gfn-symbolic] Bitwuzla worker thread 2 solved SAT witness in 41.6 ms. Concretizing calldata U256.",
            "[20:16:11] [SUCCESS] [gfn-verifier] Candidate exploit verified by `forge test -vvvv --offline`. 0.0% False Positive Gate confirmed.",
        ]
        self.log_terminal.setPlainText("\n".join(initial_logs))

        log_layout.addLayout(log_toolbar)
        log_layout.addWidget(self.log_terminal, 1)

        root_layout.addLayout(top_row)
        root_layout.addLayout(mid_row, 1)
        root_layout.addWidget(log_group, 1)

    def _bind_viewmodel(self) -> None:
        self.vm.drift_metrics_updated.connect(self._on_drift_updated)
        self.vm.hardware_metrics_updated.connect(self._on_hw_updated)
        self.vm.diagnostic_log_appended.connect(self.append_log)

    def append_log(self, line: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_terminal.appendPlainText(f"[{ts}] {line}")

    def _on_drift_updated(self, d: Dict[str, Any]) -> None:
        mmd2 = float(d.get("mmd2", 0.042))
        psi = float(d.get("psi", 0.091))
        js = float(d.get("js", 0.038))
        ks = float(d.get("ks", 0.112))
        tb_res = float(d.get("tb_residual", 0.38))
        smt_eff = float(d.get("smt_efficacy_pct", 14.2))
        mismatch = int(d.get("revm_forge_mismatch", 0))
        rho = float(d.get("spearman_rho", 0.864))
        ent = float(d.get("policy_entropy", 1.44))

        self.card_mmd.set_value(f"{mmd2:.4f}")
        self.card_mmd.set_status_badge("SAFE < 0.08" if mmd2 < 0.08 else "DRIFT ALERT", "ok" if mmd2 < 0.08 else "alert")

        self.card_psi.set_value(f"{psi:.4f}")
        self.card_psi.set_status_badge("SAFE < 0.15" if psi < 0.15 else "SHIFT ALERT", "ok" if psi < 0.15 else "alert")

        self.card_js.set_value(f"{js:.4f}")
        self.card_js.set_status_badge("SAFE < 0.10" if js < 0.10 else "PACKING SHIFT", "ok" if js < 0.10 else "alert")

        self.card_ks.set_value(f"{ks:.4f}")
        self.card_ks.set_status_badge("SAFE < 0.18" if ks < 0.18 else "RND SATURATED", "ok" if ks < 0.18 else "alert")

        self.card_tb_res.set_value(f"{tb_res:.3f}")
        self.card_tb_res.set_status_badge("OK <= 2.5" if tb_res <= 2.5 else "RESIDUAL > 2.5", "ok" if tb_res <= 2.5 else "alert")

        self.card_smt_eff.set_value(f"{smt_eff:.1f}% SAT")
        self.card_smt_eff.set_status_badge("OPTIMAL" if smt_eff >= 5.0 else "LOW EFFICACY", "ok" if smt_eff >= 5.0 else "warn")

        if mismatch == 0:
            self.card_mismatch.set_value("0 (0.000% FPR)")
            self.card_mismatch.set_status_badge("P1 = 0 (PASS)", "ok")
        else:
            self.card_mismatch.set_value(f"{mismatch} (>0.0% FPR!)")
            self.card_mismatch.set_status_badge("P1 ALERT!", "alert")

        self.card_align_rho.set_value(f"ρ={rho:.3f} | H={ent:.2f}")
        if rho >= 0.82 and ent >= 1.0:
            self.card_align_rho.set_status_badge("ALIGNED (PASS)", "ok")
        elif ent < 0.35:
            self.card_align_rho.set_status_badge("MODE COLLAPSE", "alert")
        else:
            self.card_align_rho.set_status_badge("WARMING UP", "warn")

        self.curve_tps.setData(self.vm.tick_history, self.vm.tps_history)
        self.curve_mmd.setData(self.vm.tick_history, self.vm.mmd2_history)
        self.curve_psi.setData(self.vm.tick_history, self.vm.psi_history)

    def _on_hw_updated(self, hw: Dict[str, Any]) -> None:
        vram_u = float(hw.get("gpu_vram_used_gb", 7.8))
        vram_t = float(hw.get("gpu_vram_total_gb", 24.0))
        cuda_pct = float(hw.get("cuda_util_pct", 54.0))
        cpu_pct = float(hw.get("cpu_rayon_load_pct", 68.0))
        lmdb_u = float(hw.get("lmdb_cache_used_gb", 1.4))
        lmdb_t = float(hw.get("lmdb_cache_max_gb", 32.0))
        l1_hit = float(hw.get("l1_unsat_hit_ratio_pct", 78.4))
        tps = float(hw.get("revm_tps_per_thread", 74_210.0))

        vram_pct = (vram_u / max(0.1, vram_t)) * 100.0
        self.vram_bar.setMaximum(int(vram_t * 10))
        self.vram_bar.setValue(int(vram_u * 10))
        self.vram_bar.setFormat(f"GPU VRAM Allocation: {vram_u:.1f} / {vram_t:.1f} GB ({vram_pct:.1f}%)")

        self.cuda_bar.setValue(int(cuda_pct))
        self.cuda_bar.setFormat(f"CUDA Core & Tensor Core Utilization: {cuda_pct:.1f}%")

        self.cpu_bar.setValue(int(cpu_pct))
        self.cpu_bar.setFormat(f"CPU Thread Pool Load (revm Rayon Workers): {cpu_pct:.1f}%")

        lmdb_pct = (lmdb_u / max(0.1, lmdb_t)) * 100.0
        self.lmdb_bar.setMaximum(int(lmdb_t * 10))
        self.lmdb_bar.setValue(int(lmdb_u * 10))
        self.lmdb_bar.setFormat(f"L2 LMDB Persistent Cache Size (heed): {lmdb_u:.1f} / {lmdb_t:.1f} GB ({lmdb_pct:.1f}%)")

        self.l1_cache_bar.setValue(int(l1_hit))
        self.l1_cache_bar.setFormat(f"L1 DashMap UNSAT Core Cache Hit Ratio: {l1_hit:.1f}% (< 0.01ms Fast-Path)")

        self.tps_gauge_lbl.setText(
            f"In-Memory Revm Arena Throughput: {tps:,.0f} TPS / Thread (SLA >= 65,000)"
        )
