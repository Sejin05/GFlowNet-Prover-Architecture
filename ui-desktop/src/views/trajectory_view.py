"""View 3: Interactive Trajectory & State-Graph Inspector (`TrajectoryInspectorView`)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from src.viewmodels.audit_vm import AuditViewModel, TrajectoryStepData, VerifiedFindingData
from src.views.widgets.dag_canvas import HsdgDagCanvas


class TrajectoryInspectorView(QWidget):
    """Interactive Trajectory Scrubber, EVM Storage Delta Table, SMT Inspector & HSDG Canvas."""

    def __init__(self, audit_vm: AuditViewModel, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.audit_vm = audit_vm
        self._steps: List[TrajectoryStepData] = []
        self._current_idx: int = 0
        self._play_timer = QTimer(self)
        self._play_timer.setInterval(900)
        self._play_timer.timeout.connect(self._on_play_tick)

        self._build_ui()
        self.audit_vm.selected_finding_changed.connect(self.load_finding_trajectory)
        self.audit_vm.findings_changed.connect(self._populate_trajectory_selector)
        self._populate_trajectory_selector()
        if self.audit_vm.sampled_trajectories:
            self.load_finding_trajectory(self.audit_vm.sampled_trajectories[0])

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(8)

        # --- Top Playback & Scrubber Bar ---
        scrubber_group = QGroupBox("1. Trajectory Timeline & Step Scrubber (s_0 → s_n)")
        scrubber_layout = QVBoxLayout(scrubber_group)

        top_sel_row = QHBoxLayout()
        top_sel_row.addWidget(QLabel("Sampled Trajectory:"))
        self.traj_combo = QComboBox()
        self.traj_combo.setMinimumWidth(360)
        self.traj_combo.setToolTip("Select a sampled trajectory (confirmed exploit, normal rollout, or SMT-pruned path)")
        self.traj_combo.currentIndexChanged.connect(self._on_traj_combo_changed)
        top_sel_row.addWidget(self.traj_combo)

        self.overview_label = QLabel(
            "Trajectory: audit-traj-seed-42-00384 | Steps: 4 | Reward R(s_n): 100.0 | "
            "Status: EXPLOIT_CONFIRMED | Invariant: INV_ROUNDING_DUST_04"
        )
        self.overview_label.setStyleSheet(
            "color: #58a6ff; background-color: #121d2f; border: 1px solid #1f6feb; "
            "border-radius: 5px; padding: 4px 10px; font-weight: 700;"
        )
        top_sel_row.addWidget(self.overview_label, 1)
        scrubber_layout.addLayout(top_sel_row)

        ctrl_row = QHBoxLayout()
        self.btn_first = QPushButton("⏮ First")
        self.btn_first.setToolTip("Jump to initial step s_0")
        self.btn_prev = QPushButton("◀ Prev")
        self.btn_prev.setToolTip("Step backward (s_{t-1})")
        self.btn_play = QPushButton("▶ Play")
        self.btn_play.setObjectName("PrimaryButton")
        self.btn_play.setToolTip("Auto-play macro-action transitions")
        self.btn_next = QPushButton("Next ▶")
        self.btn_next.setToolTip("Step forward (s_{t+1})")
        self.btn_last = QPushButton("Last ⏭")
        self.btn_last.setToolTip("Jump to terminal step s_n")

        self.step_slider = QSlider(Qt.Orientation.Horizontal)
        self.step_slider.setRange(0, 3)
        self.step_slider.setValue(0)
        self.step_badge = QLabel("Step 0 / 3 | log P_F: -0.42 | log P_B: -1.10 | R_novelty: 0.62")
        self.step_badge.setStyleSheet(
            "color: #3fb950; background-color: #0d2117; border: 1px solid #238636; "
            "border-radius: 4px; padding: 3px 8px; font-family: 'Cascadia Code', monospace; font-weight: 600;"
        )

        self.btn_first.clicked.connect(lambda: self.select_step(0))
        self.btn_prev.clicked.connect(lambda: self.select_step(max(0, self._current_idx - 1)))
        self.btn_play.clicked.connect(self._toggle_play)
        self.btn_next.clicked.connect(
            lambda: self.select_step(min(max(0, len(self._steps) - 1), self._current_idx + 1))
        )
        self.btn_last.clicked.connect(lambda: self.select_step(max(0, len(self._steps) - 1)))
        self.step_slider.valueChanged.connect(self.select_step)

        ctrl_row.addWidget(self.btn_first)
        ctrl_row.addWidget(self.btn_prev)
        ctrl_row.addWidget(self.btn_play)
        ctrl_row.addWidget(self.btn_next)
        ctrl_row.addWidget(self.btn_last)
        ctrl_row.addWidget(self.step_slider, 1)
        ctrl_row.addWidget(self.step_badge)
        scrubber_layout.addLayout(ctrl_row)

        # --- Middle 3-Pane Splitter: Call Trace | EVM Storage Mutation Delta | Symbolic SMT Inspector ---
        mid_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Call Trace List
        trace_group = QGroupBox("2. Macro-Action Call Trace")
        trace_layout = QVBoxLayout(trace_group)
        self.trace_list = QListWidget()
        self.trace_list.currentRowChanged.connect(self.select_step)
        self.calldata_detail = QPlainTextEdit()
        self.calldata_detail.setReadOnly(True)
        self.calldata_detail.setMaximumHeight(90)
        trace_layout.addWidget(self.trace_list, 1)
        trace_layout.addWidget(QLabel("Decoded Calldata & Foundry Cheatcodes:"))
        trace_layout.addWidget(self.calldata_detail)

        # Center: EVM Storage Mutation Delta Table
        storage_group = QGroupBox("3. EVM Storage Mutation Delta (revm CoW + storageLayout)")
        storage_layout = QVBoxLayout(storage_group)
        self.storage_model = QStandardItemModel(0, 5, self)
        self.storage_model.setHorizontalHeaderLabels(
            ["Slot ID", "Solidity Variable", "Pre-Value (s_t)", "Post-Value (s_{t+1})", "Semantic Role"]
        )
        self.storage_table = QTableView()
        self.storage_table.setModel(self.storage_model)
        self.storage_table.setAlternatingRowColors(True)
        self.storage_table.verticalHeader().setVisible(False)
        st_header = self.storage_table.horizontalHeader()
        st_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        st_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        st_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        st_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        st_header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.actor_balance_lbl = QLabel("Actor Balance Delta: -- | RND Storage Novelty: --")
        self.actor_balance_lbl.setStyleSheet(
            "color: #79c0ff; font-family: 'Cascadia Code', monospace; font-weight: 600;"
        )
        storage_layout.addWidget(self.storage_table, 1)
        storage_layout.addWidget(self.actor_balance_lbl)

        # Right: Symbolic SMT Solver Inspector (Bitwuzla / Z3 QF_BV)
        smt_group = QGroupBox("4. Symbolic SMT Solver Inspector (Bitwuzla / Z3 256-bit QF_BV)")
        smt_layout = QVBoxLayout(smt_group)
        self.smt_meta_label = QLabel("Solver Status: SAT (41.6 ms) | Branch Guard > 0.85")
        self.smt_meta_label.setStyleSheet("color: #d2a8ff; font-weight: 700;")
        self.smt_formula_viewer = QPlainTextEdit()
        self.smt_formula_viewer.setReadOnly(True)
        self.smt_witness_label = QLabel("Concrete Witness Assignment: --")
        self.smt_witness_label.setStyleSheet(
            "color: #3fb950; font-family: 'Cascadia Code', monospace; font-weight: 600;"
        )
        smt_layout.addWidget(self.smt_meta_label)
        smt_layout.addWidget(self.smt_formula_viewer, 1)
        smt_layout.addWidget(self.smt_witness_label)

        mid_splitter.addWidget(trace_group)
        mid_splitter.addWidget(storage_group)
        mid_splitter.addWidget(smt_group)
        mid_splitter.setStretchFactor(0, 4)
        mid_splitter.setStretchFactor(1, 5)
        mid_splitter.setStretchFactor(2, 4)
        mid_splitter.setSizes([360, 520, 420])

        # --- Bottom Panel: Interactive HSDG Subgraph Canvas ---
        dag_group = QGroupBox(
            "5. Heterogeneous State-Dependency Graph (HSDG Subgraph: StorageNode [64], FunctionNode [64], ConditionNode [48], ExternalCallNode [32])"
        )
        dag_layout = QVBoxLayout(dag_group)
        self.dag_canvas = HsdgDagCanvas(parent=self)
        self.node_schema_lbl = QLabel(
            "Click any HSDG node to inspect its 512-d RGAT projection and raw feature tensor layout | "
            "Edges: ReadsFrom (Blue), WritesTo (Red), Guards (Amber), Invokes (Purple)"
        )
        self.node_schema_lbl.setStyleSheet("color: #8b949e; font-size: 11px; font-weight: 600;")
        self.dag_canvas.node_selected.connect(self._on_dag_node_selected)
        dag_layout.addWidget(self.dag_canvas, 1)
        dag_layout.addWidget(self.node_schema_lbl)

        root_layout.addWidget(scrubber_group)
        root_layout.addWidget(mid_splitter, 1)
        root_layout.addWidget(dag_group, 1)

    def _populate_trajectory_selector(self) -> None:
        self.traj_combo.blockSignals(True)
        current_text = self.traj_combo.currentText()
        self.traj_combo.clear()
        selected_idx = 0
        for i, t in enumerate(self.audit_vm.sampled_trajectories):
            label = f"{t.trajectory_id} [{t.trajectory_status} | R={t.terminal_reward} | {t.violated_invariant_id}]"
            self.traj_combo.addItem(label)
            if t.trajectory_id in current_text:
                selected_idx = i
        if self.audit_vm.sampled_trajectories:
            self.traj_combo.setCurrentIndex(selected_idx)
        self.traj_combo.blockSignals(False)

    def _on_traj_combo_changed(self, idx: int) -> None:
        if 0 <= idx < len(self.audit_vm.sampled_trajectories):
            self.load_finding_trajectory(self.audit_vm.sampled_trajectories[idx])

    def _on_dag_node_selected(self, info: Dict[str, Any]) -> None:
        self.node_schema_lbl.setText(
            f"Selected [{info.get('node_type')}] {info.get('label')}: {info.get('schema')}"
        )

    def load_finding_trajectory(self, finding: VerifiedFindingData) -> None:
        self._steps = list(finding.trajectory_steps)
        self.overview_label.setText(
            f"Trajectory: {finding.trajectory_id} | Status: {finding.trajectory_status} | "
            f"Steps: {len(self._steps)} | Reward R(s_n): {finding.terminal_reward} | "
            f"Invariant: {finding.violated_invariant_id}"
        )
        self.traj_combo.blockSignals(True)
        for i in range(self.traj_combo.count()):
            if finding.trajectory_id in self.traj_combo.itemText(i):
                self.traj_combo.setCurrentIndex(i)
                break
        self.traj_combo.blockSignals(False)

        self.trace_list.blockSignals(True)
        self.trace_list.clear()
        for s in self._steps:
            txt = (
                f"[Step {s.step_idx}] {s.caller_role} -> "
                f"{s.target_contract}.{s.function_signature}"
            )
            item = QListWidgetItem(txt)
            self.trace_list.addItem(item)
        self.trace_list.blockSignals(False)

        max_idx = max(0, len(self._steps) - 1)
        self.step_slider.setRange(0, max_idx)
        self.select_step(0)

    def select_step(self, idx: int) -> None:
        if not self._steps or idx < 0 or idx >= len(self._steps):
            return
        self._current_idx = idx
        self.step_slider.blockSignals(True)
        self.step_slider.setValue(idx)
        self.step_slider.blockSignals(False)

        self.trace_list.blockSignals(True)
        self.trace_list.setCurrentRow(idx)
        self.trace_list.blockSignals(False)

        step = self._steps[idx]
        self.step_badge.setText(
            f"Step {step.step_idx} / {len(self._steps) - 1} | "
            f"log P_F: {step.log_pf:.2f} | log P_B: {step.log_pb:.2f} | "
            f"R_novelty: {step.rnd_novelty:.3f}"
        )

        args_fmt = ", ".join(step.decoded_args)
        self.calldata_detail.setPlainText(
            f"Caller Persona: {step.caller_role} ({step.caller_address})\n"
            f"Call: {step.target_contract}.{step.function_signature}({args_fmt})\n"
            f"Raw Calldata: {step.concrete_calldata_hex}\n"
            f"Cheatcodes: vm.warp(+{step.vm_warp_sec}s), vm.roll(+{step.vm_roll_blocks} blocks)"
        )

        self.storage_model.removeRows(0, self.storage_model.rowCount())
        for delta in step.storage_deltas:
            row_items = [
                QStandardItem(str(delta.get("slot", "0x00"))),
                QStandardItem(str(delta.get("variable", "slot_var"))),
                QStandardItem(str(delta.get("pre_value", "0x0"))),
                QStandardItem(str(delta.get("post_value", "0x0"))),
                QStandardItem(str(delta.get("role", "GenericState"))),
            ]
            row_items[3].setForeground(QColor("#ff7b72"))
            for it in row_items:
                it.setEditable(False)
            self.storage_model.appendRow(row_items)

        self.actor_balance_lbl.setText(
            f"Actor Balance: {step.actor_balances} | RND Storage Novelty R_novelty: {step.rnd_novelty:.3f}"
        )

        if not step.smt_guard:
            self.smt_meta_label.setText("Result: N/A | No symbolic branch condition on this step")
            self.smt_meta_label.setStyleSheet(
                "color: #8b949e; background-color: #161b22; border: 1px solid #30363d; "
                "border-radius: 4px; padding: 3px 8px; font-weight: 600;"
            )
            self.smt_formula_viewer.setPlainText(
                "// No symbolic constraint or branch guard required for this macro-action."
            )
            self.smt_witness_label.setText("Concrete Witness: None")
        else:
            guard = step.smt_guard
            res = str(guard.get("solver_result", "SAT"))
            solve_ms = float(guard.get("solve_time_ms", 15.0))
            g_type = str(guard.get("guard_type", "Arithmetic Branch"))
            ast_txt = f" | AST: {guard.get('ast_node')}" if guard.get("ast_node") else ""
            self.smt_meta_label.setText(
                f"Result: {res} ({solve_ms:.3f} ms) | {g_type}{ast_txt}"
            )
            if "UNSAT" in res:
                self.smt_meta_label.setStyleSheet(
                    "color: #ff7b72; background-color: #2d1215; border: 1px solid #da3633; "
                    "border-radius: 4px; padding: 3px 8px; font-weight: 700;"
                )
            else:
                self.smt_meta_label.setStyleSheet(
                    "color: #d2a8ff; background-color: #1e162b; border: 1px solid #8957e5; "
                    "border-radius: 4px; padding: 3px 8px; font-weight: 700;"
                )
            self.smt_formula_viewer.setPlainText(
                str(guard.get("smt_formula", "(set-logic QF_BV)\n(check-sat)"))
            )
            witness_dict = guard.get("witness", {})
            witness_str = ", ".join(f"{k} = {v}" for k, v in witness_dict.items()) or "None"
            self.smt_witness_label.setText(f"Concrete Witness: {witness_str}")

        self.dag_canvas.load_step_subgraph(idx, step)

    def _toggle_play(self) -> None:
        if self._play_timer.isActive():
            self._play_timer.stop()
            self.btn_play.setText("▶ Play")
        else:
            self._play_timer.start()
            self.btn_play.setText("⏸ Pause")

    def _on_play_tick(self) -> None:
        if not self._steps:
            return
        next_idx = (self._current_idx + 1) % len(self._steps)
        self.select_step(next_idx)
