"""Pipe skeleton tests — Phase 6A.

Verifies:
  Pipe construction with PipeGeometry + DiscretizationSpec.
  Pipe is immutable (frozen dataclass).
  Pipe kind is ComponentKind.PIPE.
  Pipe exposes exactly two ports: inlet (INLET) and outlet (OUTLET).
  Inlet/outlet PortRole is consistent with existing PortRole values.
  Pipe stores geometry and discretization by reference without mutating them.
  Pipe does not expose or store mesh/cell state beyond DiscretizationSpec.
  Pipe does not compute physics (pressure drop, friction, gravity, HTC, …).
  Pipe does not call properties/correlations/calibration.
  Pipe component package does not import CoolProp, network, or solvers.

Import-boundary assertions:
  components/pipe.py must not import coolprop, network, or solvers.
"""

from __future__ import annotations

import pytest

from mpl_sim.components.base import ComponentId, ComponentKind
from mpl_sim.components.pipe import Pipe
from mpl_sim.core.port import PortRole
from mpl_sim.discretization.primitives import DiscretizationMode, DiscretizationSpec
from mpl_sim.geometry.primitives import PipeGeometry, StraightSegment

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_geometry() -> PipeGeometry:
    traj = StraightSegment(length=1.0, delta_z=0.0)
    return PipeGeometry(L=1.0, D_h=0.01, A=7.854e-5, roughness=1e-5, trajectory=traj)


def _make_discretization_lumped() -> DiscretizationSpec:
    return DiscretizationSpec(mode=DiscretizationMode.LUMPED)


def _make_discretization_uniform(n: int = 5) -> DiscretizationSpec:
    return DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=n)


def _make_pipe(name: str = "pipe_1") -> Pipe:
    return Pipe(
        component_id=ComponentId(name),
        geometry=_make_geometry(),
        discretization=_make_discretization_lumped(),
    )


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestPipeConstruction:
    def test_basic_construction(self) -> None:
        pipe = _make_pipe()
        assert pipe.component_id == ComponentId("pipe_1")

    def test_stores_geometry_by_reference(self) -> None:
        geom = _make_geometry()
        pipe = Pipe(
            component_id=ComponentId("p"),
            geometry=geom,
            discretization=_make_discretization_lumped(),
        )
        assert pipe.geometry is geom

    def test_stores_discretization_by_reference(self) -> None:
        disc = _make_discretization_lumped()
        pipe = Pipe(
            component_id=ComponentId("p"),
            geometry=_make_geometry(),
            discretization=disc,
        )
        assert pipe.discretization is disc

    def test_construction_with_uniform_discretization(self) -> None:
        disc = _make_discretization_uniform(10)
        pipe = Pipe(
            component_id=ComponentId("p"),
            geometry=_make_geometry(),
            discretization=disc,
        )
        assert pipe.discretization.mode is DiscretizationMode.UNIFORM
        assert pipe.discretization.n_cells == 10


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


class TestPipeImmutability:
    def test_component_id_not_reassignable(self) -> None:
        pipe = _make_pipe()
        with pytest.raises((AttributeError, TypeError)):
            pipe.component_id = ComponentId("other")  # type: ignore[misc]

    def test_geometry_not_reassignable(self) -> None:
        pipe = _make_pipe()
        with pytest.raises((AttributeError, TypeError)):
            pipe.geometry = _make_geometry()  # type: ignore[misc]

    def test_discretization_not_reassignable(self) -> None:
        pipe = _make_pipe()
        with pytest.raises((AttributeError, TypeError)):
            pipe.discretization = _make_discretization_lumped()  # type: ignore[misc]

    def test_new_attribute_not_settable(self) -> None:
        pipe = _make_pipe()
        with pytest.raises((AttributeError, TypeError)):
            pipe.extra = "forbidden"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Kind
# ---------------------------------------------------------------------------


class TestPipeKind:
    def test_kind_is_pipe(self) -> None:
        assert _make_pipe().kind() is ComponentKind.PIPE

    def test_kind_is_not_pump(self) -> None:
        assert _make_pipe().kind() is not ComponentKind.PUMP

    def test_kind_is_not_accumulator(self) -> None:
        assert _make_pipe().kind() is not ComponentKind.ACCUMULATOR


# ---------------------------------------------------------------------------
# Ports
# ---------------------------------------------------------------------------


class TestPipePorts:
    def test_ports_returns_exactly_two(self) -> None:
        ports = _make_pipe().ports()
        assert len(ports) == 2

    def test_ports_contains_inlet_and_outlet(self) -> None:
        pipe = _make_pipe()
        roles = {p.role for p in pipe.ports()}
        assert PortRole.INLET in roles
        assert PortRole.OUTLET in roles

    def test_inlet_role_is_inlet(self) -> None:
        assert _make_pipe().inlet.role is PortRole.INLET

    def test_outlet_role_is_outlet(self) -> None:
        assert _make_pipe().outlet.role is PortRole.OUTLET

    def test_inlet_owner_matches_component_id(self) -> None:
        pipe = _make_pipe("my_pipe")
        assert pipe.inlet.owner == "my_pipe"

    def test_outlet_owner_matches_component_id(self) -> None:
        pipe = _make_pipe("my_pipe")
        assert pipe.outlet.owner == "my_pipe"

    def test_inlet_port_name_is_in(self) -> None:
        assert _make_pipe().inlet.id.port_name == "in"

    def test_outlet_port_name_is_out(self) -> None:
        assert _make_pipe().outlet.id.port_name == "out"

    def test_inlet_peer_is_none_before_assembly(self) -> None:
        assert _make_pipe().inlet.peer is None

    def test_outlet_peer_is_none_before_assembly(self) -> None:
        assert _make_pipe().outlet.peer is None

    def test_ports_tuple_first_element_is_inlet(self) -> None:
        pipe = _make_pipe()
        ports = pipe.ports()
        assert ports[0].role is PortRole.INLET

    def test_ports_tuple_second_element_is_outlet(self) -> None:
        pipe = _make_pipe()
        ports = pipe.ports()
        assert ports[1].role is PortRole.OUTLET

    def test_port_roles_use_existing_port_role_enum(self) -> None:
        pipe = _make_pipe()
        for port in pipe.ports():
            assert isinstance(port.role, PortRole)

    def test_ports_do_not_carry_thermodynamic_values(self) -> None:
        pipe = _make_pipe()
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
        for port in pipe.ports():
            for attr in forbidden:
                assert not hasattr(port, attr), f"Port must not have attribute {attr!r}"


# ---------------------------------------------------------------------------
# Internal state — empty in Phase 6A
# ---------------------------------------------------------------------------


class TestPipeInternalState:
    def test_internal_state_names_is_empty(self) -> None:
        assert _make_pipe().internal_state_names() == ()

    def test_no_mesh_stored_on_pipe(self) -> None:
        pipe = _make_pipe()
        # Only DiscretizationSpec is stored; no precomputed grid/cells
        mesh_attrs = ("grid", "cells", "cell_spans", "uniform_grid", "mesh")
        for attr in mesh_attrs:
            assert not hasattr(
                pipe, attr
            ), f"Pipe must not store mesh/cell state; found attribute {attr!r}"


# ---------------------------------------------------------------------------
# No physics computed
# ---------------------------------------------------------------------------


class TestPipeNoPhysics:
    def test_pipe_does_not_have_pressure_drop_method(self) -> None:
        pipe = _make_pipe()
        physics_methods = (
            "pressure_drop",
            "delta_p",
            "dP",
            "friction_factor",
            "gravity_term",
            "acceleration_term",
            "heat_transfer",
            "htc",
            "nusselt",
            "reynolds",
        )
        for method in physics_methods:
            assert not hasattr(pipe, method), f"Pipe must not expose physics method {method!r}"

    def test_pipe_has_no_residual_method(self) -> None:
        pipe = _make_pipe()
        assert not hasattr(pipe, "residual")
        assert not hasattr(pipe, "residuals")

    def test_pipe_has_no_solver_reference(self) -> None:
        pipe = _make_pipe()
        assert not hasattr(pipe, "solver")
        assert not hasattr(pipe, "network")

    def test_pipe_does_not_store_pressure(self) -> None:
        pipe = _make_pipe()
        assert not hasattr(pipe, "P")
        assert not hasattr(pipe, "pressure")

    def test_pipe_does_not_store_enthalpy(self) -> None:
        pipe = _make_pipe()
        assert not hasattr(pipe, "h")
        assert not hasattr(pipe, "enthalpy")

    def test_pipe_does_not_store_mdot(self) -> None:
        pipe = _make_pipe()
        assert not hasattr(pipe, "mdot")
        assert not hasattr(pipe, "mass_flow")


# ---------------------------------------------------------------------------
# Import-boundary checks
# ---------------------------------------------------------------------------


def _import_lines_from(module_file: str) -> list[str]:
    """Return only the import-statement lines from a source file."""
    with open(module_file) as f:
        lines = f.readlines()
    return [line.strip() for line in lines if line.strip().startswith(("import ", "from "))]


class TestPipeImportBoundary:
    def _pipe_imports(self) -> list[str]:
        import mpl_sim.components.pipe as pipe_mod

        assert pipe_mod.__file__ is not None
        return _import_lines_from(pipe_mod.__file__)

    def _init_imports(self) -> list[str]:
        import mpl_sim.components as comp_pkg

        assert comp_pkg.__file__ is not None
        return _import_lines_from(comp_pkg.__file__)

    def test_pipe_module_does_not_import_coolprop(self) -> None:
        for line in self._pipe_imports():
            assert (
                "coolprop" not in line.lower()
            ), f"components/pipe.py has forbidden CoolProp import: {line!r}"

    def test_pipe_module_does_not_import_network(self) -> None:
        for line in self._pipe_imports():
            assert (
                "network" not in line
            ), f"components/pipe.py has forbidden network import: {line!r}"

    def test_pipe_module_does_not_import_solvers(self) -> None:
        for line in self._pipe_imports():
            assert (
                "solvers" not in line
            ), f"components/pipe.py has forbidden solvers import: {line!r}"

    def test_pipe_module_does_not_import_properties(self) -> None:
        for line in self._pipe_imports():
            assert (
                "mpl_sim.properties" not in line
            ), f"components/pipe.py must not import properties in Phase 6A: {line!r}"

    def test_pipe_module_does_not_import_correlations_registry(self) -> None:
        # Phase 6B: pipe.py imports from correlations.contract (Correlation,
        # CorrelationRole, etc.) — that is allowed.
        # The registry is not imported; Pipe accepts a Correlation object
        # directly so registry coupling is deferred to the call site.
        for line in self._pipe_imports():
            assert (
                "mpl_sim.correlations.registry" not in line
            ), f"components/pipe.py must not import the CorrelationRegistry: {line!r}"

    def test_components_init_does_not_import_network(self) -> None:
        for line in self._init_imports():
            assert (
                "network" not in line
            ), f"components/__init__.py has forbidden network import: {line!r}"

    def test_components_init_does_not_import_solvers(self) -> None:
        for line in self._init_imports():
            assert (
                "solvers" not in line
            ), f"components/__init__.py has forbidden solvers import: {line!r}"

    def test_components_init_does_not_import_coolprop(self) -> None:
        for line in self._init_imports():
            assert (
                "coolprop" not in line.lower()
            ), f"components/__init__.py has forbidden CoolProp import: {line!r}"


# ---------------------------------------------------------------------------
# Component protocol conformance
# ---------------------------------------------------------------------------


class TestPipeComponentProtocol:
    def test_pipe_is_instance_of_component(self) -> None:
        from mpl_sim.components.base import Component

        pipe = _make_pipe()
        assert isinstance(pipe, Component)

    def test_two_pipes_with_same_data_are_equal(self) -> None:
        geom = _make_geometry()
        disc = _make_discretization_lumped()
        cid = ComponentId("pipe_1")
        p1 = Pipe(component_id=cid, geometry=geom, discretization=disc)
        p2 = Pipe(component_id=cid, geometry=geom, discretization=disc)
        assert p1 == p2

    def test_two_pipes_with_different_ids_are_not_equal(self) -> None:
        geom = _make_geometry()
        disc = _make_discretization_lumped()
        p1 = Pipe(component_id=ComponentId("a"), geometry=geom, discretization=disc)
        p2 = Pipe(component_id=ComponentId("b"), geometry=geom, discretization=disc)
        assert p1 != p2
