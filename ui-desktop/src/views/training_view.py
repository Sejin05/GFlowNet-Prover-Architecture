"""View 2: Intuitive Multi-Phase Training Studio (`TrainingStudioView`)."""

from __future__ import annotations

from typing import Any, Dict, Optional

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.config import TRAINING_PRESETS, TrainingHyperparameters
from src.viewmodels.training_vm import TrainingViewModel
from src.views.widgets.metric_card import MetricCardWidget

pg.setConfigOptions(antialias=True, background="#090c10", foreground="#8b949e")


class TrainingStudioView(QWidget):
    """3-Step Training Setup Wizard and Live 60 FPS PyQtGraph Telemetry Dashboard."""

    def __init__(self, vm: TrainingViewModel, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.vm = vm
        self._updating_widgets: bool = False
        self._build_ui()
        self._wire_input_changes()
        self._bind_viewmodel()
        self._sync_widgets_from_hp(self.vm.hp)
        self._refresh_charts()
        self._init_kpi_cards()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(8)

        # --- Visual 3-Step Wizard Stepper Banner ---
        stepper_frame = QFrame(self)
        stepper_frame.setObjectName("CardFrame")
        stepper_hbox = QHBoxLayout(stepper_frame)
        stepper_hbox.setContentsMargins(14, 7, 14, 7)
        self.step_badge_1 = QLabel("① Phase 2 Active: Curriculum Trajectory Balance")
        self.step_badge_1.setStyleSheet("color: #58a6ff; font-weight: 700; font-size: 12px;")
        self.step_badge_2 = QLabel("──►  ② Hyperparameters, Stability Guard & Hardware  ──►")
        self.step_badge_2.setStyleSheet("color: #3fb950; font-weight: 700; font-size: 12px;")
        self.step_badge_3 = QLabel("③ Pipeline Execution & Live 60 FPS Telemetry")
        self.step_badge_3.setStyleSheet("color: #d2a8ff; font-weight: 700; font-size: 12px;")
        stepper_hbox.addWidget(self.step_badge_1)
        stepper_hbox.addStretch()
        stepper_hbox.addWidget(self.step_badge_2)
        stepper_hbox.addStretch()
        stepper_hbox.addWidget(self.step_badge_3)
        root_layout.addWidget(stepper_frame)

        # --- Step 1: Phase Selection Wizard Header ---
        step1_group = QGroupBox("Step 1: Tri-Phase Neuro-Symbolic Training Objective Selection")
        step1_layout = QHBoxLayout(step1_group)

        self.phase_btn_group = QButtonGroup(self)
        self.radio_p1 = QRadioButton(
            "Phase 1: MSTM Self-Supervised Pre-train (L_BCE + L_CE + Smooth L_Huber, 30% Mask)"
        )
        self.radio_p2 = QRadioButton(
            "Phase 2: Curriculum Trajectory Balance (Huber L_TB, Dual LR η_θ / η_Z)"
        )
        self.radio_p3 = QRadioButton(
            "Phase 3: Continual Learning with EWC (Fisher Clamped λ_EWC = 400.0)"
        )
        self.radio_p2.setChecked(True)

        self.phase_btn_group.addButton(self.radio_p1, 1)
        self.phase_btn_group.addButton(self.radio_p2, 2)
        self.phase_btn_group.addButton(self.radio_p3, 3)
        self.phase_btn_group.idToggled.connect(self._on_phase_toggled)

        step1_layout.addWidget(self.radio_p1)
        step1_layout.addWidget(self.radio_p2)
        step1_layout.addWidget(self.radio_p3)

        # --- Step 2: Hyperparameters, Presets & Corpus ---
        step2_group = QGroupBox("Step 2: Hyperparameters, Stability Guard, Reward Mixing (α, β, γ) & Hardware")
        step2_layout = QVBoxLayout(step2_group)

        preset_bar = QHBoxLayout()
        preset_bar.addWidget(QLabel("Preset Profile:"))
        self.preset_combo = QComboBox()
        for name in TRAINING_PRESETS:
            self.preset_combo.addItem(name)
        self.preset_combo.setCurrentText("Production DeFi Tuning")
        self.preset_combo.currentTextChanged.connect(self.vm.apply_preset)

        self.reset_defaults_btn = QPushButton("Reset Defaults")
        self.load_toml_btn = QPushButton("Load TOML Config")
        self.save_toml_btn = QPushButton("Save TOML Config")
        self.reset_defaults_btn.clicked.connect(self.vm.reset_defaults)
        self.load_toml_btn.clicked.connect(self._on_load_toml)
        self.save_toml_btn.clicked.connect(self._on_save_toml)

        preset_bar.addWidget(self.preset_combo, 1)
        preset_bar.addWidget(self.reset_defaults_btn)
        preset_bar.addWidget(self.load_toml_btn)
        preset_bar.addWidget(self.save_toml_btn)
        step2_layout.addLayout(preset_bar)

        hp_grid = QGridLayout()

        # Column 1: Optimization & TB Loss
        col1_form = QFormLayout()
        self.lr_policy_spin = QDoubleSpinBox()
        self.lr_policy_spin.setDecimals(6)
        self.lr_policy_spin.setRange(1e-6, 1e-1)
        self.lr_policy_spin.setSingleStep(1e-4)

        self.lr_logz_spin = QDoubleSpinBox()
        self.lr_logz_spin.setDecimals(6)
        self.lr_logz_spin.setRange(1e-5, 1.0)
        self.lr_logz_spin.setSingleStep(1e-3)

        self.huber_delta_spin = QDoubleSpinBox()
        self.huber_delta_spin.setDecimals(2)
        self.huber_delta_spin.setRange(1.0, 100.0)

        self.ewc_lambda_spin = QDoubleSpinBox()
        self.ewc_lambda_spin.setDecimals(1)
        self.ewc_lambda_spin.setRange(1.0, 10000.0)

        mask_epoch_row = QHBoxLayout()
        self.mask_ratio_spin = QDoubleSpinBox()
        self.mask_ratio_spin.setDecimals(2)
        self.mask_ratio_spin.setRange(0.05, 0.90)
        self.mask_ratio_spin.setSingleStep(0.05)
        self.epochs_spin = QSpinBox()
        self.epochs_spin.setRange(1, 500)
        mask_epoch_row.addWidget(self.mask_ratio_spin)
        mask_epoch_row.addWidget(QLabel("Epochs:"))
        mask_epoch_row.addWidget(self.epochs_spin)

        self.lr_policy_spin.setToolTip("Peak forward/backward policy learning rate η_θ (Cosine Annealing schedule)")
        self.lr_logz_spin.setToolTip("Dedicated log-partition network learning rate η_Z (10-33x policy LR)")
        self.huber_delta_spin.setToolTip("Huber transition threshold δ_TB clamping large Trajectory Balance residuals")
        self.ewc_lambda_spin.setToolTip("Elastic Weight Consolidation Fisher penalty weight λ_EWC (Phase 3)")

        col1_form.addRow("Policy LR (η_θ):", self.lr_policy_spin)
        col1_form.addRow("Partition Log-Z LR (η_Z):", self.lr_logz_spin)
        col1_form.addRow("Huber Delta (δ_TB):", self.huber_delta_spin)
        col1_form.addRow("EWC Penalty (λ_EWC):", self.ewc_lambda_spin)
        col1_form.addRow("MSTM Mask Ratio:", mask_epoch_row)

        stab_row1 = QHBoxLayout()
        self.grad_clip_spin = QDoubleSpinBox()
        self.grad_clip_spin.setDecimals(2)
        self.grad_clip_spin.setRange(0.05, 20.0)
        self.grad_clip_spin.setSingleStep(0.10)
        self.grad_clip_spin.setToolTip("Global L2 gradient norm ceiling G_max (projects ‖∇_θ L‖₂ ≤ G_max)")
        self.warmup_steps_spin = QSpinBox()
        self.warmup_steps_spin.setRange(10, 50_000)
        self.warmup_steps_spin.setSingleStep(250)
        self.warmup_steps_spin.setToolTip("Linear learning-rate warmup steps before Cosine Annealing decay")
        stab_row1.addWidget(self.grad_clip_spin)
        stab_row1.addWidget(QLabel("Warmup:"))
        stab_row1.addWidget(self.warmup_steps_spin)
        col1_form.addRow("Grad Clip ‖g‖₂:", stab_row1)

        # Column 2: Composite Reward R(s_n) & SMT Handover
        col2_form = QFormLayout()
        self.alpha_spin = QDoubleSpinBox()
        self.alpha_spin.setDecimals(2)
        self.alpha_spin.setRange(0.0, 50.0)
        self.alpha_spin.setToolTip("Branch boundary proximity reward weight α")

        self.beta_spin = QDoubleSpinBox()
        self.beta_spin.setDecimals(2)
        self.beta_spin.setRange(0.0, 50.0)
        self.beta_spin.setToolTip("Winsorized RND storage curiosity reward weight β")

        self.gamma_spin = QDoubleSpinBox()
        self.gamma_spin.setDecimals(1)
        self.gamma_spin.setRange(1.0, 5000.0)
        self.gamma_spin.setToolTip("Terminal concrete invariant violation reward multiplier γ")

        self.smt_thresh_spin = QDoubleSpinBox()
        self.smt_thresh_spin.setDecimals(2)
        self.smt_thresh_spin.setRange(0.50, 0.99)
        self.smt_thresh_spin.setSingleStep(0.01)
        self.smt_thresh_spin.setToolTip("Normalized branch distance threshold d_norm triggering Bitwuzla QF_BV handover")

        self.val_chk = QCheckBox("Every 500 Gradient Steps (Diagonal Fisher Update)")
        self.val_chk.setChecked(True)

        stab_row2 = QHBoxLayout()
        self.ema_decay_spin = QDoubleSpinBox()
        self.ema_decay_spin.setDecimals(3)
        self.ema_decay_spin.setRange(0.500, 0.999)
        self.ema_decay_spin.setSingleStep(0.010)
        self.ema_decay_spin.setToolTip("Exponential moving average smoothing factor β_EMA for L_TB spike detection")
        self.spike_guard_chk = QCheckBox("Cosine LR + Spike Guard")
        self.spike_guard_chk.setChecked(True)
        self.spike_guard_chk.setToolTip("Automatically damps step size by 0.5x on >2.5x residual spikes and skips NaN steps")
        stab_row2.addWidget(self.ema_decay_spin)
        stab_row2.addWidget(self.spike_guard_chk)

        col2_form.addRow("Boundary Weight (α):", self.alpha_spin)
        col2_form.addRow("RND Novelty Weight (β):", self.beta_spin)
        col2_form.addRow("Exploit Realization (γ):", self.gamma_spin)
        col2_form.addRow("SMT Handover Threshold:", self.smt_thresh_spin)
        col2_form.addRow("Continuous Validation:", self.val_chk)
        col2_form.addRow("EMA Decay & Guard:", stab_row2)

        # Column 3: Hardware, Replay Buffer & Corpus
        col3_form = QFormLayout()
        dev_worker_row = QHBoxLayout()
        self.device_combo = QComboBox()
        self.device_combo.addItems(
            [
                "CUDA GPU 0 (Kind::BFloat16 + CUDA Graphs)",
                "Multi-GPU 4x A100 NVLink (NCCL All-Reduce)",
                "CPU Fallback (Kind::Float32)",
            ]
        )
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 128)
        self.workers_spin.setSuffix(" threads")
        dev_worker_row.addWidget(self.device_combo, 1)
        dev_worker_row.addWidget(self.workers_spin)

        self.replay_spin = QSpinBox()
        self.replay_spin.setRange(1000, 1_000_000)
        self.replay_spin.setSingleStep(10_000)

        corpus_row = QHBoxLayout()
        self.corpus_edit = QLineEdit(self.vm.hp.corpus_dir)
        self.browse_corpus_btn = QPushButton("Browse")
        self.browse_corpus_btn.clicked.connect(self._on_browse_corpus)
        corpus_row.addWidget(self.corpus_edit, 1)
        corpus_row.addWidget(self.browse_corpus_btn)

        self.ckpt_out_edit = QLineEdit(self.vm.hp.checkpoint_out)
        self.anchor_edit = QLineEdit(self.vm.hp.anchor_checkpoint)

        col3_form.addRow("Device & Revm Workers:", dev_worker_row)
        col3_form.addRow("PER Replay Capacity:", self.replay_spin)
        col3_form.addRow("Training Corpus Dir:", corpus_row)
        col3_form.addRow("Output SafeTensors:", self.ckpt_out_edit)
        col3_form.addRow("Anchor Checkpoint:", self.anchor_edit)

        hp_grid.addLayout(col1_form, 0, 0)
        hp_grid.addLayout(col2_form, 0, 1)
        hp_grid.addLayout(col3_form, 0, 2)
        step2_layout.addLayout(hp_grid)

        # --- Step 3: Execution & CLI Script Export ---
        step3_group = QGroupBox("Step 3: Pipeline Execution & Reproducible CLI Export")
        step3_layout = QHBoxLayout(step3_group)

        self.launch_btn = QPushButton("▶ Launch Training Pipeline")
        self.launch_btn.setObjectName("PrimaryButton")
        self.stop_train_btn = QPushButton("■ Stop Pipeline")
        self.stop_train_btn.setObjectName("DangerButton")
        self.export_cli_btn = QPushButton("Copy CLI Command (`gfn-forge ...`)")
        self.export_cli_btn.setObjectName("AccentButton")
        self.cli_preview_edit = QLineEdit()
        self.cli_preview_edit.setReadOnly(True)

        self.launch_btn.clicked.connect(self._on_launch_training)
        self.stop_train_btn.clicked.connect(self.vm.stop_training)
        self.export_cli_btn.clicked.connect(self._on_export_cli)

        step3_layout.addWidget(self.launch_btn)
        step3_layout.addWidget(self.stop_train_btn)
        step3_layout.addWidget(self.export_cli_btn)
        step3_layout.addWidget(self.cli_preview_edit, 1)

        # --- Live Real-Time Telemetry Dashboard (PyQtGraph 60 FPS) ---
        dash_group = QGroupBox("Live Real-Time Training Telemetry (PyQtGraph Hardware-Accelerated 60 FPS)")
        dash_layout = QVBoxLayout(dash_group)

        kpi_row = QHBoxLayout()
        self.card_loss = MetricCardWidget(
            "TRAJECTORY BALANCE LOSS (L_TB)", "0.384 (EMA 0.391)", "Huber Clipped @ δ_TB = 10.0 | EMA Overlay", "#58a6ff"
        )
        self.card_loss.set_status_badge("CONVERGING", "normal")
        self.card_rho = MetricCardWidget(
            "SPEARMAN RANK CORRELATION (ρ_TB)", "0.864", "Target SLA: ρ ≥ 0.82", "#3fb950"
        )
        self.card_rho.set_status_badge("SLA PASS", "ok")
        self.card_entropy = MetricCardWidget(
            "POLICY ENTROPY H(P_F)", "1.42 nats", "Healthy ≥ 1.0 | Collapse < 0.35", "#3fb950"
        )
        self.card_entropy.set_status_badge("HEALTHY EXPLORATION", "ok")
        self.card_logz = MetricCardWidget(
            "PARTITION LOG Z_θ", "18.231 ± 0.004", "Stationary Flow Conservation", "#d2a8ff"
        )
        self.card_logz.set_status_badge("STATIONARY", "normal")
        self.card_stability = MetricCardWidget(
            "GRADIENT NORM ‖g‖₂ & GUARD", "0.382 (≤ 1.00)", "Cosine Warmup + Clip ≤ 1.00", "#f0883e"
        )
        self.card_stability.set_status_badge("STABLE", "ok")

        kpi_row.addWidget(self.card_loss)
        kpi_row.addWidget(self.card_rho)
        kpi_row.addWidget(self.card_entropy)
        kpi_row.addWidget(self.card_logz)
        kpi_row.addWidget(self.card_stability)
        dash_layout.addLayout(kpi_row)

        charts_row = QHBoxLayout()

        self.plot_loss = pg.PlotWidget(title="Trajectory Balance Loss L_TB(τ) & EMA Trend")
        self.plot_loss.showGrid(x=True, y=True, alpha=0.25)
        self.plot_loss.setLabel("bottom", "Gradient Step")
        self.plot_loss.setLabel("left", "L_TB")
        self.plot_loss.addLegend(offset=(8, 8))
        self.curve_loss = self.plot_loss.plot(pen=pg.mkPen("#58a6ff", width=1.8), name="Raw L_TB")
        self.curve_loss_ema = self.plot_loss.plot(
            pen=pg.mkPen("#f0883e", width=2.2, style=Qt.PenStyle.DashLine), name="EMA L_TB"
        )
        self.scatter_huber = pg.ScatterPlotItem(
            size=7, brush=pg.mkBrush("#f85149"), pen=pg.mkPen("#ffffff", width=1), name="Huber Clipped"
        )
        self.plot_loss.addItem(self.scatter_huber)

        self.plot_rho = pg.PlotWidget(title="Spearman Flow Correlation ρ_TB (log P_F vs log R)")
        self.plot_rho.showGrid(x=True, y=True, alpha=0.25)
        self.plot_rho.setLabel("bottom", "Gradient Step")
        self.plot_rho.setLabel("left", "Spearman ρ")
        self.plot_rho.setYRange(0.0, 1.02)
        self.curve_rho = self.plot_rho.plot(pen=pg.mkPen("#3fb950", width=2))
        self.target_line_rho = pg.InfiniteLine(
            pos=0.82,
            angle=0,
            pen=pg.mkPen("#d29922", width=1.8, style=Qt.PenStyle.DashLine),
            label="SLA Target ≥ 0.82",
            labelOpts={"position": 0.75, "color": "#d29922"},
        )
        self.plot_rho.addItem(self.target_line_rho)

        self.plot_entropy = pg.PlotWidget(title="Composite 4-Head Policy Entropy H(P_F) [nats]")
        self.plot_entropy.showGrid(x=True, y=True, alpha=0.25)
        self.plot_entropy.setLabel("bottom", "Gradient Step")
        self.plot_entropy.setLabel("left", "Entropy (nats)")
        self.curve_entropy = self.plot_entropy.plot(pen=pg.mkPen("#d2a8ff", width=2))
        self.line_collapse = pg.InfiniteLine(
            pos=0.35,
            angle=0,
            pen=pg.mkPen("#f85149", width=1.5, style=Qt.PenStyle.DashLine),
            label="Mode Collapse < 0.35",
            labelOpts={"position": 0.7, "color": "#f85149"},
        )
        self.line_healthy = pg.InfiniteLine(
            pos=1.0,
            angle=0,
            pen=pg.mkPen("#3fb950", width=1.5, style=Qt.PenStyle.DotLine),
            label="Healthy ≥ 1.0",
            labelOpts={"position": 0.7, "color": "#3fb950"},
        )
        self.plot_entropy.addItem(self.line_collapse)
        self.plot_entropy.addItem(self.line_healthy)

        charts_row.addWidget(self.plot_loss, 1)
        charts_row.addWidget(self.plot_rho, 1)
        charts_row.addWidget(self.plot_entropy, 1)
        dash_layout.addLayout(charts_row, 1)

        modes_row = QHBoxLayout()
        modes_lbl = QLabel("Discovered Exploit Archetype Mode Coverage (Modes@K on MultiBug-Bench):")
        modes_lbl.setStyleSheet("font-weight: 700; color: #d0d7de;")
        self.modes_bar = QProgressBar()
        self.modes_bar.setRange(0, 16)
        self.modes_bar.setValue(14)
        self.modes_bar.setFormat("14 / 16 Distinct Exploit Modes Discovered (87.5% ≥ 85.0% Target)")
        modes_row.addWidget(modes_lbl)
        modes_row.addWidget(self.modes_bar, 1)
        dash_layout.addLayout(modes_row)

        root_layout.addWidget(step1_group)
        root_layout.addWidget(step2_group)
        root_layout.addWidget(step3_group)
        root_layout.addWidget(dash_group, 1)

    def _bind_viewmodel(self) -> None:
        self.vm.hyperparams_changed.connect(self._sync_widgets_from_hp)
        self.vm.telemetry_step_emitted.connect(self._on_telemetry_step)
        self.vm.training_state_changed.connect(self._on_training_state_changed)

    def _wire_input_changes(self) -> None:
        inputs = [
            self.lr_policy_spin.valueChanged,
            self.lr_logz_spin.valueChanged,
            self.huber_delta_spin.valueChanged,
            self.ewc_lambda_spin.valueChanged,
            self.mask_ratio_spin.valueChanged,
            self.epochs_spin.valueChanged,
            self.grad_clip_spin.valueChanged,
            self.warmup_steps_spin.valueChanged,
            self.ema_decay_spin.valueChanged,
            self.spike_guard_chk.toggled,
            self.workers_spin.valueChanged,
            self.alpha_spin.valueChanged,
            self.beta_spin.valueChanged,
            self.gamma_spin.valueChanged,
            self.smt_thresh_spin.valueChanged,
            self.replay_spin.valueChanged,
            self.corpus_edit.textChanged,
            self.ckpt_out_edit.textChanged,
            self.anchor_edit.textChanged,
            self.device_combo.currentTextChanged,
        ]
        for sig in inputs:
            sig.connect(self._on_input_changed)

    def _on_input_changed(self, *args: Any) -> None:
        if self._updating_widgets:
            return
        self._sync_hp_from_widgets()
        self.cli_preview_edit.setText(self.vm.build_cli_command())

    def _on_training_state_changed(self, is_running: bool, status_msg: str) -> None:
        self.launch_btn.setEnabled(not is_running)
        self.stop_train_btn.setEnabled(is_running)
        if is_running:
            self.launch_btn.setText("▶ Training In Progress...")
            self.step_badge_3.setText(f"③ Active: {status_msg}")
        else:
            self.launch_btn.setText("▶ Launch Training Pipeline")
            self.step_badge_3.setText("③ Pipeline Idle / Stopped")

    def _init_kpi_cards(self) -> None:
        last_loss = self.vm.loss_tb_history[-1] if self.vm.loss_tb_history else 0.384
        last_ema = self.vm.loss_ema_history[-1] if self.vm.loss_ema_history else 0.391
        last_rho = self.vm.spearman_rho_history[-1] if self.vm.spearman_rho_history else 0.864
        last_ent = self.vm.entropy_history[-1] if self.vm.entropy_history else 1.42
        self._on_telemetry_step(
            {
                "loss_tb": last_loss,
                "loss_tb_ema": last_ema,
                "grad_norm": self.vm.current_grad_norm,
                "stability_status": self.vm.stability_status,
                "spearman_rho": last_rho,
                "policy_entropy": last_ent,
                "log_z": self.vm.log_z_estimate,
                "modes_discovered": self.vm.modes_discovered,
                "modes_total": self.vm.modes_total,
            }
        )

    def _on_phase_toggled(self, phase_id: int, checked: bool) -> None:
        if checked:
            self.vm.set_phase(phase_id)
            phase_labels = {
                1: "① Phase 1 Active: MSTM Self-Supervised Pre-train",
                2: "① Phase 2 Active: Curriculum Trajectory Balance",
                3: "① Phase 3 Active: Continual Learning with EWC",
            }
            self.step_badge_1.setText(phase_labels.get(phase_id, "① Phase Objective Select"))

    def _sync_widgets_from_hp(self, hp: TrainingHyperparameters) -> None:
        self._updating_widgets = True
        try:
            self.phase_btn_group.blockSignals(True)
            if hp.phase == 1:
                self.radio_p1.setChecked(True)
            elif hp.phase == 2:
                self.radio_p2.setChecked(True)
            elif hp.phase == 3:
                self.radio_p3.setChecked(True)
            self.phase_btn_group.blockSignals(False)

            phase_labels = {
                1: "① Phase 1 Active: MSTM Self-Supervised Pre-train",
                2: "① Phase 2 Active: Curriculum Trajectory Balance",
                3: "① Phase 3 Active: Continual Learning with EWC",
            }
            self.step_badge_1.setText(phase_labels.get(hp.phase, "① Phase Objective Select"))

            if hasattr(hp, "preset_name") and hp.preset_name:
                self.preset_combo.blockSignals(True)
                idx = self.preset_combo.findText(hp.preset_name)
                if idx >= 0:
                    self.preset_combo.setCurrentIndex(idx)
                self.preset_combo.blockSignals(False)

            self.lr_policy_spin.setValue(hp.lr_policy)
            self.lr_logz_spin.setValue(hp.lr_logz if hasattr(hp, "lr_logz") else hp.lr_log_z)
            self.huber_delta_spin.setValue(hp.huber_delta)
            self.ewc_lambda_spin.setValue(hp.lambda_ewc)
            self.mask_ratio_spin.setValue(hp.mask_ratio)
            self.epochs_spin.setValue(hp.epochs)
            self.grad_clip_spin.setValue(hp.clip_grad_norm)
            self.warmup_steps_spin.setValue(hp.lr_warmup_steps)
            self.ema_decay_spin.setValue(hp.ema_decay)
            self.spike_guard_chk.setChecked(hp.enable_grad_spike_guard)
            self.workers_spin.setValue(hp.worker_threads)
            self.alpha_spin.setValue(hp.alpha_boundary)
            self.beta_spin.setValue(hp.beta_novelty)
            self.gamma_spin.setValue(hp.gamma_exploit)
            self.smt_thresh_spin.setValue(hp.boundary_trigger)
            self.replay_spin.setValue(hp.replay_capacity)
            self.corpus_edit.setText(hp.corpus_dir)
            self.ckpt_out_edit.setText(hp.checkpoint_out)
            self.anchor_edit.setText(hp.anchor_checkpoint)

            if hasattr(hp, "compute_device") and hp.compute_device:
                self.device_combo.blockSignals(True)
                idx = self.device_combo.findText(hp.compute_device)
                if idx >= 0:
                    self.device_combo.setCurrentIndex(idx)
                self.device_combo.blockSignals(False)

            self.cli_preview_edit.setText(self.vm.build_cli_command())
        finally:
            self._updating_widgets = False

    def _sync_hp_from_widgets(self) -> None:
        hp = self.vm.hp
        checked_phase = self.phase_btn_group.checkedId()
        if checked_phase in (1, 2, 3):
            hp.phase = checked_phase
        hp.preset_name = self.preset_combo.currentText()
        hp.lr_policy = self.lr_policy_spin.value()
        hp.lr_log_z = self.lr_logz_spin.value()
        hp.huber_delta = self.huber_delta_spin.value()
        hp.lambda_ewc = self.ewc_lambda_spin.value()
        hp.mask_ratio = self.mask_ratio_spin.value()
        hp.epochs = self.epochs_spin.value()
        hp.clip_grad_norm = self.grad_clip_spin.value()
        hp.lr_warmup_steps = self.warmup_steps_spin.value()
        hp.ema_decay = self.ema_decay_spin.value()
        hp.enable_grad_spike_guard = self.spike_guard_chk.isChecked()
        hp.worker_threads = self.workers_spin.value()
        hp.alpha_boundary = self.alpha_spin.value()
        hp.beta_novelty = self.beta_spin.value()
        hp.gamma_exploit = self.gamma_spin.value()
        hp.boundary_trigger = self.smt_thresh_spin.value()
        hp.replay_capacity = self.replay_spin.value()
        hp.corpus_dir = self.corpus_edit.text().strip() or "data/corpus"
        hp.checkpoint_out = self.ckpt_out_edit.text().strip() or "checkpoints/curriculum_tb.safetensors"
        hp.anchor_checkpoint = self.anchor_edit.text().strip() or "checkpoints/pretrained_mstm.safetensors"
        hp.compute_device = self.device_combo.currentText()

    def _on_browse_corpus(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Training Corpus Directory", self.corpus_edit.text())
        if folder:
            self.corpus_edit.setText(folder)
            self._sync_hp_from_widgets()

    def _on_load_toml(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Training TOML Configuration",
            str(self.vm.process_manager.workspace_root / "configs"),
            "TOML Files (*.toml)",
        )
        if path:
            self.vm.load_toml(path)

    def _on_save_toml(self) -> None:
        self._sync_hp_from_widgets()
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Training TOML Configuration",
            str(self.vm.process_manager.workspace_root / "configs" / "custom_training.toml"),
            "TOML Files (*.toml)",
        )
        if path:
            self.vm.save_toml(path)

    def _on_export_cli(self) -> None:
        self._sync_hp_from_widgets()
        cmd = self.vm.build_cli_command()
        self.cli_preview_edit.setText(cmd)
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(cmd)

    def _on_launch_training(self) -> None:
        self._sync_hp_from_widgets()
        self.cli_preview_edit.setText(self.vm.build_cli_command())
        self.vm.start_training()

    def _refresh_charts(self) -> None:
        self.curve_loss.setData(self.vm.steps_history, self.vm.loss_tb_history)
        self.curve_loss_ema.setData(self.vm.steps_history, self.vm.loss_ema_history)
        self.scatter_huber.setData(self.vm.huber_clipped_steps, self.vm.huber_clipped_vals)
        self.curve_rho.setData(self.vm.steps_history, self.vm.spearman_rho_history)
        self.curve_entropy.setData(self.vm.steps_history, self.vm.entropy_history)

    def _on_telemetry_step(self, data: Dict[str, Any]) -> None:
        self._refresh_charts()
        loss_tb = float(data.get("loss_tb", 0.38))
        loss_ema = float(data.get("loss_tb_ema", loss_tb))
        grad_norm = float(data.get("grad_norm", 0.38))
        stab_status = str(data.get("stability_status", "STABLE"))
        rho = float(data.get("spearman_rho", 0.86))
        entropy = float(data.get("policy_entropy", 1.42))
        log_z = float(data.get("log_z", 18.231))
        modes_disc = int(data.get("modes_discovered", 14))
        modes_tot = int(data.get("modes_total", 16))

        self.card_loss.set_value(f"{loss_tb:.3f} (EMA {loss_ema:.3f})")
        self.card_rho.set_value(f"{rho:.3f}")
        self.card_rho.set_status_badge("SLA PASS" if rho >= 0.82 else "WARMING UP", "ok" if rho >= 0.82 else "warn")

        self.card_entropy.set_value(f"{entropy:.2f} nats")
        if entropy < 0.35:
            self.card_entropy.set_status_badge("MODE COLLAPSE (<0.35)", "alert")
        elif entropy >= 1.0:
            self.card_entropy.set_status_badge("HEALTHY EXPLORATION", "ok")
        else:
            self.card_entropy.set_status_badge("MODERATE ENTROPY", "warn")

        self.card_logz.set_value(f"{log_z:.3f} +/- 0.004")
        self.card_stability.set_value(f"{grad_norm:.3f} (<= {self.vm.hp.clip_grad_norm:.2f})")
        if stab_status in ("STABLE", "WARMUP"):
            self.card_stability.set_status_badge(stab_status, "ok")
        elif stab_status in ("GRAD_CLIPPED", "SPIKE_DAMPED"):
            self.card_stability.set_status_badge(stab_status, "warn")
        else:
            self.card_stability.set_status_badge(stab_status, "alert")

        pct = (modes_disc / max(1, modes_tot)) * 100.0
        self.modes_bar.setMaximum(modes_tot)
        self.modes_bar.setValue(modes_disc)
        self.modes_bar.setFormat(
            f"{modes_disc} / {modes_tot} Distinct Exploit Modes Discovered ({pct:.1f}% >= 85.0% Target)"
        )
