"""Minimal steady solver tests — Phase 8C.

Covers:
  SteadySolver.solve — convergence gate:
    - zero residual  -> CONVERGED immediately
    - nonzero residual -> FAILED (no update rule in Phase 8C)
    - solver does not mutate the initial SystemState
    - evaluator is called exactly once (deterministic)
    - solver respects the tolerance threshold
    - SolverResult contains a SolverReport and a final SystemState
    - final state is independent of (not the same object as) the initial state

Import-boundary assertions:
  solvers/steady.py must not import CoolProp, properties, correlations,
  calibration, network, or components.
  Network and components must still not import solvers.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from mpl_sim.core.state import StateLayout, StateVariableId, SystemState, VariableKind
from mpl_sim.solvers.base import SolverOptions, SolverResult, SolverStatus
from mpl_sim.solvers.residuals import ResidualEvaluation, ResidualEvaluator, ResidualVector
from mpl_sim.solvers.steady import SteadySolver

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


def _simple_state(n: int = 2) -> SystemState:
    vars_ = [StateVariableId(VariableKind.P, "c", f"p{i}") for i in range(n)]
    layout = StateLayout(vars_)
    return SystemState(layout, [1.0] * n)


class _FixedResidualEvaluator(ResidualEvaluator):
    """Returns a fixed residual vector regardless of state."""

    def __init__(self, values: list[float]) -> None:
        self._values = list(values)
        self.call_count = 0

    def evaluate(self, state: SystemState) -> ResidualEvaluation:
        self.call_count += 1
        vec = ResidualVector(self._values)
        return ResidualEvaluation(vector=vec, norm=vec.l2_norm())


class _ZeroEvaluator(ResidualEvaluator):
    """Always returns zero residuals."""

    def __init__(self) -> None:
        self.call_count = 0

    def evaluate(self, state: SystemState) -> ResidualEvaluation:
        self.call_count += 1
        n = len(state)
        vec = ResidualVector([0.0] * n)
        return ResidualEvaluation(vector=vec, norm=0.0)


class _MutationDetectingEvaluator(ResidualEvaluator):
    """Records the state values at evaluation time to detect mutation."""

    def __init__(self) -> None:
        self.seen_values: list[np.ndarray] = []

    def evaluate(self, state: SystemState) -> ResidualEvaluation:
        self.seen_values.append(state.values.copy())
        vec = ResidualVector([0.0] * len(state))
        return ResidualEvaluation(vector=vec, norm=0.0)


def _default_options(**kwargs) -> SolverOptions:
    defaults = {"tolerance": 1e-6, "max_iterations": 100}
    defaults.update(kwargs)
    return SolverOptions(**defaults)


# ---------------------------------------------------------------------------
# Convergence gate: zero residual -> CONVERGED
# ---------------------------------------------------------------------------


class TestSteadySolverConverges:
    def test_zero_residual_converges(self) -> None:
        state = _simple_state()
        evaluator = _ZeroEvaluator()
        opts = _default_options()
        result = SteadySolver().solve(state, evaluator, opts)
        assert result.report.status is SolverStatus.CONVERGED

    def test_converged_result_contains_state(self) -> None:
        state = _simple_state()
        result = SteadySolver().solve(state, _ZeroEvaluator(), _default_options())
        assert result.state is not None

    def test_converged_result_contains_report(self) -> None:
        state = _simple_state()
        result = SteadySolver().solve(state, _ZeroEvaluator(), _default_options())
        assert result.report is not None

    def test_converged_report_has_zero_norm(self) -> None:
        state = _simple_state()
        result = SteadySolver().solve(state, _ZeroEvaluator(), _default_options())
        assert result.report.residual_norm == pytest.approx(0.0)

    def test_residual_exactly_at_tolerance_converges(self) -> None:
        tol = 1e-4
        # norm exactly equal to tolerance should CONVERGE (<=)
        evaluator = _FixedResidualEvaluator([tol])  # single-value l2 norm == tol
        result = SteadySolver().solve(_simple_state(), evaluator, _default_options(tolerance=tol))
        assert result.report.status is SolverStatus.CONVERGED

    def test_residual_below_tolerance_converges(self) -> None:
        tol = 1e-4
        evaluator = _FixedResidualEvaluator([tol * 0.5])
        result = SteadySolver().solve(_simple_state(), evaluator, _default_options(tolerance=tol))
        assert result.report.status is SolverStatus.CONVERGED


# ---------------------------------------------------------------------------
# Convergence gate: nonzero residual -> FAILED
# ---------------------------------------------------------------------------


class TestSteadySolverFails:
    def test_large_residual_fails(self) -> None:
        evaluator = _FixedResidualEvaluator([1.0])  # norm=1.0 >> tolerance=1e-6
        result = SteadySolver().solve(_simple_state(), evaluator, _default_options(tolerance=1e-6))
        assert result.report.status in (SolverStatus.FAILED, SolverStatus.MAX_ITERATIONS)

    def test_failed_result_still_contains_state(self) -> None:
        evaluator = _FixedResidualEvaluator([1.0, 2.0])
        result = SteadySolver().solve(_simple_state(), evaluator, _default_options())
        assert result.state is not None

    def test_failed_report_has_finite_norm(self) -> None:
        import math

        evaluator = _FixedResidualEvaluator([3.0, 4.0])  # l2 norm = 5.0
        result = SteadySolver().solve(_simple_state(), evaluator, _default_options())
        assert result.report.residual_norm is not None
        assert math.isfinite(result.report.residual_norm)

    def test_failed_report_norm_matches_evaluated_norm(self) -> None:
        evaluator = _FixedResidualEvaluator([3.0, 4.0])  # l2 norm = 5.0
        result = SteadySolver().solve(_simple_state(), evaluator, _default_options())
        assert result.report.residual_norm == pytest.approx(5.0)

    def test_residual_just_above_tolerance_fails(self) -> None:
        tol = 1e-4
        evaluator = _FixedResidualEvaluator([tol * 1.001])
        result = SteadySolver().solve(_simple_state(), evaluator, _default_options(tolerance=tol))
        assert result.report.status in (SolverStatus.FAILED, SolverStatus.MAX_ITERATIONS)


# ---------------------------------------------------------------------------
# State immutability
# ---------------------------------------------------------------------------


class TestSteadySolverDoesNotMutateState:
    def test_initial_state_values_unchanged_after_solve(self) -> None:
        state = _simple_state(3)
        original_values = state.values.copy()
        SteadySolver().solve(state, _ZeroEvaluator(), _default_options())
        assert (state.values == original_values).all()

    def test_final_state_is_different_object(self) -> None:
        state = _simple_state(2)
        result = SteadySolver().solve(state, _ZeroEvaluator(), _default_options())
        assert result.state is not state

    def test_final_state_has_same_values_as_initial(self) -> None:
        state = _simple_state(2)
        original_values = state.values.copy()
        result = SteadySolver().solve(state, _ZeroEvaluator(), _default_options())
        assert result.state is not None
        assert (result.state.values == original_values).all()

    def test_mutation_detecting_evaluator_sees_unmodified_state(self) -> None:
        state = _simple_state(2)
        original_values = state.values.copy()
        evaluator = _MutationDetectingEvaluator()
        SteadySolver().solve(state, evaluator, _default_options())
        assert len(evaluator.seen_values) == 1
        assert (evaluator.seen_values[0] == original_values).all()


# ---------------------------------------------------------------------------
# Evaluator call count (determinism)
# ---------------------------------------------------------------------------


class TestSteadySolverCallsEvaluatorOnce:
    def test_evaluator_called_exactly_once_on_converge(self) -> None:
        evaluator = _ZeroEvaluator()
        SteadySolver().solve(_simple_state(), evaluator, _default_options())
        assert evaluator.call_count == 1

    def test_evaluator_called_exactly_once_on_fail(self) -> None:
        evaluator = _FixedResidualEvaluator([100.0])
        SteadySolver().solve(_simple_state(), evaluator, _default_options())
        assert evaluator.call_count == 1

    def test_two_solves_call_evaluator_independently(self) -> None:
        evaluator = _ZeroEvaluator()
        solver = SteadySolver()
        solver.solve(_simple_state(), evaluator, _default_options())
        solver.solve(_simple_state(), evaluator, _default_options())
        assert evaluator.call_count == 2


# ---------------------------------------------------------------------------
# Tolerance semantics
# ---------------------------------------------------------------------------


class TestSteadySolverToleranceSemantics:
    def test_strict_tolerance_causes_failure(self) -> None:
        evaluator = _FixedResidualEvaluator([1e-3])  # norm=1e-3
        result = SteadySolver().solve(_simple_state(), evaluator, _default_options(tolerance=1e-10))
        assert result.report.status in (SolverStatus.FAILED, SolverStatus.MAX_ITERATIONS)

    def test_loose_tolerance_causes_convergence(self) -> None:
        evaluator = _FixedResidualEvaluator([1e-3])  # norm=1e-3
        result = SteadySolver().solve(_simple_state(), evaluator, _default_options(tolerance=1.0))
        assert result.report.status is SolverStatus.CONVERGED

    def test_result_is_solver_result_instance(self) -> None:
        result = SteadySolver().solve(_simple_state(), _ZeroEvaluator(), _default_options())
        assert isinstance(result, SolverResult)


# ---------------------------------------------------------------------------
# SolverResult structure
# ---------------------------------------------------------------------------


class TestSteadySolverResultStructure:
    def test_result_has_report(self) -> None:
        result = SteadySolver().solve(_simple_state(), _ZeroEvaluator(), _default_options())
        assert result.report is not None

    def test_result_has_state(self) -> None:
        result = SteadySolver().solve(_simple_state(), _ZeroEvaluator(), _default_options())
        assert result.state is not None

    def test_report_has_iterations(self) -> None:
        result = SteadySolver().solve(_simple_state(), _ZeroEvaluator(), _default_options())
        assert result.report.iterations >= 1

    def test_report_has_residual_norm(self) -> None:
        result = SteadySolver().solve(_simple_state(), _ZeroEvaluator(), _default_options())
        assert result.report.residual_norm is not None

    def test_report_has_message(self) -> None:
        result = SteadySolver().solve(_simple_state(), _ZeroEvaluator(), _default_options())
        assert isinstance(result.report.message, str)
        assert len(result.report.message) > 0


# ---------------------------------------------------------------------------
# Import-boundary assertions
# ---------------------------------------------------------------------------


class TestSteadySolverImportBoundaries:
    def _imports(self) -> list[str]:
        return _import_lines("mpl_sim.solvers.steady")

    def test_no_coolprop_import(self) -> None:
        imports = self._imports()
        assert not any("coolprop" in line.lower() for line in imports)

    def test_no_properties_import(self) -> None:
        imports = self._imports()
        assert not any("mpl_sim.properties" in line for line in imports)

    def test_no_correlations_import(self) -> None:
        imports = self._imports()
        assert not any("mpl_sim.correlations" in line for line in imports)

    def test_no_calibration_import(self) -> None:
        imports = self._imports()
        assert not any("mpl_sim.calibration" in line for line in imports)

    def test_no_network_import(self) -> None:
        imports = self._imports()
        assert not any("mpl_sim.network" in line for line in imports)

    def test_no_components_import(self) -> None:
        imports = self._imports()
        assert not any("mpl_sim.components" in line for line in imports)

    def test_no_geometry_import(self) -> None:
        imports = self._imports()
        assert not any("mpl_sim.geometry" in line for line in imports)


class TestFullIsolationStillHolds:
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
