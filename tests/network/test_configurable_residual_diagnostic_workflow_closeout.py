"""Acceptance / closeout tests for Block 15H-C.

Proves that the complete Block 15H explicit structural residual diagnostics
stack works coherently end-to-end across:
  - 15F-A explicit configurable algebraic residual declarations/evaluation API
  - 15F-B CONFIGURABLE_ALGEBRAIC residual-selection path
  - 15G-A explicit residual blueprint translation
  - 15G-B explicit blueprint-to-selection workflow
  - 15H-A explicit residual/unknown structural diagnostics
  - 15H-B diagnostic-aware workflow integration

This block is tests and documentation only. It does NOT add runtime modules
or modify runtime behavior.

Acceptance stories
-------------------
1   Full accepted 15H stack with evaluate=False.
2   Full accepted 15H stack with evaluate=True and complete values.
3   Perturbed values produce nonzero residuals but no solve.
4   Missing values defer before 15G-B selection/evaluation.
5   Incompatible blueprints short-circuit before diagnostics.
6   Structurally square is not solve-ready.
7   Underdetermined and overdetermined are count diagnostics only.
8   Role and component labels remain metadata only.
9   Topology changes do not create extra diagnostics requirements.
10  Direct lower layers remain independent.
11  Report stack is composable and JSON-serializable.
12  Production contract remains frozen.

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
B10 No root/least-squares/Jacobian/rank/pseudo-inverse solving.
B11 No direct 15F-A/15F-B evaluation calls from the 15H-B workflow module.

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
_DIAG_WF_MOD = importlib.import_module("mpl_sim.network.configurable_residual_diagnostic_workflows")
_DIAG_MOD = importlib.import_module("mpl_sim.network.configurable_residual_diagnostics")

# ---------------------------------------------------------------------------
# Shared scenario / blueprint / unknown-value fixtures
# ---------------------------------------------------------------------------
#
# 4-component single-loop scenario:
#   Components : accumulator, pump, evaporator, condenser
#   Nodes      : n_acc_out, n_pump_out, n_evap_out, n_cond_out
#
# Blueprints (4 explicit, yielding 4 required unknowns):
#   mb_pump_out  — mass balance: incoming=[pump], outgoing=[evaporator]
#                  requires mdot:pump, mdot:evaporator
#   p_ref        — imposed pressure at n_acc_out = 100_000 Pa
#                  requires P:n_acc_out
#   mdot_pump    — imposed mass flow at pump = 0.1 kg/s
#                  requires mdot:pump (duplicate, deduplicated by 15F-A)
#   dp_pump      — pressure difference n_acc_out→n_pump_out, delta_p=-50_000
#                  requires P:n_acc_out, P:n_pump_out
#
# Consistent point (all residuals = 0):
#   mdot:pump       = 0.1
#   mdot:evaporator = 0.1
#   P:n_acc_out     = 100_000
#   P:n_pump_out    = 150_000  (= P_acc + 50_000 rise, delta_p = -50_000)
#
# Perturbed point (pressure residual nonzero):
#   P:n_pump_out    = 200_000  (should be 150_000 → residual = 50_000 Pa)


def _make_spec(
    accumulator_role: ScenarioComponentRole = ScenarioComponentRole.ACCUMULATOR,
    pump_role: ScenarioComponentRole = ScenarioComponentRole.PUMP,
    evap_role: ScenarioComponentRole = ScenarioComponentRole.EVAPORATOR,
    cond_role: ScenarioComponentRole = ScenarioComponentRole.CONDENSER,
    scenario_id: str = "hc_closeout",
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
    scenario_id: str = "hc_closeout",
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
    "P:n_pump_out": 200_000.0,
}


# ---------------------------------------------------------------------------
# Story 1 — Full accepted 15H stack with evaluate=False
# ---------------------------------------------------------------------------


class TestStory1FullStackEvaluateFalse:
    """Prove the full diagnostic stack works without evaluation."""

    def setup_method(self) -> None:
        self.sbr = _build_scenario(scenario_id="hc_story1")
        self.bps = _four_blueprints()

    def test_request_constructs_without_side_effects(self) -> None:
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=False,
        )
        assert req.evaluate is False
        assert not hasattr(req, "structural_diagnostic")
        assert not hasattr(req, "selection_workflow_result")

    def test_blueprint_build_result_is_scenario_compatible(self) -> None:
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=False,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert result.blueprint_build_result.scenario_is_compatible is True

    def test_structural_diagnostic_exists(self) -> None:
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=False,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert result.structural_diagnostic is not None

    def test_selection_workflow_result_is_none(self) -> None:
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=False,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert result.selection_workflow_result is None

    def test_selection_and_evaluation_not_performed(self) -> None:
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=False,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert result.selection_requested is False
        assert result.selection_performed is False
        assert result.evaluation_requested is False
        assert result.evaluation_performed is False
        assert result.selected_mode is None

    def test_evaluation_ready_reflects_supplied_values(self) -> None:
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=False,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert result.evaluation_ready is True

    def test_evaluation_ready_false_when_values_omitted(self) -> None:
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            evaluate=False,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert result.evaluation_ready is False

    def test_solve_ready_false_no_solve_true(self) -> None:
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            evaluate=False,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert result.solve_ready is False
        assert result.no_solve is True

    def test_determination_status_set(self) -> None:
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            evaluate=False,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert result.determination_status is not None


# ---------------------------------------------------------------------------
# Story 2 — Full accepted 15H stack with evaluate=True and complete values
# ---------------------------------------------------------------------------


class TestStory2FullStackEvaluateTrueComplete:
    """Prove optional evaluation is gated and delegated correctly."""

    def setup_method(self) -> None:
        self.sbr = _build_scenario(scenario_id="hc_story2")
        self.bps = _four_blueprints()

    def _run(self):
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        return build_configurable_residual_diagnostic_workflow(req)

    def test_structural_diagnostic_exists(self) -> None:
        result = self._run()
        assert result.structural_diagnostic is not None

    def test_diagnostic_evaluation_ready_true(self) -> None:
        result = self._run()
        assert result.evaluation_ready is True

    def test_selection_workflow_result_exists(self) -> None:
        result = self._run()
        assert result.selection_workflow_result is not None

    def test_selected_mode_is_configurable_algebraic(self) -> None:
        result = self._run()
        assert result.selected_mode is ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC

    def test_evaluation_performed(self) -> None:
        result = self._run()
        assert result.evaluation_performed is True

    def test_residuals_zero_at_consistent_point(self) -> None:
        result = self._run()
        eval_r = result.selection_workflow_result.selection_result.evaluation_result
        for name, val in eval_r.residual_values.items():
            assert abs(val) < 1e-9, f"residual {name!r} should be zero; got {val}"
        assert eval_r.max_abs_residual < 1e-9

    def test_no_solve_occurred(self) -> None:
        result = self._run()
        assert result.solve_ready is False
        assert result.no_solve is True

    def test_deferred_reason_empty_when_evaluation_performed(self) -> None:
        result = self._run()
        assert result.deferred_reason == ""

    def test_selection_and_evaluation_flags_set(self) -> None:
        result = self._run()
        assert result.selection_requested is True
        assert result.selection_performed is True
        assert result.evaluation_requested is True


# ---------------------------------------------------------------------------
# Story 3 — Perturbed values produce nonzero residuals but no solve
# ---------------------------------------------------------------------------


class TestStory3PerturbedNonzeroNoSolve:
    """Prove the stack is not hardcoded to success."""

    def setup_method(self) -> None:
        self.sbr = _build_scenario(scenario_id="hc_story3")
        self.bps = _four_blueprints()

    def _run_perturbed(self):
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_PERTURBED_UV,
            evaluate=True,
        )
        return build_configurable_residual_diagnostic_workflow(req)

    def test_diagnostic_still_evaluation_ready_with_perturbed_complete_values(self) -> None:
        result = self._run_perturbed()
        assert result.evaluation_ready is True

    def test_evaluation_performed(self) -> None:
        result = self._run_perturbed()
        assert result.evaluation_performed is True

    def test_residuals_nonzero_at_perturbed_point(self) -> None:
        result = self._run_perturbed()
        eval_r = result.selection_workflow_result.selection_result.evaluation_result
        assert eval_r.max_abs_residual > 1.0

    def test_norm_larger_than_zero_point(self) -> None:
        req_zero = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        r_zero = build_configurable_residual_diagnostic_workflow(req_zero)
        r_pert = self._run_perturbed()
        assert (
            r_pert.selection_workflow_result.selection_result.evaluation_result.l2_norm
            > r_zero.selection_workflow_result.selection_result.evaluation_result.l2_norm + 1.0
        )

    def test_no_correction_or_solve_attempted(self) -> None:
        result = self._run_perturbed()
        assert result.solve_ready is False
        assert result.no_solve is True
        assert not hasattr(result, "converged")
        assert not hasattr(result, "iteration_count")

    def test_no_solve_after_nonzero_residuals(self) -> None:
        result = self._run_perturbed()
        assert result.selection_workflow_result.no_solve is True


# ---------------------------------------------------------------------------
# Story 4 — Missing values defer before 15G-B selection/evaluation
# ---------------------------------------------------------------------------


class TestStory4MissingValuesDefer:
    """Prove conservative gate behavior when unknown values are absent."""

    def setup_method(self) -> None:
        self.sbr = _build_scenario(scenario_id="hc_story4")
        self.bps = _four_blueprints()

    def test_structural_diagnostic_exists_without_values(self) -> None:
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert result.structural_diagnostic is not None

    def test_evaluation_ready_false_when_values_omitted(self) -> None:
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert result.evaluation_ready is False

    def test_selection_workflow_result_is_none(self) -> None:
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert result.selection_workflow_result is None

    def test_selection_and_evaluation_not_performed(self) -> None:
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert result.selection_performed is False
        assert result.evaluation_performed is False

    def test_deferred_reason_references_missing_values(self) -> None:
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert result.deferred_reason != ""
        assert "explicit unknown values were not supplied" in result.deferred_reason

    def test_no_fallback_default_values_created(self) -> None:
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert result.structural_diagnostic.unknown_values_complete is None
        assert result.structural_diagnostic.supplied_unknown_names is None

    def test_partial_values_also_defer(self) -> None:
        partial = {"mdot:pump": 0.1}
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=partial,
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert result.evaluation_ready is False
        assert result.evaluation_performed is False
        assert len(result.missing_from_values) > 0


# ---------------------------------------------------------------------------
# Story 5 — Incompatible blueprints short-circuit before diagnostics
# ---------------------------------------------------------------------------


class TestStory5IncompatibleShortCircuit:
    """Prove unsafe blueprint outputs do not enter diagnostics/selection."""

    def setup_method(self) -> None:
        self.sbr = _build_scenario(scenario_id="hc_story5")
        self.bad_bps = [
            ImposedMassFlowResidualBlueprint(
                residual_name="mdot_bad",
                component_id="nonexistent_component",
                mass_flow=0.1,
            )
        ]

    def test_blueprint_result_is_incompatible(self) -> None:
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bad_bps,
            algebraic_unknown_values={"mdot:nonexistent_component": 0.1},
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert result.blueprint_build_result.scenario_is_compatible is False

    def test_structural_diagnostic_is_none(self) -> None:
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bad_bps,
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert result.structural_diagnostic is None

    def test_selection_workflow_result_is_none(self) -> None:
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bad_bps,
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert result.selection_workflow_result is None

    def test_selected_mode_is_none(self) -> None:
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bad_bps,
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert result.selected_mode is None

    def test_evaluation_not_performed(self) -> None:
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bad_bps,
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert result.evaluation_performed is False

    def test_missing_unknowns_are_deterministic(self) -> None:
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bad_bps,
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert "mdot:nonexistent_component" in result.missing_from_scenario

    def test_no_fallback_to_other_modes(self) -> None:
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bad_bps,
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert result.selected_mode is not ConfigurableResidualMode.DECLARATION_ONLY
        assert result.selected_mode is not ConfigurableResidualMode.CLOSURE_ONLY
        assert result.selected_mode is not ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC
        assert result.selected_mode is None

    def test_determination_status_is_none(self) -> None:
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bad_bps,
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert result.determination_status is None


# ---------------------------------------------------------------------------
# Story 6 — Structurally square is not solve-ready
# ---------------------------------------------------------------------------


class TestStory6SquareNotSolveReady:
    """Prove no misleading readiness for a structurally square system."""

    def setup_method(self) -> None:
        self.sbr = _build_scenario(scenario_id="hc_story6")
        self.bps = _four_blueprints()

    def _run(self):
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        return build_configurable_residual_diagnostic_workflow(req)

    def test_determination_status_is_square(self) -> None:
        result = self._run()
        assert result.determination_status is ResidualDeterminationStatus.SQUARE

    def test_solve_ready_false(self) -> None:
        result = self._run()
        assert result.solve_ready is False

    def test_no_solve_true(self) -> None:
        result = self._run()
        assert result.no_solve is True

    def test_report_limitations_mention_count_only(self) -> None:
        result = self._run()
        report = build_configurable_residual_diagnostic_workflow_report(result)
        limitations = " ".join(report["limitations"])
        assert "count" in limitations.lower() or "structural" in limitations.lower()

    def test_15ha_diagnostic_also_shows_no_solve(self) -> None:
        result = self._run()
        diag = result.structural_diagnostic
        assert diag.solve_ready is False
        assert diag.no_solve is True


# ---------------------------------------------------------------------------
# Story 7 — Underdetermined and overdetermined are count diagnostics only
# ---------------------------------------------------------------------------


class TestStory7UnderdeterminedAndOverdeterminedCountOnly:
    """Prove count classification does not imply solver logic."""

    def setup_method(self) -> None:
        self.sbr = _build_scenario(scenario_id="hc_story7")

    def test_underdetermined_diagnostic_does_not_solve(self) -> None:
        single_bp = [
            MassBalanceResidualBlueprint(
                residual_name="mb_only",
                incoming_component_ids=("pump",),
                outgoing_component_ids=("evaporator",),
            )
        ]
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
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
        extra_bps = _four_blueprints() + [
            ImposedPressureResidualBlueprint(
                residual_name="p_extra",
                node_id="n_pump_out",
                pressure=150_000.0,
            )
        ]
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=extra_bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert (
            result.structural_diagnostic.determination_status
            is ResidualDeterminationStatus.OVERDETERMINED
        )
        assert result.solve_ready is False
        assert result.no_solve is True

    def test_underdetermined_no_rank_or_jacobian_fields(self) -> None:
        single_bp = [
            MassBalanceResidualBlueprint(
                residual_name="mb_only",
                incoming_component_ids=("pump",),
                outgoing_component_ids=("evaporator",),
            )
        ]
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=single_bp,
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert not hasattr(result, "rank")
        assert not hasattr(result, "jacobian")
        assert not hasattr(result, "converged")

    def test_determination_status_is_count_based_only(self) -> None:
        # Direct 15H-A path confirms the count comparison is the sole basis.
        single_bp = [
            MassBalanceResidualBlueprint(
                residual_name="mb_only",
                incoming_component_ids=("pump",),
                outgoing_component_ids=("evaporator",),
            )
        ]
        bp_result = build_configurable_algebraic_residuals_from_blueprints(
            single_bp, scenario_build_result=self.sbr
        )
        diag = evaluate_configurable_residual_structure(bp_result.algebraic_residual_set)
        assert diag.residual_count == 1
        assert diag.required_unknown_count == 2
        assert diag.determination_status is ResidualDeterminationStatus.UNDERDETERMINED


# ---------------------------------------------------------------------------
# Story 8 — Role and component labels remain metadata only
# ---------------------------------------------------------------------------


class TestStory8RolesRemainMetadataOnly:
    """Prove no role/component-type dispatch in the diagnostic workflow."""

    def test_different_roles_same_diagnostic_results(self) -> None:
        sbr_specific = _build_scenario(scenario_id="hc_story8_specific")
        sbr_generic = _build_scenario(
            accumulator_role=ScenarioComponentRole.GENERIC,
            pump_role=ScenarioComponentRole.GENERIC,
            evap_role=ScenarioComponentRole.GENERIC,
            cond_role=ScenarioComponentRole.GENERIC,
            scenario_id="hc_story8_generic",
        )
        bps = _four_blueprints()

        req_specific = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr_specific,
            blueprints=bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        req_generic = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr_generic,
            blueprints=bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        r_specific = build_configurable_residual_diagnostic_workflow(req_specific)
        r_generic = build_configurable_residual_diagnostic_workflow(req_generic)

        assert r_specific.required_unknown_names == r_generic.required_unknown_names
        assert r_specific.determination_status == r_generic.determination_status
        assert r_specific.missing_from_scenario == r_generic.missing_from_scenario
        assert r_specific.evaluation_ready == r_generic.evaluation_ready
        assert r_specific.selected_mode == r_generic.selected_mode

    def test_component_ids_used_as_identifier_strings_not_physics(self) -> None:
        sbr = _build_scenario(scenario_id="hc_story8_id")
        bp = ImposedMassFlowResidualBlueprint(
            residual_name="mdot_condenser_label",
            component_id="condenser",
            mass_flow=0.05,
        )
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=[bp],
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert "mdot:condenser" in result.required_unknown_names
        assert result.blueprint_build_result.scenario_is_compatible is True

    def test_pump_component_id_no_physics_dispatch(self) -> None:
        sbr = _build_scenario(scenario_id="hc_story8_pump")
        bp = ImposedMassFlowResidualBlueprint(
            residual_name="mdot_pump_only",
            component_id="pump",
            mass_flow=0.1,
        )
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=[bp],
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert result.required_unknown_names == ("mdot:pump",)

    def test_inference_flags_all_false_across_roles(self) -> None:
        sbr = _build_scenario(scenario_id="hc_story8_flags")
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert result.residuals_inferred_from_roles is False
        assert result.residuals_inferred_from_topology is False
        assert result.blueprints_inferred_from_roles is False
        assert result.blueprints_inferred_from_topology is False
        assert result.closures_inferred_from_roles is False
        assert result.production_components_executed is False


# ---------------------------------------------------------------------------
# Story 9 — Topology changes do not create extra diagnostics requirements
# ---------------------------------------------------------------------------


class TestStory9TopologyDoesNotCreateRequirements:
    """Prove topology is not used to generate requirements."""

    def test_same_blueprints_different_topology_give_same_required_unknowns(self) -> None:
        spec_a = _make_spec(scenario_id="hc_story9_a")
        spec_b = ConfigurableScenarioSpec(
            scenario_id="hc_story9_b",
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

        req_a = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr_a,
            blueprints=bps,
        )
        req_b = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr_b,
            blueprints=bps,
        )
        r_a = build_configurable_residual_diagnostic_workflow(req_a)
        r_b = build_configurable_residual_diagnostic_workflow(req_b)

        assert r_a.required_unknown_names == r_b.required_unknown_names
        assert r_a.determination_status == r_b.determination_status

    def test_extra_topology_does_not_add_residuals_or_unknowns(self) -> None:
        spec_b = ConfigurableScenarioSpec(
            scenario_id="hc_story9_c",
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
        single_bp = [ImposedPressureResidualBlueprint("p_only", "n_acc_out", 1e5)]
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr_b,
            blueprints=single_bp,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert result.required_unknown_names == ("P:n_acc_out",)
        assert result.blueprint_build_result.blueprint_count == 1


# ---------------------------------------------------------------------------
# Story 10 — Direct lower layers remain independent
# ---------------------------------------------------------------------------


class TestStory10DirectLowerLayersRemainIndependent:
    """Prove closeout did not alter lower layers."""

    def setup_method(self) -> None:
        self.sbr = _build_scenario(scenario_id="hc_story10")
        self.bps = _four_blueprints()

    def test_direct_15ha_evaluate_configurable_residual_structure_works(self) -> None:
        bp_result = build_configurable_algebraic_residuals_from_blueprints(
            self.bps, scenario_build_result=self.sbr
        )
        diag = evaluate_configurable_residual_structure(
            bp_result.algebraic_residual_set,
            scenario_build_result=self.sbr,
            unknown_values=_ZERO_UV,
        )
        assert diag.evaluation_ready is True
        assert diag.solve_ready is False

    def test_direct_15hb_diagnostic_workflow_works_independently(self) -> None:
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert result.evaluation_performed is True

    def test_direct_15gb_blueprint_workflow_still_works(self) -> None:
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        assert result.evaluation_performed is True
        assert result.selected_mode is ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC

    def test_direct_15fb_configurable_algebraic_selection_still_works(self) -> None:
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
        result = select_configurable_residual_strategy(req)
        assert result.selected_mode is ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC
        assert result.evaluation_performed is True

    def test_direct_15fa_algebraic_evaluation_still_works(self) -> None:
        # Use the approved direct path: build via 15G-A then evaluate directly.
        bp_result = build_configurable_algebraic_residuals_from_blueprints(
            self.bps, scenario_build_result=self.sbr
        )
        eval_result = evaluate_configurable_algebraic_residuals(
            bp_result.algebraic_residual_set, _ZERO_UV
        )
        assert eval_result.max_abs_residual < 1e-9
        assert eval_result.no_solve is True

    def test_15hb_and_15gb_produce_equivalent_evaluation_results(self) -> None:
        req_15hb = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        r_15hb = build_configurable_residual_diagnostic_workflow(req_15hb)

        req_15gb = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        r_15gb = build_configurable_residual_selection_from_blueprints(req_15gb)

        eval_15hb = r_15hb.selection_workflow_result.selection_result.evaluation_result
        eval_15gb = r_15gb.selection_result.evaluation_result

        assert eval_15hb.residual_names == eval_15gb.residual_names
        for name in eval_15hb.residual_names:
            assert eval_15hb.residual_values[name] == pytest.approx(
                eval_15gb.residual_values[name], abs=1e-12
            )


# ---------------------------------------------------------------------------
# Story 11 — Report stack is composable and JSON-serializable
# ---------------------------------------------------------------------------


class TestStory11ReportStackComposableAndSerializable:
    """Prove the reporting stack is honest and JSON-serializable."""

    def setup_method(self) -> None:
        self.sbr = _build_scenario(scenario_id="hc_story11")
        self.bps = _four_blueprints()

    def test_scenario_report_serializable(self) -> None:
        report = build_configurable_scenario_report(self.sbr)
        assert isinstance(json.dumps(report), str)

    def test_blueprint_report_serializable(self) -> None:
        bp_result = build_configurable_algebraic_residuals_from_blueprints(
            self.bps, scenario_build_result=self.sbr
        )
        report = build_configurable_residual_blueprint_report(bp_result)
        assert isinstance(json.dumps(report), str)

    def test_diagnostic_report_serializable(self) -> None:
        bp_result = build_configurable_algebraic_residuals_from_blueprints(
            self.bps, scenario_build_result=self.sbr
        )
        diag = evaluate_configurable_residual_structure(
            bp_result.algebraic_residual_set,
            scenario_build_result=self.sbr,
            unknown_values=_ZERO_UV,
        )
        report = build_configurable_residual_diagnostic_report(diag)
        assert isinstance(json.dumps(report), str)

    def test_15gb_workflow_report_serializable(self) -> None:
        req = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = build_configurable_residual_selection_from_blueprints(req)
        report = build_configurable_residual_blueprint_workflow_report(result)
        assert isinstance(json.dumps(report), str)

    def test_15hb_diagnostic_workflow_report_serializable(self) -> None:
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        report = build_configurable_residual_diagnostic_workflow_report(result)
        assert isinstance(json.dumps(report), str)

    def test_combined_report_stack_json_serializable(self) -> None:
        scenario_report = build_configurable_scenario_report(self.sbr)

        bp_result = build_configurable_algebraic_residuals_from_blueprints(
            self.bps, scenario_build_result=self.sbr
        )
        blueprint_report = build_configurable_residual_blueprint_report(bp_result)

        diag = evaluate_configurable_residual_structure(
            bp_result.algebraic_residual_set,
            scenario_build_result=self.sbr,
            unknown_values=_ZERO_UV,
        )
        diagnostic_report = build_configurable_residual_diagnostic_report(diag)

        req_15gb = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        r_15gb = build_configurable_residual_selection_from_blueprints(req_15gb)
        workflow_15gb_report = build_configurable_residual_blueprint_workflow_report(r_15gb)

        req_15hb = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        r_15hb = build_configurable_residual_diagnostic_workflow(req_15hb)
        workflow_15hb_report = build_configurable_residual_diagnostic_workflow_report(r_15hb)

        combined: dict[str, object] = {
            "block": "15H-C",
            "scenario_report": scenario_report,
            "blueprint_report": blueprint_report,
            "diagnostic_report": diagnostic_report,
            "workflow_15gb_report": workflow_15gb_report,
            "workflow_15hb_report": workflow_15hb_report,
        }
        serialized = json.dumps(combined)
        parsed = json.loads(serialized)
        assert isinstance(serialized, str)
        assert parsed["block"] == "15H-C"

    def test_combined_report_states_no_solve_throughout(self) -> None:
        scenario_report = build_configurable_scenario_report(self.sbr)
        bp_result = build_configurable_algebraic_residuals_from_blueprints(
            self.bps, scenario_build_result=self.sbr
        )
        blueprint_report = build_configurable_residual_blueprint_report(bp_result)

        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        workflow_report = build_configurable_residual_diagnostic_workflow_report(result)

        assert scenario_report.get("no_solve") is True
        assert blueprint_report.get("no_solve") is True
        assert workflow_report["no_solve"] is True
        assert workflow_report["solve_ready"] is False

    def test_combined_report_states_no_direct_15fa_evaluation(self) -> None:
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        report = build_configurable_residual_diagnostic_workflow_report(result)
        limitations = " ".join(report["limitations"])
        assert "evaluate_configurable_algebraic_residuals" in limitations
        assert "does not evaluate residuals directly" in limitations

    def test_combined_report_states_no_role_inference(self) -> None:
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        report = build_configurable_residual_diagnostic_workflow_report(result)
        assert report["residuals_inferred_from_roles"] is False
        assert report["blueprints_inferred_from_roles"] is False
        assert report["closures_inferred_from_roles"] is False

    def test_combined_report_states_no_topology_inference(self) -> None:
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        report = build_configurable_residual_diagnostic_workflow_report(result)
        assert report["residuals_inferred_from_topology"] is False
        assert report["blueprints_inferred_from_topology"] is False

    def test_combined_report_states_no_production_execution(self) -> None:
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        report = build_configurable_residual_diagnostic_workflow_report(result)
        assert report["production_components_executed"] is False

    def test_no_file_writing_smoke_test(self) -> None:
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=self.sbr,
            blueprints=self.bps,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        report = build_configurable_residual_diagnostic_workflow_report(result)
        assert isinstance(report, dict)


# ---------------------------------------------------------------------------
# Story 12 — Production contract remains frozen
# ---------------------------------------------------------------------------


class TestStory12ProductionContractFrozen:
    """Known production classes must still report NO_CONTRIBUTE_METHOD."""

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
    """Architecture boundary checks proving Block 15H-C introduces no new

    runtime modules and that the existing 15H-A/15H-B modules still respect
    every architecture invariant. Source-level checks scan only import lines
    or specific function source, not full module source, to avoid docstring
    false positives.
    """

    # B1 — no CoolProp / PropertyBackend / CorrelationRegistry

    def test_b1_diagnostic_workflow_module_no_coolprop_import(self) -> None:
        imports = _import_lines(_DIAG_WF_MOD)
        assert "CoolProp" not in imports
        assert not hasattr(_DIAG_WF_MOD, "CoolProp")

    def test_b1_diagnostics_module_no_coolprop_import(self) -> None:
        imports = _import_lines(_DIAG_MOD)
        assert "CoolProp" not in imports
        assert not hasattr(_DIAG_MOD, "CoolProp")

    def test_b1_no_property_backend_import(self) -> None:
        for mod in (_DIAG_WF_MOD, _DIAG_MOD):
            imports = _import_lines(mod)
            assert "PropertyBackend" not in imports
            assert not hasattr(mod, "PropertyBackend")

    def test_b1_no_correlation_registry_import(self) -> None:
        for mod in (_DIAG_WF_MOD, _DIAG_MOD):
            imports = _import_lines(mod)
            assert "CorrelationRegistry" not in imports
            assert not hasattr(mod, "CorrelationRegistry")

    def test_b1_no_mpl_sim_properties_or_correlations_import(self) -> None:
        for mod in (_DIAG_WF_MOD, _DIAG_MOD):
            imports = _import_lines(mod)
            assert "mpl_sim.properties" not in imports
            assert "mpl_sim.correlations" not in imports

    # B2 — no HX model imports/calls

    def test_b2_no_hx_models_import(self) -> None:
        for mod in (_DIAG_WF_MOD, _DIAG_MOD):
            imports = _import_lines(mod)
            assert "hx_models" not in imports
            assert not hasattr(mod, "HeatExchangerModelRegistry")

    # B3 — no production component execution imports

    def test_b3_no_mpl_sim_components_import(self) -> None:
        for mod in (_DIAG_WF_MOD, _DIAG_MOD):
            imports = _import_lines(mod)
            assert "mpl_sim.components" not in imports

    def test_b3_no_pump_evaporator_condenser_references(self) -> None:
        for mod in (_DIAG_WF_MOD, _DIAG_MOD):
            src = inspect.getsource(mod)
            assert "PumpComponent" not in src
            assert "EvaporatorComponent" not in src
            assert "CondenserComponent" not in src
            assert "AccumulatorComponent" not in src

    # B4 — no SystemState or FluidState

    def test_b4_no_system_state(self) -> None:
        for mod in (_DIAG_WF_MOD, _DIAG_MOD):
            imports = _import_lines(mod)
            assert "SystemState" not in imports
            assert not hasattr(mod, "SystemState")

    def test_b4_no_fluid_state(self) -> None:
        for mod in (_DIAG_WF_MOD, _DIAG_MOD):
            imports = _import_lines(mod)
            assert "FluidState" not in imports
            assert not hasattr(mod, "FluidState")

    # B5 — no production contribute(...)

    def test_b5_no_contribute_definition(self) -> None:
        for mod in (_DIAG_WF_MOD, _DIAG_MOD):
            src = inspect.getsource(mod)
            assert "def contribute" not in src

    def test_b5_no_dot_contribute_call(self) -> None:
        for mod in (_DIAG_WF_MOD, _DIAG_MOD):
            src = inspect.getsource(mod)
            assert ".contribute(" not in src

    def test_b5_no_contribute_attribute(self) -> None:
        for mod in (_DIAG_WF_MOD, _DIAG_MOD):
            assert not hasattr(mod, "contribute")

    # B6 — no component_type / role-based physics dispatch

    def test_b6_diagnostic_workflow_no_role_dispatch(self) -> None:
        src_fn = inspect.getsource(_DIAG_WF_MOD.build_configurable_residual_diagnostic_workflow)
        assert "component_type" not in src_fn
        assert ".role" not in src_fn

    def test_b6_diagnostics_no_role_dispatch(self) -> None:
        src_fn = inspect.getsource(_DIAG_MOD.evaluate_configurable_residual_structure)
        assert "component_type" not in src_fn
        assert ".role" not in src_fn

    # B7 — no automatic blueprint/residual/closure inference from role or topology

    def test_b7_no_role_inference_functions(self) -> None:
        for mod in (_DIAG_WF_MOD, _DIAG_MOD):
            src = inspect.getsource(mod)
            assert "infer_residuals_from_role" not in src
            assert "infer_blueprints_from_role" not in src
            assert "generate_residuals_from_role" not in src

    def test_b7_no_topology_inference_functions(self) -> None:
        for mod in (_DIAG_WF_MOD, _DIAG_MOD):
            src = inspect.getsource(mod)
            assert "infer_residuals_from_topology" not in src
            assert "infer_blueprints_from_topology" not in src
            assert "generate_residuals_from_topology" not in src

    def test_b7_no_graph_edge_inspection(self) -> None:
        for mod in (_DIAG_WF_MOD, _DIAG_MOD):
            src = inspect.getsource(mod)
            assert "graph.edges" not in src
            assert "graph.instances" not in src

    def test_b7_no_closure_auto_inference(self) -> None:
        for mod in (_DIAG_WF_MOD, _DIAG_MOD):
            src = inspect.getsource(mod)
            assert "auto_closure" not in src
            assert "closure_from_role" not in src
            assert "infer_closure" not in src

    # B8 — no generic solve(network), NetworkGraph.solve(), or named solvers

    def test_b8_no_network_graph_attribute(self) -> None:
        for mod in (_DIAG_WF_MOD, _DIAG_MOD):
            assert not hasattr(mod, "NetworkGraph")

    def test_b8_no_solve_network_function_defined(self) -> None:
        for mod in (_DIAG_WF_MOD, _DIAG_MOD):
            src = inspect.getsource(mod)
            assert "def solve_network" not in src
            assert "def solve(" not in src

    def test_b8_no_named_solver_imports(self) -> None:
        for mod in (_DIAG_WF_MOD, _DIAG_MOD):
            imports = _import_lines(mod)
            assert "solve_fixed_single_loop_residuals" not in imports
            assert "solve_network_residual_problem" not in imports

    def test_b8_no_named_solver_calls_in_source(self) -> None:
        for mod in (_DIAG_WF_MOD, _DIAG_MOD):
            src = inspect.getsource(mod)
            assert "solve_fixed_single_loop_residuals(" not in src
            assert "solve_network_residual_problem(" not in src

    # B9 — no file writing / report output

    def test_b9_no_file_writes(self) -> None:
        for mod in (_DIAG_WF_MOD, _DIAG_MOD):
            src = inspect.getsource(mod)
            assert "write_text" not in src
            assert "to_csv" not in src
            assert "to_json" not in src
            assert "open(" not in src

    # B10 — no root/least-squares/Jacobian/rank/pseudo-inverse solving

    def test_b10_no_root_finding_imports(self) -> None:
        for mod in (_DIAG_WF_MOD, _DIAG_MOD):
            imports = _import_lines(mod)
            assert "least_squares" not in imports
            assert "lstsq" not in imports
            assert "fsolve" not in imports
            assert "scipy.optimize" not in imports
            assert "numpy" not in imports

    def test_b10_no_root_finding_calls_in_source(self) -> None:
        for mod in (_DIAG_WF_MOD, _DIAG_MOD):
            src = inspect.getsource(mod)
            assert "least_squares(" not in src
            assert "fsolve(" not in src
            assert "minimize(" not in src

    def test_b10_no_jacobian_rank_pinv_in_source(self) -> None:
        for mod in (_DIAG_WF_MOD, _DIAG_MOD):
            src = inspect.getsource(mod)
            assert "pinv(" not in src
            assert "matrix_rank(" not in src
            assert "np.linalg" not in src
            assert "scipy.linalg" not in src

    def test_b10_result_has_no_solver_fields(self) -> None:
        sbr = _build_scenario(scenario_id="hc_b10")
        req = ConfigurableResidualDiagnosticWorkflowRequest(
            scenario_build_result=sbr,
            blueprints=_four_blueprints(),
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = build_configurable_residual_diagnostic_workflow(req)
        assert not hasattr(result, "converged")
        assert not hasattr(result, "iteration_count")
        assert not hasattr(result, "solution")
        assert not hasattr(result, "rank")
        assert not hasattr(result, "jacobian")

    # B11 — no direct 15F-A/15F-B evaluation calls from 15H-B workflow module

    def test_b11_diagnostic_workflow_no_direct_15fa_call(self) -> None:
        src = inspect.getsource(_DIAG_WF_MOD.build_configurable_residual_diagnostic_workflow)
        assert "evaluate_configurable_algebraic_residuals(" not in src

    def test_b11_diagnostic_workflow_no_direct_15fb_call(self) -> None:
        src = inspect.getsource(_DIAG_WF_MOD.build_configurable_residual_diagnostic_workflow)
        assert "evaluate_selected_configurable_residuals(" not in src

    def test_b11_diagnostic_workflow_module_no_direct_eval_imports(self) -> None:
        imports = _import_lines(_DIAG_WF_MOD)
        assert "evaluate_configurable_algebraic_residuals" not in imports
        assert "evaluate_selected_configurable_residuals" not in imports
