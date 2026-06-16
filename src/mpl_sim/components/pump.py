"""Pump component — Phase 10B.

Defines the Pump component: an immutable value object that holds a component
identity, declares inlet and outlet ports, and exposes evaluate_hydraulic for
the prescribed-pressure-rise law.

Phase 10A adds:
- PumpComponent: component skeleton with inlet/outlet ports

Phase 10B adds:
- PumpOperatingPoint: scalar input value object for hydraulic evaluation
- PumpHydraulicSummary: result value object (delta_p, raw_delta_p, multiplier)
- PumpComponent.evaluate_hydraulic: prescribed pressure-rise law

The pump model in V1 is a prescribed pressure-rise seam:
    delta_p = delta_p_setpoint * pressure_rise_multiplier

Sign convention:
    delta_p_setpoint > 0 means the pump raises pressure from inlet to outlet.
    Negative values are allowed (reversed pump); the caller is responsible for
    physical interpretation.  NaN and infinity are always rejected.

Calibration seam:
    pressure_rise_multiplier scales only the pressure-rise contribution.
    No other quantity is affected.  Gravity, acceleration, and mass balance
    are never scaled here.

Hard constraints respected:
- No CoolProp.
- No PropertyBackend.
- No correlations.
- No network / solver.
- No mutation of any object.
- No physical residual assembly.
- No dynamic state.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from mpl_sim.components.base import Component, ComponentId, ComponentKind
from mpl_sim.core.port import Port, PortId, PortRole

# ---------------------------------------------------------------------------
# PumpOperatingPoint
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PumpOperatingPoint:
    """Scalar inputs for PumpComponent.evaluate_hydraulic.

    Fields:
        delta_p_setpoint         : prescribed pressure rise across the pump [Pa]
                                   positive → pump raises pressure from inlet to outlet
                                   negative values allowed; finite value required
        pressure_rise_multiplier : calibration multiplier applied only to the
                                   pressure-rise setpoint (default 1.0)
                                   must be finite and >= 0
    """

    delta_p_setpoint: float
    pressure_rise_multiplier: float = 1.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.delta_p_setpoint):
            raise ValueError(
                f"PumpOperatingPoint.delta_p_setpoint must be finite; "
                f"got {self.delta_p_setpoint!r}"
            )
        if not math.isfinite(self.pressure_rise_multiplier):
            raise ValueError(
                f"PumpOperatingPoint.pressure_rise_multiplier must be finite; "
                f"got {self.pressure_rise_multiplier!r}"
            )
        if self.pressure_rise_multiplier < 0.0:
            raise ValueError(
                f"PumpOperatingPoint.pressure_rise_multiplier must be >= 0; "
                f"got {self.pressure_rise_multiplier!r}"
            )


# ---------------------------------------------------------------------------
# PumpHydraulicSummary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PumpHydraulicSummary:
    """Result of PumpComponent.evaluate_hydraulic.

    Fields:
        delta_p                  : pressure rise delivered by the pump [Pa]
                                   = raw_delta_p * pressure_rise_multiplier
        raw_delta_p              : unscaled setpoint value [Pa]
        pressure_rise_multiplier : multiplier that was applied (for inspection)
    """

    delta_p: float
    raw_delta_p: float
    pressure_rise_multiplier: float


# ---------------------------------------------------------------------------
# PumpComponent
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PumpComponent(Component):
    """Pump component.

    An immutable component representing a pump in the loop.  Declares an inlet
    port and an outlet port; exposes evaluate_hydraulic for the prescribed
    pressure-rise law.

    Fields:
        component_id : stable identity for this component

    Exposed interface:
        kind()                   → ComponentKind.PUMP
        inlet                    → Port (INLET, peer=None before assembly)
        outlet                   → Port (OUTLET, peer=None before assembly)
        ports()                  → (inlet, outlet) — exactly two in V1
        internal_state_names()   → () — shaft-speed/inertia state is a future seam
        evaluate_hydraulic(...)  → PumpHydraulicSummary  (Phase 10B)

    Must NOT:
        - call CoolProp, PropertyBackend, or any correlation
        - reference Network or Solver
        - mutate any object
        - store or compute thermodynamic state values
    """

    component_id: ComponentId

    # ------------------------------------------------------------------
    # Component contract — structural declarations
    # ------------------------------------------------------------------

    def kind(self) -> ComponentKind:
        """Returns ComponentKind.PUMP."""
        return ComponentKind.PUMP

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
        """Named internal states — empty; shaft-speed/inertia state is a future seam."""
        return ()

    # ------------------------------------------------------------------
    # Phase 10B: prescribed pressure-rise law
    # ------------------------------------------------------------------

    def evaluate_hydraulic(
        self,
        inp: PumpOperatingPoint,
    ) -> PumpHydraulicSummary:
        """Evaluate the prescribed pressure-rise law for this pump.

        Computes:
            delta_p = inp.delta_p_setpoint * inp.pressure_rise_multiplier

        The multiplier scales only the pressure-rise setpoint (calibration seam).
        Neither the pump nor any input is mutated.  No CoolProp, PropertyBackend,
        correlation, network, or solver object is referenced.

        Parameters
        ----------
        inp : PumpOperatingPoint

        Returns
        -------
        PumpHydraulicSummary
        """
        delta_p = inp.delta_p_setpoint * inp.pressure_rise_multiplier
        return PumpHydraulicSummary(
            delta_p=delta_p,
            raw_delta_p=inp.delta_p_setpoint,
            pressure_rise_multiplier=inp.pressure_rise_multiplier,
        )
