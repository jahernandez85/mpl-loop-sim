"""Components package — Phase 6B: single-phase friction kernel added.

Exports:
  Component contract primitives:
    ComponentId, ComponentKind, ComponentPort, Component

  Pipe (with Phase 6B friction kernel):
    Pipe, PipeSinglePhaseFrictionInput, PipeFrictionResult

Architectural constraints:
  - MUST NOT import from network/ or solvers/.
  - MUST NOT import CoolProp.
  - MUST NOT import properties/.
"""

from mpl_sim.components.base import (
    Component,
    ComponentId,
    ComponentKind,
    ComponentPort,
)
from mpl_sim.components.pipe import Pipe, PipeFrictionResult, PipeSinglePhaseFrictionInput

__all__ = [
    # Identity primitives
    "ComponentId",
    "ComponentKind",
    # Port declaration
    "ComponentPort",
    # Abstract base
    "Component",
    # Pipe + Phase 6B friction types
    "Pipe",
    "PipeSinglePhaseFrictionInput",
    "PipeFrictionResult",
]
