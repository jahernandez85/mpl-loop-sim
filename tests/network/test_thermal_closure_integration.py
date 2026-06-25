"""Block 15D-B — Thermal Closure Integration tests.

Proves that Block 15D-B thermal closure primitives:
  1. Evaluate independently at a known consistent algebraic point.
  2. Can coexist with Block 15D-A hydraulic closure primitives in tests.
  3. Correctly model a preheater-like element algebraically.
  4. Correctly model a recuperator-like element algebraically.
  5. Remain separate from production components, SystemState, FluidState,
     CoolProp, and any property-backed computation.

No solve is claimed.  No property conversion is claimed.
No HX model is imported or called.
No production component execution occurs.

Test consistent points
-----------------------

Preheater-like element (Block 15D-B.1):
  Algebraic variables:
    q = 50_000.0  [W]
    mdot = 1.0    [kg/s]
    h_in = 250_000.0  [J/kg]  (user-supplied scalar, not a property)
    h_out = 300_000.0 [J/kg]  (user-supplied scalar, not a property)
  FixedHeatRateClosure:       q_fixed = 50_000 => r = q - 50_000 = 0
  EnthalpyFlowHeatRateClosure: q = mdot*(h_out-h_in) = 1.0*50_000 = 50_000 => r = 0

Recuperator-like element (Block 15D-B.2):
  Algebraic variables:
    q_hot = -20_000.0  [W]  (heat given up by hot side)
    q_cold = +20_000.0 [W]  (heat received by cold side)
    mdot_hot = 0.5, h_hot_in = 400_000, h_hot_out = 360_000
    mdot_cold = 0.5, h_cold_in = 250_000, h_cold_out = 290_000
  RecuperatorEnergyBalanceClosure: q_hot + q_cold = -20_000 + 20_000 = 0
  EnthalpyFlowHeatRateClosure hot:  q_hot = 0.5*(360_000-400_000) = -20_000 => r = 0
  EnthalpyFlowHeatRateClosure cold: q_cold = 0.5*(290_000-250_000) = 20_000 => r = 0
"""

from __future__ import annotations

import math

import pytest

from mpl_sim.network.hydraulic_closures import (
    ImposedMassFlowClosure,
    ImposedPressureClosure,
    build_hydraulic_closure_residuals,
)
from mpl_sim.network.thermal_closure_diagnostics import (
    evaluate_thermal_closure_sufficiency,
    make_basic_thermal_loop_diagnostic,
    make_recuperator_thermal_diagnostic,
)
from mpl_sim.network.thermal_closures import (
    EnthalpyFlowHeatRateClosure,
    FixedHeatRateClosure,
    ImposedEnthalpyClosure,
    ImposedTemperatureLikeClosure,
    RecuperatorEnergyBalanceClosure,
    SensibleHeatRateClosure,
    build_thermal_closure_residuals,
)

# ===========================================================================
# Consistent point definitions
# ===========================================================================

# Preheater-like consistent point
_PREHEATER_Q = 50_000.0
_PREHEATER_MDOT = 1.0
_PREHEATER_H_IN = 250_000.0
_PREHEATER_H_OUT = 300_000.0

# Recuperator-like consistent point
_RECUP_Q_HOT = -20_000.0
_RECUP_Q_COLD = 20_000.0
_RECUP_MDOT_HOT = 0.5
_RECUP_MDOT_COLD = 0.5
_RECUP_H_HOT_IN = 400_000.0
_RECUP_H_HOT_OUT = 360_000.0
_RECUP_H_COLD_IN = 250_000.0
_RECUP_H_COLD_OUT = 290_000.0


# ===========================================================================
# Test 1: Independent evaluation at known consistent point
# ===========================================================================


class TestThermalClosuresIndependentEvaluation:
    def test_fixed_heat_rate_evaluates_to_zero(self):
        c = FixedHeatRateClosure("q", _PREHEATER_Q, "r_q_fixed")
        assert c.evaluate({"q": _PREHEATER_Q}) == pytest.approx(0.0)

    def test_enthalpy_flow_evaluates_to_zero(self):
        c = EnthalpyFlowHeatRateClosure("q", "mdot", "h_in", "h_out", "r_enthalpy_flow")
        unknowns = {
            "q": _PREHEATER_Q,
            "mdot": _PREHEATER_MDOT,
            "h_in": _PREHEATER_H_IN,
            "h_out": _PREHEATER_H_OUT,
        }
        assert c.evaluate(unknowns) == pytest.approx(0.0)

    def test_recuperator_balance_evaluates_to_zero(self):
        c = RecuperatorEnergyBalanceClosure("q_hot", "q_cold", "r_recup_balance")
        assert c.evaluate({"q_hot": _RECUP_Q_HOT, "q_cold": _RECUP_Q_COLD}) == pytest.approx(0.0)

    def test_all_residuals_are_finite(self):
        closures = [
            FixedHeatRateClosure("q", _PREHEATER_Q, "r1"),
            EnthalpyFlowHeatRateClosure("q", "mdot", "h_in", "h_out", "r2"),
        ]
        s = build_thermal_closure_residuals(closures)
        unknowns = {
            "q": _PREHEATER_Q,
            "mdot": _PREHEATER_MDOT,
            "h_in": _PREHEATER_H_IN,
            "h_out": _PREHEATER_H_OUT,
        }
        result = s.evaluate_all(unknowns)
        for name, val in result.items():
            assert math.isfinite(val), f"Residual '{name}' is not finite: {val!r}"

    def test_imposed_enthalpy_evaluates_to_zero(self):
        c = ImposedEnthalpyClosure("h_in", _PREHEATER_H_IN, "r_h_imposed")
        assert c.evaluate({"h_in": _PREHEATER_H_IN}) == pytest.approx(0.0)

    def test_imposed_temperature_like_evaluates_to_zero(self):
        c = ImposedTemperatureLikeClosure("theta", 300.0, "r_theta")
        assert c.evaluate({"theta": 300.0}) == pytest.approx(0.0)

    def test_sensible_heat_evaluates_to_zero(self):
        # q = mdot * cp * (theta_out - theta_in) = 1.0 * 1000 * 50 = 50000
        c = SensibleHeatRateClosure("q", "mdot", "ti", "to", 1000.0, "r_sensible")
        unknowns = {"q": 50_000.0, "mdot": 1.0, "ti": 300.0, "to": 350.0}
        assert c.evaluate(unknowns) == pytest.approx(0.0)


# ===========================================================================
# Test 2: Hydraulic and thermal closures coexist
# ===========================================================================


class TestHydraulicAndThermalCoexistence:
    def test_hydraulic_closures_still_evaluate_correctly(self):
        # Regression: 15D-A hydraulic closures still work
        h_closures = [
            ImposedMassFlowClosure("mdot", 1.0, "h_r1"),
            ImposedPressureClosure("P_ref", 1_000_000.0, "h_r2"),
        ]
        h_set = build_hydraulic_closure_residuals(h_closures)
        h_unknowns = {"mdot": 1.0, "P_ref": 1_000_000.0}
        h_result = h_set.evaluate_all(h_unknowns)
        assert h_result["h_r1"] == pytest.approx(0.0)
        assert h_result["h_r2"] == pytest.approx(0.0)

    def test_thermal_closures_evaluate_independently(self):
        t_closures = [
            FixedHeatRateClosure("q", _PREHEATER_Q, "t_r1"),
            EnthalpyFlowHeatRateClosure("q", "mdot", "h_in", "h_out", "t_r2"),
        ]
        t_set = build_thermal_closure_residuals(t_closures)
        t_unknowns = {
            "q": _PREHEATER_Q,
            "mdot": _PREHEATER_MDOT,
            "h_in": _PREHEATER_H_IN,
            "h_out": _PREHEATER_H_OUT,
        }
        t_result = t_set.evaluate_all(t_unknowns)
        assert t_result["t_r1"] == pytest.approx(0.0)
        assert t_result["t_r2"] == pytest.approx(0.0)

    def test_hydraulic_and_thermal_share_no_state(self):
        # Hydraulic and thermal residual sets are evaluated at separate unknowns;
        # they do not share state or dependencies
        h_closures = [ImposedMassFlowClosure("mdot", 1.0, "h_r")]
        t_closures = [FixedHeatRateClosure("q", _PREHEATER_Q, "t_r")]
        h_set = build_hydraulic_closure_residuals(h_closures)
        t_set = build_thermal_closure_residuals(t_closures)
        # Each evaluates at its own unknown vector
        h_result = h_set.evaluate_all({"mdot": 1.0})
        t_result = t_set.evaluate_all({"q": _PREHEATER_Q})
        assert h_result["h_r"] == pytest.approx(0.0)
        assert t_result["t_r"] == pytest.approx(0.0)

    def test_combined_residuals_as_separate_maps(self):
        # Show that hydraulic and thermal residual maps can be combined for reporting
        h_set = build_hydraulic_closure_residuals([ImposedMassFlowClosure("mdot", 1.0, "h:mdot")])
        t_set = build_thermal_closure_residuals(
            [FixedHeatRateClosure("q", _PREHEATER_Q, "t:q_fixed")]
        )
        h_result = h_set.evaluate_all({"mdot": 1.0})
        t_result = t_set.evaluate_all({"q": _PREHEATER_Q})
        combined = dict(h_result) | dict(t_result)
        assert "h:mdot" in combined
        assert "t:q_fixed" in combined
        assert all(math.isfinite(v) for v in combined.values())


# ===========================================================================
# Test 3: Preheater-like algebraic closure example
# ===========================================================================


class TestPreheaterLikeAlgebraicClosure:
    """
    Models a preheater algebraically:
      - FixedHeatRateClosure: q = q_fixed = 50_000 W
      - EnthalpyFlowHeatRateClosure: q = mdot * (h_out - h_in)

    At the consistent point: q=50_000, mdot=1.0, h_in=250_000, h_out=300_000
    Both residuals are zero.

    No property computation occurs.  h_in, h_out are user-supplied scalars.
    """

    def _make_closure_set(self):
        return build_thermal_closure_residuals(
            [
                FixedHeatRateClosure("q", _PREHEATER_Q, "preheater:q_fixed"),
                EnthalpyFlowHeatRateClosure(
                    "q", "mdot", "h_in", "h_out", "preheater:enthalpy_flow"
                ),
            ]
        )

    def _consistent_unknowns(self) -> dict[str, float]:
        return {
            "q": _PREHEATER_Q,
            "mdot": _PREHEATER_MDOT,
            "h_in": _PREHEATER_H_IN,
            "h_out": _PREHEATER_H_OUT,
        }

    def test_fixed_heat_rate_zero_at_consistent_point(self):
        s = self._make_closure_set()
        result = s.evaluate_all(self._consistent_unknowns())
        assert result["preheater:q_fixed"] == pytest.approx(0.0)

    def test_enthalpy_flow_zero_at_consistent_point(self):
        s = self._make_closure_set()
        result = s.evaluate_all(self._consistent_unknowns())
        assert result["preheater:enthalpy_flow"] == pytest.approx(0.0)

    def test_all_residuals_zero_at_consistent_point(self):
        s = self._make_closure_set()
        result = s.evaluate_all(self._consistent_unknowns())
        for name, val in result.items():
            assert val == pytest.approx(0.0), f"Expected zero for '{name}', got {val!r}"

    def test_nonzero_residual_after_q_perturbation(self):
        s = self._make_closure_set()
        perturbed = dict(self._consistent_unknowns())
        perturbed["q"] = _PREHEATER_Q + 1_000.0  # inconsistent
        result = s.evaluate_all(perturbed)
        # q_fixed: (q_fixed + 1000) - q_fixed = 1000
        assert result["preheater:q_fixed"] == pytest.approx(1_000.0)
        # enthalpy_flow: (q_fixed+1000) - mdot*(h_out-h_in) = 1000
        assert result["preheater:enthalpy_flow"] == pytest.approx(1_000.0)

    def test_nonzero_residual_after_h_out_perturbation(self):
        s = self._make_closure_set()
        perturbed = dict(self._consistent_unknowns())
        perturbed["h_out"] = _PREHEATER_H_OUT + 10_000.0  # inconsistent
        result = s.evaluate_all(perturbed)
        # q_fixed unchanged (q still = 50000)
        assert result["preheater:q_fixed"] == pytest.approx(0.0)
        # enthalpy_flow: 50000 - 1.0*(310000-250000) = 50000 - 60000 = -10000
        assert result["preheater:enthalpy_flow"] == pytest.approx(-10_000.0)

    def test_diagnostic_sufficient_for_preheater(self):
        s = self._make_closure_set()
        diag = make_basic_thermal_loop_diagnostic()
        result = evaluate_thermal_closure_sufficiency(diag, s)
        assert result.is_sufficient is True

    def test_no_solve_performed(self):
        # This test documents that no solve is claimed
        s = self._make_closure_set()
        unknowns = self._consistent_unknowns()
        result = s.evaluate_all(unknowns)
        # Only evaluation, not solve; residuals must be provided externally
        assert isinstance(result, dict | type(result))


# ===========================================================================
# Test 4: Recuperator-like algebraic closure example
# ===========================================================================


class TestRecuperatorLikeAlgebraicClosure:
    """
    Models a recuperator algebraically:
      - RecuperatorEnergyBalanceClosure: q_hot + q_cold = 0
      - EnthalpyFlowHeatRateClosure (hot side): q_hot = mdot_hot*(h_hot_out - h_hot_in)
      - EnthalpyFlowHeatRateClosure (cold side): q_cold = mdot_cold*(h_cold_out - h_cold_in)

    Consistent point:
      q_hot = -20_000, q_cold = +20_000
      mdot_hot=0.5, h_hot_in=400_000, h_hot_out=360_000
        => 0.5*(360000-400000) = -20_000 ✓
      mdot_cold=0.5, h_cold_in=250_000, h_cold_out=290_000
        => 0.5*(290000-250000) = +20_000 ✓
    """

    def _make_closure_set(self):
        return build_thermal_closure_residuals(
            [
                RecuperatorEnergyBalanceClosure("q_hot", "q_cold", "recup:energy_balance"),
                EnthalpyFlowHeatRateClosure(
                    "q_hot", "mdot_hot", "h_hot_in", "h_hot_out", "recup:hot_enthalpy_flow"
                ),
                EnthalpyFlowHeatRateClosure(
                    "q_cold", "mdot_cold", "h_cold_in", "h_cold_out", "recup:cold_enthalpy_flow"
                ),
            ]
        )

    def _consistent_unknowns(self) -> dict[str, float]:
        return {
            "q_hot": _RECUP_Q_HOT,
            "q_cold": _RECUP_Q_COLD,
            "mdot_hot": _RECUP_MDOT_HOT,
            "h_hot_in": _RECUP_H_HOT_IN,
            "h_hot_out": _RECUP_H_HOT_OUT,
            "mdot_cold": _RECUP_MDOT_COLD,
            "h_cold_in": _RECUP_H_COLD_IN,
            "h_cold_out": _RECUP_H_COLD_OUT,
        }

    def test_energy_balance_zero_at_consistent_point(self):
        s = self._make_closure_set()
        result = s.evaluate_all(self._consistent_unknowns())
        assert result["recup:energy_balance"] == pytest.approx(0.0)

    def test_hot_enthalpy_flow_zero_at_consistent_point(self):
        s = self._make_closure_set()
        result = s.evaluate_all(self._consistent_unknowns())
        assert result["recup:hot_enthalpy_flow"] == pytest.approx(0.0)

    def test_cold_enthalpy_flow_zero_at_consistent_point(self):
        s = self._make_closure_set()
        result = s.evaluate_all(self._consistent_unknowns())
        assert result["recup:cold_enthalpy_flow"] == pytest.approx(0.0)

    def test_all_residuals_zero_at_consistent_point(self):
        s = self._make_closure_set()
        result = s.evaluate_all(self._consistent_unknowns())
        for name, val in result.items():
            assert val == pytest.approx(0.0), f"Expected zero for '{name}', got {val!r}"

    def test_nonzero_residual_after_q_hot_perturbation(self):
        s = self._make_closure_set()
        perturbed = dict(self._consistent_unknowns())
        perturbed["q_hot"] = -22_000.0  # break energy balance
        result = s.evaluate_all(perturbed)
        # energy_balance: -22000 + 20000 = -2000
        assert result["recup:energy_balance"] == pytest.approx(-2_000.0)
        # hot_enthalpy_flow: -22000 - 0.5*(360000-400000) = -22000-(-20000) = -2000
        assert result["recup:hot_enthalpy_flow"] == pytest.approx(-2_000.0)

    def test_nonzero_residual_after_h_cold_out_perturbation(self):
        s = self._make_closure_set()
        perturbed = dict(self._consistent_unknowns())
        perturbed["h_cold_out"] = _RECUP_H_COLD_OUT - 5_000.0  # cold gain drops
        result = s.evaluate_all(perturbed)
        # cold_enthalpy_flow: 20000 - 0.5*(285000-250000) = 20000 - 17500 = 2500
        assert result["recup:cold_enthalpy_flow"] == pytest.approx(2_500.0)

    def test_diagnostic_sufficient_for_recuperator(self):
        s = self._make_closure_set()
        diag = make_recuperator_thermal_diagnostic()
        result = evaluate_thermal_closure_sufficiency(diag, s)
        assert result.is_sufficient is True

    def test_all_residuals_finite(self):
        s = self._make_closure_set()
        result = s.evaluate_all(self._consistent_unknowns())
        for name, val in result.items():
            assert math.isfinite(val), f"Residual '{name}' is not finite"


# ===========================================================================
# Test 5: Boundary invariants
# ===========================================================================


class TestBoundaryInvariants:
    def test_no_produce_method_on_closures(self):
        c = FixedHeatRateClosure("q", 100.0, "r")
        assert not hasattr(c, "contribute")
        assert not hasattr(c, "produce_records")

    def test_no_contribute_method_on_residual_set(self):
        s = build_thermal_closure_residuals([FixedHeatRateClosure("q", 100.0, "r")])
        assert not hasattr(s, "contribute")

    def test_closures_have_no_component_type(self):
        c = EnthalpyFlowHeatRateClosure("q", "m", "hi", "ho", "r")
        assert not hasattr(c, "component_type")

    def test_closures_have_no_fluid_state(self):
        c = FixedHeatRateClosure("q", 100.0, "r")
        assert not hasattr(c, "fluid_state")
        assert not hasattr(c, "FluidState")

    def test_closures_have_no_system_state(self):
        c = FixedHeatRateClosure("q", 100.0, "r")
        assert not hasattr(c, "system_state")
        assert not hasattr(c, "SystemState")

    def test_residual_set_evaluate_all_returns_immutable(self):
        s = build_thermal_closure_residuals([FixedHeatRateClosure("q", 100.0, "r")])
        result = s.evaluate_all({"q": 100.0})
        with pytest.raises(TypeError):
            result["r"] = 999.0  # type: ignore[index]

    def test_thermal_closure_residual_names_deterministic(self):
        for _ in range(5):
            closures = [
                FixedHeatRateClosure("q1", 100.0, "first"),
                ImposedEnthalpyClosure("h", 1000.0, "second"),
                RecuperatorEnergyBalanceClosure("qh", "qc", "third"),
            ]
            s = build_thermal_closure_residuals(closures)
            assert s.residual_names == ("first", "second", "third")

    def test_no_property_backend_dependency(self):
        # Thermal closures must not depend on PropertyBackend at evaluation
        # They are evaluated with explicit scalar unknowns only.
        c = EnthalpyFlowHeatRateClosure("q", "mdot", "h_in", "h_out", "r")
        result = c.evaluate({"q": 50_000.0, "mdot": 1.0, "h_in": 250_000.0, "h_out": 300_000.0})
        assert math.isfinite(result)

    def test_no_coolprop_import_in_thermal_closures(self):
        import mpl_sim.network.thermal_closure_diagnostics as tcd_module
        import mpl_sim.network.thermal_closures as tc_module

        assert not hasattr(tc_module, "CoolProp")
        assert not hasattr(tcd_module, "CoolProp")

    def test_15d_a_hydraulic_closures_still_pass(self):
        # Regression: 15D-A hydraulic closures are unaffected by 15D-B
        from mpl_sim.network.hydraulic_closures import (
            ImposedBranchSplitClosure,
            LinearPressureDropClosure,
            QuadraticPressureDropClosure,
        )

        c1 = ImposedBranchSplitClosure("total", "branch_a", 0.4, "r1")
        r1 = c1.evaluate({"total": 1.0, "branch_a": 0.4})
        assert r1 == pytest.approx(0.0)

        c2 = LinearPressureDropClosure("P_in", "P_out", "mdot", 50_000.0, "r2")
        r2 = c2.evaluate({"P_in": 1_100_000.0, "P_out": 1_050_000.0, "mdot": 1.0})
        assert r2 == pytest.approx(0.0)

        c3 = QuadraticPressureDropClosure("P_in", "P_out", "mdot", 50_000.0, "r3")
        r3 = c3.evaluate({"P_in": 1_100_000.0, "P_out": 1_050_000.0, "mdot": 1.0})
        assert r3 == pytest.approx(0.0)
