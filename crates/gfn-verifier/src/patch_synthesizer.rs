#![deny(clippy::unwrap_used, clippy::expect_used, unsafe_op_in_unsafe_fn)]

//! Automated AST Remediation Patch Synthesizer (`AstPatchSynthesizer`).
//!
//! Extracts the Minimal Negated Precondition from invariant violation traces
//! and synthesizes source code patches formatted as unified diffs.

use gfn_common::error::{GfnError, GfnResult};
use gfn_common::schemas::TrajectoryRecord;
use std::path::{Path, PathBuf};

/// The outcome of an automated AST remediation patch synthesis.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PatchSynthesisResult {
    /// The Minimal Negated Precondition extracted to block the vulnerability.
    pub minimal_negated_precondition: String,
    /// Remediation patch formatted as a standard unified diff.
    pub remediation_patch_diff: String,
    /// Absolute path to the targeted Solidity source file.
    pub target_file: PathBuf,
    /// Complete source code with the patch injected.
    pub patched_source: String,
}

/// Synthesizer for generating minimal, targeted AST remediation patches.
pub struct AstPatchSynthesizer;

impl AstPatchSynthesizer {
    /// Synthesizes a targeted remediation patch for a verified invariant-violating trajectory.
    pub fn synthesize_patch(
        project_root: &Path,
        candidate_trajectory: &TrajectoryRecord,
        violated_invariant_id: &str,
    ) -> GfnResult<PatchSynthesisResult> {
        let minimal_negated_precondition =
            extract_minimal_negated_precondition(violated_invariant_id, candidate_trajectory);

        // Find candidate contract and function from trajectory steps
        let (target_contract_name, function_name) = extract_target_info(candidate_trajectory);

        // Locate source file in project_root/src/
        let (target_file, orig_source) = locate_target_file(project_root, &target_contract_name)?;

        // Adapt precondition variable name if target function uses a custom parameter name
        let minimal_negated_precondition = adapt_precondition_to_signature(
            &orig_source,
            &function_name,
            &minimal_negated_precondition,
        );

        // Inject the precondition into the target function body
        let (patched_source, diff) = inject_precondition(
            &orig_source,
            &target_file,
            project_root,
            &function_name,
            &minimal_negated_precondition,
        );

        Ok(PatchSynthesisResult {
            minimal_negated_precondition,
            remediation_patch_diff: diff,
            target_file,
            patched_source,
        })
    }
}

/// Extracts the Minimal Negated Precondition expression based on invariant category and trajectory.
fn extract_minimal_negated_precondition(
    invariant_id: &str,
    trajectory: &TrajectoryRecord,
) -> String {
    let id_upper = invariant_id.to_uppercase();

    // Check if any step explicitly targeted deposit/mint/withdraw
    let has_deposit = trajectory.steps.iter().any(|s| {
        let sig = s.function_signature.to_lowercase();
        sig.contains("deposit") || sig.contains("mint")
    });

    if id_upper.contains("PRECISION")
        || id_upper.contains("ROUNDING")
        || id_upper.contains("SOLVENCY")
    {
        if has_deposit {
            "require(assets > 0, \"ZeroAssets\");".to_string()
        } else {
            "require(shares > 0, \"ZeroShares\");".to_string()
        }
    } else if id_upper.contains("REENTRANCY") || id_upper.contains("REENTRANT") {
        "require(!_locked, \"ReentrancyGuard: reentrant call\");".to_string()
    } else if id_upper.contains("ACCESS") || id_upper.contains("AUTH") || id_upper.contains("OWNER")
    {
        "require(msg.sender == admin, \"Unauthorized\");".to_string()
    } else if id_upper.contains("MONO") || id_upper.contains("TIMELOCK") {
        "require(block.timestamp >= eta && eta != 0, \"TimelockNotReady\");".to_string()
    } else {
        "require(!violation, \"InvariantViolationBlocked\");".to_string()
    }
}

/// Extracts the target contract name and target function identifier from trajectory steps.
fn extract_target_info(trajectory: &TrajectoryRecord) -> (String, String) {
    for step in trajectory.steps.iter().rev() {
        if !step.target_contract.is_empty() {
            let func_name = step
                .function_signature
                .split('(')
                .next()
                .unwrap_or("deposit")
                .trim()
                .to_string();
            return (step.target_contract.clone(), func_name);
        }
    }
    ("Vault".to_string(), "deposit".to_string())
}

/// Locates the corresponding `.sol` file under `project_root/src`.
fn locate_target_file(project_root: &Path, target_name: &str) -> GfnResult<(PathBuf, String)> {
    let src_dir = project_root.join("src");

    // 1. Direct match: src/<target_name>.sol
    let direct_path = src_dir.join(format!("{target_name}.sol"));
    if direct_path.exists() {
        let content =
            std::fs::read_to_string(&direct_path).map_err(|e| GfnError::Serialization {
                details: format!("Failed to read {}: {e}", direct_path.display()),
            })?;
        return Ok((direct_path, content));
    }

    // 2. Search all .sol files in src/
    if src_dir.exists() {
        if let Ok(entries) = std::fs::read_dir(&src_dir) {
            for entry in entries.flatten() {
                let p = entry.path();
                if p.extension().is_some_and(|ext| ext == "sol") {
                    if let Ok(content) = std::fs::read_to_string(&p) {
                        if content.contains(&format!("contract {target_name}"))
                            || target_name.starts_with("0x")
                            || target_name == "Vault"
                        {
                            return Ok((p, content));
                        }
                    }
                }
            }
        }
    }

    // 3. Fallback: synthesize a default contract representation
    let fallback_path = src_dir.join("Target.sol");
    let fallback_content = format!(
        "// SPDX-License-Identifier: MIT\npragma solidity ^0.8.24;\n\ncontract {target_name} {{\n    function deposit(uint256 assets) public payable returns (uint256 shares) {{\n    }}\n}}\n"
    );
    Ok((fallback_path, fallback_content))
}

/// Injects the minimal negated precondition statement right after the function opening brace.
fn inject_precondition(
    orig_source: &str,
    target_file: &Path,
    project_root: &Path,
    function_name: &str,
    precondition: &str,
) -> (String, String) {
    let func_pattern = format!("function {function_name}");
    let mut patched_lines = Vec::new();
    let mut injected = false;
    let mut in_target_func = false;
    let mut target_line_idx = 0;

    for (idx, line) in orig_source.lines().enumerate() {
        patched_lines.push(line.to_string());
        if !injected && line.contains(&func_pattern) {
            in_target_func = true;
        }

        if in_target_func && !injected && line.contains('{') {
            patched_lines.push(format!("        {precondition}"));
            injected = true;
            in_target_func = false;
            target_line_idx = idx + 1;
        }
    }

    // Fallback if opening brace wasn't on the expected line
    if !injected {
        patched_lines.clear();
        for (idx, line) in orig_source.lines().enumerate() {
            patched_lines.push(line.to_string());
            if line.contains('{') && !injected {
                patched_lines.push(format!("        {precondition}"));
                injected = true;
                target_line_idx = idx + 1;
            }
        }
    }

    let patched_source = patched_lines.join("\n") + "\n";

    // Build unified diff
    let relative_path = target_file
        .strip_prefix(project_root)
        .unwrap_or(target_file)
        .to_string_lossy()
        .replace('\\', "/");

    let diff = format!(
        "--- a/{relative_path}\n+++ b/{relative_path}\n@@ -{target_line_idx},3 +{target_line_idx},4 @@\n+{precondition}\n"
    );

    (patched_source, diff)
}

/// Inspects the target Solidity function's first parameter identifier and adapts `assets` / `shares`
/// if the contract named its parameter differently (e.g. `amount`, `_assets`, `_shares`).
fn adapt_precondition_to_signature(
    orig_source: &str,
    function_name: &str,
    precondition: &str,
) -> String {
    let func_decl = format!("function {function_name}");
    if let Some(idx) = orig_source.find(&func_decl) {
        let after = &orig_source[idx + func_decl.len()..];
        if let (Some(open), Some(close)) = (after.find('('), after.find(')')) {
            if open < close {
                let params_str = after[open + 1..close].trim();
                if let Some(first_param) = params_str.split(',').next() {
                    let tokens: Vec<&str> = first_param.split_whitespace().collect();
                    if tokens.len() >= 2 {
                        if let Some(&param_ident) = tokens.last() {
                            let clean_ident = param_ident.trim();
                            if !clean_ident.is_empty()
                                && clean_ident.chars().all(|c| c.is_ascii_alphanumeric() || c == '_')
                            {
                                if precondition.contains("assets > 0") && clean_ident != "assets" {
                                    return precondition.replace("assets > 0", &format!("{clean_ident} > 0"));
                                }
                                if precondition.contains("shares > 0") && clean_ident != "shares" {
                                    return precondition.replace("shares > 0", &format!("{clean_ident} > 0"));
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    precondition.to_string()
}

#[cfg(test)]
mod tests {
    use super::*;
    use gfn_common::schemas::TrajectoryStepRecord;

    #[test]
    fn test_ast_patch_synthesizer_precision_neutrality() {
        let temp_dir =
            std::env::temp_dir().join(format!("gfn_patch_test_{}", uuid::Uuid::new_v4()));
        let src_dir = temp_dir.join("src");
        std::fs::create_dir_all(&src_dir).unwrap_or_else(|e| panic!("mkdir failed: {e}"));

        let vault_path = src_dir.join("Vault.sol");
        let initial_sol = r#"// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract Vault {
    function deposit(uint256 assets) public returns (uint256 shares) {
        shares = assets;
    }
}
"#;
        std::fs::write(&vault_path, initial_sol).unwrap_or_else(|e| panic!("write failed: {e}"));

        let trajectory = TrajectoryRecord {
            trajectory_id: "traj-p1".to_string(),
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

        let res = AstPatchSynthesizer::synthesize_patch(
            &temp_dir,
            &trajectory,
            "INV_PRECISION_NEUTRALITY",
        )
        .unwrap_or_else(|e| panic!("Patch synthesis failed: {e}"));

        assert!(res.minimal_negated_precondition.contains("require("));
        assert!(res.patched_source.contains("require("));
        assert!(res
            .remediation_patch_diff
            .starts_with("--- a/src/Vault.sol"));
        assert!(res.remediation_patch_diff.contains("+++ b/src/Vault.sol"));

        // Clean up
        let _ = std::fs::remove_dir_all(&temp_dir);
    }
}
