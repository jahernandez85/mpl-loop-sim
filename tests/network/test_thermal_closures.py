"""Block 15D-B — Thermal Closure Primitive tests.

Coverage for:
  - FixedHeatRateClosure
  - ImposedEnthalpyClosure
  - ImposedTemperatureLikeClosure
  - SensibleHeatRateClosure
  - EnthalpyFlowHeatRateClosure
  - EffectivenessHeatRateClosure
  - RecuperatorEnergyBalanceClosure
  - ThermalClosureResidualSet
  - build_thermal_closure_residuals

No production component physics.  No SystemState.  No FluidState.
No CoolProp, no PropertyBackend, no correlations, no HX models.
No saturation, phase, quality, or property-backed computation.
All closures are explicit, algebraic, and immutable.
"""

from __future__ import annotations

from types import MappingProxyType

import pytest

from mpl_sim.network.thermal_closures import (
    EffectivenessHeatRateClosure,
    EnthalpyFlowHeatRateClosure,
    FixedHeatRateClosure,
    ImposedEnthalpyClosure,
    ImposedTemperatureLikeClosure,
    RecuperatorEnergyBalanceClosure,
    SensibleHeatRateClosure,
    ThermalClosureKind,
    ThermalClosureResidualSet,
    build_thermal_closure_residuals,
)

# ===========================================================================
# FixedHeatRateClosure tests
# ===========================================================================


class TestFixedHeatRateClosure:
    def test_builds(self):
        c = FixedHeatRateClosure(
            unknown_name="q_heater",
            q_fixed=5000.0,
            residual_name="closure:heater_q",
        )
        assert c.unknown_name == "q_heater"
        assert c.q_fixed == 5000.0
        assert c.residual_name == "closure:heater_q"

    def test_kind(self):
        c = FixedHeatRateClosure("q", 100.0, "r")
        assert c.kind is ThermalClosureKind.FIXED_HEAT_RATE

    def test_is_frozen(self):
        c = FixedHeatRateClosure("q", 100.0, "r")
        with pytest.raises((AttributeError, TypeError)):
            c.q_fixed = 200.0  # type: ignore[misc]

    def test_q_fixed_stored_as_float(self):
        c = FixedHeatRateClosure("q", 200, "r")
        assert isinstance(c.q_fixed, float)
        assert c.q_fixed == 200.0

    def test_evaluate_zero_at_imposed_value(self):
        c = FixedHeatRateClosure("q_heater", 5000.0, "r")
        assert c.evaluate({"q_heater": 5000.0}) == pytest.approx(0.0)

    def test_evaluate_positive_when_above(self):
        c = FixedHeatRateClosure("q", 100.0, "r")
        assert c.evaluate({"q": 150.0}) == pytest.approx(50.0)

    def test_evaluate_negative_when_below(self):
        c = FixedHeatRateClosure("q", 100.0, "r")
        assert c.evaluate({"q": 80.0}) == pytest.approx(-20.0)

    def test_negative_q_fixed_allowed(self):
        c = FixedHeatRateClosure("q", -3000.0, "r")
        assert c.evaluate({"q": -3000.0}) == pytest.approx(0.0)

    def test_zero_q_fixed_allowed(self):
        c = FixedHeatRateClosure("q", 0.0, "r")
        assert c.evaluate({"q": 0.0}) == pytest.approx(0.0)

    def test_rejects_blank_unknown_name(self):
        with pytest.raises(ValueError, match="unknown_name"):
            FixedHeatRateClosure("", 100.0, "r")

    def test_rejects_blank_residual_name(self):
        with pytest.raises(ValueError, match="residual_name"):
            FixedHeatRateClosure("q", 100.0, "")

    def test_rejects_bool_q_fixed(self):
        with pytest.raises(TypeError):
            FixedHeatRateClosure("q", True, "r")  # type: ignore[arg-type]

    def test_rejects_nan_q_fixed(self):
        with pytest.raises(ValueError):
            FixedHeatRateClosure("q", float("nan"), "r")

    def test_rejects_inf_q_fixed(self):
        with pytest.raises(ValueError):
            FixedHeatRateClosure("q", float("inf"), "r")

    def test_rejects_missing_unknown(self):
        c = FixedHeatRateClosure("q_heater", 100.0, "r")
        with pytest.raises(KeyError, match="q_heater"):
            c.evaluate({"q_other": 100.0})

    def test_rejects_bool_unknown_value(self):
        c = FixedHeatRateClosure("q", 100.0, "r")
        with pytest.raises(TypeError):
            c.evaluate({"q": True})  # type: ignore[dict-item]

    def test_rejects_nan_unknown_value(self):
        c = FixedHeatRateClosure("q", 100.0, "r")
        with pytest.raises(ValueError):
            c.evaluate({"q": float("nan")})

    def test_extra_unknowns_silently_ignored(self):
        c = FixedHeatRateClosure("q", 100.0, "r")
        result = c.evaluate({"q": 100.0, "extra": 999.0})
        assert result == pytest.approx(0.0)


# ===========================================================================
# ImposedEnthalpyClosure tests
# ===========================================================================


class TestImposedEnthalpyClosure:
    def test_builds(self):
        c = ImposedEnthalpyClosure(
            unknown_name="h_inlet",
            h_imposed=250_000.0,
            residual_name="closure:h_inlet",
        )
        assert c.unknown_name == "h_inlet"
        assert c.h_imposed == 250_000.0
        assert c.residual_name == "closure:h_inlet"

    def test_kind(self):
        c = ImposedEnthalpyClosure("h", 1000.0, "r")
        assert c.kind is ThermalClosureKind.IMPOSED_ENTHALPY

    def test_is_frozen(self):
        c = ImposedEnthalpyClosure("h", 1000.0, "r")
        with pytest.raises((AttributeError, TypeError)):
            c.h_imposed = 2000.0  # type: ignore[misc]

    def test_evaluate_zero_at_imposed(self):
        c = ImposedEnthalpyClosure("h", 250_000.0, "r")
        assert c.evaluate({"h": 250_000.0}) == pytest.approx(0.0)

    def test_evaluate_nonzero(self):
        c = ImposedEnthalpyClosure("h", 250_000.0, "r")
        assert c.evaluate({"h": 260_000.0}) == pytest.approx(10_000.0)

    def test_negative_h_allowed(self):
        c = ImposedEnthalpyClosure("h", -1000.0, "r")
        assert c.evaluate({"h": -1000.0}) == pytest.approx(0.0)

    def test_h_stored_as_float(self):
        c = ImposedEnthalpyClosure("h", 100, "r")
        assert isinstance(c.h_imposed, float)

    def test_rejects_blank_unknown_name(self):
        with pytest.raises(ValueError):
            ImposedEnthalpyClosure("  ", 1000.0, "r")

    def test_rejects_blank_residual_name(self):
        with pytest.raises(ValueError):
            ImposedEnthalpyClosure("h", 1000.0, "  ")

    def test_rejects_bool_h_imposed(self):
        with pytest.raises(TypeError):
            ImposedEnthalpyClosure("h", True, "r")  # type: ignore[arg-type]

    def test_rejects_nan_h_imposed(self):
        with pytest.raises(ValueError):
            ImposedEnthalpyClosure("h", float("nan"), "r")

    def test_rejects_inf_h_imposed(self):
        with pytest.raises(ValueError):
            ImposedEnthalpyClosure("h", float("inf"), "r")

    def test_rejects_missing_unknown(self):
        c = ImposedEnthalpyClosure("h_in", 1000.0, "r")
        with pytest.raises(KeyError):
            c.evaluate({"h_out": 1000.0})


# ===========================================================================
# ImposedTemperatureLikeClosure tests
# ===========================================================================


class TestImposedTemperatureLikeClosure:
    def test_builds(self):
        c = ImposedTemperatureLikeClosure(
            unknown_name="theta_ref",
            theta_imposed=300.0,
            residual_name="closure:theta_ref",
        )
        assert c.unknown_name == "theta_ref"
        assert c.theta_imposed == 300.0
        assert c.residual_name == "closure:theta_ref"

    def test_kind(self):
        c = ImposedTemperatureLikeClosure("theta", 300.0, "r")
        assert c.kind is ThermalClosureKind.IMPOSED_TEMPERATURE_LIKE

    def test_is_frozen(self):
        c = ImposedTemperatureLikeClosure("theta", 300.0, "r")
        with pytest.raises((AttributeError, TypeError)):
            c.theta_imposed = 400.0  # type: ignore[misc]

    def test_evaluate_zero_at_imposed(self):
        c = ImposedTemperatureLikeClosure("theta", 300.0, "r")
        assert c.evaluate({"theta": 300.0}) == pytest.approx(0.0)

    def test_evaluate_nonzero(self):
        c = ImposedTemperatureLikeClosure("theta", 300.0, "r")
        assert c.evaluate({"theta": 350.0}) == pytest.approx(50.0)

    def test_negative_theta_allowed(self):
        c = ImposedTemperatureLikeClosure("theta", -50.0, "r")
        assert c.evaluate({"theta": -50.0}) == pytest.approx(0.0)

    def test_theta_stored_as_float(self):
        c = ImposedTemperatureLikeClosure("theta", 300, "r")
        assert isinstance(c.theta_imposed, float)

    def test_rejects_bool_theta_imposed(self):
        with pytest.raises(TypeError):
            ImposedTemperatureLikeClosure("theta", True, "r")  # type: ignore[arg-type]

    def test_rejects_nan_theta_imposed(self):
        with pytest.raises(ValueError):
            ImposedTemperatureLikeClosure("theta", float("nan"), "r")

    def test_rejects_inf_theta_imposed(self):
        with pytest.raises(ValueError):
            ImposedTemperatureLikeClosure("theta", float("inf"), "r")

    def test_rejects_blank_name(self):
        with pytest.raises(ValueError):
            ImposedTemperatureLikeClosure("", 300.0, "r")

    def test_rejects_missing_unknown(self):
        c = ImposedTemperatureLikeClosure("theta", 300.0, "r")
        with pytest.raises(KeyError):
            c.evaluate({"theta_other": 300.0})

    def test_no_property_lookup_occurs(self):
        # This closure is a user-supplied scalar only; evaluation must not
        # call CoolProp or any property engine.
        c = ImposedTemperatureLikeClosure("theta", 273.15, "r")
        result = c.evaluate({"theta": 273.15})
        assert result == pytest.approx(0.0)


# ===========================================================================
# SensibleHeatRateClosure tests
# ===========================================================================


class TestSensibleHeatRateClosure:
    def test_builds(self):
        c = SensibleHeatRateClosure(
            q_name="q_heater",
            mdot_name="mdot",
            theta_in_name="theta_in",
            theta_out_name="theta_out",
            cp=4186.0,
            residual_name="closure:sensible_q",
        )
        assert c.q_name == "q_heater"
        assert c.mdot_name == "mdot"
        assert c.theta_in_name == "theta_in"
        assert c.theta_out_name == "theta_out"
        assert c.cp == 4186.0
        assert c.residual_name == "closure:sensible_q"

    def test_kind(self):
        c = SensibleHeatRateClosure("q", "m", "ti", "to", 1000.0, "r")
        assert c.kind is ThermalClosureKind.SENSIBLE_HEAT_RATE

    def test_is_frozen(self):
        c = SensibleHeatRateClosure("q", "m", "ti", "to", 1000.0, "r")
        with pytest.raises((AttributeError, TypeError)):
            c.cp = 2000.0  # type: ignore[misc]

    def test_cp_stored_as_float(self):
        c = SensibleHeatRateClosure("q", "m", "ti", "to", 1000, "r")
        assert isinstance(c.cp, float)

    def test_evaluate_zero_at_consistent_point(self):
        # q = mdot * cp * (theta_out - theta_in) = 1.0 * 1000.0 * (350.0 - 300.0) = 50000
        c = SensibleHeatRateClosure("q", "mdot", "theta_in", "theta_out", 1000.0, "r")
        unknowns = {"q": 50_000.0, "mdot": 1.0, "theta_in": 300.0, "theta_out": 350.0}
        assert c.evaluate(unknowns) == pytest.approx(0.0)

    def test_sign_convention_heating(self):
        # theta_out > theta_in => positive q (heat added)
        c = SensibleHeatRateClosure("q", "mdot", "ti", "to", 1000.0, "r")
        # q = 1.0 * 1000 * (320-300) = 20000; residual = q - 20000
        r = c.evaluate({"q": 25_000.0, "mdot": 1.0, "ti": 300.0, "to": 320.0})
        assert r == pytest.approx(5_000.0)

    def test_sign_convention_cooling(self):
        # theta_out < theta_in => negative q (heat removed)
        c = SensibleHeatRateClosure("q", "mdot", "ti", "to", 1000.0, "r")
        # q = 1.0 * 1000 * (280-300) = -20000; residual = -20000 - (-20000) = 0
        r = c.evaluate({"q": -20_000.0, "mdot": 1.0, "ti": 300.0, "to": 280.0})
        assert r == pytest.approx(0.0)

    def test_evaluate_nonzero_at_inconsistent_point(self):
        c = SensibleHeatRateClosure("q", "mdot", "ti", "to", 1000.0, "r")
        r = c.evaluate({"q": 1_000.0, "mdot": 1.0, "ti": 300.0, "to": 350.0})
        assert r == pytest.approx(1_000.0 - 50_000.0)

    def test_cp_must_be_positive(self):
        with pytest.raises(ValueError, match="positive"):
            SensibleHeatRateClosure("q", "m", "ti", "to", 0.0, "r")

    def test_cp_negative_rejected(self):
        with pytest.raises(ValueError, match="positive"):
            SensibleHeatRateClosure("q", "m", "ti", "to", -100.0, "r")

    def test_cp_bool_rejected(self):
        with pytest.raises(TypeError):
            SensibleHeatRateClosure("q", "m", "ti", "to", True, "r")  # type: ignore[arg-type]

    def test_cp_nan_rejected(self):
        with pytest.raises(ValueError):
            SensibleHeatRateClosure("q", "m", "ti", "to", float("nan"), "r")

    def test_cp_inf_rejected(self):
        with pytest.raises(ValueError):
            SensibleHeatRateClosure("q", "m", "ti", "to", float("inf"), "r")

    def test_blank_q_name_rejected(self):
        with pytest.raises(ValueError, match="q_name"):
            SensibleHeatRateClosure("", "m", "ti", "to", 1000.0, "r")

    def test_blank_mdot_name_rejected(self):
        with pytest.raises(ValueError, match="mdot_name"):
            SensibleHeatRateClosure("q", "", "ti", "to", 1000.0, "r")

    def test_blank_theta_in_name_rejected(self):
        with pytest.raises(ValueError, match="theta_in_name"):
            SensibleHeatRateClosure("q", "m", "", "to", 1000.0, "r")

    def test_blank_theta_out_name_rejected(self):
        with pytest.raises(ValueError, match="theta_out_name"):
            SensibleHeatRateClosure("q", "m", "ti", "", 1000.0, "r")

    def test_missing_unknown_raises(self):
        c = SensibleHeatRateClosure("q", "mdot", "ti", "to", 1000.0, "r")
        with pytest.raises(KeyError):
            c.evaluate({"q": 1.0, "mdot": 1.0, "ti": 300.0})  # missing "to"

    def test_bool_unknown_rejected(self):
        c = SensibleHeatRateClosure("q", "mdot", "ti", "to", 1000.0, "r")
        with pytest.raises(TypeError):
            c.evaluate({"q": True, "mdot": 1.0, "ti": 300.0, "to": 350.0})  # type: ignore[dict-item]

    def test_nan_unknown_rejected(self):
        c = SensibleHeatRateClosure("q", "mdot", "ti", "to", 1000.0, "r")
        with pytest.raises(ValueError):
            c.evaluate({"q": float("nan"), "mdot": 1.0, "ti": 300.0, "to": 350.0})


# ===========================================================================
# EnthalpyFlowHeatRateClosure tests
# ===========================================================================


class TestEnthalpyFlowHeatRateClosure:
    def test_builds(self):
        c = EnthalpyFlowHeatRateClosure(
            q_name="q_evap",
            mdot_name="mdot_primary",
            h_in_name="h_in",
            h_out_name="h_out",
            residual_name="closure:evap_q",
        )
        assert c.q_name == "q_evap"
        assert c.mdot_name == "mdot_primary"
        assert c.h_in_name == "h_in"
        assert c.h_out_name == "h_out"
        assert c.residual_name == "closure:evap_q"

    def test_kind(self):
        c = EnthalpyFlowHeatRateClosure("q", "m", "hi", "ho", "r")
        assert c.kind is ThermalClosureKind.ENTHALPY_FLOW_HEAT_RATE

    def test_is_frozen(self):
        c = EnthalpyFlowHeatRateClosure("q", "m", "hi", "ho", "r")
        with pytest.raises((AttributeError, TypeError)):
            c.q_name = "q2"  # type: ignore[misc]

    def test_evaluate_zero_at_consistent_point(self):
        # q = mdot * (h_out - h_in) = 1.0 * (500000 - 250000) = 250000
        c = EnthalpyFlowHeatRateClosure("q", "mdot", "h_in", "h_out", "r")
        unknowns = {"q": 250_000.0, "mdot": 1.0, "h_in": 250_000.0, "h_out": 500_000.0}
        assert c.evaluate(unknowns) == pytest.approx(0.0)

    def test_sign_convention_enthalpy_gain(self):
        # h_out > h_in, mdot > 0 => positive q
        c = EnthalpyFlowHeatRateClosure("q", "mdot", "h_in", "h_out", "r")
        # q = 0.5 * (300000 - 250000) = 25000; residual = 30000 - 25000 = 5000
        r = c.evaluate({"q": 30_000.0, "mdot": 0.5, "h_in": 250_000.0, "h_out": 300_000.0})
        assert r == pytest.approx(5_000.0)

    def test_sign_convention_enthalpy_loss(self):
        # h_out < h_in => negative q (condensation or cooling)
        c = EnthalpyFlowHeatRateClosure("q", "mdot", "h_in", "h_out", "r")
        # q = 1.0 * (200000 - 400000) = -200000
        r = c.evaluate({"q": -200_000.0, "mdot": 1.0, "h_in": 400_000.0, "h_out": 200_000.0})
        assert r == pytest.approx(0.0)

    def test_evaluate_nonzero_at_inconsistent_point(self):
        c = EnthalpyFlowHeatRateClosure("q", "mdot", "h_in", "h_out", "r")
        r = c.evaluate({"q": 0.0, "mdot": 1.0, "h_in": 100_000.0, "h_out": 200_000.0})
        assert r == pytest.approx(-100_000.0)

    def test_blank_q_name_rejected(self):
        with pytest.raises(ValueError):
            EnthalpyFlowHeatRateClosure("", "m", "hi", "ho", "r")

    def test_blank_mdot_name_rejected(self):
        with pytest.raises(ValueError):
            EnthalpyFlowHeatRateClosure("q", "", "hi", "ho", "r")

    def test_blank_h_in_name_rejected(self):
        with pytest.raises(ValueError):
            EnthalpyFlowHeatRateClosure("q", "m", "", "ho", "r")

    def test_blank_h_out_name_rejected(self):
        with pytest.raises(ValueError):
            EnthalpyFlowHeatRateClosure("q", "m", "hi", "", "r")

    def test_blank_residual_name_rejected(self):
        with pytest.raises(ValueError):
            EnthalpyFlowHeatRateClosure("q", "m", "hi", "ho", "")

    def test_missing_unknown_raises(self):
        c = EnthalpyFlowHeatRateClosure("q", "mdot", "h_in", "h_out", "r")
        with pytest.raises(KeyError):
            c.evaluate({"q": 1.0, "mdot": 1.0, "h_in": 100.0})  # missing h_out

    def test_nan_unknown_rejected(self):
        c = EnthalpyFlowHeatRateClosure("q", "mdot", "h_in", "h_out", "r")
        with pytest.raises(ValueError):
            c.evaluate({"q": float("nan"), "mdot": 1.0, "h_in": 100.0, "h_out": 200.0})

    def test_bool_unknown_rejected(self):
        c = EnthalpyFlowHeatRateClosure("q", "mdot", "h_in", "h_out", "r")
        with pytest.raises(TypeError):
            c.evaluate({"q": True, "mdot": 1.0, "h_in": 100.0, "h_out": 200.0})  # type: ignore[dict-item]


# ===========================================================================
# EffectivenessHeatRateClosure tests
# ===========================================================================


class TestEffectivenessHeatRateClosure:
    def test_builds(self):
        c = EffectivenessHeatRateClosure(
            q_name="q_hx",
            q_max_name="q_max",
            effectiveness=0.85,
            residual_name="closure:effectiveness",
        )
        assert c.q_name == "q_hx"
        assert c.q_max_name == "q_max"
        assert c.effectiveness == 0.85
        assert c.residual_name == "closure:effectiveness"

    def test_kind(self):
        c = EffectivenessHeatRateClosure("q", "qm", 0.5, "r")
        assert c.kind is ThermalClosureKind.EFFECTIVENESS_HEAT_RATE

    def test_is_frozen(self):
        c = EffectivenessHeatRateClosure("q", "qm", 0.5, "r")
        with pytest.raises((AttributeError, TypeError)):
            c.effectiveness = 0.9  # type: ignore[misc]

    def test_effectiveness_stored_as_float(self):
        c = EffectivenessHeatRateClosure("q", "qm", 1, "r")
        assert isinstance(c.effectiveness, float)
        assert c.effectiveness == 1.0

    def test_evaluate_zero_at_consistent_point(self):
        # q = 0.8 * q_max = 0.8 * 10000 = 8000
        c = EffectivenessHeatRateClosure("q", "q_max", 0.8, "r")
        assert c.evaluate({"q": 8_000.0, "q_max": 10_000.0}) == pytest.approx(0.0)

    def test_evaluate_nonzero(self):
        c = EffectivenessHeatRateClosure("q", "q_max", 0.8, "r")
        r = c.evaluate({"q": 9_000.0, "q_max": 10_000.0})
        assert r == pytest.approx(1_000.0)  # 9000 - 0.8*10000 = 1000

    def test_effectiveness_zero_allowed(self):
        c = EffectivenessHeatRateClosure("q", "qm", 0.0, "r")
        assert c.evaluate({"q": 0.0, "qm": 10_000.0}) == pytest.approx(0.0)

    def test_effectiveness_one_allowed(self):
        c = EffectivenessHeatRateClosure("q", "qm", 1.0, "r")
        assert c.evaluate({"q": 10_000.0, "qm": 10_000.0}) == pytest.approx(0.0)

    def test_effectiveness_rejects_above_one(self):
        with pytest.raises(ValueError, match="effectiveness"):
            EffectivenessHeatRateClosure("q", "qm", 1.01, "r")

    def test_effectiveness_rejects_below_zero(self):
        with pytest.raises(ValueError, match="effectiveness"):
            EffectivenessHeatRateClosure("q", "qm", -0.01, "r")

    def test_effectiveness_rejects_bool(self):
        with pytest.raises(TypeError):
            EffectivenessHeatRateClosure("q", "qm", True, "r")  # type: ignore[arg-type]

    def test_effectiveness_rejects_nan(self):
        with pytest.raises(ValueError):
            EffectivenessHeatRateClosure("q", "qm", float("nan"), "r")

    def test_blank_q_name_rejected(self):
        with pytest.raises(ValueError):
            EffectivenessHeatRateClosure("", "qm", 0.5, "r")

    def test_blank_q_max_name_rejected(self):
        with pytest.raises(ValueError):
            EffectivenessHeatRateClosure("q", "", 0.5, "r")

    def test_missing_unknown_raises(self):
        c = EffectivenessHeatRateClosure("q", "q_max", 0.8, "r")
        with pytest.raises(KeyError):
            c.evaluate({"q": 8_000.0})  # missing q_max

    def test_nan_unknown_rejected(self):
        c = EffectivenessHeatRateClosure("q", "q_max", 0.8, "r")
        with pytest.raises(ValueError):
            c.evaluate({"q": float("nan"), "q_max": 10_000.0})


# ===========================================================================
# RecuperatorEnergyBalanceClosure tests
# ===========================================================================


class TestRecuperatorEnergyBalanceClosure:
    def test_builds(self):
        c = RecuperatorEnergyBalanceClosure(
            q_hot_name="q_hot",
            q_cold_name="q_cold",
            residual_name="closure:recuperator_balance",
        )
        assert c.q_hot_name == "q_hot"
        assert c.q_cold_name == "q_cold"
        assert c.residual_name == "closure:recuperator_balance"

    def test_kind(self):
        c = RecuperatorEnergyBalanceClosure("q_hot", "q_cold", "r")
        assert c.kind is ThermalClosureKind.RECUPERATOR_ENERGY_BALANCE

    def test_is_frozen(self):
        c = RecuperatorEnergyBalanceClosure("q_hot", "q_cold", "r")
        with pytest.raises((AttributeError, TypeError)):
            c.q_hot_name = "q_other"  # type: ignore[misc]

    def test_evaluate_zero_at_balance(self):
        # q_hot = -5000 (heat given up), q_cold = +5000 (heat received)
        c = RecuperatorEnergyBalanceClosure("q_hot", "q_cold", "r")
        assert c.evaluate({"q_hot": -5_000.0, "q_cold": 5_000.0}) == pytest.approx(0.0)

    def test_sign_convention_positive_sum(self):
        # Both positive => non-zero residual (energy not balanced)
        c = RecuperatorEnergyBalanceClosure("q_hot", "q_cold", "r")
        r = c.evaluate({"q_hot": 3_000.0, "q_cold": 2_000.0})
        assert r == pytest.approx(5_000.0)

    def test_sign_convention_negative_sum(self):
        c = RecuperatorEnergyBalanceClosure("q_hot", "q_cold", "r")
        r = c.evaluate({"q_hot": -6_000.0, "q_cold": 4_000.0})
        assert r == pytest.approx(-2_000.0)

    def test_rejects_blank_q_hot_name(self):
        with pytest.raises(ValueError):
            RecuperatorEnergyBalanceClosure("", "q_cold", "r")

    def test_rejects_blank_q_cold_name(self):
        with pytest.raises(ValueError):
            RecuperatorEnergyBalanceClosure("q_hot", "", "r")

    def test_rejects_blank_residual_name(self):
        with pytest.raises(ValueError):
            RecuperatorEnergyBalanceClosure("q_hot", "q_cold", "")

    def test_missing_q_hot_raises(self):
        c = RecuperatorEnergyBalanceClosure("q_hot", "q_cold", "r")
        with pytest.raises(KeyError):
            c.evaluate({"q_cold": 5_000.0})

    def test_missing_q_cold_raises(self):
        c = RecuperatorEnergyBalanceClosure("q_hot", "q_cold", "r")
        with pytest.raises(KeyError):
            c.evaluate({"q_hot": -5_000.0})

    def test_nan_unknown_rejected(self):
        c = RecuperatorEnergyBalanceClosure("q_hot", "q_cold", "r")
        with pytest.raises(ValueError):
            c.evaluate({"q_hot": float("nan"), "q_cold": 5_000.0})

    def test_bool_unknown_rejected(self):
        c = RecuperatorEnergyBalanceClosure("q_hot", "q_cold", "r")
        with pytest.raises(TypeError):
            c.evaluate({"q_hot": True, "q_cold": 5_000.0})  # type: ignore[dict-item]


# ===========================================================================
# ThermalClosureResidualSet tests
# ===========================================================================


class TestThermalClosureResidualSet:
    def _make_set(self) -> ThermalClosureResidualSet:
        closures = [
            FixedHeatRateClosure("q_heater", 5_000.0, "res:q_fixed"),
            EnthalpyFlowHeatRateClosure("q_evap", "mdot", "h_in", "h_out", "res:enthalpy_flow"),
        ]
        return build_thermal_closure_residuals(closures)

    def test_builds_from_closures(self):
        s = self._make_set()
        assert len(s.closures) == 2

    def test_residual_names_ordered(self):
        s = self._make_set()
        assert s.residual_names == ("res:q_fixed", "res:enthalpy_flow")

    def test_is_frozen(self):
        s = self._make_set()
        with pytest.raises((AttributeError, TypeError)):
            s.closures = ()  # type: ignore[misc]

    def test_evaluate_all_returns_mapping_proxy(self):
        s = self._make_set()
        unknowns = {
            "q_heater": 5_000.0,
            "q_evap": 250_000.0,
            "mdot": 1.0,
            "h_in": 250_000.0,
            "h_out": 500_000.0,
        }
        result = s.evaluate_all(unknowns)
        assert isinstance(result, MappingProxyType)

    def test_evaluate_all_zero_at_consistent_point(self):
        s = self._make_set()
        unknowns = {
            "q_heater": 5_000.0,
            "q_evap": 250_000.0,
            "mdot": 1.0,
            "h_in": 250_000.0,
            "h_out": 500_000.0,
        }
        result = s.evaluate_all(unknowns)
        assert result["res:q_fixed"] == pytest.approx(0.0)
        assert result["res:enthalpy_flow"] == pytest.approx(0.0)

    def test_evaluate_all_nonzero_at_inconsistent_point(self):
        s = self._make_set()
        unknowns = {
            "q_heater": 9_999.0,
            "q_evap": 1.0,
            "mdot": 1.0,
            "h_in": 250_000.0,
            "h_out": 500_000.0,
        }
        result = s.evaluate_all(unknowns)
        assert result["res:q_fixed"] != pytest.approx(0.0)

    def test_output_map_is_read_only(self):
        s = self._make_set()
        unknowns = {
            "q_heater": 5_000.0,
            "q_evap": 250_000.0,
            "mdot": 1.0,
            "h_in": 250_000.0,
            "h_out": 500_000.0,
        }
        result = s.evaluate_all(unknowns)
        with pytest.raises(TypeError):
            result["res:q_fixed"] = 999.0  # type: ignore[index]

    def test_metadata_none_by_default(self):
        s = self._make_set()
        assert s.metadata is None

    def test_metadata_defensively_copied(self):
        meta: dict[str, object] = {"block": "15D-B"}
        c = FixedHeatRateClosure("q", 100.0, "r")
        s = build_thermal_closure_residuals([c], metadata=meta)
        assert s.metadata is not None
        assert s.metadata["block"] == "15D-B"
        meta["block"] = "modified"
        assert s.metadata["block"] == "15D-B"

    def test_metadata_is_mapping_proxy(self):
        meta: dict[str, object] = {"block": "15D-B"}
        c = FixedHeatRateClosure("q", 100.0, "r")
        s = build_thermal_closure_residuals([c], metadata=meta)
        assert isinstance(s.metadata, MappingProxyType)

    def test_extra_unknowns_silently_ignored(self):
        s = self._make_set()
        unknowns = {
            "q_heater": 5_000.0,
            "q_evap": 250_000.0,
            "mdot": 1.0,
            "h_in": 250_000.0,
            "h_out": 500_000.0,
            "extra_unknown": 999.0,
        }
        result = s.evaluate_all(unknowns)
        assert "res:q_fixed" in result
        assert "res:enthalpy_flow" in result


# ===========================================================================
# build_thermal_closure_residuals tests
# ===========================================================================


class TestBuildThermalClosureResiduals:
    def test_accepts_single_closure(self):
        c = FixedHeatRateClosure("q", 100.0, "r")
        s = build_thermal_closure_residuals([c])
        assert len(s.closures) == 1

    def test_accepts_all_closure_types(self):
        closures = [
            FixedHeatRateClosure("q1", 100.0, "r1"),
            ImposedEnthalpyClosure("h", 1000.0, "r2"),
            ImposedTemperatureLikeClosure("theta", 300.0, "r3"),
            SensibleHeatRateClosure("q2", "m", "ti", "to", 1000.0, "r4"),
            EnthalpyFlowHeatRateClosure("q3", "m2", "hi", "ho", "r5"),
            EffectivenessHeatRateClosure("q4", "qmax", 0.8, "r6"),
            RecuperatorEnergyBalanceClosure("qh", "qc", "r7"),
        ]
        s = build_thermal_closure_residuals(closures)
        assert len(s.closures) == 7

    def test_rejects_empty_list(self):
        with pytest.raises(ValueError, match="empty"):
            build_thermal_closure_residuals([])

    def test_rejects_duplicate_residual_name(self):
        c1 = FixedHeatRateClosure("q1", 100.0, "dup_name")
        c2 = FixedHeatRateClosure("q2", 200.0, "dup_name")
        with pytest.raises(ValueError, match="duplicate"):
            build_thermal_closure_residuals([c1, c2])

    def test_rejects_non_closure_item(self):
        with pytest.raises(TypeError, match="recognized"):
            build_thermal_closure_residuals(["not_a_closure"])  # type: ignore[list-item]

    def test_ordering_preserved(self):
        c1 = FixedHeatRateClosure("q1", 100.0, "first")
        c2 = ImposedEnthalpyClosure("h", 1000.0, "second")
        c3 = RecuperatorEnergyBalanceClosure("qh", "qc", "third")
        s = build_thermal_closure_residuals([c1, c2, c3])
        assert s.residual_names == ("first", "second", "third")

    def test_metadata_optional(self):
        c = FixedHeatRateClosure("q", 100.0, "r")
        s = build_thermal_closure_residuals([c])
        assert s.metadata is None

    def test_metadata_passed_correctly(self):
        c = FixedHeatRateClosure("q", 100.0, "r")
        s = build_thermal_closure_residuals([c], metadata={"version": "15D-B"})
        assert s.metadata is not None
        assert s.metadata["version"] == "15D-B"

    def test_closures_stored_as_tuple(self):
        c = FixedHeatRateClosure("q", 100.0, "r")
        s = build_thermal_closure_residuals([c])
        assert isinstance(s.closures, tuple)
