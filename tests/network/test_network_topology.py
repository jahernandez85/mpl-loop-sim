"""Network topology tests — Phase 7A.

Covers:
  Identity primitives: NetworkId, NodeId, ConnectionId.
  Topology construction: one and two Pipe components, with/without connections.
  Deterministic ordering of nodes and connections.
  Immutability: source-list mutation does not affect constructed topology.
  Immutability: NetworkTopology rejects attribute assignment after construction.
  Graph queries: isolated_components, connections_for_component, connections_for_port.
  Architecture boundaries: network modules do not import forbidden packages;
    Pipe does not import network; Ports still carry no thermodynamic values.
"""

from __future__ import annotations

import pytest

from mpl_sim.components.base import ComponentId, ComponentKind
from mpl_sim.components.pipe import Pipe
from mpl_sim.core.port import PortRole
from mpl_sim.discretization.primitives import DiscretizationMode, DiscretizationSpec
from mpl_sim.geometry.primitives import PipeGeometry, StraightSegment
from mpl_sim.network.topology import (
    ConnectionId,
    NetworkConnection,
    NetworkId,
    NetworkNode,
    NetworkTopology,
    NodeId,
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
    conn_id: str,
    from_comp: str,
    from_port: str,
    to_comp: str,
    to_port: str,
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


# ---------------------------------------------------------------------------
# NetworkId
# ---------------------------------------------------------------------------


class TestNetworkId:
    def test_construction_stores_value(self) -> None:
        nid = NetworkId(value="net_1")
        assert nid.value == "net_1"

    def test_rejects_empty_value(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            NetworkId(value="")

    def test_is_immutable(self) -> None:
        nid = NetworkId("net_1")
        with pytest.raises((AttributeError, TypeError)):
            nid.value = "other"  # type: ignore[misc]

    def test_is_hashable(self) -> None:
        nid = NetworkId("net_1")
        _ = {nid: 1}

    def test_structural_equality(self) -> None:
        assert NetworkId("a") == NetworkId("a")
        assert NetworkId("a") != NetworkId("b")

    def test_usable_as_dict_key(self) -> None:
        k = NetworkId("loop")
        d = {k: 99}
        assert d[NetworkId("loop")] == 99


# ---------------------------------------------------------------------------
# NodeId
# ---------------------------------------------------------------------------


class TestNodeId:
    def test_construction_stores_value(self) -> None:
        nid = NodeId(value="node_1")
        assert nid.value == "node_1"

    def test_rejects_empty_value(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            NodeId(value="")

    def test_is_immutable(self) -> None:
        nid = NodeId("node_1")
        with pytest.raises((AttributeError, TypeError)):
            nid.value = "x"  # type: ignore[misc]

    def test_is_hashable(self) -> None:
        _ = {NodeId("n"): 1}

    def test_structural_equality(self) -> None:
        assert NodeId("a") == NodeId("a")
        assert NodeId("a") != NodeId("b")


# ---------------------------------------------------------------------------
# ConnectionId
# ---------------------------------------------------------------------------


class TestConnectionId:
    def test_construction_stores_value(self) -> None:
        cid = ConnectionId(value="conn_1")
        assert cid.value == "conn_1"

    def test_rejects_empty_value(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ConnectionId(value="")

    def test_is_immutable(self) -> None:
        cid = ConnectionId("c1")
        with pytest.raises((AttributeError, TypeError)):
            cid.value = "c2"  # type: ignore[misc]

    def test_is_hashable(self) -> None:
        _ = {ConnectionId("c"): 1}

    def test_structural_equality(self) -> None:
        assert ConnectionId("x") == ConnectionId("x")
        assert ConnectionId("x") != ConnectionId("y")


# ---------------------------------------------------------------------------
# NetworkTopology — construction
# ---------------------------------------------------------------------------


class TestNetworkTopologyConstruction:
    def test_empty_topology(self) -> None:
        topo = NetworkTopology(
            network_id=NetworkId("empty"),
            components=[],
            connections=[],
        )
        assert len(topo.nodes()) == 0
        assert len(topo.connections()) == 0

    def test_single_pipe_no_connections(self) -> None:
        pipe = _make_pipe("p1")
        topo = NetworkTopology(
            network_id=NetworkId("single"),
            components=[pipe],
            connections=[],
        )
        assert len(topo.nodes()) == 1
        node = topo.nodes()[0]
        assert node.component_id == "p1"
        assert node.component_kind is ComponentKind.PIPE

    def test_single_pipe_node_has_correct_port_ids(self) -> None:
        pipe = _make_pipe("p1")
        topo = NetworkTopology(
            network_id=NetworkId("n"),
            components=[pipe],
            connections=[],
        )
        node = topo.nodes()[0]
        port_names = {pid.port_name for pid in node.port_ids}
        assert "in" in port_names
        assert "out" in port_names

    def test_two_pipes_one_connection(self) -> None:
        p1, p2 = _make_pipe("p1"), _make_pipe("p2")
        conn = _conn("c1", "p1", "out", "p2", "in")
        topo = NetworkTopology(
            network_id=NetworkId("two"),
            components=[p1, p2],
            connections=[conn],
        )
        assert len(topo.nodes()) == 2
        assert len(topo.connections()) == 1

    def test_network_id_is_stored(self) -> None:
        nid = NetworkId("my_network")
        topo = NetworkTopology(network_id=nid, components=[], connections=[])
        assert topo.network_id == nid

    def test_node_ids_equal_component_names(self) -> None:
        pipe = _make_pipe("pipe_alpha")
        topo = NetworkTopology(
            network_id=NetworkId("n"),
            components=[pipe],
            connections=[],
        )
        node = topo.nodes()[0]
        assert node.node_id == NodeId("pipe_alpha")
        assert node.component_id == "pipe_alpha"

    def test_returns_networknode_objects(self) -> None:
        pipe = _make_pipe("p1")
        topo = NetworkTopology(network_id=NetworkId("n"), components=[pipe], connections=[])
        for node in topo.nodes():
            assert isinstance(node, NetworkNode)


# ---------------------------------------------------------------------------
# Deterministic ordering
# ---------------------------------------------------------------------------


class TestDeterministicOrdering:
    def test_nodes_sorted_by_component_id(self) -> None:
        # Pass in reverse alphabetical order; expect sorted output.
        p_z = _make_pipe("z_pipe")
        p_a = _make_pipe("a_pipe")
        p_m = _make_pipe("m_pipe")
        topo = NetworkTopology(
            network_id=NetworkId("n"),
            components=[p_z, p_a, p_m],
            connections=[],
        )
        ids = [n.component_id for n in topo.nodes()]
        assert ids == sorted(ids)

    def test_connections_preserve_insertion_order(self) -> None:
        p1, p2, p3 = _make_pipe("p1"), _make_pipe("p2"), _make_pipe("p3")
        c_ab = _conn("c_12", "p1", "out", "p2", "in")
        c_bc = _conn("c_23", "p2", "out", "p3", "in")
        topo = NetworkTopology(
            network_id=NetworkId("chain"),
            components=[p1, p2, p3],
            connections=[c_ab, c_bc],
        )
        conn_ids = [c.connection_id.value for c in topo.connections()]
        assert conn_ids == ["c_12", "c_23"]


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


class TestImmutability:
    def test_source_component_list_mutation_does_not_affect_topology(self) -> None:
        p1, p2 = _make_pipe("p1"), _make_pipe("p2")
        comp_list = [p1]
        topo = NetworkTopology(
            network_id=NetworkId("n"),
            components=comp_list,
            connections=[],
        )
        assert len(topo.nodes()) == 1
        comp_list.append(p2)  # mutate source after construction
        assert len(topo.nodes()) == 1  # must not change

    def test_source_connection_list_mutation_does_not_affect_topology(self) -> None:
        p1, p2, p3 = _make_pipe("p1"), _make_pipe("p2"), _make_pipe("p3")
        conn_list = [_conn("c1", "p1", "out", "p2", "in")]
        topo = NetworkTopology(
            network_id=NetworkId("n"),
            components=[p1, p2, p3],
            connections=conn_list,
        )
        assert len(topo.connections()) == 1
        conn_list.append(_conn("c2", "p2", "out", "p3", "in"))
        assert len(topo.connections()) == 1  # must not change

    def test_topology_rejects_attribute_assignment(self) -> None:
        topo = NetworkTopology(network_id=NetworkId("n"), components=[], connections=[])
        with pytest.raises(AttributeError):
            topo.network_id = NetworkId("other")  # type: ignore[misc]

    def test_returned_nodes_tuple_is_immutable(self) -> None:
        pipe = _make_pipe("p1")
        topo = NetworkTopology(network_id=NetworkId("n"), components=[pipe], connections=[])
        nodes = topo.nodes()
        assert isinstance(nodes, tuple)


# ---------------------------------------------------------------------------
# Graph queries
# ---------------------------------------------------------------------------


class TestGraphQueries:
    def _three_pipe_chain(self) -> NetworkTopology:
        p1, p2, p3 = _make_pipe("p1"), _make_pipe("p2"), _make_pipe("p3")
        return NetworkTopology(
            network_id=NetworkId("chain"),
            components=[p1, p2, p3],
            connections=[
                _conn("c12", "p1", "out", "p2", "in"),
                _conn("c23", "p2", "out", "p3", "in"),
            ],
        )

    def test_connections_for_component_finds_both_sides(self) -> None:
        topo = self._three_pipe_chain()
        conns = topo.connections_for_component("p2")
        assert len(conns) == 2  # p2 appears as to in c12 and from in c23

    def test_connections_for_component_first_pipe(self) -> None:
        topo = self._three_pipe_chain()
        conns = topo.connections_for_component("p1")
        assert len(conns) == 1
        assert conns[0].connection_id.value == "c12"

    def test_connections_for_component_last_pipe(self) -> None:
        topo = self._three_pipe_chain()
        conns = topo.connections_for_component("p3")
        assert len(conns) == 1
        assert conns[0].connection_id.value == "c23"

    def test_connections_for_port_out(self) -> None:
        topo = self._three_pipe_chain()
        conns = topo.connections_for_port("p1", "out")
        assert len(conns) == 1
        assert conns[0].connection_id.value == "c12"

    def test_connections_for_port_in(self) -> None:
        topo = self._three_pipe_chain()
        conns = topo.connections_for_port("p2", "in")
        assert len(conns) == 1
        assert conns[0].connection_id.value == "c12"

    def test_connections_for_unknown_component_returns_empty(self) -> None:
        topo = self._three_pipe_chain()
        assert topo.connections_for_component("does_not_exist") == ()

    def test_isolated_components_empty_when_all_connected(self) -> None:
        topo = self._three_pipe_chain()
        assert topo.isolated_components() == ()

    def test_isolated_components_found_when_no_connections(self) -> None:
        p1, p2 = _make_pipe("p1"), _make_pipe("p2")
        topo = NetworkTopology(
            network_id=NetworkId("n"),
            components=[p1, p2],
            connections=[],
        )
        isolated = topo.isolated_components()
        assert set(isolated) == {"p1", "p2"}

    def test_isolated_components_sorted(self) -> None:
        pipes = [_make_pipe(f"pipe_{c}") for c in "zam"]
        topo = NetworkTopology(network_id=NetworkId("n"), components=pipes, connections=[])
        isolated = topo.isolated_components()
        assert list(isolated) == sorted(isolated)

    def test_partially_isolated(self) -> None:
        p1, p2, p3 = _make_pipe("p1"), _make_pipe("p2"), _make_pipe("p3")
        topo = NetworkTopology(
            network_id=NetworkId("n"),
            components=[p1, p2, p3],
            connections=[_conn("c12", "p1", "out", "p2", "in")],
        )
        assert topo.isolated_components() == ("p3",)


# ---------------------------------------------------------------------------
# Architecture boundary tests
# ---------------------------------------------------------------------------


class TestArchitectureBoundaries:
    def test_topology_module_does_not_import_coolprop(self) -> None:
        import mpl_sim.network.topology as mod

        assert mod.__file__ is not None
        for line in _import_lines(mod.__file__):
            assert "coolprop" not in line.lower(), f"Forbidden CoolProp import: {line!r}"

    def test_topology_module_does_not_import_properties(self) -> None:
        import mpl_sim.network.topology as mod

        assert mod.__file__ is not None
        for line in _import_lines(mod.__file__):
            assert "mpl_sim.properties" not in line, f"Forbidden properties import: {line!r}"

    def test_topology_module_does_not_import_correlations(self) -> None:
        import mpl_sim.network.topology as mod

        assert mod.__file__ is not None
        for line in _import_lines(mod.__file__):
            assert "mpl_sim.correlations" not in line, f"Forbidden correlations import: {line!r}"

    def test_topology_module_does_not_import_calibration(self) -> None:
        import mpl_sim.network.topology as mod

        assert mod.__file__ is not None
        for line in _import_lines(mod.__file__):
            assert "mpl_sim.calibration" not in line, f"Forbidden calibration import: {line!r}"

    def test_topology_module_does_not_import_solvers(self) -> None:
        import mpl_sim.network.topology as mod

        assert mod.__file__ is not None
        for line in _import_lines(mod.__file__):
            assert "mpl_sim.solvers" not in line, f"Forbidden solvers import: {line!r}"

    def test_validation_module_does_not_import_coolprop(self) -> None:
        import mpl_sim.network.validation as mod

        assert mod.__file__ is not None
        for line in _import_lines(mod.__file__):
            assert "coolprop" not in line.lower(), f"Forbidden CoolProp import: {line!r}"

    def test_validation_module_does_not_import_properties(self) -> None:
        import mpl_sim.network.validation as mod

        assert mod.__file__ is not None
        for line in _import_lines(mod.__file__):
            assert "mpl_sim.properties" not in line, f"Forbidden properties import: {line!r}"

    def test_validation_module_does_not_import_correlations(self) -> None:
        import mpl_sim.network.validation as mod

        assert mod.__file__ is not None
        for line in _import_lines(mod.__file__):
            assert "mpl_sim.correlations" not in line, f"Forbidden correlations import: {line!r}"

    def test_validation_module_does_not_import_calibration(self) -> None:
        import mpl_sim.network.validation as mod

        assert mod.__file__ is not None
        for line in _import_lines(mod.__file__):
            assert "mpl_sim.calibration" not in line, f"Forbidden calibration import: {line!r}"

    def test_validation_module_does_not_import_solvers(self) -> None:
        import mpl_sim.network.validation as mod

        assert mod.__file__ is not None
        for line in _import_lines(mod.__file__):
            assert "mpl_sim.solvers" not in line, f"Forbidden solvers import: {line!r}"

    def test_pipe_does_not_import_network(self) -> None:
        import mpl_sim.components.pipe as mod

        assert mod.__file__ is not None
        for line in _import_lines(mod.__file__):
            assert "mpl_sim.network" not in line, f"Pipe must not import network: {line!r}"

    def test_component_base_does_not_import_network(self) -> None:
        import mpl_sim.components.base as mod

        assert mod.__file__ is not None
        for line in _import_lines(mod.__file__):
            assert (
                "mpl_sim.network" not in line
            ), f"components/base must not import network: {line!r}"

    def test_network_construction_does_not_call_physical_methods(self) -> None:
        # If the topology called evaluate_* methods it would fail with
        # TypeError (no correlation passed). Successful construction proves
        # no physical evaluation occurred.
        pipe = _make_pipe("p1")
        topo = NetworkTopology(network_id=NetworkId("n"), components=[pipe], connections=[])
        assert len(topo.nodes()) == 1

    def test_ports_in_nodes_have_no_thermodynamic_fields(self) -> None:
        pipe = _make_pipe("p1")
        topo = NetworkTopology(network_id=NetworkId("n"), components=[pipe], connections=[])
        node = topo.nodes()[0]
        for pid in node.port_ids:
            forbidden = (
                "P",
                "h",
                "mdot",
                "rho",
                "mu",
                "quality",
                "phase",
                "Re",
                "f",
                "dP",
                "HTC",
                "Nu",
                "T",
                "x",
            )
            for attr in forbidden:
                assert not hasattr(pid, attr), f"PortId must not have attribute {attr!r}"

    def test_pipe_component_id_accessible_without_network_import(self) -> None:
        pipe = _make_pipe("my_pipe")
        # Just reading component_id — no network involvement.
        assert pipe.component_id.name == "my_pipe"
        assert pipe.kind() is ComponentKind.PIPE
        ports = pipe.ports()
        roles = {p.role for p in ports}
        assert PortRole.INLET in roles
        assert PortRole.OUTLET in roles
