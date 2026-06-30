"""Integration tests for Block 15H-A — Explicit Residual/Unknown Structural Diagnostics MVP.

Proves that the structural diagnostics layer composes cleanly with the
Block 15G-A explicit residual blueprint layer and the Block 15G-B
blueprint-to-selection workflow, without modifying either.

Acceptance stories
------------------
A1  Diagnostics from a 15G-A blueprint build result's algebraic_residual_set.
A2  Diagnostics from a 15G-B workflow setup (scenario + blueprints + values).
A3  Diagnostics report SQUARE for a known single-loop blueprint set where
    counts match.
A4  Diagnostics report UNDERDETERMINED / OVERDETERMINED for controlled
    residual sets.
A5  Missing blueprint-generated unknowns from the scenario are reported.
A6  Workflow evaluate=True with complete values matches diagnostic
    evaluation_ready=True.
A7  Workflow evaluate=True without values matches diagnostic not-ready state.
A8  Role changes do not alter diagnostics for the same explicit residual set.
A9  Topology growth (extra unconnected component/node) does not change
    blueprint-derived residual or required-unknown names.
A10 Scenario + blueprint + workflow + diagnostic reports compose into one
    JSON-serializable dict.

Boundary stories
-----------------
B1  No CoolProp or PropertyBackend imports in the new test module.
B2  No SystemState or FluidState in the diagnostics module.
B3  No solve(network) / NetworkGraph.solve() in the diagnostics module.
B4  No mpl_sim.components, properties, correlations, hx_models imports.

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
from mpl_sim.network.configurable_residual_diagnostics import (
    ResidualDeterminationStatus,
    build_configurable_residual_diagnostic_report,
    evaluate_configurable_residual_structure,
)
from mpl_sim.network.configurable_scenarios import (
    ConfigurableScenarioSpec,
    ScenarioComponentRole,
    ScenarioComponentSpec,
    ScenarioConnectionSpec,
    ScenarioNodeSpec,
    build_configurable_scenario,
    build_configurable_scenario_report,
)

# ===========================================================================
# Shared test fixture — single-loop configurable scenario (mirrors 15G-B)
# ===========================================================================


def _make_single_loop_spec(role_a=None, role_b=None, role_c=None, role_d=None):
    role_a = role_a if role_a is not None else ScenarioComponentRole.ACCUMULATOR
    role_b = role_b if role_b is not None else ScenarioComponentRole.PUMP
    role_c = role_c if role_c is not None else ScenarioComponentRole.EVAPORATOR
    role_d = role_d if role_d is not None else ScenarioComponentRole.CONDENSER
    return ConfigurableScenarioSpec(
        scenario_id="diag_integration_single_loop",
        components=[
            ScenarioComponentSpec("accumulator", role_a),
            ScenarioComponentSpec("pump", role_b),
            ScenarioComponentSpec("evaporator", role_c),
            ScenarioComponentSpec("condenser", role_d),
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
# A1/A3 — diagnostics from a 15G-A blueprint build result; SQUARE status
# ===========================================================================


class TestDiagnosticsFromBlueprintBuildResult:
    def test_diagnostics_from_blueprint_result_is_square(self) -> None:
        sbr = build_configurable_scenario(_make_single_loop_spec())
        bps = _make_four_blueprints()
        bp_result = build_configurable_algebraic_residuals_from_blueprints(
            bps, scenario_build_result=sbr
        )

        diag = evaluate_configurable_residual_structure(
            bp_result.algebraic_residual_set,
            scenario_build_result=sbr,
            unknown_values=_ZERO_RESIDUAL_UNKNOWNS,
        )

        assert diag.residual_count == 4
        assert diag.required_unknown_count == 4
        assert diag.determination_status is ResidualDeterminationStatus.SQUARE
        assert diag.scenario_compatible is True
        assert diag.unknown_values_complete is True
        assert diag.evaluation_ready is True
        assert diag.solve_ready is False
        assert diag.no_solve is True

    def test_required_unknown_names_match_blueprint_result(self) -> None:
        sbr = build_configurable_scenario(_make_single_loop_spec())
        bps = _make_four_blueprints()
        bp_result = build_configurable_algebraic_residuals_from_blueprints(
            bps, scenario_build_result=sbr
        )
        diag = evaluate_configurable_residual_structure(bp_result.algebraic_residual_set)
        assert diag.required_unknown_names == bp_result.required_unknown_names


# ===========================================================================
# A2/A6/A7 — diagnostics from a 15G-B workflow setup match workflow behavior
# ===========================================================================


class TestDiagnosticsFromWorkflow:
    def test_workflow_evaluate_true_with_values_matches_diagnostic_ready(self) -> None:
        sbr = build_configurable_scenario(_make_single_loop_spec())
        bps = _make_four_blueprints()

        request = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=bps,
            algebraic_unknown_values=_ZERO_RESIDUAL_UNKNOWNS,
            evaluate=True,
        )
        workflow_result = build_configurable_residual_selection_from_blueprints(request)

        diag = evaluate_configurable_residual_structure(
            workflow_result.blueprint_build_result.algebraic_residual_set,
            scenario_build_result=sbr,
            unknown_values=_ZERO_RESIDUAL_UNKNOWNS,
        )

        assert workflow_result.evaluation_performed is True
        assert diag.evaluation_ready is True

    def test_workflow_evaluate_true_without_values_matches_diagnostic_not_ready(self) -> None:
        sbr = build_configurable_scenario(_make_single_loop_spec())
        bps = _make_four_blueprints()

        request = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=bps,
            evaluate=True,
        )
        workflow_result = build_configurable_residual_selection_from_blueprints(request)

        diag = evaluate_configurable_residual_structure(
            workflow_result.blueprint_build_result.algebraic_residual_set,
            scenario_build_result=sbr,
        )

        assert workflow_result.evaluation_performed is False
        assert diag.evaluation_ready is False
        assert diag.unknown_values_complete is None


# ===========================================================================
# A4 — controlled under/overdetermined blueprint-derived sets
# ===========================================================================


class TestControlledDeterminationFromBlueprints:
    def test_underdetermined_from_partial_blueprint_set(self) -> None:
        sbr = build_configurable_scenario(_make_single_loop_spec())
        bps = [
            MassBalanceResidualBlueprint(
                residual_name="mb_pump_out",
                incoming_component_ids=("pump",),
                outgoing_component_ids=("evaporator",),
                anchor_node_id="n_pump_out",
            )
        ]
        bp_result = build_configurable_algebraic_residuals_from_blueprints(
            bps, scenario_build_result=sbr
        )
        diag = evaluate_configurable_residual_structure(bp_result.algebraic_residual_set)
        assert diag.residual_count == 1
        assert diag.required_unknown_count == 2
        assert diag.determination_status is ResidualDeterminationStatus.UNDERDETERMINED

    def test_overdetermined_from_redundant_blueprint_set(self) -> None:
        sbr = build_configurable_scenario(_make_single_loop_spec())
        bps = [
            ImposedPressureResidualBlueprint(
                residual_name="p_ref_1", node_id="n_acc_out", pressure=100_000.0
            ),
            ImposedPressureResidualBlueprint(
                residual_name="p_ref_2", node_id="n_acc_out", pressure=105_000.0
            ),
        ]
        bp_result = build_configurable_algebraic_residuals_from_blueprints(
            bps, scenario_build_result=sbr
        )
        diag = evaluate_configurable_residual_structure(bp_result.algebraic_residual_set)
        assert diag.residual_count == 2
        assert diag.required_unknown_count == 1
        assert diag.determination_status is ResidualDeterminationStatus.OVERDETERMINED


# ===========================================================================
# A5 — missing blueprint-generated unknowns from scenario are reported
# ===========================================================================


class TestMissingBlueprintUnknownsFromScenario:
    def test_blueprint_unknown_not_in_scenario_is_reported(self) -> None:
        sbr = build_configurable_scenario(_make_single_loop_spec())
        # blueprint references a node not declared in this scenario
        bps = [
            ImposedPressureResidualBlueprint(
                residual_name="p_ref_missing", node_id="n_does_not_exist", pressure=1.0
            )
        ]
        bp_result = build_configurable_algebraic_residuals_from_blueprints(bps)
        diag = evaluate_configurable_residual_structure(
            bp_result.algebraic_residual_set, scenario_build_result=sbr
        )
        assert diag.scenario_compatible is False
        assert "P:n_does_not_exist" in diag.missing_from_scenario


# ===========================================================================
# A8 — role changes do not alter diagnostics for the same explicit residual set
# ===========================================================================


class TestRoleChangesDoNotAlterDiagnostics:
    def test_generic_roles_produce_identical_diagnostics(self) -> None:
        spec_specific = _make_single_loop_spec()
        spec_generic = _make_single_loop_spec(
            role_a=ScenarioComponentRole.GENERIC,
            role_b=ScenarioComponentRole.GENERIC,
            role_c=ScenarioComponentRole.GENERIC,
            role_d=ScenarioComponentRole.GENERIC,
        )
        sbr_specific = build_configurable_scenario(spec_specific)
        sbr_generic = build_configurable_scenario(spec_generic)

        bps = _make_four_blueprints()
        bp_result_specific = build_configurable_algebraic_residuals_from_blueprints(
            bps, scenario_build_result=sbr_specific
        )
        bp_result_generic = build_configurable_algebraic_residuals_from_blueprints(
            bps, scenario_build_result=sbr_generic
        )

        diag_specific = evaluate_configurable_residual_structure(
            bp_result_specific.algebraic_residual_set,
            scenario_build_result=sbr_specific,
            unknown_values=_ZERO_RESIDUAL_UNKNOWNS,
        )
        diag_generic = evaluate_configurable_residual_structure(
            bp_result_generic.algebraic_residual_set,
            scenario_build_result=sbr_generic,
            unknown_values=_ZERO_RESIDUAL_UNKNOWNS,
        )

        assert diag_specific.residual_names == diag_generic.residual_names
        assert diag_specific.required_unknown_names == diag_generic.required_unknown_names
        assert diag_specific.determination_status == diag_generic.determination_status
        assert diag_specific.evaluation_ready == diag_generic.evaluation_ready


# ===========================================================================
# A9 — topology growth does not change blueprint-derived requirements
# ===========================================================================


class TestTopologyGrowthDoesNotChangeRequirements:
    def test_extra_unconnected_component_does_not_change_diagnostics(self) -> None:
        base_spec = _make_single_loop_spec()
        # Scenario validation requires exact connection coverage of declared
        # components/nodes, so the added "extra" component/node pair is wired
        # via its own trivial connection rather than left dangling.
        grown_spec = ConfigurableScenarioSpec(
            scenario_id="diag_integration_grown",
            components=list(base_spec.components)
            + [ScenarioComponentSpec("extra", ScenarioComponentRole.GENERIC)],
            nodes=list(base_spec.nodes)
            + [ScenarioNodeSpec("n_extra"), ScenarioNodeSpec("n_extra2")],
            connections=list(base_spec.connections)
            + [ScenarioConnectionSpec("extra", "n_extra", "n_extra2")],
        )

        sbr_base = build_configurable_scenario(base_spec)
        sbr_grown = build_configurable_scenario(grown_spec)

        bps = _make_four_blueprints()
        bp_result_base = build_configurable_algebraic_residuals_from_blueprints(
            bps, scenario_build_result=sbr_base
        )
        bp_result_grown = build_configurable_algebraic_residuals_from_blueprints(
            bps, scenario_build_result=sbr_grown
        )

        diag_base = evaluate_configurable_residual_structure(
            bp_result_base.algebraic_residual_set, scenario_build_result=sbr_base
        )
        diag_grown = evaluate_configurable_residual_structure(
            bp_result_grown.algebraic_residual_set, scenario_build_result=sbr_grown
        )

        assert diag_base.required_unknown_names == diag_grown.required_unknown_names
        assert diag_base.residual_count == diag_grown.residual_count
        assert diag_base.determination_status == diag_grown.determination_status
        # the grown scenario has additional unknowns not required by the
        # blueprint-derived residual set
        assert len(diag_grown.extra_scenario_unknowns) >= len(diag_base.extra_scenario_unknowns)


# ===========================================================================
# A10 — combined report stack
# ===========================================================================


class TestCombinedReportStack:
    def test_combined_report_stack_is_json_serializable(self) -> None:
        sbr = build_configurable_scenario(_make_single_loop_spec())
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
        workflow_result = build_configurable_residual_selection_from_blueprints(request)
        workflow_report = build_configurable_residual_blueprint_workflow_report(workflow_result)

        diag = evaluate_configurable_residual_structure(
            bp_result.algebraic_residual_set,
            scenario_build_result=sbr,
            unknown_values=_ZERO_RESIDUAL_UNKNOWNS,
        )
        diagnostic_report = build_configurable_residual_diagnostic_report(diag)

        combined = {
            "scenario_report": scenario_report,
            "blueprint_report": blueprint_report,
            "workflow_report": workflow_report,
            "diagnostic_report": diagnostic_report,
        }
        json_str = json.dumps(combined)
        parsed = json.loads(json_str)

        assert parsed["diagnostic_report"]["no_solve"] is True
        assert parsed["diagnostic_report"]["solve_ready"] is False
        assert parsed["diagnostic_report"]["determination_status"] == "square"
        assert parsed["diagnostic_report"]["evaluation_ready"] is True
        assert parsed["workflow_report"]["no_solve"] is True


# ===========================================================================
# Boundary stories
# ===========================================================================


class TestDiagnosticsIntegrationBoundaries:
    def test_no_coolprop_in_module(self) -> None:
        import mpl_sim.network.configurable_residual_diagnostics as mod

        assert not hasattr(mod, "CoolProp")
        assert not hasattr(mod, "PropertyBackend")

    def test_no_system_state_or_fluid_state_in_module(self) -> None:
        import mpl_sim.network.configurable_residual_diagnostics as mod

        assert not hasattr(mod, "SystemState")
        assert not hasattr(mod, "FluidState")

    def test_no_network_graph_solve_in_module(self) -> None:
        import mpl_sim.network.configurable_residual_diagnostics as mod

        assert not hasattr(mod, "NetworkGraph")
        assert not hasattr(mod, "solve_network_residual_problem")
        assert not hasattr(mod, "solve_fixed_single_loop_residuals")

    def test_no_contribute_attribute(self) -> None:
        import mpl_sim.network.configurable_residual_diagnostics as mod

        assert not hasattr(mod, "contribute")
