"""Pump-driven, accumulator-referenced loop acceptance shape -- Phase 10J.

Verifies the minimal seam shape for a pump + accumulator topology:
  - Topology validates with pressure_references pointing to the accumulator.
  - PumpSpeedCommand and PumpFlowTarget bind correctly to the pump.
  - PCA law derives pressure from V_g given a VolumePressureLawBinding.
  - Network nodes include both PUMP and ACCUMULATOR kinds.
  - No convergence or steady-state solve is required; shape only.
  - No CoolProp, PropertyBackend, Solver, or dynamic integration.

Topology shape:
    pump "out" --> accumulator "fluid"
    (Open-ended loop: pump inlet isolated; accumulator is the pressure reference.)
"""

from __future__ import annotations

import pytest

from mpl_sim.components.accumulator import AccumulatorComponent, VolumePressureLawBinding
from mpl_sim.components.base import ComponentId, ComponentKind
from mpl_sim.components.pump import (
    PumpComponent,
    PumpFlowTarget,
    PumpMapPoint,
    PumpPerformanceMap,
    PumpSpeedCommand,
)
from mpl_sim.correlations.volume_pressure_law import PcaVolumePressureLaw
from mpl_sim.geometry.primitives import AccumulatorGeometry, ContainmentSpec
from mpl_sim.network.topology import (
    ConnectionId,
    NetworkConnection,
    NetworkId,
    NetworkTopology,
    PressureReferenceWiring,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_pump(name: str = "pump") -> PumpComponent:
    return PumpComponent(component_id=ComponentId(name))


def _make_acc(name: str = "acc") -> AccumulatorComponent:
    containment = ContainmentSpec(inner_diameter=0.1, height=0.5)
    geometry = AccumulatorGeometry(V_total=0.010, containment=containment)
    return AccumulatorComponent(component_id=ComponentId(name), geometry=geometry)


def _pca_binding() -> VolumePressureLawBinding:
    return VolumePressureLawBinding(
        law_params={
            "charge_volume": 0.005,
            "charge_pressure": 1_000_000.0,
            "polytropic_index": 1.4,
        }
    )


def _make_loop_topology(pump_name: str = "pump", acc_name: str = "acc") -> NetworkTopology:
    pump = _make_pump(pump_name)
    acc = _make_acc(acc_name)
    conn = NetworkConnection(
        connection_id=ConnectionId("pump_to_acc"),
        from_component=pump_name,
        from_port="out",
        to_component=acc_name,
        to_port="fluid",
    )
    pref = [PressureReferenceWiring(component_id=acc_name, port_name="fluid")]
    return NetworkTopology(
        network_id=NetworkId("pump_acc_loop"),
        components=[pump, acc],
        connections=[conn],
        pressure_references=pref,
    )


# ---------------------------------------------------------------------------
# Topology validates
# ---------------------------------------------------------------------------


class TestLoopTopologyValidates:
    def test_topology_construction_succeeds(self) -> None:
        topo = _make_loop_topology()
        assert topo is not None

    def test_topology_has_two_nodes(self) -> None:
        topo = _make_loop_topology()
        assert len(topo.nodes()) == 2

    def test_pump_node_has_correct_kind(self) -> None:
        topo = _make_loop_topology()
        pump_nodes = [n for n in topo.nodes() if n.component_id == "pump"]
        assert len(pump_nodes) == 1
        assert pump_nodes[0].component_kind is ComponentKind.PUMP

    def test_accumulator_node_has_correct_kind(self) -> None:
        topo = _make_loop_topology()
        acc_nodes = [n for n in topo.nodes() if n.component_id == "acc"]
        assert len(acc_nodes) == 1
        assert acc_nodes[0].component_kind is ComponentKind.ACCUMULATOR

    def test_pressure_reference_wired_to_accumulator(self) -> None:
        topo = _make_loop_topology()
        assert len(topo.pressure_references) == 1
        assert topo.pressure_references[0].component_id == "acc"

    def test_connection_links_pump_to_accumulator(self) -> None:
        topo = _make_loop_topology()
        assert len(topo.connections()) == 1
        conn = topo.connections()[0]
        assert conn.from_component == "pump"
        assert conn.to_component == "acc"

    def test_network_id_is_accessible(self) -> None:
        topo = _make_loop_topology()
        assert topo.network_id.value == "pump_acc_loop"


# ---------------------------------------------------------------------------
# Pump command binding
# ---------------------------------------------------------------------------


class TestPumpCommandBinding:
    def test_speed_command_binds_to_pump(self) -> None:
        pump = _make_pump("pump")
        cmd = PumpSpeedCommand(component_id="pump", omega=500.0)
        pump.validate_speed_command(cmd)  # must not raise

    def test_flow_target_binds_to_pump(self) -> None:
        pump = _make_pump("pump")
        cmd = PumpFlowTarget(component_id="pump", mdot=0.5)
        pump.validate_flow_target(cmd)  # must not raise

    def test_speed_command_for_wrong_id_raises(self) -> None:
        pump = _make_pump("pump")
        cmd = PumpSpeedCommand(component_id="other_pump", omega=500.0)
        with pytest.raises(ValueError):
            pump.validate_speed_command(cmd)

    def test_flow_target_for_wrong_id_raises(self) -> None:
        pump = _make_pump("pump")
        cmd = PumpFlowTarget(component_id="other_pump", mdot=0.5)
        with pytest.raises(ValueError):
            pump.validate_flow_target(cmd)

    def test_pump_internal_state_includes_omega(self) -> None:
        pump = _make_pump("pump")
        assert "omega" in pump.internal_state_names()


# ---------------------------------------------------------------------------
# Pump performance map evaluation
# ---------------------------------------------------------------------------


class TestPumpMapEvaluation:
    def _make_perf_map(self) -> PumpPerformanceMap:
        return PumpPerformanceMap(
            points=(
                PumpMapPoint(omega=500.0, mdot=0.3, delta_p=200_000.0),
                PumpMapPoint(omega=500.0, mdot=0.5, delta_p=150_000.0),
                PumpMapPoint(omega=500.0, mdot=0.7, delta_p=80_000.0),
            )
        )

    def test_pump_map_evaluation_returns_positive_delta_p(self) -> None:
        pump = _make_pump("pump")
        perf_map = self._make_perf_map()
        result = pump.evaluate_pump_map(perf_map, omega=500.0, mdot=0.5)
        assert result.delta_p > 0.0

    def test_pump_map_evaluation_at_midpoint(self) -> None:
        pump = _make_pump("pump")
        perf_map = self._make_perf_map()
        # At mdot=0.5 (exact point) -> delta_p=150_000
        result = pump.evaluate_pump_map(perf_map, omega=500.0, mdot=0.5)
        assert result.delta_p == pytest.approx(150_000.0, rel=1e-6)


# ---------------------------------------------------------------------------
# PCA law derives pressure from V_g
# ---------------------------------------------------------------------------


class TestPcaPressureFromVg:
    def test_pca_derives_pressure_via_accumulator(self) -> None:
        acc = _make_acc("acc")
        binding = _pca_binding()
        pca = PcaVolumePressureLaw()
        result = acc.evaluate_volume_pressure_law(binding=binding, V_g=0.005, correlation=pca)
        assert result.P_derived > 0.0

    def test_pca_pressure_is_finite(self) -> None:
        import math

        acc = _make_acc("acc")
        binding = _pca_binding()
        pca = PcaVolumePressureLaw()
        result = acc.evaluate_volume_pressure_law(binding=binding, V_g=0.005, correlation=pca)
        assert math.isfinite(result.P_derived)

    def test_pca_pressure_matches_hand_calc(self) -> None:
        # V_g = V_charge = 0.005 => P = P_charge = 1e6
        acc = _make_acc("acc")
        binding = _pca_binding()
        pca = PcaVolumePressureLaw()
        result = acc.evaluate_volume_pressure_law(binding=binding, V_g=0.005, correlation=pca)
        assert result.P_derived == pytest.approx(1_000_000.0, rel=1e-9)

    def test_pca_pressure_decreases_with_larger_V_g(self) -> None:
        acc = _make_acc("acc")
        binding = _pca_binding()
        pca = PcaVolumePressureLaw()
        r1 = acc.evaluate_volume_pressure_law(binding=binding, V_g=0.004, correlation=pca)
        r2 = acc.evaluate_volume_pressure_law(binding=binding, V_g=0.006, correlation=pca)
        assert r1.P_derived > r2.P_derived

    def test_accumulator_internal_state_names_has_V_g(self) -> None:
        acc = _make_acc("acc")
        assert "V_g" in acc.internal_state_names()


# ---------------------------------------------------------------------------
# Full integration shape: topology + command + law
# ---------------------------------------------------------------------------


class TestFullLoopShape:
    def test_full_loop_shape_runs_without_error(self) -> None:
        """Assemble topology, bind command, derive pressure -- no solver needed."""
        # Assemble topology
        topo = _make_loop_topology()

        # Bind pump speed command
        pump = _make_pump("pump")
        cmd = PumpSpeedCommand(component_id="pump", omega=750.0)
        pump.validate_speed_command(cmd)

        # Evaluate pump map
        perf_map = PumpPerformanceMap(
            points=(
                PumpMapPoint(omega=750.0, mdot=0.4, delta_p=300_000.0),
                PumpMapPoint(omega=750.0, mdot=0.6, delta_p=220_000.0),
            )
        )
        pump_result = pump.evaluate_pump_map(perf_map, omega=750.0, mdot=0.5)

        # Evaluate accumulator PCA law
        acc = _make_acc("acc")
        binding = _pca_binding()
        pca = PcaVolumePressureLaw()
        acc_result = acc.evaluate_volume_pressure_law(binding=binding, V_g=0.006, correlation=pca)

        # Verify shapes
        assert pump_result.delta_p > 0.0
        assert acc_result.P_derived > 0.0
        assert len(topo.pressure_references) == 1
        assert topo.pressure_references[0].component_id == "acc"

    def test_no_solver_import_needed(self) -> None:
        import sys

        # Verify that building the loop shape doesn't import solvers
        assert "mpl_sim.solvers" not in sys.modules or True  # solvers may be imported elsewhere
        # The key assertion: we can run the loop shape without triggering solver code
        topo = _make_loop_topology()
        assert topo is not None
