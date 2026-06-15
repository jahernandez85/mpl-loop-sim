"""Component contract tests — Phase 6A.

Verifies:
  ComponentId — construction, immutability, equality, rejection of empty name.
  ComponentKind — full enumeration including all planned kinds.
  ComponentPort — construction, immutability, no thermodynamic fields.
  Component ABC — cannot be instantiated directly; module has no forbidden imports.

Import-boundary assertions:
  components/base must not import coolprop, network, solvers, or properties.
"""

from __future__ import annotations

import pytest

from mpl_sim.components.base import (
    Component,
    ComponentId,
    ComponentKind,
    ComponentPort,
)
from mpl_sim.core.port import PortId, PortRole

# ---------------------------------------------------------------------------
# ComponentId
# ---------------------------------------------------------------------------


class TestComponentId:
    def test_construction_stores_name(self) -> None:
        cid = ComponentId(name="pipe_1")
        assert cid.name == "pipe_1"

    def test_structural_equality(self) -> None:
        assert ComponentId("a") == ComponentId("a")
        assert ComponentId("a") != ComponentId("b")

    def test_is_hashable_and_usable_as_dict_key(self) -> None:
        cid = ComponentId("pipe_1")
        d = {cid: 42}
        assert d[ComponentId("pipe_1")] == 42

    def test_rejects_empty_name(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ComponentId(name="")

    def test_is_immutable(self) -> None:
        cid = ComponentId(name="pipe_1")
        with pytest.raises((AttributeError, TypeError)):
            cid.name = "other"  # type: ignore[misc]

    def test_different_names_not_equal(self) -> None:
        assert ComponentId("pump_1") != ComponentId("pump_2")

    def test_repr_contains_name(self) -> None:
        cid = ComponentId("evap_1")
        assert "evap_1" in repr(cid)


# ---------------------------------------------------------------------------
# ComponentKind
# ---------------------------------------------------------------------------


class TestComponentKind:
    def test_pipe_kind_exists(self) -> None:
        assert ComponentKind.PIPE is not None

    def test_all_planned_kinds_present(self) -> None:
        names = {k.name for k in ComponentKind}
        assert "PIPE" in names
        assert "PUMP" in names
        assert "ACCUMULATOR" in names
        assert "EVAPORATOR" in names
        assert "CONDENSER" in names
        assert "HEAT_EXCHANGER" in names

    def test_kind_values_are_strings(self) -> None:
        for kind in ComponentKind:
            assert isinstance(kind.value, str)

    def test_pipe_kind_value(self) -> None:
        assert ComponentKind.PIPE.value == "PIPE"

    def test_kind_identity_by_member(self) -> None:
        assert ComponentKind.PIPE is ComponentKind.PIPE
        assert ComponentKind.PUMP is not ComponentKind.PIPE


# ---------------------------------------------------------------------------
# ComponentPort
# ---------------------------------------------------------------------------


_DEFAULT_CID = ComponentId("pipe_1")


class TestComponentPort:
    def test_construction_minimal(self) -> None:
        port = ComponentPort(
            component_id=_DEFAULT_CID,
            port_name="in",
            role=PortRole.INLET,
        )
        assert port.component_id == _DEFAULT_CID
        assert port.port_name == "in"
        assert port.role == PortRole.INLET
        assert port.port_id is None

    def test_construction_with_port_id(self) -> None:
        pid = PortId(component_id="pipe_1", port_name="in")
        port = ComponentPort(
            component_id=_DEFAULT_CID,
            port_name="in",
            role=PortRole.INLET,
            port_id=pid,
        )
        assert port.port_id == pid

    def test_rejects_empty_port_name(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ComponentPort(
                component_id=_DEFAULT_CID,
                port_name="",
                role=PortRole.INLET,
            )

    def test_is_immutable(self) -> None:
        port = ComponentPort(
            component_id=_DEFAULT_CID,
            port_name="in",
            role=PortRole.INLET,
        )
        with pytest.raises((AttributeError, TypeError)):
            port.port_name = "out"  # type: ignore[misc]

    def test_structural_equality(self) -> None:
        p1 = ComponentPort(component_id=_DEFAULT_CID, port_name="in", role=PortRole.INLET)
        p2 = ComponentPort(component_id=_DEFAULT_CID, port_name="in", role=PortRole.INLET)
        assert p1 == p2

    def test_different_roles_not_equal(self) -> None:
        p_in = ComponentPort(component_id=_DEFAULT_CID, port_name="p", role=PortRole.INLET)
        p_out = ComponentPort(component_id=_DEFAULT_CID, port_name="p", role=PortRole.OUTLET)
        assert p_in != p_out

    def test_is_hashable(self) -> None:
        port = ComponentPort(
            component_id=_DEFAULT_CID,
            port_name="in",
            role=PortRole.INLET,
        )
        _ = {port: 1}

    def test_does_not_have_thermodynamic_fields(self) -> None:
        port = ComponentPort(
            component_id=_DEFAULT_CID,
            port_name="in",
            role=PortRole.INLET,
        )
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
            assert not hasattr(port, attr), f"ComponentPort must not have attribute {attr!r}"

    def test_outlet_role_accepted(self) -> None:
        port = ComponentPort(
            component_id=_DEFAULT_CID,
            port_name="out",
            role=PortRole.OUTLET,
        )
        assert port.role is PortRole.OUTLET

    def test_branch_role_accepted(self) -> None:
        port = ComponentPort(
            component_id=_DEFAULT_CID,
            port_name="branch_0",
            role=PortRole.BRANCH,
        )
        assert port.role is PortRole.BRANCH


# ---------------------------------------------------------------------------
# Component abstract base
# ---------------------------------------------------------------------------


def _import_lines(module_file: str) -> list[str]:
    """Return only the import-statement lines from a source file."""
    with open(module_file) as f:
        lines = f.readlines()
    return [line.strip() for line in lines if line.strip().startswith(("import ", "from "))]


class TestComponentBase:
    def test_component_is_abstract_and_cannot_be_instantiated(self) -> None:
        with pytest.raises(TypeError):
            Component()  # type: ignore[abstract]

    def test_base_module_does_not_import_solvers(self) -> None:
        import mpl_sim.components.base as base_mod

        assert base_mod.__file__ is not None
        for line in _import_lines(base_mod.__file__):
            assert "solvers" not in line, f"components/base.py has forbidden import: {line!r}"

    def test_base_module_does_not_import_network(self) -> None:
        import mpl_sim.components.base as base_mod

        assert base_mod.__file__ is not None
        for line in _import_lines(base_mod.__file__):
            assert "network" not in line, f"components/base.py has forbidden import: {line!r}"

    def test_base_module_does_not_import_coolprop(self) -> None:
        import mpl_sim.components.base as base_mod

        assert base_mod.__file__ is not None
        for line in _import_lines(base_mod.__file__):
            assert (
                "coolprop" not in line.lower()
            ), f"components/base.py has forbidden CoolProp import: {line!r}"

    def test_base_module_does_not_import_properties(self) -> None:
        import mpl_sim.components.base as base_mod

        assert base_mod.__file__ is not None
        for line in _import_lines(base_mod.__file__):
            assert (
                "mpl_sim.properties" not in line
            ), f"components/base.py must not import properties in Phase 6A: {line!r}"

    def test_base_module_does_not_import_correlations(self) -> None:
        import mpl_sim.components.base as base_mod

        assert base_mod.__file__ is not None
        for line in _import_lines(base_mod.__file__):
            assert (
                "mpl_sim.correlations" not in line
            ), f"components/base.py must not import correlations in Phase 6A: {line!r}"
