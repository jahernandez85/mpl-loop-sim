"""Network validation tests — Phase 7B.

Covers:
  NetworkValidationResult — immutability and fields.
  validate_topology — all structural checks:
    duplicate connection ids rejected;
    unknown component in connection rejected;
    unknown port in connection rejected;
    incompatible port roles rejected (INLET+INLET, OUTLET+OUTLET);
    self-connection rejected;
    valid OUTLET→INLET pipe-to-pipe connection accepted;
    one-to-one connectivity enforced (port connected twice rejected);
    connection lookup by component and port.

  NetworkTopology construction (integration):
    duplicate component ids rejected at construction;
    invalid connections propagate as ValueError.
"""

from __future__ import annotations

import pytest

from mpl_sim.components.base import ComponentId
from mpl_sim.components.pipe import Pipe
from mpl_sim.discretization.primitives import DiscretizationMode, DiscretizationSpec
from mpl_sim.geometry.primitives import PipeGeometry, StraightSegment
from mpl_sim.network.topology import (
    ConnectionId,
    NetworkConnection,
    NetworkId,
    NetworkTopology,
)
from mpl_sim.network.validation import NetworkValidationResult, validate_topology

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


def _comp_map(*pipes: Pipe) -> dict[str, Pipe]:
    return {p.component_id.name: p for p in pipes}


# ---------------------------------------------------------------------------
# NetworkValidationResult
# ---------------------------------------------------------------------------


class TestNetworkValidationResult:
    def test_valid_result(self) -> None:
        r = NetworkValidationResult(is_valid=True, errors=())
        assert r.is_valid is True
        assert r.errors == ()

    def test_invalid_result_stores_errors(self) -> None:
        r = NetworkValidationResult(is_valid=False, errors=("err1", "err2"))
        assert r.is_valid is False
        assert "err1" in r.errors
        assert "err2" in r.errors

    def test_is_immutable(self) -> None:
        r = NetworkValidationResult(is_valid=True, errors=())
        with pytest.raises((AttributeError, TypeError)):
            r.is_valid = False  # type: ignore[misc]

    def test_is_hashable(self) -> None:
        r = NetworkValidationResult(is_valid=True, errors=())
        _ = {r: 1}


# ---------------------------------------------------------------------------
# validate_topology — valid cases
# ---------------------------------------------------------------------------


class TestValidateTopologyValid:
    def test_empty_topology_is_valid(self) -> None:
        result = validate_topology({}, [])
        assert result.is_valid
        assert result.errors == ()

    def test_single_pipe_no_connections_is_valid(self) -> None:
        p = _make_pipe("p1")
        result = validate_topology(_comp_map(p), [])
        assert result.is_valid

    def test_valid_outlet_to_inlet_connection(self) -> None:
        p1, p2 = _make_pipe("p1"), _make_pipe("p2")
        conn = _conn("c1", "p1", "out", "p2", "in")
        result = validate_topology(_comp_map(p1, p2), [conn])
        assert result.is_valid
        assert result.errors == ()

    def test_two_connections_in_chain(self) -> None:
        p1, p2, p3 = _make_pipe("p1"), _make_pipe("p2"), _make_pipe("p3")
        conns = [
            _conn("c12", "p1", "out", "p2", "in"),
            _conn("c23", "p2", "out", "p3", "in"),
        ]
        result = validate_topology(_comp_map(p1, p2, p3), conns)
        assert result.is_valid

    def test_connection_with_label_is_valid(self) -> None:
        p1, p2 = _make_pipe("p1"), _make_pipe("p2")
        conn = NetworkConnection(
            connection_id=ConnectionId("c1"),
            from_component="p1",
            from_port="out",
            to_component="p2",
            to_port="in",
            label="main branch",
        )
        result = validate_topology(_comp_map(p1, p2), [conn])
        assert result.is_valid


# ---------------------------------------------------------------------------
# validate_topology — invalid: duplicate connection id
# ---------------------------------------------------------------------------


class TestDuplicateConnectionId:
    def test_duplicate_connection_id_produces_error(self) -> None:
        p1, p2, p3 = _make_pipe("p1"), _make_pipe("p2"), _make_pipe("p3")
        conns = [
            _conn("same_id", "p1", "out", "p2", "in"),
            _conn("same_id", "p2", "out", "p3", "in"),
        ]
        result = validate_topology(_comp_map(p1, p2, p3), conns)
        assert not result.is_valid
        assert any("same_id" in e for e in result.errors)

    def test_unique_connection_ids_ok(self) -> None:
        p1, p2 = _make_pipe("p1"), _make_pipe("p2")
        conns = [_conn("c1", "p1", "out", "p2", "in")]
        result = validate_topology(_comp_map(p1, p2), conns)
        assert result.is_valid


# ---------------------------------------------------------------------------
# validate_topology — invalid: unknown component
# ---------------------------------------------------------------------------


class TestUnknownComponent:
    def test_unknown_from_component(self) -> None:
        p2 = _make_pipe("p2")
        conn = _conn("c1", "ghost", "out", "p2", "in")
        result = validate_topology(_comp_map(p2), [conn])
        assert not result.is_valid
        assert any("ghost" in e for e in result.errors)

    def test_unknown_to_component(self) -> None:
        p1 = _make_pipe("p1")
        conn = _conn("c1", "p1", "out", "nowhere", "in")
        result = validate_topology(_comp_map(p1), [conn])
        assert not result.is_valid
        assert any("nowhere" in e for e in result.errors)

    def test_both_unknown_components(self) -> None:
        conn = _conn("c1", "ghost_a", "out", "ghost_b", "in")
        result = validate_topology({}, [conn])
        assert not result.is_valid
        assert len(result.errors) >= 1  # at least the from-component error


# ---------------------------------------------------------------------------
# validate_topology — invalid: unknown port
# ---------------------------------------------------------------------------


class TestUnknownPort:
    def test_unknown_from_port(self) -> None:
        p1, p2 = _make_pipe("p1"), _make_pipe("p2")
        conn = _conn("c1", "p1", "bad_port", "p2", "in")
        result = validate_topology(_comp_map(p1, p2), [conn])
        assert not result.is_valid
        assert any("bad_port" in e for e in result.errors)

    def test_unknown_to_port(self) -> None:
        p1, p2 = _make_pipe("p1"), _make_pipe("p2")
        conn = _conn("c1", "p1", "out", "p2", "bad_port")
        result = validate_topology(_comp_map(p1, p2), [conn])
        assert not result.is_valid
        assert any("bad_port" in e for e in result.errors)

    def test_both_ports_unknown(self) -> None:
        p1, p2 = _make_pipe("p1"), _make_pipe("p2")
        conn = _conn("c1", "p1", "bad_a", "p2", "bad_b")
        result = validate_topology(_comp_map(p1, p2), [conn])
        assert not result.is_valid
        assert len(result.errors) >= 2


# ---------------------------------------------------------------------------
# validate_topology — invalid: incompatible port roles
# ---------------------------------------------------------------------------


class TestIncompatiblePortRoles:
    def test_inlet_to_inlet_rejected(self) -> None:
        p1, p2 = _make_pipe("p1"), _make_pipe("p2")
        # Pipe ports: "in" = INLET, "out" = OUTLET.
        conn = _conn("c1", "p1", "in", "p2", "in")
        result = validate_topology(_comp_map(p1, p2), [conn])
        assert not result.is_valid
        assert any("INLET" in e or "incompatible" in e.lower() for e in result.errors)

    def test_outlet_to_outlet_rejected(self) -> None:
        p1, p2 = _make_pipe("p1"), _make_pipe("p2")
        conn = _conn("c1", "p1", "out", "p2", "out")
        result = validate_topology(_comp_map(p1, p2), [conn])
        assert not result.is_valid
        assert any("OUTLET" in e or "incompatible" in e.lower() for e in result.errors)

    def test_outlet_to_inlet_accepted(self) -> None:
        p1, p2 = _make_pipe("p1"), _make_pipe("p2")
        conn = _conn("c1", "p1", "out", "p2", "in")
        result = validate_topology(_comp_map(p1, p2), [conn])
        assert result.is_valid

    def test_inlet_to_outlet_accepted(self) -> None:
        p1, p2 = _make_pipe("p1"), _make_pipe("p2")
        conn = _conn("c1", "p1", "in", "p2", "out")
        result = validate_topology(_comp_map(p1, p2), [conn])
        assert result.is_valid


# ---------------------------------------------------------------------------
# validate_topology — invalid: self-connection
# ---------------------------------------------------------------------------


class TestSelfConnection:
    def test_self_connection_rejected(self) -> None:
        p1 = _make_pipe("p1")
        conn = _conn("c1", "p1", "out", "p1", "in")
        result = validate_topology(_comp_map(p1), [conn])
        assert not result.is_valid
        assert any("self" in e.lower() or "p1" in e for e in result.errors)

    def test_self_connection_different_port_rejected(self) -> None:
        p1 = _make_pipe("p1")
        conn = _conn("c1", "p1", "in", "p1", "out")
        result = validate_topology(_comp_map(p1), [conn])
        assert not result.is_valid


# ---------------------------------------------------------------------------
# validate_topology — invalid: one-to-one connectivity
# ---------------------------------------------------------------------------


class TestOneToOneConnectivity:
    def test_port_connected_twice_rejected(self) -> None:
        # p2.in connected from both p1 and p3 (two connections to same port).
        p1, p2, p3 = _make_pipe("p1"), _make_pipe("p2"), _make_pipe("p3")
        conns = [
            _conn("c1", "p1", "out", "p2", "in"),
            _conn("c2", "p3", "out", "p2", "in"),  # p2.in connected twice
        ]
        result = validate_topology(_comp_map(p1, p2, p3), conns)
        assert not result.is_valid
        assert any("p2" in e and "in" in e for e in result.errors)

    def test_each_port_connected_once_is_valid(self) -> None:
        p1, p2 = _make_pipe("p1"), _make_pipe("p2")
        conns = [_conn("c1", "p1", "out", "p2", "in")]
        result = validate_topology(_comp_map(p1, p2), conns)
        assert result.is_valid


# ---------------------------------------------------------------------------
# NetworkTopology construction — integration validation checks
# ---------------------------------------------------------------------------


class TestNetworkTopologyValidationIntegration:
    def test_duplicate_component_id_raises(self) -> None:
        p1a = _make_pipe("p1")
        p1b = _make_pipe("p1")  # same name
        with pytest.raises(ValueError, match="[Dd]uplicate"):
            NetworkTopology(
                network_id=NetworkId("n"),
                components=[p1a, p1b],
                connections=[],
            )

    def test_unknown_component_in_connection_raises(self) -> None:
        p1 = _make_pipe("p1")
        conn = _conn("c1", "p1", "out", "ghost", "in")
        with pytest.raises(ValueError):
            NetworkTopology(
                network_id=NetworkId("n"),
                components=[p1],
                connections=[conn],
            )

    def test_unknown_port_in_connection_raises(self) -> None:
        p1, p2 = _make_pipe("p1"), _make_pipe("p2")
        conn = _conn("c1", "p1", "no_such_port", "p2", "in")
        with pytest.raises(ValueError):
            NetworkTopology(
                network_id=NetworkId("n"),
                components=[p1, p2],
                connections=[conn],
            )

    def test_incompatible_roles_raises(self) -> None:
        p1, p2 = _make_pipe("p1"), _make_pipe("p2")
        conn = _conn("c1", "p1", "in", "p2", "in")  # INLET+INLET
        with pytest.raises(ValueError):
            NetworkTopology(
                network_id=NetworkId("n"),
                components=[p1, p2],
                connections=[conn],
            )

    def test_self_connection_raises(self) -> None:
        p1 = _make_pipe("p1")
        conn = _conn("c1", "p1", "out", "p1", "in")
        with pytest.raises(ValueError):
            NetworkTopology(
                network_id=NetworkId("n"),
                components=[p1],
                connections=[conn],
            )

    def test_valid_two_pipe_connection_constructs(self) -> None:
        p1, p2 = _make_pipe("p1"), _make_pipe("p2")
        conn = _conn("c1", "p1", "out", "p2", "in")
        topo = NetworkTopology(
            network_id=NetworkId("ok"),
            components=[p1, p2],
            connections=[conn],
        )
        assert len(topo.nodes()) == 2
        assert len(topo.connections()) == 1

    def test_connection_lookup_by_component(self) -> None:
        p1, p2 = _make_pipe("p1"), _make_pipe("p2")
        conn = _conn("c1", "p1", "out", "p2", "in")
        topo = NetworkTopology(
            network_id=NetworkId("n"),
            components=[p1, p2],
            connections=[conn],
        )
        assert len(topo.connections_for_component("p1")) == 1
        assert len(topo.connections_for_component("p2")) == 1
        assert topo.connections_for_component("p1")[0].connection_id.value == "c1"

    def test_connection_lookup_by_port(self) -> None:
        p1, p2 = _make_pipe("p1"), _make_pipe("p2")
        conn = _conn("c1", "p1", "out", "p2", "in")
        topo = NetworkTopology(
            network_id=NetworkId("n"),
            components=[p1, p2],
            connections=[conn],
        )
        assert len(topo.connections_for_port("p1", "out")) == 1
        assert len(topo.connections_for_port("p2", "in")) == 1
        assert len(topo.connections_for_port("p1", "in")) == 0
        assert len(topo.connections_for_port("p2", "out")) == 0
