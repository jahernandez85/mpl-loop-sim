"""Phase 13C: residual / unknown / scaling framework tests.

Verifies all 22 required coverage items:

 1.  Valid UnknownSpec construction.
 2.  Invalid unknown name or unit rejected.
 3.  Invalid unknown bounds rejected: nan, inf, bool, lower >= upper.
 4.  Valid ResidualSpec construction.
 5.  Invalid residual name or unit rejected.
 6.  Invalid scale rejected: zero, negative, nan, inf, bool.
 7.  Valid ResidualEvaluation construction.
 8.  Invalid residual value rejected: nan, inf, bool.
 9.  ResidualVector preserves insertion order.
10.  Duplicate residual names rejected.
11.  Empty residual vector rejected.
12.  Scaled residual values are value / scale.
13.  max_abs_scaled norm is correct.
14.  l2_scaled norm is correct.
15.  is_converged returns True/False around the tolerance boundary.
16.  Invalid convergence tolerance rejected: zero, negative, nan, inf, bool.
17.  Energy residual representation example.
18.  Pressure residual representation example.
19.  Combined energy+pressure residual vector representation.
20.  No solver or network API is introduced by Phase 13C.
21.  Public exports from mpl_sim.closed_loop include all Phase 13C types.
22.  Phase 13A/13B regression: existing solvers are unaffected.

Architecture constraints:
  - Imports only from mpl_sim.closed_loop public API.
  - No CoolProp, no PropertyBackend, no network, no generic solver.
  - All arithmetic is deterministic; no property lookup occurs.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest

from mpl_sim.closed_loop import (
    ResidualEvaluation,
    ResidualSpec,
    ResidualVector,
    UnknownSpec,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parents[2]


def _make_spec(name: str = "energy", unit: str = "J/kg", scale: float = 1000.0) -> ResidualSpec:
    return ResidualSpec(name=name, unit=unit, scale=scale)


def _make_eval(
    name: str = "energy",
    unit: str = "J/kg",
    scale: float = 1000.0,
    value: float = 50.0,
) -> ResidualEvaluation:
    return ResidualEvaluation(spec=_make_spec(name=name, unit=unit, scale=scale), value=value)


# ---------------------------------------------------------------------------
# 1. Valid UnknownSpec construction
# ---------------------------------------------------------------------------


class TestUnknownSpecValid:
    def test_unbounded(self) -> None:
        u = UnknownSpec(name="Q_cond", unit="W")
        assert u.name == "Q_cond"
        assert u.unit == "W"
        assert u.lower is None
        assert u.upper is None

    def test_lower_only(self) -> None:
        u = UnknownSpec(name="mdot", unit="kg/s", lower=0.0)
        assert u.lower == 0.0
        assert u.upper is None

    def test_upper_only(self) -> None:
        u = UnknownSpec(name="mdot", unit="kg/s", upper=10.0)
        assert u.lower is None
        assert u.upper == 10.0

    def test_both_bounds(self) -> None:
        u = UnknownSpec(name="mdot", unit="kg/s", lower=0.001, upper=1.0)
        assert u.lower == 0.001
        assert u.upper == 1.0

    def test_negative_lower(self) -> None:
        u = UnknownSpec(name="Q_cond", unit="W", lower=-5000.0, upper=-100.0)
        assert u.lower == -5000.0

    def test_frozen(self) -> None:
        u = UnknownSpec(name="x", unit="m")
        with pytest.raises((AttributeError, TypeError)):
            u.name = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 2. Invalid unknown name or unit
# ---------------------------------------------------------------------------


class TestUnknownSpecInvalidNameUnit:
    def test_empty_name(self) -> None:
        with pytest.raises(ValueError, match="name"):
            UnknownSpec(name="", unit="W")

    def test_non_string_name(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            UnknownSpec(name=123, unit="W")  # type: ignore[arg-type]

    def test_none_name(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            UnknownSpec(name=None, unit="W")  # type: ignore[arg-type]

    def test_empty_unit(self) -> None:
        with pytest.raises(ValueError, match="unit"):
            UnknownSpec(name="x", unit="")

    def test_non_string_unit(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            UnknownSpec(name="x", unit=42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 3. Invalid unknown bounds
# ---------------------------------------------------------------------------


class TestUnknownSpecInvalidBounds:
    def test_lower_nan(self) -> None:
        with pytest.raises(ValueError, match="lower"):
            UnknownSpec(name="x", unit="m", lower=float("nan"))

    def test_upper_nan(self) -> None:
        with pytest.raises(ValueError, match="upper"):
            UnknownSpec(name="x", unit="m", upper=float("nan"))

    def test_lower_inf(self) -> None:
        with pytest.raises(ValueError, match="lower"):
            UnknownSpec(name="x", unit="m", lower=float("inf"))

    def test_upper_neg_inf(self) -> None:
        with pytest.raises(ValueError, match="upper"):
            UnknownSpec(name="x", unit="m", upper=float("-inf"))

    def test_lower_bool_true(self) -> None:
        with pytest.raises(ValueError, match="lower"):
            UnknownSpec(name="x", unit="m", lower=True)  # type: ignore[arg-type]

    def test_lower_bool_false(self) -> None:
        with pytest.raises(ValueError, match="lower"):
            UnknownSpec(name="x", unit="m", lower=False)  # type: ignore[arg-type]

    def test_upper_bool_true(self) -> None:
        with pytest.raises(ValueError, match="upper"):
            UnknownSpec(name="x", unit="m", upper=True)  # type: ignore[arg-type]

    def test_upper_bool_false(self) -> None:
        with pytest.raises(ValueError, match="upper"):
            UnknownSpec(name="x", unit="m", upper=False)  # type: ignore[arg-type]

    def test_lower_equals_upper(self) -> None:
        with pytest.raises(ValueError, match="lower"):
            UnknownSpec(name="x", unit="m", lower=1.0, upper=1.0)

    def test_lower_greater_than_upper(self) -> None:
        with pytest.raises(ValueError, match="lower"):
            UnknownSpec(name="x", unit="m", lower=2.0, upper=1.0)


# ---------------------------------------------------------------------------
# 4. Valid ResidualSpec construction
# ---------------------------------------------------------------------------


class TestResidualSpecValid:
    def test_basic(self) -> None:
        spec = ResidualSpec(name="energy", unit="J/kg", scale=1000.0)
        assert spec.name == "energy"
        assert spec.unit == "J/kg"
        assert spec.scale == 1000.0

    def test_small_scale(self) -> None:
        spec = ResidualSpec(name="pressure", unit="Pa", scale=0.001)
        assert spec.scale == 0.001

    def test_large_scale(self) -> None:
        spec = ResidualSpec(name="pressure", unit="Pa", scale=1e6)
        assert spec.scale == 1e6

    def test_frozen(self) -> None:
        spec = ResidualSpec(name="e", unit="J/kg", scale=1.0)
        with pytest.raises((AttributeError, TypeError)):
            spec.scale = 2.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 5. Invalid residual name or unit
# ---------------------------------------------------------------------------


class TestResidualSpecInvalidNameUnit:
    def test_empty_name(self) -> None:
        with pytest.raises(ValueError, match="name"):
            ResidualSpec(name="", unit="J/kg", scale=1000.0)

    def test_none_name(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            ResidualSpec(name=None, unit="J/kg", scale=1000.0)  # type: ignore[arg-type]

    def test_empty_unit(self) -> None:
        with pytest.raises(ValueError, match="unit"):
            ResidualSpec(name="energy", unit="", scale=1000.0)

    def test_none_unit(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            ResidualSpec(name="energy", unit=None, scale=1000.0)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 6. Invalid scale
# ---------------------------------------------------------------------------


class TestResidualSpecInvalidScale:
    def test_zero(self) -> None:
        with pytest.raises(ValueError, match="scale"):
            ResidualSpec(name="e", unit="J/kg", scale=0.0)

    def test_negative(self) -> None:
        with pytest.raises(ValueError, match="scale"):
            ResidualSpec(name="e", unit="J/kg", scale=-1.0)

    def test_nan(self) -> None:
        with pytest.raises(ValueError, match="scale"):
            ResidualSpec(name="e", unit="J/kg", scale=float("nan"))

    def test_inf(self) -> None:
        with pytest.raises(ValueError, match="scale"):
            ResidualSpec(name="e", unit="J/kg", scale=float("inf"))

    def test_bool_true(self) -> None:
        with pytest.raises(ValueError, match="scale"):
            ResidualSpec(name="e", unit="J/kg", scale=True)  # type: ignore[arg-type]

    def test_bool_false(self) -> None:
        with pytest.raises(ValueError, match="scale"):
            ResidualSpec(name="e", unit="J/kg", scale=False)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 7. Valid ResidualEvaluation construction
# ---------------------------------------------------------------------------


class TestResidualEvaluationValid:
    def test_positive_value(self) -> None:
        spec = _make_spec()
        ev = ResidualEvaluation(spec=spec, value=200.0)
        assert ev.spec is spec
        assert ev.value == 200.0

    def test_zero_value(self) -> None:
        ev = ResidualEvaluation(spec=_make_spec(), value=0.0)
        assert ev.value == 0.0

    def test_negative_value(self) -> None:
        ev = ResidualEvaluation(spec=_make_spec(), value=-500.0)
        assert ev.value == -500.0

    def test_scaled_value_property(self) -> None:
        spec = ResidualSpec(name="e", unit="J/kg", scale=2000.0)
        ev = ResidualEvaluation(spec=spec, value=400.0)
        assert ev.scaled_value == pytest.approx(0.2)

    def test_frozen(self) -> None:
        ev = ResidualEvaluation(spec=_make_spec(), value=1.0)
        with pytest.raises((AttributeError, TypeError)):
            ev.value = 2.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 8. Invalid residual value
# ---------------------------------------------------------------------------


class TestResidualEvaluationInvalidValue:
    def test_invalid_spec_type(self) -> None:
        with pytest.raises(TypeError, match="ResidualSpec"):
            ResidualEvaluation(spec=None, value=1.0)  # type: ignore[arg-type]

    def test_nan(self) -> None:
        with pytest.raises(ValueError, match="value"):
            ResidualEvaluation(spec=_make_spec(), value=float("nan"))

    def test_inf(self) -> None:
        with pytest.raises(ValueError, match="value"):
            ResidualEvaluation(spec=_make_spec(), value=float("inf"))

    def test_neg_inf(self) -> None:
        with pytest.raises(ValueError, match="value"):
            ResidualEvaluation(spec=_make_spec(), value=float("-inf"))

    def test_bool_true(self) -> None:
        with pytest.raises(ValueError, match="value"):
            ResidualEvaluation(spec=_make_spec(), value=True)  # type: ignore[arg-type]

    def test_bool_false(self) -> None:
        with pytest.raises(ValueError, match="value"):
            ResidualEvaluation(spec=_make_spec(), value=False)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 9. ResidualVector preserves insertion order
# ---------------------------------------------------------------------------


class TestResidualVectorOrder:
    def test_two_element_order(self) -> None:
        ev_a = _make_eval(name="alpha", value=10.0, scale=100.0)
        ev_b = _make_eval(name="beta", value=20.0, scale=100.0)
        vec = ResidualVector(evaluations=(ev_a, ev_b))
        assert vec.evaluations[0].spec.name == "alpha"
        assert vec.evaluations[1].spec.name == "beta"

    def test_three_element_order(self) -> None:
        ev1 = _make_eval(name="first", value=1.0, scale=10.0)
        ev2 = _make_eval(name="second", value=2.0, scale=10.0)
        ev3 = _make_eval(name="third", value=3.0, scale=10.0)
        vec = ResidualVector(evaluations=(ev1, ev2, ev3))
        names = [ev.spec.name for ev in vec.evaluations]
        assert names == ["first", "second", "third"]

    def test_scaled_values_order_matches(self) -> None:
        ev_a = _make_eval(name="a", value=300.0, scale=1000.0)
        ev_b = _make_eval(name="b", value=50.0, scale=100.0)
        vec = ResidualVector(evaluations=(ev_a, ev_b))
        svs = vec.scaled_values()
        assert svs[0] == pytest.approx(0.3)
        assert svs[1] == pytest.approx(0.5)

    def test_list_input_converted_to_tuple(self) -> None:
        ev1 = _make_eval(name="x1", value=1.0)
        ev2 = _make_eval(name="x2", value=2.0)
        vec = ResidualVector(evaluations=[ev1, ev2])  # type: ignore[arg-type]
        assert isinstance(vec.evaluations, tuple)
        assert vec.evaluations[0].spec.name == "x1"


# ---------------------------------------------------------------------------
# 10. Duplicate residual names rejected
# ---------------------------------------------------------------------------


class TestResidualVectorDuplicateNames:
    def test_two_same_names(self) -> None:
        ev1 = _make_eval(name="energy", value=10.0)
        ev2 = _make_eval(name="energy", value=-5.0)
        with pytest.raises(ValueError, match="duplicate"):
            ResidualVector(evaluations=(ev1, ev2))

    def test_three_with_one_duplicate(self) -> None:
        ev_a = _make_eval(name="a", value=1.0)
        ev_b = _make_eval(name="b", value=2.0)
        ev_a2 = _make_eval(name="a", value=3.0)
        with pytest.raises(ValueError, match="duplicate"):
            ResidualVector(evaluations=(ev_a, ev_b, ev_a2))

    def test_case_sensitive_names_are_distinct(self) -> None:
        ev_lower = _make_eval(name="energy", value=1.0)
        ev_upper = _make_eval(name="Energy", value=2.0)
        vec = ResidualVector(evaluations=(ev_lower, ev_upper))
        assert len(vec.evaluations) == 2


# ---------------------------------------------------------------------------
# 11. Empty residual vector rejected
# ---------------------------------------------------------------------------


class TestResidualVectorEmpty:
    def test_empty_tuple(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ResidualVector(evaluations=())

    def test_empty_list(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ResidualVector(evaluations=[])  # type: ignore[arg-type]

    def test_invalid_evaluation_type(self) -> None:
        with pytest.raises(TypeError, match="ResidualEvaluation"):
            ResidualVector(evaluations=(None,))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 12. Scaled residual values are value / scale
# ---------------------------------------------------------------------------


class TestResidualVectorScaledValues:
    def test_single_element_exact(self) -> None:
        spec = ResidualSpec(name="e", unit="J/kg", scale=500.0)
        ev = ResidualEvaluation(spec=spec, value=250.0)
        vec = ResidualVector(evaluations=(ev,))
        assert vec.scaled_values() == pytest.approx((0.5,))

    def test_two_elements_exact(self) -> None:
        spec_e = ResidualSpec(name="energy", unit="J/kg", scale=1000.0)
        spec_p = ResidualSpec(name="pressure", unit="Pa", scale=100.0)
        ev_e = ResidualEvaluation(spec=spec_e, value=300.0)
        ev_p = ResidualEvaluation(spec=spec_p, value=-40.0)
        vec = ResidualVector(evaluations=(ev_e, ev_p))
        svs = vec.scaled_values()
        assert svs[0] == pytest.approx(0.3)
        assert svs[1] == pytest.approx(-0.4)

    def test_zero_value_gives_zero_scaled(self) -> None:
        ev = ResidualEvaluation(spec=_make_spec(scale=1000.0), value=0.0)
        vec = ResidualVector(evaluations=(ev,))
        assert vec.scaled_values() == (0.0,)

    def test_scaled_value_property_consistent_with_vector(self) -> None:
        spec = ResidualSpec(name="e", unit="J/kg", scale=2000.0)
        ev = ResidualEvaluation(spec=spec, value=1000.0)
        vec = ResidualVector(evaluations=(ev,))
        assert ev.scaled_value == pytest.approx(vec.scaled_values()[0])


# ---------------------------------------------------------------------------
# 13. max_abs_scaled norm
# ---------------------------------------------------------------------------


class TestResidualVectorMaxAbsScaled:
    def test_single_positive(self) -> None:
        ev = _make_eval(value=300.0, scale=1000.0)
        vec = ResidualVector(evaluations=(ev,))
        assert vec.max_abs_scaled() == pytest.approx(0.3)

    def test_single_negative(self) -> None:
        ev = _make_eval(value=-600.0, scale=1000.0)
        vec = ResidualVector(evaluations=(ev,))
        assert vec.max_abs_scaled() == pytest.approx(0.6)

    def test_two_elements_picks_larger(self) -> None:
        ev1 = _make_eval(name="a", value=-800.0, scale=1000.0)
        ev2 = _make_eval(name="b", value=300.0, scale=1000.0)
        vec = ResidualVector(evaluations=(ev1, ev2))
        assert vec.max_abs_scaled() == pytest.approx(0.8)

    def test_all_zero_gives_zero(self) -> None:
        ev = _make_eval(value=0.0, scale=1000.0)
        vec = ResidualVector(evaluations=(ev,))
        assert vec.max_abs_scaled() == 0.0


# ---------------------------------------------------------------------------
# 14. l2_scaled norm
# ---------------------------------------------------------------------------


class TestResidualVectorL2Scaled:
    def test_single_element(self) -> None:
        ev = _make_eval(value=300.0, scale=1000.0)
        vec = ResidualVector(evaluations=(ev,))
        assert vec.l2_scaled() == pytest.approx(0.3)

    def test_3_4_5_triangle(self) -> None:
        spec_a = ResidualSpec(name="a", unit="J/kg", scale=1000.0)
        spec_b = ResidualSpec(name="b", unit="Pa", scale=100.0)
        ev_a = ResidualEvaluation(spec=spec_a, value=300.0)  # scaled: 0.3
        ev_b = ResidualEvaluation(spec=spec_b, value=40.0)  # scaled: 0.4
        vec = ResidualVector(evaluations=(ev_a, ev_b))
        assert vec.l2_scaled() == pytest.approx(0.5)

    def test_zero_residual_vector(self) -> None:
        ev = _make_eval(value=0.0, scale=1000.0)
        vec = ResidualVector(evaluations=(ev,))
        assert vec.l2_scaled() == 0.0

    def test_l2_always_geq_max_abs_single(self) -> None:
        ev = _make_eval(value=123.0, scale=1000.0)
        vec = ResidualVector(evaluations=(ev,))
        assert vec.l2_scaled() >= vec.max_abs_scaled() - 1e-12

    def test_l2_geq_max_abs_two_elements(self) -> None:
        ev1 = _make_eval(name="a", value=300.0, scale=1000.0)
        ev2 = _make_eval(name="b", value=400.0, scale=1000.0)
        vec = ResidualVector(evaluations=(ev1, ev2))
        assert vec.l2_scaled() >= vec.max_abs_scaled()


# ---------------------------------------------------------------------------
# 15. Convergence check true/false around tolerance
# ---------------------------------------------------------------------------


class TestResidualVectorConvergence:
    def test_converged_when_exactly_at_tolerance(self) -> None:
        ev = _make_eval(value=100.0, scale=1000.0)  # scaled = 0.1
        vec = ResidualVector(evaluations=(ev,))
        assert vec.is_converged(tolerance=0.1) is True

    def test_converged_when_below_tolerance(self) -> None:
        ev = _make_eval(value=50.0, scale=1000.0)  # scaled = 0.05
        vec = ResidualVector(evaluations=(ev,))
        assert vec.is_converged(tolerance=0.1) is True

    def test_not_converged_when_above_tolerance(self) -> None:
        ev = _make_eval(value=200.0, scale=1000.0)  # scaled = 0.2
        vec = ResidualVector(evaluations=(ev,))
        assert vec.is_converged(tolerance=0.1) is False

    def test_negative_residual_uses_abs(self) -> None:
        ev = _make_eval(value=-200.0, scale=1000.0)  # |scaled| = 0.2
        vec = ResidualVector(evaluations=(ev,))
        assert vec.is_converged(tolerance=0.1) is False
        assert vec.is_converged(tolerance=0.3) is True

    def test_two_residuals_both_must_converge(self) -> None:
        ev1 = _make_eval(name="a", value=50.0, scale=1000.0)  # 0.05
        ev2 = _make_eval(name="b", value=150.0, scale=1000.0)  # 0.15
        vec = ResidualVector(evaluations=(ev1, ev2))
        assert vec.is_converged(tolerance=0.1) is False
        assert vec.is_converged(tolerance=0.2) is True

    def test_zero_residual_always_converged(self) -> None:
        ev = _make_eval(value=0.0, scale=1000.0)
        vec = ResidualVector(evaluations=(ev,))
        assert vec.is_converged(tolerance=1e-12) is True


# ---------------------------------------------------------------------------
# 16. Invalid convergence tolerance
# ---------------------------------------------------------------------------


class TestResidualVectorInvalidTolerance:
    def _vec(self) -> ResidualVector:
        return ResidualVector(evaluations=(_make_eval(value=1.0),))

    def test_zero_tolerance(self) -> None:
        with pytest.raises(ValueError, match="tolerance"):
            self._vec().is_converged(tolerance=0.0)

    def test_negative_tolerance(self) -> None:
        with pytest.raises(ValueError, match="tolerance"):
            self._vec().is_converged(tolerance=-1e-6)

    def test_nan_tolerance(self) -> None:
        with pytest.raises(ValueError, match="tolerance"):
            self._vec().is_converged(tolerance=float("nan"))

    def test_inf_tolerance(self) -> None:
        with pytest.raises(ValueError, match="tolerance"):
            self._vec().is_converged(tolerance=float("inf"))

    def test_bool_true_tolerance(self) -> None:
        with pytest.raises(ValueError, match="tolerance"):
            self._vec().is_converged(tolerance=True)  # type: ignore[arg-type]

    def test_bool_false_tolerance(self) -> None:
        with pytest.raises(ValueError, match="tolerance"):
            self._vec().is_converged(tolerance=False)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 17. Energy residual representation example
# ---------------------------------------------------------------------------


class TestEnergyResidualExample:
    """Demonstrates how h_return - h_reference is represented (Phase 13A context)."""

    H_REF = 250_000.0  # J/kg  — reference enthalpy
    H_RETURN = 250_050.0  # J/kg  — enthalpy at loop return after a solve step
    SCALE = 1_000.0  # J/kg  — characteristic enthalpy scale

    def test_energy_residual_spec(self) -> None:
        spec = ResidualSpec(name="energy", unit="J/kg", scale=self.SCALE)
        assert spec.name == "energy"
        assert spec.unit == "J/kg"
        assert spec.scale == self.SCALE

    def test_energy_residual_evaluation(self) -> None:
        spec = ResidualSpec(name="energy", unit="J/kg", scale=self.SCALE)
        ev = ResidualEvaluation(spec=spec, value=self.H_RETURN - self.H_REF)
        assert ev.value == pytest.approx(50.0)
        assert ev.scaled_value == pytest.approx(0.05)

    def test_energy_residual_in_vector(self) -> None:
        spec = ResidualSpec(name="energy", unit="J/kg", scale=self.SCALE)
        ev = ResidualEvaluation(spec=spec, value=self.H_RETURN - self.H_REF)
        vec = ResidualVector(evaluations=(ev,))
        assert vec.max_abs_scaled() == pytest.approx(0.05)
        assert not vec.is_converged(tolerance=0.01)
        assert vec.is_converged(tolerance=0.1)

    def test_energy_unknown_spec(self) -> None:
        u = UnknownSpec(name="Q_cond", unit="W", lower=-10_000.0, upper=0.0)
        assert u.name == "Q_cond"
        assert u.lower == -10_000.0
        assert u.upper == 0.0


# ---------------------------------------------------------------------------
# 18. Pressure residual representation example
# ---------------------------------------------------------------------------


class TestPressureResidualExample:
    """Demonstrates how pump_head - dP_total is represented (Phase 13B context)."""

    PUMP_HEAD = 5_000.0  # Pa
    DP_TOTAL = 4_800.0  # Pa
    SCALE = 100.0  # Pa  — characteristic pressure scale

    def test_pressure_residual_spec(self) -> None:
        spec = ResidualSpec(name="pressure", unit="Pa", scale=self.SCALE)
        assert spec.name == "pressure"
        assert spec.unit == "Pa"

    def test_pressure_residual_evaluation(self) -> None:
        spec = ResidualSpec(name="pressure", unit="Pa", scale=self.SCALE)
        raw = self.PUMP_HEAD - self.DP_TOTAL  # 200 Pa
        ev = ResidualEvaluation(spec=spec, value=raw)
        assert ev.value == pytest.approx(200.0)
        assert ev.scaled_value == pytest.approx(2.0)

    def test_pressure_residual_in_vector(self) -> None:
        spec = ResidualSpec(name="pressure", unit="Pa", scale=self.SCALE)
        ev = ResidualEvaluation(spec=spec, value=self.PUMP_HEAD - self.DP_TOTAL)
        vec = ResidualVector(evaluations=(ev,))
        assert vec.max_abs_scaled() == pytest.approx(2.0)
        assert not vec.is_converged(tolerance=1.0)
        assert vec.is_converged(tolerance=3.0)

    def test_pressure_unknown_spec(self) -> None:
        u = UnknownSpec(name="primary_mdot", unit="kg/s", lower=0.001, upper=1.0)
        assert u.lower == 0.001
        assert u.upper == 1.0


# ---------------------------------------------------------------------------
# 19. Combined energy+pressure residual vector
# ---------------------------------------------------------------------------


class TestCombinedResidualVector:
    """Demonstrates multi-residual representation without coupled solving."""

    def _make_combined(
        self,
        energy_value: float = 50.0,
        pressure_value: float = 200.0,
    ) -> ResidualVector:
        energy_spec = ResidualSpec(name="energy", unit="J/kg", scale=1000.0)
        pressure_spec = ResidualSpec(name="pressure", unit="Pa", scale=100.0)
        ev_energy = ResidualEvaluation(spec=energy_spec, value=energy_value)
        ev_pressure = ResidualEvaluation(spec=pressure_spec, value=pressure_value)
        return ResidualVector(evaluations=(ev_energy, ev_pressure))

    def test_two_residual_names_preserved(self) -> None:
        vec = self._make_combined()
        assert vec.evaluations[0].spec.name == "energy"
        assert vec.evaluations[1].spec.name == "pressure"

    def test_scaled_values_correct(self) -> None:
        vec = self._make_combined(energy_value=50.0, pressure_value=200.0)
        svs = vec.scaled_values()
        assert svs[0] == pytest.approx(0.05)  # 50/1000
        assert svs[1] == pytest.approx(2.0)  # 200/100

    def test_max_abs_scaled_dominated_by_pressure(self) -> None:
        vec = self._make_combined(energy_value=50.0, pressure_value=200.0)
        # |scaled_energy| = 0.05, |scaled_pressure| = 2.0
        assert vec.max_abs_scaled() == pytest.approx(2.0)

    def test_l2_scaled_correct(self) -> None:
        vec = self._make_combined(energy_value=300.0, pressure_value=400.0)
        # scaled_e = 0.3, scaled_p = 4.0; l2 = sqrt(0.09 + 16.0) = sqrt(16.09)
        expected = math.sqrt(0.3**2 + 4.0**2)
        assert vec.l2_scaled() == pytest.approx(expected)

    def test_not_converged_if_any_residual_large(self) -> None:
        vec = self._make_combined(energy_value=1.0, pressure_value=200.0)
        assert not vec.is_converged(tolerance=0.1)

    def test_converged_when_all_small(self) -> None:
        vec = self._make_combined(energy_value=0.001, pressure_value=0.001)
        assert vec.is_converged(tolerance=1e-4)

    def test_no_coupled_solver_invoked(self) -> None:
        # This test documents that constructing a ResidualVector does not
        # invoke any solver or modify any external state.  The vector is
        # purely a value object.
        vec = self._make_combined()
        assert vec is not None
        assert isinstance(vec.evaluations, tuple)


# ---------------------------------------------------------------------------
# 20. No solver or network API introduced by Phase 13C
# ---------------------------------------------------------------------------


class TestNoSolverOrNetworkAPI:
    """Phase 13C residuals.py must not introduce generic solver or network types."""

    RESIDUALS_MODULE = REPO_ROOT / "src" / "mpl_sim" / "closed_loop" / "residuals.py"

    def test_no_network_import(self) -> None:
        text = self.RESIDUALS_MODULE.read_text(encoding="utf-8")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert (
                    "network" not in node.module
                ), f"residuals.py must not import from network; found {node.module!r}"
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert "network" not in alias.name

    def test_no_solver_import(self) -> None:
        text = self.RESIDUALS_MODULE.read_text(encoding="utf-8")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert (
                    "solvers" not in node.module
                ), f"residuals.py must not import from solvers; found {node.module!r}"

    def test_no_coolprop_import(self) -> None:
        text = self.RESIDUALS_MODULE.read_text(encoding="utf-8")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert (
                    "CoolProp" not in node.module
                ), f"residuals.py must not import from CoolProp; found {node.module!r}"
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert "CoolProp" not in alias.name

    def test_no_solve_network_callable(self) -> None:
        from mpl_sim.closed_loop import residuals

        assert not hasattr(
            residuals, "solve"
        ), "residuals module must not expose a top-level solve() function"

    def test_no_network_class(self) -> None:
        from mpl_sim.closed_loop import residuals

        for name in ("Network", "Node", "Branch", "Junction"):
            assert not hasattr(residuals, name), f"residuals module must not define {name!r}"


# ---------------------------------------------------------------------------
# 21. Public exports from mpl_sim.closed_loop
# ---------------------------------------------------------------------------


class TestPublicExports:
    EXPECTED_13C_EXPORTS = {
        "UnknownSpec",
        "ResidualSpec",
        "ResidualEvaluation",
        "ResidualVector",
    }

    def test_all_13c_exports_in_init_all(self) -> None:
        from mpl_sim import closed_loop

        missing = self.EXPECTED_13C_EXPORTS - set(closed_loop.__all__)
        assert not missing, f"Missing from __all__: {missing}"

    def test_all_13c_exports_importable(self) -> None:
        from mpl_sim.closed_loop import (  # noqa: F401
            ResidualEvaluation,
            ResidualSpec,
            ResidualVector,
            UnknownSpec,
        )

    def test_unknown_spec_is_from_residuals(self) -> None:
        from mpl_sim.closed_loop import UnknownSpec as US
        from mpl_sim.closed_loop.residuals import UnknownSpec as USr

        assert US is USr

    def test_residual_spec_is_from_residuals(self) -> None:
        from mpl_sim.closed_loop import ResidualSpec as RS
        from mpl_sim.closed_loop.residuals import ResidualSpec as RSr

        assert RS is RSr

    def test_residual_evaluation_is_from_residuals(self) -> None:
        from mpl_sim.closed_loop import ResidualEvaluation as RE
        from mpl_sim.closed_loop.residuals import ResidualEvaluation as REr

        assert RE is REr

    def test_residual_vector_is_from_residuals(self) -> None:
        from mpl_sim.closed_loop import ResidualVector as RV
        from mpl_sim.closed_loop.residuals import ResidualVector as RVr

        assert RV is RVr

    def test_phase_13a_exports_still_present(self) -> None:
        from mpl_sim import closed_loop

        for name in (
            "ClosedLoopSolveConfig",
            "MinimalClosedMPLCase",
            "MinimalClosedMPLResult",
            "solve_minimal_closed_mpl",
        ):
            assert name in closed_loop.__all__, f"{name!r} missing from __all__"

    def test_phase_13b_exports_still_present(self) -> None:
        from mpl_sim import closed_loop

        for name in (
            "PumpHeadCurve",
            "PressureClosureConfig",
            "MinimalPressureClosureCase",
            "MinimalPressureClosureResult",
            "solve_minimal_pressure_closure",
        ):
            assert name in closed_loop.__all__, f"{name!r} missing from __all__"


# ---------------------------------------------------------------------------
# 22. Phase 13A/13B regression: existing solvers are unaffected
# ---------------------------------------------------------------------------


class TestPhase13ABRegression:
    """Verify that Phase 13C changes do not break Phase 13A or 13B public API.

    Full solver correctness is verified by the dedicated test files:
      tests/closed_loop/test_minimal_closed_mpl_solver.py  (Phase 13A)
      tests/closed_loop/test_minimal_pressure_closure.py   (Phase 13B)
    These tests verify that Phase 13C additions leave those APIs intact.
    """

    def test_phase_13a_solver_callable(self) -> None:
        from mpl_sim.closed_loop import (  # noqa: F401
            ClosedLoopSolveConfig,
            MinimalClosedMPLCase,
            MinimalClosedMPLResult,
            solve_minimal_closed_mpl,
        )

        assert callable(solve_minimal_closed_mpl)

    def test_phase_13a_config_constructible(self) -> None:
        from mpl_sim.closed_loop import ClosedLoopSolveConfig

        cfg = ClosedLoopSolveConfig(max_iter=50, tolerance=1e-6)
        assert cfg.max_iter == 50
        assert cfg.tolerance == 1e-6

    def test_phase_13a_config_invalid_rejected(self) -> None:
        from mpl_sim.closed_loop import ClosedLoopSolveConfig

        with pytest.raises(ValueError):
            ClosedLoopSolveConfig(max_iter=0)

    def test_phase_13b_solver_callable(self) -> None:
        from mpl_sim.closed_loop import (  # noqa: F401
            MinimalPressureClosureCase,
            MinimalPressureClosureResult,
            PressureClosureConfig,
            PumpHeadCurve,
            solve_minimal_pressure_closure,
        )

        assert callable(solve_minimal_pressure_closure)

    def test_phase_13b_pump_head_curve_constructible(self) -> None:
        from mpl_sim.closed_loop import PumpHeadCurve

        pump = PumpHeadCurve(head_Pa=5000.0)
        assert pump.head_Pa == 5000.0

    def test_phase_13b_config_constructible(self) -> None:
        from mpl_sim.closed_loop import PressureClosureConfig

        cfg = PressureClosureConfig(max_iter=60, tolerance=0.01)
        assert cfg.max_iter == 60
        assert cfg.tolerance == 0.01

    def test_phase_13b_config_invalid_rejected(self) -> None:
        from mpl_sim.closed_loop import PressureClosureConfig

        with pytest.raises(ValueError):
            PressureClosureConfig(tolerance=0.0)

    def test_residual_framework_coexists_with_13ab_exports(self) -> None:
        from mpl_sim import closed_loop

        all_names = set(closed_loop.__all__)
        # Phase 13C additions
        assert "UnknownSpec" in all_names
        assert "ResidualSpec" in all_names
        assert "ResidualEvaluation" in all_names
        assert "ResidualVector" in all_names
        # Phase 13A/13B still present
        assert "solve_minimal_closed_mpl" in all_names
        assert "solve_minimal_pressure_closure" in all_names
