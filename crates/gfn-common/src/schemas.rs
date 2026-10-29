#![deny(clippy::unwrap_used, clippy::expect_used, unsafe_op_in_unsafe_fn)]

//! Strongly typed, zero-copy data schemas for GFlowNet-Prover.

use rkyv::{Archive, Deserialize as RkyvDeserialize, Serialize as RkyvSerialize};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

/// Normalized Solidity storage slot types (18 variants).
#[derive(
    Debug,
    Clone,
    Copy,
    PartialEq,
    Eq,
    Hash,
    Serialize,
    Deserialize,
    Archive,
    RkyvSerialize,
    RkyvDeserialize,
)]
#[archive(check_bytes)]
#[repr(u8)]
pub enum SoliditySlotType {
    Uint256 = 0,
    Uint128 = 1,
    Uint64 = 2,
    Uint32 = 3,
    Uint8 = 4,
    Int256 = 5,
    Int128 = 6,
    Address = 7,
    Bool = 8,
    Bytes32 = 9,
    BytesN = 10,
    MappingAddressUint = 11,
    MappingAddressAddress = 12,
    MappingNested = 13,
    Struct = 14,
    DynamicArray = 15,
    StaticArray = 16,
    StringOrBytes = 17,
}

/// Classified semantic role for EVM storage slots (8 variants).
#[derive(
    Debug,
    Clone,
    Copy,
    PartialEq,
    Eq,
    Hash,
    Serialize,
    Deserialize,
    Archive,
    RkyvSerialize,
    RkyvDeserialize,
)]
#[archive(check_bytes)]
#[repr(u8)]
pub enum StorageSemanticRole {
    AssetBalance = 0,
    TotalSupply = 1,
    PoolReserve = 2,
    DebtShare = 3,
    OraclePrice = 4,
    AdminRole = 5,
    ReentrancyLock = 6,
    GenericState = 7,
}

/// Record describing a single state variable's physical layout in contract storage.
#[derive(
    Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Archive, RkyvSerialize, RkyvDeserialize,
)]
#[archive(check_bytes)]
pub struct StorageSlotRecord {
    pub slot_id: u64,
    pub byte_offset: u8,
    pub byte_size: u8,
    pub solidity_type: SoliditySlotType,
    pub is_dynamic_mapping: bool,
    pub semantic_role: StorageSemanticRole,
}

/// Extracted Foundry contract compilation artifact.
#[derive(
    Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Archive, RkyvSerialize, RkyvDeserialize,
)]
#[archive(check_bytes)]
pub struct FoundryContractArtifact {
    pub project_id: Uuid,
    pub contract_name: String,
    pub source_path: String,
    pub solc_version: String,
    pub deployed_bytecode_hash: [u8; 32],
    pub deployed_bytecode: Vec<u8>,
    pub abi_json_str: String,
    pub storage_slots: Vec<StorageSlotRecord>,
}

/// Invariant domain classification categories.
#[derive(
    Debug,
    Clone,
    Copy,
    PartialEq,
    Eq,
    Hash,
    Serialize,
    Deserialize,
    Archive,
    RkyvSerialize,
    RkyvDeserialize,
)]
#[archive(check_bytes)]
#[repr(u8)]
pub enum InvariantCategory {
    Solvency = 0,
    Monotonicity = 1,
    AccessControl = 2,
    PrecisionNeutrality = 3,
}

/// Parameterized safety invariant synthesized by HGT or template rules.
#[derive(
    Debug, Clone, PartialEq, Serialize, Deserialize, Archive, RkyvSerialize, RkyvDeserialize,
)]
#[archive(check_bytes)]
pub struct SynthesizedInvariant {
    pub invariant_id: String,
    pub category: InvariantCategory,
    pub formal_expression: String,
    pub confidence: f64,
    pub involved_slots: Vec<u64>,
}

/// Concrete transaction step executed inside a rollout trajectory.
#[derive(
    Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Archive, RkyvSerialize, RkyvDeserialize,
)]
#[archive(check_bytes)]
pub struct TrajectoryStepRecord {
    pub step_idx: usize,
    pub caller_role: String,
    pub caller_address: [u8; 20],
    pub target_contract: String,
    pub function_signature: String,
    pub concrete_calldata_hex: String,
    pub decoded_args: Vec<String>,
    pub vm_warp_sec: u64,
    pub vm_roll_blocks: u64,
}

/// Complete multi-step transaction trajectory record for replay and verification.
#[derive(
    Debug, Clone, PartialEq, Serialize, Deserialize, Archive, RkyvSerialize, RkyvDeserialize,
)]
#[archive(check_bytes)]
pub struct TrajectoryRecord {
    pub trajectory_id: String,
    pub steps: Vec<TrajectoryStepRecord>,
    pub terminal_reward: f64,
    pub violated_invariant_id: Option<String>,
    pub is_exploit: bool,
    pub log_pf: f32,
    pub log_pb: f32,
}

/// Project source configuration for audit submission.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ProjectSourceConfig {
    pub workspace_path: String,
    #[serde(default = "default_setup_contract")]
    pub setup_contract: String,
    #[serde(default = "default_setup_function")]
    pub setup_function: String,
    #[serde(default)]
    pub target_contracts: Vec<String>,
}

fn default_setup_contract() -> String {
    "ExploitHarnessTest".to_string()
}

fn default_setup_function() -> String {
    "setUp".to_string()
}

/// Compiler and EVM version configuration for the target protocol.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct FoundryProfileConfig {
    #[serde(default = "default_solc_version")]
    pub solc_version: String,
    #[serde(default = "default_evm_version")]
    pub evm_version: String,
    #[serde(default)]
    pub fork_block_number: Option<u64>,
}

fn default_solc_version() -> String {
    "0.8.24".to_string()
}

fn default_evm_version() -> String {
    "cancun".to_string()
}

/// Search budget and exploration parameters for an audit.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SearchBudgetConfig {
    #[serde(default = "default_max_trajectories")]
    pub max_trajectories: usize,
    #[serde(default = "default_max_depth")]
    pub max_depth: usize,
    #[serde(default = "default_batch_size")]
    pub batch_size: usize,
    #[serde(default = "default_wall_clock_timeout_sec")]
    pub wall_clock_timeout_sec: u64,
    #[serde(default = "default_smt_timeout_ms")]
    pub smt_timeout_ms: u64,
    #[serde(default = "default_enable_online_adaptation")]
    pub enable_online_adaptation: bool,
}

fn default_max_trajectories() -> usize {
    100_000
}

fn default_max_depth() -> usize {
    15
}

fn default_batch_size() -> usize {
    64
}

fn default_wall_clock_timeout_sec() -> u64 {
    900
}

fn default_smt_timeout_ms() -> u64 {
    5_000
}

fn default_enable_online_adaptation() -> bool {
    true
}

/// Top-level audit submission request payload.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AuditSubmissionRequest {
    pub project_source: ProjectSourceConfig,
    pub foundry_profile: FoundryProfileConfig,
    pub search_budget: SearchBudgetConfig,
}

/// Lifecycle status of an audit job.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum AuditStatus {
    Queued,
    ExtractingGraph,
    ExploringGflownet,
    VerifyingPoc,
    Completed,
    Failed,
}

/// Real-time execution telemetry metrics for an ongoing or completed audit.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AuditTelemetry {
    pub trajectories_evaluated: usize,
    pub revm_tps: f64,
    pub smt_queries_total: usize,
    pub smt_sat_hits: usize,
    pub smt_unsat_hits: usize,
    pub elapsed_sec: f64,
    pub log_z_estimate: f64,
}

/// Verified exploit finding confirmed by concrete `forge test` execution.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct VerifiedFinding {
    pub finding_id: String,
    pub violated_invariant_id: String,
    pub severity: String,
    pub trajectory_steps: Vec<TrajectoryStepRecord>,
    pub foundry_poc_path: String,
    pub foundry_poc_solidity_code: String,
    pub forge_test_stdout: String,
    pub minimal_negated_precondition: String,
    pub remediation_patch_diff: String,
}

/// Complete response object returned by audit status and retrieval endpoints.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AuditResultResponse {
    pub audit_id: Uuid,
    pub status: AuditStatus,
    pub telemetry: AuditTelemetry,
    pub synthesized_invariants: Vec<SynthesizedInvariant>,
    pub verified_findings: Vec<VerifiedFinding>,
}

/// Taxonomy of failure modes encountered during offline evaluation.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum EvaluationErrorKind {
    InvariantSynthesisMiss,
    FlowUnderexplored,
    SmtSolverTimeout,
    RevmForgeMismatch,
    PatchRegression,
}
