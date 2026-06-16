"""Residual evaluation interface — Phase 8B.

Immutable residual value objects and the abstract evaluator protocol.
No physics, no CoolProp, no correlations, no network, no components.

Architecture constraints:
- MUST NOT import CoolProp, properties, correlations, calibration.
- MUST NOT import network, components, or geometry.
- MUST NOT compute physics or call any backend.
- May import mpl_sim.core only (for SystemState).
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass

from mpl_sim.core.state import SystemState

# ---------------------------------------------------------------------------
# ResidualVector
# ---------------------------------------------------------------------------


class ResidualVector:
    """Immutable, finite-valued tuple of residuals.

    All values must be finite (no NaN, no positive or negative infinity).
    """

    __slots__ = ("_values",)

    def __init__(self, values: tuple[float, ...] | list[float]) -> None:
        vals: tuple[float, ...] = tuple(float(v) for v in values)
        for i, v in enumerate(vals):
            if not math.isfinite(v):
                raise ValueError(f"ResidualVector value at index {i} is not finite: {v!r}")
        self._values = vals

    @property
    def values(self) -> tuple[float, ...]:
        """Tuple of residual values (all finite)."""
        return self._values

    def __len__(self) -> int:
        return len(self._values)

    def inf_norm(self) -> float:
        """Infinity norm: maximum absolute value."""
        if not self._values:
            return 0.0
        return max(abs(v) for v in self._values)

    def l2_norm(self) -> float:
        """Euclidean (L2) norm."""
        return math.sqrt(sum(v * v for v in self._values))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ResidualVector):
            return self._values == other._values
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._values)

    def __repr__(self) -> str:
        return f"ResidualVector({self._values!r})"


# ---------------------------------------------------------------------------
# ResidualEvaluation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResidualEvaluation:
    """Immutable result of a single residual evaluation.

    Fields:
        vector  : residual values (all finite).
        norm    : pre-computed residual norm (must be finite).
        message : optional status note.
    """

    vector: ResidualVector
    norm: float
    message: str | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.norm):
            raise ValueError(f"ResidualEvaluation.norm must be finite; got {self.norm!r}")


# ---------------------------------------------------------------------------
# ResidualEvaluator
# ---------------------------------------------------------------------------


class ResidualEvaluator(ABC):
    """Abstract interface for residual evaluation over a SystemState.

    A conforming implementation computes residuals for the given trial state
    without modifying the state, any network object, or any component.
    The solver calls this interface; it does not depend on solver internals.
    """

    @abstractmethod
    def evaluate(self, state: SystemState) -> ResidualEvaluation:
        """Evaluate residuals at ``state`` and return a ResidualEvaluation.

        Must not modify ``state`` or any shared mutable object.
        """
