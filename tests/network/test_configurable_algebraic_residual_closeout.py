"""Acceptance / closeout tests for Block 15F-C.

Proves that the complete Block 15F configurable algebraic residual stack works
coherently end-to-end across:
  - 15F-A configurable algebraic residual declarations and evaluation
  - 15F-B configurable algebraic residual selection integration
  - 15E-A configurable scenario declaration builder
  - 15E-B explicit residual selection stack
  - 15E-C configurable selection closeout
  - existing 15D closure integration and fixed MVP residual layers

Acceptance stories
------------------
1   End-to-end configurable algebraic evaluation path: build scenario, declare
    residuals, select CONFIGURABLE_ALGEBRAIC, evaluate, verify report flags.
2   Perturbed explicit unknowns produce nonzero residuals (real evaluation).
3   Pure selection remains pure: evaluate=False suppresses evaluation;
    evaluate_selected_configurable_residuals raises when eval not performed.
4   Missing scenario unknowns reject compatibility with deterministic reasons.
5   Missing algebraic unknown values defer evaluation; compatibility remains True.
6   Role changes do not alter algebraic residual behavior.
7   Topology does not generate algebraic residuals; missing set → rejected.
8   Existing modes remain independent of algebraic residual fields.
9   Reports from all stack layers are composable and JSON-serializable.
10  Production contract remains frozen — six known classes still NO_CONTRIBUTE_METHOD.

Boundary / negative acceptance tests
--------------------------------------
B1  solve_fixed_single_loop_residuals is NOT referenced in the algebraic
    residual selection path.
B2  No generic solve(network) or NetworkGraph.solve in the modules.
B3  No SystemState or FluidState in the configurable algebraic modules.
B4  No CoolProp, PropertyBackend, or CorrelationRegistry in the modules.
B5  No HX-model imports or calls in the modules.
B6  No production component execution in the modules.
B7  No contribute(...) method definition or call in the modules.
B8  No role-based physics dispatch in the modules.
B9  No topology-based residual inference in the modules.
B10 No automatic closure inference in the modules.
B11 No root/least-squares/minimize in the modules.

These tests do NOT:
  - Call any solver or root-finder.
  - Execute production component physics.
  - Call CoolProp, PropertyBackend, or correlations.
  - Assemble SystemState or construct FluidState.
  - Write files, use pandas, or use numpy.
  - Infer residuals from roles or topology.
"""

from __future__ import annotations

import importlib
import inspect
import json

import pytest

from mpl_sim.network.closure_integration import (
    build_combined_closure_residuals,
)
from mpl_sim.network.configurable_algebraic_residuals import (
    ConfigurableAlgebraicResidualEvaluationResult,
    ConfigurableAlgebraicResidualSet,
    ImposedMassFlowResidualDeclaration,
    ImposedPressureResidualDeclaration,
    MassBalanceResidualDeclaration,
    PressureDifferenceResidualDeclaration,
    build_configurable_algebraic_residual_report,
    build_configurable_algebraic_residual_set,
    evaluate_configurable_algebraic_residuals,
    validate_algebraic_residuals_against_scenario,
)
from mpl_sim.network.configurable_residual_selection import (
    ConfigurableResidualMode,
    ConfigurableResidualSelectionRequest,
    build_configurable_residual_selection_report,
    evaluate_selected_configurable_residuals,
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
from mpl_sim.network.fixed_single_loop_residuals import FixedSingleLoopResidualParameters
from mpl_sim.network.hydraulic_closures import (
    ImposedMassFlowClosure,
    build_hydraulic_closure_residuals,
)
from mpl_sim.network.production_component_inspection import (
    ProductionComponentContractStatus,
    inspect_known_production_component_contracts,
)

# Modules loaded once for source inspection
_CAR_MOD = importlib.import_module("mpl_sim.network.configurable_algebraic_residuals")
_CRS_MOD = importlib.import_module("mpl_sim.network.configurable_residual_selection")

# ---------------------------------------------------------------------------
# Shared scenario helpers
# ---------------------------------------------------------------------------
#
# 3-component single-branch loop:
#   Components : pump, evaporator, condenser
#   Nodes      : n_pump_out, n_evap_out, n_cond_out
#   Unknowns   : mdot:pump, mdot:evaporator, mdot:condenser
#                P:n_pump_out, P:n_evap_out, P:n_cond_out
#
# Consistent algebraic point:
#   mdot_imposed   = 1.0 kg/s  (all mass flows equal in single branch)
#   P_pump_imposed = 200_000 Pa
#   evap_drop      = 50_000 Pa  →  P:n_evap_out = 150_000 Pa
#   cond_drop      = 30_000 Pa  →  P:n_cond_out = 120_000 Pa


_MDOT_IMPOSED = 1.0
_P_PUMP_IMPOSED = 200_000.0
_EVAP_DROP = 50_000.0
_COND_DROP = 30_000.0

_ZERO_UV: dict[str, float] = {
    "mdot:pump": _MDOT_IMPOSED,
    "mdot:evaporator": _MDOT_IMPOSED,
    "mdot:condenser": _MDOT_IMPOSED,
    "P:n_pump_out": _P_PUMP_IMPOSED,
    "P:n_evap_out": _P_PUMP_IMPOSED - _EVAP_DROP,
    "P:n_cond_out": _P_PUMP_IMPOSED - _EVAP_DROP - _COND_DROP,
}

_PERTURBED_UV: dict[str, float] = {
    **_ZERO_UV,
    "P:n_evap_out": 999_999.0,
}


def _make_spec(
    pump_role: ScenarioComponentRole = ScenarioComponentRole.PUMP,
    evap_role: ScenarioComponentRole = ScenarioComponentRole.EVAPORATOR,
    cond_role: ScenarioComponentRole = ScenarioComponentRole.CONDENSER,
    scenario_id: str = "fc_closeout",
) -> ConfigurableScenarioSpec:
    return ConfigurableScenarioSpec(
        scenario_id=scenario_id,
        components=(
            ScenarioComponentSpec("pump", pump_role),
            ScenarioComponentSpec("evaporator", evap_role),
            ScenarioComponentSpec("condenser", cond_role),
        ),
        nodes=(
            ScenarioNodeSpec("n_pump_out"),
            ScenarioNodeSpec("n_evap_out"),
            ScenarioNodeSpec("n_cond_out"),
        ),
        connections=(
            ScenarioConnectionSpec("pump", "n_cond_out", "n_pump_out"),
            ScenarioConnectionSpec("evaporator", "n_pump_out", "n_evap_out"),
            ScenarioConnectionSpec("condenser", "n_evap_out", "n_cond_out"),
        ),
    )


def _build_scenario(
    pump_role: ScenarioComponentRole = ScenarioComponentRole.PUMP,
    evap_role: ScenarioComponentRole = ScenarioComponentRole.EVAPORATOR,
    cond_role: ScenarioComponentRole = ScenarioComponentRole.CONDENSER,
    scenario_id: str = "fc_closeout",
) -> ConfigurableScenarioBuildResult:
    return build_configurable_scenario(_make_spec(pump_role, evap_role, cond_role, scenario_id))


def _make_residual_set() -> ConfigurableAlgebraicResidualSet:
    """Standard 6-residual set for the 3-component loop.

    Residuals:
      r_mb_pump_out  = mdot:pump - mdot:evaporator
      r_mb_evap_out  = mdot:evaporator - mdot:condenser
      r_P_pump_out   = P:n_pump_out - P_pump_imposed
      r_dp_evap      = P:n_evap_out - P:n_pump_out + evap_drop
      r_dp_cond      = P:n_cond_out - P:n_evap_out + cond_drop
      r_mdot_pump    = mdot:pump - mdot_imposed
    """
    return build_configurable_algebraic_residual_set(
        [
            MassBalanceResidualDeclaration(
                residual_name="r_mb_pump_out",
                incoming_unknown_names=("mdot:pump",),
                outgoing_unknown_names=("mdot:evaporator",),
            ),
            MassBalanceResidualDeclaration(
                residual_name="r_mb_evap_out",
                incoming_unknown_names=("mdot:evaporator",),
                outgoing_unknown_names=("mdot:condenser",),
            ),
            ImposedPressureResidualDeclaration(
                residual_name="r_P_pump_out",
                pressure_unknown="P:n_pump_out",
                imposed_value=_P_PUMP_IMPOSED,
            ),
            PressureDifferenceResidualDeclaration(
                residual_name="r_dp_evap",
                inlet_pressure_unknown="P:n_pump_out",
                outlet_pressure_unknown="P:n_evap_out",
                delta_p=_EVAP_DROP,
            ),
            PressureDifferenceResidualDeclaration(
                residual_name="r_dp_cond",
                inlet_pressure_unknown="P:n_evap_out",
                outlet_pressure_unknown="P:n_cond_out",
                delta_p=_COND_DROP,
            ),
            ImposedMassFlowResidualDeclaration(
                residual_name="r_mdot_pump",
                mass_flow_unknown="mdot:pump",
                imposed_value=_MDOT_IMPOSED,
            ),
        ]
    )


def _make_closure_set():
    hyd = build_hydraulic_closure_residuals(
        closures=(
            ImposedMassFlowClosure(
                unknown_name="mdot_loop",
                imposed_value=1.0,
                residual_name="r_mdot_imposed",
            ),
        )
    )
    return build_combined_closure_residuals(hydraulic=hyd)


# ---------------------------------------------------------------------------
# Story 1 — End-to-end configurable algebraic evaluation path
# ---------------------------------------------------------------------------


class TestStory1EndToEndEvaluationPath:
    """Prove the full 15F configurable algebraic evaluation path works end-to-end."""

    def setup_method(self) -> None:
        self.build_result = _build_scenario()
        self.residual_set = _make_residual_set()

    def test_mode_is_enum_member(self) -> None:
        assert ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC in ConfigurableResidualMode

    def test_scenario_has_expected_unknowns(self) -> None:
        assert "mdot:pump" in self.build_result.unknown_names
        assert "P:n_pump_out" in self.build_result.unknown_names

    def test_residual_set_has_six_declarations(self) -> None:
        assert self.residual_set.count == 6

    def test_selection_is_compatible(self) -> None:
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=self.residual_set,
        )
        result = select_configurable_residual_strategy(req)
        assert result.compatibility.is_compatible is True
        assert result.selected_mode is ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC

    def test_evaluation_at_zero_residual_point(self) -> None:
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=self.residual_set,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.evaluation_performed is True
        assert result.evaluation_deferred is False
        assert isinstance(result.evaluation_result, ConfigurableAlgebraicResidualEvaluationResult)
        for name, val in result.evaluation_result.residual_values.items():
            assert abs(val) < 1e-9, f"residual {name!r} should be zero; got {val}"
        assert result.evaluation_result.max_abs_residual < 1e-9
        assert result.evaluation_result.l2_norm < 1e-9

    def test_no_solve_always_true(self) -> None:
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=self.residual_set,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.no_solve is True
        assert result.evaluation_result.no_solve is True

    def test_report_flags(self) -> None:
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=self.residual_set,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        assert report["no_solve"] is True
        assert report["roles_selected_physics"] is False
        assert report["closures_inferred_from_roles"] is False
        assert report["residuals_inferred_from_roles"] is False
        assert report["residuals_inferred_from_topology"] is False

    def test_report_selected_mode(self) -> None:
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=self.residual_set,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        assert report["selected_mode"] == "configurable_algebraic"

    def test_report_is_json_serializable(self) -> None:
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=self.residual_set,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        serialized = json.dumps(report)
        assert isinstance(serialized, str)
        assert len(serialized) > 0

    def test_evaluation_result_unknown_names_used(self) -> None:
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=self.residual_set,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert len(result.evaluation_result.unknown_names_used) > 0
        assert all(
            n in self.build_result.unknown_names
            for n in result.evaluation_result.unknown_names_used
        )


# ---------------------------------------------------------------------------
# Story 2 — Perturbed explicit unknowns produce nonzero residuals
# ---------------------------------------------------------------------------


class TestStory2PerturbedNonzeroResiduals:
    """Prove the evaluation path does real algebraic computation, not hardcoded success."""

    def setup_method(self) -> None:
        self.build_result = _build_scenario()
        self.residual_set = _make_residual_set()

    def test_perturbed_gives_nonzero(self) -> None:
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=self.residual_set,
            algebraic_unknown_values=_PERTURBED_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.evaluation_performed is True
        rv = result.evaluation_result.residual_values
        assert abs(rv["r_dp_evap"]) > 1.0

    def test_norm_increases_relative_to_zero_point(self) -> None:
        req_zero = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=self.residual_set,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        req_perturbed = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=self.residual_set,
            algebraic_unknown_values=_PERTURBED_UV,
            evaluate=True,
        )
        r_zero = select_configurable_residual_strategy(req_zero)
        r_perturbed = select_configurable_residual_strategy(req_perturbed)
        assert r_perturbed.evaluation_result.l2_norm > r_zero.evaluation_result.l2_norm + 1.0

    def test_no_solve_attempted(self) -> None:
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=self.residual_set,
            algebraic_unknown_values=_PERTURBED_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        # No solve: evaluation returned nonzero residuals and that is the end.
        assert result.no_solve is True
        assert result.evaluation_result.no_solve is True

    def test_direct_evaluation_api_also_perturbed(self) -> None:
        direct = evaluate_configurable_algebraic_residuals(self.residual_set, _PERTURBED_UV)
        assert direct.max_abs_residual > 1.0
        assert direct.no_solve is True

    def test_mass_balance_residuals_still_zero_after_pressure_perturbation(self) -> None:
        # Mass-balance residuals depend only on mdot unknowns; perturbing a
        # pressure unknown should leave them zero.
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=self.residual_set,
            algebraic_unknown_values=_PERTURBED_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        rv = result.evaluation_result.residual_values
        assert abs(rv["r_mb_pump_out"]) < 1e-9
        assert abs(rv["r_mb_evap_out"]) < 1e-9


# ---------------------------------------------------------------------------
# Story 3 — Pure selection remains pure
# ---------------------------------------------------------------------------


class TestStory3PureSelectionRemainsPure:
    """Prove evaluate=False suppresses evaluation; evaluate_selected raises clearly."""

    def setup_method(self) -> None:
        self.build_result = _build_scenario()
        self.residual_set = _make_residual_set()

    def test_selection_without_evaluate_is_compatible(self) -> None:
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=self.residual_set,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=False,
        )
        result = select_configurable_residual_strategy(req)
        assert result.compatibility.is_compatible is True

    def test_evaluation_not_performed_when_false(self) -> None:
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=self.residual_set,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=False,
        )
        result = select_configurable_residual_strategy(req)
        assert result.evaluation_performed is False
        assert result.evaluation_result is None
        assert result.evaluation_deferred is True

    def test_deferred_reason_is_clear(self) -> None:
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=self.residual_set,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=False,
        )
        result = select_configurable_residual_strategy(req)
        assert result.evaluation_deferred_reason
        assert len(result.evaluation_deferred_reason) > 0

    def test_evaluate_selected_raises_when_evaluate_false(self) -> None:
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=self.residual_set,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=False,
        )
        with pytest.raises(ValueError):
            evaluate_selected_configurable_residuals(req)

    def test_no_solve_even_when_selection_only(self) -> None:
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=self.residual_set,
            evaluate=False,
        )
        result = select_configurable_residual_strategy(req)
        assert result.no_solve is True


# ---------------------------------------------------------------------------
# Story 4 — Missing scenario unknowns reject compatibility
# ---------------------------------------------------------------------------


class TestStory4MissingScenarioUnknownsReject:
    """Prove declared residuals are validated against scenario unknown names."""

    def setup_method(self) -> None:
        self.build_result = _build_scenario()

    def _make_bad_residual_set(self) -> ConfigurableAlgebraicResidualSet:
        return build_configurable_algebraic_residual_set(
            [
                ImposedPressureResidualDeclaration(
                    residual_name="r_bad_unknown",
                    pressure_unknown="P:n_NONEXISTENT_node",
                    imposed_value=100_000.0,
                ),
            ]
        )

    def test_compatibility_is_false(self) -> None:
        bad_set = self._make_bad_residual_set()
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=bad_set,
            algebraic_unknown_values={"P:n_NONEXISTENT_node": 1.0},
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.compatibility.is_compatible is False

    def test_missing_unknown_appears_in_reasons(self) -> None:
        bad_set = self._make_bad_residual_set()
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=bad_set,
            algebraic_unknown_values={"P:n_NONEXISTENT_node": 1.0},
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        reasons_str = " ".join(result.compatibility.reasons)
        assert "n_NONEXISTENT_node" in reasons_str or "missing" in reasons_str.lower()

    def test_evaluation_not_performed_when_incompatible(self) -> None:
        bad_set = self._make_bad_residual_set()
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=bad_set,
            algebraic_unknown_values={"P:n_NONEXISTENT_node": 1.0},
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.evaluation_performed is False

    def test_no_fallback_to_other_mode(self) -> None:
        bad_set = self._make_bad_residual_set()
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=bad_set,
        )
        result = select_configurable_residual_strategy(req)
        assert result.selected_mode is ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC

    def test_validate_function_reports_missing(self) -> None:
        bad_set = self._make_bad_residual_set()
        compat = validate_algebraic_residuals_against_scenario(bad_set, self.build_result)
        assert compat["is_compatible"] is False
        assert "P:n_NONEXISTENT_node" in compat["missing_unknowns"]

    def test_evaluate_selected_raises_on_incompatible(self) -> None:
        bad_set = self._make_bad_residual_set()
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=bad_set,
            algebraic_unknown_values={"P:n_NONEXISTENT_node": 1.0},
            evaluate=True,
        )
        with pytest.raises(ValueError):
            evaluate_selected_configurable_residuals(req)


# ---------------------------------------------------------------------------
# Story 5 — Missing algebraic unknown values defer evaluation
# ---------------------------------------------------------------------------


class TestStory5MissingAlgebraicUnknownValuesDefer:
    """Prove compatibility and evaluation are separate when values are absent."""

    def setup_method(self) -> None:
        self.build_result = _build_scenario()
        self.residual_set = _make_residual_set()

    def test_compatibility_true_without_values(self) -> None:
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=self.residual_set,
            algebraic_unknown_values=None,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.compatibility.is_compatible is True

    def test_evaluation_deferred_without_values(self) -> None:
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=self.residual_set,
            algebraic_unknown_values=None,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.evaluation_performed is False
        assert result.evaluation_deferred is True

    def test_deferred_reason_mentions_values(self) -> None:
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=self.residual_set,
            algebraic_unknown_values=None,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        reason = result.evaluation_deferred_reason.lower()
        assert "unknown_values" in reason or "values" in reason

    def test_no_solve_or_fallback(self) -> None:
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=self.residual_set,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.no_solve is True
        assert result.evaluation_result is None

    def test_evaluate_selected_raises_without_values(self) -> None:
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=self.residual_set,
            algebraic_unknown_values=None,
            evaluate=True,
        )
        with pytest.raises(ValueError):
            evaluate_selected_configurable_residuals(req)


# ---------------------------------------------------------------------------
# Story 6 — Role changes do not alter algebraic residual behavior
# ---------------------------------------------------------------------------


class TestStory6RoleChangesDoNotAlterBehavior:
    """Prove roles remain metadata only; algebraic behavior is structure-independent."""

    def test_different_roles_same_compatibility(self) -> None:
        br_roles = _build_scenario(
            pump_role=ScenarioComponentRole.PUMP,
            evap_role=ScenarioComponentRole.EVAPORATOR,
            cond_role=ScenarioComponentRole.CONDENSER,
            scenario_id="roles_specific",
        )
        br_generic = _build_scenario(
            pump_role=ScenarioComponentRole.GENERIC,
            evap_role=ScenarioComponentRole.GENERIC,
            cond_role=ScenarioComponentRole.GENERIC,
            scenario_id="roles_generic",
        )
        residual_set = _make_residual_set()

        req_roles = ConfigurableResidualSelectionRequest(
            build_result=br_roles,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=residual_set,
        )
        req_generic = ConfigurableResidualSelectionRequest(
            build_result=br_generic,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=residual_set,
        )
        r_roles = select_configurable_residual_strategy(req_roles)
        r_generic = select_configurable_residual_strategy(req_generic)

        assert r_roles.compatibility.is_compatible is True
        assert r_generic.compatibility.is_compatible is True

    def test_different_roles_same_evaluation_result(self) -> None:
        br_roles = _build_scenario(
            pump_role=ScenarioComponentRole.PUMP,
            evap_role=ScenarioComponentRole.EVAPORATOR,
            cond_role=ScenarioComponentRole.CONDENSER,
            scenario_id="roles_specific_eval",
        )
        br_generic = _build_scenario(
            pump_role=ScenarioComponentRole.GENERIC,
            evap_role=ScenarioComponentRole.GENERIC,
            cond_role=ScenarioComponentRole.GENERIC,
            scenario_id="roles_generic_eval",
        )
        residual_set = _make_residual_set()

        req_roles = ConfigurableResidualSelectionRequest(
            build_result=br_roles,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=residual_set,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        req_generic = ConfigurableResidualSelectionRequest(
            build_result=br_generic,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=residual_set,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        r_roles = select_configurable_residual_strategy(req_roles)
        r_generic = select_configurable_residual_strategy(req_generic)

        assert r_roles.evaluation_result.max_abs_residual < 1e-9
        assert r_generic.evaluation_result.max_abs_residual < 1e-9
        assert (
            r_roles.evaluation_result.residual_values.keys()
            == r_generic.evaluation_result.residual_values.keys()
        )

    def test_no_residuals_generated_from_roles(self) -> None:
        # With evaluate=True but no algebraic_residual_set, compatibility is
        # False because no set was supplied — not because roles triggered anything.
        br = _build_scenario(
            pump_role=ScenarioComponentRole.PUMP,
            scenario_id="roles_no_set",
        )
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=None,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.compatibility.is_compatible is False
        reasons_str = " ".join(result.compatibility.reasons).lower()
        assert "none" in reasons_str or "not provided" in reasons_str or "requires" in reasons_str

    def test_no_closures_generated_from_roles(self) -> None:
        br = _build_scenario(
            pump_role=ScenarioComponentRole.PUMP,
            evap_role=ScenarioComponentRole.EVAPORATOR,
            cond_role=ScenarioComponentRole.CONDENSER,
            scenario_id="roles_no_closures",
        )
        residual_set = _make_residual_set()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=residual_set,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.evaluation_performed is True
        report = build_configurable_residual_selection_report(result)
        assert report["closures_inferred_from_roles"] is False


# ---------------------------------------------------------------------------
# Story 7 — Topology does not generate algebraic residuals
# ---------------------------------------------------------------------------


class TestStory7TopologyDoesNotGenerateResiduals:
    """Prove topology alone does not create algebraic residuals."""

    def setup_method(self) -> None:
        self.build_result = _build_scenario(scenario_id="topology_no_set")

    def test_no_set_gives_incompatible(self) -> None:
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=None,
        )
        result = select_configurable_residual_strategy(req)
        assert result.compatibility.is_compatible is False

    def test_reasons_mention_missing_set(self) -> None:
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=None,
        )
        result = select_configurable_residual_strategy(req)
        reasons_str = " ".join(result.compatibility.reasons).lower()
        assert "none" in reasons_str or "requires" in reasons_str or "not" in reasons_str

    def test_evaluation_not_performed_when_no_set(self) -> None:
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=None,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.evaluation_performed is False

    def test_no_declarations_created_from_graph(self) -> None:
        # The build result has a graph with nodes and components but zero
        # residual declarations unless the user supplies them.
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=None,
        )
        result = select_configurable_residual_strategy(req)
        assert result.evaluation_result is None

    def test_no_fallback_to_declaration_only(self) -> None:
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=None,
        )
        result = select_configurable_residual_strategy(req)
        assert result.selected_mode is ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC

    def test_no_solve_even_when_incompatible(self) -> None:
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=None,
        )
        result = select_configurable_residual_strategy(req)
        assert result.no_solve is True


# ---------------------------------------------------------------------------
# Story 8 — Existing modes remain independent
# ---------------------------------------------------------------------------


class TestStory8ExistingModesRemainIndependent:
    """Prove all existing modes still work and ignore algebraic residual fields."""

    def setup_method(self) -> None:
        self.residual_set = _make_residual_set()
        self.closure_set = _make_closure_set()

    def _build_single_loop(self) -> ConfigurableScenarioBuildResult:
        spec = ConfigurableScenarioSpec(
            scenario_id="fc_sl_independent",
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

    def test_declaration_only_ignores_algebraic_fields(self) -> None:
        br = _build_scenario(scenario_id="fc_decl_only")
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
            algebraic_residual_set=self.residual_set,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.compatibility.is_compatible is True
        assert result.evaluation_performed is False
        assert result.evaluation_result is None

    def test_declaration_only_does_not_evaluate(self) -> None:
        br = _build_scenario(scenario_id="fc_decl_no_eval")
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
            algebraic_residual_set=self.residual_set,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.selected_mode is ConfigurableResidualMode.DECLARATION_ONLY
        assert result.evaluation_deferred is True

    def test_closure_only_requires_explicit_set(self) -> None:
        br = _build_scenario(scenario_id="fc_clo_only")
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.CLOSURE_ONLY,
            closure_residual_set=self.closure_set,
            algebraic_residual_set=self.residual_set,
        )
        result = select_configurable_residual_strategy(req)
        assert result.compatibility.is_compatible is True
        assert result.selected_mode is ConfigurableResidualMode.CLOSURE_ONLY

    def test_closure_only_does_not_use_algebraic_set(self) -> None:
        br = _build_scenario(scenario_id="fc_clo_no_alg")
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.CLOSURE_ONLY,
            closure_residual_set=self.closure_set,
            algebraic_residual_set=self.residual_set,
            closure_unknown_values={"mdot_loop": 1.0},
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.evaluation_performed is True
        from mpl_sim.network.closure_integration import CombinedClosureEvaluationResult

        assert isinstance(result.evaluation_result, CombinedClosureEvaluationResult)

    def test_fixed_single_loop_does_not_use_algebraic_set(self) -> None:
        br = self._build_single_loop()
        params = FixedSingleLoopResidualParameters(
            pump_pressure_rise=50_000.0,
            evaporator_pressure_drop=30_000.0,
            condenser_pressure_drop=20_000.0,
            accumulator_pressure_reference=100_000.0,
        )
        sl_uv = {
            "mdot:accumulator": 1.0,
            "mdot:pump": 1.0,
            "mdot:evaporator": 1.0,
            "mdot:condenser": 1.0,
            "P:n_acc_out": 100_000.0,
            "P:n_pump_out": 150_000.0,
            "P:n_evap_out": 120_000.0,
            "P:n_cond_out": 100_000.0,
        }
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
            single_loop_parameters=params,
            single_loop_unknown_values=sl_uv,
            algebraic_residual_set=self.residual_set,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.compatibility.is_compatible is True
        assert result.evaluation_performed is True
        from mpl_sim.network.fixed_single_loop_runner import FixedSingleLoopEvaluationResult

        assert isinstance(result.evaluation_result, FixedSingleLoopEvaluationResult)

    def test_no_existing_mode_affected_by_algebraic_unknown_values(self) -> None:
        br = _build_scenario(scenario_id="fc_decl_uvs")
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.selected_mode is ConfigurableResidualMode.DECLARATION_ONLY
        assert result.evaluation_performed is False


# ---------------------------------------------------------------------------
# Story 9 — Reports are composable and JSON-serializable
# ---------------------------------------------------------------------------


class TestStory9ReportsComposableAndSerializable:
    """Prove reports from the stack can be composed into a single JSON dict."""

    def setup_method(self) -> None:
        self.build_result = _build_scenario(scenario_id="fc_report")
        self.residual_set = _make_residual_set()

    def test_scenario_report_serializable(self) -> None:
        report = build_configurable_scenario_report(self.build_result)
        assert isinstance(json.dumps(report), str)

    def test_algebraic_residual_report_serializable(self) -> None:
        eval_result = evaluate_configurable_algebraic_residuals(self.residual_set, _ZERO_UV)
        report = build_configurable_algebraic_residual_report(eval_result)
        assert isinstance(json.dumps(report), str)

    def test_selection_report_serializable(self) -> None:
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=self.residual_set,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        assert isinstance(json.dumps(report), str)

    def test_combined_report_serializable(self) -> None:
        eval_result = evaluate_configurable_algebraic_residuals(self.residual_set, _ZERO_UV)
        scenario_report = build_configurable_scenario_report(self.build_result)
        algebraic_report = build_configurable_algebraic_residual_report(eval_result)
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=self.residual_set,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        selection_report = build_configurable_residual_selection_report(result)

        combined: dict[str, object] = {
            "block": "15F-C",
            "scenario": scenario_report,
            "algebraic_residuals": algebraic_report,
            "selection": selection_report,
        }
        serialized = json.dumps(combined)
        assert isinstance(serialized, str)
        assert len(serialized) > 0

    def test_combined_report_says_no_solve(self) -> None:
        eval_result = evaluate_configurable_algebraic_residuals(self.residual_set, _ZERO_UV)
        scenario_report = build_configurable_scenario_report(self.build_result)
        algebraic_report = build_configurable_algebraic_residual_report(eval_result)
        req = ConfigurableResidualSelectionRequest(
            build_result=self.build_result,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=self.residual_set,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        selection_report = build_configurable_residual_selection_report(result)

        assert scenario_report.get("no_solve") is True
        assert algebraic_report.get("no_solve") is True
        assert selection_report.get("no_solve") is True

    def test_no_file_writing(self) -> None:
        # Smoke test: all three report builders return plain dicts.
        eval_result = evaluate_configurable_algebraic_residuals(self.residual_set, _ZERO_UV)
        s = build_configurable_scenario_report(self.build_result)
        a = build_configurable_algebraic_residual_report(eval_result)
        assert isinstance(s, dict)
        assert isinstance(a, dict)


# ---------------------------------------------------------------------------
# Story 10 — Production contract remains frozen
# ---------------------------------------------------------------------------


class TestStory10ProductionContractFrozen:
    """Prove production classes still do not expose contribute."""

    def test_all_known_classes_return_no_contribute_method(self) -> None:
        results = inspect_known_production_component_contracts()
        assert len(results) == 6
        for r in results:
            assert (
                r.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD
            ), f"{r.class_name} should have NO_CONTRIBUTE_METHOD; got {r.status!r}"

    def test_class_names_include_all_six(self) -> None:
        results = inspect_known_production_component_contracts()
        names = {r.class_name for r in results}
        assert "Component" in names
        assert "Pipe" in names
        assert "PumpComponent" in names
        assert "AccumulatorComponent" in names
        assert "EvaporatorComponent" in names
        assert "CondenserComponent" in names

    def test_count_is_exactly_six(self) -> None:
        results = inspect_known_production_component_contracts()
        assert len(results) == 6


# ---------------------------------------------------------------------------
# Boundary / negative acceptance tests
# ---------------------------------------------------------------------------


def _import_lines(mod: object) -> str:
    """Return only import-statement lines from a module's source.

    Documentation strings may mention forbidden terms as "MUST NOT" constraints;
    checking only import lines avoids false positives from those comments.
    """
    src = inspect.getsource(mod)
    lines = [
        ln.strip()
        for ln in src.splitlines()
        if ln.strip().startswith("import ") or ln.strip().startswith("from ")
    ]
    return "\n".join(lines)


class TestBoundaryNegativeAcceptance:
    """Architecture boundary checks proving constraints are enforced.

    Module docstrings document 'MUST NOT' constraints using the very terms
    we check for.  All source-level checks therefore scan only import lines
    or def-statement lines, not full source, to avoid docstring false-positives.
    Module-attribute checks (hasattr) are unconditionally reliable.
    """

    # B1 — no solve_fixed_single_loop_residuals in algebraic path

    def test_b1_algebraic_module_does_not_import_solve_function(self) -> None:
        imports = _import_lines(_CAR_MOD)
        assert "solve_fixed_single_loop_residuals" not in imports

    def test_b1_algebraic_selection_path_does_not_call_solve(self) -> None:
        src_fn = inspect.getsource(_CRS_MOD._evaluate_configurable_algebraic)  # type: ignore[attr-defined]
        assert "solve_fixed_single_loop_residuals" not in src_fn

    def test_b1_algebraic_module_has_no_solver_attribute(self) -> None:
        assert not hasattr(_CAR_MOD, "solve_fixed_single_loop_residuals")

    # B2 — no generic solve(network) or NetworkGraph.solve

    def test_b2_algebraic_module_has_no_network_graph_attribute(self) -> None:
        assert not hasattr(_CAR_MOD, "NetworkGraph")

    def test_b2_selection_module_has_no_network_graph_attribute(self) -> None:
        assert not hasattr(_CRS_MOD, "NetworkGraph")

    def test_b2_algebraic_module_defines_no_solve_network_function(self) -> None:
        src = inspect.getsource(_CAR_MOD)
        assert "def solve_network" not in src
        assert "def solve(" not in src

    def test_b2_selection_module_defines_no_solve_network_function(self) -> None:
        src = inspect.getsource(_CRS_MOD)
        assert "def solve_network" not in src

    # B3 — no SystemState or FluidState

    def test_b3_algebraic_module_does_not_import_system_state(self) -> None:
        imports = _import_lines(_CAR_MOD)
        assert "SystemState" not in imports
        assert not hasattr(_CAR_MOD, "SystemState")

    def test_b3_algebraic_module_does_not_import_fluid_state(self) -> None:
        imports = _import_lines(_CAR_MOD)
        assert "FluidState" not in imports
        assert not hasattr(_CAR_MOD, "FluidState")

    def test_b3_selection_module_does_not_import_system_state(self) -> None:
        imports = _import_lines(_CRS_MOD)
        assert "SystemState" not in imports
        assert not hasattr(_CRS_MOD, "SystemState")

    def test_b3_selection_module_does_not_import_fluid_state(self) -> None:
        imports = _import_lines(_CRS_MOD)
        assert "FluidState" not in imports
        assert not hasattr(_CRS_MOD, "FluidState")

    # B4 — no CoolProp, PropertyBackend, CorrelationRegistry

    def test_b4_algebraic_module_does_not_import_coolprop(self) -> None:
        imports = _import_lines(_CAR_MOD)
        assert "CoolProp" not in imports
        assert not hasattr(_CAR_MOD, "CoolProp")

    def test_b4_algebraic_module_does_not_import_property_backend(self) -> None:
        imports = _import_lines(_CAR_MOD)
        assert "PropertyBackend" not in imports
        assert not hasattr(_CAR_MOD, "PropertyBackend")

    def test_b4_algebraic_module_does_not_import_correlation_registry(self) -> None:
        imports = _import_lines(_CAR_MOD)
        assert "CorrelationRegistry" not in imports
        assert not hasattr(_CAR_MOD, "CorrelationRegistry")

    def test_b4_selection_module_does_not_import_coolprop(self) -> None:
        imports = _import_lines(_CRS_MOD)
        assert "CoolProp" not in imports
        assert not hasattr(_CRS_MOD, "CoolProp")

    # B5 — no HX-model imports

    def test_b5_algebraic_module_does_not_import_hx_models(self) -> None:
        imports = _import_lines(_CAR_MOD)
        assert "hx_models" not in imports
        assert not hasattr(_CAR_MOD, "HeatExchangerModelRegistry")

    def test_b5_selection_module_does_not_import_hx_models(self) -> None:
        imports = _import_lines(_CRS_MOD)
        assert "hx_models" not in imports
        assert not hasattr(_CRS_MOD, "HeatExchangerModelRegistry")

    # B6 — no production component imports

    def test_b6_algebraic_module_does_not_import_components(self) -> None:
        imports = _import_lines(_CAR_MOD)
        assert "mpl_sim.components" not in imports

    def test_b6_selection_module_does_not_import_components(self) -> None:
        imports = _import_lines(_CRS_MOD)
        assert "mpl_sim.components" not in imports

    # B7 — no contribute definition or call

    def test_b7_algebraic_module_defines_no_contribute(self) -> None:
        src = inspect.getsource(_CAR_MOD)
        assert "def contribute" not in src

    def test_b7_algebraic_module_has_no_contribute_attribute(self) -> None:
        assert not hasattr(_CAR_MOD, "contribute")

    def test_b7_selection_module_defines_no_contribute(self) -> None:
        src = inspect.getsource(_CRS_MOD)
        assert "def contribute" not in src

    def test_b7_selection_module_has_no_contribute_attribute(self) -> None:
        assert not hasattr(_CRS_MOD, "contribute")

    # B8 — no role-based physics dispatch

    def test_b8_algebraic_selection_path_no_role_dispatch(self) -> None:
        src_fn = inspect.getsource(_CRS_MOD._evaluate_configurable_algebraic)  # type: ignore[attr-defined]
        assert "component_type" not in src_fn
        assert ".role" not in src_fn

    def test_b8_no_role_inference_functions(self) -> None:
        src_car = inspect.getsource(_CAR_MOD)
        assert "infer_residuals_from_role" not in src_car
        assert "generate_residuals_from_role" not in src_car

    def test_b8_no_role_inference_functions_in_selection(self) -> None:
        src_crs = inspect.getsource(_CRS_MOD)
        assert "infer_residuals_from_role" not in src_crs
        assert "generate_residuals_from_role" not in src_crs

    # B9 — no topology-based residual inference

    def test_b9_algebraic_module_does_not_call_graph_instances(self) -> None:
        src = inspect.getsource(_CAR_MOD)
        assert "graph.instances" not in src
        assert "graph.edges" not in src

    def test_b9_algebraic_selection_path_no_topology_inference(self) -> None:
        src_fn = inspect.getsource(_CRS_MOD._evaluate_configurable_algebraic)  # type: ignore[attr-defined]
        assert "instances()" not in src_fn
        assert "graph.edges" not in src_fn

    # B10 — no automatic closure inference

    def test_b10_algebraic_module_no_auto_closure(self) -> None:
        src = inspect.getsource(_CAR_MOD)
        assert "auto_closure" not in src
        assert "closure_from_role" not in src
        assert "infer_closure" not in src

    def test_b10_algebraic_selection_path_no_auto_closure(self) -> None:
        src_fn = inspect.getsource(_CRS_MOD._evaluate_configurable_algebraic)  # type: ignore[attr-defined]
        assert "auto_closure" not in src_fn
        assert "closure_from_role" not in src_fn

    # B11 — no root-finding or optimization

    def test_b11_algebraic_module_no_root_finding(self) -> None:
        imports = _import_lines(_CAR_MOD)
        assert "least_squares" not in imports
        assert "lstsq" not in imports
        assert "fsolve" not in imports
        assert "minimize" not in imports
        assert "scipy.optimize" not in imports

    def test_b11_selection_module_no_root_finding(self) -> None:
        imports = _import_lines(_CRS_MOD)
        assert "least_squares" not in imports
        assert "lstsq" not in imports
        assert "fsolve" not in imports
        assert "scipy.optimize" not in imports

    def test_b11_algebraic_evaluation_result_has_no_solver_fields(self) -> None:
        rs = _make_residual_set()
        ev = evaluate_configurable_algebraic_residuals(rs, _ZERO_UV)
        assert not hasattr(ev, "converged")
        assert not hasattr(ev, "iterations")
        assert not hasattr(ev, "solution")

    def test_b11_selection_result_has_no_solver_fields(self) -> None:
        br = _build_scenario(scenario_id="b11_no_solver")
        rs = _make_residual_set()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=rs,
            algebraic_unknown_values=_ZERO_UV,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert not hasattr(result, "converged")
        assert not hasattr(result, "iteration_count")
        assert result.no_solve is True
