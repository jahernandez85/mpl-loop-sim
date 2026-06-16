"""Pump component tests — Phase 10A / 10B / 10F.

Verifies:
  PumpComponent — construction, id/name, kind, ports, immutability.
  PumpGeometry — construction, validation, inertia derivation.
  PumpMapPoint — construction, validation.
  PumpPerformanceMap — evaluation, interpolation, edge cases.
  PumpSpeedCommand / PumpFlowTarget — construction, validation.
  PumpComponent.validate_speed_command / validate_flow_target — binding check.
  PumpOperatingPoint — construction, validation, immutability.
  PumpHydraulicSummary — structure, immutability.
  PumpComponent.evaluate_hydraulic — prescribed pressure-rise law.
  PumpComponent.evaluate_pump_map — map-based evaluation.
  PumpPowerInput / PumpPowerSummary — power/efficiency seam.
  PumpComponent.evaluate_power — shaft power derivation.
  internal_state_names() — "omega" is present (named-frozen seam).

Import-boundary assertions:
  components/pump.py must not import coolprop, network, solvers, or properties.
  components/pump.py must not import mpl_sim.correlations.
"""

from __future__ import annotations

import math

import pytest

from mpl_sim.components.base import ComponentId, ComponentKind
from mpl_sim.components.pump import (
    PumpComponent,
    PumpFlowTarget,
    PumpGeometry,
    PumpHydraulicSummary,
    PumpMapPoint,
    PumpOperatingPoint,
    PumpPerformanceMap,
    PumpPowerInput,
    PumpPowerSummary,
    PumpSpeedCommand,
)
from mpl_sim.core.port import PortRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pump(name: str = "pump_1") -> PumpComponent:
    return PumpComponent(component_id=ComponentId(name))


def _make_pump_with_geom(name: str = "pump_1") -> PumpComponent:
    return PumpComponent(
        component_id=ComponentId(name),
        geometry=PumpGeometry(L=0.5, A=0.002),
    )


def _import_lines(module_file: str) -> list[str]:
    with open(module_file, encoding="utf-8") as f:
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

    def test_internal_state_names_has_omega(self) -> None:
        assert "omega" in _make_pump().internal_state_names()

    def test_internal_state_names_is_tuple(self) -> None:
        assert isinstance(_make_pump().internal_state_names(), tuple)

    def test_geometry_defaults_to_none(self) -> None:
        pump = _make_pump()
        assert pump.geometry is None

    def test_geometry_stored_when_provided(self) -> None:
        geom = PumpGeometry(L=1.0, A=0.01)
        pump = PumpComponent(component_id=ComponentId("p"), geometry=geom)
        assert pump.geometry is geom


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


# ---------------------------------------------------------------------------
# Phase 10F — PumpGeometry
# ---------------------------------------------------------------------------


class TestPumpGeometry:
    def test_basic_construction(self) -> None:
        g = PumpGeometry(L=1.0, A=0.01)
        assert g.L == pytest.approx(1.0)
        assert g.A == pytest.approx(0.01)

    def test_is_immutable(self) -> None:
        g = PumpGeometry(L=1.0, A=0.01)
        with pytest.raises((AttributeError, TypeError)):
            g.L = 2.0  # type: ignore[misc]

    def test_inertia_L_over_A(self) -> None:
        g = PumpGeometry(L=1.0, A=0.01)
        assert g.inertia() == pytest.approx(100.0)

    def test_inertia_varies_with_L(self) -> None:
        g1 = PumpGeometry(L=1.0, A=0.01)
        g2 = PumpGeometry(L=2.0, A=0.01)
        assert g2.inertia() == pytest.approx(2 * g1.inertia())

    def test_rejects_zero_L(self) -> None:
        with pytest.raises(ValueError, match="> 0"):
            PumpGeometry(L=0.0, A=0.01)

    def test_rejects_negative_L(self) -> None:
        with pytest.raises(ValueError, match="> 0"):
            PumpGeometry(L=-1.0, A=0.01)

    def test_rejects_zero_A(self) -> None:
        with pytest.raises(ValueError, match="> 0"):
            PumpGeometry(L=1.0, A=0.0)

    def test_rejects_nan_L(self) -> None:
        with pytest.raises(ValueError):
            PumpGeometry(L=math.nan, A=0.01)

    def test_rejects_inf_L(self) -> None:
        with pytest.raises(ValueError):
            PumpGeometry(L=math.inf, A=0.01)


# ---------------------------------------------------------------------------
# Phase 10F — PumpMapPoint
# ---------------------------------------------------------------------------


class TestPumpMapPoint:
    def test_basic_construction(self) -> None:
        pt = PumpMapPoint(omega=1000.0, mdot=0.5, delta_p=50_000.0)
        assert pt.omega == pytest.approx(1000.0)
        assert pt.mdot == pytest.approx(0.5)
        assert pt.delta_p == pytest.approx(50_000.0)

    def test_is_immutable(self) -> None:
        pt = PumpMapPoint(omega=1000.0, mdot=0.5, delta_p=50_000.0)
        with pytest.raises((AttributeError, TypeError)):
            pt.omega = 2000.0  # type: ignore[misc]

    def test_rejects_nan_omega(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            PumpMapPoint(omega=math.nan, mdot=0.5, delta_p=50_000.0)

    def test_rejects_inf_omega(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            PumpMapPoint(omega=math.inf, mdot=0.5, delta_p=50_000.0)

    def test_rejects_nan_mdot(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            PumpMapPoint(omega=1000.0, mdot=math.nan, delta_p=50_000.0)

    def test_rejects_nan_delta_p(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            PumpMapPoint(omega=1000.0, mdot=0.5, delta_p=math.nan)

    def test_negative_omega_accepted(self) -> None:
        pt = PumpMapPoint(omega=-500.0, mdot=0.5, delta_p=1e4)
        assert pt.omega == pytest.approx(-500.0)

    def test_zero_delta_p_accepted(self) -> None:
        pt = PumpMapPoint(omega=1000.0, mdot=0.0, delta_p=0.0)
        assert pt.delta_p == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Phase 10F — PumpPerformanceMap
# ---------------------------------------------------------------------------


class TestPumpPerformanceMap:
    def _single_point_map(self) -> PumpPerformanceMap:
        return PumpPerformanceMap(points=(PumpMapPoint(omega=1000.0, mdot=0.5, delta_p=50_000.0),))

    def _two_point_map(self) -> PumpPerformanceMap:
        return PumpPerformanceMap(
            points=(
                PumpMapPoint(omega=1000.0, mdot=0.0, delta_p=60_000.0),
                PumpMapPoint(omega=1000.0, mdot=1.0, delta_p=40_000.0),
            )
        )

    def test_rejects_empty_points(self) -> None:
        with pytest.raises(ValueError):
            PumpPerformanceMap(points=())

    def test_is_immutable(self) -> None:
        m = self._single_point_map()
        with pytest.raises((AttributeError, TypeError)):
            m.points = ()  # type: ignore[misc]

    def test_single_point_returns_delta_p(self) -> None:
        m = self._single_point_map()
        assert m.evaluate(1000.0, 0.5) == pytest.approx(50_000.0)

    def test_single_point_any_mdot_returns_same_delta_p(self) -> None:
        m = self._single_point_map()
        assert m.evaluate(1000.0, 0.0) == pytest.approx(50_000.0)
        assert m.evaluate(1000.0, 99.0) == pytest.approx(50_000.0)

    def test_two_points_interpolates_at_midpoint(self) -> None:
        m = self._two_point_map()
        assert m.evaluate(1000.0, 0.5) == pytest.approx(50_000.0)

    def test_two_points_at_lower_bound(self) -> None:
        m = self._two_point_map()
        assert m.evaluate(1000.0, 0.0) == pytest.approx(60_000.0)

    def test_two_points_at_upper_bound(self) -> None:
        m = self._two_point_map()
        assert m.evaluate(1000.0, 1.0) == pytest.approx(40_000.0)

    def test_two_points_interpolation_is_linear(self) -> None:
        m = self._two_point_map()
        # At mdot=0.25: delta_p = 60000 + 0.25*(40000-60000) = 55000
        assert m.evaluate(1000.0, 0.25) == pytest.approx(55_000.0)

    def test_unknown_omega_raises(self) -> None:
        m = self._single_point_map()
        with pytest.raises(ValueError, match="omega"):
            m.evaluate(999.0, 0.5)

    def test_mdot_out_of_range_raises(self) -> None:
        m = self._two_point_map()
        with pytest.raises(ValueError):
            m.evaluate(1000.0, 2.0)

    def test_multiple_omega_values(self) -> None:
        m = PumpPerformanceMap(
            points=(
                PumpMapPoint(omega=500.0, mdot=0.5, delta_p=20_000.0),
                PumpMapPoint(omega=1000.0, mdot=0.5, delta_p=50_000.0),
            )
        )
        assert m.evaluate(500.0, 0.5) == pytest.approx(20_000.0)
        assert m.evaluate(1000.0, 0.5) == pytest.approx(50_000.0)

    def test_evaluate_is_deterministic(self) -> None:
        m = self._two_point_map()
        r1 = m.evaluate(1000.0, 0.3)
        r2 = m.evaluate(1000.0, 0.3)
        assert r1 == r2


# ---------------------------------------------------------------------------
# Phase 10F — PumpSpeedCommand
# ---------------------------------------------------------------------------


class TestPumpSpeedCommand:
    def test_basic_construction(self) -> None:
        cmd = PumpSpeedCommand(component_id="pump_1", omega=1000.0)
        assert cmd.component_id == "pump_1"
        assert cmd.omega == pytest.approx(1000.0)

    def test_is_immutable(self) -> None:
        cmd = PumpSpeedCommand(component_id="pump_1", omega=1000.0)
        with pytest.raises((AttributeError, TypeError)):
            cmd.omega = 2000.0  # type: ignore[misc]

    def test_rejects_empty_component_id(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            PumpSpeedCommand(component_id="", omega=1000.0)

    def test_rejects_nan_omega(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            PumpSpeedCommand(component_id="p", omega=math.nan)

    def test_rejects_inf_omega(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            PumpSpeedCommand(component_id="p", omega=math.inf)

    def test_zero_omega_accepted(self) -> None:
        cmd = PumpSpeedCommand(component_id="p", omega=0.0)
        assert cmd.omega == pytest.approx(0.0)

    def test_negative_omega_accepted(self) -> None:
        cmd = PumpSpeedCommand(component_id="p", omega=-500.0)
        assert cmd.omega == pytest.approx(-500.0)


# ---------------------------------------------------------------------------
# Phase 10F — PumpFlowTarget
# ---------------------------------------------------------------------------


class TestPumpFlowTarget:
    def test_basic_construction(self) -> None:
        tgt = PumpFlowTarget(component_id="pump_1", mdot=0.5)
        assert tgt.component_id == "pump_1"
        assert tgt.mdot == pytest.approx(0.5)

    def test_is_immutable(self) -> None:
        tgt = PumpFlowTarget(component_id="pump_1", mdot=0.5)
        with pytest.raises((AttributeError, TypeError)):
            tgt.mdot = 1.0  # type: ignore[misc]

    def test_rejects_empty_component_id(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            PumpFlowTarget(component_id="", mdot=0.5)

    def test_rejects_nan_mdot(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            PumpFlowTarget(component_id="p", mdot=math.nan)

    def test_rejects_inf_mdot(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            PumpFlowTarget(component_id="p", mdot=math.inf)

    def test_zero_mdot_accepted(self) -> None:
        tgt = PumpFlowTarget(component_id="p", mdot=0.0)
        assert tgt.mdot == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Phase 10F — command binding validation on PumpComponent
# ---------------------------------------------------------------------------


class TestPumpCommandBinding:
    def test_speed_command_matching_id_passes(self) -> None:
        pump = _make_pump("pump_1")
        cmd = PumpSpeedCommand(component_id="pump_1", omega=1000.0)
        pump.validate_speed_command(cmd)  # no exception

    def test_speed_command_nonmatching_id_raises(self) -> None:
        pump = _make_pump("pump_1")
        cmd = PumpSpeedCommand(component_id="pump_2", omega=1000.0)
        with pytest.raises(ValueError, match="pump_2"):
            pump.validate_speed_command(cmd)

    def test_flow_target_matching_id_passes(self) -> None:
        pump = _make_pump("pump_1")
        tgt = PumpFlowTarget(component_id="pump_1", mdot=0.5)
        pump.validate_flow_target(tgt)  # no exception

    def test_flow_target_nonmatching_id_raises(self) -> None:
        pump = _make_pump("pump_1")
        tgt = PumpFlowTarget(component_id="other_pump", mdot=0.5)
        with pytest.raises(ValueError, match="other_pump"):
            pump.validate_flow_target(tgt)

    def test_validate_does_not_mutate_pump(self) -> None:
        pump = _make_pump("pump_1")
        cmd = PumpSpeedCommand(component_id="pump_1", omega=500.0)
        pump.validate_speed_command(cmd)
        assert pump.component_id == ComponentId("pump_1")


# ---------------------------------------------------------------------------
# Phase 10F — evaluate_pump_map
# ---------------------------------------------------------------------------


class TestPumpMapEvaluation:
    def _map_single(self) -> PumpPerformanceMap:
        return PumpPerformanceMap(points=(PumpMapPoint(omega=1000.0, mdot=0.5, delta_p=50_000.0),))

    def _map_two(self) -> PumpPerformanceMap:
        return PumpPerformanceMap(
            points=(
                PumpMapPoint(omega=1000.0, mdot=0.0, delta_p=60_000.0),
                PumpMapPoint(omega=1000.0, mdot=1.0, delta_p=40_000.0),
            )
        )

    def test_map_returns_expected_delta_p(self) -> None:
        pump = _make_pump()
        result = pump.evaluate_pump_map(self._map_single(), 1000.0, 0.5)
        assert result.delta_p == pytest.approx(50_000.0)

    def test_map_result_is_hydraulic_summary(self) -> None:
        pump = _make_pump()
        result = pump.evaluate_pump_map(self._map_single(), 1000.0, 0.5)
        assert isinstance(result, PumpHydraulicSummary)

    def test_map_multiplier_is_one(self) -> None:
        pump = _make_pump()
        result = pump.evaluate_pump_map(self._map_single(), 1000.0, 0.5)
        assert result.pressure_rise_multiplier == pytest.approx(1.0)

    def test_map_raw_equals_delta_p(self) -> None:
        pump = _make_pump()
        result = pump.evaluate_pump_map(self._map_single(), 1000.0, 0.5)
        assert result.raw_delta_p == pytest.approx(result.delta_p)

    def test_map_interpolates_correctly(self) -> None:
        pump = _make_pump()
        result = pump.evaluate_pump_map(self._map_two(), 1000.0, 0.5)
        assert result.delta_p == pytest.approx(50_000.0)

    def test_map_result_is_deterministic(self) -> None:
        pump = _make_pump()
        r1 = pump.evaluate_pump_map(self._map_single(), 1000.0, 0.5)
        r2 = pump.evaluate_pump_map(self._map_single(), 1000.0, 0.5)
        assert r1.delta_p == pytest.approx(r2.delta_p)

    def test_rejects_nan_omega(self) -> None:
        pump = _make_pump()
        with pytest.raises(ValueError, match="finite"):
            pump.evaluate_pump_map(self._map_single(), math.nan, 0.5)

    def test_rejects_nan_mdot(self) -> None:
        pump = _make_pump()
        with pytest.raises(ValueError, match="finite"):
            pump.evaluate_pump_map(self._map_single(), 1000.0, math.nan)

    def test_map_does_not_mutate_pump(self) -> None:
        pump = _make_pump("pump_x")
        pump.evaluate_pump_map(self._map_single(), 1000.0, 0.5)
        assert pump.component_id == ComponentId("pump_x")

    def test_result_is_immutable(self) -> None:
        pump = _make_pump()
        result = pump.evaluate_pump_map(self._map_single(), 1000.0, 0.5)
        with pytest.raises((AttributeError, TypeError)):
            result.delta_p = 0.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Phase 10F — PumpPowerInput / PumpPowerSummary
# ---------------------------------------------------------------------------


class TestPumpPowerInput:
    def test_basic_construction(self) -> None:
        inp = PumpPowerInput(mdot=0.5, delta_p=50_000.0, specific_volume=1e-3, efficiency=0.8)
        assert inp.mdot == pytest.approx(0.5)
        assert inp.efficiency == pytest.approx(0.8)

    def test_is_immutable(self) -> None:
        inp = PumpPowerInput(mdot=0.5, delta_p=50_000.0, specific_volume=1e-3, efficiency=0.8)
        with pytest.raises((AttributeError, TypeError)):
            inp.efficiency = 0.9  # type: ignore[misc]

    def test_rejects_nan_mdot(self) -> None:
        with pytest.raises(ValueError):
            PumpPowerInput(mdot=math.nan, delta_p=5e4, specific_volume=1e-3, efficiency=0.8)

    def test_rejects_nan_delta_p(self) -> None:
        with pytest.raises(ValueError):
            PumpPowerInput(mdot=0.5, delta_p=math.nan, specific_volume=1e-3, efficiency=0.8)

    def test_rejects_zero_specific_volume(self) -> None:
        with pytest.raises(ValueError, match="> 0"):
            PumpPowerInput(mdot=0.5, delta_p=5e4, specific_volume=0.0, efficiency=0.8)

    def test_rejects_negative_specific_volume(self) -> None:
        with pytest.raises(ValueError):
            PumpPowerInput(mdot=0.5, delta_p=5e4, specific_volume=-1e-3, efficiency=0.8)

    def test_rejects_zero_efficiency(self) -> None:
        with pytest.raises(ValueError):
            PumpPowerInput(mdot=0.5, delta_p=5e4, specific_volume=1e-3, efficiency=0.0)

    def test_rejects_efficiency_above_one(self) -> None:
        with pytest.raises(ValueError):
            PumpPowerInput(mdot=0.5, delta_p=5e4, specific_volume=1e-3, efficiency=1.001)

    def test_efficiency_exactly_one_accepted(self) -> None:
        inp = PumpPowerInput(mdot=0.5, delta_p=5e4, specific_volume=1e-3, efficiency=1.0)
        assert inp.efficiency == pytest.approx(1.0)


class TestPumpPowerSummary:
    def test_is_immutable(self) -> None:
        s = PumpPowerSummary(hydraulic_power=25.0, shaft_power=31.25)
        with pytest.raises((AttributeError, TypeError)):
            s.shaft_power = 0.0  # type: ignore[misc]

    def test_fields_accessible(self) -> None:
        s = PumpPowerSummary(hydraulic_power=25.0, shaft_power=31.25)
        assert s.hydraulic_power == pytest.approx(25.0)
        assert s.shaft_power == pytest.approx(31.25)


# ---------------------------------------------------------------------------
# Phase 10F — evaluate_power
# ---------------------------------------------------------------------------


class TestPumpPowerEvaluation:
    def test_hydraulic_power_formula(self) -> None:
        # Q = mdot * specific_volume = 0.5 * 1e-3 = 5e-4 m³/s
        # W_hyd = Q * delta_p = 5e-4 * 50000 = 25 W
        pump = _make_pump()
        inp = PumpPowerInput(mdot=0.5, delta_p=50_000.0, specific_volume=1e-3, efficiency=1.0)
        result = pump.evaluate_power(inp)
        assert result.hydraulic_power == pytest.approx(25.0)

    def test_shaft_power_divided_by_efficiency(self) -> None:
        # W_shaft = 25 / 0.8 = 31.25 W
        pump = _make_pump()
        inp = PumpPowerInput(mdot=0.5, delta_p=50_000.0, specific_volume=1e-3, efficiency=0.8)
        result = pump.evaluate_power(inp)
        assert result.shaft_power == pytest.approx(31.25)

    def test_efficiency_one_shaft_equals_hydraulic(self) -> None:
        pump = _make_pump()
        inp = PumpPowerInput(mdot=0.5, delta_p=5e4, specific_volume=1e-3, efficiency=1.0)
        result = pump.evaluate_power(inp)
        assert result.shaft_power == pytest.approx(result.hydraulic_power)

    def test_result_is_immutable(self) -> None:
        pump = _make_pump()
        inp = PumpPowerInput(mdot=0.5, delta_p=5e4, specific_volume=1e-3, efficiency=0.8)
        result = pump.evaluate_power(inp)
        with pytest.raises((AttributeError, TypeError)):
            result.shaft_power = 0.0  # type: ignore[misc]

    def test_pump_not_mutated_by_power_eval(self) -> None:
        pump = _make_pump("pump_x")
        inp = PumpPowerInput(mdot=0.5, delta_p=5e4, specific_volume=1e-3, efficiency=0.8)
        pump.evaluate_power(inp)
        assert pump.component_id == ComponentId("pump_x")

    def test_zero_delta_p_gives_zero_power(self) -> None:
        pump = _make_pump()
        inp = PumpPowerInput(mdot=0.5, delta_p=0.0, specific_volume=1e-3, efficiency=0.8)
        result = pump.evaluate_power(inp)
        assert result.hydraulic_power == pytest.approx(0.0)
        assert result.shaft_power == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Phase 10F — shaft-speed internal state seam
# ---------------------------------------------------------------------------


class TestPumpInternalStateSem:
    def test_omega_in_internal_state_names(self) -> None:
        assert "omega" in _make_pump().internal_state_names()

    def test_omega_in_internal_state_names_with_geometry(self) -> None:
        assert "omega" in _make_pump_with_geom().internal_state_names()

    def test_internal_state_names_is_frozen_tuple(self) -> None:
        names = _make_pump().internal_state_names()
        assert isinstance(names, tuple)

    def test_pump_has_no_dynamic_derivative(self) -> None:
        pump = _make_pump()
        for attr in ("d_omega_dt", "domega_dt", "derivative", "dstate"):
            assert not hasattr(pump, attr), f"Pump must not have dynamic attribute {attr!r}"
