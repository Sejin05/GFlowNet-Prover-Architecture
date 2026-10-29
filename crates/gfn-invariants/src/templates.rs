#![deny(clippy::unwrap_used, clippy::expect_used, unsafe_op_in_unsafe_fn)]

//! Parameterized formal invariant templates across the 4 canonical domain categories:
//! 1. Conservation of Value & Solvency (`SOLVENCY`)
//! 2. State Machine Monotonicity & Lifecycle Integrity (`MONOTONICITY`)
//! 3. Privilege & Access Control Isolation (`ACCESS_CONTROL`)
//! 4. Rounding & Precision Neutrality (`PRECISION_NEUTRALITY`)

use alloy_primitives::U256;
use gfn_common::schemas::InvariantCategory;
use serde::{Deserialize, Serialize};

/// Parameterized formal invariant templates across the 4 canonical domain categories.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum InvariantTemplate {
    /// 1. Conservation of Value & Solvency (SOLVENCY):
    ///
    /// `\sum_{u \in Shares} slot(u) * P_{share} <= \sum_{v \in Assets} slot(v)`
    Solvency {
        /// Storage slots representing share tokens or liabilities.
        share_slots: Vec<u64>,
        /// Optional storage slot representing the share exchange rate or scaling factor.
        price_slot: Option<u64>,
        /// Storage slots representing backing reserve assets.
        asset_slots: Vec<u64>,
    },

    /// 2. State Machine Monotonicity & Lifecycle Integrity (MONOTONICITY):
    ///
    /// `slot_{state}(s_{t+1}) >= slot_{state}(s_t) \lor A_{valid}[state_t, state_{t+1}] == 1`
    Monotonicity {
        /// Storage slot tracking the protocol state or epoch counter.
        state_slot: u64,
        /// Explicit valid discrete state transition pairs `(from, to)`. If empty, monotonic non-decreasing is enforced.
        allowed_transitions: Vec<(U256, U256)>,
    },

    /// 3. Privilege & Access Control Isolation (ACCESS_CONTROL):
    ///
    /// `caller \notin AdminSet \implies slot_{critical}(s_{t+1}) == slot_{critical}(s_t)`
    AccessControl {
        /// Storage slot holding privileged addresses (owner, admin, beacon, implementation, oracle).
        critical_slot: u64,
        /// Personas permitted to mutate this slot (e.g. `1` for `ContractDeployerAdmin`).
        admin_personas: Vec<u8>,
    },

    /// 4. Rounding & Precision Neutrality (PRECISION_NEUTRALITY):
    ///
    /// `Balance_{attacker}(s_n) <= Balance_{attacker}(s_0) + \epsilon_{dust}` (where `\epsilon_{dust} = 0 wei`)
    PrecisionNeutrality {
        /// Storage slot tracking the attacker persona's asset or share balance.
        attacker_balance_slot: u64,
        /// Allowed rounding dust tolerance in wei (default 0).
        dust_tolerance: U256,
    },
}

impl InvariantTemplate {
    /// Returns the canonical category for this invariant template.
    #[must_use]
    pub fn category(&self) -> InvariantCategory {
        match self {
            Self::Solvency { .. } => InvariantCategory::Solvency,
            Self::Monotonicity { .. } => InvariantCategory::Monotonicity,
            Self::AccessControl { .. } => InvariantCategory::AccessControl,
            Self::PrecisionNeutrality { .. } => InvariantCategory::PrecisionNeutrality,
        }
    }

    /// Returns all storage slot IDs involved in this invariant template.
    #[must_use]
    pub fn involved_slots(&self) -> Vec<u64> {
        match self {
            Self::Solvency {
                share_slots,
                price_slot,
                asset_slots,
            } => {
                let mut slots = Vec::new();
                slots.extend_from_slice(share_slots);
                if let Some(p) = price_slot {
                    slots.push(*p);
                }
                slots.extend_from_slice(asset_slots);
                slots.sort_unstable();
                slots.dedup();
                slots
            }
            Self::Monotonicity { state_slot, .. } => vec![*state_slot],
            Self::AccessControl { critical_slot, .. } => vec![*critical_slot],
            Self::PrecisionNeutrality {
                attacker_balance_slot,
                ..
            } => vec![*attacker_balance_slot],
        }
    }

    /// Formats the formal mathematical expression for telemetry, SMT export, and reporting.
    #[must_use]
    pub fn formal_expression(&self) -> String {
        match self {
            Self::Solvency {
                share_slots,
                price_slot,
                asset_slots,
            } => {
                let shares_str = if share_slots.is_empty() {
                    "0".to_string()
                } else {
                    share_slots
                        .iter()
                        .map(|s| format!("slot({s})"))
                        .collect::<Vec<_>>()
                        .join(" + ")
                };
                let assets_str = if asset_slots.is_empty() {
                    "0".to_string()
                } else {
                    asset_slots
                        .iter()
                        .map(|s| format!("slot({s})"))
                        .collect::<Vec<_>>()
                        .join(" + ")
                };
                if let Some(p) = price_slot {
                    format!("({shares_str}) * slot({p}) <= ({assets_str})")
                } else {
                    format!("({shares_str}) <= ({assets_str})")
                }
            }
            Self::Monotonicity {
                state_slot,
                allowed_transitions,
            } => {
                if allowed_transitions.is_empty() {
                    format!("slot({state_slot})_next >= slot({state_slot})_prev")
                } else {
                    format!(
                        "slot({state_slot})_next >= slot({state_slot})_prev \
                         || is_valid_transition(slot({state_slot})_prev, slot({state_slot})_next)"
                    )
                }
            }
            Self::AccessControl {
                critical_slot,
                admin_personas,
            } => {
                let admins = admin_personas
                    .iter()
                    .map(|a| a.to_string())
                    .collect::<Vec<_>>()
                    .join(", ");
                format!(
                    "caller not in [{admins}] ==> slot({critical_slot})_next == slot({critical_slot})_prev"
                )
            }
            Self::PrecisionNeutrality {
                attacker_balance_slot,
                dust_tolerance,
            } => {
                format!(
                    "slot({attacker_balance_slot})_n <= slot({attacker_balance_slot})_0 + {dust_tolerance}"
                )
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_solvency_template_metadata() {
        let template = InvariantTemplate::Solvency {
            share_slots: vec![1, 2],
            price_slot: Some(5),
            asset_slots: vec![3, 4],
        };

        assert_eq!(template.category(), InvariantCategory::Solvency);
        assert_eq!(template.involved_slots(), vec![1, 2, 3, 4, 5]);
        assert_eq!(
            template.formal_expression(),
            "(slot(1) + slot(2)) * slot(5) <= (slot(3) + slot(4))"
        );
    }

    #[test]
    fn test_monotonicity_template_metadata() {
        let template = InvariantTemplate::Monotonicity {
            state_slot: 10,
            allowed_transitions: vec![(U256::from(1), U256::from(2))],
        };

        assert_eq!(template.category(), InvariantCategory::Monotonicity);
        assert_eq!(template.involved_slots(), vec![10]);
        assert!(template.formal_expression().contains("slot(10)_next"));
    }

    #[test]
    fn test_access_control_template_metadata() {
        let template = InvariantTemplate::AccessControl {
            critical_slot: 7,
            admin_personas: vec![1],
        };

        assert_eq!(template.category(), InvariantCategory::AccessControl);
        assert_eq!(template.involved_slots(), vec![7]);
        assert_eq!(
            template.formal_expression(),
            "caller not in [1] ==> slot(7)_next == slot(7)_prev"
        );
    }

    #[test]
    fn test_precision_neutrality_template_metadata() {
        let template = InvariantTemplate::PrecisionNeutrality {
            attacker_balance_slot: 0,
            dust_tolerance: U256::ZERO,
        };

        assert_eq!(template.category(), InvariantCategory::PrecisionNeutrality);
        assert_eq!(template.involved_slots(), vec![0]);
        assert_eq!(template.formal_expression(), "slot(0)_n <= slot(0)_0 + 0");
    }
}
