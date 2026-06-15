"""Pipe component skeleton — Phase 6A.

Defines the Pipe component: an immutable value object that holds a
PipeGeometry and DiscretizationSpec and declares inlet and outlet ports.

Phase 6A scope — strictly no physics:
- No pressure drop, friction factor, gravity, acceleration, heat transfer.
- No phase, quality, density, viscosity, Reynolds number, HTC, or Nu.
- No calls to PropertyBackend, CorrelationRegistry, or CalibrationRegistry.
- No CoolProp import anywhere in this module.
- No network or solver import.
- No thermodynamic values stored.
- No mesh or cell state (only the DiscretizationSpec is stored).

INTERFACE_SPEC.md §11.4 (Pipe row) — skeleton only; contribution contract
deferred to Phase 6B.
"""

from __future__ import annotations

from dataclasses import dataclass

from mpl_sim.components.base import Component, ComponentId, ComponentKind
from mpl_sim.core.port import Port, PortId, PortRole
from mpl_sim.discretization.primitives import DiscretizationSpec
from mpl_sim.geometry.primitives import PipeGeometry

# ---------------------------------------------------------------------------
# Pipe
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Pipe(Component):
    """Pipe component skeleton.

    An immutable component describing a single-passage pipe.  In Phase 6A
    it stores geometry and discretization declarations, exposes two ports
    (inlet and outlet), and performs no physics.

    Fields:
        component_id  : stable identity for this component
        geometry      : PipeGeometry — stored by reference; never mutated
        discretization: DiscretizationSpec — stored by reference; never mutated

    Exposed interface:
        kind()                → ComponentKind.PIPE
        inlet                 → Port (peer=None before assembly)
        outlet                → Port (peer=None before assembly)
        ports()               → (inlet, outlet) — exactly two in V1
        internal_state_names()→ () — deferred to Phase 6B

    Must NOT compute:
        pressure drop, friction gradient, gravity term, acceleration term,
        heat transfer, phase, quality, density, viscosity, Reynolds number,
        HTC, or Nu.

    Must NOT call:
        PropertyBackend, CorrelationRegistry, CalibrationRegistry, CoolProp.

    Must NOT contain:
        pressure, enthalpy, mdot, fluid state values, residuals, solver data,
        mesh nodes, or cell state beyond the DiscretizationSpec.
    """

    component_id: ComponentId
    geometry: PipeGeometry
    discretization: DiscretizationSpec

    # ------------------------------------------------------------------
    # Component contract — structural declarations (Phase 6A)
    # ------------------------------------------------------------------

    def kind(self) -> ComponentKind:
        """Returns ComponentKind.PIPE."""
        return ComponentKind.PIPE

    @property
    def inlet(self) -> Port:
        """Declared inlet port (peer=None before Network assembly)."""
        return Port(
            id=PortId(component_id=self.component_id.name, port_name="in"),
            owner=self.component_id.name,
            role=PortRole.INLET,
            peer=None,
        )

    @property
    def outlet(self) -> Port:
        """Declared outlet port (peer=None before Network assembly)."""
        return Port(
            id=PortId(component_id=self.component_id.name, port_name="out"),
            owner=self.component_id.name,
            role=PortRole.OUTLET,
            peer=None,
        )

    def ports(self) -> tuple[Port, ...]:
        """Returns (inlet, outlet) — exactly two ports in V1."""
        return (self.inlet, self.outlet)

    def internal_state_names(self) -> tuple[str, ...]:
        """Named internal states — empty in Phase 6A (physics deferred to 6B).

        Phase 6B will populate this with per-segment mass/momentum and
        optional wall-temperature state names keyed to Discretization.
        """
        return ()
