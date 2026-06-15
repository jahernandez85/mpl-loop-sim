"""Components package — Phase 6C: pipe gravity pressure contribution added.

Exports:
  Component contract primitives:
    ComponentId, ComponentKind, ComponentPort, Component

  Pipe (with Phase 6B friction kernel and Phase 6C gravity contribution):
    Pipe, PipeSinglePhaseFrictionInput, PipeFrictionResult,
    PipeGravityInput, PipeGravityResult

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
from mpl_sim.components.pipe import (
    Pipe,
    PipeFrictionResult,
    PipeGravityInput,
    PipeGravityResult,
    PipeSinglePhaseFrictionInput,
)

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
    # Pipe Phase 6C gravity types
    "PipeGravityInput",
    "PipeGravityResult",
]
