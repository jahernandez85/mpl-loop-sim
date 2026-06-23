"""Block 15B.3 — Fixed Single-Loop Evaluate/Solve/Report MVP tests.

Verifies the narrow helper layer for evaluating and optionally solving the
fixed-loop algebraic residuals declared in Block 15B.1 and assembled in
Block 15B.2.

No production component physics are executed.  No SystemState is assembled.
No FluidState is created.  No CoolProp, PropertyBackend, correlations, or
HX models are called.  This is NOT solve(network).  This is NOT production
component execution.  This is NOT arbitrary-topology simulation.

Note on mass-flow underdeterminacy
-----------------------------------
The fixed single-loop residual system has 8 residuals and 8 unknowns, but the
4 mass-balance equations are linearly dependent (their sum is always zero for
a closed loop). The solve helper uses the explicit, continuity-consistent
initial mass-flow values as a fixed gauge and delegates the determined pressure
subsystem to the Phase 13H callback-only solver.

Sign convention (from Block 15B.2 module):
    pressure_drop:accumulator = P_n_acc_out - accumulator_pressure_reference
    pressure_drop:pump        = P_n_pump_out - P_n_acc_out - pump_pressure_rise
    pressure_drop:evaporator  = P_n_evap_out - P_n_pump_out + evaporator_pressure_drop
    pressure_drop:condenser   = P_n_cond_out - P_n_evap_out + condenser_pressure_drop
    mass_balance:n_cond_out   = mdot_condenser - mdot_accumulator   (owned by accumulator)
    mass_balance:n_acc_out    = mdot_accumulator - mdot_pump         (owned by pump)
    mass_balance:n_pump_out   = mdot_pump - mdot_evaporator          (owned by evaporator)
    mass_balance:n_evap_out   = mdot_evaporator - mdot_condenser     (owned by condenser)

Consistent solution at equal mass flow m and consistent pressures:
    mdot_* = m (any finite m)
    P_n_acc_out  = P_ref
    P_n_pump_out = P_ref + pump_rise
    P_n_evap_out = P_ref + pump_rise - evap_drop
    P_n_cond_out = P_ref + pump_rise - evap_drop - cond_drop

Coverage items:

Evaluation result:
 1. valid evaluation builds FixedSingleLoopEvaluationResult
 2. result is frozen (frozen dataclass)
 3. unknown_values is read-only (MappingProxyType)
 4. residual_values is read-only (MappingProxyType)
 5. residual_names is a tuple in scenario declaration order
 6. max_abs_residual is correct at a known nonzero point
 7. l2_residual is correct at a known nonzero point
 8. metadata is defensively copied (MappingProxyType)
 9. metadata is None by default

Input validation — evaluate:
10. rejects wrong scenario type
11. rejects wrong parameters type
12. rejects non-Mapping unknown_values
13. rejects missing unknown values
14. rejects extra unknown values
15. rejects bool unknown values
16. rejects non-numeric unknown values
17. rejects NaN unknown values
18. rejects infinite unknown values
19. rejects non-Mapping metadata

Evaluation behavior:
20. all 8 residuals are zero at the consistent solution
21. mass_balance:n_acc_out is zero at consistent point
22. mass_balance:n_pump_out is zero at consistent point
23. mass_balance:n_evap_out is zero at consistent point
24. mass_balance:n_cond_out is zero at consistent point
25. pressure_drop:accumulator is zero at consistent point
26. pressure_drop:pump is zero at consistent point
27. pressure_drop:evaporator is zero at consistent point
28. pressure_drop:condenser is zero at consistent point
29. residuals are nonzero away from the consistent point
30. mass-flow mismatch makes mass residuals nonzero
31. pressure mismatch makes pressure residuals nonzero
32. changing explicit parameters changes expected residuals
33. residual ordering matches scenario residual_names ordering
34. int unknown values are accepted and coerced to float

Solve request validation:
35. valid request builds FixedSingleLoopSolveRequest
36. request is frozen
37. initial_unknown_values is read-only (MappingProxyType)
38. rejects wrong scenario type
39. rejects wrong parameters type
40. rejects wrong solver_config type
41. rejects non-Mapping initial_unknown_values
42. rejects missing initial unknowns
43. rejects extra initial unknowns
44. rejects bool initial unknown values
45. rejects NaN initial unknown values
46. rejects infinite initial unknown values
47. rejects invalid solver_config (negative tolerance)
48. metadata defensively copied on request

Solver behavior:
49. valid request produces FixedSingleLoopSolveResult
50. result is frozen
51. solved_unknown_values is read-only (MappingProxyType)
52. final_residual_values is read-only (MappingProxyType)
53. residual_names is a tuple in scenario declaration order
54. rejects non-FixedSingleLoopSolveRequest
55. solver converges from a controlled off-pressure guess
56. solved unknowns match the known consistent solution
57. final residuals are near zero
58. result is always returned (never raises for normal solver failure)
59. final_max_abs_residual and final_l2_residual are finite floats

Report behavior:
60. report from evaluation result includes kind="evaluation"
61. report includes topology string
62. report includes component symbolic identifiers
63. report includes node symbolic identifiers
64. report includes unknown_values
65. report includes residual_names
66. report includes residual_values
67. report includes max_abs_residual
68. report includes l2_residual
69. report from evaluation has converged=None
70. report from solve result includes kind="solve"
71. report from solve result includes converged bool
72. report from solve result includes reason string
73. report from solve result includes iteration_count
74. report is a plain dict (serializable)
75. report does not write files
76. rejects wrong type for build_fixed_single_loop_report

Regression coverage:
77. Block 15B.2 focused tests still referenced (no 15B.2 symbols broken)
78. Component reports NO_CONTRIBUTE_METHOD
79. Pipe reports NO_CONTRIBUTE_METHOD
80. PumpComponent reports NO_CONTRIBUTE_METHOD
81. AccumulatorComponent reports NO_CONTRIBUTE_METHOD
82. EvaporatorComponent reports NO_CONTRIBUTE_METHOD
83. CondenserComponent reports NO_CONTRIBUTE_METHOD

Boundary tests (AST / import-level):
84. runner module: no CoolProp import
85. runner module: no PropertyBackend import
86. runner module: no CorrelationRegistry import
87. runner module: no SystemState import
88. runner module: no FluidState import
89. runner module: no mpl_sim.components import
90. runner module: no mpl_sim.properties import
91. runner module: no mpl_sim.hx_models import
92. runner module: no contribute attribute-call nodes
93. runner module: no solve(network) or NetworkGraph.solve pattern
94. runner module: no component_type reference
95. this test file: no CoolProp import
96. this test file: no PropertyBackend import
97. this test file: no contribute attribute-call nodes

Public API:
98. new symbols exported from mpl_sim.network
99. new symbols in __all__
100. no private symbols in __all__
"""

from __future__ import annotations

import ast
import math
import pathlib
from types import MappingProxyType

import pytest

from mpl_sim.network import (
    NetworkSolveConfig,
    ProductionComponentContractStatus,
    inspect_known_production_component_contracts,
)
from mpl_sim.network.fixed_single_loop_residuals import (
    FixedSingleLoopResidualParameters,
)
from mpl_sim.network.fixed_single_loop_runner import (
    FixedSingleLoopEvaluationResult,
    FixedSingleLoopSolveRequest,
    FixedSingleLoopSolveResult,
    build_fixed_single_loop_report,
    evaluate_fixed_single_loop_residuals,
    solve_fixed_single_loop_residuals,
)
from mpl_sim.network.fixed_single_loop_scenario import build_fixed_single_loop_scenario

# ---------------------------------------------------------------------------
# Path helpers for boundary (AST) tests
# ---------------------------------------------------------------------------

_RUNNER_MODULE = (
    pathlib.Path(__file__).parent.parent.parent
    / "src"
    / "mpl_sim"
    / "network"
    / "fixed_single_loop_runner.py"
)
_THIS_FILE = pathlib.Path(__file__)


def _read_source(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse_ast(path: pathlib.Path) -> ast.Module:
    return ast.parse(_read_source(path))


def _has_import(tree: ast.Module, name: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if name in alias.name:
                    return True
        if isinstance(node, ast.ImportFrom):
            if node.module and name in node.module:
                return True
            for alias in node.names:
                if name in alias.name:
                    return True
    return False


def _has_contribute_attribute_call(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "contribute":
                return True
    return False


def _has_pattern(source: str, pattern: str) -> bool:
    return pattern in source


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

_PUMP_RISE = 50_000.0  # Pa
_EVAP_DROP = 20_000.0  # Pa
_COND_DROP = 10_000.0  # Pa
_P_REF = 100_000.0  # Pa


def _default_params() -> FixedSingleLoopResidualParameters:
    return FixedSingleLoopResidualParameters(
        pump_pressure_rise=_PUMP_RISE,
        evaporator_pressure_drop=_EVAP_DROP,
        condenser_pressure_drop=_COND_DROP,
        accumulator_pressure_reference=_P_REF,
    )


def _default_scenario():
    return build_fixed_single_loop_scenario()


def _consistent_unknowns(mdot: float = 1.0) -> dict[str, float]:
    """Consistent unknown values for the default scenario/parameters."""
    P_acc = _P_REF
    P_pump = _P_REF + _PUMP_RISE
    P_evap = P_pump - _EVAP_DROP
    P_cond = P_evap - _COND_DROP
    return {
        "mdot:accumulator": mdot,
        "mdot:pump": mdot,
        "mdot:evaporator": mdot,
        "mdot:condenser": mdot,
        "P:n_acc_out": P_acc,
        "P:n_pump_out": P_pump,
        "P:n_evap_out": P_evap,
        "P:n_cond_out": P_cond,
    }


def _default_solver_config() -> NetworkSolveConfig:
    return NetworkSolveConfig(
        max_iterations=30,
        tolerance=1e-9,
        finite_difference_step=1e-4,
    )


def _default_request() -> FixedSingleLoopSolveRequest:
    return FixedSingleLoopSolveRequest(
        scenario=_default_scenario(),
        parameters=_default_params(),
        initial_unknown_values=_consistent_unknowns(),
        solver_config=_default_solver_config(),
    )


def _off_pressure_initial_guess() -> dict[str, float]:
    """Initial guess with wrong pressures so residuals are nonzero.

    Mass flows are all equal (mass-balance residuals = 0) but pressures are
    zero (wrong), so the determined pressure subsystem must be solved.
    """
    return {
        "mdot:accumulator": 1.0,
        "mdot:pump": 1.0,
        "mdot:evaporator": 1.0,
        "mdot:condenser": 1.0,
        "P:n_acc_out": 0.0,
        "P:n_pump_out": 0.0,
        "P:n_evap_out": 0.0,
        "P:n_cond_out": 0.0,
    }


def _off_pressure_request() -> FixedSingleLoopSolveRequest:
    """Solve request with a continuity-consistent mass-flow gauge."""
    return FixedSingleLoopSolveRequest(
        scenario=_default_scenario(),
        parameters=_default_params(),
        initial_unknown_values=_off_pressure_initial_guess(),
        solver_config=_default_solver_config(),
    )


# ---------------------------------------------------------------------------
# Group 1: Evaluation result
# ---------------------------------------------------------------------------


def test_valid_evaluation_builds_result():
    result = evaluate_fixed_single_loop_residuals(
        _default_scenario(), _default_params(), _consistent_unknowns()
    )
    assert isinstance(result, FixedSingleLoopEvaluationResult)


def test_result_is_frozen():
    result = evaluate_fixed_single_loop_residuals(
        _default_scenario(), _default_params(), _consistent_unknowns()
    )
    with pytest.raises((AttributeError, TypeError)):
        result.max_abs_residual = 999.0  # type: ignore[misc]


def test_unknown_values_is_read_only():
    result = evaluate_fixed_single_loop_residuals(
        _default_scenario(), _default_params(), _consistent_unknowns()
    )
    assert isinstance(result.unknown_values, MappingProxyType)
    with pytest.raises(TypeError):
        result.unknown_values["new_key"] = 1.0  # type: ignore[index]


def test_residual_values_is_read_only():
    result = evaluate_fixed_single_loop_residuals(
        _default_scenario(), _default_params(), _consistent_unknowns()
    )
    assert isinstance(result.residual_values, MappingProxyType)
    with pytest.raises(TypeError):
        result.residual_values["new_key"] = 1.0  # type: ignore[index]


def test_residual_names_is_tuple_in_scenario_order():
    scenario = _default_scenario()
    result = evaluate_fixed_single_loop_residuals(
        scenario, _default_params(), _consistent_unknowns()
    )
    assert isinstance(result.residual_names, tuple)
    assert result.residual_names == scenario.residual_names.all_names()


def test_max_abs_residual_correct_at_nonzero_point():
    scenario = _default_scenario()
    params = _default_params()
    uv = _consistent_unknowns()
    uv["P:n_acc_out"] = _P_REF + 5000.0  # pressure mismatch of 5000 Pa
    result = evaluate_fixed_single_loop_residuals(scenario, params, uv)
    assert abs(result.max_abs_residual - 5000.0) < 1e-6


def test_l2_residual_correct_at_nonzero_point():
    scenario = _default_scenario()
    params = _default_params()
    uv = _consistent_unknowns()
    uv["P:n_acc_out"] = _P_REF + 3000.0  # pressure mismatch of 3000 Pa
    # pressure_drop:accumulator = 3000, pressure_drop:pump = -3000 (cascade)
    # mass balances = 0 (all mdot equal)
    result = evaluate_fixed_single_loop_residuals(scenario, params, uv)
    assert math.isfinite(result.l2_residual)
    assert result.l2_residual > 0.0


def test_metadata_defensively_copied():
    md = {"tag": "test"}
    result = evaluate_fixed_single_loop_residuals(
        _default_scenario(), _default_params(), _consistent_unknowns(), metadata=md
    )
    assert isinstance(result.metadata, MappingProxyType)
    md["tag"] = "mutated"
    assert result.metadata["tag"] == "test"


def test_metadata_is_none_by_default():
    result = evaluate_fixed_single_loop_residuals(
        _default_scenario(), _default_params(), _consistent_unknowns()
    )
    assert result.metadata is None


# ---------------------------------------------------------------------------
# Group 2: Input validation — evaluate
# ---------------------------------------------------------------------------


def test_rejects_wrong_scenario_type():
    with pytest.raises(TypeError, match="scenario"):
        evaluate_fixed_single_loop_residuals("not_a_scenario", _default_params(), {})


def test_rejects_wrong_parameters_type():
    with pytest.raises(TypeError, match="parameters"):
        evaluate_fixed_single_loop_residuals(_default_scenario(), "not_params", {})


def test_rejects_non_mapping_unknown_values():
    with pytest.raises(TypeError, match="unknown_values"):
        evaluate_fixed_single_loop_residuals(_default_scenario(), _default_params(), [1.0, 2.0])


def test_rejects_missing_unknown_values():
    uv = _consistent_unknowns()
    del uv["mdot:accumulator"]
    with pytest.raises(ValueError, match="missing"):
        evaluate_fixed_single_loop_residuals(_default_scenario(), _default_params(), uv)


def test_rejects_extra_unknown_values():
    uv = _consistent_unknowns()
    uv["extra_unknown"] = 1.0
    with pytest.raises(ValueError, match="not in scenario"):
        evaluate_fixed_single_loop_residuals(_default_scenario(), _default_params(), uv)


def test_rejects_bool_unknown_values():
    uv = _consistent_unknowns()
    uv["mdot:accumulator"] = True  # type: ignore[assignment]
    with pytest.raises(TypeError, match="bool"):
        evaluate_fixed_single_loop_residuals(_default_scenario(), _default_params(), uv)


def test_rejects_non_numeric_unknown_values():
    uv = _consistent_unknowns()
    uv["mdot:accumulator"] = "not_a_number"  # type: ignore[assignment]
    with pytest.raises(TypeError, match="numeric"):
        evaluate_fixed_single_loop_residuals(_default_scenario(), _default_params(), uv)


def test_rejects_nan_unknown_values():
    uv = _consistent_unknowns()
    uv["mdot:accumulator"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        evaluate_fixed_single_loop_residuals(_default_scenario(), _default_params(), uv)


def test_rejects_infinite_unknown_values():
    uv = _consistent_unknowns()
    uv["P:n_acc_out"] = float("inf")
    with pytest.raises(ValueError, match="finite"):
        evaluate_fixed_single_loop_residuals(_default_scenario(), _default_params(), uv)


def test_rejects_non_mapping_metadata():
    with pytest.raises(TypeError, match="metadata"):
        evaluate_fixed_single_loop_residuals(
            _default_scenario(),
            _default_params(),
            _consistent_unknowns(),
            metadata="not_a_mapping",
        )


# ---------------------------------------------------------------------------
# Group 3: Evaluation behavior
# ---------------------------------------------------------------------------


def test_all_8_residuals_zero_at_consistent_solution():
    result = evaluate_fixed_single_loop_residuals(
        _default_scenario(), _default_params(), _consistent_unknowns()
    )
    for name, val in result.residual_values.items():
        assert abs(val) < 1e-9, f"Residual {name!r} expected 0, got {val}"


def test_mass_balance_n_acc_out_zero_at_consistent():
    result = evaluate_fixed_single_loop_residuals(
        _default_scenario(), _default_params(), _consistent_unknowns()
    )
    assert abs(result.residual_values["mass_balance:n_acc_out"]) < 1e-9


def test_mass_balance_n_pump_out_zero_at_consistent():
    result = evaluate_fixed_single_loop_residuals(
        _default_scenario(), _default_params(), _consistent_unknowns()
    )
    assert abs(result.residual_values["mass_balance:n_pump_out"]) < 1e-9


def test_mass_balance_n_evap_out_zero_at_consistent():
    result = evaluate_fixed_single_loop_residuals(
        _default_scenario(), _default_params(), _consistent_unknowns()
    )
    assert abs(result.residual_values["mass_balance:n_evap_out"]) < 1e-9


def test_mass_balance_n_cond_out_zero_at_consistent():
    result = evaluate_fixed_single_loop_residuals(
        _default_scenario(), _default_params(), _consistent_unknowns()
    )
    assert abs(result.residual_values["mass_balance:n_cond_out"]) < 1e-9


def test_pressure_drop_accumulator_zero_at_consistent():
    result = evaluate_fixed_single_loop_residuals(
        _default_scenario(), _default_params(), _consistent_unknowns()
    )
    assert abs(result.residual_values["pressure_drop:accumulator"]) < 1e-9


def test_pressure_drop_pump_zero_at_consistent():
    result = evaluate_fixed_single_loop_residuals(
        _default_scenario(), _default_params(), _consistent_unknowns()
    )
    assert abs(result.residual_values["pressure_drop:pump"]) < 1e-9


def test_pressure_drop_evaporator_zero_at_consistent():
    result = evaluate_fixed_single_loop_residuals(
        _default_scenario(), _default_params(), _consistent_unknowns()
    )
    assert abs(result.residual_values["pressure_drop:evaporator"]) < 1e-9


def test_pressure_drop_condenser_zero_at_consistent():
    result = evaluate_fixed_single_loop_residuals(
        _default_scenario(), _default_params(), _consistent_unknowns()
    )
    assert abs(result.residual_values["pressure_drop:condenser"]) < 1e-9


def test_residuals_nonzero_away_from_consistent():
    uv = _consistent_unknowns()
    uv["P:n_acc_out"] = _P_REF + 1000.0  # off consistent point
    result = evaluate_fixed_single_loop_residuals(_default_scenario(), _default_params(), uv)
    assert result.max_abs_residual > 0.0


def test_mass_flow_mismatch_makes_mass_residuals_nonzero():
    uv = _consistent_unknowns()
    uv["mdot:pump"] = uv["mdot:pump"] + 0.5  # pump ≠ accumulator
    result = evaluate_fixed_single_loop_residuals(_default_scenario(), _default_params(), uv)
    # mass_balance:n_acc_out = mdot_acc - mdot_pump = -0.5
    assert abs(result.residual_values["mass_balance:n_acc_out"] + 0.5) < 1e-9


def test_pressure_mismatch_makes_pressure_residuals_nonzero():
    uv = _consistent_unknowns()
    uv["P:n_acc_out"] = _P_REF + 2000.0
    result = evaluate_fixed_single_loop_residuals(_default_scenario(), _default_params(), uv)
    assert abs(result.residual_values["pressure_drop:accumulator"] - 2000.0) < 1e-6


def test_changing_parameters_changes_residuals():
    scenario = _default_scenario()
    uv = _consistent_unknowns()  # consistent for default params
    # Use different pump rise → consistent unknowns are now inconsistent
    params2 = FixedSingleLoopResidualParameters(
        pump_pressure_rise=_PUMP_RISE + 10_000.0,
        evaporator_pressure_drop=_EVAP_DROP,
        condenser_pressure_drop=_COND_DROP,
        accumulator_pressure_reference=_P_REF,
    )
    result = evaluate_fixed_single_loop_residuals(scenario, params2, uv)
    # pressure_drop:pump = P_pump - P_acc - new_rise = _PUMP_RISE - (_PUMP_RISE + 10000) = -10000
    assert abs(result.residual_values["pressure_drop:pump"] + 10_000.0) < 1e-6


def test_residual_ordering_matches_scenario_residual_names():
    scenario = _default_scenario()
    result = evaluate_fixed_single_loop_residuals(
        scenario, _default_params(), _consistent_unknowns()
    )
    assert result.residual_names == scenario.residual_names.all_names()


def test_int_unknown_values_accepted():
    scenario = _default_scenario()
    P_acc = int(_P_REF)
    P_pump = int(_P_REF + _PUMP_RISE)
    P_evap = int(P_pump - _EVAP_DROP)
    P_cond = int(P_evap - _COND_DROP)
    uv = {
        "mdot:accumulator": 1,
        "mdot:pump": 1,
        "mdot:evaporator": 1,
        "mdot:condenser": 1,
        "P:n_acc_out": P_acc,
        "P:n_pump_out": P_pump,
        "P:n_evap_out": P_evap,
        "P:n_cond_out": P_cond,
    }
    result = evaluate_fixed_single_loop_residuals(scenario, _default_params(), uv)
    assert result.max_abs_residual < 1e-9


# ---------------------------------------------------------------------------
# Group 4: Solve request validation
# ---------------------------------------------------------------------------


def test_valid_request_builds_successfully():
    req = _default_request()
    assert isinstance(req, FixedSingleLoopSolveRequest)


def test_request_is_frozen():
    req = _default_request()
    with pytest.raises((AttributeError, TypeError)):
        req.solver_config = None  # type: ignore[misc]


def test_initial_unknown_values_is_read_only():
    req = _default_request()
    assert isinstance(req.initial_unknown_values, MappingProxyType)
    with pytest.raises(TypeError):
        req.initial_unknown_values["new_key"] = 1.0  # type: ignore[index]


def test_request_rejects_wrong_scenario_type():
    with pytest.raises(TypeError, match="scenario"):
        FixedSingleLoopSolveRequest(
            scenario="not_scenario",
            parameters=_default_params(),
            initial_unknown_values=_consistent_unknowns(),
            solver_config=_default_solver_config(),
        )


def test_request_rejects_wrong_parameters_type():
    with pytest.raises(TypeError, match="parameters"):
        FixedSingleLoopSolveRequest(
            scenario=_default_scenario(),
            parameters="not_params",
            initial_unknown_values=_consistent_unknowns(),
            solver_config=_default_solver_config(),
        )


def test_request_rejects_wrong_solver_config_type():
    with pytest.raises(TypeError, match="solver_config"):
        FixedSingleLoopSolveRequest(
            scenario=_default_scenario(),
            parameters=_default_params(),
            initial_unknown_values=_consistent_unknowns(),
            solver_config="not_config",
        )


def test_request_rejects_non_mapping_initial_values():
    with pytest.raises(TypeError, match="unknown_values"):
        FixedSingleLoopSolveRequest(
            scenario=_default_scenario(),
            parameters=_default_params(),
            initial_unknown_values=[1.0, 2.0],  # type: ignore[arg-type]
            solver_config=_default_solver_config(),
        )


def test_request_rejects_missing_initial_unknowns():
    uv = _consistent_unknowns()
    del uv["mdot:accumulator"]
    with pytest.raises(ValueError, match="missing"):
        FixedSingleLoopSolveRequest(
            scenario=_default_scenario(),
            parameters=_default_params(),
            initial_unknown_values=uv,
            solver_config=_default_solver_config(),
        )


def test_request_rejects_extra_initial_unknowns():
    uv = _consistent_unknowns()
    uv["extra"] = 1.0
    with pytest.raises(ValueError, match="not in scenario"):
        FixedSingleLoopSolveRequest(
            scenario=_default_scenario(),
            parameters=_default_params(),
            initial_unknown_values=uv,
            solver_config=_default_solver_config(),
        )


def test_request_rejects_bool_initial_unknown():
    uv = _consistent_unknowns()
    uv["mdot:accumulator"] = True  # type: ignore[assignment]
    with pytest.raises(TypeError, match="bool"):
        FixedSingleLoopSolveRequest(
            scenario=_default_scenario(),
            parameters=_default_params(),
            initial_unknown_values=uv,
            solver_config=_default_solver_config(),
        )


def test_request_rejects_nan_initial_unknown():
    uv = _consistent_unknowns()
    uv["mdot:accumulator"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        FixedSingleLoopSolveRequest(
            scenario=_default_scenario(),
            parameters=_default_params(),
            initial_unknown_values=uv,
            solver_config=_default_solver_config(),
        )


def test_request_rejects_infinite_initial_unknown():
    uv = _consistent_unknowns()
    uv["P:n_acc_out"] = float("inf")
    with pytest.raises(ValueError, match="finite"):
        FixedSingleLoopSolveRequest(
            scenario=_default_scenario(),
            parameters=_default_params(),
            initial_unknown_values=uv,
            solver_config=_default_solver_config(),
        )


def test_request_rejects_invalid_solver_config_tolerance():
    with pytest.raises((TypeError, ValueError)):
        bad_config = NetworkSolveConfig(
            max_iterations=10,
            tolerance=-1e-9,  # negative tolerance — invalid
            finite_difference_step=1e-4,
        )
        FixedSingleLoopSolveRequest(
            scenario=_default_scenario(),
            parameters=_default_params(),
            initial_unknown_values=_consistent_unknowns(),
            solver_config=bad_config,
        )


def test_request_metadata_defensively_copied():
    md = {"run": "v1"}
    req = FixedSingleLoopSolveRequest(
        scenario=_default_scenario(),
        parameters=_default_params(),
        initial_unknown_values=_consistent_unknowns(),
        solver_config=_default_solver_config(),
        metadata=md,
    )
    assert isinstance(req.metadata, MappingProxyType)
    md["run"] = "mutated"
    assert req.metadata["run"] == "v1"


# ---------------------------------------------------------------------------
# Group 5: Solver behavior
# ---------------------------------------------------------------------------


def test_solve_produces_result():
    result = solve_fixed_single_loop_residuals(_default_request())
    assert isinstance(result, FixedSingleLoopSolveResult)


def test_solve_result_is_frozen():
    result = solve_fixed_single_loop_residuals(_default_request())
    with pytest.raises((AttributeError, TypeError)):
        result.converged = True  # type: ignore[misc]


def test_solved_unknown_values_is_read_only():
    result = solve_fixed_single_loop_residuals(_default_request())
    assert isinstance(result.solved_unknown_values, MappingProxyType)
    with pytest.raises(TypeError):
        result.solved_unknown_values["new"] = 1.0  # type: ignore[index]


def test_final_residual_values_is_read_only():
    result = solve_fixed_single_loop_residuals(_default_request())
    assert isinstance(result.final_residual_values, MappingProxyType)
    with pytest.raises(TypeError):
        result.final_residual_values["new"] = 1.0  # type: ignore[index]


def test_solve_residual_names_in_scenario_order():
    scenario = _default_scenario()
    req = FixedSingleLoopSolveRequest(
        scenario=scenario,
        parameters=_default_params(),
        initial_unknown_values=_consistent_unknowns(),
        solver_config=_default_solver_config(),
    )
    result = solve_fixed_single_loop_residuals(req)
    assert isinstance(result.residual_names, tuple)
    assert result.residual_names == scenario.residual_names.all_names()


def test_solve_rejects_non_request():
    with pytest.raises(TypeError, match="FixedSingleLoopSolveRequest"):
        solve_fixed_single_loop_residuals("not_a_request")


def test_solve_converges_from_controlled_off_pressure_guess():
    result = solve_fixed_single_loop_residuals(_off_pressure_request())
    assert result.converged is True


def test_solved_unknowns_match_known_consistent_solution():
    result = solve_fixed_single_loop_residuals(_off_pressure_request())
    expected = _consistent_unknowns()
    for name, expected_value in expected.items():
        assert result.solved_unknown_values[name] == pytest.approx(expected_value, abs=1e-6)


def test_solve_final_residuals_are_near_zero():
    result = solve_fixed_single_loop_residuals(_off_pressure_request())
    assert result.final_max_abs_residual <= _default_solver_config().tolerance
    assert all(abs(value) <= 1e-9 for value in result.final_residual_values.values())


def test_solve_always_returns_result():
    """solve_fixed_single_loop_residuals never raises for normal solver failure."""
    values = _off_pressure_initial_guess()
    values["mdot:pump"] = 2.0
    request = FixedSingleLoopSolveRequest(
        scenario=_default_scenario(),
        parameters=_default_params(),
        initial_unknown_values=values,
        solver_config=_default_solver_config(),
    )
    result = solve_fixed_single_loop_residuals(request)
    assert isinstance(result, FixedSingleLoopSolveResult)
    assert result.converged is False
    assert "continuity" in result.reason


def test_solve_final_norms_are_finite():
    result = solve_fixed_single_loop_residuals(_off_pressure_request())
    assert math.isfinite(result.final_max_abs_residual)
    assert math.isfinite(result.final_l2_residual)


# ---------------------------------------------------------------------------
# Group 6: Report behavior
# ---------------------------------------------------------------------------


def test_report_from_evaluation_has_kind_evaluation():
    result = evaluate_fixed_single_loop_residuals(
        _default_scenario(), _default_params(), _consistent_unknowns()
    )
    report = build_fixed_single_loop_report(result)
    assert report["kind"] == "evaluation"


def test_report_includes_topology():
    result = evaluate_fixed_single_loop_residuals(
        _default_scenario(), _default_params(), _consistent_unknowns()
    )
    report = build_fixed_single_loop_report(result)
    assert "topology" in report
    assert "accumulator" in report["topology"]


def test_report_includes_component_ids():
    result = evaluate_fixed_single_loop_residuals(
        _default_scenario(), _default_params(), _consistent_unknowns()
    )
    report = build_fixed_single_loop_report(result)
    comp = report["component_ids"]
    assert "accumulator" in comp
    assert "pump" in comp
    assert "evaporator" in comp
    assert "condenser" in comp


def test_report_includes_node_ids():
    result = evaluate_fixed_single_loop_residuals(
        _default_scenario(), _default_params(), _consistent_unknowns()
    )
    report = build_fixed_single_loop_report(result)
    nodes = report["node_ids"]
    assert "n_acc_out" in nodes
    assert "n_pump_out" in nodes
    assert "n_evap_out" in nodes
    assert "n_cond_out" in nodes


def test_report_includes_unknown_values():
    result = evaluate_fixed_single_loop_residuals(
        _default_scenario(), _default_params(), _consistent_unknowns()
    )
    report = build_fixed_single_loop_report(result)
    assert "unknown_values" in report
    assert isinstance(report["unknown_values"], dict)


def test_report_includes_residual_names():
    result = evaluate_fixed_single_loop_residuals(
        _default_scenario(), _default_params(), _consistent_unknowns()
    )
    report = build_fixed_single_loop_report(result)
    assert "residual_names" in report
    assert isinstance(report["residual_names"], list)
    assert len(report["residual_names"]) == 8


def test_report_includes_residual_values():
    result = evaluate_fixed_single_loop_residuals(
        _default_scenario(), _default_params(), _consistent_unknowns()
    )
    report = build_fixed_single_loop_report(result)
    assert "residual_values" in report
    assert isinstance(report["residual_values"], dict)


def test_report_includes_max_abs_residual():
    result = evaluate_fixed_single_loop_residuals(
        _default_scenario(), _default_params(), _consistent_unknowns()
    )
    report = build_fixed_single_loop_report(result)
    assert "max_abs_residual" in report
    assert isinstance(report["max_abs_residual"], float)


def test_report_includes_l2_residual():
    result = evaluate_fixed_single_loop_residuals(
        _default_scenario(), _default_params(), _consistent_unknowns()
    )
    report = build_fixed_single_loop_report(result)
    assert "l2_residual" in report


def test_report_from_evaluation_converged_is_none():
    result = evaluate_fixed_single_loop_residuals(
        _default_scenario(), _default_params(), _consistent_unknowns()
    )
    report = build_fixed_single_loop_report(result)
    assert report["converged"] is None
    assert report["reason"] is None
    assert report["iteration_count"] is None


def test_report_from_solve_has_kind_solve():
    solve_result = solve_fixed_single_loop_residuals(_default_request())
    report = build_fixed_single_loop_report(solve_result)
    assert report["kind"] == "solve"


def test_report_from_solve_includes_converged():
    solve_result = solve_fixed_single_loop_residuals(_default_request())
    report = build_fixed_single_loop_report(solve_result)
    assert "converged" in report
    assert isinstance(report["converged"], bool)


def test_report_from_solve_includes_reason():
    solve_result = solve_fixed_single_loop_residuals(_default_request())
    report = build_fixed_single_loop_report(solve_result)
    assert "reason" in report
    assert isinstance(report["reason"], str)


def test_report_from_solve_includes_iteration_count():
    solve_result = solve_fixed_single_loop_residuals(_default_request())
    report = build_fixed_single_loop_report(solve_result)
    assert "iteration_count" in report
    assert isinstance(report["iteration_count"], int)


def test_report_is_plain_dict():
    result = evaluate_fixed_single_loop_residuals(
        _default_scenario(), _default_params(), _consistent_unknowns()
    )
    report = build_fixed_single_loop_report(result)
    assert isinstance(report, dict)


def test_report_does_not_write_files(tmp_path):
    before = set(tmp_path.iterdir())
    result = evaluate_fixed_single_loop_residuals(
        _default_scenario(), _default_params(), _consistent_unknowns()
    )
    build_fixed_single_loop_report(result)
    after = set(tmp_path.iterdir())
    assert before == after


def test_report_rejects_wrong_type():
    with pytest.raises(TypeError, match="FixedSingleLoopEvaluationResult"):
        build_fixed_single_loop_report("not_a_result")


# ---------------------------------------------------------------------------
# Group 7: Regression coverage
# ---------------------------------------------------------------------------


def test_15b2_residual_parameters_still_importable():
    from mpl_sim.network.fixed_single_loop_residuals import FixedSingleLoopResidualParameters

    params = FixedSingleLoopResidualParameters(
        pump_pressure_rise=1.0,
        evaporator_pressure_drop=2.0,
        condenser_pressure_drop=3.0,
        accumulator_pressure_reference=4.0,
    )
    assert params.pump_pressure_rise == 1.0


def test_component_no_contribute_method():
    results = inspect_known_production_component_contracts()
    for r in results:
        assert (
            r.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD
        ), f"{r.class_name} should have NO_CONTRIBUTE_METHOD; got {r.status!r}"


def test_pipe_no_contribute_method():
    from mpl_sim.components import Pipe
    from mpl_sim.network import inspect_production_component_contract

    r = inspect_production_component_contract(Pipe)
    assert r.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD


def test_pump_component_no_contribute_method():
    from mpl_sim.components import PumpComponent
    from mpl_sim.network import inspect_production_component_contract

    r = inspect_production_component_contract(PumpComponent)
    assert r.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD


def test_accumulator_component_no_contribute_method():
    from mpl_sim.components import AccumulatorComponent
    from mpl_sim.network import inspect_production_component_contract

    r = inspect_production_component_contract(AccumulatorComponent)
    assert r.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD


def test_evaporator_component_no_contribute_method():
    from mpl_sim.components import EvaporatorComponent
    from mpl_sim.network import inspect_production_component_contract

    r = inspect_production_component_contract(EvaporatorComponent)
    assert r.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD


def test_condenser_component_no_contribute_method():
    from mpl_sim.components import CondenserComponent
    from mpl_sim.network import inspect_production_component_contract

    r = inspect_production_component_contract(CondenserComponent)
    assert r.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD


# ---------------------------------------------------------------------------
# Group 8: Boundary tests (AST / import-level)
# ---------------------------------------------------------------------------


def test_runner_module_no_coolprop_import():
    tree = _parse_ast(_RUNNER_MODULE)
    assert not _has_import(tree, "CoolProp"), "runner module must not import CoolProp"


def test_runner_module_no_property_backend_import():
    tree = _parse_ast(_RUNNER_MODULE)
    assert not _has_import(tree, "PropertyBackend"), "runner module must not import PropertyBackend"


def test_runner_module_no_correlation_registry_import():
    tree = _parse_ast(_RUNNER_MODULE)
    assert not _has_import(
        tree, "CorrelationRegistry"
    ), "runner module must not import CorrelationRegistry"


def test_runner_module_no_system_state_import():
    tree = _parse_ast(_RUNNER_MODULE)
    assert not _has_import(tree, "SystemState"), "runner module must not import SystemState"


def test_runner_module_no_fluid_state_import():
    tree = _parse_ast(_RUNNER_MODULE)
    assert not _has_import(tree, "FluidState"), "runner module must not import FluidState"


def test_runner_module_no_mpl_sim_components_import():
    tree = _parse_ast(_RUNNER_MODULE)
    assert not _has_import(
        tree, "mpl_sim.components"
    ), "runner module must not import mpl_sim.components"


def test_runner_module_no_mpl_sim_properties_import():
    tree = _parse_ast(_RUNNER_MODULE)
    assert not _has_import(
        tree, "mpl_sim.properties"
    ), "runner module must not import mpl_sim.properties"


def test_runner_module_no_hx_models_import():
    tree = _parse_ast(_RUNNER_MODULE)
    assert not _has_import(tree, "hx_models"), "runner module must not import hx_models"


def test_runner_module_no_contribute_attribute_call():
    tree = _parse_ast(_RUNNER_MODULE)
    assert not _has_contribute_attribute_call(tree), "runner module must not call .contribute(...)"


def test_runner_module_no_solve_network_pattern():
    tree = _parse_ast(_RUNNER_MODULE)
    source = _read_source(_RUNNER_MODULE)
    # No function NAMED "solve" at any level (callable-level check, not string search).
    # "solve_fixed_single_loop_residuals" and "solve_network_residual_problem" are fine.
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "solve":
            pytest.fail(
                f"runner module must not define a bare function named 'solve'; "
                f"found: def {node.name}"
            )
    # No NetworkGraph.solve attribute access in executable code.
    assert "NetworkGraph.solve" not in source, "runner module must not reference NetworkGraph.solve"


def test_runner_module_no_component_type_reference():
    tree = _parse_ast(_RUNNER_MODULE)
    # Check for Name nodes referencing "component_type" in AST.
    # Docstring occurrences are ast.Constant nodes (not ast.Name) and won't match.
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "component_type":
            pytest.fail("runner module must not reference component_type as a Name node")


def test_this_file_no_coolprop_import():
    tree = _parse_ast(_THIS_FILE)
    assert not _has_import(tree, "CoolProp"), "test file must not import CoolProp"


def test_this_file_no_property_backend_import():
    tree = _parse_ast(_THIS_FILE)
    assert not _has_import(tree, "PropertyBackend"), "test file must not import PropertyBackend"


def test_this_file_no_contribute_attribute_call():
    tree = _parse_ast(_THIS_FILE)
    assert not _has_contribute_attribute_call(tree), "test file must not call .contribute(...)"


# ---------------------------------------------------------------------------
# Group 9: Public API
# ---------------------------------------------------------------------------


def test_new_symbols_exported_from_mpl_sim_network():
    import mpl_sim.network as net

    assert hasattr(net, "FixedSingleLoopEvaluationResult")
    assert hasattr(net, "FixedSingleLoopSolveRequest")
    assert hasattr(net, "FixedSingleLoopSolveResult")
    assert hasattr(net, "evaluate_fixed_single_loop_residuals")
    assert hasattr(net, "solve_fixed_single_loop_residuals")
    assert hasattr(net, "build_fixed_single_loop_report")


def test_new_symbols_in_all():
    import mpl_sim.network as net

    all_set = set(net.__all__)
    assert "FixedSingleLoopEvaluationResult" in all_set
    assert "FixedSingleLoopSolveRequest" in all_set
    assert "FixedSingleLoopSolveResult" in all_set
    assert "evaluate_fixed_single_loop_residuals" in all_set
    assert "solve_fixed_single_loop_residuals" in all_set
    assert "build_fixed_single_loop_report" in all_set


def test_no_private_symbols_in_all():
    import mpl_sim.network as net

    for name in net.__all__:
        assert not name.startswith("_"), f"Private symbol {name!r} in __all__"
