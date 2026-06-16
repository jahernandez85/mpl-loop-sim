"""Fixed-point steady solver tests — Phase 8E.

Covers SteadySolver.solve(..., update_provider=...) fixed-point path:

Behavior tests:
  - Zero residual converges without update provider (existing gate behavior preserved)
  - Nonzero residual without update provider gives FAILED (existing behavior preserved)
  - Fixed-point converges when dummy update provider drives residual to zero
  - Fixed-point reaches MAX_ITERATIONS when provider does not reduce residual
  - Update provider is called only when residual is above tolerance
  - Update provider is not called when initial state already converges
  - Final state is the candidate state from the last accepted update
  - Initial SystemState is not mutated by the solver

Metadata tests:
  - Strategy is FIXED_POINT when update_provider is supplied
  - Strategy remains RESIDUAL_GATE for solve_problem() (no-update path)
  - Final residual norm is recorded in ConvergenceMetadata
  - Iteration count is deterministic and verified explicitly

Iteration semantics (documented):
  With max_iterations=N and a non-converging residual:
    - N residual evaluations are performed.
    - N-1 update-provider calls are made (no call on the final iteration).
    - The final state is current_state at the point the loop breaks (the
      candidate from the (N-1)-th update, which was the last accepted update).
    - The final residual norm is from the N-th evaluation (at that candidate).
  This means final state and final norm are consistent: same evaluation point.

Validation tests:
  - Invalid update provider return type raises TypeError
  - Update provider returning non-SystemState candidate raises TypeError
  - Update provider raising an exception propagates naturally

Import-boundary assertions:
  solvers/steady.py must not import CoolProp, properties, correlations,
  calibration, network, components, or geometry.
  Network and components must not import solvers.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from mpl_sim.core.state import StateLayout, StateVariableId, SystemState, VariableKind
from mpl_sim.solvers.base import (
    ConvergenceStrategy,
    SolverOptions,
    SolverStatus,
)
from mpl_sim.solvers.problem import AssembledSteadyProblem
from mpl_sim.solvers.residuals import ResidualEvaluation, ResidualEvaluator, ResidualVector
from mpl_sim.solvers.steady import SteadySolver
from mpl_sim.solvers.updates import StateUpdate, StateUpdateProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _import_lines(module_name: str) -> list[str]:
    import importlib

    mod = importlib.import_module(module_name)
    src = Path(mod.__file__).read_text(encoding="utf-8")  # type: ignore[arg-type]
    return [
        line.strip() for line in src.splitlines() if line.strip().startswith(("import ", "from "))
    ]


def _state(values: list[float]) -> SystemState:
    n = len(values)
    vars_ = [StateVariableId(VariableKind.P, "c", f"p{i}") for i in range(n)]
    layout = StateLayout(vars_)
    return SystemState(layout, values)


def _opts(**kwargs) -> SolverOptions:
    defaults: dict = {"tolerance": 1e-4, "max_iterations": 10}
    defaults.update(kwargs)
    return SolverOptions(**defaults)


# ---------------------------------------------------------------------------
# Dummy evaluators
# ---------------------------------------------------------------------------


class _FixedNormEvaluator(ResidualEvaluator):
    """Returns a constant residual norm regardless of state."""

    def __init__(self, norm: float) -> None:
        self._norm = norm
        self.call_count = 0

    def evaluate(self, state: SystemState) -> ResidualEvaluation:
        self.call_count += 1
        vec = ResidualVector([self._norm])
        return ResidualEvaluation(vector=vec, norm=self._norm)


class _ZeroEvaluator(ResidualEvaluator):
    """Always returns zero residuals."""

    def __init__(self) -> None:
        self.call_count = 0

    def evaluate(self, state: SystemState) -> ResidualEvaluation:
        self.call_count += 1
        vec = ResidualVector([0.0] * len(state))
        return ResidualEvaluation(vector=vec, norm=0.0)


class _StateMaxAbsEvaluator(ResidualEvaluator):
    """Residual norm = max(|state values|).  Decays as state shrinks."""

    def __init__(self) -> None:
        self.call_count = 0

    def evaluate(self, state: SystemState) -> ResidualEvaluation:
        self.call_count += 1
        vals = [abs(v) for v in state.values.tolist()]
        norm = max(vals) if vals else 0.0
        vec = ResidualVector(vals)
        return ResidualEvaluation(vector=vec, norm=norm)


# ---------------------------------------------------------------------------
# Dummy update providers
# ---------------------------------------------------------------------------


class _IdentityProvider(StateUpdateProvider):
    """Returns a copy of the input state unchanged (residual never improves)."""

    def __init__(self) -> None:
        self.call_count = 0

    def propose_update(
        self,
        state: SystemState,
        residual: ResidualEvaluation,
    ) -> StateUpdate:
        self.call_count += 1
        return StateUpdate(state=state.copy())


class _ScaleDownProvider(StateUpdateProvider):
    """Multiplies all state values by ``factor`` each call.

    With _StateMaxAbsEvaluator and factor=0.01, convergence is fast:
      initial [10.0] -> norm=10.0 -> [0.1] -> norm=0.1 -> [0.001] -> norm=0.001
      -> [1e-5] -> norm=1e-5 < tol=1e-4 at iteration 4.
    """

    def __init__(self, factor: float = 0.01) -> None:
        self._factor = factor
        self.call_count = 0
        self.input_states: list[SystemState] = []

    def propose_update(
        self,
        state: SystemState,
        residual: ResidualEvaluation,
    ) -> StateUpdate:
        self.call_count += 1
        self.input_states.append(state)
        new_vals = [v * self._factor for v in state.values.tolist()]
        new_state = SystemState(state.layout, new_vals)
        return StateUpdate(state=new_state)


class _ZeroStateProvider(StateUpdateProvider):
    """Returns a state with all values set to zero (converges in one update)."""

    def __init__(self) -> None:
        self.call_count = 0

    def propose_update(
        self,
        state: SystemState,
        residual: ResidualEvaluation,
    ) -> StateUpdate:
        self.call_count += 1
        new_state = SystemState(state.layout, [0.0] * len(state))
        return StateUpdate(state=new_state)


class _BadReturnProvider(StateUpdateProvider):
    """Returns wrong type (not a StateUpdate)."""

    def propose_update(
        self,
        state: SystemState,
        residual: ResidualEvaluation,
    ) -> StateUpdate:
        return None  # type: ignore[return-value]


class _BadCandidateStateProvider(StateUpdateProvider):
    """Returns a StateUpdate whose .state is not a SystemState."""

    def propose_update(
        self,
        state: SystemState,
        residual: ResidualEvaluation,
    ) -> StateUpdate:
        return StateUpdate(state="not_a_system_state")  # type: ignore[arg-type]


class _RaisingProvider(StateUpdateProvider):
    """Raises RuntimeError unconditionally."""

    def propose_update(
        self,
        state: SystemState,
        residual: ResidualEvaluation,
    ) -> StateUpdate:
        raise RuntimeError("provider intentionally failed")


# ---------------------------------------------------------------------------
# 1. Existing gate behavior preserved (no update_provider)
# ---------------------------------------------------------------------------


class TestGateBehaviorPreserved:
    """Phase 8C gate remains intact when update_provider is None."""

    def test_zero_residual_converges_without_provider(self) -> None:
        result = SteadySolver().solve(_state([0.0, 0.0]), _ZeroEvaluator(), _opts())
        assert result.report.status is SolverStatus.CONVERGED

    def test_nonzero_residual_fails_without_provider(self) -> None:
        ev = _FixedNormEvaluator(1.0)
        result = SteadySolver().solve(_state([1.0]), ev, _opts(tolerance=1e-6))
        assert result.report.status in (SolverStatus.FAILED, SolverStatus.MAX_ITERATIONS)

    def test_gate_evaluator_called_exactly_once(self) -> None:
        ev = _ZeroEvaluator()
        SteadySolver().solve(_state([0.0]), ev, _opts())
        assert ev.call_count == 1

    def test_gate_no_convergence_metadata(self) -> None:
        result = SteadySolver().solve(_state([0.0]), _ZeroEvaluator(), _opts())
        assert result.report.convergence_metadata is None


# ---------------------------------------------------------------------------
# 2. Fixed-point convergence
# ---------------------------------------------------------------------------


class TestFixedPointConverges:
    """Solver converges when provider drives residual below tolerance."""

    def test_converges_status(self) -> None:
        # _ScaleDownProvider(0.01) with _StateMaxAbsEvaluator:
        #   iter=1: norm=10.0, update->[0.1]
        #   iter=2: norm=0.1,  update->[0.001]
        #   iter=3: norm=0.001,update->[1e-5]
        #   iter=4: norm=1e-5 < tol=1e-4 -> CONVERGED
        ev = _StateMaxAbsEvaluator()
        provider = _ScaleDownProvider(0.01)
        result = SteadySolver().solve(
            _state([10.0]),
            ev,
            _opts(tolerance=1e-4, max_iterations=20),
            update_provider=provider,
        )
        assert result.report.status is SolverStatus.CONVERGED

    def test_converges_iteration_count_is_deterministic(self) -> None:
        # 4 evaluations: at 10.0, 0.1, 0.001, 1e-5 (last one < tol)
        ev = _StateMaxAbsEvaluator()
        provider = _ScaleDownProvider(0.01)
        result = SteadySolver().solve(
            _state([10.0]),
            ev,
            _opts(tolerance=1e-4, max_iterations=20),
            update_provider=provider,
        )
        assert result.report.iterations == 4
        assert ev.call_count == 4

    def test_converges_provider_call_count(self) -> None:
        # provider called for iters 1-3; not called on iter 4 (converged)
        ev = _StateMaxAbsEvaluator()
        provider = _ScaleDownProvider(0.01)
        SteadySolver().solve(
            _state([10.0]),
            ev,
            _opts(tolerance=1e-4, max_iterations=20),
            update_provider=provider,
        )
        assert provider.call_count == 3

    def test_converges_final_residual_norm(self) -> None:
        ev = _StateMaxAbsEvaluator()
        provider = _ScaleDownProvider(0.01)
        result = SteadySolver().solve(
            _state([10.0]),
            ev,
            _opts(tolerance=1e-4, max_iterations=20),
            update_provider=provider,
        )
        assert result.report.residual_norm is not None
        assert result.report.residual_norm == pytest.approx(1e-5)

    def test_converges_final_state_values(self) -> None:
        # Final state = candidate after 3 updates: 10 * 0.01^3 = 1e-5
        ev = _StateMaxAbsEvaluator()
        provider = _ScaleDownProvider(0.01)
        result = SteadySolver().solve(
            _state([10.0]),
            ev,
            _opts(tolerance=1e-4, max_iterations=20),
            update_provider=provider,
        )
        assert result.state is not None
        assert result.state.values[0] == pytest.approx(1e-5)

    def test_converges_result_state_is_not_initial(self) -> None:
        initial = _state([10.0])
        ev = _StateMaxAbsEvaluator()
        result = SteadySolver().solve(
            initial,
            ev,
            _opts(tolerance=1e-4, max_iterations=20),
            update_provider=_ScaleDownProvider(0.01),
        )
        assert result.state is not initial

    def test_simple_one_update_convergence(self) -> None:
        # _ZeroStateProvider zeroes state; _StateMaxAbsEvaluator gives norm=0.
        # iter=1: norm=1.0 > tol. update->[0.0].
        # iter=2: norm=0.0 < tol. CONVERGED at iter=2.
        ev = _StateMaxAbsEvaluator()
        provider = _ZeroStateProvider()
        result = SteadySolver().solve(
            _state([1.0]),
            ev,
            _opts(tolerance=1e-6, max_iterations=10),
            update_provider=provider,
        )
        assert result.report.status is SolverStatus.CONVERGED
        assert result.report.iterations == 2
        assert provider.call_count == 1

    def test_already_converged_on_first_eval(self) -> None:
        # Initial state [0.0] -> norm=0.0 < tol -> CONVERGED on iter=1.
        ev = _StateMaxAbsEvaluator()
        provider = _ZeroStateProvider()
        result = SteadySolver().solve(
            _state([0.0]),
            ev,
            _opts(tolerance=1e-6, max_iterations=10),
            update_provider=provider,
        )
        assert result.report.status is SolverStatus.CONVERGED
        assert result.report.iterations == 1
        assert provider.call_count == 0


# ---------------------------------------------------------------------------
# 3. Update provider not called when already converged
# ---------------------------------------------------------------------------


class TestProviderNotCalledWhenConverged:
    """Update provider must not be invoked if initial residual is within tolerance."""

    def test_provider_not_called_for_zero_initial_residual(self) -> None:
        ev = _ZeroEvaluator()
        provider = _IdentityProvider()
        SteadySolver().solve(_state([1.0]), ev, _opts(), update_provider=provider)
        assert provider.call_count == 0

    def test_provider_not_called_when_norm_at_tolerance(self) -> None:
        tol = 1e-4
        # FixedNormEvaluator(tol): norm == tol -> CONVERGED (norm <= tol).
        ev = _FixedNormEvaluator(tol)
        provider = _IdentityProvider()
        result = SteadySolver().solve(
            _state([1.0]), ev, _opts(tolerance=tol), update_provider=provider
        )
        assert result.report.status is SolverStatus.CONVERGED
        assert provider.call_count == 0


# ---------------------------------------------------------------------------
# 4. MAX_ITERATIONS when provider does not reduce residual
# ---------------------------------------------------------------------------


class TestFixedPointMaxIterations:
    """Solver reports MAX_ITERATIONS when tolerance is never reached."""

    def test_max_iterations_status(self) -> None:
        ev = _FixedNormEvaluator(1.0)
        result = SteadySolver().solve(
            _state([1.0]),
            ev,
            _opts(tolerance=1e-6, max_iterations=3),
            update_provider=_IdentityProvider(),
        )
        assert result.report.status is SolverStatus.MAX_ITERATIONS

    def test_evaluator_called_max_iterations_times(self) -> None:
        # With max_iterations=3: 3 evaluations, 2 update calls.
        ev = _FixedNormEvaluator(1.0)
        provider = _IdentityProvider()
        SteadySolver().solve(
            _state([1.0]),
            ev,
            _opts(tolerance=1e-6, max_iterations=3),
            update_provider=provider,
        )
        assert ev.call_count == 3

    def test_provider_called_max_iterations_minus_one_times(self) -> None:
        # N evaluations -> N-1 provider calls (no call on the final iteration).
        ev = _FixedNormEvaluator(1.0)
        provider = _IdentityProvider()
        SteadySolver().solve(
            _state([1.0]),
            ev,
            _opts(tolerance=1e-6, max_iterations=3),
            update_provider=provider,
        )
        assert provider.call_count == 2

    def test_iteration_count_equals_max_iterations(self) -> None:
        ev = _FixedNormEvaluator(1.0)
        result = SteadySolver().solve(
            _state([1.0]),
            ev,
            _opts(tolerance=1e-6, max_iterations=5),
            update_provider=_IdentityProvider(),
        )
        assert result.report.iterations == 5

    def test_max_iterations_one(self) -> None:
        # max_iterations=1: 1 eval, 0 provider calls; MAX_ITERATIONS immediately.
        ev = _FixedNormEvaluator(1.0)
        provider = _IdentityProvider()
        result = SteadySolver().solve(
            _state([1.0]),
            ev,
            _opts(tolerance=1e-6, max_iterations=1),
            update_provider=provider,
        )
        assert result.report.status is SolverStatus.MAX_ITERATIONS
        assert ev.call_count == 1
        assert provider.call_count == 0

    def test_final_residual_norm_recorded_on_max_iterations(self) -> None:
        ev = _FixedNormEvaluator(2.5)
        result = SteadySolver().solve(
            _state([1.0]),
            ev,
            _opts(tolerance=1e-6, max_iterations=3),
            update_provider=_IdentityProvider(),
        )
        assert result.report.residual_norm == pytest.approx(2.5)


# ---------------------------------------------------------------------------
# 5. Final state is the last accepted candidate
# ---------------------------------------------------------------------------


class TestFinalStateIsLastCandidate:
    """Verify that result.state is the candidate from the last update call."""

    def test_converging_final_state_matches_last_candidate(self) -> None:
        # iter=1: [10.0]->norm=10.0. update->[0.1].
        # iter=2: [0.1]->norm=0.1.   update->[0.001].
        # iter=3: [0.001]->norm=0.001. update->[1e-5].
        # iter=4: [1e-5]->norm=1e-5 < tol=1e-4. CONVERGED. final=[1e-5].
        provider = _ScaleDownProvider(0.01)
        result = SteadySolver().solve(
            _state([10.0]),
            _StateMaxAbsEvaluator(),
            _opts(tolerance=1e-4, max_iterations=20),
            update_provider=provider,
        )
        assert result.state is not None
        assert result.state.values[0] == pytest.approx(1e-5)

    def test_max_iterations_final_state_is_last_candidate(self) -> None:
        # max_iterations=3: iter1->update->state1, iter2->update->state2,
        # iter3->eval->break.  final_state = state2 (last candidate).
        # With _ScaleDownProvider(0.1) and initial [5.0]:
        #   state0=[5.0], state1=[0.5], state2=[0.05]
        # iter1: eval([5.0])->norm=5.0. update->[0.5].
        # iter2: eval([0.5])->norm=0.5. update->[0.05].
        # iter3: eval([0.05])->norm=0.05 > tol=1e-6. break.
        # final state = [0.05].
        provider = _ScaleDownProvider(0.1)
        result = SteadySolver().solve(
            _state([5.0]),
            _StateMaxAbsEvaluator(),
            _opts(tolerance=1e-6, max_iterations=3),
            update_provider=provider,
        )
        assert result.state is not None
        assert result.state.values[0] == pytest.approx(0.05)
        assert result.report.status is SolverStatus.MAX_ITERATIONS

    def test_max_iterations_norm_is_from_last_evaluation(self) -> None:
        # Continuing above: iter3 evaluates [0.05] -> norm=0.05.
        provider = _ScaleDownProvider(0.1)
        result = SteadySolver().solve(
            _state([5.0]),
            _StateMaxAbsEvaluator(),
            _opts(tolerance=1e-6, max_iterations=3),
            update_provider=provider,
        )
        assert result.report.residual_norm == pytest.approx(0.05)


# ---------------------------------------------------------------------------
# 6. Initial SystemState immutability
# ---------------------------------------------------------------------------


class TestInitialStateNotMutated:
    def test_initial_state_unchanged_after_converging_solve(self) -> None:
        initial = _state([10.0])
        original = initial.values.copy()
        SteadySolver().solve(
            initial,
            _StateMaxAbsEvaluator(),
            _opts(tolerance=1e-4, max_iterations=20),
            update_provider=_ScaleDownProvider(0.01),
        )
        assert (initial.values == original).all()

    def test_initial_state_unchanged_after_max_iterations(self) -> None:
        initial = _state([1.0])
        original = initial.values.copy()
        SteadySolver().solve(
            initial,
            _FixedNormEvaluator(1.0),
            _opts(tolerance=1e-6, max_iterations=5),
            update_provider=_IdentityProvider(),
        )
        assert (initial.values == original).all()

    def test_result_state_is_not_same_object_as_initial(self) -> None:
        initial = _state([0.0])
        result = SteadySolver().solve(
            initial,
            _ZeroEvaluator(),
            _opts(),
            update_provider=_IdentityProvider(),
        )
        assert result.state is not initial


# ---------------------------------------------------------------------------
# 7. ConvergenceMetadata
# ---------------------------------------------------------------------------


class TestConvergenceMetadataFixedPoint:
    def test_strategy_is_fixed_point_on_converge(self) -> None:
        result = SteadySolver().solve(
            _state([0.0]),
            _ZeroEvaluator(),
            _opts(),
            update_provider=_IdentityProvider(),
        )
        assert result.report.convergence_metadata is not None
        assert result.report.convergence_metadata.strategy is ConvergenceStrategy.FIXED_POINT

    def test_strategy_is_fixed_point_on_max_iterations(self) -> None:
        result = SteadySolver().solve(
            _state([1.0]),
            _FixedNormEvaluator(1.0),
            _opts(tolerance=1e-6, max_iterations=3),
            update_provider=_IdentityProvider(),
        )
        assert result.report.convergence_metadata is not None
        assert result.report.convergence_metadata.strategy is ConvergenceStrategy.FIXED_POINT

    def test_metadata_converged_true(self) -> None:
        result = SteadySolver().solve(
            _state([0.0]),
            _ZeroEvaluator(),
            _opts(),
            update_provider=_IdentityProvider(),
        )
        assert result.report.convergence_metadata is not None
        assert result.report.convergence_metadata.converged is True

    def test_metadata_converged_false_on_max_iterations(self) -> None:
        result = SteadySolver().solve(
            _state([1.0]),
            _FixedNormEvaluator(1.0),
            _opts(tolerance=1e-6, max_iterations=3),
            update_provider=_IdentityProvider(),
        )
        assert result.report.convergence_metadata is not None
        assert result.report.convergence_metadata.converged is False

    def test_metadata_final_residual_norm_is_set(self) -> None:
        result = SteadySolver().solve(
            _state([0.0]),
            _ZeroEvaluator(),
            _opts(),
            update_provider=_IdentityProvider(),
        )
        assert result.report.convergence_metadata is not None
        assert result.report.convergence_metadata.final_residual_norm is not None

    def test_metadata_final_residual_norm_matches_report(self) -> None:
        result = SteadySolver().solve(
            _state([1.0]),
            _FixedNormEvaluator(2.5),
            _opts(tolerance=1e-6, max_iterations=3),
            update_provider=_IdentityProvider(),
        )
        meta = result.report.convergence_metadata
        assert meta is not None
        assert meta.final_residual_norm == pytest.approx(result.report.residual_norm)

    def test_metadata_tolerance_matches_options(self) -> None:
        tol = 5e-5
        result = SteadySolver().solve(
            _state([0.0]),
            _ZeroEvaluator(),
            _opts(tolerance=tol),
            update_provider=_IdentityProvider(),
        )
        assert result.report.convergence_metadata is not None
        assert result.report.convergence_metadata.tolerance == pytest.approx(tol)

    def test_metadata_max_iterations_matches_options(self) -> None:
        result = SteadySolver().solve(
            _state([1.0]),
            _FixedNormEvaluator(1.0),
            _opts(tolerance=1e-6, max_iterations=7),
            update_provider=_IdentityProvider(),
        )
        assert result.report.convergence_metadata is not None
        assert result.report.convergence_metadata.max_iterations == 7

    def test_metadata_iterations_equals_report_iterations(self) -> None:
        result = SteadySolver().solve(
            _state([1.0]),
            _FixedNormEvaluator(1.0),
            _opts(tolerance=1e-6, max_iterations=4),
            update_provider=_IdentityProvider(),
        )
        assert result.report.convergence_metadata is not None
        assert result.report.convergence_metadata.iterations == result.report.iterations

    def test_metadata_final_residual_norm_is_finite(self) -> None:
        result = SteadySolver().solve(
            _state([1.0]),
            _FixedNormEvaluator(1.0),
            _opts(tolerance=1e-6, max_iterations=3),
            update_provider=_IdentityProvider(),
        )
        meta = result.report.convergence_metadata
        assert meta is not None
        assert meta.final_residual_norm is not None
        assert math.isfinite(meta.final_residual_norm)


# ---------------------------------------------------------------------------
# 8. Metadata strategy for non-update paths
# ---------------------------------------------------------------------------


class TestNonUpdatePathMetadata:
    """No-update paths preserve their metadata contracts."""

    def test_solve_without_provider_has_no_metadata(self) -> None:
        # Gate path: solve() without update_provider has no ConvergenceMetadata.
        result = SteadySolver().solve(_state([0.0]), _ZeroEvaluator(), _opts())
        assert result.report.convergence_metadata is None

    def test_solve_problem_strategy_is_residual_gate(self) -> None:
        # solve_problem() still uses RESIDUAL_GATE strategy.
        prob = AssembledSteadyProblem(
            name="test",
            initial_state=_state([0.0]),
            evaluator=_ZeroEvaluator(),
        )
        result = SteadySolver().solve_problem(prob, _opts())
        assert result.report.convergence_metadata is not None
        assert result.report.convergence_metadata.strategy is ConvergenceStrategy.RESIDUAL_GATE


# ---------------------------------------------------------------------------
# 9. Validation and failure behavior
# ---------------------------------------------------------------------------


class TestFixedPointValidation:
    def test_bad_return_type_raises_type_error(self) -> None:
        # Provider returns None instead of StateUpdate.
        with pytest.raises(TypeError, match="StateUpdate"):
            SteadySolver().solve(
                _state([1.0]),
                _FixedNormEvaluator(1.0),
                _opts(tolerance=1e-6, max_iterations=3),
                update_provider=_BadReturnProvider(),
            )

    def test_bad_candidate_state_raises_type_error(self) -> None:
        # Provider returns StateUpdate with non-SystemState .state.
        with pytest.raises(TypeError, match="SystemState"):
            SteadySolver().solve(
                _state([1.0]),
                _FixedNormEvaluator(1.0),
                _opts(tolerance=1e-6, max_iterations=3),
                update_provider=_BadCandidateStateProvider(),
            )

    def test_raising_provider_propagates_exception(self) -> None:
        with pytest.raises(RuntimeError, match="provider intentionally failed"):
            SteadySolver().solve(
                _state([1.0]),
                _FixedNormEvaluator(1.0),
                _opts(tolerance=1e-6, max_iterations=3),
                update_provider=_RaisingProvider(),
            )


# ---------------------------------------------------------------------------
# 10. Update provider only called above tolerance
# ---------------------------------------------------------------------------


class TestProviderOnlyCalledAboveTolerance:
    def test_provider_not_called_after_convergence(self) -> None:
        # _ZeroStateProvider zeroes state; _StateMaxAbsEvaluator gives norm=0 next.
        # iter=1: norm=1.0 > tol. call provider. -> [0.0].
        # iter=2: norm=0.0 < tol. CONVERGED. provider NOT called.
        ev = _StateMaxAbsEvaluator()
        provider = _ZeroStateProvider()
        result = SteadySolver().solve(
            _state([1.0]),
            ev,
            _opts(tolerance=1e-6, max_iterations=10),
            update_provider=provider,
        )
        assert result.report.status is SolverStatus.CONVERGED
        assert provider.call_count == 1

    def test_provider_inputs_are_not_initial_state(self) -> None:
        # Verify that provider receives the candidate state, not always the initial.
        ev = _StateMaxAbsEvaluator()
        provider = _ScaleDownProvider(0.01)
        initial = _state([10.0])
        SteadySolver().solve(
            initial,
            ev,
            _opts(tolerance=1e-4, max_iterations=20),
            update_provider=provider,
        )
        # provider.input_states[0] should be initial.copy() (10.0)
        # provider.input_states[1] should be [0.1]
        # provider.input_states[2] should be [0.001]
        assert len(provider.input_states) == 3
        assert provider.input_states[0].values[0] == pytest.approx(10.0)
        assert provider.input_states[1].values[0] == pytest.approx(0.1)
        assert provider.input_states[2].values[0] == pytest.approx(0.001)


# ---------------------------------------------------------------------------
# 11. Import-boundary assertions
# ---------------------------------------------------------------------------


class TestSteadySolverImportBoundaries:
    """steady.py must remain free of forbidden imports after Phase 8E changes."""

    def _imports(self) -> list[str]:
        return _import_lines("mpl_sim.solvers.steady")

    def test_no_coolprop_import(self) -> None:
        assert not any("coolprop" in line.lower() for line in self._imports())

    def test_no_properties_import(self) -> None:
        assert not any("mpl_sim.properties" in line for line in self._imports())

    def test_no_correlations_import(self) -> None:
        assert not any("mpl_sim.correlations" in line for line in self._imports())

    def test_no_calibration_import(self) -> None:
        assert not any("mpl_sim.calibration" in line for line in self._imports())

    def test_no_network_import(self) -> None:
        assert not any("mpl_sim.network" in line for line in self._imports())

    def test_no_components_import(self) -> None:
        assert not any("mpl_sim.components" in line for line in self._imports())

    def test_no_geometry_import(self) -> None:
        assert not any("mpl_sim.geometry" in line for line in self._imports())


class TestIsolationStillHolds:
    """Network and components must not import solvers (unchanged from Phase 8D)."""

    def test_network_assembly_does_not_import_solvers(self) -> None:
        imports = _import_lines("mpl_sim.network.assembly")
        assert not any("solvers" in line for line in imports)

    def test_network_topology_does_not_import_solvers(self) -> None:
        imports = _import_lines("mpl_sim.network.topology")
        assert not any("solvers" in line for line in imports)

    def test_components_base_does_not_import_solvers(self) -> None:
        imports = _import_lines("mpl_sim.components.base")
        assert not any("solvers" in line for line in imports)

    def test_pipe_does_not_import_solvers(self) -> None:
        imports = _import_lines("mpl_sim.components.pipe")
        assert not any("solvers" in line for line in imports)
