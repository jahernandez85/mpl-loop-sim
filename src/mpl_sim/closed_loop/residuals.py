"""Residual / unknown / scaling framework foundation — Phase 13C.

Provides explicit value objects for representing unknowns, residual equations,
and scaled residual vectors for fixed-architecture closed-loop solves.

Phase 13C does NOT implement a generic solve(network) API.
Phase 13C does NOT implement simultaneous energy+pressure closure solving.
Phase 13C adds the abstraction layer that Phase 13D (coupled closure) and
later phases (network graph, configurable solver) will build on.

Public API
----------
UnknownSpec        — declares one scalar unknown: name, unit, optional bounds
ResidualSpec       — declares one residual: name, unit, characteristic scale
ResidualEvaluation — pairs a ResidualSpec with a raw residual value
ResidualVector     — ordered collection with scaled norms and convergence check

Typical usage (representation only — no solver invocation here)
--------------------------------------------------------------
    energy_spec = ResidualSpec(name="energy", unit="J/kg", scale=1000.0)
    pressure_spec = ResidualSpec(name="pressure", unit="Pa", scale=100.0)

    energy_eval = ResidualEvaluation(spec=energy_spec, value=h_return - h_ref)
    pressure_eval = ResidualEvaluation(spec=pressure_spec, value=pump_head - dP)

    vec = ResidualVector(evaluations=(energy_eval, pressure_eval))
    print(vec.max_abs_scaled())   # L-infinity norm of scaled residuals
    print(vec.l2_scaled())        # Euclidean norm of scaled residuals
    print(vec.is_converged(1e-6)) # True if max_abs_scaled <= 1e-6

No solver, network topology, or property lookup is introduced here.

Architectural constraints
-------------------------
- MUST NOT import from mpl_sim.network or mpl_sim.solvers.
- MUST NOT import CoolProp or mpl_sim.properties.
- MUST NOT resolve CorrelationRegistry or HeatExchangerModelRegistry.
- No hidden physical defaults, no automatic property inference.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class UnknownSpec:
    """Declares one scalar unknown for a closed-loop solve problem.

    Fields
    ------
    name  : non-empty string identifier (e.g. "Q_cond", "primary_mdot")
    unit  : physical unit string (e.g. "W", "kg/s")
    lower : optional finite lower bound; must not be bool; None = unbounded
    upper : optional finite upper bound; must not be bool; None = unbounded

    Validation
    ----------
    - name must be a non-empty string.
    - unit must be a non-empty string.
    - If lower is provided: not bool, finite.
    - If upper is provided: not bool, finite.
    - If both are provided: lower < upper (strictly).
    """

    name: str
    unit: str
    lower: float | None = None
    upper: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError(f"UnknownSpec.name must be a non-empty string; got {self.name!r}")
        if not isinstance(self.unit, str) or not self.unit:
            raise ValueError(f"UnknownSpec.unit must be a non-empty string; got {self.unit!r}")
        if self.lower is not None:
            if isinstance(self.lower, bool):
                raise ValueError(f"UnknownSpec.lower must not be bool; got {self.lower!r}")
            if not math.isfinite(self.lower):
                raise ValueError(f"UnknownSpec.lower must be finite; got {self.lower!r}")
        if self.upper is not None:
            if isinstance(self.upper, bool):
                raise ValueError(f"UnknownSpec.upper must not be bool; got {self.upper!r}")
            if not math.isfinite(self.upper):
                raise ValueError(f"UnknownSpec.upper must be finite; got {self.upper!r}")
        if self.lower is not None and self.upper is not None:
            if self.lower >= self.upper:
                raise ValueError(
                    f"UnknownSpec: lower must be strictly less than upper; "
                    f"got lower={self.lower!r}, upper={self.upper!r}"
                )


@dataclass(frozen=True)
class ResidualSpec:
    """Declares one residual equation with a characteristic scale.

    The scale converts the raw residual to a dimensionless scaled residual so
    that residuals in different physical units can be compared uniformly.
    Example: scale=1000.0 J/kg for an enthalpy residual; scale=100.0 Pa for
    a pressure residual.

    Fields
    ------
    name  : non-empty string identifier (e.g. "energy", "pressure")
    unit  : physical unit string (e.g. "J/kg", "Pa")
    scale : characteristic magnitude; not bool, finite, strictly > 0

    Validation
    ----------
    - name must be a non-empty string.
    - unit must be a non-empty string.
    - scale must be a non-bool, finite float strictly greater than zero.
    """

    name: str
    unit: str
    scale: float

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError(f"ResidualSpec.name must be a non-empty string; got {self.name!r}")
        if not isinstance(self.unit, str) or not self.unit:
            raise ValueError(f"ResidualSpec.unit must be a non-empty string; got {self.unit!r}")
        if isinstance(self.scale, bool):
            raise ValueError(f"ResidualSpec.scale must not be bool; got {self.scale!r}")
        if not math.isfinite(self.scale) or self.scale <= 0:
            raise ValueError(f"ResidualSpec.scale must be finite and > 0; got {self.scale!r}")


@dataclass(frozen=True)
class ResidualEvaluation:
    """Pairs a ResidualSpec with a raw residual value at a given iterate.

    Fields
    ------
    spec  : ResidualSpec declaring name, unit, and characteristic scale
    value : raw residual in the declared unit; not bool, must be finite

    Properties
    ----------
    scaled_value : value / spec.scale  (dimensionless)

    Validation
    ----------
    - value must be a non-bool, finite float.
      Zero is valid (residual is exactly satisfied).
      Negative values are valid (residual can be signed).
    """

    spec: ResidualSpec
    value: float

    def __post_init__(self) -> None:
        if not isinstance(self.spec, ResidualSpec):
            raise TypeError(
                "ResidualEvaluation.spec must be a ResidualSpec; " f"got {type(self.spec).__name__}"
            )
        if isinstance(self.value, bool):
            raise ValueError(f"ResidualEvaluation.value must not be bool; got {self.value!r}")
        if not math.isfinite(self.value):
            raise ValueError(f"ResidualEvaluation.value must be finite; got {self.value!r}")

    @property
    def scaled_value(self) -> float:
        """Dimensionless scaled residual: value / spec.scale."""
        return self.value / self.spec.scale


@dataclass(frozen=True)
class ResidualVector:
    """Ordered collection of ResidualEvaluation objects.

    Preserves insertion order.  Provides scaled norms and a convergence gate.

    Fields
    ------
    evaluations : non-empty tuple (or list, auto-converted) of
                  ResidualEvaluation objects; each must have a unique spec.name.

    Methods
    -------
    scaled_values()   : tuple[float, ...] — dimensionless residuals (value/scale)
    max_abs_scaled()  : float — L-infinity norm of scaled residuals
    l2_scaled()       : float — Euclidean (L2) norm of scaled residuals
    is_converged(tol) : bool  — True if max_abs_scaled() <= tol

    Validation
    ----------
    - evaluations must be non-empty.
    - No two evaluations may share the same spec.name (case-sensitive).
    """

    evaluations: tuple[ResidualEvaluation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.evaluations, tuple):
            object.__setattr__(self, "evaluations", tuple(self.evaluations))
        if not self.evaluations:
            raise ValueError("ResidualVector.evaluations must be non-empty; got empty sequence.")
        seen: set[str] = set()
        for ev in self.evaluations:
            if not isinstance(ev, ResidualEvaluation):
                raise TypeError(
                    "ResidualVector.evaluations must contain only ResidualEvaluation "
                    f"objects; got {type(ev).__name__}"
                )
            if ev.spec.name in seen:
                raise ValueError(
                    f"ResidualVector: duplicate residual name {ev.spec.name!r}; "
                    f"each residual must have a unique name."
                )
            seen.add(ev.spec.name)

    def scaled_values(self) -> tuple[float, ...]:
        """Scaled residuals (value / scale) in the original insertion order."""
        return tuple(ev.scaled_value for ev in self.evaluations)

    def max_abs_scaled(self) -> float:
        """L-infinity norm: maximum absolute value among the scaled residuals."""
        return max(abs(v) for v in self.scaled_values())

    def l2_scaled(self) -> float:
        """Euclidean (L2) norm of the scaled residual vector."""
        vals = self.scaled_values()
        return math.sqrt(sum(v * v for v in vals))

    def is_converged(self, tolerance: float) -> bool:
        """True if max_abs_scaled() <= tolerance.

        Parameters
        ----------
        tolerance : convergence threshold; not bool, finite, strictly > 0.

        Raises
        ------
        ValueError if tolerance is invalid (bool, zero, negative, nan, inf).
        """
        if isinstance(tolerance, bool):
            raise ValueError(
                f"ResidualVector.is_converged: tolerance must not be bool; " f"got {tolerance!r}"
            )
        if not math.isfinite(tolerance) or tolerance <= 0:
            raise ValueError(
                f"ResidualVector.is_converged: tolerance must be finite and > 0; "
                f"got {tolerance!r}"
            )
        return self.max_abs_scaled() <= tolerance
