"""Block 15D-A — Hydraulic Closure Diagnostics tests.

Coverage for:
  - HydraulicClosureCategory enum
  - HydraulicClosureDiagnostic
  - HydraulicClosureDiagnosticResult
  - evaluate_hydraulic_closure_sufficiency
  - make_two_branch_parallel_diagnostic

No production component physics.  No SystemState.  No FluidState.
No CoolProp, no PropertyBackend, no correlations, no HX models.
Diagnostics are kind-based only; no residual evaluation is required.
"""

from __future__ import annotations

import pytest

from mpl_sim.network.hydraulic_closure_diagnostics import (
    HydraulicClosureCategory,
    HydraulicClosureDiagnostic,
    evaluate_hydraulic_closure_sufficiency,
    make_two_branch_parallel_diagnostic,
)
from mpl_sim.network.hydraulic_closures import (
    ImposedBranchSplitClosure,
    ImposedMassFlowClosure,
    ImposedPressureClosure,
    LinearPressureDropClosure,
    PressureCompatibilityClosure,
    QuadraticPressureDropClosure,
    build_hydraulic_closure_residuals,
)

# ===========================================================================
# HydraulicClosureCategory tests
# ===========================================================================


class TestHydraulicClosureCategory:
    def test_all_categories_accessible(self):
        cats = {
            HydraulicClosureCategory.TOTAL_FLOW,
            HydraulicClosureCategory.BRANCH_SPLIT,
            HydraulicClosureCategory.PRESSURE_REFERENCE,
            HydraulicClosureCategory.BRANCH_PRESSURE_DROP_LAW,
            HydraulicClosureCategory.PRESSURE_COMPATIBILITY,
        }
        assert len(cats) == 5

    def test_category_string_values(self):
        assert HydraulicClosureCategory.TOTAL_FLOW == "total_flow"
        assert HydraulicClosureCategory.BRANCH_SPLIT == "branch_split"
        assert HydraulicClosureCategory.PRESSURE_REFERENCE == "pressure_reference"
        assert HydraulicClosureCategory.BRANCH_PRESSURE_DROP_LAW == "branch_pressure_drop_law"
        assert HydraulicClosureCategory.PRESSURE_COMPATIBILITY == "pressure_compatibility"


# ===========================================================================
# HydraulicClosureDiagnostic tests
# ===========================================================================


class TestHydraulicClosureDiagnostic:
    def test_builds(self):
        d = HydraulicClosureDiagnostic(
            required_categories=frozenset(
                {HydraulicClosureCategory.TOTAL_FLOW, HydraulicClosureCategory.BRANCH_SPLIT}
            ),
            description="Test topology",
        )
        assert HydraulicClosureCategory.TOTAL_FLOW in d.required_categories
        assert HydraulicClosureCategory.BRANCH_SPLIT in d.required_categories

    def test_is_frozen(self):
        d = HydraulicClosureDiagnostic(frozenset({HydraulicClosureCategory.TOTAL_FLOW}), "Test")
        with pytest.raises((AttributeError, TypeError)):
            d.description = "mutated"  # type: ignore[misc]

    def test_rejects_non_frozenset_categories(self):
        with pytest.raises(TypeError, match="frozenset"):
            HydraulicClosureDiagnostic(
                required_categories={HydraulicClosureCategory.TOTAL_FLOW},  # type: ignore[arg-type]
                description="Test",
            )

    def test_rejects_blank_description(self):
        with pytest.raises(ValueError):
            HydraulicClosureDiagnostic(
                required_categories=frozenset({HydraulicClosureCategory.TOTAL_FLOW}),
                description="   ",
            )

    def test_rejects_wrong_category_type_in_set(self):
        with pytest.raises(TypeError):
            HydraulicClosureDiagnostic(
                required_categories=frozenset({"total_flow"}),  # type: ignore[arg-type]
                description="Test",
            )

    def test_empty_required_categories_allowed(self):
        d = HydraulicClosureDiagnostic(frozenset(), "empty topology")
        assert len(d.required_categories) == 0


# ===========================================================================
# make_two_branch_parallel_diagnostic tests
# ===========================================================================


class TestMakeTwoBranchParallelDiagnostic:
    def test_returns_diagnostic(self):
        d = make_two_branch_parallel_diagnostic()
        assert isinstance(d, HydraulicClosureDiagnostic)

    def test_contains_all_required_categories(self):
        d = make_two_branch_parallel_diagnostic()
        assert HydraulicClosureCategory.TOTAL_FLOW in d.required_categories
        assert HydraulicClosureCategory.BRANCH_SPLIT in d.required_categories
        assert HydraulicClosureCategory.PRESSURE_REFERENCE in d.required_categories
        assert HydraulicClosureCategory.BRANCH_PRESSURE_DROP_LAW in d.required_categories
        assert HydraulicClosureCategory.PRESSURE_COMPATIBILITY in d.required_categories

    def test_has_five_required_categories(self):
        d = make_two_branch_parallel_diagnostic()
        assert len(d.required_categories) == 5

    def test_description_mentions_topology(self):
        d = make_two_branch_parallel_diagnostic()
        assert "parallel" in d.description.lower() or "branch" in d.description.lower()

    def test_is_frozen(self):
        d = make_two_branch_parallel_diagnostic()
        with pytest.raises((AttributeError, TypeError)):
            d.description = "mutated"  # type: ignore[misc]

    def test_deterministic(self):
        d1 = make_two_branch_parallel_diagnostic()
        d2 = make_two_branch_parallel_diagnostic()
        assert d1.required_categories == d2.required_categories


# ===========================================================================
# evaluate_hydraulic_closure_sufficiency — missing categories
# ===========================================================================


class TestDiagnosticMissingCategories:
    """Diagnostics correctly report missing closure categories."""

    def _diag(self):
        return make_two_branch_parallel_diagnostic()

    def _empty_set(self):
        return build_hydraulic_closure_residuals(
            [ImposedMassFlowClosure("mdot", 1.0, "placeholder")]
        )

    def test_reports_missing_total_flow_when_no_imposed_mass_flow(self):
        d = make_two_branch_parallel_diagnostic()
        # Only provide branch split, no total flow
        closures = build_hydraulic_closure_residuals(
            [ImposedBranchSplitClosure("mdot", "mdot_a", 0.4, "r_split")]
        )
        result = evaluate_hydraulic_closure_sufficiency(d, closures)
        assert HydraulicClosureCategory.TOTAL_FLOW in result.missing_categories

    def test_reports_missing_branch_split_when_no_split_closure(self):
        d = make_two_branch_parallel_diagnostic()
        closures = build_hydraulic_closure_residuals(
            [ImposedMassFlowClosure("mdot", 1.0, "r_total")]
        )
        result = evaluate_hydraulic_closure_sufficiency(d, closures)
        assert HydraulicClosureCategory.BRANCH_SPLIT in result.missing_categories

    def test_reports_missing_pressure_reference_when_no_pressure_closure(self):
        d = make_two_branch_parallel_diagnostic()
        closures = build_hydraulic_closure_residuals(
            [ImposedMassFlowClosure("mdot", 1.0, "r_total")]
        )
        result = evaluate_hydraulic_closure_sufficiency(d, closures)
        assert HydraulicClosureCategory.PRESSURE_REFERENCE in result.missing_categories

    def test_reports_missing_branch_pressure_drop_law(self):
        d = make_two_branch_parallel_diagnostic()
        closures = build_hydraulic_closure_residuals(
            [ImposedMassFlowClosure("mdot", 1.0, "r_total")]
        )
        result = evaluate_hydraulic_closure_sufficiency(d, closures)
        assert HydraulicClosureCategory.BRANCH_PRESSURE_DROP_LAW in result.missing_categories

    def test_reports_missing_pressure_compatibility(self):
        d = make_two_branch_parallel_diagnostic()
        closures = build_hydraulic_closure_residuals(
            [ImposedMassFlowClosure("mdot", 1.0, "r_total")]
        )
        result = evaluate_hydraulic_closure_sufficiency(d, closures)
        assert HydraulicClosureCategory.PRESSURE_COMPATIBILITY in result.missing_categories

    def test_not_sufficient_when_any_category_missing(self):
        d = make_two_branch_parallel_diagnostic()
        # Only 4 of 5 categories satisfied
        closures = build_hydraulic_closure_residuals(
            [
                ImposedMassFlowClosure("mdot", 1.0, "r1"),
                ImposedBranchSplitClosure("mdot", "mdot_a", 0.4, "r2"),
                ImposedPressureClosure("P", 1e6, "r3"),
                LinearPressureDropClosure("p_in", "p_out", "mdot_a", 1000.0, "r4"),
                # missing: PressureCompatibilityClosure
            ]
        )
        result = evaluate_hydraulic_closure_sufficiency(d, closures)
        assert not result.is_sufficient

    def test_all_five_missing_when_minimal_placeholder(self):
        d = make_two_branch_parallel_diagnostic()
        # ImposedMassFlowClosure satisfies TOTAL_FLOW but not the other 4
        closures = build_hydraulic_closure_residuals([ImposedMassFlowClosure("mdot", 1.0, "r")])
        result = evaluate_hydraulic_closure_sufficiency(d, closures)
        assert len(result.missing_categories) == 4
        assert HydraulicClosureCategory.TOTAL_FLOW in result.provided_categories
        assert not result.is_sufficient

    def test_missing_messages_non_empty_when_categories_missing(self):
        d = make_two_branch_parallel_diagnostic()
        closures = build_hydraulic_closure_residuals([ImposedMassFlowClosure("mdot", 1.0, "r")])
        result = evaluate_hydraulic_closure_sufficiency(d, closures)
        assert len(result.missing_messages) > 0
        for msg in result.missing_messages:
            assert isinstance(msg, str)
            assert len(msg) > 0


# ===========================================================================
# evaluate_hydraulic_closure_sufficiency — provided categories
# ===========================================================================


class TestDiagnosticProvidedCategories:
    def _diag(self):
        return make_two_branch_parallel_diagnostic()

    def test_reports_total_flow_when_imposed_mass_flow_present(self):
        d = self._diag()
        closures = build_hydraulic_closure_residuals([ImposedMassFlowClosure("mdot", 1.0, "r")])
        result = evaluate_hydraulic_closure_sufficiency(d, closures)
        assert HydraulicClosureCategory.TOTAL_FLOW in result.provided_categories

    def test_reports_branch_split_when_split_closure_present(self):
        d = self._diag()
        closures = build_hydraulic_closure_residuals(
            [ImposedBranchSplitClosure("mdot", "mdot_a", 0.4, "r")]
        )
        result = evaluate_hydraulic_closure_sufficiency(d, closures)
        assert HydraulicClosureCategory.BRANCH_SPLIT in result.provided_categories

    def test_reports_pressure_reference_when_imposed_pressure_present(self):
        d = self._diag()
        closures = build_hydraulic_closure_residuals([ImposedPressureClosure("P", 1e6, "r")])
        result = evaluate_hydraulic_closure_sufficiency(d, closures)
        assert HydraulicClosureCategory.PRESSURE_REFERENCE in result.provided_categories

    def test_reports_branch_pressure_drop_law_for_linear_closure(self):
        d = self._diag()
        closures = build_hydraulic_closure_residuals(
            [LinearPressureDropClosure("p_in", "p_out", "mdot", 1000.0, "r")]
        )
        result = evaluate_hydraulic_closure_sufficiency(d, closures)
        assert HydraulicClosureCategory.BRANCH_PRESSURE_DROP_LAW in result.provided_categories

    def test_reports_branch_pressure_drop_law_for_quadratic_closure(self):
        d = self._diag()
        closures = build_hydraulic_closure_residuals(
            [QuadraticPressureDropClosure("p_in", "p_out", "mdot", 500.0, "r")]
        )
        result = evaluate_hydraulic_closure_sufficiency(d, closures)
        assert HydraulicClosureCategory.BRANCH_PRESSURE_DROP_LAW in result.provided_categories

    def test_reports_pressure_compatibility_when_closure_present(self):
        d = self._diag()
        closures = build_hydraulic_closure_residuals(
            [PressureCompatibilityClosure("ma", "mb", 50_000.0, 50_000.0, "r")]
        )
        result = evaluate_hydraulic_closure_sufficiency(d, closures)
        assert HydraulicClosureCategory.PRESSURE_COMPATIBILITY in result.provided_categories


# ===========================================================================
# evaluate_hydraulic_closure_sufficiency — sufficiency verdict
# ===========================================================================


class TestDiagnosticSufficiency:
    def _all_closures(self):
        return build_hydraulic_closure_residuals(
            [
                ImposedMassFlowClosure("mdot_pump", 1.0, "r1"),
                ImposedBranchSplitClosure("mdot_pump", "mdot_branch_a", 0.4, "r2"),
                ImposedPressureClosure("P_acc_out", 1_000_000.0, "r3"),
                LinearPressureDropClosure(
                    "P_pump_out", "P_merge_out", "mdot_branch_a", 50_000.0, "r4"
                ),
                PressureCompatibilityClosure(
                    "mdot_branch_a", "mdot_branch_b", 50_000.0, 50_000.0, "r5"
                ),
            ]
        )

    def test_sufficient_when_all_categories_present(self):
        d = make_two_branch_parallel_diagnostic()
        closures = self._all_closures()
        result = evaluate_hydraulic_closure_sufficiency(d, closures)
        assert result.is_sufficient

    def test_no_missing_categories_when_sufficient(self):
        d = make_two_branch_parallel_diagnostic()
        result = evaluate_hydraulic_closure_sufficiency(d, self._all_closures())
        assert len(result.missing_categories) == 0

    def test_no_missing_messages_when_sufficient(self):
        d = make_two_branch_parallel_diagnostic()
        result = evaluate_hydraulic_closure_sufficiency(d, self._all_closures())
        assert len(result.missing_messages) == 0

    def test_closure_names_present_in_result(self):
        d = make_two_branch_parallel_diagnostic()
        result = evaluate_hydraulic_closure_sufficiency(d, self._all_closures())
        assert "r1" in result.closure_names
        assert "r5" in result.closure_names

    def test_empty_required_categories_always_sufficient(self):
        d = HydraulicClosureDiagnostic(frozenset(), "empty")
        closures = build_hydraulic_closure_residuals([ImposedMassFlowClosure("mdot", 1.0, "r")])
        result = evaluate_hydraulic_closure_sufficiency(d, closures)
        assert result.is_sufficient

    def test_result_is_frozen(self):
        d = make_two_branch_parallel_diagnostic()
        result = evaluate_hydraulic_closure_sufficiency(d, self._all_closures())
        with pytest.raises((AttributeError, TypeError)):
            result.is_sufficient = False  # type: ignore[misc]

    def test_provided_and_missing_are_frozensets(self):
        d = make_two_branch_parallel_diagnostic()
        result = evaluate_hydraulic_closure_sufficiency(d, self._all_closures())
        assert isinstance(result.provided_categories, frozenset)
        assert isinstance(result.missing_categories, frozenset)

    def test_closure_names_is_tuple(self):
        d = make_two_branch_parallel_diagnostic()
        result = evaluate_hydraulic_closure_sufficiency(d, self._all_closures())
        assert isinstance(result.closure_names, tuple)

    def test_missing_messages_is_tuple(self):
        d = make_two_branch_parallel_diagnostic()
        result = evaluate_hydraulic_closure_sufficiency(d, self._all_closures())
        assert isinstance(result.missing_messages, tuple)


# ===========================================================================
# evaluate_hydraulic_closure_sufficiency — before/after transition
# ===========================================================================


class TestDiagnosticTransition:
    """Show diagnostic transitions from 'missing' to 'sufficient' as closures
    are progressively added."""

    def test_transition_from_missing_to_sufficient(self):
        d = make_two_branch_parallel_diagnostic()

        # No closures beyond placeholder — not sufficient
        closures_none = build_hydraulic_closure_residuals(
            [ImposedMassFlowClosure("mdot_pump", 1.0, "r_total")]
        )
        result_before = evaluate_hydraulic_closure_sufficiency(d, closures_none)
        assert not result_before.is_sufficient

        # All categories satisfied — sufficient
        closures_full = build_hydraulic_closure_residuals(
            [
                ImposedMassFlowClosure("mdot_pump", 1.0, "r_total"),
                ImposedBranchSplitClosure("mdot_pump", "mdot_branch_a", 0.4, "r_split"),
                ImposedPressureClosure("P_acc_out", 1_000_000.0, "r_pref"),
                LinearPressureDropClosure(
                    "P_pump_out", "P_merge_out", "mdot_branch_a", 50_000.0, "r_drop"
                ),
                PressureCompatibilityClosure(
                    "mdot_branch_a", "mdot_branch_b", 50_000.0, 50_000.0, "r_compat"
                ),
            ]
        )
        result_after = evaluate_hydraulic_closure_sufficiency(d, closures_full)
        assert result_after.is_sufficient

    def test_partial_closure_shows_partial_coverage(self):
        d = make_two_branch_parallel_diagnostic()
        closures_partial = build_hydraulic_closure_residuals(
            [
                ImposedMassFlowClosure("mdot_pump", 1.0, "r_total"),
                ImposedBranchSplitClosure("mdot_pump", "mdot_branch_a", 0.4, "r_split"),
            ]
        )
        result = evaluate_hydraulic_closure_sufficiency(d, closures_partial)
        assert HydraulicClosureCategory.TOTAL_FLOW in result.provided_categories
        assert HydraulicClosureCategory.BRANCH_SPLIT in result.provided_categories
        assert HydraulicClosureCategory.PRESSURE_REFERENCE in result.missing_categories
        assert not result.is_sufficient


# ===========================================================================
# Input validation tests
# ===========================================================================


class TestEvaluateSufficiencyValidation:
    def test_rejects_non_diagnostic_argument(self):
        closures = build_hydraulic_closure_residuals([ImposedMassFlowClosure("mdot", 1.0, "r")])
        with pytest.raises(TypeError):
            evaluate_hydraulic_closure_sufficiency("not_a_diagnostic", closures)  # type: ignore[arg-type]

    def test_rejects_non_residual_set_argument(self):
        d = make_two_branch_parallel_diagnostic()
        with pytest.raises(TypeError):
            evaluate_hydraulic_closure_sufficiency(d, "not_a_set")  # type: ignore[arg-type]
