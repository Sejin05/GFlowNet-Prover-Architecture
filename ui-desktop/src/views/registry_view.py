"""View 5: Model Registry & Release Gate Validator (`ModelRegistryView`)."""

from __future__ import annotations

import json
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from src.viewmodels.telemetry_vm import CheckpointRecord, ReleaseGateRow, TelemetryViewModel


class ModelRegistryView(QWidget):
    """SafeTensors Checkpoint Browser, Manifest Inspector, and 7 Go/No-Go Release Gate Matrix."""

    def __init__(self, vm: TelemetryViewModel, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.vm = vm
        self._selected_checkpoint: str = "candidate_continual_ewc_v2.safetensors"
        self._build_ui()
        self._bind_viewmodel()
        self._populate_checkpoints(self.vm.checkpoints)
        self._populate_gates(self.vm.release_gates, True)
        self._update_manifest_viewer(self._selected_checkpoint)

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(10)

        # --- Top Split: Section 1 (Checkpoint Browser) | Section 2 (Manifest & Fisher Inspector) ---
        top_splitter = QSplitter(Qt.Orientation.Horizontal)

        ckpt_group = QGroupBox("1. SafeTensors Model Checkpoint Browser (Blake3 Verified)")
        ckpt_layout = QVBoxLayout(ckpt_group)

        self.ckpt_model = QStandardItemModel(0, 6, self)
        self.ckpt_model.setHorizontalHeaderLabels(
            [
                "Checkpoint Filename (.safetensors)",
                "Training Phase",
                "Registry Status",
                "Blake3 Digest",
                "Size (MB)",
                "Created Timestamp (UTC)",
            ]
        )
        self.ckpt_table = QTableView()
        self.ckpt_table.setModel(self.ckpt_model)
        self.ckpt_table.setAlternatingRowColors(True)
        self.ckpt_table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.ckpt_table.verticalHeader().setVisible(False)
        self.ckpt_table.setMaximumHeight(185)
        c_header = self.ckpt_table.horizontalHeader()
        c_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 6):
            c_header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.ckpt_table.clicked.connect(self._on_checkpoint_selected)
        ckpt_layout.addWidget(self.ckpt_table)

        manifest_group = QGroupBox("2. Checkpoint Metadata Manifest (`manifest.json` & Blake3)")
        manifest_layout = QVBoxLayout(manifest_group)
        self.manifest_viewer = QPlainTextEdit()
        self.manifest_viewer.setReadOnly(True)
        self.manifest_viewer.setMaximumHeight(185)
        manifest_layout.addWidget(self.manifest_viewer)

        top_splitter.addWidget(ckpt_group)
        top_splitter.addWidget(manifest_group)
        top_splitter.setStretchFactor(0, 6)
        top_splitter.setStretchFactor(1, 4)

        # --- Section 3: 7 Go/No-Go Release Gate Matrix ---
        gates_group = QGroupBox("3. Automated 7 Go/No-Go Release Gate Certification Matrix")
        gates_layout = QVBoxLayout(gates_group)

        self.cert_banner = QLabel(
            "Release Certification: ALL 7 RELEASE GATES PASSED (100%). "
            "Candidate is verified safe for production promotion."
        )
        self.cert_banner.setStyleSheet(
            "background-color: #0f2419; color: #3fb950; border: 1px solid #2ea043; "
            "border-radius: 5px; padding: 6px 12px; font-weight: 700;"
        )
        gates_layout.addWidget(self.cert_banner)

        self.gates_model = QStandardItemModel(0, 5, self)
        self.gates_model.setHorizontalHeaderLabels(
            [
                "Gate #",
                "Release Gate Identifier",
                "Mandatory Acceptance Target",
                "Candidate Measured Score",
                "Gate Status",
            ]
        )
        self.gates_table = QTableView()
        self.gates_table.setModel(self.gates_model)
        self.gates_table.setAlternatingRowColors(True)
        self.gates_table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.gates_table.verticalHeader().setVisible(False)
        self.gates_table.verticalHeader().setDefaultSectionSize(28)
        g_header = self.gates_table.horizontalHeader()
        g_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        g_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        g_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        g_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        g_header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        gates_layout.addWidget(self.gates_table, 1)

        # --- Action Buttons ---
        btn_row = QHBoxLayout()
        self.run_gates_btn = QPushButton("⚡ Run 7-Gate Validation Suite")
        self.run_gates_btn.setObjectName("AccentButton")
        self.run_gates_btn.setToolTip("Execute all 7 Go/No-Go Release Gates against the selected SafeTensors checkpoint")
        self.promote_btn = QPushButton("✓ Promote Candidate to Active Audit Policy")
        self.promote_btn.setObjectName("PrimaryButton")
        self.promote_btn.setToolTip("Promote verified checkpoint to active production policy (blocked unless all 7 gates pass)")
        self.rollback_btn = QPushButton("↺ Rollback Checkpoint")
        self.rollback_btn.setObjectName("DangerButton")
        self.rollback_btn.setToolTip("Atomically restore previous promoted production checkpoint")
        self.export_cert_btn = QPushButton("Export Certification Report")
        self.export_cert_btn.setToolTip("Export signed JSON release gate certification report")

        self.run_gates_btn.clicked.connect(self._on_run_gates)
        self.promote_btn.clicked.connect(self._on_promote)
        self.rollback_btn.clicked.connect(self._on_rollback)
        self.export_cert_btn.clicked.connect(self._on_export_report)

        btn_row.addWidget(self.run_gates_btn)
        btn_row.addWidget(self.promote_btn)
        btn_row.addWidget(self.rollback_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.export_cert_btn)
        gates_layout.addLayout(btn_row)

        root_layout.addWidget(top_splitter)
        root_layout.addWidget(gates_group, 1)

    def _bind_viewmodel(self) -> None:
        self.vm.checkpoints_updated.connect(self._populate_checkpoints)
        self.vm.release_gates_updated.connect(self._populate_gates)

    def _update_manifest_viewer(self, filename: str) -> None:
        manifest = self.vm.get_checkpoint_manifest(filename)
        self.manifest_viewer.setPlainText(json.dumps(manifest, indent=2))

    def _populate_checkpoints(self, records: List[CheckpointRecord]) -> None:
        self.ckpt_model.removeRows(0, self.ckpt_model.rowCount())
        selected_row = 0
        for r_idx, ckpt in enumerate(records):
            items = [
                QStandardItem(ckpt.filename),
                QStandardItem(ckpt.phase),
                QStandardItem(ckpt.status),
                QStandardItem(ckpt.blake3_digest),
                QStandardItem(f"{ckpt.size_mb:.1f} MB"),
                QStandardItem(ckpt.created_at),
            ]
            if ckpt.status == "PROMOTED":
                items[2].setForeground(QColor("#3fb950"))
                items[2].setBackground(QColor("#0f2419"))
            elif ckpt.status == "EVALUATING":
                items[2].setForeground(QColor("#58a6ff"))
            for it in items:
                it.setEditable(False)
            self.ckpt_model.appendRow(items)
            if ckpt.filename == self._selected_checkpoint:
                selected_row = r_idx

        if records:
            self.ckpt_table.selectRow(selected_row)

    def _populate_gates(self, gates: List[ReleaseGateRow], all_passed: bool) -> None:
        self.gates_model.removeRows(0, self.gates_model.rowCount())
        for g in gates:
            status_str = "PASSED (OK)" if g.passed else "BLOCKED (FAIL)"
            items = [
                QStandardItem(f"Gate {g.gate_number}"),
                QStandardItem(g.gate_id),
                QStandardItem(g.metric_target),
                QStandardItem(g.candidate_score),
                QStandardItem(status_str),
            ]
            if g.passed:
                items[4].setForeground(QColor("#3fb950"))
                items[4].setBackground(QColor("#0f2419"))
            else:
                items[4].setForeground(QColor("#f85149"))
                items[4].setBackground(QColor("#2d1215"))
            for it in items:
                it.setEditable(False)
            self.gates_model.appendRow(items)

        if all_passed:
            self.cert_banner.setText(
                f"Release Certification ({self._selected_checkpoint}): "
                "ALL 7 RELEASE GATES PASSED (100%). Safe to promote candidate."
            )
            self.cert_banner.setStyleSheet(
                "background-color: #0f2419; color: #3fb950; border: 1px solid #2ea043; "
                "border-radius: 4px; padding: 6px 12px; font-weight: 700;"
            )
            self.promote_btn.setEnabled(True)
        else:
            self.cert_banner.setText(
                f"Release Certification ({self._selected_checkpoint}): "
                "BLOCKED! Candidate failed one or more mandatory Go/No-Go Release Gates."
            )
            self.cert_banner.setStyleSheet(
                "background-color: #2d1215; color: #f85149; border: 1px solid #f85149; "
                "border-radius: 4px; padding: 6px 12px; font-weight: 700;"
            )
            self.promote_btn.setEnabled(False)

    def _on_checkpoint_selected(self, index) -> None:
        row = index.row()
        item = self.ckpt_model.item(row, 0)
        if item:
            self._selected_checkpoint = item.text()
            self._update_manifest_viewer(self._selected_checkpoint)
            self.vm.run_release_gate_validation(self._selected_checkpoint)

    def _on_run_gates(self) -> None:
        self.vm.run_release_gate_validation(self._selected_checkpoint)

    def _on_promote(self) -> None:
        if self.vm.promote_checkpoint(self._selected_checkpoint):
            self.cert_banner.setText(
                f"PROMOTED: '{self._selected_checkpoint}' is now the Active Production Audit Policy."
            )
            for r in range(self.ckpt_model.rowCount()):
                item = self.ckpt_model.item(r, 0)
                if item and item.text() == self._selected_checkpoint:
                    self.ckpt_table.selectRow(r)
                    break

    def _on_rollback(self) -> None:
        rolled_back = self.vm.rollback_checkpoint()
        self._selected_checkpoint = rolled_back
        self._update_manifest_viewer(rolled_back)
        self.vm.run_release_gate_validation(rolled_back)
        self.cert_banner.setText(f"ROLLED BACK: Restored active policy to '{rolled_back}'.")
        for r in range(self.ckpt_model.rowCount()):
            item = self.ckpt_model.item(r, 0)
            if item and item.text() == rolled_back:
                self.ckpt_table.selectRow(r)
                break

    def _on_export_report(self) -> None:
        default_out = str(self.vm.workspace_root / "release_gate_certification_report.json")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Release Gate Certification Report",
            default_out,
            "JSON Files (*.json)",
        )
        if path:
            self.vm.export_certification_report(path)
