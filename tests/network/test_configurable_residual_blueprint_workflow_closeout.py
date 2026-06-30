"""Acceptance / closeout tests for Block 15G-C.

Proves that the complete Block 15G explicit configurable residual blueprint
stack works coherently end-to-end across:
  - 15G-A explicit residual blueprint declarations and blueprint-to-algebraic
    residual assembly
  - 15G-B explicit blueprint-to-selection workflow
  - 15F-A configurable algebraic residual declarations/evaluation
  - 15F-B CONFIGURABLE_ALGEBRAIC residual-selection path
  - 15E configurable scenario declaration and residual-selection stack

This block is tests and documentation only. It does NOT add runtime modules
or modify runtime behavior.

Acceptance stories
-------------------
1   Full explicit workflow path at a known zero-residual point.
2   Perturbation proves real algebraic evaluation (nonzero residuals).
3   Evaluation remains optional (evaluate=False keeps selection pure).
4   Missing explicit unknown values defer evaluation (no hidden defaults).
5   Incompatible blueprint unknowns short-circuit selection.
6   No blueprints means no auto-generation (empty list rejected).
7   Roles and component type labels remain metadata only.
8   Topology changes do not create additional residuals.
9   Report stack is composable and JSON-serializable.
10  Existing lower layers remain independent of the workflow helper.
11  Production contract remains frozen.

Boundary / negative acceptance tests
--------------------------------------
B1  No CoolProp, PropertyBackend, or CorrelationRegistry imports.
B2  No HX model imports/calls.
B3  No production component execution imports.
B4  No SystemState or FluidState.
B5  No production contribute( calls; no .contribute(; no def contribute.
B6  No component_type or role-based physics dispatch.
B7  No automatic blueprint/residual/closure inference from role or topology.
B8  No generic solve(network), NetworkGraph.solve(), or named solvers.
B9  No file writing / report output.
B10 No root/least-squares solving.

These tests do NOT:
  - Call any solver or root-finder.
  - Execute production component physics.
  - Call CoolProp, PropertyBackend, or correlations.
  - Assemble SystemState or construct FluidState.
  - Write files, use pandas, or use numpy.
  - Infer blueprints or residuals from roles or topology.
"""

from __future__ import annotations

import importlib
import inspect
import json

import pytest

from mpl_sim.network.configurable_algebraic_residuals import (
    evaluate_configurable_algebraic_residuals,
)
from mpl_sim.network.configurable_residual_blueprint_workflows import (
    ConfigurableResidualBlueprintWorkflowRequest,
    ConfigurableResidualBlueprintWorkflowResult,
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
from mpl_sim.network.configurable_residual_selection import (
    ConfigurableResidualMode,
    ConfigurableResidualSelectionRequest,
    select_configurable_residual_strategy,
)
from mpl_sim.network.configurable_scenarios import (
    ConfigurableScenarioBuildResult,
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

# Modules loaded once for source inspection.
_WORKFLOW_MOD = importlib.import_module("mpl_sim.network.configurable_residual_blueprint_workflows")
_BLUEPRINT_MOD = importlib.import_module("mpl_sim.network.configurable_residual_blueprints")

# ---------------------------------------------------------------------------
# Shared scenario / blueprint fixtures
# ---------------------------------------------------------------------------
#
# 4-component single-loop scenario:
#   Components : accumulator, pump, evaporator, condenser
#   Nodes      : n_acc_out, n_pump_out, n_evap_out, n_cond_out
#
# Consistent algebraic point:
#   mdot_imposed = 0.1 kg/s
#   P_acc_out    = 100_000 Pa (imposed reference)
#   P_pump_out   = 150_000 Pa (P_acc_out - delta_p, delta_p = -50_000 i.e. pump rise)


def _make_spec(
    accumulator_role: ScenarioComponentRole = ScenarioComponentRole.ACCUMULATOR,
    pump_role: ScenarioComponentRole = ScenarioComponentRole.PUMP,
    evap_role: ScenarioComponentRole = ScenarioComponentRole.EVAPORATOR,
    cond_role: ScenarioComponentRole = ScenarioComponentRole.CONDENSER,
    scenario_id: str = "gc_closeout",
) -> ConfigurableScenarioSpec:
    return ConfigurableScenarioSpec(
        scenario_id=scenario_id,
        components=(
            ScenarioComponentSpec("accumulator", accumulator_role),
            ScenarioComponentSpec("pump", pump_role),
            ScenarioComponentSpec("evaporator", evap_role),
            ScenarioComponentSpec("condenser", cond_role),
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


def _build_scenario(
    accumulator_role: ScenarioComponentRole = ScenarioComponentRole.ACCUMULATOR,
    pump_role: ScenarioComponentRole = ScenarioComponentRole.PUMP,
    evap_role: ScenarioComponentRole = ScenarioComponentRole.EVAPORATOR,
    cond_role: ScenarioComponentRole = ScenarioComponentRole.CONDENSER,
    scenario_id: str = "gc_closeout",
) -> ConfigurableScenarioBuildResult:
    return build_configurable_scenario(
        _make_spec(accumulator_role, pump_role, evap_role, cond_role, scenario_id)
    )


def _four_blueprints() -> list:
    return [
        MassBalanceResidualBlueprint(
            residual_name="mb_pump_out",
            incoming_component_ids=("pump",),
            outgoing_component_ids=("evaporator",),
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


_ZERO_UV: dict[str, float] = {
    "mdot:pump": 0.1,
    "mdot:evaporator": 0.1,
    "P:n_acc_out": 100_000.0,
    "P:n_pump_out": 150_000.0,
}

_PERTURBED_UV: dict[str, float] = {
    **_ZERO_UV,
    "mdot:pump": 0.4,
}


# ---------------------------------------------------------------------------
# Story 1 — Full explicit workflow path at zero residual point
# ---------------------------------------------------------------------------


class TestStory1FullWorkflowPathAtZeroResidualPoint:
    def setup_method(self) -> None:
        self.sbr = _build_scenario()
        self.bps = _four_blueprints()

    def test_request_construction_and_run(self) -> None:
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert isinstance(result, ConfigurableResidualBlueprintWorkflowResult)

    def test_blueprint_build_result_is_compatible(self) -> None:
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert result.blueprint_build_result.scenario_is_compatible is True

    def test_selected_mode_is_configurable_algebraic(self) -> None:
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert result.selected_mode is ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC

    def test_evaluation_occurred(self) -> None:
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert result.evaluation_performed is True

    def test_residuals_zero_at_consistent_point(self) -> None:
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        eval_r = result.selection_result.evaluation_result
        for name, val in eval_r.residual_values.items():
            assert abs(val) < 1e-9, f"residual {name!r} should be zero; got {val}"
        assert eval_r.max_abs_residual < 1e-9

    def test_report_flags_match_acceptance_requirements(self) -> None:
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        report = build_configurable_residual_blueprint_workflow_report(result)
        assert report["no_solve"] is True
        assert report["blueprints_inferred_from_roles"] is False
        assert report["blueprints_inferred_from_topology"] is False
        assert report["residuals_inferred_from_roles"] is False
        assert report["residuals_inferred_from_topology"] is False
        assert report["closures_inferred_from_roles"] is False
        assert report["production_components_executed"] is False


# ---------------------------------------------------------------------------
# Story 2 — Perturbation proves real algebraic evaluation
# ---------------------------------------------------------------------------


class TestStory2PerturbationProvesRealEvaluation:
    def setup_method(self) -> None:
        self.sbr = _build_scenario(scenario_id="gc_story2")
        self.bps = _four_blueprints()

    def test_perturbed_gives_nonzero_residual(self) -> None:
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_PERTURBED_UV,
            evaluate=True,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        eval_r = result.selection_result.evaluation_result
        assert eval_r.max_abs_residual > 0.0

    def test_norm_larger_than_zero_point(self) -> None:
        req_zero = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        req_perturbed = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_PERTURBED_UV,
            evaluate=True,
        )
        r_zero = build_configurable_residual_selection_from_blueprints(req_zero)
        r_perturbed = build_configurable_residual_selection_from_blueprints(req_perturbed)
        assert (
            r_perturbed.selection_result.evaluation_result.l2_norm
            > r_zero.selection_result.evaluation_result.l2_norm
        )

    def test_no_solve_attempted_on_perturbation(self) -> None:
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_PERTURBED_UV,
            evaluate=True,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert result.no_solve is True
        assert not hasattr(result, "converged")
        assert not hasattr(result, "iteration_count")


# ---------------------------------------------------------------------------
# Story 3 — Evaluation remains optional
# ---------------------------------------------------------------------------


class TestStory3EvaluationRemainsOptional:
    def setup_method(self) -> None:
        self.sbr = _build_scenario(scenario_id="gc_story3")
        self.bps = _four_blueprints()

    def test_compatibility_true_with_evaluate_false(self) -> None:
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=False,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert result.blueprint_build_result.scenario_is_compatible is True

    def test_selection_exists_with_evaluate_false(self) -> None:
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=False,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert result.selection_result is not None
        assert result.selected_mode is ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC

    def test_evaluation_not_performed(self) -> None:
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=False,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert result.evaluation_performed is False
        assert result.selection_result.evaluation_result is None

    def test_deferred_reason_is_clear(self) -> None:
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=False,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert result.deferred_or_incompatibility_reason != ""

    def test_no_residual_values_reported_as_evaluated(self) -> None:
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=False,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        report = build_configurable_residual_blueprint_workflow_report(result)
        assert report["evaluation_performed"] is False
        sel_report = report["selection_report"]
        assert sel_report["evaluation"]["performed"] is False


# ---------------------------------------------------------------------------
# Story 4 — Missing explicit unknown values defer evaluation
# ---------------------------------------------------------------------------


class TestStory4MissingUnknownValuesDeferEvaluation:
    def setup_method(self) -> None:
        self.sbr = _build_scenario(scenario_id="gc_story4")
        self.bps = _four_blueprints()

    def test_compatibility_true_without_values(self) -> None:
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            evaluate=True,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert result.blueprint_build_result.scenario_is_compatible is True

    def test_selection_exists_without_values(self) -> None:
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            evaluate=True,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert result.selection_result is not None

    def test_evaluation_deferred_without_values(self) -> None:
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            evaluate=True,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert result.evaluation_performed is False
        assert result.selection_result.evaluation_deferred is True

    def test_no_solve_or_fallback_values_used(self) -> None:
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            evaluate=True,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert result.no_solve is True
        assert result.selection_result.evaluation_result is None


# ---------------------------------------------------------------------------
# Story 5 — Incompatible blueprint unknowns short-circuit selection
# ---------------------------------------------------------------------------


class TestStory5IncompatibleUnknownsShortCircuit:
    def setup_method(self) -> None:
        self.sbr = _build_scenario(scenario_id="gc_story5")
        self.bad_bps = [
            ImposedMassFlowResidualBlueprint(
                residual_name="mdot_bad",
                component_id="nonexistent_component",
                mass_flow=0.1,
            )
        ]

    def test_blueprint_compatibility_false(self) -> None:
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bad_bps,
            algebraic_unknown_values={"mdot:nonexistent_component": 0.1},
            evaluate=True,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert result.blueprint_build_result.scenario_is_compatible is False

    def test_selection_result_is_none(self) -> None:
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bad_bps,
            algebraic_unknown_values={"mdot:nonexistent_component": 0.1},
            evaluate=True,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert result.selection_result is None

    def test_selected_mode_is_none(self) -> None:
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bad_bps,
            algebraic_unknown_values={"mdot:nonexistent_component": 0.1},
            evaluate=True,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert result.selected_mode is None

    def test_evaluation_not_performed(self) -> None:
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bad_bps,
            algebraic_unknown_values={"mdot:nonexistent_component": 0.1},
            evaluate=True,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert result.evaluation_performed is False

    def test_missing_unknowns_are_deterministic(self) -> None:
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bad_bps,
            algebraic_unknown_values={"mdot:nonexistent_component": 0.1},
            evaluate=True,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert result.missing_unknowns == ("mdot:nonexistent_component",)

    def test_no_fallback_to_other_modes(self) -> None:
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bad_bps,
            algebraic_unknown_values={"mdot:nonexistent_component": 0.1},
            evaluate=True,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert result.selected_mode is not ConfigurableResidualMode.DECLARATION_ONLY
        assert result.selected_mode is not ConfigurableResidualMode.CLOSURE_ONLY
        assert result.selected_mode is not ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC
        assert result.selected_mode is None


# ---------------------------------------------------------------------------
# Story 6 — No blueprints means no auto-generation
# ---------------------------------------------------------------------------


class TestStory6NoBlueprintsMeansNoAutoGeneration:
    def test_empty_blueprint_list_rejected_by_15ga_builder(self) -> None:
        sbr = _build_scenario(scenario_id="gc_story6")
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=[],
        )
        with pytest.raises(ValueError, match="must not be empty"):
            build_configurable_residual_selection_from_blueprints(req)

    def test_no_blueprint_generated_from_scenario_topology(self) -> None:
        sbr = _build_scenario(scenario_id="gc_story6b")
        # The scenario has components and nodes but, with no blueprints
        # supplied, the 15G-A builder must reject construction outright
        # rather than synthesizing blueprints from the scenario graph.
        with pytest.raises(ValueError):
            build_configurable_algebraic_residuals_from_blueprints([], scenario_build_result=sbr)


# ---------------------------------------------------------------------------
# Story 7 — Roles and component type labels remain metadata only
# ---------------------------------------------------------------------------


class TestStory7RolesRemainMetadataOnly:
    def test_specific_and_generic_roles_give_equivalent_results(self) -> None:
        sbr_specific = _build_scenario(scenario_id="gc_story7_specific")
        sbr_generic = _build_scenario(
            accumulator_role=ScenarioComponentRole.GENERIC,
            pump_role=ScenarioComponentRole.GENERIC,
            evap_role=ScenarioComponentRole.GENERIC,
            cond_role=ScenarioComponentRole.GENERIC,
            scenario_id="gc_story7_generic",
        )
        bps = _four_blueprints()

        req_specific = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr_specific,
            blueprints=bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        req_generic = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr_generic,
            blueprints=bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        r_specific = build_configurable_residual_selection_from_blueprints(req_specific)
        r_generic = build_configurable_residual_selection_from_blueprints(req_generic)

        assert r_specific.selected_mode == r_generic.selected_mode
        assert (
            r_specific.selection_result.evaluation_result.residual_values
            == r_generic.selection_result.evaluation_result.residual_values
        )

    def test_role_like_component_id_strings_remain_identifiers_only(self) -> None:
        sbr = _build_scenario(scenario_id="gc_story7_idstring")
        bp = ImposedMassFlowResidualBlueprint(
            residual_name="mdot_pump_label",
            component_id="pump",
            mass_flow=0.1,
        )
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=[bp],
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        # The translation is purely identifier-based: "pump" only ever
        # becomes the string "mdot:pump"; no physical model is attached.
        assert result.required_unknown_names == ("mdot:pump",)
        assert result.blueprint_build_result.scenario_is_compatible is True

    def test_condenser_labeled_component_id_no_physics_dispatch(self) -> None:
        sbr = _build_scenario(scenario_id="gc_story7_condenser_label")
        bp = ImposedMassFlowResidualBlueprint(
            residual_name="mdot_condenser_label",
            component_id="condenser",
            mass_flow=0.05,
        )
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=[bp],
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert result.required_unknown_names == ("mdot:condenser",)
        assert result.blueprint_build_result.scenario_is_compatible is True


# ---------------------------------------------------------------------------
# Story 8 — Topology changes do not create additional residuals
# ---------------------------------------------------------------------------


class TestStory8TopologyChangesDoNotCreateResiduals:
    def test_same_blueprints_different_topology_give_same_residual_names(self) -> None:
        spec_a = ConfigurableScenarioSpec(
            scenario_id="gc_story8_a",
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
        # Same component/node set, with an additional branch spec — a
        # structural change unrelated to the explicit blueprint declarations.
        spec_b = ConfigurableScenarioSpec(
            scenario_id="gc_story8_b",
            components=(
                ScenarioComponentSpec("accumulator", ScenarioComponentRole.ACCUMULATOR),
                ScenarioComponentSpec("pump", ScenarioComponentRole.PUMP),
                ScenarioComponentSpec("evaporator", ScenarioComponentRole.EVAPORATOR),
                ScenarioComponentSpec("condenser", ScenarioComponentRole.CONDENSER),
                ScenarioComponentSpec("extra_branch", ScenarioComponentRole.GENERIC),
            ),
            nodes=(
                ScenarioNodeSpec("n_acc_out"),
                ScenarioNodeSpec("n_pump_out"),
                ScenarioNodeSpec("n_evap_out"),
                ScenarioNodeSpec("n_cond_out"),
                ScenarioNodeSpec("n_extra_out"),
            ),
            connections=(
                ScenarioConnectionSpec("accumulator", "n_cond_out", "n_acc_out"),
                ScenarioConnectionSpec("pump", "n_acc_out", "n_pump_out"),
                ScenarioConnectionSpec("evaporator", "n_pump_out", "n_evap_out"),
                ScenarioConnectionSpec("condenser", "n_evap_out", "n_cond_out"),
                ScenarioConnectionSpec("extra_branch", "n_pump_out", "n_extra_out"),
            ),
        )
        sbr_a = build_configurable_scenario(spec_a)
        sbr_b = build_configurable_scenario(spec_b)
        bps = _four_blueprints()

        bp_result_a = build_configurable_algebraic_residuals_from_blueprints(
            bps, scenario_build_result=sbr_a
        )
        bp_result_b = build_configurable_algebraic_residuals_from_blueprints(
            bps, scenario_build_result=sbr_b
        )

        assert bp_result_a.blueprint_names == bp_result_b.blueprint_names
        assert bp_result_a.required_unknown_names == bp_result_b.required_unknown_names
        assert (
            bp_result_a.algebraic_residual_set.residual_names
            == bp_result_b.algebraic_residual_set.residual_names
        )

    def test_topology_richer_scenario_does_not_add_unknown_requirements(self) -> None:
        # sbr_b above has more nodes/components than the blueprints reference;
        # the additional topology must not leak into required_unknown_names.
        spec_b = ConfigurableScenarioSpec(
            scenario_id="gc_story8_c",
            components=(
                ScenarioComponentSpec("accumulator", ScenarioComponentRole.ACCUMULATOR),
                ScenarioComponentSpec("pump", ScenarioComponentRole.PUMP),
                ScenarioComponentSpec("evaporator", ScenarioComponentRole.EVAPORATOR),
                ScenarioComponentSpec("condenser", ScenarioComponentRole.CONDENSER),
                ScenarioComponentSpec("extra_branch", ScenarioComponentRole.GENERIC),
            ),
            nodes=(
                ScenarioNodeSpec("n_acc_out"),
                ScenarioNodeSpec("n_pump_out"),
                ScenarioNodeSpec("n_evap_out"),
                ScenarioNodeSpec("n_cond_out"),
                ScenarioNodeSpec("n_extra_out"),
            ),
            connections=(
                ScenarioConnectionSpec("accumulator", "n_cond_out", "n_acc_out"),
                ScenarioConnectionSpec("pump", "n_acc_out", "n_pump_out"),
                ScenarioConnectionSpec("evaporator", "n_pump_out", "n_evap_out"),
                ScenarioConnectionSpec("condenser", "n_evap_out", "n_cond_out"),
                ScenarioConnectionSpec("extra_branch", "n_pump_out", "n_extra_out"),
            ),
        )
        sbr_b = build_configurable_scenario(spec_b)
        bps = [ImposedPressureResidualBlueprint("p_only", "n_acc_out", 1e5)]
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr_b,
            blueprints=bps,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert result.required_unknown_names == ("P:n_acc_out",)
        assert result.blueprint_build_result.blueprint_count == 1


# ---------------------------------------------------------------------------
# Story 9 — Report stack is composable and JSON-serializable
# ---------------------------------------------------------------------------


class TestStory9ReportStackComposableAndSerializable:
    def setup_method(self) -> None:
        self.sbr = _build_scenario(scenario_id="gc_story9")
        self.bps = _four_blueprints()

    def test_combined_report_stack_is_json_serializable(self) -> None:
        scenario_report = build_configurable_scenario_report(self.sbr)

        bp_result = build_configurable_algebraic_residuals_from_blueprints(
            self.bps, scenario_build_result=self.sbr
        )
        blueprint_report = build_configurable_residual_blueprint_report(bp_result)

        direct_eval = evaluate_configurable_algebraic_residuals(
            bp_result.algebraic_residual_set, _ZERO_UV
        )
        from mpl_sim.network.configurable_algebraic_residuals import (
            build_configurable_algebraic_residual_report,
        )

        algebraic_report = build_configurable_algebraic_residual_report(direct_eval)

        selection_req = ConfigurableResidualSelectionRequest(
            build_result=self.sbr,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=bp_result.algebraic_residual_set,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        from mpl_sim.network.configurable_residual_selection import (
            build_configurable_residual_selection_report,
        )

        selection_result = select_configurable_residual_strategy(selection_req)
        selection_report = build_configurable_residual_selection_report(selection_result)

        workflow_req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        workflow_result = build_configurable_residual_selection_from_blueprints(workflow_req)
        workflow_report = build_configurable_residual_blueprint_workflow_report(workflow_result)

        combined: dict[str, object] = {
            "block": "15G-C",
            "scenario_report": scenario_report,
            "blueprint_report": blueprint_report,
            "algebraic_residual_report": algebraic_report,
            "selection_report": selection_report,
            "workflow_report": workflow_report,
        }
        serialized = json.dumps(combined)
        parsed = json.loads(serialized)
        assert isinstance(serialized, str)
        assert parsed["block"] == "15G-C"

    def test_combined_report_says_no_solve_throughout(self) -> None:
        scenario_report = build_configurable_scenario_report(self.sbr)
        bp_result = build_configurable_algebraic_residuals_from_blueprints(
            self.bps, scenario_build_result=self.sbr
        )
        blueprint_report = build_configurable_residual_blueprint_report(bp_result)

        workflow_req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        workflow_result = build_configurable_residual_selection_from_blueprints(workflow_req)
        workflow_report = build_configurable_residual_blueprint_workflow_report(workflow_result)

        assert scenario_report.get("no_solve") is True
        assert blueprint_report.get("no_solve") is True
        assert workflow_report.get("no_solve") is True
        assert workflow_report["selection_report"]["no_solve"] is True

    def test_no_file_writing_smoke_test(self) -> None:
        scenario_report = build_configurable_scenario_report(self.sbr)
        bp_result = build_configurable_algebraic_residuals_from_blueprints(
            self.bps, scenario_build_result=self.sbr
        )
        blueprint_report = build_configurable_residual_blueprint_report(bp_result)
        assert isinstance(scenario_report, dict)
        assert isinstance(blueprint_report, dict)


# ---------------------------------------------------------------------------
# Story 10 — Existing lower layers remain independent
# ---------------------------------------------------------------------------


class TestStory10LowerLayersRemainIndependent:
    def setup_method(self) -> None:
        self.sbr = _build_scenario(scenario_id="gc_story10")
        self.bps = _four_blueprints()

    def test_direct_15ga_blueprint_build_works_without_workflow(self) -> None:
        bp_result = build_configurable_algebraic_residuals_from_blueprints(
            self.bps, scenario_build_result=self.sbr
        )
        assert bp_result.scenario_is_compatible is True
        assert bp_result.blueprint_count == 4

    def test_direct_15fa_evaluation_works_from_blueprint_build_result(self) -> None:
        bp_result = build_configurable_algebraic_residuals_from_blueprints(
            self.bps, scenario_build_result=self.sbr
        )
        direct_eval = evaluate_configurable_algebraic_residuals(
            bp_result.algebraic_residual_set, _ZERO_UV
        )
        assert direct_eval.max_abs_residual < 1e-9

    def test_direct_15fb_selection_works_manually(self) -> None:
        bp_result = build_configurable_algebraic_residuals_from_blueprints(
            self.bps, scenario_build_result=self.sbr
        )
        req = ConfigurableResidualSelectionRequest(
            build_result=self.sbr,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=bp_result.algebraic_residual_set,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        direct_selection = select_configurable_residual_strategy(req)
        assert direct_selection.selected_mode is ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC
        assert direct_selection.evaluation_performed is True

    def test_workflow_results_match_direct_lower_layer_path(self) -> None:
        bp_result = build_configurable_algebraic_residuals_from_blueprints(
            self.bps, scenario_build_result=self.sbr
        )
        direct_eval = evaluate_configurable_algebraic_residuals(
            bp_result.algebraic_residual_set, _PERTURBED_UV
        )

        workflow_req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_PERTURBED_UV,
            evaluate=True,
        )
        workflow_result = build_configurable_residual_selection_from_blueprints(workflow_req)
        workflow_eval = workflow_result.selection_result.evaluation_result

        assert workflow_eval.residual_names == direct_eval.residual_names
        for name in direct_eval.residual_names:
            assert workflow_eval.residual_values[name] == pytest.approx(
                direct_eval.residual_values[name], abs=1e-10
            )
        assert workflow_eval.max_abs_residual == pytest.approx(
            direct_eval.max_abs_residual, abs=1e-10
        )


# ---------------------------------------------------------------------------
# Story 11 — Production contract remains frozen
# ---------------------------------------------------------------------------


class TestStory11ProductionContractFrozen:
    def test_all_six_have_no_contribute_method(self) -> None:
        results = inspect_known_production_component_contracts()
        for r in results:
            assert (
                r.status is ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD
            ), f"{r.class_name} unexpectedly has contribute method"

    def test_class_names_include_all_six(self) -> None:
        results = inspect_known_production_component_contracts()
        names = {r.class_name for r in results}
        assert "Component" in names
        assert "Pipe" in names
        assert "PumpComponent" in names
        assert "AccumulatorComponent" in names
        assert "EvaporatorComponent" in names
        assert "CondenserComponent" in names

    def test_exactly_six_production_classes_inspected(self) -> None:
        results = inspect_known_production_component_contracts()
        assert len(results) == 6


# ---------------------------------------------------------------------------
# Boundary / negative acceptance tests
# ---------------------------------------------------------------------------


def _import_lines(mod: object) -> str:
    """Return only import-statement lines from a module's source.

    Module docstrings document "MUST NOT" constraints using the very terms
    checked here; restricting to import lines avoids false positives from
    those documentation comments.
    """
    src = inspect.getsource(mod)
    lines = [
        ln.strip()
        for ln in src.splitlines()
        if ln.strip().startswith("import ") or ln.strip().startswith("from ")
    ]
    return "\n".join(lines)


class TestBoundaryNegativeAcceptance:
    """Architecture boundary checks proving Block 15G-C introduces no new

    runtime modules and that the existing 15G-A/15G-B modules still respect
    every architecture invariant. Source-level checks scan only import lines
    or specific function source, not full module source, to avoid docstring
    false positives.
    """

    # B1 — no CoolProp / PropertyBackend / CorrelationRegistry

    def test_b1_workflow_module_no_coolprop_import(self) -> None:
        imports = _import_lines(_WORKFLOW_MOD)
        assert "CoolProp" not in imports
        assert not hasattr(_WORKFLOW_MOD, "CoolProp")

    def test_b1_blueprint_module_no_coolprop_import(self) -> None:
        imports = _import_lines(_BLUEPRINT_MOD)
        assert "CoolProp" not in imports
        assert not hasattr(_BLUEPRINT_MOD, "CoolProp")

    def test_b1_no_property_backend_import(self) -> None:
        for mod in (_WORKFLOW_MOD, _BLUEPRINT_MOD):
            imports = _import_lines(mod)
            assert "PropertyBackend" not in imports
            assert not hasattr(mod, "PropertyBackend")

    def test_b1_no_correlation_registry_import(self) -> None:
        for mod in (_WORKFLOW_MOD, _BLUEPRINT_MOD):
            imports = _import_lines(mod)
            assert "CorrelationRegistry" not in imports
            assert not hasattr(mod, "CorrelationRegistry")

    def test_b1_no_mpl_sim_properties_or_correlations_import(self) -> None:
        for mod in (_WORKFLOW_MOD, _BLUEPRINT_MOD):
            imports = _import_lines(mod)
            assert "mpl_sim.properties" not in imports
            assert "mpl_sim.correlations" not in imports

    # B2 — no HX model imports/calls

    def test_b2_no_hx_models_import(self) -> None:
        for mod in (_WORKFLOW_MOD, _BLUEPRINT_MOD):
            imports = _import_lines(mod)
            assert "hx_models" not in imports
            assert not hasattr(mod, "HeatExchangerModelRegistry")

    # B3 — no production component execution imports

    def test_b3_no_mpl_sim_components_import(self) -> None:
        for mod in (_WORKFLOW_MOD, _BLUEPRINT_MOD):
            imports = _import_lines(mod)
            assert "mpl_sim.components" not in imports

    def test_b3_no_pump_evaporator_condenser_class_references(self) -> None:
        for mod in (_WORKFLOW_MOD, _BLUEPRINT_MOD):
            src = inspect.getsource(mod)
            assert "PumpComponent" not in src
            assert "EvaporatorComponent" not in src
            assert "CondenserComponent" not in src
            assert "AccumulatorComponent" not in src

    # B4 — no SystemState or FluidState

    def test_b4_no_system_state(self) -> None:
        for mod in (_WORKFLOW_MOD, _BLUEPRINT_MOD):
            imports = _import_lines(mod)
            assert "SystemState" not in imports
            assert not hasattr(mod, "SystemState")

    def test_b4_no_fluid_state(self) -> None:
        for mod in (_WORKFLOW_MOD, _BLUEPRINT_MOD):
            imports = _import_lines(mod)
            assert "FluidState" not in imports
            assert not hasattr(mod, "FluidState")

    # B5 — no production contribute(...)

    def test_b5_no_contribute_definition(self) -> None:
        for mod in (_WORKFLOW_MOD, _BLUEPRINT_MOD):
            src = inspect.getsource(mod)
            assert "def contribute" not in src

    def test_b5_no_dot_contribute_call(self) -> None:
        for mod in (_WORKFLOW_MOD, _BLUEPRINT_MOD):
            src = inspect.getsource(mod)
            assert ".contribute(" not in src

    def test_b5_no_contribute_attribute(self) -> None:
        for mod in (_WORKFLOW_MOD, _BLUEPRINT_MOD):
            assert not hasattr(mod, "contribute")

    # B6 — no component_type / role-based physics dispatch

    def test_b6_workflow_module_no_role_dispatch(self) -> None:
        src_fn = inspect.getsource(
            _WORKFLOW_MOD.build_configurable_residual_selection_from_blueprints
        )
        assert "component_type" not in src_fn
        assert ".role" not in src_fn

    def test_b6_blueprint_module_no_role_dispatch(self) -> None:
        src_fn = inspect.getsource(
            _BLUEPRINT_MOD.build_configurable_algebraic_residuals_from_blueprints
        )
        assert "component_type" not in src_fn
        assert ".role" not in src_fn

    # B7 — no automatic blueprint/residual/closure inference from role or topology

    def test_b7_no_role_inference_functions(self) -> None:
        for mod in (_WORKFLOW_MOD, _BLUEPRINT_MOD):
            src = inspect.getsource(mod)
            assert "infer_residuals_from_role" not in src
            assert "infer_blueprints_from_role" not in src
            assert "generate_residuals_from_role" not in src

    def test_b7_no_topology_inference_functions(self) -> None:
        for mod in (_WORKFLOW_MOD, _BLUEPRINT_MOD):
            src = inspect.getsource(mod)
            assert "infer_residuals_from_topology" not in src
            assert "infer_blueprints_from_topology" not in src
            assert "generate_residuals_from_topology" not in src

    def test_b7_no_graph_edge_inspection(self) -> None:
        for mod in (_WORKFLOW_MOD, _BLUEPRINT_MOD):
            src = inspect.getsource(mod)
            assert "graph.edges" not in src
            assert "graph.instances" not in src

    def test_b7_no_closure_auto_inference(self) -> None:
        for mod in (_WORKFLOW_MOD, _BLUEPRINT_MOD):
            src = inspect.getsource(mod)
            assert "auto_closure" not in src
            assert "closure_from_role" not in src
            assert "infer_closure" not in src

    # B8 — no generic solve(network), NetworkGraph.solve(), or named solvers

    def test_b8_no_network_graph_attribute(self) -> None:
        for mod in (_WORKFLOW_MOD, _BLUEPRINT_MOD):
            assert not hasattr(mod, "NetworkGraph")

    def test_b8_no_solve_network_function_defined(self) -> None:
        for mod in (_WORKFLOW_MOD, _BLUEPRINT_MOD):
            src = inspect.getsource(mod)
            assert "def solve_network" not in src
            assert "def solve(" not in src

    def test_b8_no_named_solver_imports(self) -> None:
        for mod in (_WORKFLOW_MOD, _BLUEPRINT_MOD):
            imports = _import_lines(mod)
            assert "solve_fixed_single_loop_residuals" not in imports
            assert "solve_network_residual_problem" not in imports

    def test_b8_no_named_solver_calls_in_source(self) -> None:
        for mod in (_WORKFLOW_MOD, _BLUEPRINT_MOD):
            src = inspect.getsource(mod)
            assert "solve_fixed_single_loop_residuals(" not in src
            assert "solve_network_residual_problem(" not in src

    # B9 — no file writing / report output

    def test_b9_no_file_writes(self) -> None:
        for mod in (_WORKFLOW_MOD, _BLUEPRINT_MOD):
            src = inspect.getsource(mod)
            assert "write_text" not in src
            assert "to_csv" not in src
            assert "to_json" not in src
            assert "open(" not in src

    # B10 — no root/least-squares solving

    def test_b10_no_root_finding_imports(self) -> None:
        for mod in (_WORKFLOW_MOD, _BLUEPRINT_MOD):
            imports = _import_lines(mod)
            assert "least_squares" not in imports
            assert "lstsq" not in imports
            assert "fsolve" not in imports
            assert "scipy.optimize" not in imports

    def test_b10_no_root_finding_calls_in_source(self) -> None:
        for mod in (_WORKFLOW_MOD, _BLUEPRINT_MOD):
            src = inspect.getsource(mod)
            assert "least_squares(" not in src
            assert "fsolve(" not in src
            assert "minimize(" not in src

    def test_b10_workflow_result_has_no_solver_fields(self) -> None:
        sbr = _build_scenario(scenario_id="gc_b10")
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert not hasattr(result, "converged")
        assert not hasattr(result, "iteration_count")
        assert not hasattr(result, "solution")
