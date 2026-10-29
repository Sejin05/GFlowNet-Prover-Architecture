#![deny(clippy::unwrap_used, clippy::expect_used, unsafe_op_in_unsafe_fn)]

//! GFlowNet-Prover Extractor: Foundry compiler, Solar CFG lifter, and HSDG builder.
//!
//! Ingests multi-contract Solidity codebases and compiles them into a Heterogeneous
//! State-Dependency Graph (HSDG) with strictly typed node/edge tensors.

pub mod cfg_lifter;
pub mod compiler;
pub mod hsdg_builder;
pub mod proxy_resolver;

// Re-export core public interfaces
pub use cfg_lifter::{EdgeRelation, HsdgEdge, HsdgNode, ProjectCfgGraph, SsaCfgLifter};
pub use compiler::ProjectExtractor;
pub use hsdg_builder::{HeteroGraphTensors, HsdgBuilder, HsdgValidator};
pub use proxy_resolver::ProxySlotResolver;
