"""Acceptance / closeout tests for Block 15E-C.

Proves that the complete Block 15E configurable declaration + explicit
residual-selection stack works coherently end-to-end across:
  - 15E-A configurable scenario declarations
  - 15E-B explicit configurable residual-mode selection
  - 15D-C combined closure integration
  - 15B  fixed single-loop evaluation-only layer
  - 15C-B fixed two-branch evaluation-only layer

Acceptance stories
------------------
1  Declaration-only: scenario builds, no residual evaluation, honest reports.
2  Fixed single-loop algebraic: explicit mode → zero residuals at consistent
   point; perturbed → nonzero; no solve.
3  Fixed two-branch parallel algebraic: explicit mode → zero residuals;
   perturbed → nonzero; no solve.
4  Closure-only: explicit closure set evaluated; closures NOT inferred from
   roles; no solve.
5  Role changes do not select physics or change compatibility.
6  Incompatible scenarios are rejected cleanly with deterministic reasons and
   no silent fallback to another mode.
7  Reports from all three stack layers coexist as JSON-serializable plain dicts.

Boundary stories
----------------
B1 no_solve=True in every result regardless of mode or evaluation outcome.
B2 solve_fixed_single_loop_residuals is NOT imported into the selection module.
B3 No CoolProp / PropertyBackend / SystemState / FluidState in the module.
B4 No generic solve(network) or solver attribute in selection results.
B5 No contribute attribute in the selection module.
B6 No role-based physics dispatch (closures not inferred from roles).

Regression
----------
R1 Production contracts still show NO_CONTRIBUTE_METHOD for all 6 classes.
R2 inspect_known_production_component_contracts returns exactly 6 results.

These tests do NOT:
  - Call solve_fixed_single_loop_residuals.
  - Execute production component physics.
  - Call CoolProp, PropertyBackend, or correlations.
  - Assemble SystemState or construct FluidState.
  - Call solve(network) or NetworkGraph.solve().
  - Write files, use pandas, or use numpy.
"""

from __future__ import annotations

import importlib
import json

import pytest

from mpl_sim.network.closure_integration import (
    build_combined_closure_report,
    build_combined_closure_residuals,
    evaluate_combined_closure_residuals,
)
from mpl_sim.network.configurable_residual_selection import (
    ConfigurableResidualMode,
    ConfigurableResidualSelectionRequest,
    build_configurable_residual_selection_report,
    evaluate_selected_configurable_residuals,
    select_configurable_residual_strategy,
)
from mpl_sim.network.configurable_scenarios import (
    ConfigurableScenarioSpec,
    ScenarioBranchSpec,
    ScenarioComponentRole,
    ScenarioComponentSpec,
    ScenarioConnectionSpec,
    ScenarioNodeSpec,
    build_configurable_scenario,
    build_configurable_scenario_report,
)
from mpl_sim.network.fixed_single_loop_residuals import FixedSingleLoopResidualParameters
from mpl_sim.network.fixed_single_loop_runner import FixedSingleLoopEvaluationResult
from mpl_sim.network.hydraulic_closures import (
    ImposedMassFlowClosure,
    build_hydraulic_closure_residuals,
)
from mpl_sim.network.parallel_topology_residuals import (
    ParallelTopologyEvaluationResult,
    ParallelTopologyResidualParameters,
)

# Module under inspection (imported once for reuse in boundary tests)
_CRS_MOD = importlib.import_module("mpl_sim.network.configurable_residual_selection")


# ---------------------------------------------------------------------------
# Shared test parameters
# ---------------------------------------------------------------------------

# Single-loop consistent point (all four pressure-drop residuals == 0):
#   P_n_acc_out = 100000  Pa  (acc_ref)
#   P_n_pump_out = 100000 + 50000 = 150000
#   P_n_evap_out = 150000 - 30000 = 120000
#   P_n_cond_out = 120000 - 20000 = 100000  (== acc_ref ✓)
_SL_PARAMS = FixedSingleLoopResidualParameters(
    pump_pressure_rise=50000.0,
    evaporator_pressure_drop=30000.0,
    condenser_pressure_drop=20000.0,
    accumulator_pressure_reference=100000.0,
)
_SL_UV = {
    "mdot:accumulator": 1.0,
    "mdot:pump": 1.0,
    "mdot:evaporator": 1.0,
    "mdot:condenser": 1.0,
    "P:n_acc_out": 100000.0,
    "P:n_pump_out": 150000.0,
    "P:n_evap_out": 120000.0,
    "P:n_cond_out": 100000.0,
}
_SL_UV_PERTURBED = {**_SL_UV, "P:n_acc_out": 110000.0}  # off-solution

# Two-branch consistent point (branch_a+merge_a == branch_b+merge_b == 50000):
_TB_PARAMS = ParallelTopologyResidualParameters(
    accumulator_pressure_reference=100000.0,
    pump_pressure_rise=50000.0,
    branch_a_pressure_drop=30000.0,
    branch_b_pressure_drop=40000.0,
    merge_a_pressure_drop=20000.0,
    merge_b_pressure_drop=10000.0,
    condenser_pressure_drop=5000.0,
)
_TB_UV = {
    "mdot:accumulator": 1.0,
    "mdot:pump": 1.0,
    "mdot:branch_a": 0.4,
    "mdot:branch_b": 0.6,
    "mdot:merge_a": 0.4,
    "mdot:merge_b": 0.6,
    "mdot:condenser": 1.0,
    "P:n_acc_out": 100000.0,
    "P:n_pump_out": 150000.0,
    "P:n_a_out": 120000.0,
    "P:n_b_out": 110000.0,
    "P:n_merge_out": 100000.0,
    "P:n_cond_out": 95000.0,
}
_TB_UV_PERTURBED = {**_TB_UV, "P:n_pump_out": 140000.0}  # off-solution

# Closure consistent point: imposed_value == unknown_value
_CLOSURE_IMPOSED_MDOT = 1.2
_CLOSURE_UV = {"mdot_loop": _CLOSURE_IMPOSED_MDOT}
_CLOSURE_UV_PERTURBED = {"mdot_loop": 2.5}  # off-solution


# ---------------------------------------------------------------------------
# Scenario / closure helpers
# ---------------------------------------------------------------------------


def _build_single_loop(scenario_id: str = "co_sl"):
    """Conventional single-loop with IDs matching fixed single-loop defaults."""
    spec = ConfigurableScenarioSpec(
        scenario_id=scenario_id,
        components=(
            ScenarioComponentSpec("accumulator", ScenarioComponentRole.ACCUMULATOR),
            ScenarioComponentSpec("pump", ScenarioComponentRole.PUMP),
            ScenarioComponentSpec("evaporator", ScenarioComponentRole.EVAPORATOR),
            ScenarioComponentSpec("condenser", ScenarioComponentRole.CONDENSER),
        ),
        nodes=(
            ScenarioNodeSpec("n_acc_out"),
            ScenarioNodeSpec("n_pump_out"),
            ScenarioNodeSpec("n_evap_out"),
            ScenarioNodeSpec("n_cond_out"),
        ),
        connections=(
            ScenarioConnectionSpec("accumulator", "n_cond_out", "n_acc_out"),
            ScenarioConnectionSpec("pump", "n_acc_out", "n_pump_out"),
            ScenarioConnectionSpec("evaporator", "n_pump_out", "n_evap_out"),
            ScenarioConnectionSpec("condenser", "n_evap_out", "n_cond_out"),
        ),
    )
    return build_configurable_scenario(spec)


def _build_single_loop_generic_roles(scenario_id: str = "co_sl_generic"):
    """Same IDs as conventional single-loop but all roles are GENERIC."""
    spec = ConfigurableScenarioSpec(
        scenario_id=scenario_id,
        components=(
            ScenarioComponentSpec("accumulator", ScenarioComponentRole.GENERIC),
            ScenarioComponentSpec("pump", ScenarioComponentRole.GENERIC),
            ScenarioComponentSpec("evaporator", ScenarioComponentRole.GENERIC),
            ScenarioComponentSpec("condenser", ScenarioComponentRole.GENERIC),
        ),
        nodes=(
            ScenarioNodeSpec("n_acc_out"),
            ScenarioNodeSpec("n_pump_out"),
            ScenarioNodeSpec("n_evap_out"),
            ScenarioNodeSpec("n_cond_out"),
        ),
        connections=(
            ScenarioConnectionSpec("accumulator", "n_cond_out", "n_acc_out"),
            ScenarioConnectionSpec("pump", "n_acc_out", "n_pump_out"),
            ScenarioConnectionSpec("evaporator", "n_pump_out", "n_evap_out"),
            ScenarioConnectionSpec("condenser", "n_evap_out", "n_cond_out"),
        ),
    )
    return build_configurable_scenario(spec)


def _build_two_branch(scenario_id: str = "co_tb"):
    """Conventional two-branch with IDs matching fixed two-branch defaults."""
    spec = ConfigurableScenarioSpec(
        scenario_id=scenario_id,
        components=(
            ScenarioComponentSpec("accumulator", ScenarioComponentRole.ACCUMULATOR),
            ScenarioComponentSpec("pump", ScenarioComponentRole.PUMP),
            ScenarioComponentSpec("branch_a", ScenarioComponentRole.PIPE),
            ScenarioComponentSpec("branch_b", ScenarioComponentRole.PIPE),
            ScenarioComponentSpec("merge_a", ScenarioComponentRole.JUNCTION),
            ScenarioComponentSpec("merge_b", ScenarioComponentRole.JUNCTION),
            ScenarioComponentSpec("condenser", ScenarioComponentRole.CONDENSER),
        ),
        nodes=(
            ScenarioNodeSpec("n_acc_out"),
            ScenarioNodeSpec("n_pump_out"),
            ScenarioNodeSpec("n_a_out"),
            ScenarioNodeSpec("n_b_out"),
            ScenarioNodeSpec("n_merge_out"),
            ScenarioNodeSpec("n_cond_out"),
        ),
        connections=(
            ScenarioConnectionSpec("accumulator", "n_cond_out", "n_acc_out"),
            ScenarioConnectionSpec("pump", "n_acc_out", "n_pump_out"),
            ScenarioConnectionSpec("branch_a", "n_pump_out", "n_a_out"),
            ScenarioConnectionSpec("branch_b", "n_pump_out", "n_b_out"),
            ScenarioConnectionSpec("merge_a", "n_a_out", "n_merge_out"),
            ScenarioConnectionSpec("merge_b", "n_b_out", "n_merge_out"),
            ScenarioConnectionSpec("condenser", "n_merge_out", "n_cond_out"),
        ),
        branches=(
            ScenarioBranchSpec(
                branch_id="branch_a",
                inlet_node_id="n_pump_out",
                outlet_node_id="n_merge_out",
                component_ids=("branch_a", "merge_a"),
            ),
            ScenarioBranchSpec(
                branch_id="branch_b",
                inlet_node_id="n_pump_out",
                outlet_node_id="n_merge_out",
                component_ids=("branch_b", "merge_b"),
            ),
        ),
    )
    return build_configurable_scenario(spec)


def _build_incompatible(scenario_id: str = "co_incompatible"):
    """Custom scenario with non-conventional IDs — incompatible with any fixed mode."""
    spec = ConfigurableScenarioSpec(
        scenario_id=scenario_id,
        components=(
            ScenarioComponentSpec("unit_x", ScenarioComponentRole.GENERIC),
            ScenarioComponentSpec("unit_y", ScenarioComponentRole.GENERIC),
        ),
        nodes=(
            ScenarioNodeSpec("node_alpha"),
            ScenarioNodeSpec("node_beta"),
        ),
        connections=(
            ScenarioConnectionSpec("unit_x", "node_beta", "node_alpha"),
            ScenarioConnectionSpec("unit_y", "node_alpha", "node_beta"),
        ),
    )
    return build_configurable_scenario(spec)


def _build_closure_set():
    """Explicit combined closure: single imposed mass flow at 1.2 kg/s."""
    hyd = build_hydraulic_closure_residuals(
        closures=(
            ImposedMassFlowClosure(
                unknown_name="mdot_loop",
                imposed_value=_CLOSURE_IMPOSED_MDOT,
                residual_name="r_mdot_imposed",
            ),
        )
    )
    return build_combined_closure_residuals(hydraulic=hyd)


# ---------------------------------------------------------------------------
# Story 1 — Declaration-only acceptance
# ---------------------------------------------------------------------------


class TestStory1DeclarationOnly:
    def test_builds_and_selects_without_error(self):
        br = _build_single_loop()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        assert result is not None

    def test_no_evaluation_performed(self):
        br = _build_single_loop()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        assert result.evaluation_performed is False
        assert result.evaluation_result is None

    def test_no_solve_true(self):
        br = _build_single_loop()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        assert result.no_solve is True

    def test_report_is_json_serializable(self):
        br = _build_single_loop()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        json.dumps(report)

    def test_report_no_solve_true(self):
        br = _build_single_loop()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        assert report["no_solve"] is True

    def test_report_roles_selected_physics_false(self):
        br = _build_single_loop()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        assert report["roles_selected_physics"] is False

    def test_report_closures_inferred_from_roles_false(self):
        br = _build_single_loop()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        assert report["closures_inferred_from_roles"] is False

    def test_two_branch_declaration_only_also_accepted(self):
        br = _build_two_branch()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        assert result.evaluation_performed is False
        assert result.no_solve is True

    def test_incompatible_scenario_declaration_only_accepted(self):
        """DECLARATION_ONLY accepts any valid build result, even non-conventional."""
        br = _build_incompatible()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        assert result.compatibility.is_compatible is True
        assert result.no_solve is True


# ---------------------------------------------------------------------------
# Story 2 — Explicit fixed single-loop algebraic evaluation
# ---------------------------------------------------------------------------


class TestStory2FixedSingleLoopAlgebraic:
    def test_consistent_point_zero_residuals(self):
        br = _build_single_loop()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
            single_loop_parameters=_SL_PARAMS,
            single_loop_unknown_values=_SL_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.evaluation_performed is True
        ev = result.evaluation_result
        assert isinstance(ev, FixedSingleLoopEvaluationResult)
        assert ev.max_abs_residual == pytest.approx(0.0, abs=1e-9)
        assert ev.l2_residual == pytest.approx(0.0, abs=1e-9)

    def test_perturbed_point_nonzero_residuals(self):
        br = _build_single_loop()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
            single_loop_parameters=_SL_PARAMS,
            single_loop_unknown_values=_SL_UV_PERTURBED,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        ev = result.evaluation_result
        assert isinstance(ev, FixedSingleLoopEvaluationResult)
        assert ev.max_abs_residual > 0.0

    def test_no_solve_true_after_evaluation(self):
        br = _build_single_loop()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
            single_loop_parameters=_SL_PARAMS,
            single_loop_unknown_values=_SL_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.no_solve is True

    def test_report_no_solve_true(self):
        br = _build_single_loop()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
            single_loop_parameters=_SL_PARAMS,
            single_loop_unknown_values=_SL_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        assert report["no_solve"] is True

    def test_evaluate_selected_returns_result(self):
        br = _build_single_loop()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
            single_loop_parameters=_SL_PARAMS,
            single_loop_unknown_values=_SL_UV,
            evaluate=True,
        )
        result = evaluate_selected_configurable_residuals(req)
        assert result.evaluation_performed is True
        assert isinstance(result.evaluation_result, FixedSingleLoopEvaluationResult)

    def test_result_has_no_converged_field(self):
        """Evaluation-only path: result carries no solver convergence attributes."""
        br = _build_single_loop()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
            single_loop_parameters=_SL_PARAMS,
            single_loop_unknown_values=_SL_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        ev = result.evaluation_result
        assert not hasattr(ev, "converged")
        assert not hasattr(ev, "iteration_count")

    def test_report_json_serializable_with_residuals(self):
        br = _build_single_loop()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
            single_loop_parameters=_SL_PARAMS,
            single_loop_unknown_values=_SL_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        json.dumps(report)
        assert report["evaluation"]["performed"] is True
        assert "residual_values" in report["evaluation"]


# ---------------------------------------------------------------------------
# Story 3 — Explicit fixed two-branch parallel algebraic evaluation
# ---------------------------------------------------------------------------


class TestStory3FixedTwoBranchAlgebraic:
    def test_consistent_point_zero_residuals(self):
        br = _build_two_branch()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC,
            two_branch_parameters=_TB_PARAMS,
            two_branch_unknown_values=_TB_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.evaluation_performed is True
        ev = result.evaluation_result
        assert isinstance(ev, ParallelTopologyEvaluationResult)
        assert ev.max_abs_residual == pytest.approx(0.0, abs=1e-9)
        assert ev.l2_residual == pytest.approx(0.0, abs=1e-9)

    def test_perturbed_point_nonzero_residuals(self):
        br = _build_two_branch()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC,
            two_branch_parameters=_TB_PARAMS,
            two_branch_unknown_values=_TB_UV_PERTURBED,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        ev = result.evaluation_result
        assert isinstance(ev, ParallelTopologyEvaluationResult)
        assert ev.max_abs_residual > 0.0

    def test_no_solve_true_after_evaluation(self):
        br = _build_two_branch()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC,
            two_branch_parameters=_TB_PARAMS,
            two_branch_unknown_values=_TB_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.no_solve is True

    def test_report_no_solve_true(self):
        br = _build_two_branch()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC,
            two_branch_parameters=_TB_PARAMS,
            two_branch_unknown_values=_TB_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        assert report["no_solve"] is True

    def test_evaluate_selected_returns_result(self):
        br = _build_two_branch()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC,
            two_branch_parameters=_TB_PARAMS,
            two_branch_unknown_values=_TB_UV,
            evaluate=True,
        )
        result = evaluate_selected_configurable_residuals(req)
        assert result.evaluation_performed is True
        assert isinstance(result.evaluation_result, ParallelTopologyEvaluationResult)

    def test_report_json_serializable(self):
        br = _build_two_branch()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC,
            two_branch_parameters=_TB_PARAMS,
            two_branch_unknown_values=_TB_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        json.dumps(report)
        assert report["evaluation"]["performed"] is True


# ---------------------------------------------------------------------------
# Story 4 — Explicit closure-only evaluation
# ---------------------------------------------------------------------------


class TestStory4ClosureOnly:
    def test_consistent_point_zero_residuals(self):
        closure_set = _build_closure_set()
        br = _build_single_loop()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.CLOSURE_ONLY,
            closure_residual_set=closure_set,
            closure_unknown_values=_CLOSURE_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.evaluation_performed is True
        assert result.evaluation_result.max_absolute_residual == pytest.approx(0.0, abs=1e-9)

    def test_perturbed_point_nonzero_residuals(self):
        closure_set = _build_closure_set()
        br = _build_single_loop()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.CLOSURE_ONLY,
            closure_residual_set=closure_set,
            closure_unknown_values=_CLOSURE_UV_PERTURBED,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.evaluation_result.max_absolute_residual > 0.0

    def test_no_solve_true(self):
        closure_set = _build_closure_set()
        br = _build_single_loop()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.CLOSURE_ONLY,
            closure_residual_set=closure_set,
            closure_unknown_values=_CLOSURE_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.no_solve is True

    def test_report_closures_inferred_from_roles_false(self):
        closure_set = _build_closure_set()
        br = _build_single_loop()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.CLOSURE_ONLY,
            closure_residual_set=closure_set,
            closure_unknown_values=_CLOSURE_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        assert report["closures_inferred_from_roles"] is False

    def test_report_roles_selected_physics_false(self):
        closure_set = _build_closure_set()
        br = _build_single_loop()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.CLOSURE_ONLY,
            closure_residual_set=closure_set,
            closure_unknown_values=_CLOSURE_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        assert report["roles_selected_physics"] is False

    def test_report_no_solve_true(self):
        closure_set = _build_closure_set()
        br = _build_single_loop()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.CLOSURE_ONLY,
            closure_residual_set=closure_set,
            closure_unknown_values=_CLOSURE_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        assert report["no_solve"] is True

    def test_evaluate_selected_works(self):
        closure_set = _build_closure_set()
        br = _build_single_loop()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.CLOSURE_ONLY,
            closure_residual_set=closure_set,
            closure_unknown_values=_CLOSURE_UV,
            evaluate=True,
        )
        result = evaluate_selected_configurable_residuals(req)
        assert result.evaluation_performed is True

    def test_closure_not_inferred_without_explicit_set(self):
        """No closure is created unless an explicit closure_residual_set is provided."""
        br = _build_single_loop()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.CLOSURE_ONLY,
            # No closure_residual_set
        )
        result = select_configurable_residual_strategy(req)
        assert result.compatibility.is_compatible is False
        assert result.evaluation_performed is False


# ---------------------------------------------------------------------------
# Story 5 — Role changes do not select physics
# ---------------------------------------------------------------------------


class TestStory5RoleChangesDoNotSelectPhysics:
    def test_conventional_roles_compatible_with_single_loop_mode(self):
        br = _build_single_loop()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
        )
        result = select_configurable_residual_strategy(req)
        assert result.compatibility.is_compatible is True

    def test_generic_roles_same_compatibility_as_conventional(self):
        """Same IDs with all GENERIC roles: still compatible based on ID ordering."""
        br_generic = _build_single_loop_generic_roles()
        req = ConfigurableResidualSelectionRequest(
            build_result=br_generic,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
        )
        result = select_configurable_residual_strategy(req)
        assert result.compatibility.is_compatible is True

    def test_generic_roles_zero_residuals_at_consistent_point(self):
        """Changing roles does not change which residuals are evaluated."""
        br_generic = _build_single_loop_generic_roles()
        req = ConfigurableResidualSelectionRequest(
            build_result=br_generic,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
            single_loop_parameters=_SL_PARAMS,
            single_loop_unknown_values=_SL_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        ev = result.evaluation_result
        assert isinstance(ev, FixedSingleLoopEvaluationResult)
        assert ev.max_abs_residual == pytest.approx(0.0, abs=1e-9)

    def test_declaration_only_compatible_with_any_role_set(self):
        for build_fn in (_build_single_loop, _build_single_loop_generic_roles):
            br = build_fn()
            req = ConfigurableResidualSelectionRequest(
                build_result=br,
                mode=ConfigurableResidualMode.DECLARATION_ONLY,
            )
            result = select_configurable_residual_strategy(req)
            assert result.compatibility.is_compatible is True
            assert result.no_solve is True

    def test_report_roles_flag_always_false_regardless_of_roles(self):
        for build_fn in (_build_single_loop, _build_single_loop_generic_roles):
            br = build_fn()
            req = ConfigurableResidualSelectionRequest(
                build_result=br,
                mode=ConfigurableResidualMode.DECLARATION_ONLY,
            )
            result = select_configurable_residual_strategy(req)
            report = build_configurable_residual_selection_report(result)
            assert report["roles_selected_physics"] is False


# ---------------------------------------------------------------------------
# Story 6 — Incompatible scenarios are rejected cleanly
# ---------------------------------------------------------------------------


class TestStory6IncompatibleRejectedCleanly:
    def test_single_loop_scenario_incompatible_with_two_branch_mode(self):
        """4-component single-loop does not satisfy two-branch ID requirements."""
        br = _build_single_loop()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC,
        )
        result = select_configurable_residual_strategy(req)
        assert result.compatibility.is_compatible is False

    def test_incompatible_mode_not_evaluated_despite_evaluate_true(self):
        br = _build_single_loop()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC,
            two_branch_parameters=_TB_PARAMS,
            two_branch_unknown_values=_TB_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.evaluation_performed is False

    def test_incompatible_evaluate_selected_raises(self):
        br = _build_incompatible()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
        )
        with pytest.raises(ValueError):
            evaluate_selected_configurable_residuals(req)

    def test_incompatible_report_has_deterministic_reasons(self):
        br = _build_incompatible()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        assert report["compatibility"]["is_compatible"] is False
        reasons = report["compatibility"]["reasons"]
        assert isinstance(reasons, list)
        assert len(reasons) > 0

    def test_incompatible_no_solve_still_true(self):
        """no_solve is always True even for incompatible scenario."""
        br = _build_incompatible()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        assert report["no_solve"] is True

    def test_no_fallback_to_declaration_only(self):
        """Selected mode stays as requested; no silent substitution on incompatibility."""
        br = _build_incompatible()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
        )
        result = select_configurable_residual_strategy(req)
        assert result.selected_mode is ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC
        assert result.compatibility.is_compatible is False

    def test_incompatible_report_is_json_serializable(self):
        br = _build_incompatible()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        json.dumps(report)


# ---------------------------------------------------------------------------
# Story 7 — Combined reports from all three layers are JSON-serializable
# ---------------------------------------------------------------------------


class TestStory7CombinedReportsSerializable:
    def test_scenario_declaration_report_is_serializable(self):
        br = _build_single_loop()
        scenario_report = build_configurable_scenario_report(br)
        json.dumps(scenario_report)
        assert scenario_report["no_solve"] is True

    def test_selection_report_is_serializable(self):
        br = _build_single_loop()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
            single_loop_parameters=_SL_PARAMS,
            single_loop_unknown_values=_SL_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        selection_report = build_configurable_residual_selection_report(result)
        json.dumps(selection_report)
        assert selection_report["no_solve"] is True

    def test_closure_report_is_serializable(self):
        closure_set = _build_closure_set()
        ev = evaluate_combined_closure_residuals(closure_set, _CLOSURE_UV)
        closure_report = build_combined_closure_report(ev)
        json.dumps(closure_report)
        assert closure_report["no_solve"] is True

    def test_combined_three_layer_dict_is_serializable(self):
        """All three layer reports coexist in one test-only aggregation dict."""
        br = _build_single_loop()
        scenario_report = build_configurable_scenario_report(br)
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
            single_loop_parameters=_SL_PARAMS,
            single_loop_unknown_values=_SL_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        selection_report = build_configurable_residual_selection_report(result)
        closure_set = _build_closure_set()
        ev = evaluate_combined_closure_residuals(closure_set, _CLOSURE_UV)
        closure_report = build_combined_closure_report(ev)
        combined = {
            "block_15e_c_closeout": True,
            "scenario": scenario_report,
            "residual_selection": selection_report,
            "closure": closure_report,
        }
        json.dumps(combined)

    def test_all_three_no_solve_flags_true(self):
        br = _build_single_loop()
        scenario_report = build_configurable_scenario_report(br)
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        selection_report = build_configurable_residual_selection_report(result)
        closure_set = _build_closure_set()
        ev = evaluate_combined_closure_residuals(closure_set, _CLOSURE_UV)
        closure_report = build_combined_closure_report(ev)
        assert scenario_report["no_solve"] is True
        assert selection_report["no_solve"] is True
        assert closure_report["no_solve"] is True


# ---------------------------------------------------------------------------
# Boundary B1 — no_solve=True in every result regardless of mode
# ---------------------------------------------------------------------------


class TestBoundaryNoSolveAlwaysTrue:
    def test_declaration_only_no_solve(self):
        br = _build_single_loop()
        result = select_configurable_residual_strategy(
            ConfigurableResidualSelectionRequest(
                build_result=br,
                mode=ConfigurableResidualMode.DECLARATION_ONLY,
            )
        )
        assert result.no_solve is True

    def test_single_loop_evaluated_no_solve(self):
        br = _build_single_loop()
        result = select_configurable_residual_strategy(
            ConfigurableResidualSelectionRequest(
                build_result=br,
                mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
                single_loop_parameters=_SL_PARAMS,
                single_loop_unknown_values=_SL_UV,
                evaluate=True,
            )
        )
        assert result.no_solve is True

    def test_two_branch_evaluated_no_solve(self):
        br = _build_two_branch()
        result = select_configurable_residual_strategy(
            ConfigurableResidualSelectionRequest(
                build_result=br,
                mode=ConfigurableResidualMode.FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC,
                two_branch_parameters=_TB_PARAMS,
                two_branch_unknown_values=_TB_UV,
                evaluate=True,
            )
        )
        assert result.no_solve is True

    def test_closure_only_evaluated_no_solve(self):
        br = _build_single_loop()
        result = select_configurable_residual_strategy(
            ConfigurableResidualSelectionRequest(
                build_result=br,
                mode=ConfigurableResidualMode.CLOSURE_ONLY,
                closure_residual_set=_build_closure_set(),
                closure_unknown_values=_CLOSURE_UV,
                evaluate=True,
            )
        )
        assert result.no_solve is True

    def test_incompatible_scenario_no_solve(self):
        br = _build_incompatible()
        result = select_configurable_residual_strategy(
            ConfigurableResidualSelectionRequest(
                build_result=br,
                mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
            )
        )
        assert result.no_solve is True


# ---------------------------------------------------------------------------
# Boundary B2–B6 — module-level architecture constraints
# ---------------------------------------------------------------------------


class TestBoundaryArchitectureConstraints:
    def test_solve_fixed_single_loop_residuals_not_imported(self):
        """Only evaluate_fixed_single_loop_residuals is imported, not the solve variant."""
        assert not hasattr(_CRS_MOD, "solve_fixed_single_loop_residuals")

    def test_evaluate_fixed_single_loop_residuals_is_imported(self):
        """evaluate_fixed_single_loop_residuals must be present (not solve variant)."""
        assert hasattr(_CRS_MOD, "evaluate_fixed_single_loop_residuals")

    def test_no_coolprop_in_module(self):
        assert not hasattr(_CRS_MOD, "CoolProp")
        assert "CoolProp" not in _CRS_MOD.__dict__

    def test_no_property_backend_in_module(self):
        assert not hasattr(_CRS_MOD, "PropertyBackend")

    def test_no_system_state_in_module(self):
        assert not hasattr(_CRS_MOD, "SystemState")

    def test_no_fluid_state_in_module(self):
        assert not hasattr(_CRS_MOD, "FluidState")

    def test_no_contribute_attribute_in_module(self):
        assert not hasattr(_CRS_MOD, "contribute")

    def test_no_generic_solve_in_selection_result(self):
        br = _build_single_loop()
        result = select_configurable_residual_strategy(
            ConfigurableResidualSelectionRequest(
                build_result=br,
                mode=ConfigurableResidualMode.DECLARATION_ONLY,
            )
        )
        assert not hasattr(result, "solve")
        assert not hasattr(result, "converged")
        assert not hasattr(result, "iteration_count")

    def test_report_carries_no_solver_fields(self):
        br = _build_single_loop()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
            single_loop_parameters=_SL_PARAMS,
            single_loop_unknown_values=_SL_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        assert "converged" not in report
        assert "iterations" not in report
        assert report["no_solve"] is True

    def test_closure_without_explicit_set_is_incompatible(self):
        """No closure is auto-created from roles; must be supplied explicitly."""
        br = _build_single_loop_generic_roles()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.CLOSURE_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        assert result.compatibility.is_compatible is False

    def test_limitations_present_for_all_modes(self):
        """All four modes carry the module-level limitations list."""
        for mode in ConfigurableResidualMode:
            br = _build_single_loop()
            req = ConfigurableResidualSelectionRequest(build_result=br, mode=mode)
            result = select_configurable_residual_strategy(req)
            assert len(result.limitations) > 0


# ---------------------------------------------------------------------------
# Regression R1–R2 — production contracts unchanged
# ---------------------------------------------------------------------------


class TestRegressionProductionContracts:
    def test_all_six_production_classes_no_contribute(self):
        """Phase 14G regression: all known production classes still NO_CONTRIBUTE_METHOD."""
        from mpl_sim.network.production_component_inspection import (
            ProductionComponentContractStatus,
            inspect_known_production_component_contracts,
        )

        expected = {
            "Component",
            "Pipe",
            "PumpComponent",
            "AccumulatorComponent",
            "EvaporatorComponent",
            "CondenserComponent",
        }
        results = inspect_known_production_component_contracts()
        found = {r.class_name for r in results}
        for name in expected:
            assert name in found, f"Expected class {name!r} not in inspection results"
        for r in results:
            assert (
                r.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD
            ), f"{r.class_name!r} unexpectedly has a contribute method"

    def test_inspection_returns_exactly_six_results(self):
        from mpl_sim.network.production_component_inspection import (
            inspect_known_production_component_contracts,
        )

        results = inspect_known_production_component_contracts()
        assert len(results) == 6
