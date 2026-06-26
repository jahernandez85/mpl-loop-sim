"""Integration tests for Block 15E-B configurable residual selection.

Tests actual residual evaluation through existing fixed-evaluation backends.
Proves that:
  - FIXED_SINGLE_LOOP_ALGEBRAIC evaluates via evaluate_fixed_single_loop_residuals
    and returns zero residuals at the consistent point
  - FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC evaluates via evaluate_parallel_topology_residuals
    and returns zero residuals at the consistent point
  - CLOSURE_ONLY evaluates via evaluate_combined_closure_residuals
  - Perturbed points give nonzero residuals
  - No solve is performed in any mode
  - evaluate_selected_configurable_residuals works and requires params
  - Reports contain actual residual values and norms after evaluation

These tests do NOT:
  - Call any solver.
  - Execute production component physics.
  - Call CoolProp, PropertyBackend, or correlations.
  - Assemble SystemState or FluidState.

Sign conventions (from existing modules):
  Fixed single-loop:
    pressure_drop:accumulator = P_n_acc_out - acc_ref                   [= 0]
    pressure_drop:pump        = P_n_pump_out - P_n_acc_out - pump_rise  [= 0]
    pressure_drop:evaporator  = P_n_evap_out - P_n_pump_out + evap_drop [= 0]
    pressure_drop:condenser   = P_n_cond_out - P_n_evap_out + cond_drop [= 0]

  Fixed two-branch:
    branch compat: branch_a_drop + merge_a_drop == branch_b_drop + merge_b_drop
"""

from __future__ import annotations

import json

import pytest

from mpl_sim.network.closure_integration import (
    CombinedClosureEvaluationResult,
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
)
from mpl_sim.network.fixed_single_loop_residuals import FixedSingleLoopResidualParameters
from mpl_sim.network.fixed_single_loop_runner import FixedSingleLoopEvaluationResult
from mpl_sim.network.hydraulic_closures import (
    ImposedMassFlowClosure,
    ImposedPressureClosure,
    build_hydraulic_closure_residuals,
)
from mpl_sim.network.parallel_topology_residuals import (
    ParallelTopologyEvaluationResult,
    ParallelTopologyResidualParameters,
)

# ---------------------------------------------------------------------------
# Consistent test parameters
# ---------------------------------------------------------------------------

# Fixed single-loop consistent point:
#   P_n_acc_out  = 100000 Pa
#   P_n_pump_out = 100000 + 50000 = 150000 Pa
#   P_n_evap_out = 150000 - 30000 = 120000 Pa
#   P_n_cond_out = 120000 - 20000 = 100000 Pa  (consistent: acc_ref=100000)
_SL_PARAMS = FixedSingleLoopResidualParameters(
    pump_pressure_rise=50000.0,
    evaporator_pressure_drop=30000.0,
    condenser_pressure_drop=20000.0,
    accumulator_pressure_reference=100000.0,
)
_SL_CONSISTENT_UV = {
    "mdot:accumulator": 1.0,
    "mdot:pump": 1.0,
    "mdot:evaporator": 1.0,
    "mdot:condenser": 1.0,
    "P:n_acc_out": 100000.0,
    "P:n_pump_out": 150000.0,
    "P:n_evap_out": 120000.0,
    "P:n_cond_out": 100000.0,
}
_SL_PERTURBED_UV = {
    "mdot:accumulator": 1.0,
    "mdot:pump": 1.0,
    "mdot:evaporator": 1.0,
    "mdot:condenser": 1.0,
    "P:n_acc_out": 110000.0,  # wrong — off-solution
    "P:n_pump_out": 150000.0,
    "P:n_evap_out": 120000.0,
    "P:n_cond_out": 100000.0,
}

# Fixed two-branch consistent point:
#   branch_a_drop=30000, merge_a_drop=20000 → path_a=50000
#   branch_b_drop=40000, merge_b_drop=10000 → path_b=50000  (compatible)
#   P_n_acc_out=100000, pump_rise=50000
#   P_n_pump_out  = 100000 + 50000 = 150000
#   P_n_a_out     = 150000 - 30000 = 120000
#   P_n_b_out     = 150000 - 40000 = 110000
#   P_n_merge_out = 120000 - 20000 = 100000 (= 110000 - 10000 ✓)
#   P_n_cond_out  = 100000 - 5000  = 95000
_TB_PARAMS = ParallelTopologyResidualParameters(
    accumulator_pressure_reference=100000.0,
    pump_pressure_rise=50000.0,
    branch_a_pressure_drop=30000.0,
    branch_b_pressure_drop=40000.0,
    merge_a_pressure_drop=20000.0,
    merge_b_pressure_drop=10000.0,
    condenser_pressure_drop=5000.0,
)
_TB_CONSISTENT_UV = {
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
_TB_PERTURBED_UV = {
    **_TB_CONSISTENT_UV,
    "P:n_pump_out": 140000.0,  # wrong — off-solution
}


# ---------------------------------------------------------------------------
# Helpers: build configurable scenarios
# ---------------------------------------------------------------------------


def _single_loop_result():
    spec = ConfigurableScenarioSpec(
        scenario_id="sl_integration",
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


def _two_branch_result():
    spec = ConfigurableScenarioSpec(
        scenario_id="tb_integration",
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


def _closure_set_with_imposed_flow():
    """A simple combined closure: imposed mdot=1.0 and imposed P=100000."""
    hyd = build_hydraulic_closure_residuals(
        closures=(
            ImposedMassFlowClosure(
                unknown_name="mdot_ref",
                imposed_value=1.0,
                residual_name="r_mdot_imposed",
            ),
            ImposedPressureClosure(
                unknown_name="P_ref",
                imposed_value=100000.0,
                residual_name="r_P_imposed",
            ),
        )
    )
    return build_combined_closure_residuals(hydraulic=hyd)


# ---------------------------------------------------------------------------
# Tests: Fixed single-loop evaluation
# ---------------------------------------------------------------------------


class TestFixedSingleLoopEvaluation:
    def test_consistent_point_zero_residuals(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
            single_loop_parameters=_SL_PARAMS,
            single_loop_unknown_values=_SL_CONSISTENT_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.evaluation_performed is True
        assert result.evaluation_result is not None
        ev = result.evaluation_result
        assert isinstance(ev, FixedSingleLoopEvaluationResult)
        assert ev.max_abs_residual == pytest.approx(0.0, abs=1e-9)
        assert ev.l2_residual == pytest.approx(0.0, abs=1e-9)

    def test_perturbed_point_nonzero_residuals(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
            single_loop_parameters=_SL_PARAMS,
            single_loop_unknown_values=_SL_PERTURBED_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.evaluation_performed is True
        ev = result.evaluation_result
        assert isinstance(ev, FixedSingleLoopEvaluationResult)
        assert ev.max_abs_residual > 0.0

    def test_evaluation_result_has_eight_residuals(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
            single_loop_parameters=_SL_PARAMS,
            single_loop_unknown_values=_SL_CONSISTENT_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        ev = result.evaluation_result
        assert isinstance(ev, FixedSingleLoopEvaluationResult)
        assert len(ev.residual_names) == 8
        assert len(ev.residual_values) == 8

    def test_no_solve_true_after_evaluation(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
            single_loop_parameters=_SL_PARAMS,
            single_loop_unknown_values=_SL_CONSISTENT_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.no_solve is True

    def test_evaluate_selected_requires_params_and_returns_result(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
            single_loop_parameters=_SL_PARAMS,
            single_loop_unknown_values=_SL_CONSISTENT_UV,
            evaluate=True,
        )
        result = evaluate_selected_configurable_residuals(req)
        assert result.evaluation_performed is True
        assert isinstance(result.evaluation_result, FixedSingleLoopEvaluationResult)

    def test_report_includes_residual_values_after_evaluation(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
            single_loop_parameters=_SL_PARAMS,
            single_loop_unknown_values=_SL_CONSISTENT_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        ev_section = report["evaluation"]
        assert ev_section["performed"] is True  # type: ignore[index]
        assert "residual_values" in ev_section  # type: ignore[operator]
        assert "max_abs_residual" in ev_section  # type: ignore[operator]
        json.dumps(report)

    def test_report_evaluation_backend_is_fixed_single_loop(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
            single_loop_parameters=_SL_PARAMS,
            single_loop_unknown_values=_SL_CONSISTENT_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        assert report["evaluation"]["backend"] == "fixed_single_loop"  # type: ignore[index]

    def test_uses_evaluation_only_path_not_solve(self):
        """The result should not have any solver-originated fields."""
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
            single_loop_parameters=_SL_PARAMS,
            single_loop_unknown_values=_SL_CONSISTENT_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        ev = result.evaluation_result
        assert isinstance(ev, FixedSingleLoopEvaluationResult)
        # FixedSingleLoopEvaluationResult has no converged/iteration_count fields
        # (those belong to FixedSingleLoopSolveResult)
        assert not hasattr(ev, "converged")
        assert not hasattr(ev, "iteration_count")


# ---------------------------------------------------------------------------
# Tests: Fixed two-branch parallel evaluation
# ---------------------------------------------------------------------------


class TestFixedTwoBranchEvaluation:
    def test_consistent_point_zero_residuals(self):
        br = _two_branch_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC,
            two_branch_parameters=_TB_PARAMS,
            two_branch_unknown_values=_TB_CONSISTENT_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.evaluation_performed is True
        ev = result.evaluation_result
        assert isinstance(ev, ParallelTopologyEvaluationResult)
        assert ev.max_abs_residual == pytest.approx(0.0, abs=1e-9)
        assert ev.l2_residual == pytest.approx(0.0, abs=1e-9)

    def test_perturbed_point_nonzero_residuals(self):
        br = _two_branch_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC,
            two_branch_parameters=_TB_PARAMS,
            two_branch_unknown_values=_TB_PERTURBED_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.evaluation_performed is True
        ev = result.evaluation_result
        assert isinstance(ev, ParallelTopologyEvaluationResult)
        assert ev.max_abs_residual > 0.0

    def test_evaluation_result_has_thirteen_residuals(self):
        br = _two_branch_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC,
            two_branch_parameters=_TB_PARAMS,
            two_branch_unknown_values=_TB_CONSISTENT_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        ev = result.evaluation_result
        assert isinstance(ev, ParallelTopologyEvaluationResult)
        assert len(ev.residual_names) == 13

    def test_no_solve_true_after_evaluation(self):
        br = _two_branch_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC,
            two_branch_parameters=_TB_PARAMS,
            two_branch_unknown_values=_TB_CONSISTENT_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.no_solve is True

    def test_evaluate_selected_works_for_two_branch(self):
        br = _two_branch_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC,
            two_branch_parameters=_TB_PARAMS,
            two_branch_unknown_values=_TB_CONSISTENT_UV,
            evaluate=True,
        )
        result = evaluate_selected_configurable_residuals(req)
        assert result.evaluation_performed is True
        assert isinstance(result.evaluation_result, ParallelTopologyEvaluationResult)

    def test_report_is_json_serializable_with_residuals(self):
        br = _two_branch_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC,
            two_branch_parameters=_TB_PARAMS,
            two_branch_unknown_values=_TB_CONSISTENT_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        json.dumps(report)
        ev_section = report["evaluation"]
        assert ev_section["performed"] is True  # type: ignore[index]
        assert "residual_values" in ev_section  # type: ignore[operator]

    def test_report_backend_is_parallel_topology(self):
        br = _two_branch_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC,
            two_branch_parameters=_TB_PARAMS,
            two_branch_unknown_values=_TB_CONSISTENT_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        assert report["evaluation"]["backend"] == "parallel_topology"  # type: ignore[index]

    def test_two_branch_deferred_without_params(self):
        br = _two_branch_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC,
            # No params
        )
        result = select_configurable_residual_strategy(req)
        assert result.evaluation_performed is False
        assert result.evaluation_deferred is True


# ---------------------------------------------------------------------------
# Tests: Closure-only evaluation
# ---------------------------------------------------------------------------


class TestClosureOnlyEvaluation:
    def test_closure_evaluates_at_consistent_point(self):
        closure_set = _closure_set_with_imposed_flow()
        # Consistent: mdot_ref=1.0, P_ref=100000 (match imposed values)
        uvs = {"mdot_ref": 1.0, "P_ref": 100000.0}

        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.CLOSURE_ONLY,
            closure_residual_set=closure_set,
            closure_unknown_values=uvs,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.evaluation_performed is True
        ev = result.evaluation_result
        assert isinstance(ev, CombinedClosureEvaluationResult)
        # r = mdot_ref - 1.0 = 0.0; r = P_ref - 100000 = 0.0
        assert ev.max_absolute_residual == pytest.approx(0.0, abs=1e-9)

    def test_closure_perturbed_point_nonzero(self):
        closure_set = _closure_set_with_imposed_flow()
        uvs = {"mdot_ref": 2.0, "P_ref": 100000.0}  # mdot_ref is wrong

        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.CLOSURE_ONLY,
            closure_residual_set=closure_set,
            closure_unknown_values=uvs,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.evaluation_performed is True
        ev = result.evaluation_result
        assert isinstance(ev, CombinedClosureEvaluationResult)
        assert ev.max_absolute_residual > 0.0

    def test_evaluate_selected_works_for_closure_only(self):
        closure_set = _closure_set_with_imposed_flow()
        uvs = {"mdot_ref": 1.0, "P_ref": 100000.0}
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.CLOSURE_ONLY,
            closure_residual_set=closure_set,
            closure_unknown_values=uvs,
            evaluate=True,
        )
        result = evaluate_selected_configurable_residuals(req)
        assert result.evaluation_performed is True
        assert isinstance(result.evaluation_result, CombinedClosureEvaluationResult)

    def test_closure_only_no_solve(self):
        closure_set = _closure_set_with_imposed_flow()
        uvs = {"mdot_ref": 1.0, "P_ref": 100000.0}
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.CLOSURE_ONLY,
            closure_residual_set=closure_set,
            closure_unknown_values=uvs,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.no_solve is True

    def test_report_with_closure_residuals(self):
        closure_set = _closure_set_with_imposed_flow()
        uvs = {"mdot_ref": 1.0, "P_ref": 100000.0}
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.CLOSURE_ONLY,
            closure_residual_set=closure_set,
            closure_unknown_values=uvs,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        json.dumps(report)
        ev_section = report["evaluation"]
        assert ev_section["performed"] is True  # type: ignore[index]
        assert "combined_residuals" in ev_section  # type: ignore[operator]
        assert ev_section["backend"] == "combined_closure"  # type: ignore[index]

    def test_closure_only_deferred_without_unknown_values(self):
        closure_set = _closure_set_with_imposed_flow()
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.CLOSURE_ONLY,
            closure_residual_set=closure_set,
            # No closure_unknown_values
        )
        result = select_configurable_residual_strategy(req)
        assert result.evaluation_performed is False
        assert result.evaluation_deferred is True

    def test_closure_only_incompatible_without_set(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.CLOSURE_ONLY,
            # No closure_residual_set
        )
        result = select_configurable_residual_strategy(req)
        assert result.compatibility.is_compatible is False
        assert result.evaluation_performed is False


# ---------------------------------------------------------------------------
# Tests: Declaration-only refuses evaluation
# ---------------------------------------------------------------------------


class TestDeclarationOnlyRefusesEvaluation:
    def test_declaration_only_never_evaluates_even_with_params(self):
        """Even if single_loop_parameters are provided, DECLARATION_ONLY never evaluates."""
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
            single_loop_parameters=_SL_PARAMS,
            single_loop_unknown_values=_SL_CONSISTENT_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.evaluation_performed is False
        assert result.evaluation_result is None

    def test_declaration_only_evaluate_selected_raises(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
            single_loop_parameters=_SL_PARAMS,
            single_loop_unknown_values=_SL_CONSISTENT_UV,
            evaluate=True,
        )
        with pytest.raises(ValueError):
            evaluate_selected_configurable_residuals(req)

    def test_declaration_only_report_no_residual_values(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        ev_section = report["evaluation"]
        assert ev_section["performed"] is False  # type: ignore[index]
        assert "residual_values" not in ev_section  # type: ignore[operator]


# ---------------------------------------------------------------------------
# Tests: Regression — 15E-A, 15D-C, 15C-B, 14G still pass (structural)
# ---------------------------------------------------------------------------


class TestRegressionBoundaries:
    def test_production_component_inspection_still_no_contribute(self):
        """Phase 14G production contract inspection must still show NO_CONTRIBUTE_METHOD."""
        from mpl_sim.network.production_component_inspection import (
            ProductionComponentContractStatus,
            inspect_known_production_component_contracts,
        )

        results = inspect_known_production_component_contracts()
        for r in results:
            assert (
                r.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD
            ), f"Production class {r.class_name!r} unexpectedly has a contribute method"

    def test_configurable_scenarios_still_work(self):
        """15E-A configurable builder still works correctly."""
        br = _single_loop_result()
        assert len(br.component_ids) == 4
        assert len(br.node_ids) == 4
        assert len(br.unknown_names) == 8

    def test_parallel_topology_residuals_still_work(self):
        """15C-B parallel topology evaluation still works independently."""
        from mpl_sim.network.parallel_topology_scenario import build_parallel_topology_scenario

        scenario = build_parallel_topology_scenario()
        from mpl_sim.network.parallel_topology_residuals import evaluate_parallel_topology_residuals

        result = evaluate_parallel_topology_residuals(scenario, _TB_PARAMS, _TB_CONSISTENT_UV)
        assert result.max_abs_residual == pytest.approx(0.0, abs=1e-9)

    def test_closure_integration_still_works(self):
        """15D-C closure integration still works independently."""
        hyd = build_hydraulic_closure_residuals(
            closures=(
                ImposedMassFlowClosure(
                    unknown_name="mdot",
                    imposed_value=1.5,
                    residual_name="r_mdot",
                ),
            )
        )
        combined = build_combined_closure_residuals(hydraulic=hyd)
        ev = evaluate_combined_closure_residuals(combined, {"mdot": 1.5})
        assert ev.max_absolute_residual == pytest.approx(0.0, abs=1e-9)

    def test_no_coolprop_in_new_module(self):
        """configurable_residual_selection must not import CoolProp."""
        import importlib
        import sys

        mod_name = "mpl_sim.network.configurable_residual_selection"
        mod = sys.modules.get(mod_name) or importlib.import_module(mod_name)
        # CoolProp should not appear in module's direct imports
        assert "CoolProp" not in (getattr(mod, "__dict__", {}) or {})

    def test_no_systemstate_or_fluidstate_in_new_module(self):
        """configurable_residual_selection must not reference SystemState or FluidState."""
        import importlib
        import sys

        mod_name = "mpl_sim.network.configurable_residual_selection"
        mod = sys.modules.get(mod_name) or importlib.import_module(mod_name)
        assert "SystemState" not in (getattr(mod, "__dict__", {}) or {})
        assert "FluidState" not in (getattr(mod, "__dict__", {}) or {})
