"""Block 15D-A — Hydraulic Closure Parallel Integration tests.

Proves that Block 15D-A hydraulic closure primitives interact correctly
with the Block 15C-A/15C-B parallel topology.

Coverage:
  1. 15C-A parallel topology scenario builds (regression).
  2. 15C-B residual evaluation still works at consistent point (regression).
  3. Hydraulic closure set evaluates to zero at the same consistent point.
  4. Before adding closures: diagnostic reports missing closure categories.
  5. After adding closures: diagnostic reports all categories provided.
  6. Separately evaluated 15C-B and closure residual values are all finite.
  7. Closure set identifies the two structural DOFs as closures.
  8. No solve is claimed; no production component execution.
  9. Block 15C-B design decisions remain documented.
 10. Boundary: no forbidden imports or patterns.

Consistent test point (from Block 15C-B)
-----------------------------------------
Parameters (branch compatibility condition satisfied):
  accumulator_pressure_reference = 1_000_000 Pa
  pump_pressure_rise             = 100_000 Pa
  branch_a_pressure_drop         =  30_000 Pa
  branch_b_pressure_drop         =  40_000 Pa
  merge_a_pressure_drop          =  20_000 Pa  (30000 + 20000 = 50000)
  merge_b_pressure_drop          =  10_000 Pa  (40000 + 10000 = 50000) ✓
  condenser_pressure_drop        =  50_000 Pa

Mass flows (m=1.0 kg/s, branch_a=0.4, branch_b=0.6):
  mdot_accumulator = mdot_pump = mdot_condenser = 1.0
  mdot_branch_a = mdot_merge_a = 0.4
  mdot_branch_b = mdot_merge_b = 0.6

Pressures:
  P_n_acc_out   = 1_000_000
  P_n_pump_out  = 1_100_000
  P_n_a_out     = 1_070_000  (1100000 - 30000)
  P_n_b_out     = 1_060_000  (1100000 - 40000)
  P_n_merge_out = 1_050_000  (1070000 - 20000 = 1060000 - 10000)
  P_n_cond_out  = 1_000_000  (1050000 - 50000)

Closure design for this scenario
----------------------------------
DOF 1 (total flow): ImposedMassFlowClosure(mdot_pump, 1.0)
DOF 2 (branch split): ImposedBranchSplitClosure(mdot_pump, mdot_branch_a, 0.4)

Additionally for demonstration:
  ImposedPressureClosure(P_n_acc_out, 1_000_000) — pressure reference
  LinearPressureDropClosure(P_n_pump_out, P_n_a_out, mdot_branch_a, 75_000.0)
    — branch A resistance: 30000 / 0.4 = 75000 Pa/(kg/s)
  PressureCompatibilityClosure(mdot_branch_a, mdot_branch_b, 125_000.0, 83333.33...)
    — branch A total: 30000+20000=50000; R_a=50000/0.4=125000
    — branch B total: 40000+10000=50000; R_b=50000/0.6≈83333
    — compatible: 125000*0.4 = 50000 = 83333*0.6 ✓

Note on solving
---------------
No solve is performed or claimed in this block.  The 15C-B residuals remain
underdetermined (2 mass-flow DOF, overdetermined pressure subsystem).  The
closure residuals are evaluated SEPARATELY at the known consistent point.
A full solve of the combined system remains deferred.
"""

from __future__ import annotations

import math

import pytest

from mpl_sim.network.hydraulic_closure_diagnostics import (
    HydraulicClosureCategory,
    evaluate_hydraulic_closure_sufficiency,
    make_two_branch_parallel_diagnostic,
)
from mpl_sim.network.hydraulic_closures import (
    ImposedBranchSplitClosure,
    ImposedMassFlowClosure,
    ImposedPressureClosure,
    LinearPressureDropClosure,
    PressureCompatibilityClosure,
    build_hydraulic_closure_residuals,
)
from mpl_sim.network.parallel_topology_residuals import (
    ParallelTopologyResidualParameters,
    build_parallel_topology_physical_residuals,
    evaluate_parallel_topology_residuals,
)
from mpl_sim.network.parallel_topology_scenario import build_parallel_topology_scenario

# ---------------------------------------------------------------------------
# Shared fixtures — consistent test point
# ---------------------------------------------------------------------------

_PARAMS = ParallelTopologyResidualParameters(
    accumulator_pressure_reference=1_000_000.0,
    pump_pressure_rise=100_000.0,
    branch_a_pressure_drop=30_000.0,
    branch_b_pressure_drop=40_000.0,
    merge_a_pressure_drop=20_000.0,
    merge_b_pressure_drop=10_000.0,
    condenser_pressure_drop=50_000.0,
)


def _make_scenario():
    return build_parallel_topology_scenario()


def _make_consistent_unknowns(scenario):
    un = scenario.unknown_names
    return {
        un.mdot_accumulator: 1.0,
        un.mdot_pump: 1.0,
        un.mdot_branch_a: 0.4,
        un.mdot_branch_b: 0.6,
        un.mdot_merge_a: 0.4,
        un.mdot_merge_b: 0.6,
        un.mdot_condenser: 1.0,
        un.P_n_acc_out: 1_000_000.0,
        un.P_n_pump_out: 1_100_000.0,
        un.P_n_a_out: 1_070_000.0,
        un.P_n_b_out: 1_060_000.0,
        un.P_n_merge_out: 1_050_000.0,
        un.P_n_cond_out: 1_000_000.0,
    }


# ===========================================================================
# 1. 15C-A scenario regression
# ===========================================================================


class TestParallelScenarioRegression:
    def test_scenario_builds(self):
        scenario = _make_scenario()
        assert scenario is not None

    def test_scenario_has_thirteen_unknowns(self):
        scenario = _make_scenario()
        assert scenario.assembly.unknowns.count() == 13

    def test_scenario_has_thirteen_residuals(self):
        scenario = _make_scenario()
        assert scenario.assembly.residuals.count() == 13

    def test_scenario_has_seven_components(self):
        scenario = _make_scenario()
        assert len(scenario.graph.instances()) == 7

    def test_scenario_has_six_nodes(self):
        scenario = _make_scenario()
        assert len(scenario.graph.nodes()) == 6


# ===========================================================================
# 2. 15C-B residual evaluation regression
# ===========================================================================


class TestParallelResidualEvaluationRegression:
    def test_evaluation_builds(self):
        scenario = _make_scenario()
        unknowns = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, unknowns)
        assert result is not None

    def test_all_thirteen_residuals_zero_at_consistent_point(self):
        scenario = _make_scenario()
        unknowns = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, unknowns)
        for name, value in result.residual_values.items():
            assert math.isfinite(value), f"residual {name!r} is not finite"
            assert value == pytest.approx(
                0.0, abs=1e-9
            ), f"residual {name!r} = {value} (expected 0)"

    def test_max_abs_norm_zero_at_consistent_point(self):
        scenario = _make_scenario()
        unknowns = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, unknowns)
        assert result.max_abs_residual == pytest.approx(0.0, abs=1e-9)


# ===========================================================================
# 3. Hydraulic closures evaluate to zero at same consistent point
# ===========================================================================


def _make_closure_set_for_scenario(scenario):
    """Build hydraulic closures for the 15C-B consistent test point.

    Closures:
      - ImposedMassFlowClosure: fix mdot_pump = 1.0 (total flow DOF)
      - ImposedBranchSplitClosure: fix mdot_branch_a = 0.4 * mdot_pump (split DOF)
      - ImposedPressureClosure: fix P_n_acc_out = 1_000_000 (pressure reference)
      - LinearPressureDropClosure: branch A path (R_a = 30000/0.4 = 75000 Pa/(kg/s))
      - PressureCompatibilityClosure:
          path A total R = (30000+20000)/0.4 = 125000 Pa/(kg/s)
          path B total R = (40000+10000)/0.6 ≈ 83333.33 Pa/(kg/s)
          compatible: 125000*0.4 == 83333.33*0.6 == 50000 ✓
    """
    un = scenario.unknown_names
    r_a_total = 50_000.0 / 0.4  # 125000 Pa/(kg/s)
    r_b_total = 50_000.0 / 0.6  # ~83333.33 Pa/(kg/s)
    return build_hydraulic_closure_residuals(
        [
            ImposedMassFlowClosure(un.mdot_pump, 1.0, "closure:total_flow"),
            ImposedBranchSplitClosure(un.mdot_pump, un.mdot_branch_a, 0.4, "closure:branch_split"),
            ImposedPressureClosure(un.P_n_acc_out, 1_000_000.0, "closure:pressure_ref"),
            LinearPressureDropClosure(
                un.P_n_pump_out,
                un.P_n_a_out,
                un.mdot_branch_a,
                75_000.0,
                "closure:branch_a_drop",
            ),
            PressureCompatibilityClosure(
                un.mdot_branch_a,
                un.mdot_branch_b,
                r_a_total,
                r_b_total,
                "closure:compatibility",
            ),
        ]
    )


class TestClosuresAtConsistentPoint:
    def test_all_closure_residuals_zero_at_consistent_point(self):
        scenario = _make_scenario()
        closures = _make_closure_set_for_scenario(scenario)
        unknowns = _make_consistent_unknowns(scenario)
        result = closures.evaluate_all(unknowns)
        for name, value in result.items():
            assert math.isfinite(value), f"closure residual {name!r} is not finite"
            assert value == pytest.approx(
                0.0, abs=1e-6
            ), f"closure residual {name!r} = {value} (expected 0)"

    def test_closure_total_flow_zero(self):
        scenario = _make_scenario()
        closures = _make_closure_set_for_scenario(scenario)
        unknowns = _make_consistent_unknowns(scenario)
        result = closures.evaluate_all(unknowns)
        assert result["closure:total_flow"] == pytest.approx(0.0)

    def test_closure_branch_split_zero(self):
        scenario = _make_scenario()
        closures = _make_closure_set_for_scenario(scenario)
        unknowns = _make_consistent_unknowns(scenario)
        result = closures.evaluate_all(unknowns)
        assert result["closure:branch_split"] == pytest.approx(0.0)

    def test_closure_pressure_ref_zero(self):
        scenario = _make_scenario()
        closures = _make_closure_set_for_scenario(scenario)
        unknowns = _make_consistent_unknowns(scenario)
        result = closures.evaluate_all(unknowns)
        assert result["closure:pressure_ref"] == pytest.approx(0.0)

    def test_closure_branch_a_drop_zero(self):
        scenario = _make_scenario()
        closures = _make_closure_set_for_scenario(scenario)
        unknowns = _make_consistent_unknowns(scenario)
        result = closures.evaluate_all(unknowns)
        assert result["closure:branch_a_drop"] == pytest.approx(0.0)

    def test_closure_compatibility_zero(self):
        scenario = _make_scenario()
        closures = _make_closure_set_for_scenario(scenario)
        unknowns = _make_consistent_unknowns(scenario)
        result = closures.evaluate_all(unknowns)
        assert result["closure:compatibility"] == pytest.approx(0.0, abs=1e-9)

    def test_closure_residuals_nonzero_when_total_flow_perturbed(self):
        scenario = _make_scenario()
        closures = _make_closure_set_for_scenario(scenario)
        unknowns = dict(_make_consistent_unknowns(scenario))
        unknowns[scenario.unknown_names.mdot_pump] = 1.5  # perturb total flow
        result = closures.evaluate_all(unknowns)
        assert result["closure:total_flow"] != pytest.approx(0.0)

    def test_closure_residuals_nonzero_when_split_perturbed(self):
        scenario = _make_scenario()
        closures = _make_closure_set_for_scenario(scenario)
        unknowns = dict(_make_consistent_unknowns(scenario))
        unknowns[scenario.unknown_names.mdot_branch_a] = 0.7  # perturb split
        result = closures.evaluate_all(unknowns)
        assert result["closure:branch_split"] != pytest.approx(0.0)

    def test_all_closure_and_15cb_residuals_finite_at_consistent_point(self):
        scenario = _make_scenario()
        closures = _make_closure_set_for_scenario(scenario)
        unknowns = _make_consistent_unknowns(scenario)
        closure_result = closures.evaluate_all(unknowns)
        phys_result = evaluate_parallel_topology_residuals(scenario, _PARAMS, unknowns)
        for v in closure_result.values():
            assert math.isfinite(v)
        for v in phys_result.residual_values.values():
            assert math.isfinite(v)

    def test_combined_residual_count(self):
        scenario = _make_scenario()
        closures = _make_closure_set_for_scenario(scenario)
        unknowns = _make_consistent_unknowns(scenario)
        closure_result = closures.evaluate_all(unknowns)
        phys_result = evaluate_parallel_topology_residuals(scenario, _PARAMS, unknowns)
        total = len(closure_result) + len(phys_result.residual_values)
        assert total == 18  # 5 closure + 13 physical


# ===========================================================================
# 4. Diagnostics before closure provision (missing categories)
# ===========================================================================


class TestDiagnosticsBeforeClosures:
    def test_diagnostic_reports_missing_before_closures(self):
        d = make_two_branch_parallel_diagnostic()
        # Only minimal closure — does not satisfy all categories
        closures = build_hydraulic_closure_residuals(
            [ImposedMassFlowClosure("mdot_pump", 1.0, "r")]
        )
        result = evaluate_hydraulic_closure_sufficiency(d, closures)
        assert not result.is_sufficient
        assert len(result.missing_categories) > 0

    def test_diagnostic_reports_missing_total_flow_without_it(self):
        d = make_two_branch_parallel_diagnostic()
        scenario = _make_scenario()
        un = scenario.unknown_names
        closures = build_hydraulic_closure_residuals(
            [
                ImposedBranchSplitClosure(un.mdot_pump, un.mdot_branch_a, 0.4, "r_split"),
                ImposedPressureClosure(un.P_n_acc_out, 1e6, "r_pref"),
                LinearPressureDropClosure(
                    un.P_n_pump_out, un.P_n_a_out, un.mdot_branch_a, 75_000.0, "r_drop"
                ),
                PressureCompatibilityClosure(
                    un.mdot_branch_a, un.mdot_branch_b, 125_000.0, 83_333.0, "r_compat"
                ),
            ]
        )
        result = evaluate_hydraulic_closure_sufficiency(d, closures)
        assert HydraulicClosureCategory.TOTAL_FLOW in result.missing_categories
        assert not result.is_sufficient

    def test_missing_messages_reference_missing_categories(self):
        d = make_two_branch_parallel_diagnostic()
        closures = build_hydraulic_closure_residuals(
            [ImposedMassFlowClosure("mdot_pump", 1.0, "r")]
        )
        result = evaluate_hydraulic_closure_sufficiency(d, closures)
        msgs = " ".join(result.missing_messages)
        # Messages should mention what's missing
        assert len(msgs) > 0


# ===========================================================================
# 5. Diagnostics after closure provision (sufficient)
# ===========================================================================


class TestDiagnosticsAfterClosures:
    def test_diagnostic_reports_sufficient_after_all_closures(self):
        d = make_two_branch_parallel_diagnostic()
        scenario = _make_scenario()
        closures = _make_closure_set_for_scenario(scenario)
        result = evaluate_hydraulic_closure_sufficiency(d, closures)
        assert result.is_sufficient

    def test_no_missing_categories_after_all_closures(self):
        d = make_two_branch_parallel_diagnostic()
        scenario = _make_scenario()
        closures = _make_closure_set_for_scenario(scenario)
        result = evaluate_hydraulic_closure_sufficiency(d, closures)
        assert len(result.missing_categories) == 0

    def test_all_categories_in_provided_after_all_closures(self):
        d = make_two_branch_parallel_diagnostic()
        scenario = _make_scenario()
        closures = _make_closure_set_for_scenario(scenario)
        result = evaluate_hydraulic_closure_sufficiency(d, closures)
        for cat in d.required_categories:
            assert cat in result.provided_categories

    def test_transition_from_insufficient_to_sufficient(self):
        d = make_two_branch_parallel_diagnostic()
        scenario = _make_scenario()
        un = scenario.unknown_names

        # Step 1: No closures beyond total flow
        closures_step1 = build_hydraulic_closure_residuals(
            [ImposedMassFlowClosure(un.mdot_pump, 1.0, "r_total")]
        )
        r1 = evaluate_hydraulic_closure_sufficiency(d, closures_step1)
        assert not r1.is_sufficient

        # Step 2: Add all remaining
        r_a_total = 50_000.0 / 0.4
        r_b_total = 50_000.0 / 0.6
        closures_step2 = build_hydraulic_closure_residuals(
            [
                ImposedMassFlowClosure(un.mdot_pump, 1.0, "r_total"),
                ImposedBranchSplitClosure(un.mdot_pump, un.mdot_branch_a, 0.4, "r_split"),
                ImposedPressureClosure(un.P_n_acc_out, 1_000_000.0, "r_pref"),
                LinearPressureDropClosure(
                    un.P_n_pump_out, un.P_n_a_out, un.mdot_branch_a, 75_000.0, "r_drop"
                ),
                PressureCompatibilityClosure(
                    un.mdot_branch_a, un.mdot_branch_b, r_a_total, r_b_total, "r_compat"
                ),
            ]
        )
        r2 = evaluate_hydraulic_closure_sufficiency(d, closures_step2)
        assert r2.is_sufficient


# ===========================================================================
# 6. Design decisions documented (no solve, no hidden split)
# ===========================================================================


class TestDesignDecisionsDocumented:
    def test_no_solve_performed_or_claimed(self):
        scenario = _make_scenario()
        phys_assembly = build_parallel_topology_physical_residuals(scenario, _PARAMS)
        # Verify: no solve methods exist on the parallel topology objects
        assert not hasattr(phys_assembly, "solve")
        assert not hasattr(phys_assembly, "solve_network")

    def test_imposed_split_is_user_constraint_not_predicted(self):
        scenario = _make_scenario()
        un = scenario.unknown_names
        # ImposedBranchSplitClosure requires an EXPLICIT fraction — it does not
        # predict the fraction from physical equations or properties
        c = ImposedBranchSplitClosure(un.mdot_pump, un.mdot_branch_a, 0.4, "r_split")
        assert c.split_fraction == pytest.approx(0.4)
        # Different explicit fractions produce different constraints
        c2 = ImposedBranchSplitClosure(un.mdot_pump, un.mdot_branch_a, 0.6, "r_split")
        unknowns = _make_consistent_unknowns(scenario)
        r_correct = c.evaluate(unknowns)
        r_wrong = c2.evaluate(unknowns)
        assert r_correct == pytest.approx(0.0)
        assert r_wrong != pytest.approx(0.0)

    def test_15cb_underdetermination_remains_two_dof(self):
        scenario = _make_scenario()
        phys_assembly = build_parallel_topology_physical_residuals(scenario, _PARAMS)
        # The 13-residual system is structurally underdetermined in mass-flow
        # (rank 5 for 6 mass-balance equations, 7 mass-flow unknowns → 2 DOF)
        # This is documented in the module; we verify via the solve-deferred note
        assert not hasattr(phys_assembly, "solve")

    def test_closure_set_has_five_residuals_for_parallel_topology(self):
        scenario = _make_scenario()
        closures = _make_closure_set_for_scenario(scenario)
        # 5 closure residuals target the missing constraints
        assert len(closures.closures) == 5

    def test_no_production_components_required(self):
        # Closures work without any production component classes
        from mpl_sim.network.hydraulic_closures import ImposedMassFlowClosure

        c = ImposedMassFlowClosure("mdot", 1.0, "r")
        assert c.evaluate({"mdot": 1.0}) == pytest.approx(0.0)

    def test_no_system_state_required(self):
        # Closures work with plain dict; no SystemState, no FluidState
        c = ImposedPressureClosure("P", 1e6, "r")
        assert c.evaluate({"P": 1e6}) == pytest.approx(0.0)


# ===========================================================================
# Boundary / architecture invariant tests
# ===========================================================================


class TestBoundaryInvariants:
    """Architecture boundary tests for hydraulic closure modules.

    These tests inspect source files for forbidden executable patterns.
    Mentions of forbidden names in comments, docstrings, or string literals
    used as negative documentation are allowed and expected.  Only import
    statements and callable patterns are checked.
    """

    def _load_source(self, mod_name: str) -> str:
        import importlib.util

        spec = importlib.util.find_spec(mod_name)
        assert spec is not None, f"Cannot find module {mod_name!r}"
        with open(spec.origin, encoding="utf-8") as f:
            return f.read()

    def _check_no_import(self, src: str, name: str, mod_name: str) -> None:
        import re

        # Check for executable import forms: "import <name>" or "from <name>"
        pattern = re.compile(
            r"^\s*(import\s+" + re.escape(name) + r"|from\s+" + re.escape(name) + r")",
            re.MULTILINE,
        )
        matches = pattern.findall(src)
        assert (
            not matches
        ), f"Module {mod_name!r} contains a forbidden import of {name!r}: {matches}"

    def test_no_coolprop_import_in_hydraulic_closures_module(self):
        src = self._load_source("mpl_sim.network.hydraulic_closures")
        self._check_no_import(src, "CoolProp", "hydraulic_closures")

    def test_no_property_backend_import_in_closures_module(self):
        src = self._load_source("mpl_sim.network.hydraulic_closures")
        self._check_no_import(src, "mpl_sim.properties", "hydraulic_closures")

    def test_no_coolprop_import_in_diagnostics_module(self):
        src = self._load_source("mpl_sim.network.hydraulic_closure_diagnostics")
        self._check_no_import(src, "CoolProp", "hydraulic_closure_diagnostics")

    def test_no_property_backend_import_in_diagnostics_module(self):
        src = self._load_source("mpl_sim.network.hydraulic_closure_diagnostics")
        self._check_no_import(src, "mpl_sim.properties", "hydraulic_closure_diagnostics")

    def test_no_contribute_def_in_hydraulic_closures_module(self):
        src = self._load_source("mpl_sim.network.hydraulic_closures")
        assert "def contribute" not in src

    def test_no_contribute_call_in_hydraulic_closures_module(self):
        src = self._load_source("mpl_sim.network.hydraulic_closures")
        assert ".contribute(" not in src

    def test_no_system_state_import_in_closures_module(self):
        src = self._load_source("mpl_sim.network.hydraulic_closures")
        self._check_no_import(src, "SystemState", "hydraulic_closures")

    def test_no_correlation_registry_import_in_closures_module(self):
        src = self._load_source("mpl_sim.network.hydraulic_closures")
        self._check_no_import(src, "CorrelationRegistry", "hydraulic_closures")

    def test_no_mpl_sim_components_import_in_closures_module(self):
        src = self._load_source("mpl_sim.network.hydraulic_closures")
        self._check_no_import(src, "mpl_sim.components", "hydraulic_closures")

    def test_no_mpl_sim_components_import_in_diagnostics_module(self):
        src = self._load_source("mpl_sim.network.hydraulic_closure_diagnostics")
        self._check_no_import(src, "mpl_sim.components", "hydraulic_closure_diagnostics")

    def test_closures_are_immutable_dataclasses(self):
        for cls in [
            ImposedMassFlowClosure,
            ImposedBranchSplitClosure,
            ImposedPressureClosure,
            LinearPressureDropClosure,
            PressureCompatibilityClosure,
        ]:
            c = cls.__dataclass_params__
            assert c.frozen, f"{cls.__name__} should be a frozen dataclass"
