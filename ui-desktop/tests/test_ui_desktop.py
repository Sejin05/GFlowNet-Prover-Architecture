"""Comprehensive Automated Test Suite for GFlowNet-Prover Native Desktop UI."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import psutil
import pytest
from PySide6.QtWidgets import QApplication

from src.config import TRAINING_PRESETS, AuditConfig, ConfigManager
from src.main import create_application
from src.services.process_manager import LocalProcessManager
from src.services.prom_client import PrometheusScraper
from src.services.sse_client import NativeSseClient


@pytest.fixture(scope="session")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    yield app


def test_startup_latency_and_memory_footprint(qapp, tmp_path: Path):
    """Verify Step 1 SLA: Cold startup <= 1.2s and idle memory < 95 MB."""
    t0 = time.perf_counter()
    _, window, startup_sec = create_application([])
    elapsed = time.perf_counter() - t0
    assert startup_sec <= 1.2, f"Startup latency {startup_sec:.3f}s exceeded 1.2s SLA"
    assert elapsed <= 1.2

    mem_info = psutil.Process(os.getpid()).memory_info()
    private_mb = getattr(mem_info, "private", mem_info.rss) / (1024 * 1024)
    assert private_mb < 95.0, f"Idle Private Memory {private_mb:.2f} MB exceeded 95 MB SLA"
    window.close()


def test_toml_config_roundtrip_and_presets(tmp_path: Path):
    """Verify TOML configuration loading, saving, and JSON payload conversion."""
    audit_cfg = AuditConfig()
    audit_cfg.project_source.workspace_path = "/tmp/defi-vault"
    audit_cfg.search_budget.max_trajectories = 250_000
    audit_cfg.search_budget.max_depth = 18

    saved_audit = ConfigManager.save_audit_config(audit_cfg, tmp_path / "audit.toml")
    loaded_audit = ConfigManager.load_audit_config(saved_audit)
    assert loaded_audit.project_source.workspace_path == "/tmp/defi-vault"
    assert loaded_audit.search_budget.max_trajectories == 250_000
    assert loaded_audit.search_budget.max_depth == 18

    payload = loaded_audit.to_submission_payload()
    assert payload["project_source"]["setup_contract"] == "ExploitHarnessTest"
    assert payload["search_budget"]["max_trajectories"] == 250_000

    # Also test loading the repository's canonical configs
    repo_root = Path(__file__).resolve().parents[2]
    default_audit = ConfigManager.load_audit_config(repo_root / "configs" / "default_audit.toml")
    assert default_audit.foundry_profile.solc_version == "0.8.24"
    assert default_audit.foundry_profile.evm_version == "cancun"

    tb_hp = ConfigManager.load_training_config(repo_root / "configs" / "curriculum_tb.toml")
    assert tb_hp.huber_delta == pytest.approx(10.0)
    assert tb_hp.lr_policy == pytest.approx(3e-4)
    assert tb_hp.lr_log_z == pytest.approx(5e-3)
    assert tb_hp.clip_grad_norm == pytest.approx(1.0)
    assert tb_hp.ema_decay == pytest.approx(0.95)
    assert tb_hp.max_residual_clip == pytest.approx(100.0)
    assert tb_hp.enable_grad_spike_guard is True

    mstm_hp = ConfigManager.load_training_config(repo_root / "configs" / "pretrain_mstm.toml")
    assert mstm_hp.phase == 1
    assert mstm_hp.mask_ratio == pytest.approx(0.30)

    # Save and reload TrainingHyperparameters
    saved_train = ConfigManager.save_training_config(tb_hp, tmp_path / "train.toml")
    reloaded_train = ConfigManager.load_training_config(saved_train)
    assert reloaded_train.huber_delta == pytest.approx(10.0)
    assert set(TRAINING_PRESETS.keys()) == {
        "Smoke Test",
        "Production DeFi Tuning",
        "Deep Exploit Search",
    }


def test_ipc_services_and_parsers(qapp):
    """Verify LocalProcessManager CLI formatting, NativeSseClient framing, and PrometheusScraper parsing."""
    pm = LocalProcessManager()
    audit_args = pm.build_audit_args(".", "configs/default_audit.toml", "ExploitHarnessTest", "setUp", 50_000)
    assert audit_args[:2] == ["audit", "--project"]
    assert "50000" in audit_args

    p1_args = pm.build_training_args(1, "configs/pretrain_mstm.toml", "data/corpus", "out.st", epochs=5)
    assert p1_args[0] == "pretrain"
    p2_args = pm.build_training_args(
        2, "configs/curriculum_tb.toml", "data/corpus", "out.st", pretrained_weights="mstm.st"
    )
    assert p2_args[0] == "train" and "--pretrained-weights" in p2_args
    p3_args = pm.build_training_args(
        3, "configs/curriculum_tb.toml", "data/corpus", "out.st", anchor_checkpoint="tb.st", lambda_ewc=400.0
    )
    assert p3_args[0] == "train-continual" and "400.0" in p3_args

    # Test SSE stream parser
    sse = NativeSseClient()
    received_events = []
    discovered_findings = []
    updated_invariants = []
    sse.sse_event_received.connect(lambda ev, d: received_events.append((ev, d)))
    sse.finding_discovered.connect(lambda f: discovered_findings.append(f))
    sse.invariant_updated.connect(lambda inv: updated_invariants.append(inv))

    sse.feed_sse_chunk(
        'event: status_change\ndata: {"status": "EXPLORING_GFLOWNET"}\n\n'
        'event: invariant_synthesized\ndata: {"invariant_id": "INV_SOLVENCY_01", "category": "SOLVENCY", "confidence": 0.992}\n\n'
        'event: finding_discovered\ndata: {"finding_id": "FINDING-99", "violated_invariant_id": "INV_SOLVENCY_01", "severity": "CRITICAL"}\n\n'
    )
    assert len(received_events) == 3
    assert received_events[0][0] == "status_change"
    assert len(updated_invariants) == 1
    assert updated_invariants[0]["invariant_id"] == "INV_SOLVENCY_01"
    assert len(discovered_findings) == 1
    assert discovered_findings[0]["finding_id"] == "FINDING-99"

    # Test Prometheus exposition text parser
    prom_text = """
    # HELP gfn_revm_steps_per_sec_per_thread Revm throughput per worker thread
    # TYPE gfn_revm_steps_per_sec_per_thread gauge
    gfn_revm_steps_per_sec_per_thread{worker="0"} 74210.5
    gfn_flow_spearman_rho_logpf_logr 0.864
    gfn_smt_unsat_cache_hit_rate 0.784
    gfn_forge_verification_rejected_total 0
    """
    parsed = PrometheusScraper.parse_prometheus_text(prom_text)
    assert parsed["gfn_revm_steps_per_sec_per_thread"] == pytest.approx(74210.5)
    assert parsed["gfn_flow_spearman_rho_logpf_logr"] == pytest.approx(0.864)
    assert parsed["gfn_smt_unsat_cache_hit_rate"] == pytest.approx(0.784)
    assert parsed["gfn_forge_verification_rejected_total"] == pytest.approx(0.0)


def test_all_five_views_and_viewmodels(qapp, tmp_path: Path):
    """Instantiate all 5 views and verify interactive workflows across the MVVM stack."""
    _, window, _ = create_application([])
    window.ensure_all_views_loaded()

    # View 1: Audit Workbench
    audit_view = window.switch_view(0)
    assert audit_view.inv_model.rowCount() == 4
    assert audit_view.findings_combo.count() >= 2
    assert "ExploitPoCTest" in audit_view.poc_editor.toPlainText()
    assert "--- a/src/VaultErc4626.sol" in audit_view.diff_editor.toPlainText()

    # Switch between verified findings in Audit Workbench
    audit_view.findings_combo.setCurrentIndex(1)
    assert "INV_SOLVENCY_01" in audit_view.finding_banner.text()

    # Export verified findings report
    findings_export = window.audit_vm.export_findings_report(tmp_path / "findings.json")
    assert findings_export.exists()
    findings_json = json.loads(findings_export.read_text(encoding="utf-8"))
    assert findings_json["false_positive_rate"] == 0.0
    assert len(findings_json["verified_findings"]) >= 2

    # Trigger audit telemetry step
    window.audit_vm.start_local_synchronous_audit()
    window.audit_vm._step_telemetry()
    window.audit_vm.stop_audit()
    assert window.audit_vm.status == "COMPLETED"

    # View 2: Training Studio
    train_view = window.switch_view(1)
    window.training_vm.apply_preset("Deep Exploit Search")
    assert window.training_vm.hp.beta_novelty == pytest.approx(1.50)
    assert window.training_vm.hp.clip_grad_norm == pytest.approx(0.75)
    assert train_view.grad_clip_spin.value() == pytest.approx(0.75)
    window.training_vm.reset_defaults()
    assert window.training_vm.hp.beta_novelty == pytest.approx(0.50)
    assert window.training_vm.hp.clip_grad_norm == pytest.approx(1.0)
    lr_w, _ = window.training_vm.compute_lr_schedule(0)
    lr_peak, _ = window.training_vm.compute_lr_schedule(window.training_vm.hp.lr_warmup_steps - 1)
    assert lr_w < lr_peak
    window.training_vm.set_phase(3)
    cmd = window.training_vm.build_cli_command()
    assert "gfn-forge train-continual" in cmd
    window.training_vm._tick_training_telemetry()
    assert len(window.training_vm.steps_history) > 100
    assert len(window.training_vm.loss_ema_history) == len(window.training_vm.loss_tb_history)
    assert len(window.training_vm.grad_norm_history) == len(window.training_vm.loss_tb_history)
    assert "EMA" in train_view.card_loss.value_label.text()
    assert train_view.card_stability.badge_label.text() in ("STABLE", "WARMUP", "GRAD_CLIPPED", "SPIKE_DAMPED")

    # View 3: Trajectory & State-Graph Inspector
    traj_view = window.switch_view(2)
    assert traj_view.traj_combo.count() >= 3
    traj_view.traj_combo.setCurrentIndex(0)
    traj_view.select_step(1)
    assert "BitVec 256" in traj_view.smt_formula_viewer.toPlainText()
    assert traj_view.storage_model.rowCount() >= 2
    # Select UNSAT pruned trajectory
    traj_view.traj_combo.setCurrentIndex(2)
    assert "UNSAT" in traj_view.smt_meta_label.text()
    # Select HSDG node to verify feature tensor schema banner
    node_item = traj_view.dag_canvas._node_items["st_assets"]
    node_item.setSelected(True)
    assert "StorageNode" in traj_view.node_schema_lbl.text()

    # View 4: Operational Telemetry & Drift Monitor (with PyQtGraph curves)
    telem_view = window.switch_view(3)
    window.telemetry_vm._on_prometheus_metrics(
        {
            "gfn_revm_steps_per_sec_per_thread": 75100.0,
            "gfn_flow_spearman_rho_logpf_logr": 0.88,
            "gfn_smt_unsat_cache_hit_rate": 0.81,
            "gfn_forge_verification_rejected_total": 0.0,
        }
    )
    assert "75,100" in telem_view.tps_gauge_lbl.text()
    assert len(window.telemetry_vm.tps_history) >= 60

    # View 5: Model Registry & 7 Release Gates
    reg_view = window.switch_view(4)
    assert reg_view.gates_model.rowCount() == 7
    assert "StateGraphRgatEncoder" in reg_view.manifest_viewer.toPlainText()

    # Verify pretrain-only checkpoint fails release gates and blocks promotion
    assert not window.telemetry_vm.promote_checkpoint("checkpoint_pretrained_mstm_v1.safetensors")

    # Verify candidate EWC checkpoint passes all 7 release gates and promotes cleanly
    assert window.telemetry_vm.promote_checkpoint("candidate_continual_ewc_v2.safetensors")
    assert window.telemetry_vm.active_promoted_checkpoint == "candidate_continual_ewc_v2.safetensors"
    rolled_back = window.telemetry_vm.rollback_checkpoint()
    assert rolled_back == "checkpoint_curriculum_tb_v1.safetensors"

    cert_file = window.telemetry_vm.export_certification_report(tmp_path / "cert.json")
    assert cert_file.exists()

    window.close()


def test_ui_synchronization_and_bugfixes(qapp):
    """Verify all dynamic synchronization fixes across training, trajectory, telemetry, and registry views."""
    _, window, _ = create_application([])
    window.ensure_all_views_loaded()

    # 1. Training Studio Synchronization
    train_view = window.switch_view(1)
    # Verify Phase radio button and badge sync
    window.training_vm.set_phase(3)
    assert train_view.radio_p3.isChecked()
    assert not train_view.radio_p1.isChecked()
    assert not train_view.radio_p2.isChecked()
    assert "Phase 3 Active" in train_view.step_badge_1.text()

    window.training_vm.set_phase(1)
    assert train_view.radio_p1.isChecked()
    assert "Phase 1 Active" in train_view.step_badge_1.text()

    # Verify Preset combo sync
    window.training_vm.apply_preset("Smoke Test")
    assert train_view.preset_combo.currentText() == "Smoke Test"
    assert window.training_vm.hp.preset_name == "Smoke Test"

    # Verify CLI command update when hyperparameter widgets change
    train_view.epochs_spin.setValue(12)
    assert window.training_vm.hp.epochs == 12
    assert "--epochs 12" in train_view.cli_preview_edit.text()

    # Verify training state badge and button enabled state
    window.training_vm.start_training()
    assert not train_view.launch_btn.isEnabled()
    assert train_view.stop_train_btn.isEnabled()
    assert "Active:" in train_view.step_badge_3.text()
    window.training_vm.stop_training()
    assert train_view.launch_btn.isEnabled()
    assert not train_view.stop_train_btn.isEnabled()

    # 2. Trajectory Inspector SMT & Selector Sync
    traj_view = window.switch_view(2)
    # Step with NO symbolic branch guard
    step_no_guard = window.audit_vm.sampled_trajectories[0].trajectory_steps[0]
    step_no_guard.smt_guard = None
    traj_view.select_step(0)
    assert "Result: N/A" in traj_view.smt_meta_label.text()
    assert "No symbolic constraint" in traj_view.smt_formula_viewer.toPlainText()

    # Switching findings updates traj_combo
    finding_1 = window.audit_vm.findings[1]
    window.audit_vm.selected_finding_changed.emit(finding_1)
    assert finding_1.trajectory_id in traj_view.traj_combo.currentText()

    # 3. Operational Telemetry Mismatch and SLA badges
    telem_view = window.switch_view(3)
    # Zero mismatch -> PASS badge
    telem_view._on_drift_updated({"revm_forge_mismatch": 0, "spearman_rho": 0.89, "policy_entropy": 1.25, "smt_efficacy_pct": 12.0})
    assert "0 (0.000% FPR)" in telem_view.card_mismatch.value_label.text()
    assert telem_view.card_mismatch.badge_label.text() == "P1 = 0 (PASS)"
    assert "ALIGNED (PASS)" in telem_view.card_align_rho.badge_label.text()

    # Non-zero mismatch -> ALERT badge
    telem_view._on_drift_updated({"revm_forge_mismatch": 4, "spearman_rho": 0.50, "policy_entropy": 0.20, "smt_efficacy_pct": 1.5})
    assert "4 (>0.0% FPR!)" in telem_view.card_mismatch.value_label.text()
    assert telem_view.card_mismatch.badge_label.text() == "P1 ALERT!"
    assert "MODE COLLAPSE" in telem_view.card_align_rho.badge_label.text()
    assert "LOW EFFICACY" in telem_view.card_smt_eff.badge_label.text()

    # 4. Model Registry Table Selection & Rollback Gate Validation
    reg_view = window.switch_view(4)
    assert reg_view.ckpt_table.selectionModel().hasSelection()
    reg_view._on_rollback()
    assert "ROLLED BACK" in reg_view.cert_banner.text()
    assert reg_view.gates_model.rowCount() == 7

    window.close()
