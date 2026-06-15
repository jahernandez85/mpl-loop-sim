"""Component contract base — Phase 6A.

Defines component identity primitives (ComponentId, ComponentKind),
port declarations (ComponentPort), and the abstract Component base.

Architectural constraints:
- Imports only: standard library + mpl_sim.core.port.
- Must NOT import CoolProp, properties, correlations, geometry,
  discretization, calibration, network, or solvers.
- Must NOT compute physics, thermodynamics, or balances.
- Must NOT call PropertyBackend, CorrelationRegistry, or CalibrationRegistry.
- Must NOT store or mutate SystemState, FluidState, or geometry objects.
- No thermodynamic values (P, h, mdot, T, x, rho, mu, quality, phase,
  Re, f, dP, HTC, Nu) on port declarations or in this module.
"""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass

from mpl_sim.core.port import Port, PortId, PortRole

# ---------------------------------------------------------------------------
# ComponentKind
# ---------------------------------------------------------------------------


class ComponentKind(enum.Enum):
    """Bounded kind enumeration for components in the MPL simulation framework.

    Only PIPE has a concrete skeleton in Phase 6A.  The remaining kinds are
    declared here so ComponentKind is complete from the start and no new
    enum values need to be added in later phases.
    """

    PIPE = "PIPE"
    PUMP = "PUMP"
    ACCUMULATOR = "ACCUMULATOR"
    EVAPORATOR = "EVAPORATOR"
    CONDENSER = "CONDENSER"
    HEAT_EXCHANGER = "HEAT_EXCHANGER"


# ---------------------------------------------------------------------------
# ComponentId
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ComponentId:
    """Immutable, structurally comparable identity for a component.

    Fields:
        name: the component's name string (must be non-empty)

    Hashable and compares by structural equality; safe as a dict key or
    set element.

    INTERFACE_SPEC.md §12 — ComponentId referenced in the Network contract.
    """

    name: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("ComponentId.name must be non-empty")


# ---------------------------------------------------------------------------
# ComponentPort
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ComponentPort:
    """Declaration of a port belonging to a component (pre-Network-assembly).

    Represents the component's side of a port declaration — a record of
    which port a component owns and its role, optionally carrying the
    PortId once one is assigned.

    Fields:
        component_id : the owning component's ComponentId
        port_name    : local name within the component (e.g. "in", "out");
                       must be non-empty
        role         : PortRole annotation (INLET | OUTLET | BRANCH |
                       BIDIRECTIONAL); does not forbid reverse flow
        port_id      : optional PortId; None before Network assembly assigns
                       a PortId to this declaration

    No thermodynamic values are stored here.  Forbidden fields:
    P, h, mdot, FluidState, T, x, rho, mu, quality, phase, Re, f, dP,
    HTC, Nu — none of these are or will be attributes of ComponentPort.
    """

    component_id: ComponentId
    port_name: str
    role: PortRole
    port_id: PortId | None = None

    def __post_init__(self) -> None:
        if not self.port_name:
            raise ValueError("ComponentPort.port_name must be non-empty")


# ---------------------------------------------------------------------------
# Component — abstract base
# ---------------------------------------------------------------------------


class Component(ABC):
    """Abstract base for all components in the MPL simulation framework.

    Declares the minimal structural interface for Phase 6A:
      - kind()                 → ComponentKind
      - ports()                → tuple[Port, ...]
      - internal_state_names() → tuple[str, ...]

    The full contribution contract (contribute / result_contribution) and
    slot declarations (correlation_slots, calibration_slots,
    scenario_bindings) are added in Phase 6B when physics is implemented.

    INTERFACE_SPEC.md §11.1  <<FROZEN signature skeleton>>

    Architectural invariants:
    - Must not access the Network or any component neighbour.
    - Must not own global solver logic or network topology.
    - Must not mutate SystemState, FluidState, or geometry objects.
    - The Solver is never referenced; nothing here depends on it.
    """

    @abstractmethod
    def kind(self) -> ComponentKind:
        """The component's kind (PIPE, PUMP, ACCUMULATOR, etc.)."""

    @abstractmethod
    def ports(self) -> tuple[Port, ...]:
        """All declared ports for this component.

        Ports are returned with peer=None before Network assembly.
        The returned tuple is immutable and ordered consistently.
        """

    @abstractmethod
    def internal_state_names(self) -> tuple[str, ...]:
        """Names of this component's internal states.

        Empty before physics is implemented (Phase 6B+).
        In steady state, named states carry zero derivative.
        """
