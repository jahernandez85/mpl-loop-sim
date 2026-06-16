"""Generic state update interface — Phase 8D.

Defines the contract for proposing a new SystemState based on the current
state and its residual.  No physics, no network, no components.

Architecture constraints:
- MUST NOT import CoolProp, properties, correlations, calibration.
- MUST NOT import network, components, or geometry.
- MUST NOT mutate the input SystemState.
- May import mpl_sim.core (for SystemState) and mpl_sim.solvers.residuals.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass

from mpl_sim.core.state import SystemState
from mpl_sim.solvers.residuals import ResidualEvaluation


@dataclass(frozen=True)
class StateUpdate:
    """Immutable record of a proposed state update.

    Fields:
        state     : candidate new SystemState.
        step_norm : optional norm of the update step; must be finite and >= 0
                    when present.
        message   : optional human-readable note.
    """

    state: SystemState
    step_norm: float | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if self.step_norm is not None:
            if not math.isfinite(self.step_norm):
                raise ValueError(
                    f"StateUpdate.step_norm must be finite when present; " f"got {self.step_norm!r}"
                )
            if self.step_norm < 0.0:
                raise ValueError(
                    f"StateUpdate.step_norm must be >= 0 when present; " f"got {self.step_norm!r}"
                )


class StateUpdateProvider(ABC):
    """Abstract interface for proposing a new SystemState.

    Implementations supply an update rule (fixed-point, Newton, etc.) without
    performing physics directly.  The solver calls this interface during
    iteration; it does not depend on solver internals.

    Phase 8D: interface declared only.  No implementation is invoked by the
    Phase 8D convergence-gate solver.
    """

    @abstractmethod
    def propose_update(
        self,
        state: SystemState,
        residual: ResidualEvaluation,
    ) -> StateUpdate:
        """Propose a new SystemState based on ``state`` and its ``residual``.

        Must not modify ``state``, ``residual``, or any shared mutable object.
        The returned StateUpdate.state must be a new object.
        """
