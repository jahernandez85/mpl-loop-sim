"""Components package — Phase 6D: pipe acceleration pressure contribution added.

Exports:
  Component contract primitives:
    ComponentId, ComponentKind, ComponentPort, Component

  Pipe (with Phase 6B friction, Phase 6C gravity, Phase 6D acceleration):
    Pipe, PipeSinglePhaseFrictionInput, PipeFrictionResult,
    PipeGravityInput, PipeGravityResult,
    PipeAccelerationInput, PipeAccelerationResult

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
    PipeAccelerationInput,
    PipeAccelerationResult,
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
    # Pipe Phase 6D acceleration types
    "PipeAccelerationInput",
    "PipeAccelerationResult",
]
