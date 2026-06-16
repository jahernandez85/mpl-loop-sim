"""Pump component — Phase 10F.

Phase 10A: PumpComponent skeleton with inlet/outlet ports.
Phase 10B: PumpOperatingPoint, PumpHydraulicSummary, evaluate_hydraulic
           (prescribed pressure-rise seam).
Phase 10F (this phase):
  - PumpGeometry: minimal loop-inertia geometry (L, A); inertia = L / A
  - PumpMapPoint: one (omega, mdot, delta_p) point on the 2-D performance map
  - PumpPerformanceMap: discrete map with deterministic evaluate(omega, mdot)
  - PumpSpeedCommand: commanded shaft-speed binding (omega) for a named pump
  - PumpFlowTarget: commanded mass-flow target (mdot) for a named pump
  - PumpPowerInput / PumpPowerSummary: power/efficiency seam
  - PumpComponent.internal_state_names() → ("omega",)  — shaft speed named, frozen
  - PumpComponent.validate_speed_command / validate_flow_target
  - PumpComponent.evaluate_pump_map
  - PumpComponent.evaluate_power

Sign conventions (Phase 10B):
  delta_p_setpoint > 0 means the pump raises pressure from inlet to outlet.
  Negative values are allowed (reversed pump); the caller is responsible for
  physical interpretation.  NaN and infinity are always rejected.

Calibration seam (Phase 10B):
  pressure_rise_multiplier scales only the pressure-rise contribution.
  No other quantity is affected.

Performance-map interpolation (Phase 10F):
  Given commanded omega, the map finds all points at that exact omega and
  linearly interpolates delta_p in mdot between them.  If a single point
  exists at the commanded omega, that delta_p is returned regardless of mdot
  (the nearest-match rule).  mdot outside the point range raises ValueError.

Power seam (Phase 10F):
  hydraulic_power = mdot * specific_volume * delta_p        [W]
  shaft_power     = hydraulic_power / efficiency             [W]
  specific_volume (= 1/rho) is provided by the caller; no PropertyBackend used.

Internal state seam (Phase 10F):
  omega (shaft speed) is named as a frozen internal state for V1.
  No derivative is computed; no dynamics are implemented.

Hard constraints respected through Phase 10F:
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
# PumpGeometry — minimal loop-inertia geometry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PumpGeometry:
    """Minimal pump geometry for loop-inertia calculations.

    L : equivalent pipe length   [m]  — must be finite and > 0
    A : cross-sectional area     [m²] — must be finite and > 0

    The loop inertia I = L / A [m⁻¹] is available via inertia().
    It is named-but-frozen in V1 (no dynamic equation is computed here).
    """

    L: float
    A: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.L) or self.L <= 0:
            raise ValueError(f"PumpGeometry.L must be finite and > 0; got {self.L!r}")
        if not math.isfinite(self.A) or self.A <= 0:
            raise ValueError(f"PumpGeometry.A must be finite and > 0; got {self.A!r}")

    def inertia(self) -> float:
        """Loop inertia I = L / A [m⁻¹]; named-frozen for V1."""
        return self.L / self.A


# ---------------------------------------------------------------------------
# PumpOperatingPoint — Phase 10B, prescribed pressure-rise
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
# PumpHydraulicSummary — Phase 10B
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PumpHydraulicSummary:
    """Result of PumpComponent.evaluate_hydraulic or evaluate_pump_map.

    Fields:
        delta_p                  : pressure rise delivered by the pump [Pa]
        raw_delta_p              : unscaled pressure rise [Pa]
        pressure_rise_multiplier : multiplier that was applied (1.0 for map evals)
    """

    delta_p: float
    raw_delta_p: float
    pressure_rise_multiplier: float


# ---------------------------------------------------------------------------
# PumpMapPoint — one point on the 2-D performance map
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PumpMapPoint:
    """Single point on the pump performance map.

    Fields:
        omega   : shaft speed [rad/s] — must be finite
        mdot    : mass flow rate [kg/s] — must be finite
        delta_p : pressure rise at this (omega, mdot) [Pa] — must be finite
    """

    omega: float
    mdot: float
    delta_p: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.omega):
            raise ValueError(f"PumpMapPoint.omega must be finite; got {self.omega!r}")
        if not math.isfinite(self.mdot):
            raise ValueError(f"PumpMapPoint.mdot must be finite; got {self.mdot!r}")
        if not math.isfinite(self.delta_p):
            raise ValueError(f"PumpMapPoint.delta_p must be finite; got {self.delta_p!r}")


# ---------------------------------------------------------------------------
# PumpPerformanceMap — 2-D performance map
# ---------------------------------------------------------------------------


def _linear_interp(x_vals: list[float], y_vals: list[float], x: float) -> float:
    """Piecewise-linear interpolation over sorted (x_vals, y_vals).

    x_vals must be sorted ascending and have at least 2 entries.
    Raises ValueError if x is outside [x_vals[0], x_vals[-1]].
    """
    if x < x_vals[0] or x > x_vals[-1]:
        raise ValueError(
            f"mdot={x!r} is outside the map range " f"[{x_vals[0]!r}, {x_vals[-1]!r}] at this omega"
        )
    for i in range(len(x_vals) - 1):
        x0, x1 = x_vals[i], x_vals[i + 1]
        if x0 <= x <= x1:
            if x1 == x0:
                return y_vals[i]
            t = (x - x0) / (x1 - x0)
            return y_vals[i] + t * (y_vals[i + 1] - y_vals[i])
    return y_vals[-1]


@dataclass(frozen=True)
class PumpPerformanceMap:
    """Discrete 2-D pump performance map: delta_p = f(omega, mdot).

    Stores a tuple of PumpMapPoint records.  At evaluation time:
    - All points whose omega matches the commanded omega exactly are collected.
    - If no points match, ValueError is raised.
    - If exactly one point matches, its delta_p is returned (mdot ignored).
    - If multiple points match, delta_p is linearly interpolated in mdot.
      If mdot is outside the point range, ValueError is raised.

    Fields:
        points : non-empty tuple of PumpMapPoint records
    """

    points: tuple[PumpMapPoint, ...]

    def __post_init__(self) -> None:
        if not self.points:
            raise ValueError("PumpPerformanceMap requires at least one PumpMapPoint")

    def evaluate(self, omega: float, mdot: float) -> float:
        """Return delta_p [Pa] for the commanded (omega, mdot).

        Parameters
        ----------
        omega : commanded shaft speed [rad/s] — must match a map omega exactly
        mdot  : operating mass flow rate [kg/s]

        Raises
        ------
        ValueError
            If no points exist at the commanded omega, or if mdot is outside
            the range spanned by the matching points.
        """
        matching = [p for p in self.points if p.omega == omega]
        if not matching:
            available = sorted({p.omega for p in self.points})
            raise ValueError(
                f"No map points at omega={omega!r}. " f"Available omega values: {available!r}"
            )
        if len(matching) == 1:
            return matching[0].delta_p
        sorted_pts = sorted(matching, key=lambda p: p.mdot)
        mdot_vals = [p.mdot for p in sorted_pts]
        dp_vals = [p.delta_p for p in sorted_pts]
        return _linear_interp(mdot_vals, dp_vals, mdot)


# ---------------------------------------------------------------------------
# PumpSpeedCommand — commanded shaft-speed binding
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PumpSpeedCommand:
    """Commanded shaft speed for a named pump.

    Fields:
        component_id : name of the target pump component (must be non-empty)
        omega        : commanded shaft speed [rad/s] (must be finite)
    """

    component_id: str
    omega: float

    def __post_init__(self) -> None:
        if not self.component_id:
            raise ValueError("PumpSpeedCommand.component_id must be non-empty")
        if not math.isfinite(self.omega):
            raise ValueError(f"PumpSpeedCommand.omega must be finite; got {self.omega!r}")


# ---------------------------------------------------------------------------
# PumpFlowTarget — commanded mass-flow target binding
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PumpFlowTarget:
    """Commanded mass-flow target for a named pump.

    Fields:
        component_id : name of the target pump component (must be non-empty)
        mdot         : commanded mass flow rate [kg/s] (must be finite)
    """

    component_id: str
    mdot: float

    def __post_init__(self) -> None:
        if not self.component_id:
            raise ValueError("PumpFlowTarget.component_id must be non-empty")
        if not math.isfinite(self.mdot):
            raise ValueError(f"PumpFlowTarget.mdot must be finite; got {self.mdot!r}")


# ---------------------------------------------------------------------------
# PumpPowerInput / PumpPowerSummary — power/efficiency seam
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PumpPowerInput:
    """Scalar inputs for PumpComponent.evaluate_power.

    Fields:
        mdot            : mass flow rate [kg/s] (must be finite)
        delta_p         : pump pressure rise [Pa] (must be finite)
        specific_volume : fluid specific volume [m³/kg] = 1/rho
                          (must be finite and > 0; caller obtains from FluidState)
        efficiency      : pump total efficiency; 0 < eta <= 1 (must be finite)
    """

    mdot: float
    delta_p: float
    specific_volume: float
    efficiency: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.mdot):
            raise ValueError(f"PumpPowerInput.mdot must be finite; got {self.mdot!r}")
        if not math.isfinite(self.delta_p):
            raise ValueError(f"PumpPowerInput.delta_p must be finite; got {self.delta_p!r}")
        if not math.isfinite(self.specific_volume) or self.specific_volume <= 0:
            raise ValueError(
                f"PumpPowerInput.specific_volume must be finite and > 0; "
                f"got {self.specific_volume!r}"
            )
        if not math.isfinite(self.efficiency) or self.efficiency <= 0 or self.efficiency > 1:
            raise ValueError(
                f"PumpPowerInput.efficiency must be finite and in (0, 1]; "
                f"got {self.efficiency!r}"
            )


@dataclass(frozen=True)
class PumpPowerSummary:
    """Result of PumpComponent.evaluate_power.

    Fields:
        hydraulic_power : Q * delta_p  [W]  where Q = mdot * specific_volume
        shaft_power     : hydraulic_power / efficiency  [W]
    """

    hydraulic_power: float
    shaft_power: float


# ---------------------------------------------------------------------------
# PumpComponent
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PumpComponent(Component):
    """Pump component — Phase 10F.

    An immutable component representing a pump in the loop.  Declares an inlet
    port and an outlet port; exposes evaluate_hydraulic for the prescribed
    pressure-rise seam (Phase 10B) and evaluate_pump_map for map-based
    evaluation (Phase 10F).

    Fields:
        component_id : stable identity for this component
        geometry     : optional minimal pump geometry (L, A); None by default

    Exposed interface:
        kind()                   → ComponentKind.PUMP
        inlet                    → Port (INLET, peer=None before assembly)
        outlet                   → Port (OUTLET, peer=None before assembly)
        ports()                  → (inlet, outlet)
        internal_state_names()   → ("omega",)  — shaft speed named, frozen in V1
        evaluate_hydraulic(...)  → PumpHydraulicSummary  (Phase 10B)
        validate_speed_command(cmd)  → None or ValueError
        validate_flow_target(cmd)    → None or ValueError
        evaluate_pump_map(...)   → PumpHydraulicSummary  (Phase 10F)
        evaluate_power(...)      → PumpPowerSummary       (Phase 10F)

    Must NOT:
        - call CoolProp, PropertyBackend, or any correlation
        - reference Network or Solver
        - mutate any object
        - store or compute thermodynamic state values
    """

    component_id: ComponentId
    geometry: PumpGeometry | None = None

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
        """Named internal states — omega (shaft speed) is declared, frozen in V1.

        The shaft speed is a named internal state seam for future dynamic use.
        No derivative is computed; no dynamics are implemented in V1.
        """
        return ("omega",)

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

    # ------------------------------------------------------------------
    # Phase 10F: command binding validation
    # ------------------------------------------------------------------

    def validate_speed_command(self, cmd: PumpSpeedCommand) -> None:
        """Check that a PumpSpeedCommand targets this pump.

        Raises
        ------
        ValueError
            If cmd.component_id does not match this pump's component_id.name.
        """
        if cmd.component_id != self.component_id.name:
            raise ValueError(
                f"PumpSpeedCommand targets {cmd.component_id!r}, " f"not {self.component_id.name!r}"
            )

    def validate_flow_target(self, cmd: PumpFlowTarget) -> None:
        """Check that a PumpFlowTarget targets this pump.

        Raises
        ------
        ValueError
            If cmd.component_id does not match this pump's component_id.name.
        """
        if cmd.component_id != self.component_id.name:
            raise ValueError(
                f"PumpFlowTarget targets {cmd.component_id!r}, " f"not {self.component_id.name!r}"
            )

    # ------------------------------------------------------------------
    # Phase 10F: performance-map evaluation
    # ------------------------------------------------------------------

    def evaluate_pump_map(
        self,
        perf_map: PumpPerformanceMap,
        omega: float,
        mdot: float,
    ) -> PumpHydraulicSummary:
        """Evaluate delta_p from the performance map at (omega, mdot).

        Parameters
        ----------
        perf_map : PumpPerformanceMap
        omega    : commanded shaft speed [rad/s] — must be finite
        mdot     : operating mass flow rate [kg/s] — must be finite

        Returns
        -------
        PumpHydraulicSummary with pressure_rise_multiplier = 1.0
        """
        if not math.isfinite(omega):
            raise ValueError(f"omega must be finite; got {omega!r}")
        if not math.isfinite(mdot):
            raise ValueError(f"mdot must be finite; got {mdot!r}")
        delta_p = perf_map.evaluate(omega, mdot)
        return PumpHydraulicSummary(
            delta_p=delta_p,
            raw_delta_p=delta_p,
            pressure_rise_multiplier=1.0,
        )

    # ------------------------------------------------------------------
    # Phase 10F: power/efficiency seam
    # ------------------------------------------------------------------

    def evaluate_power(self, inp: PumpPowerInput) -> PumpPowerSummary:
        """Evaluate pump hydraulic and shaft power.

        hydraulic_power = mdot * specific_volume * delta_p
        shaft_power     = hydraulic_power / efficiency

        Parameters
        ----------
        inp : PumpPowerInput

        Returns
        -------
        PumpPowerSummary
        """
        hydraulic_power = inp.mdot * inp.specific_volume * inp.delta_p
        shaft_power = hydraulic_power / inp.efficiency
        return PumpPowerSummary(
            hydraulic_power=hydraulic_power,
            shaft_power=shaft_power,
        )
