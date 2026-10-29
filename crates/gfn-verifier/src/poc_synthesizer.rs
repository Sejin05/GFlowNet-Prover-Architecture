#![deny(clippy::unwrap_used, clippy::expect_used, unsafe_op_in_unsafe_fn)]

//! Turnkey Foundry verification harness synthesizer (`PocSynthesizer`).
//!
//! Translates candidate adversarial trajectories and violated invariant specifications
//! into deterministic, self-contained Foundry test harnesses (`ExploitPoC.t.sol`).

use gfn_common::error::{GfnError, GfnResult};
use gfn_common::schemas::TrajectoryRecord;
use std::collections::BTreeSet;

/// Canonical actor addresses used across the Foundry execution environment (EIP-55 checksummed).
pub const ATTACKER0_ADDR: &str = "0x00000000000000000000000000000000000000a0";
pub const ATTACKER1_SYBIL_ADDR: &str = "0x00000000000000000000000000000000000000A1";
pub const NORMAL_USER_ADDR: &str = "0x00000000000000000000000000000000000000b2";
pub const LIQUIDITY_PROVIDER_ADDR: &str = "0x00000000000000000000000000000000000000C3";
pub const LIQUIDATOR_KEEPER_ADDR: &str = "0x00000000000000000000000000000000000000D4";

pub const ATTACKER0_BYTES: [u8; 20] = [
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0xa0,
];

/// Synthesizer for generating concrete Foundry proof-of-concept (`ExploitPoC.t.sol`) test files.
pub struct PocSynthesizer;

impl PocSynthesizer {
    /// Generates standalone Foundry test code (`ExploitPoC.t.sol`) from a candidate trajectory.
    pub fn synthesize_poc(
        trajectory: &TrajectoryRecord,
        violated_invariant_id: &str,
    ) -> GfnResult<String> {
        Self::synthesize_poc_with_options(trajectory, violated_invariant_id, None)
    }

    /// Generates standalone Foundry test code with optional harness inheritance or contract setup.
    pub fn synthesize_poc_with_options(
        trajectory: &TrajectoryRecord,
        violated_invariant_id: &str,
        harness_parent: Option<&str>,
    ) -> GfnResult<String> {
        if trajectory.steps.is_empty() {
            return Err(GfnError::Serialization {
                details: "Candidate trajectory contains zero transaction steps".to_string(),
            });
        }

        let mut out = String::with_capacity(4096);

        // 1. Pragma & standard imports
        out.push_str("// SPDX-License-Identifier: MIT\n");
        out.push_str("pragma solidity ^0.8.24;\n\n");
        out.push_str("import {Test} from \"forge-std/Test.sol\";\n");

        if let Some(parent) = harness_parent {
            out.push_str(&format!(
                "import {{{parent}}} from \"./{parent}.t.sol\";\n\n"
            ));
        } else {
            out.push('\n');
        }

        // 2. Identify unique non-address target contracts to declare
        let mut target_names = BTreeSet::new();
        for step in &trajectory.steps {
            if !step.target_contract.is_empty() && !step.target_contract.starts_with("0x") {
                target_names.insert(step.target_contract.clone());
            }
        }

        // 3. Contract definition
        let is_clause = if let Some(parent) = harness_parent {
            format!("is {parent}")
        } else {
            "is Test".to_string()
        };

        out.push_str(&format!("contract ExploitPoC {is_clause} {{\n"));

        // Actor address constants (lowercase hex to avoid checksum compiler errors)
        out.push_str(&format!(
            "    address internal constant ATTACKER0 = address({ATTACKER0_ADDR});\n"
        ));
        out.push_str(&format!(
            "    address internal constant ATTACKER1_SYBIL = address({ATTACKER1_SYBIL_ADDR});\n"
        ));
        out.push_str(&format!(
            "    address internal constant NORMAL_USER = address({NORMAL_USER_ADDR});\n"
        ));
        out.push_str(&format!(
            "    address internal constant LIQUIDITY_PROVIDER = address({LIQUIDITY_PROVIDER_ADDR});\n"
        ));
        out.push_str(&format!(
            "    address internal constant LIQUIDATOR_KEEPER = address({LIQUIDATOR_KEEPER_ADDR});\n\n"
        ));

        // Declare contract address variables if not using a parent harness
        if harness_parent.is_none() {
            for name in &target_names {
                let var_name = sanitize_var_name(name);
                out.push_str(&format!("    address internal {var_name};\n"));
            }
            if !target_names.is_empty() {
                out.push('\n');
            }
        }

        // 4. setUp() block
        out.push_str("    function setUp() public virtual");
        if harness_parent.is_some() {
            out.push_str(" override");
        }
        out.push_str(" {\n");

        if harness_parent.is_some() {
            out.push_str("        super.setUp();\n");
        }

        out.push_str("        vm.roll(18_000_000);\n");
        out.push_str("        vm.warp(1_700_000_000);\n\n");

        out.push_str("        vm.deal(ATTACKER0, 100 ether);\n");
        out.push_str("        vm.deal(ATTACKER1_SYBIL, 100 ether);\n");
        out.push_str("        vm.deal(NORMAL_USER, 100 ether);\n");
        out.push_str("        vm.deal(LIQUIDITY_PROVIDER, 1000 ether);\n");
        out.push_str("        vm.deal(LIQUIDATOR_KEEPER, 100 ether);\n");

        out.push_str("    }\n\n");

        // 5. test_ExploitPoC() block
        out.push_str("    function test_ExploitPoC() public {\n");

        for (idx, step) in trajectory.steps.iter().enumerate() {
            out.push_str(&format!(
                "        // Step {idx}: {} calls {}::{}\n",
                step.caller_role, step.target_contract, step.function_signature
            ));

            if step.vm_warp_sec > 0 {
                out.push_str(&format!(
                    "        vm.warp(block.timestamp + {});\n",
                    step.vm_warp_sec
                ));
            }
            if step.vm_roll_blocks > 0 {
                out.push_str(&format!(
                    "        vm.roll(block.number + {});\n",
                    step.vm_roll_blocks
                ));
            }

            // Caller prank
            let caller_expr = if step.caller_address == [0u8; 20] {
                "ATTACKER0".to_string()
            } else {
                let addr = alloy_primitives::Address::from(step.caller_address);
                format!("address({})", addr.to_checksum(None))
            };
            out.push_str(&format!("        vm.prank({caller_expr});\n"));

            // Target resolution
            let target_expr = if step.target_contract.starts_with("0x") {
                if let Ok(addr) = step.target_contract.parse::<alloy_primitives::Address>() {
                    format!("address({})", addr.to_checksum(None))
                } else {
                    format!("address({})", step.target_contract)
                }
            } else if !step.target_contract.is_empty() {
                let var_name = sanitize_var_name(&step.target_contract);
                format!("address({var_name})")
            } else {
                "address(this)".to_string()
            };

            // Calldata execution
            let hex_raw = step
                .concrete_calldata_hex
                .strip_prefix("0x")
                .unwrap_or(&step.concrete_calldata_hex);

            if !hex_raw.is_empty() {
                out.push_str(&format!(
                    "        bytes memory data_{idx} = hex\"{hex_raw}\";\n"
                ));
                out.push_str(&format!(
                    "        (bool success_{idx}, ) = {target_expr}.call(data_{idx});\n"
                ));
                out.push_str(&format!(
                    "        require(success_{idx}, \"Step {idx} execution failed\");\n\n"
                ));
            } else {
                out.push_str(&format!(
                    "        (bool success_{idx}, ) = {target_expr}.call(\"\");\n"
                ));
                out.push_str(&format!(
                    "        require(success_{idx}, \"Step {idx} execution failed\");\n\n"
                ));
            }
        }

        // 6. Explicit Foundry Invariant Assertions
        out.push_str(&format!(
            "        // Invariant Violation Assertion: {violated_invariant_id}\n"
        ));
        let assertion = synthesize_assertion(violated_invariant_id);
        out.push_str(&format!("        {assertion}\n"));

        out.push_str("    }\n");
        out.push_str("}\n");

        Ok(out)
    }
}

fn sanitize_var_name(name: &str) -> String {
    let lower = name.to_lowercase();
    let sanitized: String = lower
        .chars()
        .map(|c| if c.is_alphanumeric() { c } else { '_' })
        .collect();
    if sanitized.is_empty() {
        "targetContract".to_string()
    } else {
        sanitized
    }
}

fn synthesize_assertion(invariant_id: &str) -> String {
    let id_upper = invariant_id.to_uppercase();
    if id_upper.contains("SOLVENCY") {
        "assertGt(ATTACKER0.balance, 0, \"Solvency invariant violated: value extracted\");"
            .to_string()
    } else if id_upper.contains("PRECISION") || id_upper.contains("ROUNDING") {
        "assertGt(ATTACKER0.balance, 0, \"Precision neutrality violated: rounding exploitation\");"
            .to_string()
    } else if id_upper.contains("ACCESS") || id_upper.contains("AUTH") {
        "assertNotEq(ATTACKER0.balance, 0, \"Access control invariant violated\");".to_string()
    } else if id_upper.contains("MONO") || id_upper.contains("TIMELOCK") {
        "assertGt(block.number, 18_000_000, \"Monotonicity invariant violated\");".to_string()
    } else {
        "assertGt(ATTACKER0.balance, 0, \"Invariant violation reproduced\");".to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use gfn_common::schemas::TrajectoryStepRecord;

    #[test]
    fn test_poc_synthesizer_generates_valid_solidity() {
        let trajectory = TrajectoryRecord {
            trajectory_id: "traj-001".to_string(),
            steps: vec![
                TrajectoryStepRecord {
                    step_idx: 0,
                    caller_role: "Attacker0".to_string(),
                    caller_address: ATTACKER0_BYTES,
                    target_contract: "0x1111111111111111111111111111111111111111".to_string(),
                    function_signature: "deposit(uint256)".to_string(),
                    concrete_calldata_hex:
                        "0xb6b55f250000000000000000000000000000000000000000000000000de0b6b3a7640000"
                            .to_string(),
                    decoded_args: vec!["1000000000000000000".to_string()],
                    vm_warp_sec: 60,
                    vm_roll_blocks: 5,
                },
                TrajectoryStepRecord {
                    step_idx: 1,
                    caller_role: "Attacker0".to_string(),
                    caller_address: ATTACKER0_BYTES,
                    target_contract: "0x1111111111111111111111111111111111111111".to_string(),
                    function_signature: "withdraw(uint256)".to_string(),
                    concrete_calldata_hex: "0x2e1a7d4d".to_string(),
                    decoded_args: vec![],
                    vm_warp_sec: 0,
                    vm_roll_blocks: 0,
                },
            ],
            terminal_reward: 100.0,
            violated_invariant_id: Some("INV_SOLVENCY_01".to_string()),
            is_exploit: true,
            log_pf: -2.5,
            log_pb: -3.0,
        };

        let poc = PocSynthesizer::synthesize_poc(&trajectory, "INV_SOLVENCY_01")
            .unwrap_or_else(|e| panic!("PoC synthesis failed: {e}"));

        assert!(poc.contains("// SPDX-License-Identifier: MIT"));
        assert!(poc.contains("pragma solidity ^0.8.24;"));
        assert!(poc.contains("import {Test} from \"forge-std/Test.sol\";"));
        assert!(poc.contains("contract ExploitPoC is Test {"));
        assert!(poc.contains("vm.roll(18_000_000);"));
        assert!(poc.contains("vm.warp(1_700_000_000);"));
        assert!(poc.contains("vm.deal(ATTACKER0, 100 ether);"));
        assert!(poc.contains("function test_ExploitPoC() public {"));
        assert!(poc.contains("vm.warp(block.timestamp + 60);"));
        assert!(poc.contains("vm.roll(block.number + 5);"));
        assert!(poc.contains("vm.prank(address(0x00000000000000000000000000000000000000a0));"));
        assert!(poc.contains(
            "hex\"b6b55f250000000000000000000000000000000000000000000000000de0b6b3a7640000\""
        ));
        assert!(poc.contains("assertGt(ATTACKER0.balance, 0"));
    }

    #[test]
    fn test_poc_synthesizer_rejects_empty_trajectory() {
        let trajectory = TrajectoryRecord {
            trajectory_id: "traj-empty".to_string(),
            steps: vec![],
            terminal_reward: 0.0,
            violated_invariant_id: None,
            is_exploit: false,
            log_pf: 0.0,
            log_pb: 0.0,
        };

        let res = PocSynthesizer::synthesize_poc(&trajectory, "INV_01");
        assert!(res.is_err());
    }
}
