"""
components/base.py — Component Abstract Base Class & Port Definition
=====================================================================
MPL Simulation Library — Module 3a (Phase 3)

Defines the fundamental building blocks used by every component in the loop:
  - Port       : thermodynamic + mass-flow connection point between components
  - Component  : abstract base that all MPL components inherit

Design principles
-----------------
* Equation-oriented: each component exposes solve_ss() which returns the
  outlet Port given a fixed inlet Port and component parameters.
* State variables are (P, h) per VanGerner (2016) — avoids phase-region
  discontinuities and is natural for HEM.
* Components are *stateless* between calls: no persistent internal state.
  This makes them safe for Newton-Raphson loops in loop.py.
* Strategy pattern for correlations: components accept HTCCorrelation and
  DPCorrelation callables so they can be swapped without subclassing.

Port connectivity model
-----------------------
Components are connected as a directed graph:

    [Pump] --outlet--> inlet--[Pipe]--outlet--> inlet--[Evaporator] ...

The loop assembler (loop.py) wires components by sharing Port objects and
solves the system of equations iteratively.

References
----------
[1] T.N. Dogan, "Forced-convection boiling flow instabilities,"
    Int. J. Heat Fluid Flow 4 (1983) 145-156.  [HEM basis]
[2] M. VanGerner et al., "1D dynamic model for CO2 two-phase loop,"
    (2016).  [(P, h) as state variables]
[3] R. Kokate, C. Park, "Pumped two-phase loop …,"
    Appl. Therm. Eng. 229 (2023) 120630.  [component interface reference]
[4] Middelhuis et al., "Review MPL experiments," (2024).  [loop topology]
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# FluidState import — lazy / duck-typed to avoid circular deps during testing
# ---------------------------------------------------------------------------

_FLUIDSTATE_REQUIRED = (
    "phase", "T", "P", "h", "rho", "x",
)


def _check_fluid_state(state: object, caller: str) -> None:
    """Raise TypeError if *state* is missing any required FluidState attribute."""
    missing = [a for a in _FLUIDSTATE_REQUIRED if not hasattr(state, a)]
    if missing:
        raise TypeError(
            f"{caller}: state object is missing attributes {missing}. "
            "Pass a fluid_properties.FluidState instance."
        )


# ---------------------------------------------------------------------------
# Port
# ---------------------------------------------------------------------------

@dataclass
class Port:
    """
    Thermodynamic + mass-flow connection point between two components.

    A Port carries the *complete* thermodynamic state at a cross-section
    together with the mass flow rate. It is the sole data structure passed
    between components; no component stores per-connection state internally.

    Parameters
    ----------
    state : FluidState (or compatible duck-type)
        Full thermodynamic state at the port cross-section.
        Must expose at minimum: P [Pa], h [J/kg], T [K], rho [kg/m³],
        x [-], phase (str).
    mdot : float
        Mass flow rate [kg/s]. Positive = flow in the direction of the
        component arrow (inlet → outlet).

    Notes
    -----
    * The Port does *not* own its FluidState; it holds a reference.
      Components create new FluidState objects for their outlet Port.
    * For the loop assembler, the inlet Port of component N is the
      *same object* as the outlet Port of component N-1.  Changes to
      the outlet Port propagate automatically.
    """
    state: object           # FluidState — thermodynamic state at section
    mdot:  float            # [kg/s]  mass flow rate (positive = forward)

    # ------------------------------------------------------------------
    # Convenience accessors (delegate to embedded state)
    # ------------------------------------------------------------------

    @property
    def P(self) -> float:
        """Static pressure [Pa]."""
        return self.state.P

    @property
    def h(self) -> float:
        """Specific enthalpy [J/kg]."""
        return self.state.h

    @property
    def T(self) -> float:
        """Temperature [K]."""
        return self.state.T

    @property
    def rho(self) -> float:
        """Density [kg/m³] (HEM mixture for two-phase)."""
        return self.state.rho

    @property
    def x(self) -> float:
        """Vapour quality [-].  0 = saturated liquid, 1 = saturated vapour."""
        return self.state.x

    @property
    def phase(self) -> str:
        """Phase string: 'liquid' | 'two-phase' | 'vapor'."""
        return self.state.phase

    @property
    def G(self) -> float:
        """
        Mass flux [kg/m²·s] — *not* available until the Port is associated
        with a specific cross-sectional area.  This property is intentionally
        omitted here and computed inside the component that owns the geometry.
        """
        raise AttributeError(
            "Port.G (mass flux) requires a cross-sectional area. "
            "Compute inside the component: G = mdot / A_c."
        )

    def __repr__(self) -> str:
        ph = getattr(self.state, "phase", "?")
        P  = getattr(self.state, "P",     float("nan"))
        h  = getattr(self.state, "h",     float("nan"))
        T  = getattr(self.state, "T",     float("nan"))
        x  = getattr(self.state, "x",     float("nan"))
        return (
            f"Port(phase={ph!r}, P={P/1e5:.3f} bar, "
            f"T={T-273.15:.2f} °C, h={h/1e3:.1f} kJ/kg, "
            f"x={x:.3f}, mdot={self.mdot:.4f} kg/s)"
        )


# ---------------------------------------------------------------------------
# Component — abstract base class
# ---------------------------------------------------------------------------

class Component(ABC):
    """
    Abstract base class for all MPL components.

    Every component in the loop (pipe, evaporator, condenser, pump,
    accumulator) inherits from this class and must implement the three
    abstract methods:

      solve_ss(inlet)  → outlet Port
      pressure_drop()  → float  [Pa]
      heat_transfer()  → float  [W]

    Attributes
    ----------
    name : str
        Human-readable component identifier, used in loop logs and error
        messages.
    inlet : Port | None
        Inlet connection point. Set by the loop assembler before solve_ss().
    outlet : Port | None
        Outlet connection point. Populated by solve_ss().

    Notes
    -----
    * Components do not own physical geometry — that belongs to the
      subclass __init__.
    * Components are stateless between solve_ss() calls: repeated calls
      with the same inlet must produce identical outlets.
    * After solve_ss() the attributes pressure_drop() and heat_transfer()
      may be queried as *cached* results from the last solve.
    """

    def __init__(self, name: str = ""):
        self.name:   str          = name or self.__class__.__name__
        self.inlet:  Optional[Port] = None
        self.outlet: Optional[Port] = None
        self._last_dP: float = 0.0   # cached from last solve_ss()
        self._last_Q:  float = 0.0   # cached from last solve_ss()

    # ------------------------------------------------------------------
    # Abstract interface — must be implemented by every component
    # ------------------------------------------------------------------

    @abstractmethod
    def solve_ss(self, inlet: Port) -> Port:
        """
        Steady-state solution: compute the outlet Port given the inlet.

        The method must:
          1. Store the inlet  → self.inlet
          2. Compute the outlet thermodynamic state and mdot.
          3. Store the outlet → self.outlet
          4. Cache ΔP        → self._last_dP  [Pa]
          5. Cache Q         → self._last_Q   [W]
          6. Return the outlet Port.

        Parameters
        ----------
        inlet : Port
            Upstream connection carrying state and mass flow rate.

        Returns
        -------
        Port
            Outlet Port with updated (P_out, h_out, mdot).
        """
        ...

    @abstractmethod
    def pressure_drop(self) -> float:
        """
        Total pressure drop across the component [Pa].

        ΔP = P_inlet − P_outlet  (positive = pressure decreases in flow direction).

        Must be valid after the last call to solve_ss().
        """
        ...

    @abstractmethod
    def heat_transfer(self) -> float:
        """
        Net heat added to the fluid [W].

        Q > 0  →  heat flows into the fluid  (evaporator, preheated pipe)
        Q < 0  →  heat flows out of the fluid (condenser, heat loss)
        Q = 0  →  adiabatic

        Must be valid after the last call to solve_ss().
        """
        ...

    # ------------------------------------------------------------------
    # Concrete helpers available to all subclasses
    # ------------------------------------------------------------------

    def _require_inlet(self, caller: str = "") -> Port:
        """
        Guard: raises RuntimeError if self.inlet is not set.
        Call at the top of solve_ss() implementations.
        """
        if self.inlet is None:
            raise RuntimeError(
                f"{self.name}.{caller or 'solve_ss'}: inlet Port is not set. "
                "Assign component.inlet before calling solve_ss()."
            )
        return self.inlet

    def _validate_inlet_state(self) -> None:
        """Validate that self.inlet.state is a compatible FluidState."""
        if self.inlet is None:
            raise RuntimeError(f"{self.name}: inlet not set.")
        _check_fluid_state(self.inlet.state, f"{self.name}.inlet.state")

    def __repr__(self) -> str:
        inlet_repr  = repr(self.inlet)  if self.inlet  is not None else "None"
        outlet_repr = repr(self.outlet) if self.outlet is not None else "None"
        return (
            f"{self.__class__.__name__}(name={self.name!r},\n"
            f"  inlet ={inlet_repr},\n"
            f"  outlet={outlet_repr})"
        )

    # ------------------------------------------------------------------
    # Energy / pressure balance convenience (read-only after solve)
    # ------------------------------------------------------------------

    @property
    def dP(self) -> float:
        """Alias for pressure_drop() — pressure drop [Pa] from last solve."""
        return self.pressure_drop()

    @property
    def Q(self) -> float:
        """Alias for heat_transfer() — heat added to fluid [W] from last solve."""
        return self.heat_transfer()


# ---------------------------------------------------------------------------
# ComponentError — typed exception for component-level failures
# ---------------------------------------------------------------------------

class ComponentError(RuntimeError):
    """
    Raised when a component's steady-state solve fails to converge or
    receives physically inconsistent inputs.

    Attributes
    ----------
    component : Component
        The component that raised the error.
    """

    def __init__(self, component: "Component", message: str):
        self.component = component
        super().__init__(f"[{component.name}] {message}")


# ---------------------------------------------------------------------------
# Orientation enum-like constants (used by Pipe and future components)
# ---------------------------------------------------------------------------

class Orientation:
    """
    Named constants for pipe / component orientation.

    Used as the *orientation* parameter in pressure-drop calculations
    to apply the correct gravitational term.

    Attributes
    ----------
    HORIZONTAL      : str
    VERTICAL_UP     : str  — flow goes upward (gravity opposes flow)
    VERTICAL_DOWN   : str  — flow goes downward (gravity aids flow)
    """
    HORIZONTAL     = "horizontal"
    VERTICAL_UP    = "vertical_up"
    VERTICAL_DOWN  = "vertical_down"

    _VALID = {HORIZONTAL, VERTICAL_UP, VERTICAL_DOWN}

    @classmethod
    def validate(cls, value: str) -> str:
        if value not in cls._VALID:
            raise ValueError(
                f"orientation must be one of {cls._VALID!r}; got {value!r}."
            )
        return value


# ---------------------------------------------------------------------------
# Module self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # ---- minimal smoke test (no CoolProp required) ----------------------
    from dataclasses import dataclass as _dc

    @_dc
    class _StubState:
        phase: str  = "liquid"
        P:     float = 5e5
        h:     float = 2e5
        T:     float = 300.0
        rho:   float = 1000.0
        x:     float = 0.0

    # Port construction
    s    = _StubState()
    port = Port(state=s, mdot=0.05)
    print("Port repr:", port)
    assert port.P   == 5e5
    assert port.h   == 2e5
    assert port.T   == 300.0
    assert port.rho == 1000.0
    assert port.x   == 0.0

    # Orientation validation
    Orientation.validate("horizontal")
    try:
        Orientation.validate("diagonal")
        assert False, "Should have raised"
    except ValueError:
        pass

    # Component cannot be instantiated (abstract)
    try:
        Component()  # type: ignore
        assert False, "Should have raised TypeError"
    except TypeError:
        pass

    print("base.py smoke test passed ✓")
