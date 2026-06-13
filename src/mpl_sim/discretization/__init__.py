"""Discretization package — numerical partitioning primitives.

Stores mode and resolution choices only.  No physical state, no thermodynamics.

Architectural constraints:
- No thermodynamic state stored or computed here.
- No import of CoolProp, properties, correlations, components, calibration,
  network, solvers, or geometry.
"""

from mpl_sim.discretization.primitives import (
    CellIndex,
    CellSpan,
    DiscretizationMode,
    DiscretizationSpec,
    UniformGrid,
)

__all__ = [
    "CellIndex",
    "CellSpan",
    "DiscretizationMode",
    "DiscretizationSpec",
    "UniformGrid",
]
