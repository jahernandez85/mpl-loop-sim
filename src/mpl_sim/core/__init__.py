"""Core data primitives — Phase 1A/1B/1C.

Phase 1A: FluidIdentity (PureFluid, Mixture, CustomFluid) and FluidState.
Phase 1B: Port connectivity primitives (PortRole, PortId, Port).
Phase 1C: Solver-owned state vector primitives (VariableKind, StateVariableId,
          PortVariableHandle, InternalStateHandle, StateLayout, SystemState).
"""

from mpl_sim.core.fluid_identity import CustomFluid, FluidIdentity, Mixture, PureFluid
from mpl_sim.core.fluid_state import FluidState
from mpl_sim.core.port import Port, PortId, PortRole
from mpl_sim.core.state import (
    InternalStateHandle,
    PortVariableHandle,
    StateLayout,
    StateVariableId,
    SystemState,
    VariableKind,
)

__all__ = [
    # Phase 1A
    "CustomFluid",
    "FluidIdentity",
    "FluidState",
    "Mixture",
    "PureFluid",
    # Phase 1B
    "Port",
    "PortId",
    "PortRole",
    # Phase 1C
    "InternalStateHandle",
    "PortVariableHandle",
    "StateLayout",
    "StateVariableId",
    "SystemState",
    "VariableKind",
]
