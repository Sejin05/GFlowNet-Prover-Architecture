#![deny(clippy::unwrap_used, clippy::expect_used, unsafe_op_in_unsafe_fn)]

//! Concrete Foundry Verification Gate (`ConcreteForgeVerifier`).
//!
//! Enforces a strict 0.0% False Positive Rate (FPR) gate by executing candidate
//! invariant violations inside full-featured Foundry tests (`forge test --offline`),
//! followed by automated AST remediation patch synthesis and non-regression auditing.

use crate::patch_synthesizer::AstPatchSynthesizer;
use crate::poc_synthesizer::PocSynthesizer;
use gfn_common::error::{GfnError, GfnResult};
use gfn_common::schemas::{TrajectoryRecord, VerifiedFinding};
use std::path::{Path, PathBuf};

/// Concrete Foundry verification and automated remediation patch gatekeeper.
pub struct ConcreteForgeVerifier {
    project_root: PathBuf,
}

impl ConcreteForgeVerifier {
    /// Constructs a new `ConcreteForgeVerifier` for the specified project root.
    pub fn new(project_root: &Path) -> Self {
        Self {
            project_root: project_root.to_path_buf(),
        }
    }

    /// Writes `ExploitPoC.t.sol`, executes `forge test --offline`, synthesizes AST patch,
    /// and validates non-regression. Returns `Err(GfnError::FalsePositiveRejected)` if `forge test` fails.
    pub async fn verify_and_synthesize(
        &self,
        candidate_trajectory: &TrajectoryRecord,
        violated_invariant_id: &str,
    ) -> GfnResult<VerifiedFinding> {
        if candidate_trajectory.steps.is_empty() {
            return Err(GfnError::Serialization {
                details: "Candidate trajectory contains zero transaction steps".to_string(),
            });
        }

        // 1. Synthesize ExploitPoC.t.sol
        let test_dir = self.project_root.join("test");
        if !test_dir.exists() {
            std::fs::create_dir_all(&test_dir).map_err(|e| GfnError::CompilationArtifact {
                reason: format!(
                    "Failed to create test directory {}: {e}",
                    test_dir.display()
                ),
            })?;
        }

        let harness_exists = test_dir.join("ExploitHarness.t.sol").exists();
        let harness_parent = if harness_exists {
            Some("ExploitHarness")
        } else {
            None
        };

        let poc_solidity_code = PocSynthesizer::synthesize_poc_with_options(
            candidate_trajectory,
            violated_invariant_id,
            harness_parent,
        )?;

        let poc_path = test_dir.join("ExploitPoC.t.sol");
        std::fs::write(&poc_path, &poc_solidity_code).map_err(|e| {
            GfnError::CompilationArtifact {
                reason: format!("Failed to write {}: {e}", poc_path.display()),
            }
        })?;

        // 2. Execute concrete forge test --match-test test_ExploitPoC -vvvv --offline
        let forge_output = tokio::process::Command::new("forge")
            .arg("test")
            .arg("--match-test")
            .arg("test_ExploitPoC")
            .arg("-vvvv")
            .arg("--offline")
            .current_dir(&self.project_root)
            .env("FOUNDRY_OFFLINE", "true")
            .output()
            .await;

        let output = match forge_output {
            Ok(out) => out,
            Err(e) => {
                let _ = std::fs::remove_file(&poc_path);
                return Err(GfnError::CompilationArtifact {
                    reason: format!("Failed to spawn `forge test`: {e}"),
                });
            }
        };

        let stdout = String::from_utf8_lossy(&output.stdout).to_string();
        let stderr = String::from_utf8_lossy(&output.stderr).to_string();

        // Strict 0.0% False Positive Gate: If the PoC fails, reject immediately
        if !output.status.success() {
            let _ = std::fs::remove_file(&poc_path);
            let combined_err = format!("{stdout}\n{stderr}");
            return Err(GfnError::FalsePositiveRejected {
                stdout: combined_err,
            });
        }

        // 3. Exploit confirmed concretely! Now synthesize AST remediation patch
        let patch_result = AstPatchSynthesizer::synthesize_patch(
            &self.project_root,
            candidate_trajectory,
            violated_invariant_id,
        )?;

        // 4. Automated Patch Non-Regression Verification
        if patch_result.target_file.exists() {
            let original_content =
                std::fs::read_to_string(&patch_result.target_file).map_err(|e| {
                    GfnError::Serialization {
                        details: format!(
                            "Failed to read target file {}: {e}",
                            patch_result.target_file.display()
                        ),
                    }
                })?;

            // Apply patch
            std::fs::write(&patch_result.target_file, &patch_result.patched_source).map_err(
                |e| GfnError::Serialization {
                    details: format!(
                        "Failed to apply patch to {}: {e}",
                        patch_result.target_file.display()
                    ),
                },
            )?;

            // a) Verify that the exploit is now blocked (test_ExploitPoC must fail)
            let post_patch_output = tokio::process::Command::new("forge")
                .arg("test")
                .arg("--match-test")
                .arg("test_ExploitPoC")
                .arg("--offline")
                .current_dir(&self.project_root)
                .env("FOUNDRY_OFFLINE", "true")
                .output()
                .await;

            let exploit_blocked = match post_patch_output {
                Ok(out) => !out.status.success(),
                Err(_) => false,
            };

            // b) Run benign regression test suite: forge test --no-match-contract ExploitPoC --offline
            let benign_output = tokio::process::Command::new("forge")
                .arg("test")
                .arg("--no-match-contract")
                .arg("ExploitPoC")
                .arg("--offline")
                .current_dir(&self.project_root)
                .env("FOUNDRY_OFFLINE", "true")
                .output()
                .await;

            let benign_passed = match benign_output {
                Ok(out) => out.status.success(),
                Err(_) => false,
            };

            // Restore original unpatched source to leave workspace untouched
            let _ = std::fs::write(&patch_result.target_file, original_content);

            if !exploit_blocked || !benign_passed {
                let _ = std::fs::remove_file(&poc_path);
                return Err(GfnError::FalsePositiveRejected {
                    stdout: format!(
                        "Patch validation check failed: exploit_blocked={exploit_blocked}, benign_passed={benign_passed}"
                    ),
                });
            }
        }

        // Clean up ExploitPoC test file
        let _ = std::fs::remove_file(&poc_path);

        let severity = if violated_invariant_id.to_uppercase().contains("SOLVENCY")
            || violated_invariant_id.to_uppercase().contains("PRECISION")
        {
            "CRITICAL".to_string()
        } else {
            "HIGH".to_string()
        };

        Ok(VerifiedFinding {
            finding_id: format!("FINDING-{}", uuid::Uuid::new_v4()),
            violated_invariant_id: violated_invariant_id.to_string(),
            severity,
            trajectory_steps: candidate_trajectory.steps.clone(),
            foundry_poc_path: poc_path.to_string_lossy().to_string(),
            foundry_poc_solidity_code: poc_solidity_code,
            forge_test_stdout: stdout,
            minimal_negated_precondition: patch_result.minimal_negated_precondition,
            remediation_patch_diff: patch_result.remediation_patch_diff,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use gfn_common::schemas::TrajectoryStepRecord;

    fn setup_test_foundry_project() -> PathBuf {
        let temp_dir =
            std::env::temp_dir().join(format!("gfn_verifier_test_{}", uuid::Uuid::new_v4()));
        let src_dir = temp_dir.join("src");
        let test_dir = temp_dir.join("test");
        let lib_dir = temp_dir.join("lib").join("forge-std").join("src");

        std::fs::create_dir_all(&src_dir).unwrap_or_else(|e| panic!("mkdir src failed: {e}"));
        std::fs::create_dir_all(&test_dir).unwrap_or_else(|e| panic!("mkdir test failed: {e}"));
        std::fs::create_dir_all(&lib_dir).unwrap_or_else(|e| panic!("mkdir lib failed: {e}"));

        // foundry.toml
        let foundry_toml = r#"[profile.default]
src = 'src'
test = 'test'
libs = ['lib']
evm_version = 'cancun'
offline = true
"#;
        std::fs::write(temp_dir.join("foundry.toml"), foundry_toml)
            .unwrap_or_else(|e| panic!("write foundry.toml failed: {e}"));

        // remappings.txt
        std::fs::write(
            temp_dir.join("remappings.txt"),
            "forge-std/=lib/forge-std/src/\n",
        )
        .unwrap_or_else(|e| panic!("write remappings.txt failed: {e}"));

        // lib/forge-std/src/Test.sol
        let test_sol = r#"// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface Vm {
    function warp(uint256) external;
    function roll(uint256) external;
    function prank(address) external;
    function deal(address, uint256) external;
}

contract Test {
    Vm public constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    function assertGt(uint256 a, uint256 b) internal pure {
        require(a > b, "assertGt failed");
    }
    function assertGt(uint256 a, uint256 b, string memory err) internal pure {
        require(a > b, err);
    }
    function assertLt(uint256 a, uint256 b) internal pure {
        require(a < b, "assertLt failed");
    }
    function assertLt(uint256 a, uint256 b, string memory err) internal pure {
        require(a < b, err);
    }
    function assertEq(uint256 a, uint256 b) internal pure {
        require(a == b, "assertEq failed");
    }
    function assertEq(uint256 a, uint256 b, string memory err) internal pure {
        require(a == b, err);
    }
    function assertNotEq(uint256 a, uint256 b) internal pure {
        require(a != b, "assertNotEq failed");
    }
    function assertNotEq(uint256 a, uint256 b, string memory err) internal pure {
        require(a != b, err);
    }
}
"#;
        std::fs::write(lib_dir.join("Test.sol"), test_sol)
            .unwrap_or_else(|e| panic!("write Test.sol failed: {e}"));

        // src/Vault.sol
        let vault_sol = r#"// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract Vault {
    mapping(address => uint256) public balances;
    uint256 public totalAssets;
    uint256 public totalShares;

    function deposit(uint256 assets) public payable returns (uint256 shares) {
        if (totalAssets == 0) {
            shares = assets;
        } else {
            shares = (assets * totalShares) / totalAssets;
        }
        balances[msg.sender] += shares;
        totalShares += shares;
        totalAssets += assets;
    }

    function withdraw(uint256 shares) public returns (uint256 assets) {
        require(balances[msg.sender] >= shares, "Insufficient");
        assets = (shares * totalAssets) / totalShares;
        balances[msg.sender] -= shares;
        totalShares -= shares;
        totalAssets -= assets;
        payable(msg.sender).transfer(assets);
    }

    receive() external payable {}
}
"#;
        std::fs::write(src_dir.join("Vault.sol"), vault_sol)
            .unwrap_or_else(|e| panic!("write Vault.sol failed: {e}"));

        // test/ExploitHarness.t.sol
        let harness_sol = r#"// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {Vault} from "../src/Vault.sol";

contract ExploitHarness is Test {
    Vault internal vault;

    function setUp() public virtual {
        vault = new Vault();
    }
}
"#;
        std::fs::write(test_dir.join("ExploitHarness.t.sol"), harness_sol)
            .unwrap_or_else(|e| panic!("write ExploitHarness.t.sol failed: {e}"));

        // test/BenignUserTest.t.sol
        let benign_sol = r#"// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {Vault} from "../src/Vault.sol";

contract BenignUserTest is Test {
    Vault internal vault;

    function setUp() public {
        vault = new Vault();
    }

    function test_BenignDeposit() public {
        vault.deposit{value: 1 ether}(1 ether);
        assertGt(vault.balances(address(this)), 0, "Benign deposit succeeded");
    }
}
"#;
        std::fs::write(test_dir.join("BenignUserTest.t.sol"), benign_sol)
            .unwrap_or_else(|e| panic!("write BenignUserTest.t.sol failed: {e}"));

        temp_dir
    }

    #[tokio::test]
    async fn test_1_valid_candidate_verification() {
        let temp_dir = setup_test_foundry_project();
        let verifier = ConcreteForgeVerifier::new(&temp_dir);

        // deposit(uint256) selector: 0xb6b55f25, arg: 0 (zero assets exploit)
        let trajectory = TrajectoryRecord {
            trajectory_id: "valid-exploit-01".to_string(),
            steps: vec![TrajectoryStepRecord {
                step_idx: 0,
                caller_role: "Attacker0".to_string(),
                caller_address: [
                    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0xa0,
                ],
                target_contract: "Vault".to_string(),
                function_signature: "deposit(uint256)".to_string(),
                concrete_calldata_hex:
                    "0xb6b55f250000000000000000000000000000000000000000000000000000000000000000"
                        .to_string(),
                decoded_args: vec!["0".to_string()],
                vm_warp_sec: 10,
                vm_roll_blocks: 1,
            }],
            terminal_reward: 100.0,
            violated_invariant_id: Some("INV_PRECISION_NEUTRALITY_01".to_string()),
            is_exploit: true,
            log_pf: -1.0,
            log_pb: -2.0,
        };

        let finding_res = verifier
            .verify_and_synthesize(&trajectory, "INV_PRECISION_NEUTRALITY_01")
            .await;

        let finding = finding_res.unwrap_or_else(|e| panic!("Verification failed: {e}"));

        assert!(!finding.foundry_poc_solidity_code.is_empty());
        assert!(!finding.minimal_negated_precondition.is_empty());
        assert!(!finding.remediation_patch_diff.is_empty());
        assert!(finding.forge_test_stdout.contains("[PASS]"));

        let _ = std::fs::remove_dir_all(&temp_dir);
    }

    #[tokio::test]
    async fn test_2_false_positive_rejection() {
        let temp_dir = setup_test_foundry_project();
        let verifier = ConcreteForgeVerifier::new(&temp_dir);

        // Fabricated / hallucinated trajectory calling withdraw with no shares deposited
        // withdraw(uint256) selector: 0x2e1a7d4d
        let hallucinated_trajectory = TrajectoryRecord {
            trajectory_id: "hallucinated-01".to_string(),
            steps: vec![TrajectoryStepRecord {
                step_idx: 0,
                caller_role: "Attacker0".to_string(),
                caller_address: [
                    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0xa0,
                ],
                target_contract: "Vault".to_string(),
                function_signature: "withdraw(uint256)".to_string(),
                concrete_calldata_hex:
                    "0x2e1a7d4d0000000000000000000000000000000000000000000000000de0b6b3a7640000"
                        .to_string(),
                decoded_args: vec!["1000000000000000000".to_string()],
                vm_warp_sec: 0,
                vm_roll_blocks: 0,
            }],
            terminal_reward: 0.0,
            violated_invariant_id: Some("INV_SOLVENCY_01".to_string()),
            is_exploit: false,
            log_pf: -10.0,
            log_pb: -10.0,
        };

        let res = verifier
            .verify_and_synthesize(&hallucinated_trajectory, "INV_SOLVENCY_01")
            .await;

        match res {
            Err(GfnError::FalsePositiveRejected { stdout }) => {
                assert!(
                    stdout.contains("[FAIL")
                        || stdout.contains("revert")
                        || stdout.contains("FAILED")
                );
            }
            Ok(_) => panic!("Expected FalsePositiveRejected, but candidate unexpectedly passed!"),
            Err(other) => panic!("Expected FalsePositiveRejected, got: {other}"),
        }

        let _ = std::fs::remove_dir_all(&temp_dir);
    }

    #[tokio::test]
    async fn test_3_patch_non_regression_verification() {
        let temp_dir = setup_test_foundry_project();

        // 1. Synthesize patch for Vault
        let trajectory = TrajectoryRecord {
            trajectory_id: "traj-03".to_string(),
            steps: vec![TrajectoryStepRecord {
                step_idx: 0,
                caller_role: "Attacker0".to_string(),
                caller_address: [
                    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0xa0,
                ],
                target_contract: "Vault".to_string(),
                function_signature: "deposit(uint256)".to_string(),
                concrete_calldata_hex: "0x".to_string(),
                decoded_args: vec![],
                vm_warp_sec: 0,
                vm_roll_blocks: 0,
            }],
            terminal_reward: 100.0,
            violated_invariant_id: Some("INV_PRECISION_NEUTRALITY".to_string()),
            is_exploit: true,
            log_pf: 0.0,
            log_pb: 0.0,
        };

        let patch_res = AstPatchSynthesizer::synthesize_patch(
            &temp_dir,
            &trajectory,
            "INV_PRECISION_NEUTRALITY",
        )
        .unwrap_or_else(|e| panic!("Patch synthesis failed: {e}"));

        // 2. Apply patch to Vault.sol
        std::fs::write(&patch_res.target_file, &patch_res.patched_source)
            .unwrap_or_else(|e| panic!("Failed to write patched source: {e}"));

        // 3. Verify benign test suite passes 100%
        let benign_output = tokio::process::Command::new("forge")
            .arg("test")
            .arg("--match-contract")
            .arg("BenignUserTest")
            .arg("--offline")
            .current_dir(&temp_dir)
            .env("FOUNDRY_OFFLINE", "true")
            .output()
            .await
            .unwrap_or_else(|e| panic!("forge test failed: {e}"));

        assert!(
            benign_output.status.success(),
            "Benign tests must pass 100% after patch application: {}",
            String::from_utf8_lossy(&benign_output.stdout)
        );

        let _ = std::fs::remove_dir_all(&temp_dir);
    }
}
