# GFlowNet-Prover Native Desktop UI (`ui-desktop/`)

High-performance, resource-efficient **PySide6 / Qt 6 Native Desktop** studio for **GFlowNet-Prover (Pure Rust / Foundry Edition)** with real-time 60 FPS `PyQtGraph` telemetry and interactive HSDG OpenGL/QGraphicsScene visualization.

## Key Architectural Properties & SLAs
- **Zero Web/Electron Runtime Bloat**: 100% Native Qt 6 OS widgets, `QPainter`, and `PyQtGraph`.
- **Cold Startup Latency**: $\le 1.2\text{ seconds}$ (measured $\sim 876\text{ ms}$).
- **Idle Memory Footprint**: $\le 95.0\text{ MB}$ RAM (measured $\sim 75.4\text{ MB}$).
- **Zero UI Thread Blocking**: All `gfn-forge` CLI processes (`QProcess`), Server-Sent Events (`GET /v1/audits/:id/stream` via `QNetworkAccessManager`), and Prometheus scrapes (`127.0.0.1:9090/metrics` at $1\text{ Hz}$) execute asynchronously.

## Primary Workbenches
1. **View 1: Auditing & Verification Workbench (`src/views/audit_view.py`)**
   - Foundry workspace selector (`QFileSystemModel`), `solc` (`svm-rs`) & `*Test.sol` auto-detection.
   - Search budget sliders (`max_trajectories`, `max_depth`, `batch_size`, `smt_timeout_ms`, online adaptation toggle).
   - 4 Canonical HGT Invariant categories (*Conservation of Value & Solvency*, *State Machine Monotonicity*, *Privilege & Access Control Isolation*, *Rounding & Precision Neutrality*) with live `SYNTHESIZING`, `STABLE`, and flashing `VIOLATED` badges.
   - Split-pane syntax-highlighted `ExploitPoC.t.sol` viewer and unified Git diff remediation patch viewer.
2. **View 2: Intuitive Multi-Phase Training Studio (`src/views/training_view.py`)**
   - 3-Step wizard for Phase 1 (MSTM Pre-train), Phase 2 (Curriculum Trajectory Balance), and Phase 3 (Continual EWC, $\lambda_{\text{EWC}} = 400.0$).
   - 60 FPS `PyQtGraph` live charts for $\mathcal{L}_{TB}(\tau)$ with Huber-clipping markers ($\delta_{TB} = 10.0$), Spearman flow correlation $\rho_{TB}$ ($\ge 0.82$ SLA target line), Action Policy Entropy $H(P_F)$ ($< 0.35$ mode collapse / $\ge 1.0$ healthy), and $\text{Modes}@K$ progress bar.
3. **View 3: Interactive Trajectory & State-Graph Inspector (`src/views/trajectory_view.py`)**
   - Step-by-step scrubber ($s_0 \to s_n$), macro-action call trace, `revm` CoW storage slot mutation delta table, Bitwuzla/Z3 256-bit `QF_BV` formula & concrete witness inspector, and interactive HSDG subgraph canvas (`StorageNode`, `FunctionNode`, `ConditionNode`, `ExternalCallNode`).
4. **View 4: Operational Telemetry & Drift Monitor (`src/views/telemetry_view.py`)**
   - Structural drift gauges (Spectral $\text{MMD}^2 < 0.08$, Opcode $\text{PSI} < 0.15$, Storage $D_{JS} < 0.10$, RND $D_{KS} < 0.18$), concept drift gauges ($|\Delta_{TB}| \le 2.5$, SMT handover efficacy, Revm-to-Forge mismatch P1 alert), hardware gauges, and live diagnostic terminal.
5. **View 5: Model Registry & Release Gate Validator (`src/views/registry_view.py`)**
   - SafeTensors checkpoint browser with Blake3 digests and interactive 7 Go/No-Go Release Gate certification matrix.

## Quickstart & Commands

```powershell
# Run SLA Self-Check (Startup Latency & Idle Memory Footprint)
.\.venv\Scripts\python.exe -m src.main --self-check

# Launch the Native Desktop Studio
.\.venv\Scripts\python.exe -m src.main

# Run Automated Test Suite
.\.venv\Scripts\pytest.exe tests/test_ui_desktop.py -v

# Package Standalone Native Executable (PyInstaller)
.\.venv\Scripts\pyinstaller.exe gfn_prover_ui.spec --noconfirm
```
