"""Pressure-reference wiring tests -- Phase 10I.

Verifies:
  PressureReferenceWiring -- construction, immutability, non-empty checks
  NetworkTopology -- accepts pressure_references parameter
  Validation:
    - exactly-one-ACCUMULATOR rule enforced when pressure_references is supplied
    - non-ACCUMULATOR kind rejected
    - unknown component id rejected
    - zero or multiple references rejected
    - None (omitted) skips validation (backward-compat)
  No pressure values stored anywhere
"""

from __future__ import annotations

import pytest

from mpl_sim.components.accumulator import AccumulatorComponent
from mpl_sim.components.base import ComponentId, ComponentKind
from mpl_sim.components.pipe import Pipe
from mpl_sim.discretization.primitives import DiscretizationMode, DiscretizationSpec
from mpl_sim.geometry.primitives import (
    AccumulatorGeometry,
    ContainmentSpec,
    PipeGeometry,
    StraightSegment,
)
from mpl_sim.network.topology import (
    ConnectionId,
    NetworkConnection,
    NetworkId,
    NetworkTopology,
    PressureReferenceWiring,
)
from mpl_sim.network.validation import validate_topology

# ---------------------------------------------------------------------------
# Minimal test fixtures
# ---------------------------------------------------------------------------


def _make_acc(name: str = "acc") -> AccumulatorComponent:
    containment = ContainmentSpec(inner_diameter=0.1, height=0.5)
    geometry = AccumulatorGeometry(V_total=0.010, containment=containment)
    return AccumulatorComponent(component_id=ComponentId(name), geometry=geometry)


def _make_pipe(name: str = "p1") -> Pipe:
    traj = StraightSegment(length=1.0, delta_z=0.0)
    geom = PipeGeometry(L=1.0, D_h=0.01, A=7.854e-5, roughness=1e-5, trajectory=traj)
    disc = DiscretizationSpec(mode=DiscretizationMode.LUMPED)
    return Pipe(component_id=ComponentId(name), geometry=geom, discretization=disc)


def _make_conn(
    cid: str,
    from_comp: str,
    from_port: str,
    to_comp: str,
    to_port: str,
) -> NetworkConnection:
    return NetworkConnection(
        connection_id=ConnectionId(cid),
        from_component=from_comp,
        from_port=from_port,
        to_component=to_comp,
        to_port=to_port,
    )


# ---------------------------------------------------------------------------
# PressureReferenceWiring construction
# ---------------------------------------------------------------------------


class TestPressureReferenceWiringConstruction:
    def test_basic_construction(self) -> None:
        w = PressureReferenceWiring(component_id="acc", port_name="fluid")
        assert w.component_id == "acc"
        assert w.port_name == "fluid"

    def test_is_immutable(self) -> None:
        w = PressureReferenceWiring(component_id="acc", port_name="fluid")
        with pytest.raises((AttributeError, TypeError)):
            w.component_id = "other"  # type: ignore[misc]

    def test_rejects_empty_component_id(self) -> None:
        with pytest.raises(ValueError, match="component_id"):
            PressureReferenceWiring(component_id="", port_name="fluid")

    def test_rejects_empty_port_name(self) -> None:
        with pytest.raises(ValueError, match="port_name"):
            PressureReferenceWiring(component_id="acc", port_name="")

    def test_carries_no_pressure_value(self) -> None:
        w = PressureReferenceWiring(component_id="acc", port_name="fluid")
        forbidden = ("P", "pressure", "p_ref", "P_sys", "p_sys", "value")
        for attr in forbidden:
            assert not hasattr(w, attr), f"Wiring must not carry {attr!r}"

    def test_equality(self) -> None:
        w1 = PressureReferenceWiring(component_id="a", port_name="fluid")
        w2 = PressureReferenceWiring(component_id="a", port_name="fluid")
        assert w1 == w2

    def test_different_ids_not_equal(self) -> None:
        w1 = PressureReferenceWiring(component_id="a", port_name="fluid")
        w2 = PressureReferenceWiring(component_id="b", port_name="fluid")
        assert w1 != w2


# ---------------------------------------------------------------------------
# validate_topology pressure-reference checks
# ---------------------------------------------------------------------------


class TestValidateTopologyPressureReference:
    def test_none_skips_validation(self) -> None:
        acc = _make_acc("acc")
        comp_map = {acc.component_id.name: acc}
        result = validate_topology(comp_map, [], pressure_references=None)
        assert result.is_valid

    def test_empty_list_is_invalid(self) -> None:
        acc = _make_acc("acc")
        comp_map = {acc.component_id.name: acc}
        result = validate_topology(comp_map, [], pressure_references=[])
        assert not result.is_valid
        assert any("Exactly one" in e for e in result.errors)

    def test_single_accumulator_reference_is_valid(self) -> None:
        acc = _make_acc("acc")
        comp_map = {acc.component_id.name: acc}
        pref = [PressureReferenceWiring(component_id="acc", port_name="fluid")]
        result = validate_topology(comp_map, [], pressure_references=pref)
        assert result.is_valid, result.errors

    def test_two_references_rejected(self) -> None:
        acc = _make_acc("acc")
        comp_map = {acc.component_id.name: acc}
        pref = [
            PressureReferenceWiring(component_id="acc", port_name="fluid"),
            PressureReferenceWiring(component_id="acc", port_name="fluid"),
        ]
        result = validate_topology(comp_map, [], pressure_references=pref)
        assert not result.is_valid
        assert any("Exactly one" in e for e in result.errors)

    def test_unknown_component_rejected(self) -> None:
        acc = _make_acc("acc")
        comp_map = {acc.component_id.name: acc}
        pref = [PressureReferenceWiring(component_id="nonexistent", port_name="fluid")]
        result = validate_topology(comp_map, [], pressure_references=pref)
        assert not result.is_valid
        assert any("nonexistent" in e for e in result.errors)

    def test_non_accumulator_component_rejected(self) -> None:
        pipe = _make_pipe("p1")
        comp_map = {pipe.component_id.name: pipe}
        pref = [PressureReferenceWiring(component_id="p1", port_name="inlet")]
        result = validate_topology(comp_map, [], pressure_references=pref)
        assert not result.is_valid
        assert any("ACCUMULATOR" in e for e in result.errors)

    def test_error_names_component_kind_when_wrong(self) -> None:
        pipe = _make_pipe("p1")
        comp_map = {pipe.component_id.name: pipe}
        pref = [PressureReferenceWiring(component_id="p1", port_name="inlet")]
        result = validate_topology(comp_map, [], pressure_references=pref)
        assert any("pipe" in e.lower() or "PIPE" in e for e in result.errors)


# ---------------------------------------------------------------------------
# NetworkTopology with pressure_references
# ---------------------------------------------------------------------------


class TestNetworkTopologyPressureReferences:
    def _make_simple_loop(self):
        """Pipe 'out' port wired to Accumulator 'fluid' port."""
        acc = _make_acc("acc")
        p1 = _make_pipe("p1")
        conn1 = _make_conn("c1", "p1", "out", "acc", "fluid")
        return [p1, acc], [conn1], acc

    def test_valid_topology_with_pressure_reference(self) -> None:
        components, connections, acc = self._make_simple_loop()
        pref = [PressureReferenceWiring(component_id="acc", port_name="fluid")]
        topo = NetworkTopology(
            network_id=NetworkId("test_net"),
            components=components,
            connections=connections,
            pressure_references=pref,
        )
        assert topo is not None

    def test_pressure_references_property_is_accessible(self) -> None:
        components, connections, acc = self._make_simple_loop()
        pref = [PressureReferenceWiring(component_id="acc", port_name="fluid")]
        topo = NetworkTopology(
            network_id=NetworkId("test_net"),
            components=components,
            connections=connections,
            pressure_references=pref,
        )
        assert len(topo.pressure_references) == 1
        assert topo.pressure_references[0].component_id == "acc"

    def test_pressure_references_property_empty_when_not_declared(self) -> None:
        components, connections, acc = self._make_simple_loop()
        topo = NetworkTopology(
            network_id=NetworkId("test_net"),
            components=components,
            connections=connections,
        )
        assert topo.pressure_references == ()

    def test_non_accumulator_reference_raises_on_construction(self) -> None:
        p1 = _make_pipe("p1")
        p2 = _make_pipe("p2")
        conn = _make_conn("c1", "p1", "out", "p2", "in")
        pref = [PressureReferenceWiring(component_id="p1", port_name="in")]
        with pytest.raises(ValueError, match="ACCUMULATOR"):
            NetworkTopology(
                network_id=NetworkId("test_net"),
                components=[p1, p2],
                connections=[conn],
                pressure_references=pref,
            )

    def test_unknown_component_reference_raises_on_construction(self) -> None:
        acc = _make_acc("acc")
        pref = [PressureReferenceWiring(component_id="ghost", port_name="fluid")]
        with pytest.raises(ValueError, match="ghost"):
            NetworkTopology(
                network_id=NetworkId("test_net"),
                components=[acc],
                connections=[],
                pressure_references=pref,
            )

    def test_no_pressure_reference_omitted_is_backward_compatible(self) -> None:
        p1 = _make_pipe("p1")
        p2 = _make_pipe("p2")
        conn = _make_conn("c1", "p1", "out", "p2", "in")
        # No pressure_references argument -- must succeed as before
        topo = NetworkTopology(
            network_id=NetworkId("test_net"),
            components=[p1, p2],
            connections=[conn],
        )
        assert topo is not None

    def test_pressure_reference_wiring_carries_no_pressure(self) -> None:
        components, connections, acc = self._make_simple_loop()
        pref = [PressureReferenceWiring(component_id="acc", port_name="fluid")]
        topo = NetworkTopology(
            network_id=NetworkId("test_net"),
            components=components,
            connections=connections,
            pressure_references=pref,
        )
        for w in topo.pressure_references:
            forbidden = ("P", "pressure", "p_ref", "P_sys", "p_sys", "value")
            for attr in forbidden:
                assert not hasattr(w, attr), f"Wiring must not carry {attr!r}"

    def test_topology_is_immutable_after_construction(self) -> None:
        components, connections, acc = self._make_simple_loop()
        pref = [PressureReferenceWiring(component_id="acc", port_name="fluid")]
        topo = NetworkTopology(
            network_id=NetworkId("test_net"),
            components=components,
            connections=connections,
            pressure_references=pref,
        )
        with pytest.raises(AttributeError):
            topo._pressure_references = ()  # type: ignore[misc]

    def test_node_for_accumulator_has_correct_kind(self) -> None:
        components, connections, acc = self._make_simple_loop()
        pref = [PressureReferenceWiring(component_id="acc", port_name="fluid")]
        topo = NetworkTopology(
            network_id=NetworkId("test_net"),
            components=components,
            connections=connections,
            pressure_references=pref,
        )
        acc_nodes = [n for n in topo.nodes() if n.component_id == "acc"]
        assert len(acc_nodes) == 1
        assert acc_nodes[0].component_kind is ComponentKind.ACCUMULATOR
