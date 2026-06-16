"""Pump component tests — Phase 10A / 10B.

Verifies:
  PumpComponent — construction, id/name, kind, ports, immutability.
  PumpOperatingPoint — construction, validation, immutability.
  PumpHydraulicSummary — structure, immutability.
  PumpComponent.evaluate_hydraulic — prescribed pressure-rise law, sign
    convention, calibration multiplier, invalid inputs rejected, no mutation.

Import-boundary assertions:
  components/pump.py must not import coolprop, network, solvers, or properties.
"""

from __future__ import annotations

import math

import pytest

from mpl_sim.components.base import ComponentId, ComponentKind
from mpl_sim.components.pump import (
    PumpComponent,
    PumpHydraulicSummary,
    PumpOperatingPoint,
)
from mpl_sim.core.port import PortRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pump(name: str = "pump_1") -> PumpComponent:
    return PumpComponent(component_id=ComponentId(name))


def _import_lines(module_file: str) -> list[str]:
    with open(module_file) as f:
        lines = f.readlines()
    return [line.strip() for line in lines if line.strip().startswith(("import ", "from "))]


# ---------------------------------------------------------------------------
# Phase 10A — skeleton: construction and identity
# ---------------------------------------------------------------------------


class TestPumpConstruction:
    def test_basic_construction(self) -> None:
        pump = _make_pump()
        assert pump.component_id == ComponentId("pump_1")

    def test_kind_is_pump(self) -> None:
        assert _make_pump().kind() is ComponentKind.PUMP

    def test_is_immutable(self) -> None:
        pump = _make_pump()
        with pytest.raises((AttributeError, TypeError)):
            pump.component_id = ComponentId("other")  # type: ignore[misc]

    def test_rejects_empty_name(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            PumpComponent(component_id=ComponentId(""))

    def test_different_ids_not_equal(self) -> None:
        assert _make_pump("p1") != _make_pump("p2")

    def test_same_ids_are_equal(self) -> None:
        assert _make_pump("p1") == _make_pump("p1")

    def test_repr_contains_name(self) -> None:
        pump = _make_pump("mypump")
        assert "mypump" in repr(pump)

    def test_internal_state_names_empty(self) -> None:
        assert _make_pump().internal_state_names() == ()


# ---------------------------------------------------------------------------
# Phase 10A — ports consistent with component contract
# ---------------------------------------------------------------------------


class TestPumpPorts:
    def test_ports_returns_two_ports(self) -> None:
        assert len(_make_pump().ports()) == 2

    def test_first_port_is_inlet(self) -> None:
        ports = _make_pump().ports()
        assert ports[0].role is PortRole.INLET

    def test_second_port_is_outlet(self) -> None:
        ports = _make_pump().ports()
        assert ports[1].role is PortRole.OUTLET

    def test_inlet_property_role(self) -> None:
        assert _make_pump().inlet.role is PortRole.INLET

    def test_outlet_property_role(self) -> None:
        assert _make_pump().outlet.role is PortRole.OUTLET

    def test_inlet_port_name(self) -> None:
        assert _make_pump("p").inlet.id.port_name == "in"

    def test_outlet_port_name(self) -> None:
        assert _make_pump("p").outlet.id.port_name == "out"

    def test_ports_owned_by_component(self) -> None:
        pump = _make_pump("mypump")
        for port in pump.ports():
            assert port.owner == "mypump"

    def test_inlet_port_id_references_component(self) -> None:
        pump = _make_pump("mypump")
        assert pump.inlet.id.component_id == "mypump"

    def test_outlet_port_id_references_component(self) -> None:
        pump = _make_pump("mypump")
        assert pump.outlet.id.component_id == "mypump"

    def test_ports_have_no_peer_before_assembly(self) -> None:
        for port in _make_pump().ports():
            assert port.peer is None

    def test_ports_carry_no_thermodynamic_values(self) -> None:
        forbidden = ("P", "h", "mdot", "T", "x", "rho", "mu", "quality", "phase")
        for port in _make_pump().ports():
            for attr in forbidden:
                assert not hasattr(port, attr), f"Port must not have attribute {attr!r}"

    def test_inlet_and_outlet_have_different_ids(self) -> None:
        pump = _make_pump()
        assert pump.inlet.id != pump.outlet.id


# ---------------------------------------------------------------------------
# Phase 10A — import boundary: pump module must not touch forbidden packages
# ---------------------------------------------------------------------------


class TestPumpImportBoundaries:
    def test_pump_module_does_not_import_coolprop(self) -> None:
        import mpl_sim.components.pump as mod

        assert mod.__file__ is not None
        for line in _import_lines(mod.__file__):
            assert "coolprop" not in line.lower(), f"Forbidden import: {line!r}"

    def test_pump_module_does_not_import_network(self) -> None:
        import mpl_sim.components.pump as mod

        assert mod.__file__ is not None
        for line in _import_lines(mod.__file__):
            assert "network" not in line, f"Forbidden import: {line!r}"

    def test_pump_module_does_not_import_solvers(self) -> None:
        import mpl_sim.components.pump as mod

        assert mod.__file__ is not None
        for line in _import_lines(mod.__file__):
            assert "solvers" not in line, f"Forbidden import: {line!r}"

    def test_pump_module_does_not_import_properties(self) -> None:
        import mpl_sim.components.pump as mod

        assert mod.__file__ is not None
        for line in _import_lines(mod.__file__):
            assert "mpl_sim.properties" not in line, f"Forbidden import: {line!r}"

    def test_pump_module_does_not_import_correlations(self) -> None:
        import mpl_sim.components.pump as mod

        assert mod.__file__ is not None
        for line in _import_lines(mod.__file__):
            assert "mpl_sim.correlations" not in line, f"Forbidden import: {line!r}"


# ---------------------------------------------------------------------------
# Phase 10B — PumpOperatingPoint validation
# ---------------------------------------------------------------------------


class TestPumpOperatingPoint:
    def test_basic_construction(self) -> None:
        op = PumpOperatingPoint(delta_p_setpoint=50_000.0)
        assert op.delta_p_setpoint == 50_000.0
        assert op.pressure_rise_multiplier == 1.0

    def test_construction_with_multiplier(self) -> None:
        op = PumpOperatingPoint(delta_p_setpoint=50_000.0, pressure_rise_multiplier=1.2)
        assert op.pressure_rise_multiplier == 1.2

    def test_is_immutable(self) -> None:
        op = PumpOperatingPoint(delta_p_setpoint=1e5)
        with pytest.raises((AttributeError, TypeError)):
            op.delta_p_setpoint = 2e5  # type: ignore[misc]

    def test_rejects_nan_setpoint(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            PumpOperatingPoint(delta_p_setpoint=math.nan)

    def test_rejects_pos_inf_setpoint(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            PumpOperatingPoint(delta_p_setpoint=math.inf)

    def test_rejects_neg_inf_setpoint(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            PumpOperatingPoint(delta_p_setpoint=-math.inf)

    def test_rejects_nan_multiplier(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            PumpOperatingPoint(delta_p_setpoint=1e5, pressure_rise_multiplier=math.nan)

    def test_rejects_inf_multiplier(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            PumpOperatingPoint(delta_p_setpoint=1e5, pressure_rise_multiplier=math.inf)

    def test_rejects_negative_multiplier(self) -> None:
        with pytest.raises(ValueError, match=">= 0"):
            PumpOperatingPoint(delta_p_setpoint=1e5, pressure_rise_multiplier=-0.1)

    def test_zero_multiplier_accepted(self) -> None:
        op = PumpOperatingPoint(delta_p_setpoint=1e5, pressure_rise_multiplier=0.0)
        assert op.pressure_rise_multiplier == 0.0

    def test_negative_setpoint_accepted(self) -> None:
        op = PumpOperatingPoint(delta_p_setpoint=-1e4)
        assert op.delta_p_setpoint == -1e4

    def test_zero_setpoint_accepted(self) -> None:
        op = PumpOperatingPoint(delta_p_setpoint=0.0)
        assert op.delta_p_setpoint == 0.0


# ---------------------------------------------------------------------------
# Phase 10B — PumpHydraulicSummary structure
# ---------------------------------------------------------------------------


class TestPumpHydraulicSummary:
    def test_is_immutable(self) -> None:
        summary = PumpHydraulicSummary(
            delta_p=1e5,
            raw_delta_p=1e5,
            pressure_rise_multiplier=1.0,
        )
        with pytest.raises((AttributeError, TypeError)):
            summary.delta_p = 2e5  # type: ignore[misc]

    def test_fields_accessible(self) -> None:
        summary = PumpHydraulicSummary(
            delta_p=1.2e5,
            raw_delta_p=1e5,
            pressure_rise_multiplier=1.2,
        )
        assert summary.delta_p == 1.2e5
        assert summary.raw_delta_p == 1e5
        assert summary.pressure_rise_multiplier == 1.2


# ---------------------------------------------------------------------------
# Phase 10B — evaluate_hydraulic behaviour
# ---------------------------------------------------------------------------


class TestPumpEvaluateHydraulic:
    def test_prescribed_pressure_rise_default_multiplier(self) -> None:
        pump = _make_pump()
        result = pump.evaluate_hydraulic(PumpOperatingPoint(delta_p_setpoint=50_000.0))
        assert result.delta_p == pytest.approx(50_000.0)

    def test_raw_delta_p_equals_setpoint(self) -> None:
        pump = _make_pump()
        result = pump.evaluate_hydraulic(PumpOperatingPoint(delta_p_setpoint=30_000.0))
        assert result.raw_delta_p == pytest.approx(30_000.0)

    def test_multiplier_scales_pressure_rise(self) -> None:
        pump = _make_pump()
        op = PumpOperatingPoint(delta_p_setpoint=50_000.0, pressure_rise_multiplier=1.2)
        result = pump.evaluate_hydraulic(op)
        assert result.delta_p == pytest.approx(60_000.0)

    def test_multiplier_does_not_affect_raw(self) -> None:
        pump = _make_pump()
        op = PumpOperatingPoint(delta_p_setpoint=50_000.0, pressure_rise_multiplier=2.0)
        result = pump.evaluate_hydraulic(op)
        assert result.raw_delta_p == pytest.approx(50_000.0)

    def test_zero_multiplier_gives_zero_delta_p(self) -> None:
        pump = _make_pump()
        op = PumpOperatingPoint(delta_p_setpoint=50_000.0, pressure_rise_multiplier=0.0)
        result = pump.evaluate_hydraulic(op)
        assert result.delta_p == pytest.approx(0.0)

    def test_negative_setpoint_propagates(self) -> None:
        pump = _make_pump()
        result = pump.evaluate_hydraulic(PumpOperatingPoint(delta_p_setpoint=-5_000.0))
        assert result.delta_p == pytest.approx(-5_000.0)

    def test_sign_convention_positive_raises_pressure(self) -> None:
        pump = _make_pump()
        assert pump.evaluate_hydraulic(PumpOperatingPoint(delta_p_setpoint=10_000.0)).delta_p > 0
        assert pump.evaluate_hydraulic(PumpOperatingPoint(delta_p_setpoint=-10_000.0)).delta_p < 0

    def test_result_multiplier_echoed(self) -> None:
        pump = _make_pump()
        op = PumpOperatingPoint(delta_p_setpoint=1e5, pressure_rise_multiplier=1.5)
        result = pump.evaluate_hydraulic(op)
        assert result.pressure_rise_multiplier == pytest.approx(1.5)

    def test_result_is_immutable(self) -> None:
        pump = _make_pump()
        result = pump.evaluate_hydraulic(PumpOperatingPoint(delta_p_setpoint=1e5))
        with pytest.raises((AttributeError, TypeError)):
            result.delta_p = 2e5  # type: ignore[misc]

    def test_pump_not_mutated_by_evaluation(self) -> None:
        pump = _make_pump("pump_x")
        pump.evaluate_hydraulic(PumpOperatingPoint(delta_p_setpoint=1e5))
        assert pump.component_id == ComponentId("pump_x")

    def test_zero_setpoint_returns_zero(self) -> None:
        pump = _make_pump()
        result = pump.evaluate_hydraulic(PumpOperatingPoint(delta_p_setpoint=0.0))
        assert result.delta_p == pytest.approx(0.0)
        assert result.raw_delta_p == pytest.approx(0.0)
