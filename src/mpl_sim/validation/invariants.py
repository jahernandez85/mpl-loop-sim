"""Validation invariant primitives — Phase 9C.

Data-only primitives describing what invariants exist and their check results.
No physical balance computations are performed here.  This layer declares the
vocabulary; future phases wire it to actual residuals from the solver.

Architecture constraints:
- MUST NOT import CoolProp, properties, correlations, calibration.
- MUST NOT import network, components, geometry, or solvers.
- MUST NOT compute physics or call any backend.
- Standard library only (plus math for finite checks).
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# InvariantStatus
# ---------------------------------------------------------------------------


class InvariantStatus(enum.Enum):
    """Closed vocabulary of invariant check outcome states."""

    OK = "OK"
    WARNING = "WARNING"
    FAILED = "FAILED"
    NOT_EVALUATED = "NOT_EVALUATED"


# ---------------------------------------------------------------------------
# InvariantKind
# ---------------------------------------------------------------------------


class InvariantKind(enum.Enum):
    """Closed vocabulary of physical invariant categories."""

    MASS_BALANCE = "MASS_BALANCE"
    ENERGY_BALANCE = "ENERGY_BALANCE"
    PRESSURE_CLOSURE = "PRESSURE_CLOSURE"
    STATE_BOUNDS = "STATE_BOUNDS"
    CUSTOM = "CUSTOM"


# ---------------------------------------------------------------------------
# ValidationInvariant
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationInvariant:
    """Immutable descriptor for a validation invariant.

    This object describes *what* invariant is checked; it does not perform
    any computation.  The tolerance is a threshold against which a residual
    is compared at check time.

    Fields:
        kind        : InvariantKind classifying the invariant.
        name        : non-empty human-readable name (e.g. "global_mass_balance").
        tolerance   : non-negative threshold; residual must satisfy
                      abs(residual) <= tolerance to pass.
        units       : optional SI unit label (e.g. "kg/s", "W").
        description : optional free-text description.
    """

    kind: InvariantKind
    name: str
    tolerance: float
    units: str | None = None
    description: str | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("ValidationInvariant.name must be non-empty")
        if not math.isfinite(self.tolerance):
            raise ValueError(
                f"ValidationInvariant.tolerance must be finite; got {self.tolerance!r}"
            )
        if self.tolerance < 0.0:
            raise ValueError(f"ValidationInvariant.tolerance must be >= 0; got {self.tolerance!r}")


# ---------------------------------------------------------------------------
# InvariantCheckResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InvariantCheckResult:
    """Immutable record of a single invariant check.

    Fields:
        invariant : the ValidationInvariant that was checked.
        residual  : the computed residual value; must be finite.
        tolerance : the threshold applied at check time (may differ from
                    invariant.tolerance if overridden at call site).
        status    : explicit InvariantStatus outcome of the check.
        message   : optional human-readable detail string.
    """

    invariant: ValidationInvariant
    residual: float
    tolerance: float
    status: InvariantStatus
    message: str | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.residual):
            raise ValueError(f"InvariantCheckResult.residual must be finite; got {self.residual!r}")
        if not math.isfinite(self.tolerance):
            raise ValueError(
                f"InvariantCheckResult.tolerance must be finite; got {self.tolerance!r}"
            )
        if self.tolerance < 0.0:
            raise ValueError(f"InvariantCheckResult.tolerance must be >= 0; got {self.tolerance!r}")


# ---------------------------------------------------------------------------
# ValidationReport
# ---------------------------------------------------------------------------


class ValidationReport:
    """Immutable collection of invariant check results with an overall status.

    The overall status is derived deterministically:
    - OK            : all checks passed (status == OK).
    - WARNING       : at least one check has WARNING; none has FAILED.
    - FAILED        : at least one check has FAILED.
    - NOT_EVALUATED : all checks are NOT_EVALUATED (empty report also maps here).

    Fields are exposed through read-only properties; the internal tuple of
    checks is defensively copied on construction.
    """

    def __init__(
        self,
        checks: tuple[InvariantCheckResult, ...] | list[InvariantCheckResult] = (),
    ) -> None:
        self._checks: tuple[InvariantCheckResult, ...] = tuple(checks)

    # ------------------------------------------------------------------
    # Read-only properties
    # ------------------------------------------------------------------

    @property
    def checks(self) -> tuple[InvariantCheckResult, ...]:
        return self._checks

    @property
    def overall_status(self) -> InvariantStatus:
        if not self._checks:
            return InvariantStatus.NOT_EVALUATED
        statuses = {c.status for c in self._checks}
        if InvariantStatus.FAILED in statuses:
            return InvariantStatus.FAILED
        if InvariantStatus.WARNING in statuses:
            return InvariantStatus.WARNING
        if all(c.status == InvariantStatus.NOT_EVALUATED for c in self._checks):
            return InvariantStatus.NOT_EVALUATED
        return InvariantStatus.OK

    @property
    def failed_checks(self) -> tuple[InvariantCheckResult, ...]:
        return tuple(c for c in self._checks if c.status == InvariantStatus.FAILED)

    @property
    def warning_checks(self) -> tuple[InvariantCheckResult, ...]:
        return tuple(c for c in self._checks if c.status == InvariantStatus.WARNING)

    # ------------------------------------------------------------------
    # Identity and comparison
    # ------------------------------------------------------------------

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ValidationReport):
            return NotImplemented
        return self._checks == other._checks

    def __hash__(self) -> int:
        return hash(self._checks)

    def __repr__(self) -> str:
        return (
            f"ValidationReport(overall_status={self.overall_status.name!r}, "
            f"checks={len(self._checks)})"
        )
