"""Solver contract primitives — Phase 8A/8D.

Immutable, data-only primitives defining the solver vocabulary.
No physics, no correlations, no CoolProp, no network, no components.

Architecture constraints:
- MUST NOT import CoolProp, properties, correlations, calibration.
- MUST NOT import network, components, or geometry.
- MUST NOT compute physics or call any backend.
- May import mpl_sim.core only (for SystemState).
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass

from mpl_sim.core.state import SystemState

# ---------------------------------------------------------------------------
# SolverId
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SolverId:
    """Immutable, hashable solver identity.

    name: non-empty string naming the solver strategy.
    """

    name: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("SolverId.name must be non-empty")


# ---------------------------------------------------------------------------
# SolverStatus
# ---------------------------------------------------------------------------


class SolverStatus(enum.Enum):
    """Closed vocabulary of solver outcome states."""

    NOT_STARTED = "NOT_STARTED"
    CONVERGED = "CONVERGED"
    FAILED = "FAILED"
    MAX_ITERATIONS = "MAX_ITERATIONS"
    INVALID_PROBLEM = "INVALID_PROBLEM"


# ---------------------------------------------------------------------------
# SolverOptions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SolverOptions:
    """Immutable scalar solver settings.

    Fields:
        tolerance      : residual-norm convergence threshold; must be > 0.
        max_iterations : maximum iteration count; must be > 0.
        relaxation     : under-relaxation factor; must be > 0 when provided.
    """

    tolerance: float
    max_iterations: int
    relaxation: float | None = None

    def __post_init__(self) -> None:
        if self.tolerance <= 0.0:
            raise ValueError(f"SolverOptions.tolerance must be > 0; got {self.tolerance!r}")
        if self.max_iterations <= 0:
            raise ValueError(
                f"SolverOptions.max_iterations must be > 0; got {self.max_iterations!r}"
            )
        if self.relaxation is not None and self.relaxation <= 0.0:
            raise ValueError(
                f"SolverOptions.relaxation must be > 0 when provided; got {self.relaxation!r}"
            )


# ---------------------------------------------------------------------------
# ConvergenceStrategy
# ---------------------------------------------------------------------------


class ConvergenceStrategy(enum.Enum):
    """Closed vocabulary of convergence algorithm strategies.

    RESIDUAL_GATE : evaluate once; converge if norm <= tolerance (Phase 8C/8D).
    FIXED_POINT   : iterative fixed-point update (Phase 8E+, not yet implemented).
    NEWTON        : Newton-Raphson with Jacobian (future phase).
    USER_PROVIDED : custom external strategy.
    """

    RESIDUAL_GATE = "RESIDUAL_GATE"
    FIXED_POINT = "FIXED_POINT"
    NEWTON = "NEWTON"
    USER_PROVIDED = "USER_PROVIDED"


# ---------------------------------------------------------------------------
# ConvergenceMetadata
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConvergenceMetadata:
    """Immutable record of convergence process details.

    Fields:
        strategy            : ConvergenceStrategy used.
        tolerance           : convergence threshold; must be > 0.
        max_iterations      : iteration budget; must be > 0.
        iterations          : iterations actually performed; must be >= 0.
        converged           : True when the convergence criterion was met.
        final_residual_norm : last evaluated residual norm; must be finite
                              and >= 0 when present.
        message             : optional human-readable note.
    """

    strategy: ConvergenceStrategy
    tolerance: float
    max_iterations: int
    iterations: int
    converged: bool
    final_residual_norm: float | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if self.tolerance <= 0.0:
            raise ValueError(f"ConvergenceMetadata.tolerance must be > 0; got {self.tolerance!r}")
        if self.max_iterations <= 0:
            raise ValueError(
                f"ConvergenceMetadata.max_iterations must be > 0; " f"got {self.max_iterations!r}"
            )
        if self.iterations < 0:
            raise ValueError(
                f"ConvergenceMetadata.iterations must be >= 0; got {self.iterations!r}"
            )
        if self.final_residual_norm is not None:
            if not math.isfinite(self.final_residual_norm):
                raise ValueError(
                    f"ConvergenceMetadata.final_residual_norm must be finite when present; "
                    f"got {self.final_residual_norm!r}"
                )
            if self.final_residual_norm < 0.0:
                raise ValueError(
                    f"ConvergenceMetadata.final_residual_norm must be >= 0 when present; "
                    f"got {self.final_residual_norm!r}"
                )


# ---------------------------------------------------------------------------
# SolverReport
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SolverReport:
    """Immutable solver run summary.

    Fields:
        status               : final SolverStatus.
        iterations           : number of solver iterations performed.
        residual_norm        : final residual norm; must be finite when present.
        message              : human-readable description of the outcome.
        convergence_metadata : optional ConvergenceMetadata with strategy details.
    """

    status: SolverStatus
    iterations: int
    residual_norm: float | None
    message: str
    convergence_metadata: ConvergenceMetadata | None = None

    def __post_init__(self) -> None:
        if self.residual_norm is not None and not math.isfinite(self.residual_norm):
            raise ValueError(
                f"SolverReport.residual_norm must be finite when present; "
                f"got {self.residual_norm!r}"
            )


# ---------------------------------------------------------------------------
# SolverResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SolverResult:
    """Immutable solver output: final state and convergence report.

    Fields:
        state  : final SystemState (a copy; the original is never mutated).
                 None only when no state is available (e.g. INVALID_PROBLEM
                 before any evaluation).
        report : SolverReport with status, iterations, norm, and message.

    No component or network object is mutated to produce this result.
    """

    state: SystemState | None
    report: SolverReport
