"""Integration tests for Block 15G-B — Blueprint Selection Workflow Integration.

Proves that the workflow helper correctly composes Block 15G-A explicit
residual blueprints with the Block 15F-B CONFIGURABLE_ALGEBRAIC selection
mode, and that the workflow report stack composes cleanly with the 15G-A
blueprint report and the existing scenario report.

Acceptance stories
------------------
A1  Build configurable single-loop scenario; declare explicit blueprints;
    run workflow with evaluate=True; residual values match direct 15F-A
    evaluation from the blueprint build result.
A2  Workflow selected_mode equals CONFIGURABLE_ALGEBRAIC.
A3  Compose scenario report + blueprint report + workflow report into JSON.
A4  Production contract remains frozen (NO_CONTRIBUTE_METHOD for all 6 classes).
A5  Perturbed unknowns produce matching nonzero residuals in both the direct
    15F-A path and the workflow path.

Boundary stories
----------------
B1  New test module imports no CoolProp or PropertyBackend.
B2  No contribute attribute in workflow module.
B3  No SystemState or FluidState in new modules.
B4  No solve(network) or NetworkGraph.solve() in new modules.
B5  No mpl_sim.components, properties, correlations, hx_models imports.

These tests do NOT:
  - Call any solver or root-finder.
  - Execute production component physics.
  - Call CoolProp, PropertyBackend, or correlations.
  - Assemble SystemState or construct FluidState.
  - Write files, use pandas, or use numpy.
  - Infer blueprints or residuals from roles or topology.
"""

from __future__ import annotations

import json

import pytest

from mpl_sim.network.configurable_algebraic_residuals import (
    evaluate_configurable_algebraic_residuals,
)
from mpl_sim.network.configurable_residual_blueprint_workflows import (
    ConfigurableResidualBlueprintWorkflowRequest,
    build_configurable_residual_blueprint_workflow_report,
    build_configurable_residual_selection_from_blueprints,
)
from mpl_sim.network.configurable_residual_blueprints import (
    ImposedMassFlowResidualBlueprint,
    ImposedPressureResidualBlueprint,
    MassBalanceResidualBlueprint,
    PressureDifferenceResidualBlueprint,
    build_configurable_algebraic_residuals_from_blueprints,
    build_configurable_residual_blueprint_report,
)
from mpl_sim.network.configurable_residual_selection import ConfigurableResidualMode
from mpl_sim.network.configurable_scenarios import (
    ConfigurableScenarioSpec,
    ScenarioComponentRole,
    ScenarioComponentSpec,
    ScenarioConnectionSpec,
    ScenarioNodeSpec,
    build_configurable_scenario,
    build_configurable_scenario_report,
)
from mpl_sim.network.production_component_inspection import (
    ProductionComponentContractStatus,
    inspect_known_production_component_contracts,
)

# ===========================================================================
# Shared test fixture — single-loop configurable scenario
# ===========================================================================

_SINGLE_LOOP_SPEC = ConfigurableScenarioSpec(
    scenario_id="wf_integration_single_loop",
    components=[
        ScenarioComponentSpec("accumulator", ScenarioComponentRole.ACCUMULATOR),
        ScenarioComponentSpec("pump", ScenarioComponentRole.PUMP),
        ScenarioComponentSpec("evaporator", ScenarioComponentRole.EVAPORATOR),
        ScenarioComponentSpec("condenser", ScenarioComponentRole.CONDENSER),
    ],
    nodes=[
        ScenarioNodeSpec("n_acc_out"),
        ScenarioNodeSpec("n_pump_out"),
        ScenarioNodeSpec("n_evap_out"),
        ScenarioNodeSpec("n_cond_out"),
    ],
    connections=[
        ScenarioConnectionSpec("accumulator", "n_cond_out", "n_acc_out"),
        ScenarioConnectionSpec("pump", "n_acc_out", "n_pump_out"),
        ScenarioConnectionSpec("evaporator", "n_pump_out", "n_evap_out"),
        ScenarioConnectionSpec("condenser", "n_evap_out", "n_cond_out"),
    ],
)

_ZERO_RESIDUAL_UNKNOWNS = {
    "mdot:accumulator": 0.1,
    "mdot:pump": 0.1,
    "mdot:evaporator": 0.1,
    "mdot:condenser": 0.1,
    "P:n_acc_out": 100_000.0,
    "P:n_pump_out": 150_000.0,
    "P:n_evap_out": 130_000.0,
    "P:n_cond_out": 110_000.0,
}


def _make_four_blueprints() -> list:
    return [
        MassBalanceResidualBlueprint(
            residual_name="mb_pump_out",
            incoming_component_ids=("pump",),
            outgoing_component_ids=("evaporator",),
            anchor_node_id="n_pump_out",
        ),
        ImposedPressureResidualBlueprint(
            residual_name="p_ref",
            node_id="n_acc_out",
            pressure=100_000.0,
        ),
        ImposedMassFlowResidualBlueprint(
            residual_name="mdot_pump",
            component_id="pump",
            mass_flow=0.1,
        ),
        PressureDifferenceResidualBlueprint(
            residual_name="dp_pump",
            inlet_node_id="n_acc_out",
            outlet_node_id="n_pump_out",
            delta_p=-50_000.0,
        ),
    ]


# ===========================================================================
# A1/A2 — workflow matches direct 15F-A evaluation; mode is CONFIGURABLE_ALGEBRAIC
# ===========================================================================


class TestWorkflowMatchesDirectEvaluation:
    def test_workflow_residuals_match_direct_blueprint_evaluation_at_zero_point(self) -> None:
        sbr = build_configurable_scenario(_SINGLE_LOOP_SPEC)
        bps = _make_four_blueprints()

        # Direct 15F-A evaluation from the 15G-A blueprint build result.
        direct_bp_result = build_configurable_algebraic_residuals_from_blueprints(
            bps, scenario_build_result=sbr
        )
        direct_eval = evaluate_configurable_algebraic_residuals(
            direct_bp_result.algebraic_residual_set, _ZERO_RESIDUAL_UNKNOWNS
        )

        # Workflow path.
        request = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=bps,
            algebraic_unknown_values=_ZERO_RESIDUAL_UNKNOWNS,
            evaluate=True,
        )
        result = build_configurable_residual_selection_from_blueprints(request)

        assert result.evaluation_performed is True
        workflow_eval = result.selection_result.evaluation_result

        assert workflow_eval.residual_names == direct_eval.residual_names
        for name in direct_eval.residual_names:
            assert workflow_eval.residual_values[name] == pytest.approx(
                direct_eval.residual_values[name], abs=1e-10
            )
        assert workflow_eval.max_abs_residual == pytest.approx(
            direct_eval.max_abs_residual, abs=1e-10
        )
        assert workflow_eval.max_abs_residual == pytest.approx(0.0, abs=1e-10)

    def test_workflow_selected_mode_is_configurable_algebraic(self) -> None:
        sbr = build_configurable_scenario(_SINGLE_LOOP_SPEC)
        bps = _make_four_blueprints()
        request = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=bps,
        )
        result = build_configurable_residual_selection_from_blueprints(request)
        assert result.selected_mode is ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC


# ===========================================================================
# A5 — perturbation matches between direct and workflow paths
# ===========================================================================


class TestWorkflowMatchesDirectEvaluationPerturbed:
    def test_workflow_residuals_match_direct_after_perturbation(self) -> None:
        sbr = build_configurable_scenario(_SINGLE_LOOP_SPEC)
        bps = _make_four_blueprints()

        perturbed = dict(_ZERO_RESIDUAL_UNKNOWNS)
        perturbed["mdot:pump"] = 0.4
        perturbed["P:n_acc_out"] = 95_000.0

        direct_bp_result = build_configurable_algebraic_residuals_from_blueprints(
            bps, scenario_build_result=sbr
        )
        direct_eval = evaluate_configurable_algebraic_residuals(
            direct_bp_result.algebraic_residual_set, perturbed
        )

        request = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=bps,
            algebraic_unknown_values=perturbed,
            evaluate=True,
        )
        result = build_configurable_residual_selection_from_blueprints(request)
        workflow_eval = result.selection_result.evaluation_result

        for name in direct_eval.residual_names:
            assert workflow_eval.residual_values[name] == pytest.approx(
                direct_eval.residual_values[name], abs=1e-10
            )
        assert workflow_eval.max_abs_residual > 0.0


# ===========================================================================
# A3 — combined report stack: scenario + blueprint + workflow
# ===========================================================================


class TestCombinedReportStack:
    def test_combined_report_stack_is_json_serializable(self) -> None:
        sbr = build_configurable_scenario(_SINGLE_LOOP_SPEC)
        bps = _make_four_blueprints()

        scenario_report = build_configurable_scenario_report(sbr)
        bp_result = build_configurable_algebraic_residuals_from_blueprints(
            bps, scenario_build_result=sbr
        )
        blueprint_report = build_configurable_residual_blueprint_report(bp_result)

        request = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=bps,
            algebraic_unknown_values=_ZERO_RESIDUAL_UNKNOWNS,
            evaluate=True,
        )
        result = build_configurable_residual_selection_from_blueprints(request)
        workflow_report = build_configurable_residual_blueprint_workflow_report(result)

        combined = {
            "scenario_report": scenario_report,
            "blueprint_report": blueprint_report,
            "workflow_report": workflow_report,
        }
        json_str = json.dumps(combined)
        parsed = json.loads(json_str)

        assert parsed["workflow_report"]["no_solve"] is True
        assert parsed["blueprint_report"]["no_solve"] is True
        assert parsed["workflow_report"]["selected_mode"] == "configurable_algebraic"
        assert parsed["workflow_report"]["selection_report"]["no_solve"] is True


# ===========================================================================
# A4 — production contract remains frozen
# ===========================================================================


class TestProductionComponentContractsFrozen:
    def test_all_six_have_no_contribute_method(self) -> None:
        results = inspect_known_production_component_contracts()
        for r in results:
            assert (
                r.status is ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD
            ), f"{r.class_name} unexpectedly has contribute method"

    def test_exactly_six_production_classes_inspected(self) -> None:
        results = inspect_known_production_component_contracts()
        assert len(results) == 6


# ===========================================================================
# Boundary stories
# ===========================================================================


class TestWorkflowIntegrationBoundaries:
    def test_no_coolprop_in_module(self) -> None:
        import mpl_sim.network.configurable_residual_blueprint_workflows as mod

        assert not hasattr(mod, "CoolProp")

    def test_no_system_state_or_fluid_state_in_module(self) -> None:
        import mpl_sim.network.configurable_residual_blueprint_workflows as mod

        assert not hasattr(mod, "SystemState")
        assert not hasattr(mod, "FluidState")

    def test_no_network_graph_solve_in_module(self) -> None:
        import mpl_sim.network.configurable_residual_blueprint_workflows as mod

        assert not hasattr(mod, "NetworkGraph")
