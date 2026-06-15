"""Network assembly tests — Phase 7C.

Covers:
  Successful assembly of single-pipe and multi-pipe topologies.
  StateLayout properties: variable kinds, ordering, size, determinism.
  PortVariableHandle allocation: P/H/MDOT per port; slots are integers.
  Connected port peer mapping via connected_port().
  Internal state allocation: empty for Pipe V1, no INTERNAL variables emitted.
  Zero-initialized SystemState: values are all zero, length matches layout.
  Architecture boundaries:
    assembly module does not import CoolProp, solvers, properties,
    correlations, or calibration.
    network __init__ does not import solvers.
    Pipe remains unaware of Network.
  Component and topology immutability: assembly does not mutate inputs.
  Assembly does not call component physical evaluation methods.
  Assembly rejects invalid topology (fails at NetworkTopology construction).
  No thermodynamic values stored on Port or ComponentPort.
"""

from __future__ import annotations

import pytest

from mpl_sim.components.base import ComponentId
from mpl_sim.components.pipe import Pipe
from mpl_sim.core.port import PortId
from mpl_sim.core.state import (
    PortVariableHandle,
    StateLayout,
    SystemState,
    VariableKind,
)
from mpl_sim.discretization.primitives import DiscretizationMode, DiscretizationSpec
from mpl_sim.geometry.primitives import PipeGeometry, StraightSegment
from mpl_sim.network.assembly import NetworkAssembly, assemble_network
from mpl_sim.network.topology import (
    ConnectionId,
    NetworkConnection,
    NetworkId,
    NetworkTopology,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_pipe(name: str = "pipe_1") -> Pipe:
    traj = StraightSegment(length=1.0, delta_z=0.0)
    geom = PipeGeometry(L=1.0, D_h=0.01, A=7.854e-5, roughness=1e-5, trajectory=traj)
    disc = DiscretizationSpec(mode=DiscretizationMode.LUMPED)
    return Pipe(component_id=ComponentId(name), geometry=geom, discretization=disc)


def _conn(
    conn_id: str, from_comp: str, from_port: str, to_comp: str, to_port: str
) -> NetworkConnection:
    return NetworkConnection(
        connection_id=ConnectionId(conn_id),
        from_component=from_comp,
        from_port=from_port,
        to_component=to_comp,
        to_port=to_port,
    )


def _import_lines(module_file: str) -> list[str]:
    with open(module_file) as f:
        lines = f.readlines()
    return [line.strip() for line in lines if line.strip().startswith(("import ", "from "))]


def _two_pipe_topology() -> tuple[NetworkTopology, Pipe, Pipe]:
    p1, p2 = _make_pipe("p1"), _make_pipe("p2")
    topo = NetworkTopology(
        network_id=NetworkId("net"),
        components=[p1, p2],
        connections=[_conn("c1", "p1", "out", "p2", "in")],
    )
    return topo, p1, p2


def _three_pipe_chain() -> tuple[NetworkTopology, list[Pipe]]:
    pipes = [_make_pipe(f"p{i}") for i in range(1, 4)]
    topo = NetworkTopology(
        network_id=NetworkId("chain"),
        components=pipes,
        connections=[
            _conn("c12", "p1", "out", "p2", "in"),
            _conn("c23", "p2", "out", "p3", "in"),
        ],
    )
    return topo, pipes


# ---------------------------------------------------------------------------
# Basic assembly
# ---------------------------------------------------------------------------


class TestBasicAssembly:
    def test_single_pipe_assembles(self) -> None:
        pipe = _make_pipe("p1")
        topo = NetworkTopology(network_id=NetworkId("n"), components=[pipe], connections=[])
        result = assemble_network(topo, [pipe])
        assert isinstance(result, NetworkAssembly)

    def test_assembly_returns_state_layout(self) -> None:
        pipe = _make_pipe("p1")
        topo = NetworkTopology(network_id=NetworkId("n"), components=[pipe], connections=[])
        result = assemble_network(topo, [pipe])
        assert isinstance(result.layout, StateLayout)

    def test_assembly_returns_system_state(self) -> None:
        pipe = _make_pipe("p1")
        topo = NetworkTopology(network_id=NetworkId("n"), components=[pipe], connections=[])
        result = assemble_network(topo, [pipe])
        assert isinstance(result.initial_state, SystemState)

    def test_assembly_stores_topology(self) -> None:
        pipe = _make_pipe("p1")
        topo = NetworkTopology(network_id=NetworkId("n"), components=[pipe], connections=[])
        result = assemble_network(topo, [pipe])
        assert result.topology is topo

    def test_empty_topology_assembles(self) -> None:
        topo = NetworkTopology(network_id=NetworkId("empty"), components=[], connections=[])
        result = assemble_network(topo)
        assert len(result.layout) == 0
        assert len(result.initial_state) == 0

    def test_without_components_arg_assembles(self) -> None:
        pipe = _make_pipe("p1")
        topo = NetworkTopology(network_id=NetworkId("n"), components=[pipe], connections=[])
        result = assemble_network(topo)  # no components arg
        assert isinstance(result.layout, StateLayout)


# ---------------------------------------------------------------------------
# Variable allocation
# ---------------------------------------------------------------------------


class TestVariableAllocation:
    def test_single_pipe_allocates_six_variables(self) -> None:
        # Pipe has 2 ports ("in", "out"); 3 variables each → 6 total.
        pipe = _make_pipe("p1")
        topo = NetworkTopology(network_id=NetworkId("n"), components=[pipe], connections=[])
        result = assemble_network(topo, [pipe])
        assert len(result.layout) == 6

    def test_two_pipe_topology_allocates_twelve_variables(self) -> None:
        topo, p1, p2 = _two_pipe_topology()
        result = assemble_network(topo, [p1, p2])
        # 2 pipes × 2 ports × 3 variables = 12
        assert len(result.layout) == 12

    def test_variables_use_p_h_mdot_kinds(self) -> None:
        pipe = _make_pipe("p1")
        topo = NetworkTopology(network_id=NetworkId("n"), components=[pipe], connections=[])
        result = assemble_network(topo, [pipe])
        kinds = {var.kind for var in result.layout}
        assert VariableKind.P in kinds
        assert VariableKind.H in kinds
        assert VariableKind.MDOT in kinds

    def test_no_internal_variables_for_pipe(self) -> None:
        pipe = _make_pipe("p1")
        topo = NetworkTopology(network_id=NetworkId("n"), components=[pipe], connections=[])
        result = assemble_network(topo, [pipe])
        internal = [v for v in result.layout if v.kind is VariableKind.INTERNAL]
        assert internal == []

    def test_port_variables_owner_matches_component_id(self) -> None:
        pipe = _make_pipe("my_pipe")
        topo = NetworkTopology(network_id=NetworkId("n"), components=[pipe], connections=[])
        result = assemble_network(topo, [pipe])
        for var in result.layout:
            assert var.owner == "my_pipe"

    def test_port_variable_local_names_are_port_names(self) -> None:
        pipe = _make_pipe("p1")
        topo = NetworkTopology(network_id=NetworkId("n"), components=[pipe], connections=[])
        result = assemble_network(topo, [pipe])
        local_names = {var.local_name for var in result.layout}
        assert "in" in local_names
        assert "out" in local_names

    def test_initial_state_length_matches_layout(self) -> None:
        topo, p1, p2 = _two_pipe_topology()
        result = assemble_network(topo, [p1, p2])
        assert len(result.initial_state) == len(result.layout)

    def test_initial_state_is_zero_initialized(self) -> None:
        topo, p1, p2 = _two_pipe_topology()
        result = assemble_network(topo, [p1, p2])
        assert (result.initial_state.values == 0.0).all()


# ---------------------------------------------------------------------------
# Port variable handles
# ---------------------------------------------------------------------------


class TestPortVariableHandles:
    def test_port_handle_returns_port_variable_handle(self) -> None:
        pipe = _make_pipe("p1")
        topo = NetworkTopology(network_id=NetworkId("n"), components=[pipe], connections=[])
        result = assemble_network(topo, [pipe])
        pid = PortId(component_id="p1", port_name="in")
        handle = result.port_handle(pid)
        assert isinstance(handle, PortVariableHandle)

    def test_port_handle_port_field_matches_port_id(self) -> None:
        pipe = _make_pipe("p1")
        topo = NetworkTopology(network_id=NetworkId("n"), components=[pipe], connections=[])
        result = assemble_network(topo, [pipe])
        pid = PortId(component_id="p1", port_name="in")
        handle = result.port_handle(pid)
        assert handle.port == pid

    def test_port_handle_slots_are_integers(self) -> None:
        pipe = _make_pipe("p1")
        topo = NetworkTopology(network_id=NetworkId("n"), components=[pipe], connections=[])
        result = assemble_network(topo, [pipe])
        pid = PortId(component_id="p1", port_name="in")
        handle = result.port_handle(pid)
        assert isinstance(handle.slot_P, int)
        assert isinstance(handle.slot_h, int)
        assert isinstance(handle.slot_mdot, int)

    def test_all_ports_have_distinct_slots(self) -> None:
        topo, p1, p2 = _two_pipe_topology()
        result = assemble_network(topo, [p1, p2])
        all_slots: list[int] = []
        for node in topo.nodes():
            for pid in node.port_ids:
                h = result.port_handle(pid)
                all_slots.extend([h.slot_P, h.slot_h, h.slot_mdot])
        assert len(all_slots) == len(set(all_slots)), "All slot indices must be distinct"

    def test_port_handle_via_layout_matches_assembly_method(self) -> None:
        pipe = _make_pipe("p1")
        topo = NetworkTopology(network_id=NetworkId("n"), components=[pipe], connections=[])
        result = assemble_network(topo, [pipe])
        pid = PortId(component_id="p1", port_name="out")
        assert result.port_handle(pid) == result.layout.port_handle(pid)

    def test_unknown_port_raises_key_error(self) -> None:
        pipe = _make_pipe("p1")
        topo = NetworkTopology(network_id=NetworkId("n"), components=[pipe], connections=[])
        result = assemble_network(topo, [pipe])
        bad = PortId(component_id="does_not_exist", port_name="in")
        with pytest.raises(KeyError):
            result.port_handle(bad)


# ---------------------------------------------------------------------------
# Connected port peer mapping
# ---------------------------------------------------------------------------


class TestConnectedPortPeers:
    def test_connected_port_returns_peer(self) -> None:
        topo, p1, p2 = _two_pipe_topology()
        result = assemble_network(topo, [p1, p2])
        from_pid = PortId(component_id="p1", port_name="out")
        to_pid = PortId(component_id="p2", port_name="in")
        assert result.connected_port(from_pid) == to_pid

    def test_peer_mapping_is_bidirectional(self) -> None:
        topo, p1, p2 = _two_pipe_topology()
        result = assemble_network(topo, [p1, p2])
        from_pid = PortId(component_id="p1", port_name="out")
        to_pid = PortId(component_id="p2", port_name="in")
        assert result.connected_port(to_pid) == from_pid

    def test_unconnected_port_returns_none(self) -> None:
        topo, p1, p2 = _two_pipe_topology()
        result = assemble_network(topo, [p1, p2])
        # p1.in and p2.out are unconnected in the two-pipe topology.
        assert result.connected_port(PortId("p1", "in")) is None
        assert result.connected_port(PortId("p2", "out")) is None

    def test_isolated_pipe_ports_all_none(self) -> None:
        pipe = _make_pipe("solo")
        topo = NetworkTopology(network_id=NetworkId("n"), components=[pipe], connections=[])
        result = assemble_network(topo, [pipe])
        for node in topo.nodes():
            for pid in node.port_ids:
                assert result.connected_port(pid) is None

    def test_connected_ports_have_independent_variables(self) -> None:
        # V1 mapping: each port gets its own P/H/MDOT; continuity is Phase 8.
        topo, p1, p2 = _two_pipe_topology()
        result = assemble_network(topo, [p1, p2])
        h_from = result.port_handle(PortId("p1", "out"))
        h_to = result.port_handle(PortId("p2", "in"))
        # Slots must differ — separate state variables per port.
        assert h_from.slot_P != h_to.slot_P
        assert h_from.slot_h != h_to.slot_h
        assert h_from.slot_mdot != h_to.slot_mdot

    def test_three_pipe_chain_all_peers_correct(self) -> None:
        topo, _ = _three_pipe_chain()
        result = assemble_network(topo)
        assert result.connected_port(PortId("p1", "out")) == PortId("p2", "in")
        assert result.connected_port(PortId("p2", "in")) == PortId("p1", "out")
        assert result.connected_port(PortId("p2", "out")) == PortId("p3", "in")
        assert result.connected_port(PortId("p3", "in")) == PortId("p2", "out")


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_repeated_assembly_identical_layout_length(self) -> None:
        topo, p1, p2 = _two_pipe_topology()
        r1 = assemble_network(topo, [p1, p2])
        r2 = assemble_network(topo, [p1, p2])
        assert len(r1.layout) == len(r2.layout)

    def test_repeated_assembly_identical_variable_order(self) -> None:
        topo, p1, p2 = _two_pipe_topology()
        r1 = assemble_network(topo, [p1, p2])
        r2 = assemble_network(topo, [p1, p2])
        vars1 = list(r1.layout)
        vars2 = list(r2.layout)
        assert vars1 == vars2

    def test_repeated_assembly_identical_port_handle_slots(self) -> None:
        topo, p1, p2 = _two_pipe_topology()
        r1 = assemble_network(topo, [p1, p2])
        r2 = assemble_network(topo, [p1, p2])
        pid = PortId("p1", "in")
        h1 = r1.port_handle(pid)
        h2 = r2.port_handle(pid)
        assert h1 == h2

    def test_node_order_independent_of_insertion_order(self) -> None:
        # Insert in reverse alphabetical order; expect sorted output.
        pipes = [_make_pipe("z_pipe"), _make_pipe("a_pipe"), _make_pipe("m_pipe")]
        topo = NetworkTopology(network_id=NetworkId("n"), components=pipes, connections=[])
        result = assemble_network(topo, pipes)
        # First 6 vars should belong to "a_pipe" (alphabetically first node).
        owners = [v.owner for v in result.layout]
        assert owners[:6] == ["a_pipe"] * 6

    def test_port_variable_order_within_node(self) -> None:
        # Within a node, ports are sorted by name: "in" < "out".
        # Variable order within a port is P, H, MDOT.
        pipe = _make_pipe("p1")
        topo = NetworkTopology(network_id=NetworkId("n"), components=[pipe], connections=[])
        result = assemble_network(topo, [pipe])
        vars_ = list(result.layout)
        # Slots 0,1,2 → "in" port; slots 3,4,5 → "out" port.
        assert vars_[0].local_name == "in" and vars_[0].kind == VariableKind.P
        assert vars_[1].local_name == "in" and vars_[1].kind == VariableKind.H
        assert vars_[2].local_name == "in" and vars_[2].kind == VariableKind.MDOT
        assert vars_[3].local_name == "out" and vars_[3].kind == VariableKind.P
        assert vars_[4].local_name == "out" and vars_[4].kind == VariableKind.H
        assert vars_[5].local_name == "out" and vars_[5].kind == VariableKind.MDOT


# ---------------------------------------------------------------------------
# Immutability — assembly must not mutate inputs
# ---------------------------------------------------------------------------


class TestImmutability:
    def test_assembly_does_not_mutate_pipe_component(self) -> None:
        pipe = _make_pipe("p1")
        cid_before = pipe.component_id
        kind_before = pipe.kind()
        ports_before = pipe.ports()
        topo = NetworkTopology(network_id=NetworkId("n"), components=[pipe], connections=[])
        assemble_network(topo, [pipe])
        assert pipe.component_id == cid_before
        assert pipe.kind() == kind_before
        assert pipe.ports() == ports_before

    def test_assembly_does_not_mutate_topology_node_count(self) -> None:
        topo, p1, p2 = _two_pipe_topology()
        node_count_before = len(topo.nodes())
        assemble_network(topo, [p1, p2])
        assert len(topo.nodes()) == node_count_before

    def test_assembly_does_not_mutate_topology_connection_count(self) -> None:
        topo, p1, p2 = _two_pipe_topology()
        conn_count_before = len(topo.connections())
        assemble_network(topo, [p1, p2])
        assert len(topo.connections()) == conn_count_before

    def test_initial_state_is_independent_copy(self) -> None:
        pipe = _make_pipe("p1")
        topo = NetworkTopology(network_id=NetworkId("n"), components=[pipe], connections=[])
        result = assemble_network(topo, [pipe])
        # Modifying initial_state does not affect a second assembly.
        result.initial_state.set_by_index(0, 999.0)
        result2 = assemble_network(topo, [pipe])
        assert result2.initial_state.get_by_index(0) == 0.0


# ---------------------------------------------------------------------------
# No thermodynamic values on Port / ComponentPort
# ---------------------------------------------------------------------------


class TestNoThermodynamicValues:
    _FORBIDDEN = (
        "P",
        "h",
        "mdot",
        "rho",
        "mu",
        "T",
        "x",
        "quality",
        "phase",
        "Re",
        "f",
        "dP",
        "HTC",
        "Nu",
    )

    def test_port_objects_carry_no_thermodynamic_fields(self) -> None:
        pipe = _make_pipe("p1")
        for port in pipe.ports():
            for attr in self._FORBIDDEN:
                assert not hasattr(port, attr), f"Port must not have attribute {attr!r}"

    def test_port_id_carries_no_thermodynamic_fields(self) -> None:
        pid = PortId(component_id="p1", port_name="in")
        for attr in self._FORBIDDEN:
            assert not hasattr(pid, attr), f"PortId must not have attribute {attr!r}"

    def test_port_variable_handle_carries_no_thermodynamic_fields(self) -> None:
        pipe = _make_pipe("p1")
        topo = NetworkTopology(network_id=NetworkId("n"), components=[pipe], connections=[])
        result = assemble_network(topo, [pipe])
        handle = result.port_handle(PortId("p1", "in"))
        for attr in self._FORBIDDEN:
            assert not hasattr(handle, attr), f"PortVariableHandle must not have attribute {attr!r}"


# ---------------------------------------------------------------------------
# Rejection of invalid topology
# ---------------------------------------------------------------------------


class TestInvalidTopologyRejected:
    def test_unknown_component_in_connection_fails(self) -> None:
        pipe = _make_pipe("p1")
        bad_conn = _conn("c1", "p1", "out", "missing", "in")
        with pytest.raises(ValueError, match="Invalid topology"):
            NetworkTopology(
                network_id=NetworkId("n"),
                components=[pipe],
                connections=[bad_conn],
            )

    def test_self_connection_fails(self) -> None:
        pipe = _make_pipe("p1")
        bad_conn = _conn("c1", "p1", "out", "p1", "in")
        with pytest.raises(ValueError, match="Invalid topology"):
            NetworkTopology(
                network_id=NetworkId("n"),
                components=[pipe],
                connections=[bad_conn],
            )

    def test_incompatible_roles_fail(self) -> None:
        p1, p2 = _make_pipe("p1"), _make_pipe("p2")
        bad_conn = _conn("c1", "p1", "in", "p2", "in")  # INLET ↔ INLET
        with pytest.raises(ValueError, match="Invalid topology"):
            NetworkTopology(
                network_id=NetworkId("n"),
                components=[p1, p2],
                connections=[bad_conn],
            )

    def test_duplicate_component_ids_fail(self) -> None:
        p1a, p1b = _make_pipe("p1"), _make_pipe("p1")
        with pytest.raises(ValueError, match="Duplicate component id"):
            NetworkTopology(
                network_id=NetworkId("n"),
                components=[p1a, p1b],
                connections=[],
            )


# ---------------------------------------------------------------------------
# Architecture boundaries
# ---------------------------------------------------------------------------


class TestArchitectureBoundaries:
    def test_assembly_module_does_not_import_coolprop(self) -> None:
        import mpl_sim.network.assembly as mod

        assert mod.__file__ is not None
        for line in _import_lines(mod.__file__):
            assert "coolprop" not in line.lower(), f"Forbidden CoolProp import: {line!r}"

    def test_assembly_module_does_not_import_solvers(self) -> None:
        import mpl_sim.network.assembly as mod

        assert mod.__file__ is not None
        for line in _import_lines(mod.__file__):
            assert "mpl_sim.solvers" not in line, f"Forbidden solvers import: {line!r}"

    def test_assembly_module_does_not_import_properties(self) -> None:
        import mpl_sim.network.assembly as mod

        assert mod.__file__ is not None
        for line in _import_lines(mod.__file__):
            assert "mpl_sim.properties" not in line, f"Forbidden properties import: {line!r}"

    def test_assembly_module_does_not_import_correlations(self) -> None:
        import mpl_sim.network.assembly as mod

        assert mod.__file__ is not None
        for line in _import_lines(mod.__file__):
            assert "mpl_sim.correlations" not in line, f"Forbidden correlations import: {line!r}"

    def test_assembly_module_does_not_import_calibration(self) -> None:
        import mpl_sim.network.assembly as mod

        assert mod.__file__ is not None
        for line in _import_lines(mod.__file__):
            assert "mpl_sim.calibration" not in line, f"Forbidden calibration import: {line!r}"

    def test_network_init_does_not_import_solvers(self) -> None:
        import mpl_sim.network as mod

        assert mod.__file__ is not None
        for line in _import_lines(mod.__file__):
            assert "mpl_sim.solvers" not in line, f"Forbidden solvers import: {line!r}"

    def test_pipe_does_not_import_network(self) -> None:
        import mpl_sim.components.pipe as mod

        assert mod.__file__ is not None
        for line in _import_lines(mod.__file__):
            assert "mpl_sim.network" not in line, f"Pipe must not import network: {line!r}"

    def test_assembly_does_not_call_physical_evaluation_methods(self) -> None:
        # evaluate_single_phase_friction / evaluate_gravity_pressure / etc.
        # require a Correlation argument; if assembly called any of them it
        # would raise TypeError.  Successful completion proves none were called.
        pipe = _make_pipe("p1")
        topo = NetworkTopology(network_id=NetworkId("n"), components=[pipe], connections=[])
        result = assemble_network(topo, [pipe])
        assert len(result.layout) == 6  # normal completion; no exception raised

    def test_assembly_does_not_import_property_backend(self) -> None:
        import mpl_sim.network.assembly as mod

        assert mod.__file__ is not None
        for line in _import_lines(mod.__file__):
            assert "PropertyBackend" not in line, f"Forbidden PropertyBackend import: {line!r}"

    def test_network_assembly_accessible_from_package(self) -> None:
        import mpl_sim.network as net_pkg

        assert hasattr(net_pkg, "NetworkAssembly")
        assert hasattr(net_pkg, "assemble_network")
