"""Assembled steady problem wrapper tests — Phase 8D.

Covers:
  AssembledSteadyProblem — construction, field validation, immutability,
    evaluate_residual delegation, state non-mutation.

Import-boundary assertions:
  solvers/problem.py must not import CoolProp, properties, correlations,
  calibration, network, components, or geometry.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mpl_sim.core.state import StateLayout, StateVariableId, SystemState, VariableKind
from mpl_sim.solvers.problem import AssembledSteadyProblem
from mpl_sim.solvers.residuals import ResidualEvaluation, ResidualEvaluator, ResidualVector

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


class _ZeroEvaluator(ResidualEvaluator):
    def __init__(self) -> None:
        self.call_count = 0
        self.last_state: SystemState | None = None

    def evaluate(self, state: SystemState) -> ResidualEvaluation:
        self.call_count += 1
        self.last_state = state
        n = len(state)
        vec = ResidualVector([0.0] * n)
        return ResidualEvaluation(vector=vec, norm=0.0)


class _FixedEvaluator(ResidualEvaluator):
    def __init__(self, values: list[float]) -> None:
        self._values = list(values)
        self.call_count = 0

    def evaluate(self, state: SystemState) -> ResidualEvaluation:
        self.call_count += 1
        vec = ResidualVector(self._values)
        return ResidualEvaluation(vector=vec, norm=vec.l2_norm())


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestAssembledSteadyProblemConstruction:
    def test_minimal_construction(self) -> None:
        state = _simple_state()
        ev = _ZeroEvaluator()
        prob = AssembledSteadyProblem(name="test", initial_state=state, evaluator=ev)
        assert prob.name == "test"
        assert prob.initial_state is state
        assert prob.evaluator is ev
        assert prob.description is None

    def test_construction_with_description(self) -> None:
        state = _simple_state()
        prob = AssembledSteadyProblem(
            name="test",
            initial_state=state,
            evaluator=_ZeroEvaluator(),
            description="a test problem",
        )
        assert prob.description == "a test problem"

    def test_rejects_empty_name(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            AssembledSteadyProblem(
                name="",
                initial_state=_simple_state(),
                evaluator=_ZeroEvaluator(),
            )

    def test_rejects_non_system_state(self) -> None:
        with pytest.raises(TypeError):
            AssembledSteadyProblem(
                name="test",
                initial_state="not a state",  # type: ignore[arg-type]
                evaluator=_ZeroEvaluator(),
            )

    def test_rejects_non_evaluator(self) -> None:
        with pytest.raises(TypeError):
            AssembledSteadyProblem(
                name="test",
                initial_state=_simple_state(),
                evaluator="not an evaluator",  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


class TestAssembledSteadyProblemImmutability:
    def test_name_is_immutable(self) -> None:
        prob = AssembledSteadyProblem(
            name="test", initial_state=_simple_state(), evaluator=_ZeroEvaluator()
        )
        with pytest.raises((AttributeError, TypeError)):
            prob.name = "other"  # type: ignore[misc]

    def test_initial_state_field_is_immutable(self) -> None:
        prob = AssembledSteadyProblem(
            name="test", initial_state=_simple_state(), evaluator=_ZeroEvaluator()
        )
        with pytest.raises((AttributeError, TypeError)):
            prob.initial_state = _simple_state()  # type: ignore[misc]

    def test_evaluator_field_is_immutable(self) -> None:
        prob = AssembledSteadyProblem(
            name="test", initial_state=_simple_state(), evaluator=_ZeroEvaluator()
        )
        with pytest.raises((AttributeError, TypeError)):
            prob.evaluator = _ZeroEvaluator()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# evaluate_residual delegation
# ---------------------------------------------------------------------------


class TestAssembledSteadyProblemEvaluateResidual:
    def test_evaluate_residual_delegates_to_evaluator(self) -> None:
        state = _simple_state()
        ev = _ZeroEvaluator()
        prob = AssembledSteadyProblem(name="test", initial_state=state, evaluator=ev)
        result = prob.evaluate_residual(state)
        assert ev.call_count == 1
        assert isinstance(result, ResidualEvaluation)

    def test_evaluate_residual_returns_correct_norm(self) -> None:
        state = _simple_state(2)
        ev = _FixedEvaluator([3.0, 4.0])
        prob = AssembledSteadyProblem(name="test", initial_state=state, evaluator=ev)
        result = prob.evaluate_residual(state)
        assert result.norm == pytest.approx(5.0)

    def test_evaluator_not_called_on_construction(self) -> None:
        ev = _ZeroEvaluator()
        AssembledSteadyProblem(name="test", initial_state=_simple_state(), evaluator=ev)
        assert ev.call_count == 0

    def test_evaluate_residual_called_exactly_once_per_call(self) -> None:
        state = _simple_state()
        ev = _ZeroEvaluator()
        prob = AssembledSteadyProblem(name="test", initial_state=state, evaluator=ev)
        prob.evaluate_residual(state)
        prob.evaluate_residual(state)
        assert ev.call_count == 2

    def test_evaluate_residual_does_not_mutate_initial_state(self) -> None:

        state = _simple_state(3)
        original_values = state.values.copy()
        ev = _ZeroEvaluator()
        prob = AssembledSteadyProblem(name="test", initial_state=state, evaluator=ev)
        prob.evaluate_residual(prob.initial_state)
        assert (state.values == original_values).all()

    def test_evaluate_residual_does_not_mutate_passed_state(self) -> None:

        initial = _simple_state(2)
        query_state = _simple_state(2)
        original_query_values = query_state.values.copy()
        ev = _ZeroEvaluator()
        prob = AssembledSteadyProblem(name="test", initial_state=initial, evaluator=ev)
        prob.evaluate_residual(query_state)
        assert (query_state.values == original_query_values).all()


# ---------------------------------------------------------------------------
# Initial state preserved (not evaluated, not mutated)
# ---------------------------------------------------------------------------


class TestAssembledSteadyProblemStatePreservation:
    def test_initial_state_values_preserved(self) -> None:

        state = _simple_state(3)
        expected = state.values.copy()
        ev = _ZeroEvaluator()
        prob = AssembledSteadyProblem(name="test", initial_state=state, evaluator=ev)
        assert (prob.initial_state.values == expected).all()

    def test_initial_state_is_same_object(self) -> None:
        state = _simple_state()
        prob = AssembledSteadyProblem(name="test", initial_state=state, evaluator=_ZeroEvaluator())
        assert prob.initial_state is state


# ---------------------------------------------------------------------------
# Import-boundary assertions
# ---------------------------------------------------------------------------


class TestAssembledProblemImportBoundaries:
    def _imports(self) -> list[str]:
        return _import_lines("mpl_sim.solvers.problem")

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
