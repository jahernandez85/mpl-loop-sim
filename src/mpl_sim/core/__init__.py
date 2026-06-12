"""Core data primitives — Phase 1A/1B.

Phase 1A: FluidIdentity (PureFluid, Mixture, CustomFluid) and FluidState.
Phase 1B: Port connectivity primitives (PortRole, PortId, Port).
Phase 1C: SystemState, StateLayout, PortHandle, InternalStateHandle.
"""

from mpl_sim.core.fluid_identity import CustomFluid, FluidIdentity, Mixture, PureFluid
from mpl_sim.core.fluid_state import FluidState
from mpl_sim.core.port import Port, PortId, PortRole

__all__ = [
    "CustomFluid",
    "FluidIdentity",
    "FluidState",
    "Mixture",
    "Port",
    "PortId",
    "PortRole",
    "PureFluid",
]
