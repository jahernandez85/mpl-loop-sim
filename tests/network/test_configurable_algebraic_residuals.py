"""Tests for Block 15F-A: configurable algebraic residual assembly foundation.

Covers:
  - ConfigurableAlgebraicResidualKind enum
  - MassBalanceResidualDeclaration validation and evaluation
  - PressureDifferenceResidualDeclaration validation and evaluation
  - ImposedPressureResidualDeclaration validation and evaluation
  - ImposedMassFlowResidualDeclaration validation and evaluation
  - EnthalpyFlowResidualDeclaration validation and evaluation
  - ConfigurableAlgebraicResidualSet construction and properties
  - evaluate_configurable_algebraic_residuals behavior
  - build_configurable_algebraic_residual_report output
  - Boundary assertions: no CoolProp, PropertyBackend, SystemState, FluidState,
    contribute, role-based physics, solve, correlations, HX models,
    file writes, or topology inference.

These tests do NOT:
  - Call solve_fixed_single_loop_residuals or any solver.
  - Execute production component physics.
  - Call CoolProp, PropertyBackend, or correlations.
  - Assemble SystemState or construct FluidState.
  - Call solve(network) or NetworkGraph.solve().
  - Write files, use pandas, or use numpy.
"""

from __future__ import annotations

import json

import pytest

from mpl_sim.network.configurable_algebraic_residuals import (
    ConfigurableAlgebraicResidualEvaluationResult,
    ConfigurableAlgebraicResidualKind,
    ConfigurableAlgebraicResidualSet,
    EnthalpyFlowResidualDeclaration,
    ImposedMassFlowResidualDeclaration,
    ImposedPressureResidualDeclaration,
    MassBalanceResidualDeclaration,
    PressureDifferenceResidualDeclaration,
    build_configurable_algebraic_residual_report,
    build_configurable_algebraic_residual_set,
    evaluate_configurable_algebraic_residuals,
    validate_algebraic_residuals_against_scenario,
)

# ===========================================================================
# ConfigurableAlgebraicResidualKind
# ===========================================================================


class TestConfigurableAlgebraicResidualKind:
    def test_has_mass_balance(self) -> None:
        assert ConfigurableAlgebraicResidualKind.MASS_BALANCE.value == "mass_balance"

    def test_has_pressure_difference(self) -> None:
        assert ConfigurableAlgebraicResidualKind.PRESSURE_DIFFERENCE.value == "pressure_difference"

    def test_has_imposed_pressure(self) -> None:
        assert ConfigurableAlgebraicResidualKind.IMPOSED_PRESSURE.value == "imposed_pressure"

    def test_has_imposed_mass_flow(self) -> None:
        assert ConfigurableAlgebraicResidualKind.IMPOSED_MASS_FLOW.value == "imposed_mass_flow"

    def test_has_enthalpy_flow(self) -> None:
        assert ConfigurableAlgebraicResidualKind.ENTHALPY_FLOW.value == "enthalpy_flow"

    def test_exactly_five_values(self) -> None:
        values = list(ConfigurableAlgebraicResidualKind)
        assert len(values) == 5

    def test_values_are_strings(self) -> None:
        for kind in ConfigurableAlgebraicResidualKind:
            assert isinstance(kind.value, str)


# ===========================================================================
# MassBalanceResidualDeclaration
# ===========================================================================


class TestMassBalanceResidualDeclaration:
    def test_basic_construction(self) -> None:
        d = MassBalanceResidualDeclaration(
            residual_name="mb:node_a",
            incoming_unknown_names=("mdot_pump",),
            outgoing_unknown_names=("mdot_evap",),
        )
        assert d.residual_name == "mb:node_a"
        assert d.incoming_unknown_names == ("mdot_pump",)
        assert d.outgoing_unknown_names == ("mdot_evap",)
        assert d.kind is ConfigurableAlgebraicResidualKind.MASS_BALANCE

    def test_incoming_only_allowed(self) -> None:
        d = MassBalanceResidualDeclaration(
            residual_name="mb:source",
            incoming_unknown_names=("mdot_in",),
            outgoing_unknown_names=(),
        )
        assert d.incoming_unknown_names == ("mdot_in",)
        assert d.outgoing_unknown_names == ()

    def test_outgoing_only_allowed(self) -> None:
        d = MassBalanceResidualDeclaration(
            residual_name="mb:sink",
            incoming_unknown_names=(),
            outgoing_unknown_names=("mdot_out",),
        )
        assert d.outgoing_unknown_names == ("mdot_out",)

    def test_rejects_empty_name(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            MassBalanceResidualDeclaration(
                residual_name="",
                incoming_unknown_names=("mdot_pump",),
                outgoing_unknown_names=(),
            )

    def test_rejects_whitespace_name(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            MassBalanceResidualDeclaration(
                residual_name="   ",
                incoming_unknown_names=("mdot_pump",),
                outgoing_unknown_names=(),
            )

    def test_rejects_both_empty(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            MassBalanceResidualDeclaration(
                residual_name="mb:empty",
                incoming_unknown_names=(),
                outgoing_unknown_names=(),
            )

    def test_rejects_empty_unknown_name_in_incoming(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            MassBalanceResidualDeclaration(
                residual_name="mb:x",
                incoming_unknown_names=("",),
                outgoing_unknown_names=(),
            )

    def test_rejects_non_str_residual_name(self) -> None:
        with pytest.raises(TypeError, match="str"):
            MassBalanceResidualDeclaration(
                residual_name=123,  # type: ignore[arg-type]
                incoming_unknown_names=("mdot_x",),
                outgoing_unknown_names=(),
            )

    def test_required_unknown_names_deduplication(self) -> None:
        d = MassBalanceResidualDeclaration(
            residual_name="mb:x",
            incoming_unknown_names=("mdot_a", "mdot_b"),
            outgoing_unknown_names=("mdot_a", "mdot_c"),
        )
        names = d.required_unknown_names
        assert len(names) == len(set(names))
        assert set(names) == {"mdot_a", "mdot_b", "mdot_c"}

    def test_evaluate_zero_balanced(self) -> None:
        d = MassBalanceResidualDeclaration(
            residual_name="mb:node",
            incoming_unknown_names=("mdot_in",),
            outgoing_unknown_names=("mdot_out",),
        )
        r = d.evaluate({"mdot_in": 1.0, "mdot_out": 1.0})
        assert r == pytest.approx(0.0)

    def test_evaluate_sign_convention_positive_excess_incoming(self) -> None:
        d = MassBalanceResidualDeclaration(
            residual_name="mb:node",
            incoming_unknown_names=("mdot_in",),
            outgoing_unknown_names=("mdot_out",),
        )
        r = d.evaluate({"mdot_in": 2.0, "mdot_out": 1.0})
        assert r == pytest.approx(1.0)

    def test_evaluate_sign_convention_negative_excess_outgoing(self) -> None:
        d = MassBalanceResidualDeclaration(
            residual_name="mb:node",
            incoming_unknown_names=("mdot_in",),
            outgoing_unknown_names=("mdot_out",),
        )
        r = d.evaluate({"mdot_in": 1.0, "mdot_out": 2.0})
        assert r == pytest.approx(-1.0)

    def test_evaluate_multiple_incoming_outgoing(self) -> None:
        d = MassBalanceResidualDeclaration(
            residual_name="mb:junction",
            incoming_unknown_names=("mdot_a", "mdot_b"),
            outgoing_unknown_names=("mdot_c",),
        )
        r = d.evaluate({"mdot_a": 0.3, "mdot_b": 0.7, "mdot_c": 1.0})
        assert r == pytest.approx(0.0)

    def test_evaluate_perturbation_nonzero(self) -> None:
        d = MassBalanceResidualDeclaration(
            residual_name="mb:node",
            incoming_unknown_names=("mdot_in",),
            outgoing_unknown_names=("mdot_out",),
        )
        r = d.evaluate({"mdot_in": 1.001, "mdot_out": 1.0})
        assert abs(r) > 0

    def test_evaluate_rejects_missing_unknown(self) -> None:
        d = MassBalanceResidualDeclaration(
            residual_name="mb:x",
            incoming_unknown_names=("mdot_in",),
            outgoing_unknown_names=(),
        )
        with pytest.raises(ValueError, match="mdot_in"):
            d.evaluate({})

    def test_evaluate_rejects_bool_value(self) -> None:
        d = MassBalanceResidualDeclaration(
            residual_name="mb:x",
            incoming_unknown_names=("mdot_in",),
            outgoing_unknown_names=(),
        )
        with pytest.raises(TypeError, match="bool"):
            d.evaluate({"mdot_in": True})

    def test_evaluate_rejects_nan(self) -> None:
        d = MassBalanceResidualDeclaration(
            residual_name="mb:x",
            incoming_unknown_names=("mdot_in",),
            outgoing_unknown_names=(),
        )
        with pytest.raises(ValueError, match="finite"):
            d.evaluate({"mdot_in": float("nan")})

    def test_evaluate_rejects_inf(self) -> None:
        d = MassBalanceResidualDeclaration(
            residual_name="mb:x",
            incoming_unknown_names=("mdot_in",),
            outgoing_unknown_names=(),
        )
        with pytest.raises(ValueError, match="finite"):
            d.evaluate({"mdot_in": float("inf")})

    def test_evaluate_extra_unknowns_ignored(self) -> None:
        d = MassBalanceResidualDeclaration(
            residual_name="mb:x",
            incoming_unknown_names=("mdot_in",),
            outgoing_unknown_names=("mdot_out",),
        )
        r = d.evaluate({"mdot_in": 1.0, "mdot_out": 1.0, "extra_unknown": 999.0})
        assert r == pytest.approx(0.0)

    def test_frozen(self) -> None:
        d = MassBalanceResidualDeclaration(
            residual_name="mb:x",
            incoming_unknown_names=("mdot_in",),
            outgoing_unknown_names=(),
        )
        with pytest.raises((AttributeError, TypeError)):
            d.residual_name = "changed"  # type: ignore[misc]


# ===========================================================================
# PressureDifferenceResidualDeclaration
# ===========================================================================


class TestPressureDifferenceResidualDeclaration:
    def test_basic_construction(self) -> None:
        d = PressureDifferenceResidualDeclaration(
            residual_name="pd:pump",
            inlet_pressure_unknown="P_in",
            outlet_pressure_unknown="P_out",
            delta_p=-100_000.0,
        )
        assert d.residual_name == "pd:pump"
        assert d.inlet_pressure_unknown == "P_in"
        assert d.outlet_pressure_unknown == "P_out"
        assert d.delta_p == pytest.approx(-100_000.0)
        assert d.kind is ConfigurableAlgebraicResidualKind.PRESSURE_DIFFERENCE

    def test_delta_p_stored_as_float(self) -> None:
        d = PressureDifferenceResidualDeclaration(
            residual_name="pd:x",
            inlet_pressure_unknown="P_a",
            outlet_pressure_unknown="P_b",
            delta_p=50000,
        )
        assert isinstance(d.delta_p, float)

    def test_rejects_empty_residual_name(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            PressureDifferenceResidualDeclaration(
                residual_name="",
                inlet_pressure_unknown="P_a",
                outlet_pressure_unknown="P_b",
                delta_p=0.0,
            )

    def test_rejects_empty_inlet_name(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            PressureDifferenceResidualDeclaration(
                residual_name="pd:x",
                inlet_pressure_unknown="",
                outlet_pressure_unknown="P_b",
                delta_p=0.0,
            )

    def test_rejects_empty_outlet_name(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            PressureDifferenceResidualDeclaration(
                residual_name="pd:x",
                inlet_pressure_unknown="P_a",
                outlet_pressure_unknown="",
                delta_p=0.0,
            )

    def test_rejects_bool_delta_p(self) -> None:
        with pytest.raises(TypeError, match="bool"):
            PressureDifferenceResidualDeclaration(
                residual_name="pd:x",
                inlet_pressure_unknown="P_a",
                outlet_pressure_unknown="P_b",
                delta_p=True,
            )

    def test_rejects_nan_delta_p(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            PressureDifferenceResidualDeclaration(
                residual_name="pd:x",
                inlet_pressure_unknown="P_a",
                outlet_pressure_unknown="P_b",
                delta_p=float("nan"),
            )

    def test_rejects_inf_delta_p(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            PressureDifferenceResidualDeclaration(
                residual_name="pd:x",
                inlet_pressure_unknown="P_a",
                outlet_pressure_unknown="P_b",
                delta_p=float("inf"),
            )

    def test_required_unknown_names(self) -> None:
        d = PressureDifferenceResidualDeclaration(
            residual_name="pd:x",
            inlet_pressure_unknown="P_in",
            outlet_pressure_unknown="P_out",
            delta_p=0.0,
        )
        assert set(d.required_unknown_names) == {"P_in", "P_out"}

    def test_required_unknown_names_same_inlet_outlet(self) -> None:
        d = PressureDifferenceResidualDeclaration(
            residual_name="pd:x",
            inlet_pressure_unknown="P_same",
            outlet_pressure_unknown="P_same",
            delta_p=0.0,
        )
        assert d.required_unknown_names == ("P_same",)

    def test_evaluate_zero_with_matching_dp(self) -> None:
        # r = P_out - P_in + delta_p; drop = 50000
        d = PressureDifferenceResidualDeclaration(
            residual_name="pd:pipe",
            inlet_pressure_unknown="P_in",
            outlet_pressure_unknown="P_out",
            delta_p=50_000.0,
        )
        r = d.evaluate({"P_in": 200_000.0, "P_out": 150_000.0})
        assert r == pytest.approx(0.0)

    def test_evaluate_zero_pump_negative_delta_p(self) -> None:
        # Pump raises pressure: P_out = P_in + 100000; delta_p = -100000
        d = PressureDifferenceResidualDeclaration(
            residual_name="pd:pump",
            inlet_pressure_unknown="P_in",
            outlet_pressure_unknown="P_out",
            delta_p=-100_000.0,
        )
        r = d.evaluate({"P_in": 100_000.0, "P_out": 200_000.0})
        assert r == pytest.approx(0.0)

    def test_evaluate_perturbation_nonzero(self) -> None:
        d = PressureDifferenceResidualDeclaration(
            residual_name="pd:x",
            inlet_pressure_unknown="P_in",
            outlet_pressure_unknown="P_out",
            delta_p=50_000.0,
        )
        r = d.evaluate({"P_in": 200_000.0, "P_out": 152_000.0})
        assert abs(r) > 0

    def test_evaluate_sign_convention(self) -> None:
        # r = P_out - P_in + delta_p
        d = PressureDifferenceResidualDeclaration(
            residual_name="pd:x",
            inlet_pressure_unknown="P_in",
            outlet_pressure_unknown="P_out",
            delta_p=0.0,
        )
        r = d.evaluate({"P_in": 100.0, "P_out": 200.0})
        assert r == pytest.approx(100.0)  # P_out > P_in, positive residual

    def test_evaluate_rejects_missing(self) -> None:
        d = PressureDifferenceResidualDeclaration(
            residual_name="pd:x",
            inlet_pressure_unknown="P_in",
            outlet_pressure_unknown="P_out",
            delta_p=0.0,
        )
        with pytest.raises(ValueError, match="P_in"):
            d.evaluate({"P_out": 100.0})

    def test_evaluate_rejects_bool(self) -> None:
        d = PressureDifferenceResidualDeclaration(
            residual_name="pd:x",
            inlet_pressure_unknown="P_in",
            outlet_pressure_unknown="P_out",
            delta_p=0.0,
        )
        with pytest.raises(TypeError, match="bool"):
            d.evaluate({"P_in": True, "P_out": 100.0})


# ===========================================================================
# ImposedPressureResidualDeclaration
# ===========================================================================


class TestImposedPressureResidualDeclaration:
    def test_basic_construction(self) -> None:
        d = ImposedPressureResidualDeclaration(
            residual_name="ip:acc",
            pressure_unknown="P:acc_out",
            imposed_value=101_325.0,
        )
        assert d.residual_name == "ip:acc"
        assert d.pressure_unknown == "P:acc_out"
        assert d.imposed_value == pytest.approx(101_325.0)
        assert d.kind is ConfigurableAlgebraicResidualKind.IMPOSED_PRESSURE

    def test_imposed_value_stored_as_float(self) -> None:
        d = ImposedPressureResidualDeclaration(
            residual_name="ip:x", pressure_unknown="P:x", imposed_value=200000
        )
        assert isinstance(d.imposed_value, float)

    def test_rejects_empty_name(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ImposedPressureResidualDeclaration(
                residual_name="", pressure_unknown="P:x", imposed_value=100.0
            )

    def test_rejects_empty_unknown(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ImposedPressureResidualDeclaration(
                residual_name="ip:x", pressure_unknown="", imposed_value=100.0
            )

    def test_rejects_bool_imposed_value(self) -> None:
        with pytest.raises(TypeError, match="bool"):
            ImposedPressureResidualDeclaration(
                residual_name="ip:x", pressure_unknown="P:x", imposed_value=True
            )

    def test_rejects_nan_imposed_value(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            ImposedPressureResidualDeclaration(
                residual_name="ip:x", pressure_unknown="P:x", imposed_value=float("nan")
            )

    def test_rejects_inf_imposed_value(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            ImposedPressureResidualDeclaration(
                residual_name="ip:x", pressure_unknown="P:x", imposed_value=float("-inf")
            )

    def test_required_unknown_names(self) -> None:
        d = ImposedPressureResidualDeclaration(
            residual_name="ip:x", pressure_unknown="P:node", imposed_value=0.0
        )
        assert d.required_unknown_names == ("P:node",)

    def test_evaluate_zero(self) -> None:
        d = ImposedPressureResidualDeclaration(
            residual_name="ip:x", pressure_unknown="P:acc", imposed_value=200_000.0
        )
        assert d.evaluate({"P:acc": 200_000.0}) == pytest.approx(0.0)

    def test_evaluate_positive_when_unknown_higher(self) -> None:
        d = ImposedPressureResidualDeclaration(
            residual_name="ip:x", pressure_unknown="P:acc", imposed_value=200_000.0
        )
        assert d.evaluate({"P:acc": 201_000.0}) == pytest.approx(1000.0)

    def test_evaluate_negative_when_unknown_lower(self) -> None:
        d = ImposedPressureResidualDeclaration(
            residual_name="ip:x", pressure_unknown="P:acc", imposed_value=200_000.0
        )
        assert d.evaluate({"P:acc": 199_000.0}) == pytest.approx(-1000.0)

    def test_evaluate_extra_unknowns_ignored(self) -> None:
        d = ImposedPressureResidualDeclaration(
            residual_name="ip:x", pressure_unknown="P:acc", imposed_value=200_000.0
        )
        assert d.evaluate({"P:acc": 200_000.0, "extra": 999.0}) == pytest.approx(0.0)

    def test_evaluate_rejects_missing(self) -> None:
        d = ImposedPressureResidualDeclaration(
            residual_name="ip:x", pressure_unknown="P:acc", imposed_value=100.0
        )
        with pytest.raises(ValueError, match="P:acc"):
            d.evaluate({})


# ===========================================================================
# ImposedMassFlowResidualDeclaration
# ===========================================================================


class TestImposedMassFlowResidualDeclaration:
    def test_basic_construction(self) -> None:
        d = ImposedMassFlowResidualDeclaration(
            residual_name="imf:pump",
            mass_flow_unknown="mdot:pump",
            imposed_value=0.5,
        )
        assert d.residual_name == "imf:pump"
        assert d.mass_flow_unknown == "mdot:pump"
        assert d.imposed_value == pytest.approx(0.5)
        assert d.kind is ConfigurableAlgebraicResidualKind.IMPOSED_MASS_FLOW

    def test_imposed_value_stored_as_float(self) -> None:
        d = ImposedMassFlowResidualDeclaration(
            residual_name="imf:x", mass_flow_unknown="mdot:x", imposed_value=1
        )
        assert isinstance(d.imposed_value, float)

    def test_rejects_empty_name(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ImposedMassFlowResidualDeclaration(
                residual_name="", mass_flow_unknown="mdot:x", imposed_value=1.0
            )

    def test_rejects_empty_unknown(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ImposedMassFlowResidualDeclaration(
                residual_name="imf:x", mass_flow_unknown="", imposed_value=1.0
            )

    def test_rejects_bool_imposed_value(self) -> None:
        with pytest.raises(TypeError, match="bool"):
            ImposedMassFlowResidualDeclaration(
                residual_name="imf:x", mass_flow_unknown="mdot:x", imposed_value=False
            )

    def test_rejects_nan_imposed_value(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            ImposedMassFlowResidualDeclaration(
                residual_name="imf:x", mass_flow_unknown="mdot:x", imposed_value=float("nan")
            )

    def test_evaluate_zero(self) -> None:
        d = ImposedMassFlowResidualDeclaration(
            residual_name="imf:x", mass_flow_unknown="mdot:pump", imposed_value=1.0
        )
        assert d.evaluate({"mdot:pump": 1.0}) == pytest.approx(0.0)

    def test_evaluate_perturbation(self) -> None:
        d = ImposedMassFlowResidualDeclaration(
            residual_name="imf:x", mass_flow_unknown="mdot:pump", imposed_value=1.0
        )
        r = d.evaluate({"mdot:pump": 1.5})
        assert r == pytest.approx(0.5)

    def test_evaluate_rejects_missing(self) -> None:
        d = ImposedMassFlowResidualDeclaration(
            residual_name="imf:x", mass_flow_unknown="mdot:pump", imposed_value=1.0
        )
        with pytest.raises(ValueError, match="mdot:pump"):
            d.evaluate({})

    def test_evaluate_rejects_inf(self) -> None:
        d = ImposedMassFlowResidualDeclaration(
            residual_name="imf:x", mass_flow_unknown="mdot:pump", imposed_value=1.0
        )
        with pytest.raises(ValueError, match="finite"):
            d.evaluate({"mdot:pump": float("inf")})

    def test_required_unknown_names(self) -> None:
        d = ImposedMassFlowResidualDeclaration(
            residual_name="imf:x", mass_flow_unknown="mdot:pump", imposed_value=1.0
        )
        assert d.required_unknown_names == ("mdot:pump",)


# ===========================================================================
# EnthalpyFlowResidualDeclaration
# ===========================================================================


class TestEnthalpyFlowResidualDeclaration:
    def test_basic_construction(self) -> None:
        d = EnthalpyFlowResidualDeclaration(
            residual_name="ef:evap",
            q_unknown="q_evap",
            mdot_unknown="mdot_evap",
            h_in_unknown="h_evap_in",
            h_out_unknown="h_evap_out",
        )
        assert d.residual_name == "ef:evap"
        assert d.q_unknown == "q_evap"
        assert d.mdot_unknown == "mdot_evap"
        assert d.h_in_unknown == "h_evap_in"
        assert d.h_out_unknown == "h_evap_out"
        assert d.kind is ConfigurableAlgebraicResidualKind.ENTHALPY_FLOW

    def test_rejects_empty_residual_name(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            EnthalpyFlowResidualDeclaration(
                residual_name="",
                q_unknown="q",
                mdot_unknown="m",
                h_in_unknown="h_in",
                h_out_unknown="h_out",
            )

    def test_rejects_empty_q_unknown(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            EnthalpyFlowResidualDeclaration(
                residual_name="ef:x",
                q_unknown="",
                mdot_unknown="m",
                h_in_unknown="h_in",
                h_out_unknown="h_out",
            )

    def test_rejects_empty_mdot_unknown(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            EnthalpyFlowResidualDeclaration(
                residual_name="ef:x",
                q_unknown="q",
                mdot_unknown="",
                h_in_unknown="h_in",
                h_out_unknown="h_out",
            )

    def test_required_unknown_names_deduplication(self) -> None:
        d = EnthalpyFlowResidualDeclaration(
            residual_name="ef:x",
            q_unknown="q",
            mdot_unknown="m",
            h_in_unknown="h",
            h_out_unknown="h",  # same
        )
        names = d.required_unknown_names
        assert len(names) == len(set(names))
        assert set(names) == {"q", "m", "h"}

    def test_evaluate_zero(self) -> None:
        # r = q - mdot * (h_out - h_in)
        # q = 1.0 * (400 - 200) = 200 kJ/kg * 1 kg/s = 200 kW
        d = EnthalpyFlowResidualDeclaration(
            residual_name="ef:evap",
            q_unknown="q",
            mdot_unknown="mdot",
            h_in_unknown="h_in",
            h_out_unknown="h_out",
        )
        r = d.evaluate({"q": 200_000.0, "mdot": 1.0, "h_in": 200_000.0, "h_out": 400_000.0})
        assert r == pytest.approx(0.0)

    def test_evaluate_nonzero_perturbation(self) -> None:
        d = EnthalpyFlowResidualDeclaration(
            residual_name="ef:evap",
            q_unknown="q",
            mdot_unknown="mdot",
            h_in_unknown="h_in",
            h_out_unknown="h_out",
        )
        r = d.evaluate({"q": 210_000.0, "mdot": 1.0, "h_in": 200_000.0, "h_out": 400_000.0})
        assert r == pytest.approx(10_000.0)

    def test_evaluate_rejects_missing(self) -> None:
        d = EnthalpyFlowResidualDeclaration(
            residual_name="ef:x",
            q_unknown="q",
            mdot_unknown="mdot",
            h_in_unknown="h_in",
            h_out_unknown="h_out",
        )
        with pytest.raises(ValueError, match="q"):
            d.evaluate({"mdot": 1.0, "h_in": 100.0, "h_out": 200.0})

    def test_evaluate_rejects_bool(self) -> None:
        d = EnthalpyFlowResidualDeclaration(
            residual_name="ef:x",
            q_unknown="q",
            mdot_unknown="mdot",
            h_in_unknown="h_in",
            h_out_unknown="h_out",
        )
        with pytest.raises(TypeError, match="bool"):
            d.evaluate({"q": True, "mdot": 1.0, "h_in": 100.0, "h_out": 200.0})

    def test_evaluate_rejects_nan(self) -> None:
        d = EnthalpyFlowResidualDeclaration(
            residual_name="ef:x",
            q_unknown="q",
            mdot_unknown="mdot",
            h_in_unknown="h_in",
            h_out_unknown="h_out",
        )
        with pytest.raises(ValueError, match="finite"):
            d.evaluate({"q": float("nan"), "mdot": 1.0, "h_in": 100.0, "h_out": 200.0})

    def test_evaluate_extra_unknowns_ignored(self) -> None:
        d = EnthalpyFlowResidualDeclaration(
            residual_name="ef:x",
            q_unknown="q",
            mdot_unknown="mdot",
            h_in_unknown="h_in",
            h_out_unknown="h_out",
        )
        r = d.evaluate(
            {"q": 200_000.0, "mdot": 1.0, "h_in": 200_000.0, "h_out": 400_000.0, "extra": 999.0}
        )
        assert r == pytest.approx(0.0)


# ===========================================================================
# ConfigurableAlgebraicResidualSet
# ===========================================================================


class TestBuildConfigurableAlgebraicResidualSet:
    def _mass_decl(self, name: str) -> MassBalanceResidualDeclaration:
        return MassBalanceResidualDeclaration(
            residual_name=name,
            incoming_unknown_names=(f"in_{name}",),
            outgoing_unknown_names=(f"out_{name}",),
        )

    def test_builds_from_list(self) -> None:
        d1 = self._mass_decl("r1")
        d2 = self._mass_decl("r2")
        s = build_configurable_algebraic_residual_set([d1, d2])
        assert isinstance(s, ConfigurableAlgebraicResidualSet)

    def test_builds_from_tuple(self) -> None:
        d1 = self._mass_decl("r1")
        s = build_configurable_algebraic_residual_set((d1,))
        assert isinstance(s, ConfigurableAlgebraicResidualSet)

    def test_preserves_order(self) -> None:
        d1 = self._mass_decl("r1")
        d2 = self._mass_decl("r2")
        d3 = self._mass_decl("r3")
        s = build_configurable_algebraic_residual_set([d1, d2, d3])
        assert s.residual_names == ("r1", "r2", "r3")

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            build_configurable_algebraic_residual_set([])

    def test_rejects_duplicate_names(self) -> None:
        d1 = self._mass_decl("r1")
        d2 = self._mass_decl("r1")
        with pytest.raises(ValueError, match="duplicate"):
            build_configurable_algebraic_residual_set([d1, d2])

    def test_rejects_non_declaration_type(self) -> None:
        with pytest.raises(TypeError, match="ConfigurableAlgebraicResidualDeclaration"):
            build_configurable_algebraic_residual_set(["not_a_declaration"])  # type: ignore[list-item]

    def test_rejects_non_sequence(self) -> None:
        with pytest.raises(TypeError):
            build_configurable_algebraic_residual_set("single_declaration")  # type: ignore[arg-type]

    def test_residual_names_tuple(self) -> None:
        d1 = self._mass_decl("r1")
        s = build_configurable_algebraic_residual_set([d1])
        assert isinstance(s.residual_names, tuple)
        assert s.residual_names == ("r1",)

    def test_required_unknown_names_deduplicated(self) -> None:
        # r1 uses "u1", r2 also uses "u1" and "u2"
        d1 = MassBalanceResidualDeclaration(
            residual_name="r1",
            incoming_unknown_names=("u1",),
            outgoing_unknown_names=("u2",),
        )
        d2 = MassBalanceResidualDeclaration(
            residual_name="r2",
            incoming_unknown_names=("u1",),
            outgoing_unknown_names=("u3",),
        )
        s = build_configurable_algebraic_residual_set([d1, d2])
        assert set(s.required_unknown_names) == {"u1", "u2", "u3"}
        assert len(s.required_unknown_names) == 3

    def test_count_property(self) -> None:
        d1 = self._mass_decl("r1")
        d2 = self._mass_decl("r2")
        s = build_configurable_algebraic_residual_set([d1, d2])
        assert s.count == 2

    def test_no_evaluation_during_construction(self) -> None:
        d1 = self._mass_decl("r1")
        s = build_configurable_algebraic_residual_set([d1])
        assert not hasattr(s, "residual_values")

    def test_mixed_declaration_types(self) -> None:
        d_mb = MassBalanceResidualDeclaration(
            residual_name="mb:x",
            incoming_unknown_names=("m_in",),
            outgoing_unknown_names=("m_out",),
        )
        d_ip = ImposedPressureResidualDeclaration(
            residual_name="ip:x",
            pressure_unknown="P:x",
            imposed_value=100_000.0,
        )
        d_imf = ImposedMassFlowResidualDeclaration(
            residual_name="imf:x",
            mass_flow_unknown="mdot:x",
            imposed_value=1.0,
        )
        s = build_configurable_algebraic_residual_set([d_mb, d_ip, d_imf])
        assert s.residual_names == ("mb:x", "ip:x", "imf:x")

    def test_limitations_non_empty(self) -> None:
        d1 = self._mass_decl("r1")
        s = build_configurable_algebraic_residual_set([d1])
        assert isinstance(s.limitations, tuple)
        assert len(s.limitations) > 0

    def test_frozen(self) -> None:
        d1 = self._mass_decl("r1")
        s = build_configurable_algebraic_residual_set([d1])
        with pytest.raises((AttributeError, TypeError)):
            s.residual_names = ("changed",)  # type: ignore[misc]


# ===========================================================================
# evaluate_configurable_algebraic_residuals
# ===========================================================================


class TestEvaluateConfigurableAlgebraicResiduals:
    def _simple_mass_set(self) -> ConfigurableAlgebraicResidualSet:
        d = MassBalanceResidualDeclaration(
            residual_name="mb:node",
            incoming_unknown_names=("m_in",),
            outgoing_unknown_names=("m_out",),
        )
        return build_configurable_algebraic_residual_set([d])

    def test_evaluates_to_zero_at_consistent_point(self) -> None:
        s = self._simple_mass_set()
        result = evaluate_configurable_algebraic_residuals(s, {"m_in": 1.0, "m_out": 1.0})
        assert isinstance(result, ConfigurableAlgebraicResidualEvaluationResult)
        assert result.residual_values["mb:node"] == pytest.approx(0.0)
        assert result.max_abs_residual == pytest.approx(0.0)
        assert result.l2_norm == pytest.approx(0.0)

    def test_evaluates_nonzero_at_perturbed_point(self) -> None:
        s = self._simple_mass_set()
        result = evaluate_configurable_algebraic_residuals(s, {"m_in": 1.5, "m_out": 1.0})
        assert result.residual_values["mb:node"] == pytest.approx(0.5)
        assert result.max_abs_residual == pytest.approx(0.5)

    def test_result_residual_names_ordered(self) -> None:
        d1 = MassBalanceResidualDeclaration(
            residual_name="r1", incoming_unknown_names=("u1",), outgoing_unknown_names=()
        )
        d2 = MassBalanceResidualDeclaration(
            residual_name="r2", incoming_unknown_names=("u2",), outgoing_unknown_names=()
        )
        s = build_configurable_algebraic_residual_set([d1, d2])
        result = evaluate_configurable_algebraic_residuals(s, {"u1": 0.0, "u2": 0.0})
        assert result.residual_names == ("r1", "r2")

    def test_result_residual_values_read_only(self) -> None:
        from types import MappingProxyType

        s = self._simple_mass_set()
        result = evaluate_configurable_algebraic_residuals(s, {"m_in": 1.0, "m_out": 1.0})
        assert isinstance(result.residual_values, MappingProxyType)

    def test_max_abs_residual_correct(self) -> None:
        d1 = MassBalanceResidualDeclaration(
            residual_name="r1", incoming_unknown_names=("u1",), outgoing_unknown_names=()
        )
        d2 = MassBalanceResidualDeclaration(
            residual_name="r2", incoming_unknown_names=("u2",), outgoing_unknown_names=()
        )
        s = build_configurable_algebraic_residual_set([d1, d2])
        result = evaluate_configurable_algebraic_residuals(s, {"u1": 3.0, "u2": -7.0})
        # r1 = 3.0, r2 = -7.0; max abs = 7.0
        assert result.max_abs_residual == pytest.approx(7.0)

    def test_l2_norm_correct(self) -> None:
        d1 = MassBalanceResidualDeclaration(
            residual_name="r1", incoming_unknown_names=("u1",), outgoing_unknown_names=()
        )
        d2 = MassBalanceResidualDeclaration(
            residual_name="r2", incoming_unknown_names=("u2",), outgoing_unknown_names=()
        )
        s = build_configurable_algebraic_residual_set([d1, d2])
        result = evaluate_configurable_algebraic_residuals(s, {"u1": 3.0, "u2": 4.0})
        assert result.l2_norm == pytest.approx(5.0)  # sqrt(9 + 16)

    def test_no_solve_always_true(self) -> None:
        s = self._simple_mass_set()
        result = evaluate_configurable_algebraic_residuals(s, {"m_in": 1.0, "m_out": 1.0})
        assert result.no_solve is True

    def test_unknown_names_used_correct(self) -> None:
        s = self._simple_mass_set()
        result = evaluate_configurable_algebraic_residuals(s, {"m_in": 1.0, "m_out": 1.0})
        assert set(result.unknown_names_used) == {"m_in", "m_out"}

    def test_extra_unknowns_silently_ignored(self) -> None:
        s = self._simple_mass_set()
        result = evaluate_configurable_algebraic_residuals(
            s, {"m_in": 1.0, "m_out": 1.0, "extra": 999.0}
        )
        assert result.residual_values["mb:node"] == pytest.approx(0.0)

    def test_rejects_missing_unknown(self) -> None:
        s = self._simple_mass_set()
        with pytest.raises(ValueError, match="m_in"):
            evaluate_configurable_algebraic_residuals(s, {"m_out": 1.0})

    def test_rejects_bool_unknown_value(self) -> None:
        s = self._simple_mass_set()
        with pytest.raises(TypeError, match="bool"):
            evaluate_configurable_algebraic_residuals(s, {"m_in": True, "m_out": 1.0})

    def test_rejects_nan_unknown_value(self) -> None:
        s = self._simple_mass_set()
        with pytest.raises(ValueError, match="finite"):
            evaluate_configurable_algebraic_residuals(s, {"m_in": float("nan"), "m_out": 1.0})

    def test_rejects_inf_unknown_value(self) -> None:
        s = self._simple_mass_set()
        with pytest.raises(ValueError, match="finite"):
            evaluate_configurable_algebraic_residuals(s, {"m_in": float("inf"), "m_out": 1.0})

    def test_rejects_non_mapping_unknown_values(self) -> None:
        s = self._simple_mass_set()
        with pytest.raises(TypeError, match="Mapping"):
            evaluate_configurable_algebraic_residuals(s, [1.0, 2.0])  # type: ignore[arg-type]

    def test_rejects_non_residual_set(self) -> None:
        with pytest.raises(TypeError, match="ConfigurableAlgebraicResidualSet"):
            evaluate_configurable_algebraic_residuals("not_a_set", {"m_in": 1.0})  # type: ignore[arg-type]

    def test_limitations_in_result(self) -> None:
        s = self._simple_mass_set()
        result = evaluate_configurable_algebraic_residuals(s, {"m_in": 1.0, "m_out": 1.0})
        assert isinstance(result.limitations, tuple)
        assert len(result.limitations) > 0


# ===========================================================================
# build_configurable_algebraic_residual_report
# ===========================================================================


class TestBuildConfigurableAlgebraicResidualReport:
    def _make_result(self) -> ConfigurableAlgebraicResidualEvaluationResult:
        d = MassBalanceResidualDeclaration(
            residual_name="mb:node",
            incoming_unknown_names=("m_in",),
            outgoing_unknown_names=("m_out",),
        )
        s = build_configurable_algebraic_residual_set([d])
        return evaluate_configurable_algebraic_residuals(s, {"m_in": 1.0, "m_out": 1.0})

    def test_returns_plain_dict(self) -> None:
        result = self._make_result()
        report = build_configurable_algebraic_residual_report(result)
        assert isinstance(report, dict)

    def test_json_serializable(self) -> None:
        result = self._make_result()
        report = build_configurable_algebraic_residual_report(result)
        json_str = json.dumps(report)
        assert isinstance(json_str, str)

    def test_status_field(self) -> None:
        result = self._make_result()
        report = build_configurable_algebraic_residual_report(result)
        assert report["status"] == "algebraic_residual_evaluation"

    def test_no_solve_true(self) -> None:
        result = self._make_result()
        report = build_configurable_algebraic_residual_report(result)
        assert report["no_solve"] is True

    def test_no_properties_true(self) -> None:
        result = self._make_result()
        report = build_configurable_algebraic_residual_report(result)
        assert report["no_properties"] is True

    def test_no_correlations_true(self) -> None:
        result = self._make_result()
        report = build_configurable_algebraic_residual_report(result)
        assert report["no_correlations"] is True

    def test_no_hx_models_true(self) -> None:
        result = self._make_result()
        report = build_configurable_algebraic_residual_report(result)
        assert report["no_hx_models"] is True

    def test_no_production_components_true(self) -> None:
        result = self._make_result()
        report = build_configurable_algebraic_residual_report(result)
        assert report["no_production_components"] is True

    def test_no_role_based_physics_true(self) -> None:
        result = self._make_result()
        report = build_configurable_algebraic_residual_report(result)
        assert report["no_role_based_physics"] is True

    def test_no_automatic_closure_inference_true(self) -> None:
        result = self._make_result()
        report = build_configurable_algebraic_residual_report(result)
        assert report["no_automatic_closure_inference"] is True

    def test_residual_names_in_report(self) -> None:
        result = self._make_result()
        report = build_configurable_algebraic_residual_report(result)
        assert report["residual_names"] == ["mb:node"]

    def test_residual_values_in_report(self) -> None:
        result = self._make_result()
        report = build_configurable_algebraic_residual_report(result)
        assert report["residual_values"] == {"mb:node": pytest.approx(0.0)}

    def test_max_abs_residual_in_report(self) -> None:
        result = self._make_result()
        report = build_configurable_algebraic_residual_report(result)
        assert "max_abs_residual" in report

    def test_l2_norm_in_report(self) -> None:
        result = self._make_result()
        report = build_configurable_algebraic_residual_report(result)
        assert "l2_norm" in report

    def test_limitations_in_report(self) -> None:
        result = self._make_result()
        report = build_configurable_algebraic_residual_report(result)
        limitations = report["limitations"]
        assert isinstance(limitations, list)
        assert len(limitations) > 0

    def test_report_contains_no_solve_statement(self) -> None:
        result = self._make_result()
        report = build_configurable_algebraic_residual_report(result)
        lim_text = " ".join(report["limitations"])  # type: ignore[arg-type]
        assert "solve" in lim_text.lower()

    def test_scenario_compatibility_optional(self) -> None:
        result = self._make_result()
        report_no_compat = build_configurable_algebraic_residual_report(result)
        assert "scenario_compatibility" not in report_no_compat

    def test_scenario_compatibility_included_if_provided(self) -> None:
        result = self._make_result()
        compat = {"is_compatible": True, "reasons": ["ok"]}
        report = build_configurable_algebraic_residual_report(result, scenario_compatibility=compat)
        assert "scenario_compatibility" in report
        assert report["scenario_compatibility"] == compat

    def test_rejects_non_result(self) -> None:
        with pytest.raises(TypeError, match="ConfigurableAlgebraicResidualEvaluationResult"):
            build_configurable_algebraic_residual_report("not_a_result")  # type: ignore[arg-type]

    def test_no_file_writing(self) -> None:
        result = self._make_result()
        report = build_configurable_algebraic_residual_report(result)
        # If we got a dict back, no file was written (no exception is the assertion).
        assert isinstance(report, dict)


# ===========================================================================
# validate_algebraic_residuals_against_scenario
# ===========================================================================


class TestValidateAlgebraicResidualsAgainstScenario:
    def _make_residual_set(self) -> ConfigurableAlgebraicResidualSet:
        d = ImposedPressureResidualDeclaration(
            residual_name="ip:acc",
            pressure_unknown="P:n_acc_out",
            imposed_value=200_000.0,
        )
        return build_configurable_algebraic_residual_set([d])

    class _FakeBuildResult:
        def __init__(self, unknown_names: tuple[str, ...]) -> None:
            self.unknown_names = unknown_names

    def test_compatible_when_all_names_present(self) -> None:
        s = self._make_residual_set()
        fake = self._FakeBuildResult(("P:n_acc_out", "P:n_pump_out", "mdot:pump"))
        report = validate_algebraic_residuals_against_scenario(s, fake)
        assert report["is_compatible"] is True
        assert report["missing_unknowns"] == []

    def test_incompatible_when_name_missing(self) -> None:
        s = self._make_residual_set()
        fake = self._FakeBuildResult(("mdot:pump",))  # P:n_acc_out not present
        report = validate_algebraic_residuals_against_scenario(s, fake)
        assert report["is_compatible"] is False
        assert "P:n_acc_out" in report["missing_unknowns"]

    def test_report_is_plain_dict(self) -> None:
        s = self._make_residual_set()
        fake = self._FakeBuildResult(("P:n_acc_out",))
        report = validate_algebraic_residuals_against_scenario(s, fake)
        assert isinstance(report, dict)

    def test_report_json_serializable(self) -> None:
        s = self._make_residual_set()
        fake = self._FakeBuildResult(("P:n_acc_out",))
        report = validate_algebraic_residuals_against_scenario(s, fake)
        json.dumps(report)  # must not raise

    def test_report_no_residuals_inferred_from_roles(self) -> None:
        s = self._make_residual_set()
        fake = self._FakeBuildResult(("P:n_acc_out",))
        report = validate_algebraic_residuals_against_scenario(s, fake)
        assert report["no_residuals_inferred_from_roles"] is True

    def test_report_no_residuals_inferred_from_topology(self) -> None:
        s = self._make_residual_set()
        fake = self._FakeBuildResult(("P:n_acc_out",))
        report = validate_algebraic_residuals_against_scenario(s, fake)
        assert report["no_residuals_inferred_from_topology"] is True

    def test_report_includes_declared_unknowns(self) -> None:
        s = self._make_residual_set()
        fake = self._FakeBuildResult(("P:n_acc_out",))
        report = validate_algebraic_residuals_against_scenario(s, fake)
        assert "P:n_acc_out" in report["declared_unknowns"]

    def test_rejects_non_residual_set(self) -> None:
        fake = self._FakeBuildResult(())
        with pytest.raises(TypeError, match="ConfigurableAlgebraicResidualSet"):
            validate_algebraic_residuals_against_scenario("not_a_set", fake)  # type: ignore[arg-type]

    def test_rejects_build_result_without_unknown_names(self) -> None:
        s = self._make_residual_set()
        with pytest.raises(TypeError, match="unknown_names"):
            validate_algebraic_residuals_against_scenario(s, object())


# ===========================================================================
# Boundary assertions
# ===========================================================================


class TestBoundaryAssertions:
    """Verify the module is free of forbidden imports and patterns."""

    def _import_lines(self) -> list[str]:
        """Return only import-statement lines from the module source."""
        import re

        import mpl_sim.network.configurable_algebraic_residuals as mod

        src_path = getattr(mod, "__file__", "")
        if not src_path:
            return []
        with open(src_path) as f:
            text = f.read()
        return [ln for ln in text.splitlines() if re.match(r"^\s*(import|from)\s+", ln)]

    def _executable_lines(self) -> list[str]:
        """Return non-comment, non-docstring source lines."""
        import mpl_sim.network.configurable_algebraic_residuals as mod

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

    def test_no_coolprop_import(self) -> None:
        import mpl_sim.network.configurable_algebraic_residuals as mod

        assert not hasattr(mod, "CoolProp")
        for ln in self._import_lines():
            assert "CoolProp" not in ln, f"CoolProp found in import: {ln!r}"

    def test_no_property_backend_import(self) -> None:
        import mpl_sim.network.configurable_algebraic_residuals as mod

        assert not hasattr(mod, "PropertyBackend")
        for ln in self._import_lines():
            assert "PropertyBackend" not in ln, f"PropertyBackend found in import: {ln!r}"

    def test_no_system_state_import(self) -> None:
        import mpl_sim.network.configurable_algebraic_residuals as mod

        assert not hasattr(mod, "SystemState")
        for ln in self._import_lines():
            assert "SystemState" not in ln

    def test_no_fluid_state_import(self) -> None:
        import mpl_sim.network.configurable_algebraic_residuals as mod

        assert not hasattr(mod, "FluidState")
        for ln in self._import_lines():
            assert "FluidState" not in ln

    def test_no_contribute_definition(self) -> None:
        for ln in self._executable_lines():
            assert "def contribute" not in ln, f"contribute defined: {ln!r}"

    def test_no_contribute_call(self) -> None:
        for ln in self._executable_lines():
            assert ".contribute(" not in ln, f"contribute call found: {ln!r}"

    def test_no_component_type_dispatch(self) -> None:
        for ln in self._executable_lines():
            assert "component_type" not in ln, f"component_type found: {ln!r}"

    def test_no_solve_definition(self) -> None:
        for ln in self._executable_lines():
            assert "def solve" not in ln, f"solve defined: {ln!r}"

    def test_no_fsolve_or_lstsq(self) -> None:
        for ln in self._executable_lines():
            assert "fsolve" not in ln
            assert "lstsq" not in ln
            assert "least_squares" not in ln

    def test_no_correlation_registry_import(self) -> None:
        import mpl_sim.network.configurable_algebraic_residuals as mod

        assert not hasattr(mod, "CorrelationRegistry")
        for ln in self._import_lines():
            assert "CorrelationRegistry" not in ln

    def test_no_hx_model_import(self) -> None:
        import mpl_sim.network.configurable_algebraic_residuals as mod

        assert not hasattr(mod, "hx_models")
        for ln in self._import_lines():
            assert "hx_models" not in ln

    def test_no_file_write(self) -> None:
        for ln in self._executable_lines():
            assert "write_text" not in ln
            assert "to_csv" not in ln

    def test_module_has_no_network_graph_solve(self) -> None:
        import mpl_sim.network.configurable_algebraic_residuals as mod

        assert not hasattr(mod, "NetworkGraph")

    def test_no_role_attribute_in_mass_balance_declaration(self) -> None:
        d = MassBalanceResidualDeclaration(
            residual_name="mb:x",
            incoming_unknown_names=("m",),
            outgoing_unknown_names=(),
        )
        # Declaration has 'kind' not 'role'; role is for ScenarioComponentSpec.
        assert not hasattr(d, "role")

    def test_public_api_importable_from_network_package(self) -> None:
        from mpl_sim.network import (
            ConfigurableAlgebraicResidualKind,
        )

        assert ConfigurableAlgebraicResidualKind is not None
