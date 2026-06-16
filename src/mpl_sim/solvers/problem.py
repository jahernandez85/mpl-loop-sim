"""Assembled steady problem wrapper — Phase 8D.

Generic container that the steady solver consumes without knowing network or
component internals.  Immutable after construction.

Architecture constraints:
- MUST NOT import CoolProp, properties, correlations, calibration.
- MUST NOT import network, components, or geometry.
- MUST NOT evaluate residuals on construction.
- MUST NOT mutate the initial SystemState.
- May import mpl_sim.core (for SystemState) and mpl_sim.solvers.residuals.
"""

from __future__ import annotations

from dataclasses import dataclass

from mpl_sim.core.state import SystemState
from mpl_sim.solvers.residuals import ResidualEvaluation, ResidualEvaluator


@dataclass(frozen=True)
class AssembledSteadyProblem:
    """Immutable assembled problem wrapper for steady-state solving.

    Bundles the initial state, residual evaluator, and optional metadata that
    the solver needs, without exposing network or component internals.

    Fields:
        name          : non-empty problem identifier.
        initial_state : starting SystemState (never mutated by this wrapper).
        evaluator     : ResidualEvaluator; not called on construction.
        description   : optional human-readable description.
    """

    name: str
    initial_state: SystemState
    evaluator: ResidualEvaluator
    description: str | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("AssembledSteadyProblem.name must be non-empty")
        if not isinstance(self.initial_state, SystemState):
            raise TypeError(
                f"AssembledSteadyProblem.initial_state must be a SystemState; "
                f"got {type(self.initial_state)!r}"
            )
        if not isinstance(self.evaluator, ResidualEvaluator):
            raise TypeError(
                f"AssembledSteadyProblem.evaluator must be a ResidualEvaluator; "
                f"got {type(self.evaluator)!r}"
            )

    def evaluate_residual(self, state: SystemState) -> ResidualEvaluation:
        """Delegate residual evaluation to the stored evaluator.

        Does not modify ``state`` or the problem's ``initial_state``.
        """
        return self.evaluator.evaluate(state)
