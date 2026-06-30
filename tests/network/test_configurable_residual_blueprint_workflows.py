"""Tests for Block 15G-B: explicit residual blueprint selection workflow integration.

Covers:
  - ConfigurableResidualBlueprintWorkflowRequest validation and defensive copying
  - build_configurable_residual_selection_from_blueprints behavior
  - ConfigurableResidualBlueprintWorkflowResult structure
  - build_configurable_residual_blueprint_workflow_report output
  - No-inference safeguards (roles, topology, no auto-generation)
  - Boundary assertions: no CoolProp, no PropertyBackend, no SystemState, no
    FluidState, no solve, no contribute, no file writes.

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
    ConfigurableResidualBlueprintWorkflowResult,
    build_configurable_residual_blueprint_workflow_report,
    build_configurable_residual_selection_from_blueprints,
)
from mpl_sim.network.configurable_residual_blueprints import (
    ImposedMassFlowResidualBlueprint,
    ImposedPressureResidualBlueprint,
    MassBalanceResidualBlueprint,
    PressureDifferenceResidualBlueprint,
    build_configurable_residual_blueprint_set,
)
from mpl_sim.network.configurable_residual_selection import ConfigurableResidualMode
from mpl_sim.network.configurable_scenarios import (
    ConfigurableScenarioSpec,
    ScenarioComponentRole,
    ScenarioComponentSpec,
    ScenarioConnectionSpec,
    ScenarioNodeSpec,
    build_configurable_scenario,
)

# ===========================================================================
# Shared fixtures
# ===========================================================================

_SINGLE_LOOP_SPEC = ConfigurableScenarioSpec(
    scenario_id="wf_unit_single_loop",
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
    "mdot:pump": 0.1,
    "mdot:evaporator": 0.1,
    "P:n_acc_out": 100_000.0,
    "P:n_pump_out": 150_000.0,
}


def _build_sbr():
    return build_configurable_scenario(_SINGLE_LOOP_SPEC)


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


# ===========================================================================
# ConfigurableResidualBlueprintWorkflowRequest
# ===========================================================================


class TestWorkflowRequestValidation:
    def test_requires_scenario_build_result_type(self) -> None:
        with pytest.raises(TypeError, match="scenario_build_result"):
            ConfigurableResidualBlueprintWorkflowRequest(
                scenario_build_result="not a build result",
                blueprints=_four_blueprints(),
            )

    def test_rejects_invalid_blueprint_element(self) -> None:
        sbr = _build_sbr()
        with pytest.raises(TypeError, match="blueprints"):
            ConfigurableResidualBlueprintWorkflowRequest(
                scenario_build_result=sbr,
                blueprints=[object()],
            )

    def test_rejects_invalid_blueprints_container_type(self) -> None:
        sbr = _build_sbr()
        with pytest.raises(TypeError, match="blueprints"):
            ConfigurableResidualBlueprintWorkflowRequest(
                scenario_build_result=sbr,
                blueprints=12345,
            )

    def test_accepts_blueprint_set(self) -> None:
        sbr = _build_sbr()
        bp_set = build_configurable_residual_blueprint_set(_four_blueprints())
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=bp_set,
        )
        assert req.blueprints is bp_set

    def test_preserves_blueprint_order(self) -> None:
        sbr = _build_sbr()
        bps = _four_blueprints()
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=bps,
        )
        assert tuple(b.residual_name for b in req.blueprints) == (
            "mb_pump_out",
            "p_ref",
            "mdot_pump",
            "dp_pump",
        )

    def test_list_blueprints_converted_to_tuple(self) -> None:
        sbr = _build_sbr()
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
        )
        assert isinstance(req.blueprints, tuple)

    def test_defensive_copy_of_unknown_values(self) -> None:
        sbr = _build_sbr()
        mutable = dict(_ZERO_RESIDUAL_UNKNOWNS)
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
            algebraic_unknown_values=mutable,
        )
        mutable["mdot:pump"] = 999.0
        assert req.algebraic_unknown_values["mdot:pump"] == 0.1

    def test_unknown_values_default_none(self) -> None:
        sbr = _build_sbr()
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
        )
        assert req.algebraic_unknown_values is None

    def test_rejects_non_mapping_unknown_values(self) -> None:
        sbr = _build_sbr()
        with pytest.raises(TypeError, match="algebraic_unknown_values"):
            ConfigurableResidualBlueprintWorkflowRequest(
                scenario_build_result=sbr,
                blueprints=_four_blueprints(),
                algebraic_unknown_values=["not", "a", "mapping"],
            )

    def test_evaluate_defaults_false(self) -> None:
        sbr = _build_sbr()
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
        )
        assert req.evaluate is False

    def test_evaluate_rejects_non_bool(self) -> None:
        sbr = _build_sbr()
        with pytest.raises(TypeError, match="evaluate"):
            ConfigurableResidualBlueprintWorkflowRequest(
                scenario_build_result=sbr,
                blueprints=_four_blueprints(),
                evaluate="yes",
            )

    def test_request_construction_does_not_evaluate(self) -> None:
        sbr = _build_sbr()
        # No exception, no evaluation side effects; just successful construction.
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
            algebraic_unknown_values=_ZERO_RESIDUAL_UNKNOWNS,
            evaluate=True,
        )
        assert req.evaluate is True
        # Constructing the request must not itself produce a build/selection result.
        assert not hasattr(req, "selection_result")


# ===========================================================================
# build_configurable_residual_selection_from_blueprints
# ===========================================================================


class TestWorkflowHelper:
    def test_rejects_non_request_type(self) -> None:
        with pytest.raises(TypeError, match="request"):
            build_configurable_residual_selection_from_blueprints("not a request")

    def test_compatible_creates_configurable_algebraic_selection(self) -> None:
        sbr = _build_sbr()
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert result.selection_result is not None
        assert result.selected_mode is ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC

    def test_evaluate_false_defers_evaluation(self) -> None:
        sbr = _build_sbr()
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
            algebraic_unknown_values=_ZERO_RESIDUAL_UNKNOWNS,
            evaluate=False,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert result.evaluation_performed is False
        assert result.selection_result.evaluation_deferred is True

    def test_evaluate_true_with_zero_point_values_gives_zero_residuals(self) -> None:
        sbr = _build_sbr()
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
            algebraic_unknown_values=_ZERO_RESIDUAL_UNKNOWNS,
            evaluate=True,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert result.evaluation_performed is True
        eval_r = result.selection_result.evaluation_result
        assert eval_r.max_abs_residual == pytest.approx(0.0, abs=1e-9)

    def test_evaluate_true_with_perturbed_values_gives_nonzero_residuals(self) -> None:
        sbr = _build_sbr()
        perturbed = dict(_ZERO_RESIDUAL_UNKNOWNS)
        perturbed["mdot:pump"] = 0.5
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
            algebraic_unknown_values=perturbed,
            evaluate=True,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert result.evaluation_performed is True
        assert result.selection_result.evaluation_result.max_abs_residual > 0.0

    def test_evaluate_true_without_values_defers_evaluation(self) -> None:
        sbr = _build_sbr()
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
            evaluate=True,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert result.evaluation_performed is False
        assert result.selection_result.evaluation_deferred is True
        assert result.deferred_or_incompatibility_reason != ""

    def test_incompatible_blueprint_unknowns_produce_no_selection_and_no_evaluation(
        self,
    ) -> None:
        sbr = _build_sbr()
        bad_bps = [
            ImposedMassFlowResidualBlueprint(
                residual_name="mdot_bad",
                component_id="nonexistent_component",
                mass_flow=0.1,
            )
        ]
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=bad_bps,
            evaluate=True,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert result.selection_result is None
        assert result.selected_mode is None
        assert result.evaluation_performed is False
        assert "mdot:nonexistent_component" in result.missing_unknowns
        assert result.deferred_or_incompatibility_reason != ""

    def test_empty_blueprints_rejected_through_15ga_builder(self) -> None:
        sbr = _build_sbr()
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=[],
        )
        with pytest.raises(ValueError, match="must not be empty"):
            build_configurable_residual_selection_from_blueprints(req)

    def test_duplicate_blueprint_names_rejected_through_15ga_builder(self) -> None:
        sbr = _build_sbr()
        dup_bps = [
            ImposedPressureResidualBlueprint("dup", "n_acc_out", 1e5),
            ImposedPressureResidualBlueprint("dup", "n_pump_out", 1.5e5),
        ]
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=dup_bps,
        )
        with pytest.raises(ValueError, match="duplicate"):
            build_configurable_residual_selection_from_blueprints(req)

    def test_no_fallback_to_declaration_only_or_closure_only_mode(self) -> None:
        sbr = _build_sbr()
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert result.selected_mode is ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC
        assert result.selected_mode is not ConfigurableResidualMode.DECLARATION_ONLY
        assert result.selected_mode is not ConfigurableResidualMode.CLOSURE_ONLY


# ===========================================================================
# ConfigurableResidualBlueprintWorkflowResult structure
# ===========================================================================


class TestWorkflowResultStructure:
    def test_no_solve_true(self) -> None:
        sbr = _build_sbr()
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert result.no_solve is True

    def test_inference_flags_all_false(self) -> None:
        sbr = _build_sbr()
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert result.blueprints_inferred_from_roles is False
        assert result.blueprints_inferred_from_topology is False
        assert result.residuals_inferred_from_roles is False
        assert result.residuals_inferred_from_topology is False
        assert result.closures_inferred_from_roles is False
        assert result.production_components_executed is False

    def test_required_unknown_names_present(self) -> None:
        sbr = _build_sbr()
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert "mdot:pump" in result.required_unknown_names
        assert "P:n_acc_out" in result.required_unknown_names

    def test_selected_mode_none_implies_selection_result_none(self) -> None:
        with pytest.raises(ValueError, match="selected_mode"):
            ConfigurableResidualBlueprintWorkflowResult(
                blueprint_build_result=build_configurable_residual_selection_from_blueprints(
                    ConfigurableResidualBlueprintWorkflowRequest(
                        scenario_build_result=_build_sbr(),
                        blueprints=_four_blueprints(),
                    )
                ).blueprint_build_result,
                selection_result=None,
                selected_mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
                evaluation_performed=False,
                deferred_or_incompatibility_reason="x",
                required_unknown_names=(),
                missing_unknowns=(),
                no_solve=True,
                blueprints_inferred_from_roles=False,
                blueprints_inferred_from_topology=False,
                residuals_inferred_from_roles=False,
                residuals_inferred_from_topology=False,
                closures_inferred_from_roles=False,
                production_components_executed=False,
                limitations=(),
            )


# ===========================================================================
# build_configurable_residual_blueprint_workflow_report
# ===========================================================================


class TestWorkflowReport:
    def test_rejects_non_result_type(self) -> None:
        with pytest.raises(TypeError, match="result"):
            build_configurable_residual_blueprint_workflow_report("not a result")

    def test_report_is_json_serializable(self) -> None:
        sbr = _build_sbr()
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
            algebraic_unknown_values=_ZERO_RESIDUAL_UNKNOWNS,
            evaluate=True,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        report = build_configurable_residual_blueprint_workflow_report(result)
        json_str = json.dumps(report)
        assert json.loads(json_str)["status"] == "configurable_residual_blueprint_workflow"

    def test_report_includes_blueprint_report(self) -> None:
        sbr = _build_sbr()
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        report = build_configurable_residual_blueprint_workflow_report(result)
        assert report["blueprint_report"]["status"] == "configurable_residual_blueprint_build"

    def test_report_includes_selection_report_when_created(self) -> None:
        sbr = _build_sbr()
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        report = build_configurable_residual_blueprint_workflow_report(result)
        assert report["selection_report"] is not None
        assert report["selection_report"]["selected_mode"] == "configurable_algebraic"

    def test_report_marks_selection_report_none_when_not_created(self) -> None:
        sbr = _build_sbr()
        bad_bps = [ImposedMassFlowResidualBlueprint("mdot_bad", "nonexistent_component", 0.1)]
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=bad_bps,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        report = build_configurable_residual_blueprint_workflow_report(result)
        assert report["selection_report"] is None
        assert report["selected_mode"] is None

    def test_report_includes_no_solve_and_inference_flags(self) -> None:
        sbr = _build_sbr()
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
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

    def test_report_includes_limitations(self) -> None:
        sbr = _build_sbr()
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        report = build_configurable_residual_blueprint_workflow_report(result)
        assert isinstance(report["limitations"], list)
        assert len(report["limitations"]) > 0

    def test_report_does_not_imply_automatic_residual_generation(self) -> None:
        sbr = _build_sbr()
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        report = build_configurable_residual_blueprint_workflow_report(result)
        limitation_text = " ".join(report["limitations"]).lower()
        assert "user-declared" in limitation_text or "no blueprints inferred" in limitation_text


# ===========================================================================
# No-inference safeguards
# ===========================================================================


class TestNoInferenceSafeguards:
    def test_role_changes_do_not_alter_workflow_result(self) -> None:
        variant_spec = ConfigurableScenarioSpec(
            scenario_id="wf_role_variant",
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
        sbr_original = _build_sbr()

        req_original = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr_original,
            blueprints=_four_blueprints(),
        )
        req_variant = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr_variant,
            blueprints=_four_blueprints(),
        )
        result_original = build_configurable_residual_selection_from_blueprints(req_original)
        result_variant = build_configurable_residual_selection_from_blueprints(req_variant)

        assert (
            result_original.blueprint_build_result.required_unknown_names
            == result_variant.blueprint_build_result.required_unknown_names
        )
        assert result_original.selected_mode == result_variant.selected_mode

    def test_topology_change_does_not_create_new_blueprints(self) -> None:
        sbr = _build_sbr()
        single_bp = [ImposedPressureResidualBlueprint("p_only", "n_acc_out", 1e5)]
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=single_bp,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert result.blueprint_build_result.blueprint_count == 1
        assert result.blueprint_build_result.blueprint_names == ("p_only",)

    def test_workflow_with_no_blueprints_rejected_not_auto_generated(self) -> None:
        sbr = _build_sbr()
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=[],
        )
        with pytest.raises(ValueError):
            build_configurable_residual_selection_from_blueprints(req)

    def test_anchor_metadata_does_not_discover_connected_components(self) -> None:
        sbr = _build_sbr()
        bp_with_anchor = MassBalanceResidualBlueprint(
            residual_name="mb_anchor",
            incoming_component_ids=("pump",),
            outgoing_component_ids=(),
            anchor_node_id="n_pump_out",
        )
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=[bp_with_anchor],
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        # Only the explicitly declared incoming component contributes an unknown.
        assert result.required_unknown_names == ("mdot:pump",)

    def test_component_type_labels_do_not_dispatch_physics(self) -> None:
        # Using a component ID that happens to look like a known role string
        # ("condenser") must not trigger any special physics; translation is
        # purely identifier-based.
        sbr = _build_sbr()
        bp = ImposedMassFlowResidualBlueprint(
            residual_name="mdot_condenser",
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


# ===========================================================================
# Boundary stories — module attribute checks
# ===========================================================================


class TestWorkflowModuleBoundaries:
    def _workflow_import_lines(self) -> list[str]:
        import re

        import mpl_sim.network.configurable_residual_blueprint_workflows as mod

        src_path = getattr(mod, "__file__", "")
        if not src_path:
            return []
        with open(src_path) as f:
            text = f.read()
        return [ln for ln in text.splitlines() if re.match(r"^\s*(import|from)\s+", ln)]

    def _workflow_executable_lines(self) -> list[str]:
        import mpl_sim.network.configurable_residual_blueprint_workflows as mod

        src_path = getattr(mod, "__file__", "")
        if not src_path:
            return []
        lines: list[str] = []
        in_docstring = False
        docstring_char = None
        with open(src_path) as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                for dq in ('"""', "'''"):
                    if dq in line:
                        count = line.count(dq)
                        if in_docstring and docstring_char == dq:
                            in_docstring = count % 2 == 0
                            docstring_char = None if not in_docstring else dq
                        elif not in_docstring and count % 2 == 1:
                            in_docstring = True
                            docstring_char = dq
                        break
                if in_docstring:
                    continue
                lines.append(line)
        return lines

    def test_module_no_coolprop(self) -> None:
        import mpl_sim.network.configurable_residual_blueprint_workflows as mod

        assert not hasattr(mod, "CoolProp")
        for ln in self._workflow_import_lines():
            assert "CoolProp" not in ln

    def test_module_no_property_backend(self) -> None:
        import mpl_sim.network.configurable_residual_blueprint_workflows as mod

        assert not hasattr(mod, "PropertyBackend")
        for ln in self._workflow_import_lines():
            assert "PropertyBackend" not in ln

    def test_module_no_system_state(self) -> None:
        import mpl_sim.network.configurable_residual_blueprint_workflows as mod

        assert not hasattr(mod, "SystemState")
        for ln in self._workflow_import_lines():
            assert "SystemState" not in ln

    def test_module_no_fluid_state(self) -> None:
        import mpl_sim.network.configurable_residual_blueprint_workflows as mod

        assert not hasattr(mod, "FluidState")
        for ln in self._workflow_import_lines():
            assert "FluidState" not in ln

    def test_module_no_contribute(self) -> None:
        for ln in self._workflow_executable_lines():
            assert ".contribute(" not in ln, f"contribute call found: {ln!r}"
            assert "def contribute" not in ln

    def test_module_no_solve_network(self) -> None:
        import mpl_sim.network.configurable_residual_blueprint_workflows as mod

        assert not hasattr(mod, "NetworkGraph")
        for ln in self._workflow_executable_lines():
            assert "solve(network" not in ln
            assert "NetworkGraph.solve" not in ln
            assert "solve_fixed_single_loop_residuals" not in ln
            assert "solve_network_residual_problem" not in ln

    def test_module_no_components_or_properties_import(self) -> None:
        import mpl_sim.network.configurable_residual_blueprint_workflows as mod

        assert not hasattr(mod, "components")
        for ln in self._workflow_import_lines():
            assert "mpl_sim.components" not in ln
            assert "mpl_sim.properties" not in ln
            assert "mpl_sim.correlations" not in ln
            assert "mpl_sim.hx_models" not in ln

    def test_module_no_file_writes(self) -> None:
        for ln in self._workflow_executable_lines():
            assert "write_text" not in ln
            assert "to_csv" not in ln
            assert "to_json" not in ln

    def test_module_no_least_squares_or_root_finding(self) -> None:
        for ln in self._workflow_executable_lines():
            assert "least_squares" not in ln
            assert "fsolve" not in ln
            assert "lstsq" not in ln
            assert "minimize" not in ln
