"""Tests for Block 15H-B: structural diagnostics workflow integration.

Covers:
  - ConfigurableResidualDiagnosticWorkflowRequest validation and defensive copying
  - build_configurable_residual_diagnostic_workflow behavior
  - ConfigurableResidualDiagnosticWorkflowResult structure
  - build_configurable_residual_diagnostic_workflow_report output
  - Diagnostic gating before optional 15G-B selection/evaluation
  - No-inference safeguards (roles, topology, no auto-generation)
  - Boundary assertions: no CoolProp, no PropertyBackend, no SystemState, no
    FluidState, no solve, no contribute, no file writes, no Jacobian/rank.

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
    ConfigurableResidualBlueprintWorkflowResult,
)
from mpl_sim.network.configurable_residual_blueprints import (
    ImposedMassFlowResidualBlueprint,
    ImposedPressureResidualBlueprint,
    MassBalanceResidualBlueprint,
    PressureDifferenceResidualBlueprint,
    build_configurable_residual_blueprint_set,
)
from mpl_sim.network.configurable_residual_diagnostic_workflows import (
    ConfigurableResidualDiagnosticWorkflowRequest,
    ConfigurableResidualDiagnosticWorkflowResult,
    build_configurable_residual_diagnostic_workflow,
    build_configurable_residual_diagnostic_workflow_report,
)
from mpl_sim.network.configurable_residual_diagnostics import ResidualDeterminationStatus
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
    scenario_id="diag_wf_unit_single_loop",
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


def _valid_result() -> ConfigurableResidualDiagnosticWorkflowResult:
    sbr = _build_sbr()
    req = ConfigurableResidualDiagnosticWorkflowRequest(
        scenario_build_result=sbr,
        blueprints=_four_blueprints(),
        algebraic_unknown_values=_COMPLETE_UNKNOWNS,
        evaluate=True,
    )
    return build_configurable_residual_diagnostic_workflow(req)


# ===========================================================================
# ConfigurableResidualDiagnosticWorkflowRequest
# ===========================================================================


class TestRequestValidation:
    def test_requires_scenario_build_result_type(self) -> None:
        with pytest.raises(TypeError, match="scenario_build_result"):
            ConfigurableResidualDiagnosticWorkflowRequest(
                scenario_build_result="not a build result",
                blueprints=_four_blueprints(),
            )

    def test_rejects_invalid_blueprint_element(self) -> None:
        sbr = _build_sbr()
        with pytest.raises(TypeError, match="blueprints"):
            ConfigurableResidualDiagnosticWorkflowRequest(
                scenario_build_result=sbr,
                blueprints=[object()],
            )

    def test_rejects_invalid_blueprints_container_type(self) -> None:
        sbr = _build_sbr()
        with pytest.raises(TypeError, match="blueprints"):
            ConfigurableResidualDiagnosticWorkflowRequest(
                scenario_build_result=sbr,
                blueprints=12345,
            )

    def test_accepts_blueprint_set(self) -> None:
        sbr = _build_sbr()
        bp_set = build_configurable_residual_blueprint_set(_four_blueprints())
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=bp_set,
        )
        assert req.blueprints is bp_set

    def test_blueprint_sequence_defensively_copied_to_tuple(self) -> None:
        sbr = _build_sbr()
        bps = _four_blueprints()
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=bps,
        )
        assert isinstance(req.blueprints, tuple)
        assert tuple(b.residual_name for b in req.blueprints) == (
            "mb_pump_out",
            "p_ref",
            "mdot_pump",
            "dp_pump",
        )

    def test_defensive_copy_of_unknown_values(self) -> None:
        sbr = _build_sbr()
        mutable = dict(_COMPLETE_UNKNOWNS)
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
            algebraic_unknown_values=mutable,
        )
        mutable["mdot:pump"] = 999.0
        assert req.algebraic_unknown_values["mdot:pump"] == 0.1

    def test_unknown_values_default_none(self) -> None:
        sbr = _build_sbr()
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
        )
        assert req.algebraic_unknown_values is None

    def test_rejects_non_mapping_unknown_values(self) -> None:
        sbr = _build_sbr()
        with pytest.raises(TypeError, match="algebraic_unknown_values"):
            ConfigurableResidualDiagnosticWorkflowRequest(
                scenario_build_result=sbr,
                blueprints=_four_blueprints(),
                algebraic_unknown_values=["not", "a", "mapping"],
            )

    def test_evaluate_defaults_false(self) -> None:
        sbr = _build_sbr()
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
        )
        assert req.evaluate is False

    def test_evaluate_rejects_non_bool(self) -> None:
        sbr = _build_sbr()
        with pytest.raises(TypeError, match="evaluate"):
            ConfigurableResidualDiagnosticWorkflowRequest(
                scenario_build_result=sbr,
                blueprints=_four_blueprints(),
                evaluate="yes",
            )

    def test_request_construction_has_no_side_effects(self) -> None:
        sbr = _build_sbr()
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
            algebraic_unknown_values=_COMPLETE_UNKNOWNS,
            evaluate=True,
        )
        assert req.evaluate is True
        assert not hasattr(req, "structural_diagnostic")
        assert not hasattr(req, "selection_workflow_result")


# ===========================================================================
# build_configurable_residual_diagnostic_workflow
# ===========================================================================


class TestWorkflowHelper:
    def test_rejects_non_request_type(self) -> None:
        with pytest.raises(TypeError, match="request"):
            build_configurable_residual_diagnostic_workflow("not a request")

    def test_incompatible_blueprint_short_circuits_diagnostic_and_selection(self) -> None:
        sbr = _build_sbr()
        bad_bps = [
            ImposedMassFlowResidualBlueprint(
                residual_name="mdot_bad",
                component_id="nonexistent_component",
                mass_flow=0.1,
            )
        ]
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=bad_bps,
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert result.structural_diagnostic is None
        assert result.selection_workflow_result is None
        assert result.selection_requested is False
        assert result.selection_performed is False
        assert result.evaluation_performed is False
        assert result.evaluation_ready is False
        assert result.selected_mode is None
        assert result.determination_status is None
        assert result.no_solve is True
        assert "mdot:nonexistent_component" in result.missing_from_scenario
        assert result.deferred_reason != ""

    def test_compatible_evaluate_false_returns_diagnostic_only(self) -> None:
        sbr = _build_sbr()
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
            algebraic_unknown_values=_COMPLETE_UNKNOWNS,
            evaluate=False,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert result.structural_diagnostic is not None
        assert result.selection_workflow_result is None
        assert result.selection_requested is False
        assert result.selection_performed is False
        assert result.evaluation_requested is False
        assert result.evaluation_performed is False
        assert result.selected_mode is None

    def test_compatible_complete_values_evaluate_true_performs_selection(self) -> None:
        result = _valid_result()
        assert result.structural_diagnostic is not None
        assert result.selection_workflow_result is not None
        assert isinstance(
            result.selection_workflow_result, ConfigurableResidualBlueprintWorkflowResult
        )
        assert result.selection_requested is True
        assert result.selection_performed is True
        assert result.evaluation_requested is True
        assert result.evaluation_ready is True
        assert result.evaluation_performed is True
        assert result.selected_mode is ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC
        assert result.deferred_reason == ""

    def test_compatible_missing_values_evaluate_true_defers(self) -> None:
        sbr = _build_sbr()
        partial = dict(_COMPLETE_UNKNOWNS)
        del partial["P:n_pump_out"]
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
            algebraic_unknown_values=partial,
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert result.structural_diagnostic is not None
        assert result.evaluation_ready is False
        assert result.selection_workflow_result is None
        assert result.selection_performed is False
        assert result.evaluation_performed is False
        assert result.selected_mode is None
        assert "P:n_pump_out" in result.missing_from_values
        assert result.deferred_reason != ""

    def test_compatible_no_values_evaluate_true_defers(self) -> None:
        sbr = _build_sbr()
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert result.evaluation_ready is False
        assert result.selection_workflow_result is None
        assert result.evaluation_performed is False
        assert result.selected_mode is None
        assert "explicit unknown values were not supplied" in result.deferred_reason

    def test_structurally_square_still_no_solve(self) -> None:
        result = _valid_result()
        status = result.structural_diagnostic.determination_status
        assert status is ResidualDeterminationStatus.SQUARE
        assert result.solve_ready is False
        assert result.no_solve is True

    def test_underdetermined_diagnostic_does_not_solve(self) -> None:
        sbr = _build_sbr()
        # One mass-balance residual requires two unknowns (mdot:pump,
        # mdot:evaporator); 1 residual < 2 required unknowns => underdetermined.
        single_bp = [
            MassBalanceResidualBlueprint(
                residual_name="mb_only",
                incoming_component_ids=("pump",),
                outgoing_component_ids=("evaporator",),
            )
        ]
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=single_bp,
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert result.structural_diagnostic is not None
        assert (
            result.structural_diagnostic.determination_status
            is ResidualDeterminationStatus.UNDERDETERMINED
        )
        assert result.solve_ready is False
        assert result.no_solve is True

    def test_overdetermined_diagnostic_does_not_solve(self) -> None:
        sbr = _build_sbr()
        bps = _four_blueprints() + [
            ImposedPressureResidualBlueprint(
                residual_name="p_extra",
                node_id="n_pump_out",
                pressure=150_000.0,
            )
        ]
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=bps,
            algebraic_unknown_values=_COMPLETE_UNKNOWNS,
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert (
            result.structural_diagnostic.determination_status
            is ResidualDeterminationStatus.OVERDETERMINED
        )
        assert result.solve_ready is False
        assert result.no_solve is True

    def test_empty_blueprints_rejected_through_15ga_builder(self) -> None:
        sbr = _build_sbr()
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=[],
        )
        with pytest.raises(ValueError, match="must not be empty"):
            build_configurable_residual_diagnostic_workflow(req)

    def test_duplicate_blueprint_names_rejected_through_15ga_builder(self) -> None:
        sbr = _build_sbr()
        dup_bps = [
            ImposedPressureResidualBlueprint("dup", "n_acc_out", 1e5),
            ImposedPressureResidualBlueprint("dup", "n_pump_out", 1.5e5),
        ]
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=dup_bps,
        )
        with pytest.raises(ValueError, match="duplicate"):
            build_configurable_residual_diagnostic_workflow(req)

    def test_deferred_reasons_are_deterministic(self) -> None:
        sbr = _build_sbr()
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
            evaluate=True,
        )
        result1 = build_configurable_residual_diagnostic_workflow(req)
        result2 = build_configurable_residual_diagnostic_workflow(req)
        assert result1.deferred_reason == result2.deferred_reason


# ===========================================================================
# ConfigurableResidualDiagnosticWorkflowResult structure
# ===========================================================================


class TestResultStructure:
    def test_no_solve_true_solve_ready_false(self) -> None:
        result = _valid_result()
        assert result.no_solve is True
        assert result.solve_ready is False

    def test_inference_flags_all_false(self) -> None:
        result = _valid_result()
        assert result.residuals_inferred_from_roles is False
        assert result.residuals_inferred_from_topology is False
        assert result.blueprints_inferred_from_roles is False
        assert result.blueprints_inferred_from_topology is False
        assert result.closures_inferred_from_roles is False
        assert result.production_components_executed is False

    def test_required_unknown_names_present(self) -> None:
        result = _valid_result()
        assert "mdot:pump" in result.required_unknown_names
        assert "P:n_acc_out" in result.required_unknown_names

    def test_selected_mode_requires_selection_performed(self) -> None:
        sbr = _build_sbr()
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
            algebraic_unknown_values=_COMPLETE_UNKNOWNS,
            evaluate=True,
        )
        valid_result = build_configurable_residual_diagnostic_workflow(req)
        with pytest.raises(ValueError, match="selected_mode"):
            ConfigurableResidualDiagnosticWorkflowResult(
                blueprint_build_result=valid_result.blueprint_build_result,
                structural_diagnostic=valid_result.structural_diagnostic,
                selection_workflow_result=None,
                selection_requested=False,
                selection_performed=False,
                evaluation_requested=False,
                evaluation_ready=True,
                evaluation_performed=False,
                deferred_reason="x",
                selected_mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
                required_unknown_names=(),
                missing_from_scenario=(),
                missing_from_values=(),
                determination_status=valid_result.determination_status,
                solve_ready=False,
                no_solve=True,
                residuals_inferred_from_roles=False,
                residuals_inferred_from_topology=False,
                blueprints_inferred_from_roles=False,
                blueprints_inferred_from_topology=False,
                closures_inferred_from_roles=False,
                production_components_executed=False,
                limitations=(),
            )

    def test_diagnostic_and_determination_status_must_match_presence(self) -> None:
        sbr = _build_sbr()
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
        )
        bp_result = build_configurable_residual_diagnostic_workflow(req).blueprint_build_result
        with pytest.raises(ValueError, match="determination_status"):
            ConfigurableResidualDiagnosticWorkflowResult(
                blueprint_build_result=bp_result,
                structural_diagnostic=None,
                selection_workflow_result=None,
                selection_requested=False,
                selection_performed=False,
                evaluation_requested=False,
                evaluation_ready=False,
                evaluation_performed=False,
                deferred_reason="",
                selected_mode=None,
                required_unknown_names=(),
                missing_from_scenario=(),
                missing_from_values=(),
                determination_status=ResidualDeterminationStatus.SQUARE,
                solve_ready=False,
                no_solve=True,
                residuals_inferred_from_roles=False,
                residuals_inferred_from_topology=False,
                blueprints_inferred_from_roles=False,
                blueprints_inferred_from_topology=False,
                closures_inferred_from_roles=False,
                production_components_executed=False,
                limitations=(),
            )

    def test_solve_ready_true_rejected(self) -> None:
        sbr = _build_sbr()
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
        )
        bp_result = build_configurable_residual_diagnostic_workflow(req).blueprint_build_result
        with pytest.raises(ValueError, match="solve_ready"):
            ConfigurableResidualDiagnosticWorkflowResult(
                blueprint_build_result=bp_result,
                structural_diagnostic=None,
                selection_workflow_result=None,
                selection_requested=False,
                selection_performed=False,
                evaluation_requested=False,
                evaluation_ready=False,
                evaluation_performed=False,
                deferred_reason="",
                selected_mode=None,
                required_unknown_names=(),
                missing_from_scenario=(),
                missing_from_values=(),
                determination_status=None,
                solve_ready=True,
                no_solve=True,
                residuals_inferred_from_roles=False,
                residuals_inferred_from_topology=False,
                blueprints_inferred_from_roles=False,
                blueprints_inferred_from_topology=False,
                closures_inferred_from_roles=False,
                production_components_executed=False,
                limitations=(),
            )


# ===========================================================================
# build_configurable_residual_diagnostic_workflow_report
# ===========================================================================


class TestWorkflowReport:
    def test_rejects_non_result_type(self) -> None:
        with pytest.raises(TypeError, match="result"):
            build_configurable_residual_diagnostic_workflow_report("not a result")

    def test_report_is_json_serializable(self) -> None:
        result = _valid_result()
        report = build_configurable_residual_diagnostic_workflow_report(result)
        json_str = json.dumps(report)
        assert json.loads(json_str)["status"] == "configurable_residual_diagnostic_workflow"

    def test_report_includes_blueprint_diagnostic_and_selection_sections(self) -> None:
        result = _valid_result()
        report = build_configurable_residual_diagnostic_workflow_report(result)
        assert report["blueprint_report"]["status"] == "configurable_residual_blueprint_build"
        assert (
            report["diagnostic_report"]["status"] == "configurable_residual_structural_diagnostic"
        )
        assert report["selection_report"]["status"] == "configurable_residual_blueprint_workflow"

    def test_report_marks_diagnostic_and_selection_none_when_incompatible(self) -> None:
        sbr = _build_sbr()
        bad_bps = [ImposedMassFlowResidualBlueprint("mdot_bad", "nonexistent_component", 0.1)]
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=bad_bps,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        report = build_configurable_residual_diagnostic_workflow_report(result)
        assert report["diagnostic_report"] is None
        assert report["selection_report"] is None
        assert report["selected_mode"] is None

    def test_report_marks_selection_none_when_evaluate_false(self) -> None:
        sbr = _build_sbr()
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        report = build_configurable_residual_diagnostic_workflow_report(result)
        assert report["diagnostic_report"] is not None
        assert report["selection_report"] is None
        assert report["selected_mode"] is None

    def test_report_includes_no_solve_and_inference_flags(self) -> None:
        result = _valid_result()
        report = build_configurable_residual_diagnostic_workflow_report(result)
        assert report["no_solve"] is True
        assert report["solve_ready"] is False
        assert report["blueprints_inferred_from_roles"] is False
        assert report["blueprints_inferred_from_topology"] is False
        assert report["residuals_inferred_from_roles"] is False
        assert report["residuals_inferred_from_topology"] is False
        assert report["closures_inferred_from_roles"] is False
        assert report["production_components_executed"] is False

    def test_report_includes_determination_status(self) -> None:
        result = _valid_result()
        report = build_configurable_residual_diagnostic_workflow_report(result)
        assert report["determination_status"] == "square"

    def test_report_selected_mode_only_when_selection_performed(self) -> None:
        result = _valid_result()
        report = build_configurable_residual_diagnostic_workflow_report(result)
        assert report["selected_mode"] == "configurable_algebraic"

        sbr = _build_sbr()
        req_deferred = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
            evaluate=True,
        )
        deferred_result = build_configurable_residual_diagnostic_workflow(req_deferred)
        deferred_report = build_configurable_residual_diagnostic_workflow_report(deferred_result)
        assert deferred_report["selected_mode"] is None

    def test_report_includes_limitations(self) -> None:
        result = _valid_result()
        report = build_configurable_residual_diagnostic_workflow_report(result)
        assert isinstance(report["limitations"], list)
        assert len(report["limitations"]) > 0


# ===========================================================================
# Boundary stories — module attribute checks
# ===========================================================================


class TestWorkflowModuleBoundaries:
    def _import_lines(self) -> list[str]:
        import re

        import mpl_sim.network.configurable_residual_diagnostic_workflows as mod

        src_path = getattr(mod, "__file__", "")
        if not src_path:
            return []
        with open(src_path) as f:
            text = f.read()
        return [ln for ln in text.splitlines() if re.match(r"^\s*(import|from)\s+", ln)]

    def _executable_lines(self) -> list[str]:
        import mpl_sim.network.configurable_residual_diagnostic_workflows as mod

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
        import mpl_sim.network.configurable_residual_diagnostic_workflows as mod

        assert not hasattr(mod, "CoolProp")
        for ln in self._import_lines():
            assert "CoolProp" not in ln

    def test_module_no_property_backend(self) -> None:
        import mpl_sim.network.configurable_residual_diagnostic_workflows as mod

        assert not hasattr(mod, "PropertyBackend")
        for ln in self._import_lines():
            assert "PropertyBackend" not in ln

    def test_module_no_system_state(self) -> None:
        import mpl_sim.network.configurable_residual_diagnostic_workflows as mod

        assert not hasattr(mod, "SystemState")
        for ln in self._import_lines():
            assert "SystemState" not in ln

    def test_module_no_fluid_state(self) -> None:
        import mpl_sim.network.configurable_residual_diagnostic_workflows as mod

        assert not hasattr(mod, "FluidState")
        for ln in self._import_lines():
            assert "FluidState" not in ln

    def test_module_no_contribute(self) -> None:
        for ln in self._executable_lines():
            assert ".contribute(" not in ln, f"contribute call found: {ln!r}"
            assert "def contribute" not in ln

    def test_module_no_solve_network(self) -> None:
        import mpl_sim.network.configurable_residual_diagnostic_workflows as mod

        assert not hasattr(mod, "NetworkGraph")
        for ln in self._executable_lines():
            assert "solve(network" not in ln
            assert "NetworkGraph.solve" not in ln
            assert "solve_fixed_single_loop_residuals" not in ln
            assert "solve_network_residual_problem" not in ln

    def test_module_no_components_or_properties_import(self) -> None:
        import mpl_sim.network.configurable_residual_diagnostic_workflows as mod

        assert not hasattr(mod, "components")
        for ln in self._import_lines():
            assert "mpl_sim.components" not in ln
            assert "mpl_sim.properties" not in ln
            assert "mpl_sim.correlations" not in ln
            assert "mpl_sim.hx_models" not in ln

    def test_module_no_file_writes(self) -> None:
        for ln in self._executable_lines():
            assert "write_text" not in ln
            assert "to_csv" not in ln
            assert "to_json" not in ln

    def test_module_no_least_squares_or_root_finding(self) -> None:
        for ln in self._executable_lines():
            assert "least_squares" not in ln
            assert "fsolve" not in ln
            assert "lstsq" not in ln
            assert "minimize" not in ln

    def test_module_no_jacobian_rank_pinv(self) -> None:
        # The module's documented limitations legitimately state (as a negative
        # claim) that no Jacobian/rank/pseudo-inverse is computed; that text is
        # allowed.  This check targets actual numpy/scipy linear-algebra usage.
        for ln in self._executable_lines():
            assert "pinv(" not in ln
            assert "matrix_rank" not in ln
            assert "numpy" not in ln
            assert "np.linalg" not in ln
            assert "scipy" not in ln

    def test_module_no_direct_15fa_15fb_evaluation_calls(self) -> None:
        for ln in self._executable_lines():
            assert "evaluate_configurable_algebraic_residuals(" not in ln
            assert "evaluate_selected_configurable_residuals(" not in ln


# ===========================================================================
# No-inference safeguards
# ===========================================================================


class TestNoInferenceSafeguards:
    def test_role_changes_do_not_alter_workflow_result(self) -> None:
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
        sbr_original = _build_sbr()

        req_original = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr_original,
            blueprints=_four_blueprints(),
            algebraic_unknown_values=_COMPLETE_UNKNOWNS,
            evaluate=True,
        )
        req_variant = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr_variant,
            blueprints=_four_blueprints(),
            algebraic_unknown_values=_COMPLETE_UNKNOWNS,
            evaluate=True,
        )
        result_original = build_configurable_residual_diagnostic_workflow(req_original)
        result_variant = build_configurable_residual_diagnostic_workflow(req_variant)

        assert result_original.required_unknown_names == result_variant.required_unknown_names
        assert result_original.selected_mode == result_variant.selected_mode
        assert (
            result_original.structural_diagnostic.determination_status
            == result_variant.structural_diagnostic.determination_status
        )

    def test_topology_change_does_not_create_additional_requirements(self) -> None:
        sbr = _build_sbr()
        single_bp = [ImposedPressureResidualBlueprint("p_only", "n_acc_out", 1e5)]
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=single_bp,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert result.blueprint_build_result.blueprint_count == 1
        assert result.required_unknown_names == ("P:n_acc_out",)
