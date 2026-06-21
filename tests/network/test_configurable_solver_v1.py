"""Tests for configurable network solver v1 — Phase 13H.

Tests all 30 required coverage items:
 1  NetworkSolveConfig accepts valid values
 2  Config rejects bool max_iterations
 3  Config rejects non-positive max_iterations
 4  Config rejects invalid tolerance (zero, negative, nan, inf, bool)
 5  Config rejects invalid finite_difference_step (zero, negative, nan, inf, bool)
 6  Solves 1D linear problem
 7  Solves 2D linear problem
 8  Final values close to analytical solution
 9  Final residual norm below tolerance
10  Iteration count deterministic and bounded
11  Final evaluation result is a Phase 13G NetworkResidualEvaluationResult
12  Initial mapping not mutated
13  Assembly not mutated
14  Non-convergence returns converged=False and reason
15  Singular Jacobian returns converged=False and reason
16  Mismatched unknown/residual count rejected before iteration
17  Callback exception propagates
18  Evaluator mismatch handled by Phase 13G validation
19  Scale mismatch handled by Phase 13G validation
20  No solve method on NetworkGraph
21  No automatic component execution
22  No property lookup
23  No registry resolution
24  No CoolProp
25  No SciPy/fsolve/root/least_squares import in solver
26  No contribute( call in solver
27  Unknown values not attached to graph
28  Public exports work from mpl_sim.network
29  Existing Phase 13E/13F/13G tests pass (implicit; regression guard)
30  Docs do not claim automatic physical network simulation
"""

from __future__ import annotations

import math
import pathlib
from dataclasses import FrozenInstanceError

import pytest

from mpl_sim.network import (
    ComponentInstance,
    ComponentInstanceId,
    GraphNode,
    GraphNodeId,
    NetworkGraph,
    NetworkResidualAssembly,
    NetworkResidualDeclaration,
    NetworkResidualEvaluationResult,
    NetworkResidualEvaluator,
    NetworkResidualSet,
    NetworkSolveConfig,
    NetworkSolveResult,
    NetworkUnknownDeclaration,
    NetworkUnknownSet,
    NetworkUnknownValues,
    assemble_network_residuals,
    evaluate_network_residuals,
    solve_network_residual_problem,
)

# ---------------------------------------------------------------------------
# Helpers: minimal assembly builders
# ---------------------------------------------------------------------------

_SOLVER_MODULE = (
    pathlib.Path(__file__).parent.parent.parent / "src" / "mpl_sim" / "network" / "solver.py"
)


def _assembly_1d() -> NetworkResidualAssembly:
    """1 unknown, 1 residual assembly."""
    return NetworkResidualAssembly(
        unknowns=NetworkUnknownSet(unknowns=(NetworkUnknownDeclaration(name="x", unit="kg/s"),)),
        residuals=NetworkResidualSet(
            residuals=(NetworkResidualDeclaration(name="r_x", unit="kg/s"),)
        ),
    )


def _assembly_2d() -> NetworkResidualAssembly:
    """2 unknowns, 2 residuals assembly."""
    return NetworkResidualAssembly(
        unknowns=NetworkUnknownSet(
            unknowns=(
                NetworkUnknownDeclaration(name="x", unit="kg/s"),
                NetworkUnknownDeclaration(name="y", unit="kg/s"),
            )
        ),
        residuals=NetworkResidualSet(
            residuals=(
                NetworkResidualDeclaration(name="r1", unit="kg/s"),
                NetworkResidualDeclaration(name="r2", unit="kg/s"),
            )
        ),
    )


def _assembly_1u_2r() -> NetworkResidualAssembly:
    """Mismatched: 1 unknown, 2 residuals."""
    return NetworkResidualAssembly(
        unknowns=NetworkUnknownSet(unknowns=(NetworkUnknownDeclaration(name="x", unit="kg/s"),)),
        residuals=NetworkResidualSet(
            residuals=(
                NetworkResidualDeclaration(name="r1", unit="kg/s"),
                NetworkResidualDeclaration(name="r2", unit="kg/s"),
            )
        ),
    )


def _default_config(**overrides: object) -> NetworkSolveConfig:
    base = dict(
        max_iterations=100,
        tolerance=1e-10,
        finite_difference_step=1e-6,
    )
    base.update(overrides)
    return NetworkSolveConfig(**base)  # type: ignore[arg-type]


# 1D linear problem: r = x - 5, solution x = 5
_EVAL_1D = [NetworkResidualEvaluator(name="r_x", callback=lambda v: v["x"] - 5.0)]
_SCALES_1D = {"r_x": 1.0}
_INIT_1D = NetworkUnknownValues(values={"x": 0.0})

# 2D linear problem: r1 = x+y-3, r2 = x-y-1, solution x=2, y=1
_EVAL_2D = [
    NetworkResidualEvaluator(name="r1", callback=lambda v: v["x"] + v["y"] - 3.0),
    NetworkResidualEvaluator(name="r2", callback=lambda v: v["x"] - v["y"] - 1.0),
]
_SCALES_2D = {"r1": 1.0, "r2": 1.0}
_INIT_2D = NetworkUnknownValues(values={"x": 0.0, "y": 0.0})


# ---------------------------------------------------------------------------
# 1. Config accepts valid values
# ---------------------------------------------------------------------------


class TestNetworkSolveConfigValid:
    def test_minimal_config(self) -> None:
        cfg = NetworkSolveConfig(
            max_iterations=10,
            tolerance=1e-6,
            finite_difference_step=1e-5,
        )
        assert cfg.max_iterations == 10
        assert cfg.tolerance == 1e-6
        assert cfg.finite_difference_step == 1e-5
        assert cfg.damping == 1.0
        assert cfg.record_history is False

    def test_full_config(self) -> None:
        cfg = NetworkSolveConfig(
            max_iterations=200,
            tolerance=1e-12,
            finite_difference_step=1e-7,
            damping=0.5,
            record_history=True,
        )
        assert cfg.max_iterations == 200
        assert cfg.tolerance == 1e-12
        assert cfg.finite_difference_step == 1e-7
        assert cfg.damping == 0.5
        assert cfg.record_history is True

    def test_max_iterations_1(self) -> None:
        cfg = NetworkSolveConfig(max_iterations=1, tolerance=1.0, finite_difference_step=1e-6)
        assert cfg.max_iterations == 1

    def test_damping_one(self) -> None:
        cfg = NetworkSolveConfig(
            max_iterations=10, tolerance=1e-6, finite_difference_step=1e-5, damping=1.0
        )
        assert cfg.damping == 1.0

    def test_frozen(self) -> None:
        cfg = NetworkSolveConfig(max_iterations=5, tolerance=1e-4, finite_difference_step=1e-6)
        with pytest.raises(FrozenInstanceError):
            cfg.max_iterations = 99  # type: ignore[misc]

    def test_large_tolerance(self) -> None:
        cfg = NetworkSolveConfig(max_iterations=5, tolerance=1e6, finite_difference_step=1e-6)
        assert cfg.tolerance == 1e6

    def test_int_tolerance_accepted(self) -> None:
        cfg = NetworkSolveConfig(max_iterations=5, tolerance=1, finite_difference_step=1)
        assert cfg.tolerance == 1


# ---------------------------------------------------------------------------
# 2. Config rejects bool max_iterations
# ---------------------------------------------------------------------------


class TestConfigRejectsBoolMaxIterations:
    def test_true_rejected(self) -> None:
        with pytest.raises(TypeError, match="max_iterations"):
            NetworkSolveConfig(max_iterations=True, tolerance=1e-6, finite_difference_step=1e-6)

    def test_false_rejected(self) -> None:
        with pytest.raises(TypeError, match="max_iterations"):
            NetworkSolveConfig(max_iterations=False, tolerance=1e-6, finite_difference_step=1e-6)


# ---------------------------------------------------------------------------
# 3. Config rejects non-positive max_iterations
# ---------------------------------------------------------------------------


class TestConfigRejectsNonPositiveMaxIterations:
    def test_zero(self) -> None:
        with pytest.raises(ValueError, match="max_iterations"):
            NetworkSolveConfig(max_iterations=0, tolerance=1e-6, finite_difference_step=1e-6)

    def test_negative(self) -> None:
        with pytest.raises(ValueError, match="max_iterations"):
            NetworkSolveConfig(max_iterations=-1, tolerance=1e-6, finite_difference_step=1e-6)

    def test_large_negative(self) -> None:
        with pytest.raises(ValueError, match="max_iterations"):
            NetworkSolveConfig(max_iterations=-100, tolerance=1e-6, finite_difference_step=1e-6)

    def test_float_not_int(self) -> None:
        with pytest.raises(TypeError, match="max_iterations"):
            NetworkSolveConfig(max_iterations=5.0, tolerance=1e-6, finite_difference_step=1e-6)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 4. Config rejects invalid tolerance
# ---------------------------------------------------------------------------


class TestConfigRejectsInvalidTolerance:
    def test_zero(self) -> None:
        with pytest.raises(ValueError, match="tolerance"):
            NetworkSolveConfig(max_iterations=5, tolerance=0.0, finite_difference_step=1e-6)

    def test_negative(self) -> None:
        with pytest.raises(ValueError, match="tolerance"):
            NetworkSolveConfig(max_iterations=5, tolerance=-1e-6, finite_difference_step=1e-6)

    def test_nan(self) -> None:
        with pytest.raises(ValueError, match="tolerance"):
            NetworkSolveConfig(
                max_iterations=5, tolerance=float("nan"), finite_difference_step=1e-6
            )

    def test_inf(self) -> None:
        with pytest.raises(ValueError, match="tolerance"):
            NetworkSolveConfig(
                max_iterations=5, tolerance=float("inf"), finite_difference_step=1e-6
            )

    def test_bool_true(self) -> None:
        with pytest.raises(TypeError, match="tolerance"):
            NetworkSolveConfig(max_iterations=5, tolerance=True, finite_difference_step=1e-6)  # type: ignore[arg-type]

    def test_bool_false(self) -> None:
        with pytest.raises((TypeError, ValueError)):
            NetworkSolveConfig(max_iterations=5, tolerance=False, finite_difference_step=1e-6)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 5. Config rejects invalid finite_difference_step
# ---------------------------------------------------------------------------


class TestConfigRejectsInvalidFDStep:
    def test_zero(self) -> None:
        with pytest.raises(ValueError, match="finite_difference_step"):
            NetworkSolveConfig(max_iterations=5, tolerance=1e-6, finite_difference_step=0.0)

    def test_negative(self) -> None:
        with pytest.raises(ValueError, match="finite_difference_step"):
            NetworkSolveConfig(max_iterations=5, tolerance=1e-6, finite_difference_step=-1e-6)

    def test_nan(self) -> None:
        with pytest.raises(ValueError, match="finite_difference_step"):
            NetworkSolveConfig(
                max_iterations=5, tolerance=1e-6, finite_difference_step=float("nan")
            )

    def test_inf(self) -> None:
        with pytest.raises(ValueError, match="finite_difference_step"):
            NetworkSolveConfig(
                max_iterations=5, tolerance=1e-6, finite_difference_step=float("inf")
            )

    def test_bool_true(self) -> None:
        with pytest.raises(TypeError, match="finite_difference_step"):
            NetworkSolveConfig(max_iterations=5, tolerance=1e-6, finite_difference_step=True)  # type: ignore[arg-type]

    def test_bool_false(self) -> None:
        with pytest.raises((TypeError, ValueError)):
            NetworkSolveConfig(max_iterations=5, tolerance=1e-6, finite_difference_step=False)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 6. Solves 1D linear problem
# ---------------------------------------------------------------------------


class TestSolve1DLinear:
    def test_solve_x_minus_5(self) -> None:
        result = solve_network_residual_problem(
            _assembly_1d(), _INIT_1D, _EVAL_1D, _SCALES_1D, _default_config()
        )
        assert isinstance(result, NetworkSolveResult)
        assert result.converged

    def test_returns_network_solve_result(self) -> None:
        result = solve_network_residual_problem(
            _assembly_1d(), _INIT_1D, _EVAL_1D, _SCALES_1D, _default_config()
        )
        assert type(result) is NetworkSolveResult

    def test_1d_final_x_close_to_5(self) -> None:
        result = solve_network_residual_problem(
            _assembly_1d(), _INIT_1D, _EVAL_1D, _SCALES_1D, _default_config()
        )
        x_final = result.final_unknown_values.values["x"]
        assert abs(x_final - 5.0) < 1e-8

    def test_1d_initial_values_also_accepted_as_plain_dict(self) -> None:
        result = solve_network_residual_problem(
            _assembly_1d(), {"x": 0.0}, _EVAL_1D, _SCALES_1D, _default_config()
        )
        assert result.converged
        assert abs(result.final_unknown_values.values["x"] - 5.0) < 1e-8


# ---------------------------------------------------------------------------
# 7. Solves 2D linear problem
# ---------------------------------------------------------------------------


class TestSolve2DLinear:
    def test_solve_2d_converges(self) -> None:
        result = solve_network_residual_problem(
            _assembly_2d(), _INIT_2D, _EVAL_2D, _SCALES_2D, _default_config()
        )
        assert result.converged

    def test_2d_x_close_to_2(self) -> None:
        result = solve_network_residual_problem(
            _assembly_2d(), _INIT_2D, _EVAL_2D, _SCALES_2D, _default_config()
        )
        assert abs(result.final_unknown_values.values["x"] - 2.0) < 1e-8

    def test_2d_y_close_to_1(self) -> None:
        result = solve_network_residual_problem(
            _assembly_2d(), _INIT_2D, _EVAL_2D, _SCALES_2D, _default_config()
        )
        assert abs(result.final_unknown_values.values["y"] - 1.0) < 1e-8

    def test_2d_graph_based_assembly(self) -> None:
        """2D solve works with an assembly built from a NetworkGraph.

        A 2-node, 1-component graph with pressure unknowns/residuals enabled
        gives 3 unknowns (mdot:comp, P:n_a, P:n_b) and 3 residuals
        (mass_balance:n_a, mass_balance:n_b, pressure_drop:comp) — a square
        3×3 system that the solver can handle.
        """
        node_a = GraphNode(node_id=GraphNodeId("n_a"))
        node_b = GraphNode(node_id=GraphNodeId("n_b"))
        inst = ComponentInstance(
            instance_id=ComponentInstanceId("comp"),
            component_type="test",
            inlet_node=GraphNodeId("n_a"),
            outlet_node=GraphNodeId("n_b"),
        )
        graph = NetworkGraph(nodes=[node_a, node_b], instances=[inst])
        # With pressure enabled: 3 unknowns, 3 residuals (square system).
        asm = assemble_network_residuals(graph)
        # Use three independent explicit algebraic residuals.
        # Solution: mdot:comp=0.05, P:n_a=200, P:n_b=100.
        # Jacobian is diagonal — non-singular.
        evaluators = [
            NetworkResidualEvaluator(
                name="mass_balance:n_a",
                callback=lambda v: v["mdot:comp"] - 0.05,
            ),
            NetworkResidualEvaluator(
                name="mass_balance:n_b",
                callback=lambda v: v["P:n_a"] - 200.0,
            ),
            NetworkResidualEvaluator(
                name="pressure_drop:comp",
                callback=lambda v: v["P:n_b"] - 100.0,
            ),
        ]
        scales = {
            "mass_balance:n_a": 0.01,
            "mass_balance:n_b": 10.0,
            "pressure_drop:comp": 10.0,
        }
        init = NetworkUnknownValues(values={"mdot:comp": 0.0, "P:n_a": 0.0, "P:n_b": 0.0})
        cfg = _default_config()
        result = solve_network_residual_problem(asm, init, evaluators, scales, cfg)
        assert result.converged
        assert abs(result.final_unknown_values.values["mdot:comp"] - 0.05) < 1e-8
        assert abs(result.final_unknown_values.values["P:n_a"] - 200.0) < 1e-5
        assert abs(result.final_unknown_values.values["P:n_b"] - 100.0) < 1e-5


# ---------------------------------------------------------------------------
# 8. Final values close to analytical solution
# ---------------------------------------------------------------------------


class TestFinalValuesCloseToAnalytical:
    def test_1d_residual_at_solution(self) -> None:
        result = solve_network_residual_problem(
            _assembly_1d(), _INIT_1D, _EVAL_1D, _SCALES_1D, _default_config()
        )
        x = result.final_unknown_values.values["x"]
        assert abs(x - 5.0) < 1e-8

    def test_2d_both_values_close(self) -> None:
        result = solve_network_residual_problem(
            _assembly_2d(), _INIT_2D, _EVAL_2D, _SCALES_2D, _default_config()
        )
        x = result.final_unknown_values.values["x"]
        y = result.final_unknown_values.values["y"]
        assert abs(x - 2.0) < 1e-8
        assert abs(y - 1.0) < 1e-8

    def test_1d_negative_initial_guess(self) -> None:
        init = NetworkUnknownValues(values={"x": -100.0})
        result = solve_network_residual_problem(
            _assembly_1d(), init, _EVAL_1D, _SCALES_1D, _default_config()
        )
        assert result.converged
        assert abs(result.final_unknown_values.values["x"] - 5.0) < 1e-8

    def test_2d_nonzero_initial_guess(self) -> None:
        init = NetworkUnknownValues(values={"x": 10.0, "y": 10.0})
        result = solve_network_residual_problem(
            _assembly_2d(), init, _EVAL_2D, _SCALES_2D, _default_config()
        )
        assert result.converged
        assert abs(result.final_unknown_values.values["x"] - 2.0) < 1e-8
        assert abs(result.final_unknown_values.values["y"] - 1.0) < 1e-8


# ---------------------------------------------------------------------------
# 9. Final residual norm below tolerance
# ---------------------------------------------------------------------------


class TestFinalResidualNorm:
    def test_1d_max_abs_scaled_below_tolerance(self) -> None:
        cfg = _default_config(tolerance=1e-10)
        result = solve_network_residual_problem(_assembly_1d(), _INIT_1D, _EVAL_1D, _SCALES_1D, cfg)
        assert result.converged
        assert result.final_evaluation.max_abs_scaled <= 1e-10

    def test_2d_max_abs_scaled_below_tolerance(self) -> None:
        cfg = _default_config(tolerance=1e-10)
        result = solve_network_residual_problem(_assembly_2d(), _INIT_2D, _EVAL_2D, _SCALES_2D, cfg)
        assert result.converged
        assert result.final_evaluation.max_abs_scaled <= 1e-10

    def test_norm_is_finite(self) -> None:
        result = solve_network_residual_problem(
            _assembly_1d(), _INIT_1D, _EVAL_1D, _SCALES_1D, _default_config()
        )
        assert math.isfinite(result.final_evaluation.max_abs_scaled)

    def test_initial_norm_greater_than_final(self) -> None:
        result = solve_network_residual_problem(
            _assembly_1d(), _INIT_1D, _EVAL_1D, _SCALES_1D, _default_config()
        )
        assert result.initial_evaluation.max_abs_scaled > result.final_evaluation.max_abs_scaled


# ---------------------------------------------------------------------------
# 10. Iteration count deterministic and bounded
# ---------------------------------------------------------------------------


class TestIterationCount:
    def test_1d_converges_in_small_number_of_iterations(self) -> None:
        result = solve_network_residual_problem(
            _assembly_1d(), _INIT_1D, _EVAL_1D, _SCALES_1D, _default_config()
        )
        # Linear problem: Newton converges in 1 iteration
        assert result.iteration_count >= 1
        assert result.iteration_count <= 10

    def test_2d_converges_in_small_number_of_iterations(self) -> None:
        result = solve_network_residual_problem(
            _assembly_2d(), _INIT_2D, _EVAL_2D, _SCALES_2D, _default_config()
        )
        assert result.iteration_count >= 1
        assert result.iteration_count <= 10

    def test_1d_linear_converges_in_few_iterations(self) -> None:
        # For a linear problem Newton converges very quickly (finite-difference
        # Jacobian introduces small floating-point error, so it may take 1-3 steps).
        result = solve_network_residual_problem(
            _assembly_1d(), _INIT_1D, _EVAL_1D, _SCALES_1D, _default_config()
        )
        assert result.iteration_count <= 3

    def test_2d_linear_converges_in_few_iterations(self) -> None:
        result = solve_network_residual_problem(
            _assembly_2d(), _INIT_2D, _EVAL_2D, _SCALES_2D, _default_config()
        )
        assert result.iteration_count <= 3

    def test_already_converged_zero_iterations(self) -> None:
        # Start exactly at the solution.
        init = NetworkUnknownValues(values={"x": 5.0})
        result = solve_network_residual_problem(
            _assembly_1d(), init, _EVAL_1D, _SCALES_1D, _default_config()
        )
        assert result.converged
        assert result.iteration_count == 0

    def test_iteration_count_bounded_by_max_iterations(self) -> None:
        cfg = NetworkSolveConfig(
            max_iterations=3,
            tolerance=1e-20,
            finite_difference_step=1e-6,
        )
        init = NetworkUnknownValues(values={"x": 100.0})
        eval_nl = [NetworkResidualEvaluator(name="r_x", callback=lambda v: v["x"] ** 2 - 2.0)]
        result = solve_network_residual_problem(_assembly_1d(), init, eval_nl, _SCALES_1D, cfg)
        assert result.iteration_count <= 3


# ---------------------------------------------------------------------------
# 11. Final evaluation result is Phase 13G NetworkResidualEvaluationResult
# ---------------------------------------------------------------------------


class TestFinalEvaluationIsPhase13G:
    def test_final_evaluation_type(self) -> None:
        result = solve_network_residual_problem(
            _assembly_1d(), _INIT_1D, _EVAL_1D, _SCALES_1D, _default_config()
        )
        assert isinstance(result.final_evaluation, NetworkResidualEvaluationResult)

    def test_initial_evaluation_type(self) -> None:
        result = solve_network_residual_problem(
            _assembly_1d(), _INIT_1D, _EVAL_1D, _SCALES_1D, _default_config()
        )
        assert isinstance(result.initial_evaluation, NetworkResidualEvaluationResult)

    def test_final_evaluation_has_residual_vector(self) -> None:
        from mpl_sim.closed_loop.residuals import ResidualVector

        result = solve_network_residual_problem(
            _assembly_1d(), _INIT_1D, _EVAL_1D, _SCALES_1D, _default_config()
        )
        assert isinstance(result.final_evaluation.residual_vector, ResidualVector)

    def test_final_evaluation_assembly_is_same(self) -> None:
        asm = _assembly_1d()
        result = solve_network_residual_problem(
            asm, _INIT_1D, _EVAL_1D, _SCALES_1D, _default_config()
        )
        assert result.final_evaluation.assembly is asm

    def test_initial_evaluation_matches_initial_values(self) -> None:
        init = NetworkUnknownValues(values={"x": 0.0})
        result = solve_network_residual_problem(
            _assembly_1d(), init, _EVAL_1D, _SCALES_1D, _default_config()
        )
        # Initial residual at x=0 is r = 0-5 = -5, scaled by 1.0 → max_abs_scaled = 5
        assert abs(result.initial_evaluation.max_abs_scaled - 5.0) < 1e-12

    def test_final_evaluation_unknown_values_match_final(self) -> None:
        result = solve_network_residual_problem(
            _assembly_1d(), _INIT_1D, _EVAL_1D, _SCALES_1D, _default_config()
        )
        assert (
            result.final_evaluation.unknown_values.values["x"]
            == result.final_unknown_values.values["x"]
        )


# ---------------------------------------------------------------------------
# 12. Initial mapping not mutated
# ---------------------------------------------------------------------------


class TestInitialMappingNotMutated:
    def test_plain_dict_not_mutated(self) -> None:
        initial_dict: dict[str, float] = {"x": 0.0}
        solve_network_residual_problem(
            _assembly_1d(), initial_dict, _EVAL_1D, _SCALES_1D, _default_config()
        )
        assert initial_dict == {"x": 0.0}

    def test_network_unknown_values_not_mutated(self) -> None:
        init = NetworkUnknownValues(values={"x": 0.0})
        solve_network_residual_problem(
            _assembly_1d(), init, _EVAL_1D, _SCALES_1D, _default_config()
        )
        assert init.values["x"] == 0.0

    def test_2d_dict_not_mutated(self) -> None:
        initial_dict: dict[str, float] = {"x": 0.0, "y": 0.0}
        solve_network_residual_problem(
            _assembly_2d(), initial_dict, _EVAL_2D, _SCALES_2D, _default_config()
        )
        assert initial_dict == {"x": 0.0, "y": 0.0}


# ---------------------------------------------------------------------------
# 13. Assembly not mutated
# ---------------------------------------------------------------------------


class TestAssemblyNotMutated:
    def test_assembly_summary_unchanged_after_solve(self) -> None:
        asm = _assembly_1d()
        summary_before = asm.summary()
        solve_network_residual_problem(asm, _INIT_1D, _EVAL_1D, _SCALES_1D, _default_config())
        assert asm.summary() == summary_before

    def test_assembly_unknown_names_unchanged(self) -> None:
        asm = _assembly_2d()
        names_before = asm.unknowns.names()
        solve_network_residual_problem(asm, _INIT_2D, _EVAL_2D, _SCALES_2D, _default_config())
        assert asm.unknowns.names() == names_before


# ---------------------------------------------------------------------------
# 14. Non-convergence returns converged=False and reason
# ---------------------------------------------------------------------------


class TestNonConvergence:
    def _nonlinear_eval_1d(self) -> list[NetworkResidualEvaluator]:
        return [NetworkResidualEvaluator(name="r_x", callback=lambda v: v["x"] ** 2 - 2.0)]

    def test_max_iterations_returns_false(self) -> None:
        cfg = NetworkSolveConfig(max_iterations=1, tolerance=1e-15, finite_difference_step=1e-6)
        init = NetworkUnknownValues(values={"x": 10.0})
        result = solve_network_residual_problem(
            _assembly_1d(), init, self._nonlinear_eval_1d(), _SCALES_1D, cfg
        )
        assert not result.converged

    def test_reason_mentions_max_iterations(self) -> None:
        cfg = NetworkSolveConfig(max_iterations=1, tolerance=1e-15, finite_difference_step=1e-6)
        init = NetworkUnknownValues(values={"x": 10.0})
        result = solve_network_residual_problem(
            _assembly_1d(), init, self._nonlinear_eval_1d(), _SCALES_1D, cfg
        )
        assert "max_iterations" in result.reason or "iteration" in result.reason.lower()

    def test_reason_is_non_empty_string(self) -> None:
        cfg = NetworkSolveConfig(max_iterations=2, tolerance=1e-15, finite_difference_step=1e-6)
        init = NetworkUnknownValues(values={"x": 100.0})
        result = solve_network_residual_problem(
            _assembly_1d(), init, self._nonlinear_eval_1d(), _SCALES_1D, cfg
        )
        assert isinstance(result.reason, str)
        assert len(result.reason) > 0

    def test_non_converged_result_still_has_evaluations(self) -> None:
        cfg = NetworkSolveConfig(max_iterations=1, tolerance=1e-15, finite_difference_step=1e-6)
        init = NetworkUnknownValues(values={"x": 10.0})
        result = solve_network_residual_problem(
            _assembly_1d(), init, self._nonlinear_eval_1d(), _SCALES_1D, cfg
        )
        assert isinstance(result.final_evaluation, NetworkResidualEvaluationResult)
        assert isinstance(result.initial_evaluation, NetworkResidualEvaluationResult)

    def test_iteration_count_equals_max_when_exhausted(self) -> None:
        cfg = NetworkSolveConfig(max_iterations=3, tolerance=1e-15, finite_difference_step=1e-6)
        init = NetworkUnknownValues(values={"x": 100.0})
        result = solve_network_residual_problem(
            _assembly_1d(), init, self._nonlinear_eval_1d(), _SCALES_1D, cfg
        )
        assert not result.converged
        assert result.iteration_count == 3


# ---------------------------------------------------------------------------
# 15. Singular Jacobian returns converged=False and reason
# ---------------------------------------------------------------------------


class TestSingularJacobian:
    """Jacobian [[1,1],[1,1]] is singular; solver must return non-converged."""

    _SINGULAR_EVAL = [
        NetworkResidualEvaluator(name="r1", callback=lambda v: v["x"] + v["y"] - 3.0),
        NetworkResidualEvaluator(name="r2", callback=lambda v: v["x"] + v["y"] - 5.0),
    ]
    _SINGULAR_SCALES = {"r1": 1.0, "r2": 1.0}
    _SINGULAR_INIT = NetworkUnknownValues(values={"x": 0.0, "y": 0.0})

    def test_singular_returns_not_converged(self) -> None:
        result = solve_network_residual_problem(
            _assembly_2d(),
            self._SINGULAR_INIT,
            self._SINGULAR_EVAL,
            self._SINGULAR_SCALES,
            _default_config(),
        )
        assert not result.converged

    def test_singular_reason_mentions_singular(self) -> None:
        result = solve_network_residual_problem(
            _assembly_2d(),
            self._SINGULAR_INIT,
            self._SINGULAR_EVAL,
            self._SINGULAR_SCALES,
            _default_config(),
        )
        assert "singular" in result.reason.lower()

    def test_singular_final_evaluation_present(self) -> None:
        result = solve_network_residual_problem(
            _assembly_2d(),
            self._SINGULAR_INIT,
            self._SINGULAR_EVAL,
            self._SINGULAR_SCALES,
            _default_config(),
        )
        assert isinstance(result.final_evaluation, NetworkResidualEvaluationResult)


# ---------------------------------------------------------------------------
# 16. Mismatched unknown/residual count rejected before iteration
# ---------------------------------------------------------------------------


class TestMismatchedCounts:
    def test_1_unknown_2_residual_rejected(self) -> None:
        asm = _assembly_1u_2r()
        init = NetworkUnknownValues(values={"x": 0.0})
        evaluators = [
            NetworkResidualEvaluator(name="r1", callback=lambda v: v["x"] - 1.0),
            NetworkResidualEvaluator(name="r2", callback=lambda v: v["x"] - 2.0),
        ]
        scales = {"r1": 1.0, "r2": 1.0}
        result = solve_network_residual_problem(asm, init, evaluators, scales, _default_config())
        assert not result.converged
        assert "1" in result.reason
        assert "2" in result.reason

    def test_mismatch_returns_solve_result_not_raises(self) -> None:
        asm = _assembly_1u_2r()
        init = NetworkUnknownValues(values={"x": 0.0})
        evaluators = [
            NetworkResidualEvaluator(name="r1", callback=lambda v: v["x"] - 1.0),
            NetworkResidualEvaluator(name="r2", callback=lambda v: v["x"] - 2.0),
        ]
        scales = {"r1": 1.0, "r2": 1.0}
        result = solve_network_residual_problem(asm, init, evaluators, scales, _default_config())
        assert isinstance(result, NetworkSolveResult)
        assert result.iteration_count == 0

    def test_mismatch_initial_evaluation_still_present(self) -> None:
        asm = _assembly_1u_2r()
        init = NetworkUnknownValues(values={"x": 0.0})
        evaluators = [
            NetworkResidualEvaluator(name="r1", callback=lambda v: v["x"] - 1.0),
            NetworkResidualEvaluator(name="r2", callback=lambda v: v["x"] - 2.0),
        ]
        scales = {"r1": 1.0, "r2": 1.0}
        result = solve_network_residual_problem(asm, init, evaluators, scales, _default_config())
        assert isinstance(result.initial_evaluation, NetworkResidualEvaluationResult)


# ---------------------------------------------------------------------------
# 17. Callback exception propagates
# ---------------------------------------------------------------------------


class TestCallbackExceptionPropagates:
    def test_zero_division_propagates(self) -> None:
        def bad_callback(v: object) -> float:
            raise ZeroDivisionError("deliberate error in callback")

        evaluators = [NetworkResidualEvaluator(name="r_x", callback=bad_callback)]
        with pytest.raises(ZeroDivisionError, match="deliberate error"):
            solve_network_residual_problem(
                _assembly_1d(), _INIT_1D, evaluators, _SCALES_1D, _default_config()
            )

    def test_value_error_propagates(self) -> None:
        def bad_callback(v: object) -> float:
            raise ValueError("callback value error")

        evaluators = [NetworkResidualEvaluator(name="r_x", callback=bad_callback)]
        with pytest.raises(ValueError, match="callback value error"):
            solve_network_residual_problem(
                _assembly_1d(), _INIT_1D, evaluators, _SCALES_1D, _default_config()
            )


# ---------------------------------------------------------------------------
# 18. Evaluator mismatch handled by Phase 13G validation
# ---------------------------------------------------------------------------


class TestEvaluatorMismatchHandledByPhase13G:
    def test_extra_evaluator_raises(self) -> None:
        extra_evaluators = _EVAL_1D + [
            NetworkResidualEvaluator(name="extra", callback=lambda v: 0.0)
        ]
        with pytest.raises((ValueError, TypeError)):
            solve_network_residual_problem(
                _assembly_1d(), _INIT_1D, extra_evaluators, _SCALES_1D, _default_config()
            )

    def test_missing_evaluator_raises(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            solve_network_residual_problem(
                _assembly_2d(), _INIT_2D, _EVAL_1D[:1], _SCALES_2D, _default_config()
            )

    def test_wrong_name_evaluator_raises(self) -> None:
        wrong_eval = [NetworkResidualEvaluator(name="wrong_name", callback=lambda v: v["x"] - 5.0)]
        with pytest.raises((ValueError, TypeError)):
            solve_network_residual_problem(
                _assembly_1d(), _INIT_1D, wrong_eval, _SCALES_1D, _default_config()
            )


# ---------------------------------------------------------------------------
# 19. Scale mismatch handled by Phase 13G validation
# ---------------------------------------------------------------------------


class TestScaleMismatchHandledByPhase13G:
    def test_extra_scale_raises(self) -> None:
        extra_scales = {"r_x": 1.0, "extra": 1.0}
        with pytest.raises((ValueError, TypeError)):
            solve_network_residual_problem(
                _assembly_1d(), _INIT_1D, _EVAL_1D, extra_scales, _default_config()
            )

    def test_missing_scale_raises(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            solve_network_residual_problem(
                _assembly_1d(), _INIT_1D, _EVAL_1D, {}, _default_config()
            )

    def test_zero_scale_raises(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            solve_network_residual_problem(
                _assembly_1d(), _INIT_1D, _EVAL_1D, {"r_x": 0.0}, _default_config()
            )


# ---------------------------------------------------------------------------
# 20. No solve method on NetworkGraph
# ---------------------------------------------------------------------------


class TestNoSolveOnNetworkGraph:
    def test_network_graph_has_no_solve_method(self) -> None:
        assert not hasattr(NetworkGraph, "solve")

    def test_network_graph_instance_has_no_solve(self) -> None:
        node_a = GraphNode(node_id=GraphNodeId("n_a"))
        node_b = GraphNode(node_id=GraphNodeId("n_b"))
        inst = ComponentInstance(
            instance_id=ComponentInstanceId("c"),
            component_type="test",
            inlet_node=GraphNodeId("n_a"),
            outlet_node=GraphNodeId("n_b"),
        )
        graph = NetworkGraph(nodes=[node_a, node_b], instances=[inst])
        assert not hasattr(graph, "solve")


# ---------------------------------------------------------------------------
# 21. No automatic component execution
# ---------------------------------------------------------------------------


class TestNoAutomaticComponentExecution:
    def test_solver_uses_explicit_callbacks_not_component_execute(self) -> None:
        import ast

        tree = ast.parse(_SOLVER_MODULE.read_text())
        # The solver must not import or instantiate component types.
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    assert "components" not in module
                    assert "mpl_sim.solvers" not in module
                for alias in node.names:
                    assert alias.name not in (
                        "EvaporatorComponent",
                        "CondenserComponent",
                        "ComponentInstance",
                    )
        # The solver must not call .execute() or .contribute() methods.
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    assert node.func.attr not in ("execute", "contribute")

    def test_result_does_not_expose_component_output(self) -> None:
        result = solve_network_residual_problem(
            _assembly_1d(), _INIT_1D, _EVAL_1D, _SCALES_1D, _default_config()
        )
        assert not hasattr(result, "component_outputs")
        assert not hasattr(result, "hx_results")


# ---------------------------------------------------------------------------
# 22. No property lookup
# ---------------------------------------------------------------------------


class TestNoPropertyLookup:
    def test_solver_has_no_property_backend_import(self) -> None:
        import ast

        tree = ast.parse(_SOLVER_MODULE.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "PropertyBackend" not in alias.name
                    assert "properties" not in alias.name
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert "properties" not in module
                assert "PropertyBackend" not in module
                for alias in node.names:
                    assert alias.name != "PropertyBackend"

    def test_solver_has_no_coolprop_import(self) -> None:
        import ast

        tree = ast.parse(_SOLVER_MODULE.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "coolprop" not in alias.name.lower()
            elif isinstance(node, ast.ImportFrom):
                module = (node.module or "").lower()
                assert "coolprop" not in module

    def test_result_has_no_fluid_state(self) -> None:
        result = solve_network_residual_problem(
            _assembly_1d(), _INIT_1D, _EVAL_1D, _SCALES_1D, _default_config()
        )
        assert not hasattr(result, "fluid_state")
        assert not hasattr(result, "primary_state")


# ---------------------------------------------------------------------------
# 23. No registry resolution
# ---------------------------------------------------------------------------


class TestNoRegistryResolution:
    def test_solver_has_no_correlation_registry_import(self) -> None:
        import ast

        tree = ast.parse(_SOLVER_MODULE.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "CorrelationRegistry" not in alias.name
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    assert alias.name != "CorrelationRegistry"

    def test_solver_has_no_hx_model_registry_import(self) -> None:
        import ast

        tree = ast.parse(_SOLVER_MODULE.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "HeatExchangerModelRegistry" not in alias.name
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    assert alias.name != "HeatExchangerModelRegistry"


# ---------------------------------------------------------------------------
# 24. No CoolProp (boundary)
# ---------------------------------------------------------------------------


class TestNoCoolProp:
    def test_solver_has_no_coolprop_import_ast(self) -> None:
        import ast

        tree = ast.parse(_SOLVER_MODULE.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "coolprop" not in alias.name.lower()
            elif isinstance(node, ast.ImportFrom):
                module = (node.module or "").lower()
                assert "coolprop" not in module

    def test_network_init_has_no_coolprop_import(self) -> None:
        import ast

        init_path = _SOLVER_MODULE.parent / "__init__.py"
        tree = ast.parse(init_path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "coolprop" not in alias.name.lower()
            elif isinstance(node, ast.ImportFrom):
                module = (node.module or "").lower()
                assert "coolprop" not in module


# ---------------------------------------------------------------------------
# 25. No SciPy/fsolve/root/least_squares import in solver
# ---------------------------------------------------------------------------


class TestNoSciPyImport:
    def test_no_scipy_import_ast(self) -> None:
        import ast

        tree = ast.parse(_SOLVER_MODULE.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "scipy" not in alias.name.lower()
            elif isinstance(node, ast.ImportFrom):
                module = (node.module or "").lower()
                assert "scipy" not in module

    def test_no_numpy_import_ast(self) -> None:
        import ast

        tree = ast.parse(_SOLVER_MODULE.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "numpy" not in alias.name.lower()
            elif isinstance(node, ast.ImportFrom):
                module = (node.module or "").lower()
                assert "numpy" not in module

    def test_no_fsolve_in_source(self) -> None:
        import ast

        tree = ast.parse(_SOLVER_MODULE.read_text())
        # fsolve is not an importable symbol we'd call; verify it does not
        # appear as a Name node in the AST (function calls, attributes, etc.).
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                assert node.id not in ("fsolve", "least_squares", "root")

    def test_no_least_squares_import(self) -> None:
        import ast

        tree = ast.parse(_SOLVER_MODULE.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "least_squares" not in alias.name
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    assert alias.name != "least_squares"


# ---------------------------------------------------------------------------
# 26. No contribute( call in solver
# ---------------------------------------------------------------------------


class TestNoContributeCall:
    def test_solver_has_no_contribute_call(self) -> None:
        import ast

        tree = ast.parse(_SOLVER_MODULE.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    assert node.func.attr != "contribute"
                elif isinstance(node.func, ast.Name):
                    assert node.func.id != "contribute"


# ---------------------------------------------------------------------------
# 27. Unknown values not attached to graph
# ---------------------------------------------------------------------------


class TestUnknownValuesNotAttachedToGraph:
    def test_graph_nodes_have_no_value_fields(self) -> None:
        node = GraphNode(node_id=GraphNodeId("n"))
        assert not hasattr(node, "unknown_values")
        assert not hasattr(node, "mdot")
        assert not hasattr(node, "pressure")

    def test_component_instance_has_no_value_fields(self) -> None:
        inst = ComponentInstance(
            instance_id=ComponentInstanceId("c"),
            component_type="test",
            inlet_node=GraphNodeId("n1"),
            outlet_node=GraphNodeId("n2"),
        )
        assert not hasattr(inst, "mdot_value")
        assert not hasattr(inst, "pressure_drop")
        assert not hasattr(inst, "unknown_values")

    def test_solve_does_not_attach_values_to_graph(self) -> None:
        # Build a graph and run a complete solve using the 3×3 square system.
        node_a = GraphNode(node_id=GraphNodeId("n_a"))
        node_b = GraphNode(node_id=GraphNodeId("n_b"))
        inst = ComponentInstance(
            instance_id=ComponentInstanceId("comp"),
            component_type="test",
            inlet_node=GraphNodeId("n_a"),
            outlet_node=GraphNodeId("n_b"),
        )
        graph = NetworkGraph(nodes=[node_a, node_b], instances=[inst])
        asm = assemble_network_residuals(graph)
        evaluators = [
            NetworkResidualEvaluator(
                name="mass_balance:n_a",
                callback=lambda v: v["mdot:comp"] - 0.05,
            ),
            NetworkResidualEvaluator(
                name="mass_balance:n_b",
                callback=lambda v: v["P:n_a"] - 200.0,
            ),
            NetworkResidualEvaluator(
                name="pressure_drop:comp",
                callback=lambda v: v["P:n_b"] - 100.0,
            ),
        ]
        scales = {
            "mass_balance:n_a": 0.01,
            "mass_balance:n_b": 10.0,
            "pressure_drop:comp": 10.0,
        }
        init = NetworkUnknownValues(values={"mdot:comp": 0.0, "P:n_a": 0.0, "P:n_b": 0.0})
        result = solve_network_residual_problem(asm, init, evaluators, scales, _default_config())
        assert result.converged
        # After a successful solve, graph nodes still have no physical values attached.
        for node in graph.nodes():
            assert not hasattr(node, "mdot")
            assert not hasattr(node, "pressure")
            assert not hasattr(node, "unknown_values")


# ---------------------------------------------------------------------------
# 28. Public exports work from mpl_sim.network
# ---------------------------------------------------------------------------


class TestPublicExports:
    def test_network_solve_config_importable(self) -> None:
        from mpl_sim.network import NetworkSolveConfig as NSC

        assert NSC is NetworkSolveConfig

    def test_network_solve_result_importable(self) -> None:
        from mpl_sim.network import NetworkSolveResult as NSR

        assert NSR is NetworkSolveResult

    def test_solve_network_residual_problem_importable(self) -> None:
        from mpl_sim.network import solve_network_residual_problem as snrp

        assert snrp is solve_network_residual_problem

    def test_all_exports_in_dunder_all(self) -> None:
        import mpl_sim.network as net

        assert "NetworkSolveConfig" in net.__all__
        assert "NetworkSolveResult" in net.__all__
        assert "solve_network_residual_problem" in net.__all__

    def test_prior_phase_exports_still_present(self) -> None:
        from mpl_sim.network import (
            ComponentInstance,
            ComponentInstanceId,
            GraphNode,
            GraphNodeId,
            NetworkGraph,
            NetworkResidualAssembly,
            NetworkResidualEvaluationResult,
            NetworkResidualEvaluator,
            NetworkUnknownValues,
            assemble_network_residuals,
            evaluate_network_residuals,
        )

        assert all(
            obj is not None
            for obj in [
                ComponentInstance,
                ComponentInstanceId,
                GraphNode,
                GraphNodeId,
                NetworkGraph,
                NetworkResidualAssembly,
                NetworkResidualEvaluationResult,
                NetworkResidualEvaluator,
                NetworkUnknownValues,
                assemble_network_residuals,
                evaluate_network_residuals,
            ]
        )


# ---------------------------------------------------------------------------
# 29. Regression guard: existing Phase 13E/13F/13G still functional
# ---------------------------------------------------------------------------


class TestPhase13EFGRegression:
    def test_network_graph_still_builds(self) -> None:
        # Self-loop should still raise (Phase 13E behaviour unchanged).
        with pytest.raises(ValueError):
            ComponentInstance(
                instance_id=ComponentInstanceId("c"),
                component_type="test",
                inlet_node=GraphNodeId("n"),
                outlet_node=GraphNodeId("n"),
            )
        # Valid graph still builds.
        node_a = GraphNode(node_id=GraphNodeId("a"))
        node_b = GraphNode(node_id=GraphNodeId("b"))
        inst2 = ComponentInstance(
            instance_id=ComponentInstanceId("c2"),
            component_type="pump",
            inlet_node=GraphNodeId("a"),
            outlet_node=GraphNodeId("b"),
        )
        graph = NetworkGraph(nodes=[node_a, node_b], instances=[inst2])
        assert graph.nodes()[0].node_id.value == "a"

    def test_residual_assembly_still_works(self) -> None:
        node_a = GraphNode(node_id=GraphNodeId("x"))
        node_b = GraphNode(node_id=GraphNodeId("y"))
        inst = ComponentInstance(
            instance_id=ComponentInstanceId("comp"),
            component_type="test",
            inlet_node=GraphNodeId("x"),
            outlet_node=GraphNodeId("y"),
        )
        graph = NetworkGraph(nodes=[node_a, node_b], instances=[inst])
        asm = assemble_network_residuals(
            graph, include_pressure_unknowns=False, include_pressure_residuals=False
        )
        assert asm.unknowns.count() == 1
        assert asm.residuals.count() == 2

    def test_evaluate_network_residuals_still_works(self) -> None:
        asm = _assembly_1d()
        uv = NetworkUnknownValues(values={"x": 5.0})
        ev = [NetworkResidualEvaluator(name="r_x", callback=lambda v: v["x"] - 5.0)]
        scales = {"r_x": 1.0}
        result = evaluate_network_residuals(asm, uv, ev, scales)
        assert isinstance(result, NetworkResidualEvaluationResult)
        assert result.max_abs_scaled == 0.0


# ---------------------------------------------------------------------------
# 30. Docs do not claim automatic physical network simulation
# ---------------------------------------------------------------------------


class TestDocsHonestClaims:
    def test_solver_module_docstring_says_not_physical(self) -> None:
        solver_src = _SOLVER_MODULE.read_text()
        assert "MUST NOT construct residuals automatically from component physics" in solver_src

    def test_solver_module_does_not_claim_mpl_simulator(self) -> None:
        solver_src = _SOLVER_MODULE.read_text()
        assert "MPL simulator" not in solver_src
        assert "validated model" not in solver_src
        assert "validated against experiment" not in solver_src

    def test_concepts_doc_marks_phase_13h_implemented(self) -> None:
        concepts_path = (
            pathlib.Path(__file__).parent.parent.parent / "docs" / "user_guide" / "CONCEPTS.md"
        )
        content = concepts_path.read_text()
        assert "Phase 13H" in content

    def test_concepts_doc_says_not_physical_simulator(self) -> None:
        concepts_path = (
            pathlib.Path(__file__).parent.parent.parent / "docs" / "user_guide" / "CONCEPTS.md"
        )
        content = concepts_path.read_text()
        # CONCEPTS.md must clarify that Phase 13H is not a physical simulator.
        assert "does not construct residuals from physical components" in content
        assert (
            "not the full MPL simulator" in content
            or "not implement the full MPL simulator" in content
        )

    def test_history_recording_works_when_enabled(self) -> None:
        cfg = NetworkSolveConfig(
            max_iterations=100,
            tolerance=1e-10,
            finite_difference_step=1e-6,
            record_history=True,
        )
        result = solve_network_residual_problem(_assembly_1d(), _INIT_1D, _EVAL_1D, _SCALES_1D, cfg)
        assert result.converged
        assert result.residual_norm_history is not None
        assert isinstance(result.residual_norm_history, tuple)
        assert len(result.residual_norm_history) == result.iteration_count
        assert all(math.isfinite(v) for v in result.residual_norm_history)

    def test_history_is_none_when_disabled(self) -> None:
        cfg = _default_config(record_history=False)
        result = solve_network_residual_problem(_assembly_1d(), _INIT_1D, _EVAL_1D, _SCALES_1D, cfg)
        assert result.residual_norm_history is None

    def test_type_error_for_wrong_config(self) -> None:
        with pytest.raises(TypeError, match="config"):
            solve_network_residual_problem(
                _assembly_1d(), _INIT_1D, _EVAL_1D, _SCALES_1D, "not a config"
            )

    def test_type_error_for_wrong_assembly(self) -> None:
        cfg = _default_config()
        with pytest.raises(TypeError, match="assembly"):
            solve_network_residual_problem("not an assembly", _INIT_1D, _EVAL_1D, _SCALES_1D, cfg)

    def test_type_error_for_wrong_initial_values(self) -> None:
        cfg = _default_config()
        with pytest.raises(TypeError, match="initial_values"):
            solve_network_residual_problem(_assembly_1d(), 42, _EVAL_1D, _SCALES_1D, cfg)
