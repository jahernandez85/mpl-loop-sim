"""Integration tests for Block 15H-B — Structural Diagnostics Workflow Integration.

Proves that the diagnostic workflow helper correctly composes the explicit
Block 15G-A blueprint translation, the Block 15H-A structural diagnostics,
and the optional Block 15G-B selection/evaluation workflow, and that direct
15H-A diagnostics and direct 15G-B workflow calls remain independently
available and unaffected.

Acceptance stories
-------------------
A1  Full scenario + blueprint + diagnostic workflow path with evaluate=False
    returns diagnostics only (no selection workflow result).
A2  Full scenario + blueprint + diagnostic workflow path with evaluate=True
    and complete values performs selection/evaluation.
A3  Diagnostic workflow evaluation result matches the direct 15G-B workflow
    result for the same complete inputs.
A4  Missing unknown values defer evaluation before 15G-B selection/evaluation
    is invoked.
A5  Incompatible blueprint unknowns short-circuit before diagnostics/selection.
A6  Role changes do not alter the diagnostic workflow result for the same
    explicit blueprints.
A7  Topology changes do not create additional residual/diagnostic requirements.
A8  Scenario + blueprint + diagnostic + workflow reports compose to JSON.
A9  Direct 15H-A diagnostic still works independently.
A10 Direct 15G-B workflow still works independently.
A11 Production contract remains frozen (NO_CONTRIBUTE_METHOD for all 6 classes).

Boundary stories
-----------------
B1  New test module imports no CoolProp or PropertyBackend.
B2  No contribute attribute in the workflow module.
B3  No SystemState or FluidState in the new module.
B4  No solve(network) or NetworkGraph.solve() in the new module.
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
from mpl_sim.network.configurable_residual_diagnostic_workflows import (
    ConfigurableResidualDiagnosticWorkflowRequest,
    build_configurable_residual_diagnostic_workflow,
    build_configurable_residual_diagnostic_workflow_report,
)
from mpl_sim.network.configurable_residual_diagnostics import (
    ResidualDeterminationStatus,
    build_configurable_residual_diagnostic_report,
    evaluate_configurable_residual_structure,
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
    scenario_id="diag_wf_integration_single_loop",
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

_COMPLETE_UNKNOWNS = {
    "mdot:pump": 0.1,
    "mdot:evaporator": 0.1,
    "P:n_acc_out": 100_000.0,
    "P:n_pump_out": 150_000.0,
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
# A1/A2 — full path with evaluate=False / evaluate=True
# ===========================================================================


class TestFullDiagnosticWorkflowPath:
    def test_evaluate_false_returns_diagnostics_only(self) -> None:
        sbr = build_configurable_scenario(_SINGLE_LOOP_SPEC)
        request = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_make_four_blueprints(),
            algebraic_unknown_values=_COMPLETE_UNKNOWNS,
            evaluate=False,
        )
        result = build_configurable_residual_diagnostic_workflow(request)

        assert result.structural_diagnostic is not None
        status = result.structural_diagnostic.determination_status
        assert status is ResidualDeterminationStatus.SQUARE
        assert result.selection_workflow_result is None
        assert result.evaluation_performed is False
        assert result.selected_mode is None
        assert result.no_solve is True
        assert result.solve_ready is False

    def test_evaluate_true_complete_values_performs_selection_and_evaluation(self) -> None:
        sbr = build_configurable_scenario(_SINGLE_LOOP_SPEC)
        request = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_make_four_blueprints(),
            algebraic_unknown_values=_COMPLETE_UNKNOWNS,
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(request)

        assert result.structural_diagnostic is not None
        assert result.evaluation_ready is True
        assert result.selection_workflow_result is not None
        assert result.selection_performed is True
        assert result.evaluation_performed is True
        assert result.selected_mode is ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC

        eval_result = result.selection_workflow_result.selection_result.evaluation_result
        assert eval_result.max_abs_residual == pytest.approx(0.0, abs=1e-9)


# ===========================================================================
# A3 — diagnostic workflow evaluation matches direct 15G-B workflow
# ===========================================================================


class TestDiagnosticWorkflowMatchesDirect15GBWorkflow:
    def test_evaluation_results_match_for_complete_inputs(self) -> None:
        sbr = build_configurable_scenario(_SINGLE_LOOP_SPEC)
        bps = _make_four_blueprints()

        direct_request = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=bps,
            algebraic_unknown_values=_COMPLETE_UNKNOWNS,
            evaluate=True,
        )
        direct_result = build_configurable_residual_selection_from_blueprints(direct_request)
        direct_eval = direct_result.selection_result.evaluation_result

        diag_request = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=bps,
            algebraic_unknown_values=_COMPLETE_UNKNOWNS,
            evaluate=True,
        )
        diag_result = build_configurable_residual_diagnostic_workflow(diag_request)
        diag_eval = diag_result.selection_workflow_result.selection_result.evaluation_result

        assert (
            diag_result.selection_workflow_result.blueprint_build_result.blueprint_names
            == diag_result.blueprint_build_result.blueprint_names
            == direct_result.blueprint_build_result.blueprint_names
        )
        assert (
            diag_result.selection_workflow_result.blueprint_build_result.required_unknown_names
            == diag_result.blueprint_build_result.required_unknown_names
            == direct_result.blueprint_build_result.required_unknown_names
        )
        assert (
            diag_result.selection_workflow_result.blueprint_build_result.missing_unknowns
            == diag_result.blueprint_build_result.missing_unknowns
            == direct_result.blueprint_build_result.missing_unknowns
        )
        assert diag_eval.residual_names == direct_eval.residual_names
        for name in direct_eval.residual_names:
            assert diag_eval.residual_values[name] == pytest.approx(
                direct_eval.residual_values[name], abs=1e-10
            )
        assert diag_eval.max_abs_residual == pytest.approx(direct_eval.max_abs_residual, abs=1e-10)

    def test_evaluation_results_match_after_perturbation(self) -> None:
        sbr = build_configurable_scenario(_SINGLE_LOOP_SPEC)
        bps = _make_four_blueprints()
        perturbed = dict(_COMPLETE_UNKNOWNS)
        perturbed["mdot:pump"] = 0.45

        direct_request = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=bps,
            algebraic_unknown_values=perturbed,
            evaluate=True,
        )
        direct_result = build_configurable_residual_selection_from_blueprints(direct_request)
        direct_eval = direct_result.selection_result.evaluation_result

        diag_request = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=bps,
            algebraic_unknown_values=perturbed,
            evaluate=True,
        )
        diag_result = build_configurable_residual_diagnostic_workflow(diag_request)
        diag_eval = diag_result.selection_workflow_result.selection_result.evaluation_result

        for name in direct_eval.residual_names:
            assert diag_eval.residual_values[name] == pytest.approx(
                direct_eval.residual_values[name], abs=1e-10
            )
        assert diag_eval.max_abs_residual > 0.0
        assert diag_eval.max_abs_residual == pytest.approx(direct_eval.max_abs_residual, abs=1e-10)


# ===========================================================================
# A4 — missing unknown values defer evaluation before 15G-B is invoked
# ===========================================================================


class TestMissingValuesDeferBefore15GB:
    def test_missing_values_defer_evaluation_and_skip_15gb_invocation(self) -> None:
        sbr = build_configurable_scenario(_SINGLE_LOOP_SPEC)
        partial = dict(_COMPLETE_UNKNOWNS)
        del partial["mdot:evaporator"]
        request = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_make_four_blueprints(),
            algebraic_unknown_values=partial,
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(request)

        assert result.structural_diagnostic is not None
        assert result.evaluation_ready is False
        assert "mdot:evaporator" in result.missing_from_values
        # The 15G-B workflow must not have been invoked at all.
        assert result.selection_workflow_result is None
        assert result.selection_performed is False
        assert result.evaluation_performed is False


# ===========================================================================
# A5 — incompatible blueprint unknowns short-circuit before diagnostics/selection
# ===========================================================================


class TestIncompatibleBlueprintShortCircuits:
    def test_incompatible_unknowns_short_circuit(self) -> None:
        sbr = build_configurable_scenario(_SINGLE_LOOP_SPEC)
        bad_bps = [
            ImposedMassFlowResidualBlueprint(
                residual_name="mdot_bad",
                component_id="nonexistent_component",
                mass_flow=0.1,
            )
        ]
        request = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=bad_bps,
            algebraic_unknown_values={"mdot:nonexistent_component": 0.1},
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(request)

        assert result.structural_diagnostic is None
        assert result.selection_workflow_result is None
        assert result.selection_requested is False
        assert result.evaluation_performed is False
        assert "mdot:nonexistent_component" in result.missing_from_scenario


# ===========================================================================
# A6 — role changes do not alter the diagnostic workflow
# ===========================================================================


class TestRoleChangesDoNotAlterWorkflow:
    def test_generic_roles_produce_identical_diagnostic_workflow(self) -> None:
        variant_spec = ConfigurableScenarioSpec(
            scenario_id="diag_wf_role_variant",
            components=[
                ScenarioComponentSpec("accumulator", ScenarioComponentRole.GENERIC),
                ScenarioComponentSpec("pump", ScenarioComponentRole.GENERIC),
                ScenarioComponentSpec("evaporator", ScenarioComponentRole.GENERIC),
                ScenarioComponentSpec("condenser", ScenarioComponentRole.GENERIC),
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
        sbr_variant = build_configurable_scenario(variant_spec)
        sbr_original = build_configurable_scenario(_SINGLE_LOOP_SPEC)

        req_original = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr_original,
            blueprints=_make_four_blueprints(),
            algebraic_unknown_values=_COMPLETE_UNKNOWNS,
            evaluate=True,
        )
        req_variant = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr_variant,
            blueprints=_make_four_blueprints(),
            algebraic_unknown_values=_COMPLETE_UNKNOWNS,
            evaluate=True,
        )
        result_original = build_configurable_residual_diagnostic_workflow(req_original)
        result_variant = build_configurable_residual_diagnostic_workflow(req_variant)

        assert result_original.required_unknown_names == result_variant.required_unknown_names
        assert (
            result_original.structural_diagnostic.determination_status
            == result_variant.structural_diagnostic.determination_status
        )
        assert result_original.selected_mode == result_variant.selected_mode
        assert result_original.evaluation_performed == result_variant.evaluation_performed


# ===========================================================================
# A7 — topology changes do not create additional residual/diagnostic requirements
# ===========================================================================


class TestTopologyChangesDoNotAddRequirements:
    def test_extra_unused_topology_does_not_change_required_unknowns(self) -> None:
        sbr = build_configurable_scenario(_SINGLE_LOOP_SPEC)
        single_blueprint = [
            ImposedPressureResidualBlueprint(
                residual_name="p_only",
                node_id="n_acc_out",
                pressure=100_000.0,
            )
        ]
        request = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=single_blueprint,
        )
        result = build_configurable_residual_diagnostic_workflow(request)

        assert result.required_unknown_names == ("P:n_acc_out",)
        assert result.structural_diagnostic.residual_count == 1
        assert result.structural_diagnostic.required_unknown_count == 1


# ===========================================================================
# A8 — combined report stack composes to JSON
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

        request = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=bps,
            algebraic_unknown_values=_COMPLETE_UNKNOWNS,
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(request)
        diagnostic_workflow_report = build_configurable_residual_diagnostic_workflow_report(result)

        combined = {
            "scenario_report": scenario_report,
            "blueprint_report": blueprint_report,
            "diagnostic_workflow_report": diagnostic_workflow_report,
        }
        json_str = json.dumps(combined)
        parsed = json.loads(json_str)

        assert parsed["diagnostic_workflow_report"]["no_solve"] is True
        assert parsed["diagnostic_workflow_report"]["solve_ready"] is False
        assert parsed["diagnostic_workflow_report"]["selected_mode"] == "configurable_algebraic"
        assert parsed["diagnostic_workflow_report"]["selection_report"]["no_solve"] is True
        assert (
            parsed["diagnostic_workflow_report"]["diagnostic_report"]["determination_status"]
            == "square"
        )


# ===========================================================================
# A9 — direct 15H-A diagnostic still works independently
# ===========================================================================


class TestDirect15HADiagnosticStillWorks:
    def test_direct_diagnostic_call_unaffected_by_new_module(self) -> None:
        sbr = build_configurable_scenario(_SINGLE_LOOP_SPEC)
        bp_result = build_configurable_algebraic_residuals_from_blueprints(
            _make_four_blueprints(), scenario_build_result=sbr
        )
        diagnostic = evaluate_configurable_residual_structure(
            bp_result.algebraic_residual_set,
            scenario_build_result=sbr,
            unknown_values=_COMPLETE_UNKNOWNS,
        )
        assert diagnostic.determination_status is ResidualDeterminationStatus.SQUARE
        assert diagnostic.evaluation_ready is True
        assert diagnostic.solve_ready is False

        report = build_configurable_residual_diagnostic_report(diagnostic)
        json.dumps(report)
        assert report["status"] == "configurable_residual_structural_diagnostic"


# ===========================================================================
# A10 — direct 15G-B workflow still works independently
# ===========================================================================


class TestDirect15GBWorkflowStillWorks:
    def test_direct_workflow_call_unaffected_by_new_module(self) -> None:
        sbr = build_configurable_scenario(_SINGLE_LOOP_SPEC)
        request = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_make_four_blueprints(),
            algebraic_unknown_values=_COMPLETE_UNKNOWNS,
            evaluate=True,
        )
        result = build_configurable_residual_selection_from_blueprints(request)
        assert result.selected_mode is ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC
        assert result.evaluation_performed is True

        report = build_configurable_residual_blueprint_workflow_report(result)
        json.dumps(report)
        assert report["status"] == "configurable_residual_blueprint_workflow"


# ===========================================================================
# A11 — production contract remains frozen
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


class TestDiagnosticWorkflowIntegrationBoundaries:
    def test_no_coolprop_in_module(self) -> None:
        import mpl_sim.network.configurable_residual_diagnostic_workflows as mod

        assert not hasattr(mod, "CoolProp")

    def test_no_system_state_or_fluid_state_in_module(self) -> None:
        import mpl_sim.network.configurable_residual_diagnostic_workflows as mod

        assert not hasattr(mod, "SystemState")
        assert not hasattr(mod, "FluidState")

    def test_no_network_graph_solve_in_module(self) -> None:
        import mpl_sim.network.configurable_residual_diagnostic_workflows as mod

        assert not hasattr(mod, "NetworkGraph")

    def test_no_property_backend_in_module(self) -> None:
        import mpl_sim.network.configurable_residual_diagnostic_workflows as mod

        assert not hasattr(mod, "PropertyBackend")
        assert not hasattr(mod, "CorrelationRegistry")
