"""Accumulator component — Phase 10D.

Defines the Accumulator component: an immutable value object that stores
AccumulatorGeometry (containment only), declares one bidirectional fluid port,
and exposes evaluate_pressure_reference for the prescribed pressure-reference law.

Phase 10C adds:
- AccumulatorComponent: component skeleton with one fluid port

Phase 10D adds:
- AccumulatorOperatingPoint: scalar input value object for pressure-reference evaluation
- AccumulatorPressureSummary: result value object (p_ref, p_setpoint)
- AccumulatorComponent.evaluate_pressure_reference: prescribed pressure-reference law

The accumulator model in V1 is a prescribed pressure-reference seam:
    p_ref = p_setpoint

The accumulator declares one BIDIRECTIONAL port — the node at which it sets the
system pressure reference.  The Network owns which node is the reference; the
accumulator law owns the value; the Solver owns global consistency.

P_sys is never stored on the accumulator.  V_g and the volume-pressure law are
future seams, not implemented in Phase 10.

Hard constraints respected:
- No CoolProp.
- No PropertyBackend.
- No correlations.
- No network / solver.
- No mutation of any object.
- No dynamic integration.
- No mass / energy balance.
- P_sys is never stored on the accumulator (architecture invariant).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from mpl_sim.components.base import Component, ComponentId, ComponentKind
from mpl_sim.core.port import Port, PortId, PortRole
from mpl_sim.geometry.primitives import AccumulatorGeometry

# ---------------------------------------------------------------------------
# AccumulatorOperatingPoint
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AccumulatorOperatingPoint:
    """Scalar inputs for AccumulatorComponent.evaluate_pressure_reference.

    Fields:
        p_setpoint : prescribed system pressure reference [Pa]
                     must be finite and strictly positive (physical pressure)
    """

    p_setpoint: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.p_setpoint):
            raise ValueError(
                f"AccumulatorOperatingPoint.p_setpoint must be finite; " f"got {self.p_setpoint!r}"
            )
        if self.p_setpoint <= 0.0:
            raise ValueError(
                f"AccumulatorOperatingPoint.p_setpoint must be > 0 (physical pressure); "
                f"got {self.p_setpoint!r}"
            )


# ---------------------------------------------------------------------------
# AccumulatorPressureSummary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AccumulatorPressureSummary:
    """Result of AccumulatorComponent.evaluate_pressure_reference.

    Fields:
        p_ref      : pressure reference returned by the accumulator [Pa]
        p_setpoint : setpoint value that was used [Pa]
    """

    p_ref: float
    p_setpoint: float


# ---------------------------------------------------------------------------
# AccumulatorComponent
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AccumulatorComponent(Component):
    """Accumulator component — pressure-reference seam.

    An immutable component representing a pressure-reference accumulator.
    Stores containment geometry (no law parameters), declares one BIDIRECTIONAL
    fluid port, and exposes evaluate_pressure_reference for the prescribed-
    pressure-reference law.

    P_sys is never stored on this object.  The Network owns reference-node
    wiring; the Solver owns global consistency.  V_g and volume-pressure laws
    are future seams.

    Fields:
        component_id : stable identity for this component
        geometry     : AccumulatorGeometry — containment only; law parameters
                       must NOT be stored here

    Exposed interface:
        kind()                             → ComponentKind.ACCUMULATOR
        fluid_port                         → Port (BIDIRECTIONAL, peer=None before assembly)
        ports()                            → (fluid_port,) — exactly one in V1
        internal_state_names()             → () — V_g state deferred to future law integration
        evaluate_pressure_reference(...)   → AccumulatorPressureSummary  (Phase 10D)

    Must NOT:
        - call CoolProp, PropertyBackend, or any correlation
        - reference Network or Solver
        - store P_sys, V_g, or any dynamic inventory state
        - implement dynamic integration or mass / energy balance
        - mutate any object
    """

    component_id: ComponentId
    geometry: AccumulatorGeometry

    # ------------------------------------------------------------------
    # Component contract — structural declarations
    # ------------------------------------------------------------------

    def kind(self) -> ComponentKind:
        """Returns ComponentKind.ACCUMULATOR."""
        return ComponentKind.ACCUMULATOR

    @property
    def fluid_port(self) -> Port:
        """Declared fluid port (BIDIRECTIONAL; peer=None before Network assembly)."""
        return Port(
            id=PortId(component_id=self.component_id.name, port_name="fluid"),
            owner=self.component_id.name,
            role=PortRole.BIDIRECTIONAL,
            peer=None,
        )

    def ports(self) -> tuple[Port, ...]:
        """Returns (fluid_port,) — exactly one port in V1."""
        return (self.fluid_port,)

    def internal_state_names(self) -> tuple[str, ...]:
        """Named internal states — empty; V_g is a future seam."""
        return ()

    # ------------------------------------------------------------------
    # Phase 10D: prescribed pressure-reference law
    # ------------------------------------------------------------------

    def evaluate_pressure_reference(
        self,
        inp: AccumulatorOperatingPoint,
    ) -> AccumulatorPressureSummary:
        """Evaluate the prescribed pressure-reference law for this accumulator.

        Computes:
            p_ref = inp.p_setpoint

        The accumulator returns the prescribed setpoint as its pressure reference.
        Neither the accumulator, its geometry, nor the input is mutated.  No
        CoolProp, PropertyBackend, correlation, network, or solver is called.

        Parameters
        ----------
        inp : AccumulatorOperatingPoint

        Returns
        -------
        AccumulatorPressureSummary
        """
        return AccumulatorPressureSummary(
            p_ref=inp.p_setpoint,
            p_setpoint=inp.p_setpoint,
        )
