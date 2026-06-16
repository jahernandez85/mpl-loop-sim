"""Residual evaluation interface tests — Phase 8B.

Covers:
  ResidualVector — construction, finite-value enforcement (NaN rejected,
    infinity rejected), length, values, inf_norm, l2_norm.
  ResidualEvaluation — construction, finite norm enforcement, immutable.
  ResidualEvaluator — abstract; concrete dummy subclass can return a
    valid ResidualEvaluation; evaluator is deterministic.

Import-boundary assertions:
  solvers/residuals.py must not import CoolProp, properties, correlations,
  calibration, network, or components.
  Network and components must still not import solvers.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from mpl_sim.core.state import StateLayout, StateVariableId, SystemState, VariableKind
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


def _simple_state(n: int = 3) -> SystemState:
    vars_ = [StateVariableId(VariableKind.P, "c", f"p{i}") for i in range(n)]
    layout = StateLayout(vars_)
    return SystemState(layout, [float(i) for i in range(n)])


class _ZeroEvaluator(ResidualEvaluator):
    """Dummy evaluator that always returns zero residuals matching state length."""

    def evaluate(self, state: SystemState) -> ResidualEvaluation:
        n = len(state)
        vec = ResidualVector([0.0] * n)
        norm = vec.l2_norm()
        return ResidualEvaluation(vector=vec, norm=norm, message="zero")


class _ConstantEvaluator(ResidualEvaluator):
    """Dummy evaluator returning a fixed constant residual vector."""

    def __init__(self, values: list[float]) -> None:
        self._values = list(values)

    def evaluate(self, state: SystemState) -> ResidualEvaluation:
        vec = ResidualVector(self._values)
        norm = vec.l2_norm()
        return ResidualEvaluation(vector=vec, norm=norm)


class _CallCountEvaluator(ResidualEvaluator):
    """Dummy evaluator that counts how many times evaluate() is called."""

    def __init__(self) -> None:
        self.call_count = 0

    def evaluate(self, state: SystemState) -> ResidualEvaluation:
        self.call_count += 1
        vec = ResidualVector([0.0])
        return ResidualEvaluation(vector=vec, norm=0.0)


# ---------------------------------------------------------------------------
# ResidualVector
# ---------------------------------------------------------------------------


class TestResidualVector:
    def test_construction_empty(self) -> None:
        vec = ResidualVector([])
        assert len(vec) == 0
        assert vec.values == ()

    def test_construction_from_list(self) -> None:
        vec = ResidualVector([1.0, -2.0, 3.0])
        assert vec.values == (1.0, -2.0, 3.0)

    def test_construction_from_tuple(self) -> None:
        vec = ResidualVector((1.0, 2.0))
        assert vec.values == (1.0, 2.0)

    def test_values_are_floats(self) -> None:
        vec = ResidualVector([1, 2, 3])  # ints should be coerced
        for v in vec.values:
            assert isinstance(v, float)

    def test_len(self) -> None:
        vec = ResidualVector([1.0, 2.0, 3.0, 4.0])
        assert len(vec) == 4

    def test_values_property_returns_tuple(self) -> None:
        vec = ResidualVector([1.0, 2.0])
        assert isinstance(vec.values, tuple)

    # --- NaN rejection ---

    def test_rejects_nan(self) -> None:
        with pytest.raises(ValueError, match="not finite"):
            ResidualVector([float("nan")])

    def test_rejects_nan_in_second_position(self) -> None:
        with pytest.raises(ValueError, match="not finite"):
            ResidualVector([0.0, float("nan"), 1.0])

    # --- Infinity rejection ---

    def test_rejects_positive_infinity(self) -> None:
        with pytest.raises(ValueError, match="not finite"):
            ResidualVector([float("inf")])

    def test_rejects_negative_infinity(self) -> None:
        with pytest.raises(ValueError, match="not finite"):
            ResidualVector([float("-inf")])

    # --- Infinity norm ---

    def test_inf_norm_empty(self) -> None:
        vec = ResidualVector([])
        assert vec.inf_norm() == 0.0

    def test_inf_norm_single(self) -> None:
        vec = ResidualVector([3.0])
        assert vec.inf_norm() == pytest.approx(3.0)

    def test_inf_norm_mixed_signs(self) -> None:
        vec = ResidualVector([1.0, -5.0, 3.0])
        assert vec.inf_norm() == pytest.approx(5.0)

    def test_inf_norm_zero(self) -> None:
        vec = ResidualVector([0.0, 0.0, 0.0])
        assert vec.inf_norm() == 0.0

    # --- L2 norm ---

    def test_l2_norm_zero(self) -> None:
        vec = ResidualVector([0.0, 0.0])
        assert vec.l2_norm() == 0.0

    def test_l2_norm_single(self) -> None:
        vec = ResidualVector([4.0])
        assert vec.l2_norm() == pytest.approx(4.0)

    def test_l2_norm_pythagorean(self) -> None:
        vec = ResidualVector([3.0, 4.0])
        assert vec.l2_norm() == pytest.approx(5.0)

    def test_l2_norm_is_finite(self) -> None:
        vec = ResidualVector([1.0, 2.0, 3.0])
        assert math.isfinite(vec.l2_norm())

    # --- Equality and hash ---

    def test_equality_same_values(self) -> None:
        assert ResidualVector([1.0, 2.0]) == ResidualVector([1.0, 2.0])

    def test_inequality_different_values(self) -> None:
        assert ResidualVector([1.0]) != ResidualVector([2.0])

    def test_is_hashable(self) -> None:
        vec = ResidualVector([1.0, 2.0])
        d = {vec: "ok"}
        assert d[ResidualVector([1.0, 2.0])] == "ok"

    # --- Repr ---

    def test_repr(self) -> None:
        vec = ResidualVector([1.0, 2.0])
        assert "ResidualVector" in repr(vec)


# ---------------------------------------------------------------------------
# ResidualEvaluation
# ---------------------------------------------------------------------------


class TestResidualEvaluation:
    def _zero_vec(self, n: int = 3) -> ResidualVector:
        return ResidualVector([0.0] * n)

    def test_construction(self) -> None:
        vec = self._zero_vec(2)
        ev = ResidualEvaluation(vector=vec, norm=0.0)
        assert ev.vector is vec
        assert ev.norm == 0.0
        assert ev.message is None

    def test_construction_with_message(self) -> None:
        vec = self._zero_vec(1)
        ev = ResidualEvaluation(vector=vec, norm=0.0, message="ok")
        assert ev.message == "ok"

    def test_rejects_nan_norm(self) -> None:
        vec = self._zero_vec(1)
        with pytest.raises(ValueError, match="finite"):
            ResidualEvaluation(vector=vec, norm=float("nan"))

    def test_rejects_inf_norm(self) -> None:
        vec = self._zero_vec(1)
        with pytest.raises(ValueError, match="finite"):
            ResidualEvaluation(vector=vec, norm=float("inf"))

    def test_rejects_neg_inf_norm(self) -> None:
        vec = self._zero_vec(1)
        with pytest.raises(ValueError, match="finite"):
            ResidualEvaluation(vector=vec, norm=float("-inf"))

    def test_is_immutable(self) -> None:
        vec = self._zero_vec(1)
        ev = ResidualEvaluation(vector=vec, norm=0.0)
        with pytest.raises((AttributeError, TypeError)):
            ev.norm = 1.0  # type: ignore[misc]

    def test_nonzero_norm_accepted(self) -> None:
        vec = ResidualVector([3.0, 4.0])
        ev = ResidualEvaluation(vector=vec, norm=5.0)
        assert ev.norm == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# ResidualEvaluator (via concrete dummy implementations)
# ---------------------------------------------------------------------------


class TestResidualEvaluator:
    def test_zero_evaluator_returns_evaluation(self) -> None:
        state = _simple_state(3)
        ev = _ZeroEvaluator().evaluate(state)
        assert isinstance(ev, ResidualEvaluation)

    def test_zero_evaluator_returns_zero_norm(self) -> None:
        state = _simple_state(3)
        ev = _ZeroEvaluator().evaluate(state)
        assert ev.norm == pytest.approx(0.0)

    def test_zero_evaluator_residuals_are_all_zero(self) -> None:
        state = _simple_state(3)
        ev = _ZeroEvaluator().evaluate(state)
        assert all(v == 0.0 for v in ev.vector.values)

    def test_constant_evaluator_returns_correct_values(self) -> None:
        state = _simple_state(3)
        ev = _ConstantEvaluator([1.0, 2.0, 3.0]).evaluate(state)
        assert ev.vector.values == (1.0, 2.0, 3.0)

    def test_constant_evaluator_l2_norm(self) -> None:
        state = _simple_state(3)
        ev = _ConstantEvaluator([3.0, 4.0]).evaluate(state)
        assert ev.norm == pytest.approx(5.0)

    def test_evaluator_is_deterministic(self) -> None:
        state = _simple_state(3)
        evaluator = _ConstantEvaluator([1.0, 2.0, 3.0])
        ev1 = evaluator.evaluate(state)
        ev2 = evaluator.evaluate(state)
        assert ev1.vector == ev2.vector
        assert ev1.norm == ev2.norm

    def test_evaluator_does_not_mutate_state(self) -> None:
        state = _simple_state(3)
        original_values = state.values.copy()
        _ZeroEvaluator().evaluate(state)
        assert (state.values == original_values).all()

    def test_abstract_evaluator_cannot_be_instantiated(self) -> None:
        with pytest.raises(TypeError):
            ResidualEvaluator()  # type: ignore[abstract]

    def test_call_count_evaluator_tracks_calls(self) -> None:
        state = _simple_state(1)
        evaluator = _CallCountEvaluator()
        assert evaluator.call_count == 0
        evaluator.evaluate(state)
        assert evaluator.call_count == 1
        evaluator.evaluate(state)
        assert evaluator.call_count == 2


# ---------------------------------------------------------------------------
# Import-boundary assertions
# ---------------------------------------------------------------------------


class TestResidualsImportBoundaries:
    def _imports(self) -> list[str]:
        return _import_lines("mpl_sim.solvers.residuals")

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


class TestNetworkStillDoesNotImportSolvers:
    def test_network_assembly_still_clean(self) -> None:
        imports = _import_lines("mpl_sim.network.assembly")
        assert not any("solvers" in line for line in imports)

    def test_network_topology_still_clean(self) -> None:
        imports = _import_lines("mpl_sim.network.topology")
        assert not any("solvers" in line for line in imports)


class TestComponentsStillDoNotImportSolvers:
    def test_pipe_still_clean(self) -> None:
        imports = _import_lines("mpl_sim.components.pipe")
        assert not any("solvers" in line for line in imports)
