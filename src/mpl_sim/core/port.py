"""Port — pure connectivity primitives for the MPL simulation framework.

A Port carries connectivity only: a stable identifier, an owning component
reference (for identity, not as a callable back-reference), a role annotation,
and the connected peer PortId.

No thermodynamic values (P, h, mdot, FluidState, T, x, rho) are stored here.
The primary unknowns P, h, and mdot live in the solver-owned SystemState and
are mapped to it via PortHandle (Phase 1C).

Frozen contracts: INTERFACE_SPEC.md §4.1  <<FROZEN>>
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class PortRole(enum.Enum):
    """Connectivity role annotation for a Port.

    Roles are annotations, not hard flow-direction constraints; reverse flow is
    permissible.  The set is bounded by the frozen architecture.

    INTERFACE_SPEC.md §4.1: INLET | OUTLET | BRANCH | BIDIRECTIONAL
    """

    INLET = "INLET"
    OUTLET = "OUTLET"
    BRANCH = "BRANCH"
    BIDIRECTIONAL = "BIDIRECTIONAL"


@dataclass(frozen=True)
class PortId:
    """Stable, immutable identifier for a port within the simulation.

    Fields:
        component_id : identifier string of the owning component
        port_name    : local name of this port within that component
                       (e.g. "in", "out", "branch_0")

    PortId is hashable and compares by structural equality, so it is safe as a
    dict key or set element.
    """

    component_id: str
    port_name: str


@dataclass(frozen=True)
class Port:
    """Pure connectivity descriptor — carries no thermodynamic values.

    Fields (INTERFACE_SPEC.md §4.1  <<FROZEN>>):
        id    : unique identifier for this port
        owner : ComponentId string — for identity only; NOT a callable
                back-reference to the component object
        role  : INLET | OUTLET | BRANCH | BIDIRECTIONAL (annotation only;
                does not forbid reverse flow)
        peer  : PortId of the connected port; None before Network assembly

    Port is immutable after construction.  The fields P, h, mdot, FluidState,
    and any derived thermodynamic quantity must never be added here.
    """

    id: PortId
    owner: str  # ComponentId — identity string only
    role: PortRole
    peer: PortId | None = None
