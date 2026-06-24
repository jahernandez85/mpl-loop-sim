"""Block 15D-A — Hydraulic Closure Primitive tests.

Coverage for:
  - ImposedMassFlowClosure
  - ImposedBranchSplitClosure
  - ImposedPressureClosure
  - LinearPressureDropClosure
  - QuadraticPressureDropClosure
  - PressureCompatibilityClosure
  - HydraulicClosureResidualSet
  - build_hydraulic_closure_residuals

No production component physics are executed.  No SystemState is assembled.
No FluidState is created.  No CoolProp, no PropertyBackend, no correlations,
no HX models.  All closures are explicit, algebraic, and immutable.
"""

from __future__ import annotations

import math
from types import MappingProxyType

import pytest

from mpl_sim.network.hydraulic_closures import (
    HydraulicClosureKind,
    HydraulicClosureResidualSet,
    ImposedBranchSplitClosure,
    ImposedMassFlowClosure,
    ImposedPressureClosure,
    LinearPressureDropClosure,
    PressureCompatibilityClosure,
    QuadraticPressureDropClosure,
    build_hydraulic_closure_residuals,
)

# ===========================================================================
# ImposedMassFlowClosure tests
# ===========================================================================


class TestImposedMassFlowClosure:
    def test_builds(self):
        c = ImposedMassFlowClosure(
            unknown_name="mdot_pump",
            imposed_value=1.5,
            residual_name="closure:total_flow",
        )
        assert c.unknown_name == "mdot_pump"
        assert c.imposed_value == 1.5
        assert c.residual_name == "closure:total_flow"

    def test_kind(self):
        c = ImposedMassFlowClosure("mdot_pump", 1.0, "r")
        assert c.kind is HydraulicClosureKind.IMPOSED_MASS_FLOW

    def test_is_frozen(self):
        c = ImposedMassFlowClosure("mdot_pump", 1.0, "r")
        with pytest.raises((AttributeError, TypeError)):
            c.imposed_value = 2.0  # type: ignore[misc]

    def test_imposed_value_stored_as_float(self):
        c = ImposedMassFlowClosure("mdot_pump", 2, "r")
        assert isinstance(c.imposed_value, float)
        assert c.imposed_value == 2.0

    # Residual evaluation ---------------------------------------------------

    def test_evaluate_zero_at_imposed_value(self):
        c = ImposedMassFlowClosure("mdot", 1.5, "r")
        assert c.evaluate({"mdot": 1.5}) == pytest.approx(0.0)

    def test_evaluate_positive_when_above_imposed(self):
        c = ImposedMassFlowClosure("mdot", 1.0, "r")
        r = c.evaluate({"mdot": 2.0})
        assert r == pytest.approx(1.0)

    def test_evaluate_negative_when_below_imposed(self):
        c = ImposedMassFlowClosure("mdot", 1.0, "r")
        r = c.evaluate({"mdot": 0.5})
        assert r == pytest.approx(-0.5)

    def test_evaluate_ignores_extra_unknowns(self):
        c = ImposedMassFlowClosure("mdot_pump", 1.0, "r")
        r = c.evaluate({"mdot_pump": 1.0, "some_other": 99.0})
        assert r == pytest.approx(0.0)

    def test_evaluate_negative_imposed_value(self):
        c = ImposedMassFlowClosure("mdot", -0.5, "r")
        assert c.evaluate({"mdot": -0.5}) == pytest.approx(0.0)
        assert c.evaluate({"mdot": 0.0}) == pytest.approx(0.5)

    def test_evaluate_raises_for_missing_unknown(self):
        c = ImposedMassFlowClosure("mdot_pump", 1.0, "r")
        with pytest.raises(KeyError):
            c.evaluate({"mdot_other": 1.0})

    def test_evaluate_raises_for_bool_unknown(self):
        c = ImposedMassFlowClosure("mdot", 1.0, "r")
        with pytest.raises(TypeError):
            c.evaluate({"mdot": True})

    def test_evaluate_raises_for_nan_unknown(self):
        c = ImposedMassFlowClosure("mdot", 1.0, "r")
        with pytest.raises(ValueError):
            c.evaluate({"mdot": float("nan")})

    def test_evaluate_raises_for_inf_unknown(self):
        c = ImposedMassFlowClosure("mdot", 1.0, "r")
        with pytest.raises(ValueError):
            c.evaluate({"mdot": float("inf")})

    # Constructor validation ------------------------------------------------

    def test_rejects_bool_imposed_value(self):
        with pytest.raises(TypeError):
            ImposedMassFlowClosure("mdot", True, "r")

    def test_rejects_nan_imposed_value(self):
        with pytest.raises(ValueError):
            ImposedMassFlowClosure("mdot", float("nan"), "r")

    def test_rejects_inf_imposed_value(self):
        with pytest.raises(ValueError):
            ImposedMassFlowClosure("mdot", float("inf"), "r")

    def test_rejects_non_numeric_imposed_value(self):
        with pytest.raises(TypeError):
            ImposedMassFlowClosure("mdot", "1.0", "r")  # type: ignore[arg-type]

    def test_rejects_blank_unknown_name(self):
        with pytest.raises(ValueError):
            ImposedMassFlowClosure("  ", 1.0, "r")

    def test_rejects_blank_residual_name(self):
        with pytest.raises(ValueError):
            ImposedMassFlowClosure("mdot", 1.0, "  ")

    def test_rejects_non_str_unknown_name(self):
        with pytest.raises(TypeError):
            ImposedMassFlowClosure(123, 1.0, "r")  # type: ignore[arg-type]


# ===========================================================================
# ImposedBranchSplitClosure tests
# ===========================================================================


class TestImposedBranchSplitClosure:
    def test_builds(self):
        c = ImposedBranchSplitClosure(
            total_flow_name="mdot_pump",
            branch_flow_name="mdot_branch_a",
            split_fraction=0.4,
            residual_name="closure:split",
        )
        assert c.total_flow_name == "mdot_pump"
        assert c.branch_flow_name == "mdot_branch_a"
        assert c.split_fraction == pytest.approx(0.4)
        assert c.residual_name == "closure:split"

    def test_kind(self):
        c = ImposedBranchSplitClosure("tot", "br", 0.5, "r")
        assert c.kind is HydraulicClosureKind.IMPOSED_BRANCH_SPLIT

    def test_is_frozen(self):
        c = ImposedBranchSplitClosure("tot", "br", 0.5, "r")
        with pytest.raises((AttributeError, TypeError)):
            c.split_fraction = 0.6  # type: ignore[misc]

    def test_split_fraction_stored_as_float(self):
        c = ImposedBranchSplitClosure("tot", "br", 0.3, "r")
        assert isinstance(c.split_fraction, float)
        assert c.split_fraction == pytest.approx(0.3)

    # Residual evaluation ---------------------------------------------------

    def test_evaluate_zero_at_consistent_split(self):
        c = ImposedBranchSplitClosure("mdot_pump", "mdot_branch_a", 0.4, "r")
        r = c.evaluate({"mdot_pump": 1.0, "mdot_branch_a": 0.4})
        assert r == pytest.approx(0.0)

    def test_evaluate_nonzero_when_split_wrong(self):
        c = ImposedBranchSplitClosure("mdot_pump", "mdot_branch_a", 0.4, "r")
        r = c.evaluate({"mdot_pump": 1.0, "mdot_branch_a": 0.6})
        assert r == pytest.approx(0.2)

    def test_evaluate_with_varied_total_flow(self):
        c = ImposedBranchSplitClosure("mdot_pump", "mdot_branch_a", 0.3, "r")
        r = c.evaluate({"mdot_pump": 2.0, "mdot_branch_a": 0.6})
        assert r == pytest.approx(0.0)

    def test_evaluate_raises_missing_total_unknown(self):
        c = ImposedBranchSplitClosure("mdot_pump", "mdot_branch_a", 0.4, "r")
        with pytest.raises(KeyError):
            c.evaluate({"mdot_branch_a": 0.4})

    def test_evaluate_raises_missing_branch_unknown(self):
        c = ImposedBranchSplitClosure("mdot_pump", "mdot_branch_a", 0.4, "r")
        with pytest.raises(KeyError):
            c.evaluate({"mdot_pump": 1.0})

    # Constructor validation ------------------------------------------------

    def test_rejects_split_fraction_zero(self):
        with pytest.raises(ValueError):
            ImposedBranchSplitClosure("tot", "br", 0.0, "r")

    def test_rejects_split_fraction_one(self):
        with pytest.raises(ValueError):
            ImposedBranchSplitClosure("tot", "br", 1.0, "r")

    def test_rejects_split_fraction_negative(self):
        with pytest.raises(ValueError):
            ImposedBranchSplitClosure("tot", "br", -0.1, "r")

    def test_rejects_split_fraction_above_one(self):
        with pytest.raises(ValueError):
            ImposedBranchSplitClosure("tot", "br", 1.1, "r")

    def test_rejects_bool_split_fraction(self):
        with pytest.raises(TypeError):
            ImposedBranchSplitClosure("tot", "br", True, "r")

    def test_rejects_nan_split_fraction(self):
        with pytest.raises(ValueError):
            ImposedBranchSplitClosure("tot", "br", float("nan"), "r")

    def test_rejects_blank_total_flow_name(self):
        with pytest.raises(ValueError):
            ImposedBranchSplitClosure("", "br", 0.5, "r")

    def test_rejects_blank_branch_flow_name(self):
        with pytest.raises(ValueError):
            ImposedBranchSplitClosure("tot", "  ", 0.5, "r")

    def test_accepts_small_valid_fraction(self):
        c = ImposedBranchSplitClosure("tot", "br", 0.01, "r")
        assert c.split_fraction == pytest.approx(0.01)

    def test_accepts_large_valid_fraction(self):
        c = ImposedBranchSplitClosure("tot", "br", 0.99, "r")
        assert c.split_fraction == pytest.approx(0.99)


# ===========================================================================
# ImposedPressureClosure tests
# ===========================================================================


class TestImposedPressureClosure:
    def test_builds(self):
        c = ImposedPressureClosure(
            unknown_name="P_acc_out",
            imposed_value=1_000_000.0,
            residual_name="closure:pressure_ref",
        )
        assert c.unknown_name == "P_acc_out"
        assert c.imposed_value == pytest.approx(1_000_000.0)

    def test_kind(self):
        c = ImposedPressureClosure("P", 1e6, "r")
        assert c.kind is HydraulicClosureKind.IMPOSED_PRESSURE

    def test_is_frozen(self):
        c = ImposedPressureClosure("P", 1e6, "r")
        with pytest.raises((AttributeError, TypeError)):
            c.imposed_value = 2e6  # type: ignore[misc]

    def test_evaluate_zero_at_imposed_pressure(self):
        c = ImposedPressureClosure("P_acc_out", 1_000_000.0, "r")
        assert c.evaluate({"P_acc_out": 1_000_000.0}) == pytest.approx(0.0)

    def test_evaluate_positive_when_pressure_above_imposed(self):
        c = ImposedPressureClosure("P_acc_out", 1_000_000.0, "r")
        r = c.evaluate({"P_acc_out": 1_100_000.0})
        assert r == pytest.approx(100_000.0)

    def test_evaluate_negative_when_pressure_below_imposed(self):
        c = ImposedPressureClosure("P_acc_out", 1_000_000.0, "r")
        r = c.evaluate({"P_acc_out": 900_000.0})
        assert r == pytest.approx(-100_000.0)

    def test_evaluate_raises_for_missing_unknown(self):
        c = ImposedPressureClosure("P_acc_out", 1e6, "r")
        with pytest.raises(KeyError):
            c.evaluate({"P_other": 1e6})

    def test_rejects_bool_imposed_value(self):
        with pytest.raises(TypeError):
            ImposedPressureClosure("P", True, "r")

    def test_rejects_nan_imposed_value(self):
        with pytest.raises(ValueError):
            ImposedPressureClosure("P", float("nan"), "r")

    def test_rejects_non_numeric_imposed_value(self):
        with pytest.raises(TypeError):
            ImposedPressureClosure("P", None, "r")  # type: ignore[arg-type]

    def test_imposed_value_stored_as_float(self):
        c = ImposedPressureClosure("P", 1_000_000, "r")
        assert isinstance(c.imposed_value, float)


# ===========================================================================
# LinearPressureDropClosure tests
# ===========================================================================


class TestLinearPressureDropClosure:
    def _make(self, resistance: float = 50_000.0) -> LinearPressureDropClosure:
        return LinearPressureDropClosure(
            p_in_name="P_pump_out",
            p_out_name="P_branch_a_out",
            mdot_name="mdot_branch_a",
            resistance=resistance,
            residual_name="closure:linear_drop_a",
        )

    def test_builds(self):
        c = self._make()
        assert c.p_in_name == "P_pump_out"
        assert c.p_out_name == "P_branch_a_out"
        assert c.mdot_name == "mdot_branch_a"
        assert c.resistance == pytest.approx(50_000.0)

    def test_kind(self):
        assert self._make().kind is HydraulicClosureKind.LINEAR_PRESSURE_DROP

    def test_is_frozen(self):
        c = self._make()
        with pytest.raises((AttributeError, TypeError)):
            c.resistance = 99_000.0  # type: ignore[misc]

    def test_resistance_stored_as_float(self):
        c = LinearPressureDropClosure("p_in", "p_out", "mdot", 50000, "r")
        assert isinstance(c.resistance, float)

    # Residual evaluation ---------------------------------------------------

    def test_evaluate_zero_at_consistent_point(self):
        # R=50000, mdot=0.4: dP = 20000
        # P_in = 1_100_000, P_out = 1_080_000
        c = LinearPressureDropClosure("p_in", "p_out", "mdot", 50_000.0, "r")
        r = c.evaluate({"p_in": 1_100_000.0, "p_out": 1_080_000.0, "mdot": 0.4})
        assert r == pytest.approx(0.0)

    def test_evaluate_nonzero_when_perturbed(self):
        c = LinearPressureDropClosure("p_in", "p_out", "mdot", 50_000.0, "r")
        r = c.evaluate({"p_in": 1_100_000.0, "p_out": 1_100_000.0, "mdot": 0.4})
        # r = 1100000 - 1100000 - 50000*0.4 = -20000
        assert r == pytest.approx(-20_000.0)

    def test_sign_convention_positive_drop(self):
        # Positive mdot → P_in > P_out at solution
        c = LinearPressureDropClosure("p_in", "p_out", "mdot", 100.0, "r")
        r = c.evaluate({"p_in": 200.0, "p_out": 100.0, "mdot": 1.0})
        assert r == pytest.approx(0.0)

    def test_sign_convention_zero_resistance_no_drop(self):
        # Zero resistance: P_in == P_out at solution
        c = LinearPressureDropClosure("p_in", "p_out", "mdot", 0.0, "r")
        r = c.evaluate({"p_in": 500.0, "p_out": 500.0, "mdot": 5.0})
        assert r == pytest.approx(0.0)

    def test_evaluate_raises_missing_p_in(self):
        c = self._make()
        with pytest.raises(KeyError):
            c.evaluate({"P_branch_a_out": 1e6, "mdot_branch_a": 0.4})

    def test_evaluate_raises_missing_p_out(self):
        c = self._make()
        with pytest.raises(KeyError):
            c.evaluate({"P_pump_out": 1.1e6, "mdot_branch_a": 0.4})

    def test_evaluate_raises_missing_mdot(self):
        c = self._make()
        with pytest.raises(KeyError):
            c.evaluate({"P_pump_out": 1.1e6, "P_branch_a_out": 1.08e6})

    # Constructor validation ------------------------------------------------

    def test_rejects_negative_resistance(self):
        with pytest.raises(ValueError):
            LinearPressureDropClosure("p_in", "p_out", "mdot", -1.0, "r")

    def test_rejects_nan_resistance(self):
        with pytest.raises(ValueError):
            LinearPressureDropClosure("p_in", "p_out", "mdot", float("nan"), "r")

    def test_rejects_inf_resistance(self):
        with pytest.raises(ValueError):
            LinearPressureDropClosure("p_in", "p_out", "mdot", float("inf"), "r")

    def test_rejects_bool_resistance(self):
        with pytest.raises(TypeError):
            LinearPressureDropClosure("p_in", "p_out", "mdot", True, "r")

    def test_rejects_blank_p_in_name(self):
        with pytest.raises(ValueError):
            LinearPressureDropClosure("", "p_out", "mdot", 100.0, "r")

    def test_rejects_blank_p_out_name(self):
        with pytest.raises(ValueError):
            LinearPressureDropClosure("p_in", "", "mdot", 100.0, "r")

    def test_rejects_blank_mdot_name(self):
        with pytest.raises(ValueError):
            LinearPressureDropClosure("p_in", "p_out", "", 100.0, "r")

    def test_accepts_zero_resistance(self):
        c = LinearPressureDropClosure("p_in", "p_out", "mdot", 0.0, "r")
        assert c.resistance == pytest.approx(0.0)


# ===========================================================================
# QuadraticPressureDropClosure tests
# ===========================================================================


class TestQuadraticPressureDropClosure:
    def _make(self, coefficient: float = 50_000.0) -> QuadraticPressureDropClosure:
        return QuadraticPressureDropClosure(
            p_in_name="P_in",
            p_out_name="P_out",
            mdot_name="mdot",
            coefficient=coefficient,
            residual_name="closure:quad_drop",
        )

    def test_builds(self):
        c = self._make()
        assert c.coefficient == pytest.approx(50_000.0)

    def test_kind(self):
        assert self._make().kind is HydraulicClosureKind.QUADRATIC_PRESSURE_DROP

    def test_is_frozen(self):
        c = self._make()
        with pytest.raises((AttributeError, TypeError)):
            c.coefficient = 0.0  # type: ignore[misc]

    def test_evaluate_zero_at_consistent_point(self):
        # C=100, mdot=2: dP = 100*2*2 = 400
        c = QuadraticPressureDropClosure("p_in", "p_out", "mdot", 100.0, "r")
        r = c.evaluate({"p_in": 1400.0, "p_out": 1000.0, "mdot": 2.0})
        assert r == pytest.approx(0.0)

    def test_sign_convention_forward_flow(self):
        # Positive mdot: P_in > P_out
        c = QuadraticPressureDropClosure("p_in", "p_out", "mdot", 1.0, "r")
        r = c.evaluate({"p_in": 9.0, "p_out": 0.0, "mdot": 3.0})
        assert r == pytest.approx(0.0)

    def test_sign_convention_reverse_flow_sign_preserving(self):
        # Negative mdot: mdot * |mdot| is negative → P_in - P_out should be negative
        c = QuadraticPressureDropClosure("p_in", "p_out", "mdot", 1.0, "r")
        # mdot=-3: contribution = 1.0*(-3)*3 = -9 → r = P_in - P_out - (-9) = P_in - P_out + 9
        # At solution: P_in - P_out = -9 (outlet > inlet for reverse flow)
        r = c.evaluate({"p_in": -9.0, "p_out": 0.0, "mdot": -3.0})
        assert r == pytest.approx(0.0)

    def test_evaluate_nonzero_when_perturbed(self):
        c = QuadraticPressureDropClosure("p_in", "p_out", "mdot", 100.0, "r")
        # Consistent: dP=400 at mdot=2; perturb P_out
        r = c.evaluate({"p_in": 1400.0, "p_out": 1100.0, "mdot": 2.0})
        # r = 1400 - 1100 - 400 = -100
        assert r == pytest.approx(-100.0)

    def test_rejects_negative_coefficient(self):
        with pytest.raises(ValueError):
            QuadraticPressureDropClosure("p_in", "p_out", "mdot", -1.0, "r")

    def test_rejects_bool_coefficient(self):
        with pytest.raises(TypeError):
            QuadraticPressureDropClosure("p_in", "p_out", "mdot", True, "r")

    def test_rejects_nan_coefficient(self):
        with pytest.raises(ValueError):
            QuadraticPressureDropClosure("p_in", "p_out", "mdot", float("nan"), "r")

    def test_accepts_zero_coefficient(self):
        c = QuadraticPressureDropClosure("p_in", "p_out", "mdot", 0.0, "r")
        assert c.coefficient == pytest.approx(0.0)

    def test_evaluate_raises_missing_unknown(self):
        c = self._make()
        with pytest.raises(KeyError):
            c.evaluate({"P_in": 1e6})


# ===========================================================================
# PressureCompatibilityClosure tests
# ===========================================================================


class TestPressureCompatibilityClosure:
    def _make(
        self, resistance_a: float = 50_000.0, resistance_b: float = 50_000.0
    ) -> PressureCompatibilityClosure:
        return PressureCompatibilityClosure(
            mdot_a_name="mdot_branch_a",
            mdot_b_name="mdot_branch_b",
            resistance_a=resistance_a,
            resistance_b=resistance_b,
            residual_name="closure:compatibility",
        )

    def test_builds(self):
        c = self._make(50_000.0, 25_000.0)
        assert c.mdot_a_name == "mdot_branch_a"
        assert c.mdot_b_name == "mdot_branch_b"
        assert c.resistance_a == pytest.approx(50_000.0)
        assert c.resistance_b == pytest.approx(25_000.0)

    def test_kind(self):
        assert self._make().kind is HydraulicClosureKind.PRESSURE_COMPATIBILITY

    def test_is_frozen(self):
        c = self._make()
        with pytest.raises((AttributeError, TypeError)):
            c.resistance_a = 1.0  # type: ignore[misc]

    def test_evaluate_zero_at_compatible_flows(self):
        # R_a=50000, R_b=25000 → compatible when mdot_a/mdot_b = R_b/R_a = 0.5
        # mdot_a=0.4, mdot_b=0.8 → 50000*0.4 = 25000*0.8 = 20000 ✓
        c = PressureCompatibilityClosure("mdot_a", "mdot_b", 50_000.0, 25_000.0, "r")
        r = c.evaluate({"mdot_a": 0.4, "mdot_b": 0.8})
        assert r == pytest.approx(0.0)

    def test_evaluate_nonzero_when_incompatible(self):
        c = PressureCompatibilityClosure("mdot_a", "mdot_b", 50_000.0, 25_000.0, "r")
        # Equal flows → R_a * mdot_a = 50000*0.5, R_b * mdot_b = 25000*0.5 → not equal
        r = c.evaluate({"mdot_a": 0.5, "mdot_b": 0.5})
        assert r == pytest.approx(50_000.0 * 0.5 - 25_000.0 * 0.5)
        assert r != pytest.approx(0.0)

    def test_evaluate_zero_equal_resistances_equal_flows(self):
        c = self._make(50_000.0, 50_000.0)
        r = c.evaluate({"mdot_branch_a": 0.5, "mdot_branch_b": 0.5})
        assert r == pytest.approx(0.0)

    def test_evaluate_raises_missing_mdot_a(self):
        c = self._make()
        with pytest.raises(KeyError):
            c.evaluate({"mdot_branch_b": 0.5})

    def test_evaluate_raises_missing_mdot_b(self):
        c = self._make()
        with pytest.raises(KeyError):
            c.evaluate({"mdot_branch_a": 0.5})

    def test_rejects_negative_resistance_a(self):
        with pytest.raises(ValueError):
            PressureCompatibilityClosure("ma", "mb", -1.0, 50_000.0, "r")

    def test_rejects_negative_resistance_b(self):
        with pytest.raises(ValueError):
            PressureCompatibilityClosure("ma", "mb", 50_000.0, -1.0, "r")

    def test_rejects_bool_resistance_a(self):
        with pytest.raises(TypeError):
            PressureCompatibilityClosure("ma", "mb", True, 50_000.0, "r")

    def test_rejects_nan_resistance_a(self):
        with pytest.raises(ValueError):
            PressureCompatibilityClosure("ma", "mb", float("nan"), 50_000.0, "r")

    def test_accepts_zero_resistance(self):
        c = PressureCompatibilityClosure("ma", "mb", 0.0, 0.0, "r")
        assert c.resistance_a == pytest.approx(0.0)

    def test_evaluate_zero_resistance_zero_product(self):
        c = PressureCompatibilityClosure("ma", "mb", 0.0, 0.0, "r")
        r = c.evaluate({"ma": 100.0, "mb": 200.0})
        assert r == pytest.approx(0.0)


# ===========================================================================
# HydraulicClosureKind tests
# ===========================================================================


class TestHydraulicClosureKind:
    def test_all_kinds_accessible(self):
        kinds = {
            HydraulicClosureKind.IMPOSED_MASS_FLOW,
            HydraulicClosureKind.IMPOSED_BRANCH_SPLIT,
            HydraulicClosureKind.IMPOSED_PRESSURE,
            HydraulicClosureKind.LINEAR_PRESSURE_DROP,
            HydraulicClosureKind.QUADRATIC_PRESSURE_DROP,
            HydraulicClosureKind.PRESSURE_COMPATIBILITY,
        }
        assert len(kinds) == 6

    def test_kind_string_values(self):
        assert HydraulicClosureKind.IMPOSED_MASS_FLOW == "imposed_mass_flow"
        assert HydraulicClosureKind.IMPOSED_BRANCH_SPLIT == "imposed_branch_split"
        assert HydraulicClosureKind.IMPOSED_PRESSURE == "imposed_pressure"
        assert HydraulicClosureKind.LINEAR_PRESSURE_DROP == "linear_pressure_drop"
        assert HydraulicClosureKind.QUADRATIC_PRESSURE_DROP == "quadratic_pressure_drop"
        assert HydraulicClosureKind.PRESSURE_COMPATIBILITY == "pressure_compatibility"


# ===========================================================================
# HydraulicClosureResidualSet tests
# ===========================================================================


class TestHydraulicClosureResidualSet:
    def _make_set(self) -> HydraulicClosureResidualSet:
        return build_hydraulic_closure_residuals(
            [
                ImposedMassFlowClosure("mdot_pump", 1.0, "closure:total_flow"),
                ImposedBranchSplitClosure("mdot_pump", "mdot_branch_a", 0.4, "closure:split"),
                ImposedPressureClosure("P_acc_out", 1_000_000.0, "closure:pressure_ref"),
            ]
        )

    def test_builds(self):
        s = self._make_set()
        assert len(s.closures) == 3

    def test_residual_names_deterministic(self):
        s = self._make_set()
        assert s.residual_names == (
            "closure:total_flow",
            "closure:split",
            "closure:pressure_ref",
        )

    def test_evaluate_all_returns_mappingproxy(self):
        s = self._make_set()
        unknowns = {
            "mdot_pump": 1.0,
            "mdot_branch_a": 0.4,
            "P_acc_out": 1_000_000.0,
        }
        result = s.evaluate_all(unknowns)
        assert isinstance(result, MappingProxyType)

    def test_evaluate_all_read_only(self):
        s = self._make_set()
        unknowns = {"mdot_pump": 1.0, "mdot_branch_a": 0.4, "P_acc_out": 1_000_000.0}
        result = s.evaluate_all(unknowns)
        with pytest.raises(TypeError):
            result["closure:total_flow"] = 99.0  # type: ignore[index]

    def test_evaluate_all_zero_at_consistent_point(self):
        s = self._make_set()
        unknowns = {"mdot_pump": 1.0, "mdot_branch_a": 0.4, "P_acc_out": 1_000_000.0}
        result = s.evaluate_all(unknowns)
        assert all(math.isfinite(v) for v in result.values())
        assert result["closure:total_flow"] == pytest.approx(0.0)
        assert result["closure:split"] == pytest.approx(0.0)
        assert result["closure:pressure_ref"] == pytest.approx(0.0)

    def test_evaluate_all_nonzero_at_perturbed_point(self):
        s = self._make_set()
        unknowns = {"mdot_pump": 1.5, "mdot_branch_a": 0.4, "P_acc_out": 1_000_000.0}
        result = s.evaluate_all(unknowns)
        assert result["closure:total_flow"] == pytest.approx(0.5)
        assert result["closure:split"] != pytest.approx(0.0)

    def test_evaluate_all_all_values_finite(self):
        s = self._make_set()
        unknowns = {"mdot_pump": 1.0, "mdot_branch_a": 0.4, "P_acc_out": 1_000_000.0}
        result = s.evaluate_all(unknowns)
        for v in result.values():
            assert math.isfinite(v)

    def test_evaluate_all_extra_unknowns_allowed(self):
        s = self._make_set()
        unknowns = {
            "mdot_pump": 1.0,
            "mdot_branch_a": 0.4,
            "P_acc_out": 1_000_000.0,
            "some_extra": 999.0,
        }
        result = s.evaluate_all(unknowns)
        assert result["closure:total_flow"] == pytest.approx(0.0)

    def test_metadata_stored_as_mappingproxy(self):
        s = build_hydraulic_closure_residuals(
            [ImposedMassFlowClosure("mdot", 1.0, "r")],
            metadata={"source": "test"},
        )
        assert isinstance(s.metadata, MappingProxyType)
        assert s.metadata["source"] == "test"

    def test_metadata_defensively_copied(self):
        meta = {"key": "value"}
        s = build_hydraulic_closure_residuals(
            [ImposedMassFlowClosure("mdot", 1.0, "r")],
            metadata=meta,
        )
        meta["key"] = "mutated"
        assert s.metadata["key"] == "value"

    def test_no_metadata_is_none(self):
        s = build_hydraulic_closure_residuals([ImposedMassFlowClosure("mdot", 1.0, "r")])
        assert s.metadata is None

    def test_closures_tuple_is_immutable(self):
        s = self._make_set()
        with pytest.raises((AttributeError, TypeError)):
            s.closures = ()  # type: ignore[misc]


# ===========================================================================
# build_hydraulic_closure_residuals tests
# ===========================================================================


class TestBuildHydraulicClosureResiduals:
    def test_builds_single_closure(self):
        s = build_hydraulic_closure_residuals([ImposedMassFlowClosure("mdot", 1.0, "r")])
        assert len(s.closures) == 1

    def test_builds_multiple_closures(self):
        closures = [
            ImposedMassFlowClosure("mdot_pump", 1.0, "r1"),
            ImposedPressureClosure("P_acc_out", 1e6, "r2"),
            LinearPressureDropClosure("p_in", "p_out", "mdot", 1000.0, "r3"),
        ]
        s = build_hydraulic_closure_residuals(closures)
        assert len(s.closures) == 3

    def test_rejects_empty_closures(self):
        with pytest.raises(ValueError, match="empty"):
            build_hydraulic_closure_residuals([])

    def test_rejects_duplicate_residual_names(self):
        with pytest.raises(ValueError, match="duplicate"):
            build_hydraulic_closure_residuals(
                [
                    ImposedMassFlowClosure("mdot_a", 1.0, "same_name"),
                    ImposedMassFlowClosure("mdot_b", 0.5, "same_name"),
                ]
            )

    def test_rejects_non_closure_type(self):
        with pytest.raises(TypeError):
            build_hydraulic_closure_residuals(["not_a_closure"])  # type: ignore[list-item]

    def test_preserves_insertion_order(self):
        closures = [
            ImposedMassFlowClosure("mdot_pump", 1.0, "first"),
            ImposedPressureClosure("P_acc_out", 1e6, "second"),
            ImposedBranchSplitClosure("mdot_pump", "mdot_branch_a", 0.4, "third"),
        ]
        s = build_hydraulic_closure_residuals(closures)
        assert s.residual_names == ("first", "second", "third")

    def test_all_closure_types_accepted(self):
        closures = [
            ImposedMassFlowClosure("mdot", 1.0, "r1"),
            ImposedBranchSplitClosure("mdot", "mdot_a", 0.4, "r2"),
            ImposedPressureClosure("P", 1e6, "r3"),
            LinearPressureDropClosure("p_in", "p_out", "mdot_a", 1000.0, "r4"),
            QuadraticPressureDropClosure("p_in", "p_out", "mdot_a", 500.0, "r5"),
            PressureCompatibilityClosure("mdot_a", "mdot_b", 1000.0, 2000.0, "r6"),
        ]
        s = build_hydraulic_closure_residuals(closures)
        assert len(s.closures) == 6

    def test_accepts_generator(self):
        def gen():
            yield ImposedMassFlowClosure("mdot", 1.0, "r1")
            yield ImposedPressureClosure("P", 1e6, "r2")

        s = build_hydraulic_closure_residuals(gen())
        assert len(s.closures) == 2


# ===========================================================================
# Small algebraic system closure tests (standalone square system)
# ===========================================================================


class TestSmallAlgebraicSystemClosure:
    """Prove closures can close a small algebraic mass-flow/pressure subsystem.

    Three-unknown, three-equation system:
      - mdot (total flow)
      - P_in (inlet pressure)
      - P_out (outlet pressure)

    Closures:
      1. ImposedMassFlowClosure: mdot = 2.0
      2. ImposedPressureClosure: P_in = 500_000
      3. LinearPressureDropClosure: P_in - P_out = 10_000 * mdot

    Consistent solution:
      mdot = 2.0, P_in = 500_000, P_out = 500_000 - 10_000*2 = 480_000
    """

    _UNKNOWNS_CONSISTENT = {
        "mdot": 2.0,
        "P_in": 500_000.0,
        "P_out": 480_000.0,
    }

    _UNKNOWNS_PERTURBED = {
        "mdot": 2.0,
        "P_in": 500_000.0,
        "P_out": 490_000.0,  # wrong P_out
    }

    def _make_closure_set(self) -> HydraulicClosureResidualSet:
        return build_hydraulic_closure_residuals(
            [
                ImposedMassFlowClosure("mdot", 2.0, "r_mdot"),
                ImposedPressureClosure("P_in", 500_000.0, "r_pressure"),
                LinearPressureDropClosure("P_in", "P_out", "mdot", 10_000.0, "r_drop"),
            ]
        )

    def test_all_residuals_zero_at_consistent_point(self):
        s = self._make_closure_set()
        result = s.evaluate_all(self._UNKNOWNS_CONSISTENT)
        assert result["r_mdot"] == pytest.approx(0.0)
        assert result["r_pressure"] == pytest.approx(0.0)
        assert result["r_drop"] == pytest.approx(0.0)

    def test_residuals_nonzero_at_perturbed_point(self):
        s = self._make_closure_set()
        result = s.evaluate_all(self._UNKNOWNS_PERTURBED)
        assert result["r_drop"] != pytest.approx(0.0)

    def test_system_has_three_equations(self):
        s = self._make_closure_set()
        assert len(s.closures) == 3
        assert len(s.residual_names) == 3

    def test_quadratic_closure_closes_system(self):
        # Replace linear with quadratic: dP = C * mdot * |mdot|
        # C=2500, mdot=2: dP = 2500*2*2 = 10000 → P_out = 490000
        s = build_hydraulic_closure_residuals(
            [
                ImposedMassFlowClosure("mdot", 2.0, "r_mdot"),
                ImposedPressureClosure("P_in", 500_000.0, "r_pressure"),
                QuadraticPressureDropClosure("P_in", "P_out", "mdot", 2_500.0, "r_drop"),
            ]
        )
        result = s.evaluate_all({"mdot": 2.0, "P_in": 500_000.0, "P_out": 490_000.0})
        assert result["r_mdot"] == pytest.approx(0.0)
        assert result["r_pressure"] == pytest.approx(0.0)
        assert result["r_drop"] == pytest.approx(0.0)

    def test_compatibility_closure_evaluates_at_known_split(self):
        # At the known mass-balanced split mdot_a=0.4, mdot_b=0.6,
        # the explicit linearized path drops are equal:
        # 60000*0.4 == 40000*0.6 == 24000.
        # This closure alone does not impose mdot_a + mdot_b = mdot_total.
        s = build_hydraulic_closure_residuals(
            [
                ImposedMassFlowClosure("mdot_total", 1.0, "r_total"),
                PressureCompatibilityClosure("mdot_a", "mdot_b", 60_000.0, 40_000.0, "r_compat"),
            ]
        )
        result = s.evaluate_all({"mdot_total": 1.0, "mdot_a": 0.4, "mdot_b": 0.6})
        assert result["r_total"] == pytest.approx(0.0)
        assert result["r_compat"] == pytest.approx(0.0)
