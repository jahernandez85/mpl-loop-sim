"""Components package — Phase 6A: component contract and Pipe skeleton.

Exports:
  Component contract primitives:
    ComponentId, ComponentKind, ComponentPort, Component

  Pipe skeleton:
    Pipe

Architectural constraints:
  - MUST NOT import from network/ or solvers/.
  - MUST NOT import CoolProp.
  - MUST NOT import properties/ or correlations/ in Phase 6A.
"""

from mpl_sim.components.base import (
    Component,
    ComponentId,
    ComponentKind,
    ComponentPort,
)
from mpl_sim.components.pipe import Pipe

__all__ = [
    # Identity primitives
    "ComponentId",
    "ComponentKind",
    # Port declaration
    "ComponentPort",
    # Abstract base
    "Component",
    # Pipe skeleton
    "Pipe",
]
