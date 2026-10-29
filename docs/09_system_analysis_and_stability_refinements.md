# System Script Analysis, Training Mechanism Stability Refinements, and Native UI Updates

**Document ID:** `GFN-SPEC-009`  
**Status:** Production Baseline (Verified)  
**Scope:** End-to-End Codebase Script Inventory, Mathematical & Algorithmic Training Stability Refinements (`gfn-engine`, `gfn-cli`, `configs/`), and Native Desktop UI Enhancements (`ui-desktop/`)

---

## 1. Comprehensive System Script Analysis

The **GFlowNet-Prover Architecture** is a hybrid Rust + Python/Qt6 formal verification and multi-transaction smart contract exploit synthesis platform. It consists of **9 Rust crates** (compiled under strict `#![deny(clippy::unwrap_used, clippy::expect_used, unsafe_op_in_unsafe_fn)]` safety gates) and a **Native Desktop UI** (`ui-desktop/`) built with PySide6 (Qt6) and PyQtGraph.

### 1.1 Rust Workspace Crates (`crates/`)

| Crate | Script Path | Primary Responsibilities & Key Abstractions |
| :--- | :--- | :--- |
| **`gfn-common`** | `crates/gfn-common/src/lib.rs`<br>`crates/gfn-common/src/error.rs`<br>`crates/gfn-common/src/math.rs`<br>`crates/gfn-common/src/schemas.rs` | Shared domain schemas (`FoundryContractArtifact`, `StorageSlotRecord`, `TrajectoryStepRecord`, `TrajectoryRecord`, `SynthesizedInvariant`, `VerifiedFinding`), structured error hierarchy (`GfnError`, `GfnResult`), and mathematical normalization (`u256_to_log2_norm`, `u256_signed_log2_delta`, `u256_sinusoidal_chunk_encoding`, `spearman_rank_correlation`). |
| **`gfn-extractor`** | `crates/gfn-extractor/src/lib.rs`<br>`crates/gfn-extractor/src/compiler.rs`<br>`crates/gfn-extractor/src/cfg_lifter.rs`<br>`crates/gfn-extractor/src/proxy_resolver.rs`<br>`crates/gfn-extractor/src/hsdg_builder.rs` | Programmatic Foundry compiler (`ProjectExtractor`), SSA Control Flow Graph lifter (`SsaCfgLifter`), EIP-1967/UUPS/Diamond proxy resolver (`ProxySlotResolver`), and 4-node-type, 8-relation **Heterogeneous State-Dependency Graph (HSDG)** tensor builder (`HsdgBuilder`, `HsdgValidator`). |
| **`gfn-invariants`** | `crates/gfn-invariants/src/lib.rs`<br>`crates/gfn-invariants/src/templates.rs`<br>`crates/gfn-invariants/src/compiler.rs`<br>`crates/gfn-invariants/src/hgt.rs` | **Heterogeneous Graph Transformer (`HgtInvariantSynthesizer`, `BilinearSlotMatcher`)** and `InvariantCompiler` that score and compile 4 canonical DeFi formal invariant classes (`Solvency`, `Monotonicity`, `AccessControl`, `PrecisionNeutrality`) with a strict 0% False Lock-In benign trace filter. |
| **`gfn-evm`** | `crates/gfn-evm/src/lib.rs`<br>`crates/gfn-evm/src/arena.rs`<br>`crates/gfn-evm/src/inspector.rs`<br>`crates/gfn-evm/src/cheatcodes.rs` | High-throughput in-memory EVM execution sandbox (`RevmArena`) using `revm` with Copy-on-Write (`CacheDB`) snapshots (`O(1)` fork/restore), custom `GfnEvmInspector` recording normalized arithmetic branch proximity $d_{\text{norm}}(b) \in [0, 1]$ at `JUMPI` opcodes and post-`SLOAD` stack words, and Foundry cheatcodes (`prank`, `warp`, `roll`, `deal`). |
| **`gfn-symbolic`** | `crates/gfn-symbolic/src/lib.rs`<br>`crates/gfn-symbolic/src/concolic_evm.rs`<br>`crates/gfn-symbolic/src/concretizer.rs`<br>`crates/gfn-symbolic/src/unsat_cache.rs`<br>`crates/gfn-symbolic/src/solver.rs` | **Hybrid Concolic SMT Engine (`ConcolicEvmTranslator`, `SymbolicConcretizer`, `TwoTierUnsatCache`, `SmtWorkerPool`)** encoding narrow arithmetic guards ($d_{\text{norm}} > 0.85$) into QF_BV (`BV256`) formulas, concretizing invariant storage slots and `evm_keccak256` bijections, and caching `SAT`/`UNSAT` resolutions in L1 `DashMap` + L2 `heed` LMDB. |
| **`gfn-engine`** | `crates/gfn-engine/src/lib.rs`<br>`crates/gfn-engine/src/rgat.rs`<br>`crates/gfn-engine/src/policy.rs`<br>`crates/gfn-engine/src/tb_loss.rs`<br>`crates/gfn-engine/src/reward_rnd.rs`<br>`crates/gfn-engine/src/replay_buffer.rs`<br>`crates/gfn-engine/src/rollout_worker.rs` | Core **Trajectory GFlowNet** neural engine: 6-layer edge-typed Relational Graph Attention Network (`StateGraphRgatEncoder`), 4-head `AutoregressiveForwardPolicyHead`, `BackwardPolicyHead`, `LogPartitionNet`, Huber-clipped `TrajectoryBalanceLoss`, `MstmPretrainLoss`, `compute_ewc_penalty`, `RndCuriosityModule` with `WelfordRunningStats`, `PrioritizedReplayBuffer` ($O(\log N)$ Fenwick `SumTree`), `OnlineAdaptationController`, and `TrainingStabilityController`. |
| **`gfn-verifier`** | `crates/gfn-verifier/src/lib.rs`<br>`crates/gfn-verifier/src/poc_synthesizer.rs`<br>`crates/gfn-verifier/src/patch_synthesizer.rs`<br>`crates/gfn-verifier/src/forge_gate.rs` | **Zero False-Positive Concrete Verification Gate (`ConcreteForgeVerifier`, `PocSynthesizer`, `AstPatchSynthesizer`)** that compiles and executes candidate exploit traces as standalone Foundry `ExploitPoC.t.sol` tests via `forge test --offline` (0.0% FPR gate) and synthesizes signature-aware AST remediation patches. |
| **`gfn-monitor`** | `crates/gfn-monitor/src/lib.rs`<br>`crates/gfn-monitor/src/drift.rs`<br>`crates/gfn-monitor/src/telemetry.rs` | Real-time **Prometheus Telemetry Exporter** (`TelemetryExporter`, `/metrics`) and **Statistical Drift Detector (`DriftDetector`)** computing Spectral $\text{MMD}^2$, Opcode $\text{PSI}$, Storage $D_{JS}$, RND Two-Sample $D_{KS}$, and Spearman $\rho_{TB}$ concept drift alerts. |
| **`gfn-cli`** | `crates/gfn-cli/src/main.rs`<br>`crates/gfn-cli/src/lib.rs`<br>`crates/gfn-cli/src/server.rs` | Unified `gfn-forge` binary CLI (`audit`, `pretrain`, `train`, `train-continual`, `serve`) and asynchronous Axum HTTP/REST + Server-Sent Events (SSE) server (`/v1/audits`, `/v1/audits/:id`, `/v1/audits/:id/stream`, `/openapi.json`, `/health`) with a 2 ms dynamic micro-batching actor. |

---

### 1.2 Native Desktop UI (`ui-desktop/src/`)

| Layer | Script Path | Responsibilities |
| :--- | :--- | :--- |
| **Entrypoint & Shell** | `ui-desktop/src/main.py`<br>`ui-desktop/src/app.py`<br>`ui-desktop/src/config.py` | Application bootstrap (`create_application`), dark engineering stylesheet, lazy-loaded 5-view `MainWindow` shell (cold start $\le 1.2\text{ s}$, private memory $< 95\text{ MB}$), and TOML configuration serialization (`ConfigManager`, `AuditConfig`, `TrainingHyperparameters`, `TRAINING_PRESETS`). |
| **IPC & Services** | `ui-desktop/src/services/process_manager.py`<br>`ui-desktop/src/services/sse_client.py`<br>`ui-desktop/src/services/prom_client.py` | Non-blocking `QProcess` lifecycle manager (`LocalProcessManager`), async `QNetworkAccessManager` SSE stream parser (`NativeSseClient`), and 1 Hz Prometheus `/metrics` text parser (`PrometheusScraper`). |
| **ViewModels (MVVM)** | `ui-desktop/src/viewmodels/audit_vm.py`<br>`ui-desktop/src/viewmodels/training_vm.py`<br>`ui-desktop/src/viewmodels/telemetry_vm.py` | Reactive Qt `QObject` state machines emitting typed `Signal` updates for the Audit Workbench, Multi-Phase Training Studio, Operational Telemetry, and 7-Gate Model Registry. |
| **Views & Widgets** | `ui-desktop/src/views/audit_view.py`<br>`ui-desktop/src/views/training_view.py`<br>`ui-desktop/src/views/trajectory_view.py`<br>`ui-desktop/src/views/telemetry_view.py`<br>`ui-desktop/src/views/registry_view.py`<br>`ui-desktop/src/views/widgets/metric_card.py`<br>`ui-desktop/src/views/widgets/code_editor.py`<br>`ui-desktop/src/views/widgets/dag_canvas.py` | Five specialized engineering workspaces: (1) Formal Audit & PoC Workbench, (2) Multi-Phase Training Studio, (3) Trajectory & HSDG Inspector, (4) Operational Telemetry & Drift Monitor, and (5) Model Registry & 7 Release Gates. |

---

## 2. Training Mechanism Stability Analysis & Refinements

During our deep audit of `crates/gfn-engine`, `crates/gfn-invariants`, `crates/gfn-cli`, and `configs/`, we identified and resolved eight structural sources of training instability across the 3-phase training pipeline:

### 2.1 Weighted Trajectory Balance Loss & Residual Safety Clamping (`crates/gfn-engine/src/tb_loss.rs`)
* **Previous Issue**: `TrajectoryBalanceLoss::forward` computed an unweighted mean over the batch (`huber_loss.mean(Kind::Float)`), ignoring Importance Sampling (IS) weights $w_i = (N \cdot P(i))^{-\beta_{\text{PER}}} / \max_j w_j$ produced by `PrioritizedReplayBuffer::sample_batch`. Furthermore, unbounded $\log Z_\theta$, $\sum \log P_F$, or $\sum \log P_B$ values on deep or out-of-distribution trajectories could cause $|\Delta_{TB}|$ to overflow before Huber clipping.
* **Refinement**:
  1. Added `TrajectoryBalanceLoss::forward_weighted` accepting `is_weights: Option<&Tensor>` to weight per-trajectory Huber losses by normalized PER Importance Sampling weights clamped to $[10^{-4}, 10.0]$.
  2. Added `max_residual_clip` (default $100.0$, configurable via `.with_residual_clip(...)` and `configs/curriculum_tb.toml`) and pre-clamped $\log Z_\theta \in [-50, 50]$, $\sum \log P_F \in [-200, 0]$, and $\sum \log P_B \in [-200, 0]$ in `Kind::Float` precision:
     $$\Delta_{TB}^{\text{safe}}(\tau; \theta) = \text{clip}\!\left(\log Z_\theta(s_0) + \sum_{t=0}^{n-1} \log P_F(s_{t+1} \mid s_t) - \log \text{clip}(R(s_n), R_{\min}, 10^6) - \sum_{t=1}^{n} \log P_B(s_{t-1} \mid s_t),\; -\Delta_{\max},\; \Delta_{\max}\right)$$

### 2.2 Smooth Piecewise Huber Loss & Logit Clamping in Phase 1 MSTM Pretraining (`crates/gfn-engine/src/tb_loss.rs`)
* **Previous Issue**: `MstmPretrainLoss::forward` computed `let delta_diff = (pred_delta - target_delta).abs(); let huber_delta_loss = delta_diff.mean(Kind::Float);`, which was an unclipped $L_1$ loss with discontinuous gradients at $0$, and passed raw unbounded logits into `binary_cross_entropy_with_logits` and `cross_entropy_for_logits`.
* **Refinement**:
  1. Replaced the $L_1$ approximation with an exact piecewise quadratic/linear smooth Huber loss parameterized by `huber_delta` ($\delta_{\text{MSTM}} = 1.0$).
  2. Clamped `pred_mutated_logits` and `pred_direction_logits` to $[-30.0, 30.0]$ prior to cross-entropy evaluation, guaranteeing finite `Kind::Float` losses and gradients.

### 2.3 Fisher Information Diagonal Clamping in Phase 3 EWC (`crates/gfn-engine/src/tb_loss.rs`)
* **Previous Issue**: In `compute_ewc_penalty`, sharp gradient spikes on specific parameters during Fisher estimation could produce arbitrarily large $F_i$, causing $\frac{1}{2} \lambda_{\text{EWC}} \sum_i F_i (\theta_i - \theta_i^*)^2$ (with $\lambda_{\text{EWC}} = 400.0$) to explode gradients during continual updates.
* **Refinement**: Clamped Fisher diagonal entries to $[0.0, 10^4]$ (`fisher_diag.clamp(0.0, 1e4)`) and parameter drift $(\theta_i - \theta_i^*)$ to $[-10.0, 10.0]$, ensuring stable quadratic regularization in strict `Kind::Float` precision.

### 2.4 Autoregressive Policy Logit Soft-Clamping & Full 4-Head Entropy (`crates/gfn-engine/src/policy.rs`)
* **Previous Issue**:
  1. `AutoregressiveForwardPolicyHead` passed raw MLP and pointer-network dot-product logits into `softmax` and `log_softmax` without bounding extreme values, and `compute_policy_entropy` only summed caller and function sub-head entropies while ignoring argument domain (`domain_mlp`) and environment manipulation (`env_mlp`) entropies.
  2. `LogPartitionNet` and `BackwardPolicyHead` had no output clamping.
* **Refinement**:
  1. Added `logit_clip_bound: f64` (default $30.0$, configurable via `.with_logit_clip(...)`) across all 4 autoregressive sub-heads in `sample_actions`, `evaluate_log_pf`, and `compute_policy_entropy`, and clamped sampling temperature to $[0.1, 10.0]$ and uniform exploration $\epsilon \in [0.0, 0.5]$.
  2. Upgraded `compute_policy_entropy` to evaluate the composite entropy across all 4 sub-heads:
     $$\bar{H}(P_F) = H(P_{\text{caller}}) + H(P_{\text{func}}) + 0.25 \cdot \left(\bar{H}(P_{\text{domain}}) + H(P_{\text{env}})\right)$$
  3. Clamped `LogPartitionNet::forward` to $[-50.0, 50.0]$ and `BackwardPolicyHead::evaluate_log_pb` to $[-100.0, 0.0]$.

### 2.5 Winsorized Welford & EMA Running Statistics for RND Curiosity (`crates/gfn-engine/src/reward_rnd.rs`)
* **Previous Issue**: `WelfordRunningStats::update` accepted raw squared L2 errors without filtering non-finite values or extreme early outliers, which could permanently inflate running variance $\sigma^2$ and collapse intrinsic novelty rewards $R_{\text{novelty}} \to 0$.
* **Refinement**:
  1. Added `WelfordRunningStats::update_winsorized(val, max_z_score)` (with $z_{\max} = 5.0$ after a 10-sample warm-up) and non-finite (`is_finite()`) filtering.
  2. Added Exponential Moving Average (`ema_mean`, `ema_var`, $\beta = 0.99$) tracking alongside Welford statistics and clamped predictor-target differences to $[-50.0, 50.0]$.

### 2.6 `TrainingStabilityController` & Bidirectional Adaptation (`crates/gfn-engine/src/rollout_worker.rs`)
* **Previous Issue**: `OnlineAdaptationController::check_entropy_guard` only boosted temperature when entropy collapsed ($\bar{H}(P_F) < 0.35\text{ nats}$) and never annealed temperature back down once exploration recovered. Moreover, there was no centralized controller for Linear Warmup + Cosine Annealing learning rate scheduling, global L2 gradient norm clipping, EMA loss tracking, or residual spike damping.
* **Refinement**:
  1. Upgraded `OnlineAdaptationController::check_entropy_guard` with bidirectional recovery: when $\bar{H}(P_F) > 1.2\text{ nats}$ and $\tau > 1.0$, temperature and novelty weight smoothly decay by $0.98\times$ per step back toward their baseline values ($\tau = 1.0, \beta = 0.5$).
  2. Implemented `TrainingStabilityController` and `StabilityStepReport` in `crates/gfn-engine/src/rollout_worker.rs` (wired into `RolloutWorker` and `crates/gfn-cli/src/main.rs`):
     * **Linear Warmup + Cosine Annealing Schedule (`compute_lr_schedule`)**:
       $$\eta(t) = \begin{cases} \eta_{\max} \cdot \frac{t + 1}{T_{\text{warmup}}} & \text{if } t < T_{\text{warmup}} \\ \eta_{\max} \cdot \left[\rho_{\min} + (1 - \rho_{\min}) \cdot \frac{1}{2}\left(1 + \cos\!\left(\pi \frac{t - T_{\text{warmup}}}{T_{\text{total}} - T_{\text{warmup}}}\right)\right)\right] & \text{if } t \ge T_{\text{warmup}} \end{cases}$$
       where $\rho_{\min} = 0.10$, applied synchronously to both $\eta_\theta(t)$ and $\eta_Z(t)$.
     * **Global L2 Gradient Norm Clipping & Residual Spike Damping (`observe_and_clip_step`)**:
       Tracks $\mathcal{L}_{\text{EMA}}(t) = \beta_{\text{EMA}} \mathcal{L}_{\text{EMA}}(t-1) + (1 - \beta_{\text{EMA}}) \mathcal{L}_{TB}(t)$, projects $\|\nabla_\theta \mathcal{L}\|_2 \le G_{\max}$, halves the effective step size (`step_scale = 0.5`, status `"SPIKE_DAMPED"`) whenever $\mathcal{L}_{TB}(t) > 2.5 \times \max(0.25, \mathcal{L}_{\text{EMA}}(t-1))$ post-warmup, and zeroes the step (`step_scale = 0.0`, status `"NAN_GUARD"`) if any non-finite value is encountered.

### 2.7 Drift-Free Binary `SumTree` & Bounded PER Priorities (`crates/gfn-engine/src/replay_buffer.rs`)
* **Previous Issue**: `SumTree::update` propagated priority deltas up the tree using incremental addition (`self.tree[tree_idx] += delta`). Over millions of replay updates, floating-point cancellation between large and small priorities causes internal node sums to drift from the true sum of their children. Additionally, `PrioritizedReplayBuffer::compute_priority` did not filter non-finite (`NaN`/`Inf`) or unbounded residuals.
* **Refinement**:
  1. Replaced `self.tree[tree_idx] += delta` in `SumTree::update` with exact child summation `self.tree[tree_idx] = (self.tree[2 * tree_idx] + self.tree[2 * tree_idx + 1]).max(0.0)` in $O(\log N)$ time, eliminating cumulative floating-point drift.
  2. Clamped rewards to $[0.0, 10^4]$ and residuals $|\Delta_{TB}|$ to $[0.0, 100.0]$ (with finite checks) in `compute_priority`.

### 2.8 Relational Graph Attention & HGT Logit Clamping (`crates/gfn-engine/src/rgat.rs`, `crates/gfn-invariants/src/hgt.rs`)
* **Previous Issue**: Raw dot-product attention scores in `RgatConvLayer::forward` and `HgtConvLayer::forward`, as well as slot/pair classification logits in `BilinearSlotMatcher`, were unclipped before `.exp()` / `.sigmoid()`.
* **Refinement**: Clamped scaled attention scores and bilinear matcher logits to $[-30.0, 30.0]$ across both the 6-layer `StateGraphRgatEncoder` and the 4-layer `HgtInvariantSynthesizer`.

### 2.9 Cross-Crate Symbolic, EVM, Extractor, Verifier & Server Hardening
* **Token-Boundary Storage Concretization (`crates/gfn-symbolic/src/concretizer.rs`)**:
  * Fixed a prefix-substring collision in `SymbolicConcretizer::concretize_query` where iterating over `BTreeMap<u64, U256>` in ascending order caused `slot_1` to partially replace `slot_10`. Implemented descending slot iteration (`.rev()`) combined with S-expression token-boundary matching (`replace_smt_token`).
* **Full 256-Bit Signed & Shift BitVector Evaluation (`crates/gfn-symbolic/src/solver.rs`)**:
  * Added EVM-exact 256-bit two's complement signed division (`bvsdiv` / `SDIV`), signed remainder (`bvsrem` / `SMOD`), shifts (`bvshl`, `bvlshr`, `bvashr`), negation (`bvneg`), and signed comparisons (`bvslt`, `bvsgt`, `bvsle`, `bvsge`) to `eval_ast` and `eval_bool`, and expanded `collect_vars` keyword filtering so BitVector operators and `evm_keccak256` are never misclassified as symbolic variables.
* **EVM Inspector `SLOAD` Post-Value Capture & `ISZERO` Distance (`crates/gfn-evm/src/inspector.rs`)**:
  * Added `pending_sload` tracking in `GfnEvmInspector::step` and `step_end` so `StorageAccessRecord.value` captures the actual 256-bit word pushed onto the stack after `SLOAD`, and added `opcode::ISZERO` branch distance calculation before `JUMPI`.
* **Batch-Aggregated & Finite-Sanitized Dynamic Graph Updates (`crates/gfn-extractor/src/hsdg_builder.rs`)**:
  * Updated `HsdgBuilder::update_dynamic_batch` to average dynamic storage features and branch telemetry across all `batch_size` environments while filtering non-finite values and clamping to $[-100.0, 100.0]$.
* **Adaptive Precondition & EIP-55 Checksum-Verified PoC Synthesis (`crates/gfn-verifier/src/patch_synthesizer.rs`, `crates/gfn-verifier/src/poc_synthesizer.rs`)**:
  * Added `adapt_precondition_to_signature` in `AstPatchSynthesizer` to match the target Solidity function's actual parameter identifier while preserving EIP-55 checksummed actor constants in `PocSynthesizer`.
* **End-to-End Prometheus & SSE Protocol Alignment (`crates/gfn-monitor/src/telemetry.rs`, `crates/gfn-cli/src/server.rs`, `crates/gfn-cli/src/main.rs`)**:
  * Aligned Prometheus gauge names (`gfn_revm_steps_per_sec_per_thread`, `gfn_smt_unsat_cache_hit_rate`) and SSE event envelopes (`emit_typed_event`) between the Rust backend and Python desktop client.

---

## 3. Native Desktop UI Updates (`ui-desktop/`)

To expose these training stability mechanisms to security engineers and ML practitioners, the following updates were implemented across `ui-desktop/`:

1. **`ui-desktop/src/config.py` (`TrainingHyperparameters`, `TRAINING_PRESETS`, `ConfigManager`)**:
   * Added `clip_grad_norm` (default `1.0`), `ema_decay` (default `0.95`), `logit_clip_bound` (default `30.0`), `entropy_reg_coeff` (default `0.01`), `target_entropy_nats` (default `0.35`), `enable_grad_spike_guard` (default `True`), and `max_residual_clip` (default `100.0`).
   * Updated `to_toml_dict()` and `ConfigManager.load_training_config()` to round-trip the `[stability]`, `[optim]`, and `[tb_loss]` sections from `configs/curriculum_tb.toml`.
   * Tailored stability parameters across all three presets (`Smoke Test`, `Production DeFi Tuning`, and `Deep Exploit Search`).
2. **`ui-desktop/src/viewmodels/training_vm.py` (`TrainingViewModel`)**:
   * Added `compute_lr_schedule(step)` implementing Linear Warmup + Cosine Annealing for $(\eta_\theta, \eta_Z)$.
   * Added rolling telemetry buffers `loss_ema_history` and `grad_norm_history`, plus live state counters `current_grad_norm`, `grad_clip_events`, `spike_damp_events`, and `stability_status`.
   * Emits real-time EMA loss, clipped gradient norm, scheduled learning rates, and stability guard status in `telemetry_step_emitted`.
3. **`ui-desktop/src/views/training_view.py` (`TrainingStudioView`)**:
   * **Step 2 Controls**: Added interactive spinboxes and toggles for **Grad Clip $\|\mathbf{g}\|_2$** (`grad_clip_spin`), **Warmup Steps** (`warmup_steps_spin`), **EMA Decay $\beta$** (`ema_decay_spin`), and **Cosine LR + Spike Guard** (`spike_guard_chk`).
   * **Live 60 FPS Telemetry Dashboard**:
     * Added a fifth KPI card: **`GRADIENT NORM ‖g‖₂ & GUARD`** (`card_stability`) displaying live clipped gradient norm against $G_{\max}$ and a dynamic status badge (`STABLE`, `WARMUP`, `GRAD_CLIPPED`, `SPIKE_DAMPED`, or `NAN_GUARD`).
     * Added a dashed orange **EMA $\mathcal{L}_{TB}$ overlay curve** (`curve_loss_ema`) with a legend (`addLegend`) onto the Trajectory Balance Loss `PyQtGraph` plot alongside raw $\mathcal{L}_{TB}$ and red Huber-clipped scatter markers.
     * Updated the **`TRAJECTORY BALANCE LOSS (L_TB)`** card to display both instantaneous $\mathcal{L}_{TB}$ and smoothed $\text{EMA }\mathcal{L}_{TB}$.
4. **`ui-desktop/src/viewmodels/telemetry_vm.py` (`TelemetryViewModel::scan_checkpoints`)**:
   * Fixed `Path.with_extension("manifest.json")` (a Rust `std::path::Path` method name) to Python's `Path.with_suffix(".manifest.json")` when discovering live `.safetensors` checkpoints on disk, and preserved the three canonical reference checkpoints alongside newly discovered artifacts.
5. **Visual Quality, Intuitiveness & Readability Polish Across All 5 Views**:
   * **`ui-desktop/resources/styles/dark_theme.qss`**: Upgraded the global dark engineering stylesheet with pill-styled `QGroupBox::title` headers, custom `QToolTip` badges, gradient `QProgressBar` and `QSlider` grooves, rounded `NavButton` active indicators, and refined table/input focus rings.
   * **`ui-desktop/src/views/widgets/metric_card.py` (`MetricCardWidget`)**: Added a color-coded left accent border (`border-left: 3px solid {accent_color}`), refined typography spacing, and preserved distinct metric accent colors across `"ok"` / `"normal"` badge states while escalating to amber/red on `"warn"` / `"alert"`.
   * **`ui-desktop/src/app.py` (`MainWindow`)**: Added keyboard shortcuts (`Ctrl+1` .. `Ctrl+5`), rich tooltips, a dynamic `active_view_badge` indicator in the top toolbar with a right-aligned spacer for daemon controls, and a styled `VERIFIED SYSTEM SLAs` card in the navigation sidebar.
   * **Mathematical Typography & Interactive Controls (`audit_view.py`, `training_view.py`, `trajectory_view.py`, `telemetry_view.py`, `registry_view.py`)**:
     * Replaced literal `&&` in `QGroupBox` headers (which Qt renders literally on `QGroupBox` unlike button mnemonics) with clean `&` headers.
     * Upgraded ASCII approximations with crisp mathematical symbols (`η_θ`, `η_Z`, `δ_TB`, `λ_EWC`, `‖g‖₂`, `ρ_TB`, `log Z_θ`, `MMD²`, `|Δ_TB|`, `≥`, `≤`, `±`, `→`).
     * Added dynamic phase badge highlighting in `TrainingStudioView._on_phase_toggled`, dynamic `SAT` (purple) vs `UNSAT` (red) pill badges and transport controls (`⏮ First`, `◀ Prev`, `▶ Play`, `Next ▶`, `Last ⏭`) in `TrajectoryInspectorView`, chart legends in `OperationalTelemetryView`, and center-aligned status/confidence columns in `AuditWorkbenchView`.

---

## 4. Verification Summary

* **Rust Workspace Tests (`cargo test`)**: All unit and integration tests across `gfn-common`, `gfn-extractor`, `gfn-invariants`, `gfn-evm`, `gfn-symbolic`, `gfn-engine`, `gfn-verifier`, `gfn-monitor`, and `gfn-cli` pass with zero warnings or `unwrap`/`expect` violations.
* **Native Desktop UI Tests (`pytest ui-desktop/tests/test_ui_desktop.py`)**: All 4 comprehensive test suites pass, confirming:
  * Cold startup latency $\le 1.2\text{ s}$ and idle private memory $< 95\text{ MB}$.
  * Full TOML round-trip serialization of `[stability]`, `[optim]`, and `[tb_loss]` parameters.
  * Live `TrainingViewModel` and `TrainingStudioView` synchronization of stability controls, EMA loss curves, and gradient clipping telemetry.
