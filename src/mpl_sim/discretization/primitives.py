"""Immutable discretization primitives — Phase 4B.

Discretization describes how a geometry may be divided numerically.
It stores partitioning choices only — no physical state, no thermodynamics.

Architectural constraints enforced here:
- No thermodynamic state (T, P, h, mdot, quality, phase, rho, mu, Re, HTC, f, dP).
- No calls to PropertyBackend or correlations.
- No component balances, no physics solving, no geometry mutation.
- No import of CoolProp, properties, correlations, components,
  calibration, network, solvers, or geometry.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# DiscretizationMode
# ---------------------------------------------------------------------------


class DiscretizationMode(enum.Enum):
    """Supported discretization modes."""

    LUMPED = "lumped"
    UNIFORM = "uniform"
    MOVING_BOUNDARY = "moving_boundary"


# ---------------------------------------------------------------------------
# DiscretizationSpec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DiscretizationSpec:
    """Immutable specification of the intended discretization.

    LUMPED  — one implicit control volume; n_cells must be None or 1.
    UNIFORM — n_cells equal-length cells; n_cells must be a positive integer.
    MOVING_BOUNDARY — declared seam; no physical behaviour in V1; n_cells optional.
    """

    mode: DiscretizationMode
    n_cells: int | None = None
    label: str | None = None

    def __post_init__(self) -> None:
        if self.mode is DiscretizationMode.UNIFORM:
            if self.n_cells is None:
                raise ValueError("DiscretizationSpec: n_cells must be provided for UNIFORM mode.")
            if self.n_cells < 1:
                raise ValueError(
                    f"DiscretizationSpec: n_cells must be >= 1 for UNIFORM mode;"
                    f" got {self.n_cells!r}"
                )
        elif self.mode is DiscretizationMode.LUMPED:
            if self.n_cells is not None and self.n_cells != 1:
                raise ValueError(
                    "DiscretizationSpec: LUMPED mode represents one implicit cell;"
                    f" n_cells must be None or 1, got {self.n_cells!r}"
                )


# ---------------------------------------------------------------------------
# CellIndex
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CellIndex:
    """Immutable zero-based cell index."""

    index: int

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError(f"CellIndex.index must be >= 0; got {self.index!r}")


# ---------------------------------------------------------------------------
# CellSpan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CellSpan:
    """Immutable dimensional span of one cell along a path.

    x0 and x1 are positions [m] measured from the path inlet.
    No thermodynamic state is stored here.
    """

    index: int
    x0: float
    x1: float

    def __post_init__(self) -> None:
        if self.x0 < 0:
            raise ValueError(f"CellSpan.x0 must be >= 0; got {self.x0!r}")
        if self.x1 <= self.x0:
            raise ValueError(f"CellSpan.x1 must be > x0; got x0={self.x0!r}, x1={self.x1!r}")


# ---------------------------------------------------------------------------
# UniformGrid
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UniformGrid:
    """Immutable 1D uniform grid derived from total length and cell count.

    All cells have equal length (length / n_cells) and together cover [0, length]
    exactly.  The grid is deterministic: identical inputs always produce identical
    cell spans.

    Use UniformGrid.from_length(length, n_cells) as the canonical factory.
    """

    length: float
    n_cells: int

    def __post_init__(self) -> None:
        if self.length <= 0:
            raise ValueError(f"UniformGrid.length must be > 0; got {self.length!r}")
        if self.n_cells < 1:
            raise ValueError(f"UniformGrid.n_cells must be >= 1; got {self.n_cells!r}")

    @property
    def cell_length(self) -> float:
        return self.length / self.n_cells

    @property
    def cells(self) -> tuple[CellSpan, ...]:
        dx = self.length / self.n_cells
        return tuple(CellSpan(index=i, x0=i * dx, x1=(i + 1) * dx) for i in range(self.n_cells))

    @classmethod
    def from_length(cls, length: float, n_cells: int) -> UniformGrid:
        return cls(length=length, n_cells=n_cells)
