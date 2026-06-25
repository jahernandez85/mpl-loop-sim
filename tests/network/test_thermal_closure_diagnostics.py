"""Block 15D-B — Thermal Closure Diagnostics tests.

Coverage for:
  - ThermalClosureCategory enum
  - ThermalClosureDiagnostic
  - ThermalClosureDiagnosticResult
  - evaluate_thermal_closure_sufficiency
  - make_basic_thermal_loop_diagnostic
  - make_recuperator_thermal_diagnostic

No production component physics.  No SystemState.  No FluidState.
No CoolProp, no PropertyBackend, no correlations, no HX models.
Diagnostics are kind-based only; no residual evaluation is performed.
"""

from __future__ import annotations

import pytest

from mpl_sim.network.thermal_closure_diagnostics import (
    ThermalClosureCategory,
    ThermalClosureDiagnostic,
    evaluate_thermal_closure_sufficiency,
    make_basic_thermal_loop_diagnostic,
    make_recuperator_thermal_diagnostic,
)
from mpl_sim.network.thermal_closures import (
    EffectivenessHeatRateClosure,
    EnthalpyFlowHeatRateClosure,
    FixedHeatRateClosure,
    ImposedEnthalpyClosure,
    ImposedTemperatureLikeClosure,
    RecuperatorEnergyBalanceClosure,
    SensibleHeatRateClosure,
    build_thermal_closure_residuals,
)

# ===========================================================================
# ThermalClosureCategory tests
# ===========================================================================


class TestThermalClosureCategory:
    def test_all_categories_accessible(self):
        cats = {
            ThermalClosureCategory.HEAT_RATE,
            ThermalClosureCategory.ENTHALPY_REFERENCE,
            ThermalClosureCategory.TEMPERATURE_LIKE_REFERENCE,
            ThermalClosureCategory.SENSIBLE_HEAT_RELATION,
            ThermalClosureCategory.ENTHALPY_FLOW_RELATION,
            ThermalClosureCategory.EFFECTIVENESS_RELATION,
            ThermalClosureCategory.RECUPERATOR_ENERGY_BALANCE,
        }
        assert len(cats) == 7

    def test_string_values(self):
        assert ThermalClosureCategory.HEAT_RATE == "heat_rate"
        assert ThermalClosureCategory.ENTHALPY_REFERENCE == "enthalpy_reference"
        assert ThermalClosureCategory.TEMPERATURE_LIKE_REFERENCE == "temperature_like_reference"
        assert ThermalClosureCategory.SENSIBLE_HEAT_RELATION == "sensible_heat_relation"
        assert ThermalClosureCategory.ENTHALPY_FLOW_RELATION == "enthalpy_flow_relation"
        assert ThermalClosureCategory.EFFECTIVENESS_RELATION == "effectiveness_relation"
        assert ThermalClosureCategory.RECUPERATOR_ENERGY_BALANCE == "recuperator_energy_balance"


# ===========================================================================
# ThermalClosureDiagnostic tests
# ===========================================================================


class TestThermalClosureDiagnostic:
    def test_builds_with_required_categories(self):
        d = ThermalClosureDiagnostic(
            required_categories=frozenset({ThermalClosureCategory.HEAT_RATE}),
            description="test diagnostic",
        )
        assert ThermalClosureCategory.HEAT_RATE in d.required_categories

    def test_is_frozen(self):
        d = ThermalClosureDiagnostic(
            required_categories=frozenset({ThermalClosureCategory.HEAT_RATE}),
            description="test",
        )
        with pytest.raises((AttributeError, TypeError)):
            d.description = "modified"  # type: ignore[misc]

    def test_rejects_non_frozenset_categories(self):
        with pytest.raises(TypeError, match="frozenset"):
            ThermalClosureDiagnostic(
                required_categories={ThermalClosureCategory.HEAT_RATE},  # type: ignore[arg-type]
                description="test",
            )

    def test_rejects_wrong_category_type(self):
        with pytest.raises(TypeError):
            ThermalClosureDiagnostic(
                required_categories=frozenset({"not_a_category"}),  # type: ignore[arg-type]
                description="test",
            )

    def test_rejects_blank_description(self):
        with pytest.raises(ValueError, match="description"):
            ThermalClosureDiagnostic(
                required_categories=frozenset({ThermalClosureCategory.HEAT_RATE}),
                description="   ",
            )

    def test_empty_required_categories_allowed(self):
        d = ThermalClosureDiagnostic(
            required_categories=frozenset(),
            description="trivial diagnostic",
        )
        assert len(d.required_categories) == 0


# ===========================================================================
# evaluate_thermal_closure_sufficiency tests
# ===========================================================================


class TestEvaluateThermalClosureSufficiency:
    def _make_diagnostic(self, *categories: ThermalClosureCategory) -> ThermalClosureDiagnostic:
        return ThermalClosureDiagnostic(
            required_categories=frozenset(categories),
            description="test diagnostic",
        )

    def test_sufficient_when_all_categories_present(self):
        diag = self._make_diagnostic(ThermalClosureCategory.HEAT_RATE)
        closure_set = build_thermal_closure_residuals([FixedHeatRateClosure("q", 100.0, "r")])
        result = evaluate_thermal_closure_sufficiency(diag, closure_set)
        assert result.is_sufficient is True

    def test_insufficient_when_heat_rate_missing(self):
        diag = self._make_diagnostic(ThermalClosureCategory.HEAT_RATE)
        closure_set = build_thermal_closure_residuals([ImposedEnthalpyClosure("h", 1000.0, "r")])
        result = evaluate_thermal_closure_sufficiency(diag, closure_set)
        assert result.is_sufficient is False
        assert ThermalClosureCategory.HEAT_RATE in result.missing_categories

    def test_insufficient_when_enthalpy_flow_missing(self):
        diag = self._make_diagnostic(ThermalClosureCategory.ENTHALPY_FLOW_RELATION)
        closure_set = build_thermal_closure_residuals([FixedHeatRateClosure("q", 100.0, "r")])
        result = evaluate_thermal_closure_sufficiency(diag, closure_set)
        assert result.is_sufficient is False
        assert ThermalClosureCategory.ENTHALPY_FLOW_RELATION in result.missing_categories

    def test_insufficient_when_enthalpy_reference_missing(self):
        diag = self._make_diagnostic(ThermalClosureCategory.ENTHALPY_REFERENCE)
        closure_set = build_thermal_closure_residuals([FixedHeatRateClosure("q", 100.0, "r")])
        result = evaluate_thermal_closure_sufficiency(diag, closure_set)
        assert result.is_sufficient is False
        assert ThermalClosureCategory.ENTHALPY_REFERENCE in result.missing_categories

    def test_insufficient_when_temperature_like_reference_missing(self):
        diag = self._make_diagnostic(ThermalClosureCategory.TEMPERATURE_LIKE_REFERENCE)
        closure_set = build_thermal_closure_residuals([FixedHeatRateClosure("q", 100.0, "r")])
        result = evaluate_thermal_closure_sufficiency(diag, closure_set)
        assert result.is_sufficient is False
        assert ThermalClosureCategory.TEMPERATURE_LIKE_REFERENCE in result.missing_categories

    def test_insufficient_when_recuperator_energy_balance_missing(self):
        diag = self._make_diagnostic(ThermalClosureCategory.RECUPERATOR_ENERGY_BALANCE)
        closure_set = build_thermal_closure_residuals(
            [EnthalpyFlowHeatRateClosure("q", "m", "hi", "ho", "r")]
        )
        result = evaluate_thermal_closure_sufficiency(diag, closure_set)
        assert result.is_sufficient is False
        assert ThermalClosureCategory.RECUPERATOR_ENERGY_BALANCE in result.missing_categories

    def test_provided_categories_reported(self):
        diag = self._make_diagnostic(
            ThermalClosureCategory.HEAT_RATE,
            ThermalClosureCategory.ENTHALPY_FLOW_RELATION,
        )
        closure_set = build_thermal_closure_residuals(
            [
                FixedHeatRateClosure("q", 100.0, "r1"),
                EnthalpyFlowHeatRateClosure("q2", "m", "hi", "ho", "r2"),
            ]
        )
        result = evaluate_thermal_closure_sufficiency(diag, closure_set)
        assert ThermalClosureCategory.HEAT_RATE in result.provided_categories
        assert ThermalClosureCategory.ENTHALPY_FLOW_RELATION in result.provided_categories
        assert result.is_sufficient is True

    def test_missing_messages_non_empty_when_missing(self):
        diag = self._make_diagnostic(ThermalClosureCategory.HEAT_RATE)
        closure_set = build_thermal_closure_residuals([ImposedEnthalpyClosure("h", 1000.0, "r")])
        result = evaluate_thermal_closure_sufficiency(diag, closure_set)
        assert len(result.missing_messages) > 0
        assert any("heat-rate" in msg for msg in result.missing_messages)

    def test_missing_messages_empty_when_sufficient(self):
        diag = self._make_diagnostic(ThermalClosureCategory.HEAT_RATE)
        closure_set = build_thermal_closure_residuals([FixedHeatRateClosure("q", 100.0, "r")])
        result = evaluate_thermal_closure_sufficiency(diag, closure_set)
        assert len(result.missing_messages) == 0

    def test_closure_names_reported(self):
        diag = self._make_diagnostic(ThermalClosureCategory.HEAT_RATE)
        closure_set = build_thermal_closure_residuals(
            [FixedHeatRateClosure("q", 100.0, "my_closure")]
        )
        result = evaluate_thermal_closure_sufficiency(diag, closure_set)
        assert "my_closure" in result.closure_names

    def test_trivial_diagnostic_always_sufficient(self):
        diag = ThermalClosureDiagnostic(
            required_categories=frozenset(),
            description="trivial",
        )
        closure_set = build_thermal_closure_residuals([FixedHeatRateClosure("q", 100.0, "r")])
        result = evaluate_thermal_closure_sufficiency(diag, closure_set)
        assert result.is_sufficient is True

    def test_sensible_heat_relation_satisfied_by_sensible_closure(self):
        diag = self._make_diagnostic(ThermalClosureCategory.SENSIBLE_HEAT_RELATION)
        closure_set = build_thermal_closure_residuals(
            [SensibleHeatRateClosure("q", "m", "ti", "to", 4000.0, "r")]
        )
        result = evaluate_thermal_closure_sufficiency(diag, closure_set)
        assert result.is_sufficient is True

    def test_effectiveness_relation_satisfied_by_effectiveness_closure(self):
        diag = self._make_diagnostic(ThermalClosureCategory.EFFECTIVENESS_RELATION)
        closure_set = build_thermal_closure_residuals(
            [EffectivenessHeatRateClosure("q", "qm", 0.8, "r")]
        )
        result = evaluate_thermal_closure_sufficiency(diag, closure_set)
        assert result.is_sufficient is True

    def test_recuperator_balance_satisfied_by_recuperator_closure(self):
        diag = self._make_diagnostic(ThermalClosureCategory.RECUPERATOR_ENERGY_BALANCE)
        closure_set = build_thermal_closure_residuals(
            [RecuperatorEnergyBalanceClosure("qh", "qc", "r")]
        )
        result = evaluate_thermal_closure_sufficiency(diag, closure_set)
        assert result.is_sufficient is True

    def test_temperature_like_reference_satisfied_by_temp_closure(self):
        diag = self._make_diagnostic(ThermalClosureCategory.TEMPERATURE_LIKE_REFERENCE)
        closure_set = build_thermal_closure_residuals(
            [ImposedTemperatureLikeClosure("theta", 300.0, "r")]
        )
        result = evaluate_thermal_closure_sufficiency(diag, closure_set)
        assert result.is_sufficient is True

    def test_rejects_wrong_diagnostic_type(self):
        closure_set = build_thermal_closure_residuals([FixedHeatRateClosure("q", 100.0, "r")])
        with pytest.raises(TypeError, match="ThermalClosureDiagnostic"):
            evaluate_thermal_closure_sufficiency("not_a_diagnostic", closure_set)  # type: ignore[arg-type]

    def test_rejects_wrong_closure_set_type(self):
        diag = self._make_diagnostic(ThermalClosureCategory.HEAT_RATE)
        with pytest.raises(TypeError, match="ThermalClosureResidualSet"):
            evaluate_thermal_closure_sufficiency(diag, "not_a_set")  # type: ignore[arg-type]

    def test_diagnostic_is_category_based_not_rank_analysis(self):
        # Verify the result notes make no claim about rank/DAE
        diag = self._make_diagnostic(ThermalClosureCategory.HEAT_RATE)
        closure_set = build_thermal_closure_residuals([FixedHeatRateClosure("q", 100.0, "r")])
        result = evaluate_thermal_closure_sufficiency(diag, closure_set)
        # is_sufficient=True does NOT claim full rank; just checks category presence
        assert isinstance(result.is_sufficient, bool)
        assert isinstance(result.provided_categories, frozenset)
        assert isinstance(result.missing_categories, frozenset)


# ===========================================================================
# make_basic_thermal_loop_diagnostic tests
# ===========================================================================


class TestMakeBasicThermalLoopDiagnostic:
    def test_builds(self):
        d = make_basic_thermal_loop_diagnostic()
        assert isinstance(d, ThermalClosureDiagnostic)

    def test_requires_heat_rate_and_enthalpy_flow(self):
        d = make_basic_thermal_loop_diagnostic()
        assert ThermalClosureCategory.HEAT_RATE in d.required_categories
        assert ThermalClosureCategory.ENTHALPY_FLOW_RELATION in d.required_categories

    def test_description_non_empty(self):
        d = make_basic_thermal_loop_diagnostic()
        assert isinstance(d.description, str)
        assert len(d.description) > 0

    def test_sufficient_with_correct_closures(self):
        d = make_basic_thermal_loop_diagnostic()
        closure_set = build_thermal_closure_residuals(
            [
                FixedHeatRateClosure("q", 5_000.0, "r1"),
                EnthalpyFlowHeatRateClosure("q2", "m", "hi", "ho", "r2"),
            ]
        )
        result = evaluate_thermal_closure_sufficiency(d, closure_set)
        assert result.is_sufficient is True

    def test_insufficient_without_enthalpy_flow(self):
        d = make_basic_thermal_loop_diagnostic()
        closure_set = build_thermal_closure_residuals([FixedHeatRateClosure("q", 5_000.0, "r1")])
        result = evaluate_thermal_closure_sufficiency(d, closure_set)
        assert result.is_sufficient is False
        assert ThermalClosureCategory.ENTHALPY_FLOW_RELATION in result.missing_categories

    def test_insufficient_without_heat_rate(self):
        d = make_basic_thermal_loop_diagnostic()
        closure_set = build_thermal_closure_residuals(
            [EnthalpyFlowHeatRateClosure("q", "m", "hi", "ho", "r")]
        )
        result = evaluate_thermal_closure_sufficiency(d, closure_set)
        assert result.is_sufficient is False
        assert ThermalClosureCategory.HEAT_RATE in result.missing_categories


# ===========================================================================
# make_recuperator_thermal_diagnostic tests
# ===========================================================================


class TestMakeRecuperatorThermalDiagnostic:
    def test_builds(self):
        d = make_recuperator_thermal_diagnostic()
        assert isinstance(d, ThermalClosureDiagnostic)

    def test_requires_recuperator_balance_and_enthalpy_flow(self):
        d = make_recuperator_thermal_diagnostic()
        assert ThermalClosureCategory.RECUPERATOR_ENERGY_BALANCE in d.required_categories
        assert ThermalClosureCategory.ENTHALPY_FLOW_RELATION in d.required_categories

    def test_description_non_empty(self):
        d = make_recuperator_thermal_diagnostic()
        assert isinstance(d.description, str)
        assert len(d.description) > 0

    def test_sufficient_with_correct_closures(self):
        d = make_recuperator_thermal_diagnostic()
        closure_set = build_thermal_closure_residuals(
            [
                RecuperatorEnergyBalanceClosure("q_hot", "q_cold", "r1"),
                EnthalpyFlowHeatRateClosure("q_cold", "mdot", "h_in", "h_out", "r2"),
            ]
        )
        result = evaluate_thermal_closure_sufficiency(d, closure_set)
        assert result.is_sufficient is True

    def test_insufficient_without_recuperator_balance(self):
        d = make_recuperator_thermal_diagnostic()
        closure_set = build_thermal_closure_residuals(
            [EnthalpyFlowHeatRateClosure("q", "m", "hi", "ho", "r")]
        )
        result = evaluate_thermal_closure_sufficiency(d, closure_set)
        assert result.is_sufficient is False
        assert ThermalClosureCategory.RECUPERATOR_ENERGY_BALANCE in result.missing_categories

    def test_insufficient_without_enthalpy_flow(self):
        d = make_recuperator_thermal_diagnostic()
        closure_set = build_thermal_closure_residuals(
            [RecuperatorEnergyBalanceClosure("qh", "qc", "r")]
        )
        result = evaluate_thermal_closure_sufficiency(d, closure_set)
        assert result.is_sufficient is False
        assert ThermalClosureCategory.ENTHALPY_FLOW_RELATION in result.missing_categories

    def test_missing_message_for_recuperator_balance(self):
        d = make_recuperator_thermal_diagnostic()
        closure_set = build_thermal_closure_residuals(
            [EnthalpyFlowHeatRateClosure("q", "m", "hi", "ho", "r")]
        )
        result = evaluate_thermal_closure_sufficiency(d, closure_set)
        assert any("recuperator" in msg.lower() for msg in result.missing_messages)
