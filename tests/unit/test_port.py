"""Tests for Port connectivity primitives.

Acceptance criteria (INTERFACE_SPEC §4.1, TEST_PLAN_V1 §7-handles):
- PortId is immutable, hashable, and compares by structural equality.
- PortId is usable as a dict key and set element.
- PortRole contains exactly the expected role annotations.
- Port can be constructed with and without a peer.
- Port is immutable after construction.
- Port does NOT expose P, h, mdot, state, FluidState, T, x, or rho.
- Port source does not import CoolProp, solvers, network, or component modules.
- Phase 1A tests are unaffected.
"""

import sys
from pathlib import Path

import pytest

from mpl_sim.core.port import Port, PortId, PortRole

# ---------------------------------------------------------------------------
# PortId
# ---------------------------------------------------------------------------


class TestPortId:
    def test_construction(self):
        pid = PortId(component_id="pump_1", port_name="out")
        assert pid.component_id == "pump_1"
        assert pid.port_name == "out"

    def test_structural_equality(self):
        a = PortId(component_id="pump_1", port_name="out")
        b = PortId(component_id="pump_1", port_name="out")
        assert a == b

    def test_structural_inequality_different_component(self):
        assert PortId("pump_1", "out") != PortId("pump_2", "out")

    def test_structural_inequality_different_port_name(self):
        assert PortId("pump_1", "in") != PortId("pump_1", "out")

    def test_hashable_equal_objects_have_equal_hashes(self):
        a = PortId(component_id="pipe_1", port_name="in")
        b = PortId(component_id="pipe_1", port_name="in")
        assert hash(a) == hash(b)

    def test_usable_as_dict_key(self):
        pid = PortId("pipe_1", "in")
        d = {pid: "sentinel"}
        assert d[pid] == "sentinel"

    def test_usable_in_set_deduplicates(self):
        a = PortId("c", "in")
        b = PortId("c", "in")  # same as a
        c = PortId("c", "out")  # different
        s = {a, b, c}
        assert len(s) == 2

    def test_immutable_component_id(self):
        pid = PortId(component_id="pump_1", port_name="out")
        with pytest.raises(AttributeError):
            pid.component_id = "pump_2"  # type: ignore[misc]

    def test_immutable_port_name(self):
        pid = PortId(component_id="pump_1", port_name="out")
        with pytest.raises(AttributeError):
            pid.port_name = "in"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PortRole
# ---------------------------------------------------------------------------


class TestPortRole:
    def test_inlet_exists(self):
        assert PortRole.INLET is not None

    def test_outlet_exists(self):
        assert PortRole.OUTLET is not None

    def test_branch_exists(self):
        assert PortRole.BRANCH is not None

    def test_bidirectional_exists(self):
        assert PortRole.BIDIRECTIONAL is not None

    def test_exactly_four_roles(self):
        # Guard against accidental over-expansion (IMPLEMENTATION_PLAN §21-3).
        assert len(PortRole) == 4

    def test_all_roles_are_enum_members(self):
        for role in (PortRole.INLET, PortRole.OUTLET, PortRole.BRANCH, PortRole.BIDIRECTIONAL):
            assert isinstance(role, PortRole)


# ---------------------------------------------------------------------------
# Port construction
# ---------------------------------------------------------------------------


class TestPortConstruction:
    def test_construction_without_peer(self):
        pid = PortId("pipe_1", "in")
        port = Port(id=pid, owner="pipe_1", role=PortRole.INLET)
        assert port.id == pid
        assert port.owner == "pipe_1"
        assert port.role == PortRole.INLET
        assert port.peer is None

    def test_construction_with_peer(self):
        pid_in = PortId("pipe_1", "in")
        pid_out = PortId("pump_1", "out")
        port = Port(id=pid_in, owner="pipe_1", role=PortRole.INLET, peer=pid_out)
        assert port.peer == pid_out

    def test_all_roles_are_constructible(self):
        for role in PortRole:
            pid = PortId("comp", "p")
            port = Port(id=pid, owner="comp", role=role)
            assert port.role == role

    def test_outlet_construction(self):
        pid = PortId("pipe_1", "out")
        port = Port(id=pid, owner="pipe_1", role=PortRole.OUTLET)
        assert port.role == PortRole.OUTLET

    def test_branch_construction(self):
        pid = PortId("junction_1", "branch_0")
        port = Port(id=pid, owner="junction_1", role=PortRole.BRANCH)
        assert port.role == PortRole.BRANCH


# ---------------------------------------------------------------------------
# Port immutability
# ---------------------------------------------------------------------------


class TestPortImmutability:
    def _make_port(self) -> Port:
        pid = PortId("c", "p")
        return Port(id=pid, owner="c", role=PortRole.INLET)

    def test_cannot_reassign_id(self):
        port = self._make_port()
        with pytest.raises(AttributeError):
            port.id = PortId("c2", "p2")  # type: ignore[misc]

    def test_cannot_reassign_owner(self):
        port = self._make_port()
        with pytest.raises(AttributeError):
            port.owner = "c2"  # type: ignore[misc]

    def test_cannot_reassign_role(self):
        port = self._make_port()
        with pytest.raises(AttributeError):
            port.role = PortRole.OUTLET  # type: ignore[misc]

    def test_cannot_reassign_peer(self):
        port = self._make_port()
        with pytest.raises(AttributeError):
            port.peer = PortId("other", "out")  # type: ignore[misc]

    def test_cannot_add_arbitrary_attribute(self):
        port = self._make_port()
        with pytest.raises(AttributeError):
            port.extra = "not allowed"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Port carries no thermodynamic state
# ---------------------------------------------------------------------------


class TestPortNoThermodynamicState:
    """Port must never carry thermodynamic values (INTERFACE_SPEC §4.1)."""

    FORBIDDEN_ATTRS = ("P", "h", "mdot", "state", "fluid_state", "T", "x", "rho", "mu", "k")

    def test_no_forbidden_attributes_on_instance(self):
        pid = PortId("c", "p")
        port = Port(id=pid, owner="c", role=PortRole.INLET)
        for attr in self.FORBIDDEN_ATTRS:
            assert not hasattr(port, attr), f"Port must not have attribute '{attr}'"

    def test_port_has_exactly_four_fields(self):
        """Verify Port is not growing silently beyond its four declared fields."""
        import dataclasses

        fields = {f.name for f in dataclasses.fields(Port)}
        assert fields == {"id", "owner", "role", "peer"}


# ---------------------------------------------------------------------------
# No forbidden imports in port module source
# ---------------------------------------------------------------------------


class TestPortNoCoolProp:
    """port.py must not reference CoolProp (ARCHITECTURE_MASTER §3, §19-9)."""

    def test_no_coolprop_string_in_source(self):
        import mpl_sim.core.port as port_module

        source = Path(port_module.__file__).read_text(encoding="utf-8")
        assert "CoolProp" not in source
        assert "coolprop" not in source.lower()

    def test_importing_port_does_not_load_coolprop(self):
        before = "CoolProp" in sys.modules
        import mpl_sim.core.port  # noqa: F401

        after = "CoolProp" in sys.modules
        if not before:
            assert not after, "Importing port.py must not load CoolProp"


class TestPortNoForbiddenImports:
    """port.py must not import solvers, components, or network modules."""

    def _source(self) -> str:
        import mpl_sim.core.port as port_module

        return Path(port_module.__file__).read_text(encoding="utf-8")

    def test_no_solvers_import(self):
        source = self._source()
        assert "solvers" not in source

    def test_no_components_import(self):
        source = self._source()
        assert "mpl_sim.components" not in source

    def test_no_network_import(self):
        source = self._source()
        assert "mpl_sim.network" not in source

    def test_no_properties_import(self):
        source = self._source()
        assert "mpl_sim.properties" not in source
