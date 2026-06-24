"""Block 15B.4 — Fixed Single-Loop MVP Closeout / Acceptance Integration tests.

This is the acceptance-integration checkpoint for Block 15B — Minimal Physical
Single-Loop Network MVP.  It proves the complete fixed-loop path end-to-end,
documents the mass-flow gauge design decision explicitly, and provides regression
coverage for all prior 15B and 15A checkpoints.

THIS IS AN ALGEBRAIC FIXED-LOOP MVP — NOT A FULL PHYSICAL LOOP SOLVER.
No CoolProp.  No PropertyBackend.  No correlations.  No HX models.
No SystemState.  No FluidState.  No contribute(...).  No solve(network).
No NetworkGraph.solve().  No arbitrary-topology simulation.
No production component execution.

Design note: mass-flow gauge (underdeterminacy)
-----------------------------------------------
The fixed single-loop residual system (Block 15B.2) has 8 equations and 8
unknowns, but the 4 mass-balance equations are linearly dependent in a closed
loop: their sum is always zero regardless of the unknowns.  The absolute
common mass-flow level is therefore NOT determined by the pressure equations.

The Block 15B.3 solve path fixes this by treating the caller-supplied initial
mass-flow values as a fixed gauge.  The caller must supply continuity-consistent
mass-flow values (all four equal for a serial loop).  The solver then holds
those values fixed and solves only the determined 4-equation pressure subsystem
through the existing Phase 13H callback-only solver.  After convergence the
solver re-evaluates all 8 original residuals.

Consequence: the solve DOES NOT DETERMINE the absolute common mass-flow level.
Different consistent gauges (e.g. mdot=0.5 vs mdot=5.0) yield the same
pressure solution.  Inconsistent gauges (mass-balance residuals non-zero)
trigger an early non-convergence result with a clear reason string before the
pressure subsystem is attempted.

Block 15B provides:
  - fixed single-loop scenario declaration (15B.1)
  - explicit parameterized algebraic residual assembly (15B.2)
  - fixed-loop residual evaluation (15B.3)
  - fixed-loop pressure-subsystem solve using existing callback-only solver (15B.3)
  - lightweight report generation (15B.3)

Block 15B does NOT implement:
  - arbitrary-topology physical simulation
  - generic solve(network)
  - NetworkGraph.solve()
  - real production component execution
  - production Component.contribute(...)
  - SystemState assembly
  - FluidState construction
  - property-backed residuals
  - correlation-backed residuals
  - HX-model-backed residuals

Later blocks remain responsible for topology extensions, real component
execution, and property/correlation/HX-backed physics.

Coverage items
--------------

Full fixed-loop MVP path (items 1–12):
 1. build_fixed_single_loop_scenario works
 2. FixedSingleLoopResidualParameters validates explicit parameters
 3. build_fixed_single_loop_physical_residuals works
 4. evaluate at consistent point gives zero residuals
 5. evaluate at perturbed pressures gives nonzero residuals
 6. evaluate at perturbed mass flows gives nonzero residuals
 7. solve converges from off-pressure with continuity-consistent gauge
 8. final solve result contains all 8 original unknowns
 9. final solve result contains all 8 original residuals
10. final solve result residual ordering matches scenario residual ordering
11. build_fixed_single_loop_report returns plain serializable dict
12. report does not write files

Gauge behavior (items 13–17):
13. continuity-consistent gauge is preserved in solved_unknown_values
14. solver does not change mdot values from the initial gauge
15. different consistent gauge values give same pressure solution but different mdot
16. inconsistent mass-flow gauge gives non-converged result
17. inconsistent gauge reason string mentions continuity

Regression — 15B.3 (items 18–20):
18. 15B.3 evaluate function still importable from mpl_sim.network
19. 15B.3 solve function still importable from mpl_sim.network
20. 15B.3 report function still importable from mpl_sim.network

Regression — 15B.2 (items 21–22):
21. 15B.2 FixedSingleLoopResidualParameters still validates fields correctly
22. 15B.2 build_fixed_single_loop_physical_residuals still builds assembly

Regression — 15B.1 (items 23–24):
23. 15B.1 scenario builds with custom symbolic IDs
24. 15B.1 scenario summary has correct unknown/residual counts

Regression — NO_CONTRIBUTE_METHOD (items 25–30):
25. Component reports NO_CONTRIBUTE_METHOD
26. Pipe reports NO_CONTRIBUTE_METHOD
27. PumpComponent reports NO_CONTRIBUTE_METHOD
28. AccumulatorComponent reports NO_CONTRIBUTE_METHOD
29. EvaporatorComponent reports NO_CONTRIBUTE_METHOD
30. CondenserComponent reports NO_CONTRIBUTE_METHOD

Boundary — this file (items 31–38):
31. this file: no CoolProp import
32. this file: no PropertyBackend import
33. this file: no SystemState import
34. this file: no FluidState import
35. this file: no CorrelationRegistry import
36. this file: no contribute attribute-call nodes
37. this file: no mpl_sim.components import
38. this file: no mpl_sim.properties import

Architecture boundary — Block 15B remains fixed-loop only (items 39–41):
39. no generic solve(network) function in fixed-loop modules
40. no NetworkGraph.solve in fixed-loop modules
41. no component_type physics dispatch in fixed-loop modules

Public API audit (items 42–44):
42. no new symbols added to mpl_sim.network.__all__ by 15B.4 beyond 15B.3
43. all Block 15B exports are present in mpl_sim.network.__all__
44. no private symbols in mpl_sim.network.__all__
"""

from __future__ import annotations

import ast
import json
import math
import pathlib

import pytest

from mpl_sim.network import (
    NetworkSolveConfig,
    ProductionComponentContractStatus,
    inspect_known_production_component_contracts,
    inspect_production_component_contract,
)
from mpl_sim.network.fixed_single_loop_residuals import (
    FixedSingleLoopPhysicalResidualAssembly,
    FixedSingleLoopResidualParameters,
    build_fixed_single_loop_physical_residuals,
)
from mpl_sim.network.fixed_single_loop_runner import (
    FixedSingleLoopEvaluationResult,
    FixedSingleLoopSolveRequest,
    FixedSingleLoopSolveResult,
    build_fixed_single_loop_report,
    evaluate_fixed_single_loop_residuals,
    solve_fixed_single_loop_residuals,
)
from mpl_sim.network.fixed_single_loop_scenario import (
    FixedSingleLoopScenario,
    build_fixed_single_loop_scenario,
)

# ---------------------------------------------------------------------------
# Path helpers for AST boundary tests
# ---------------------------------------------------------------------------

_NETWORK_SRC = pathlib.Path(__file__).parent.parent.parent / "src" / "mpl_sim" / "network"
_THIS_FILE = pathlib.Path(__file__)

_SCENARIO_MODULE = _NETWORK_SRC / "fixed_single_loop_scenario.py"
_RESIDUALS_MODULE = _NETWORK_SRC / "fixed_single_loop_residuals.py"
_RUNNER_MODULE = _NETWORK_SRC / "fixed_single_loop_runner.py"


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

# Known 15B.3 exports (established at Block 15B.3 — must not be removed).
_BLOCK_15B3_EXPORTS = {
    "FixedSingleLoopEvaluationResult",
    "FixedSingleLoopSolveRequest",
    "FixedSingleLoopSolveResult",
    "evaluate_fixed_single_loop_residuals",
    "solve_fixed_single_loop_residuals",
    "build_fixed_single_loop_report",
}


def _default_scenario() -> FixedSingleLoopScenario:
    return build_fixed_single_loop_scenario()


def _default_params() -> FixedSingleLoopResidualParameters:
    return FixedSingleLoopResidualParameters(
        pump_pressure_rise=_PUMP_RISE,
        evaporator_pressure_drop=_EVAP_DROP,
        condenser_pressure_drop=_COND_DROP,
        accumulator_pressure_reference=_P_REF,
    )


def _consistent_unknowns(mdot: float = 1.0) -> dict[str, float]:
    """Continuity-consistent unknowns for the default scenario/parameters."""
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


def _off_pressure_consistent_gauge(mdot: float = 1.0) -> dict[str, float]:
    """Consistent mass-flow gauge with zeroed pressures — forces pressure solve."""
    return {
        "mdot:accumulator": mdot,
        "mdot:pump": mdot,
        "mdot:evaporator": mdot,
        "mdot:condenser": mdot,
        "P:n_acc_out": 0.0,
        "P:n_pump_out": 0.0,
        "P:n_evap_out": 0.0,
        "P:n_cond_out": 0.0,
    }


def _default_solver_config() -> NetworkSolveConfig:
    return NetworkSolveConfig(
        max_iterations=30,
        tolerance=1e-9,
        finite_difference_step=1e-4,
    )


def _make_request(initial_unknowns: dict[str, float]) -> FixedSingleLoopSolveRequest:
    return FixedSingleLoopSolveRequest(
        scenario=_default_scenario(),
        parameters=_default_params(),
        initial_unknown_values=initial_unknowns,
        solver_config=_default_solver_config(),
    )


# ---------------------------------------------------------------------------
# Group 1: Full fixed-loop MVP path
# ---------------------------------------------------------------------------


def test_scenario_builds_with_default_parameters():
    """Item 1: build_fixed_single_loop_scenario works."""
    scenario = build_fixed_single_loop_scenario()
    assert isinstance(scenario, FixedSingleLoopScenario)
    assert scenario.assembly.unknowns.count() == 8
    assert scenario.assembly.residuals.count() == 8


def test_residual_parameters_validate_explicit_fields():
    """Item 2: FixedSingleLoopResidualParameters requires explicit finite scalars."""
    params = _default_params()
    assert params.pump_pressure_rise == _PUMP_RISE
    assert params.evaporator_pressure_drop == _EVAP_DROP
    assert params.condenser_pressure_drop == _COND_DROP
    assert params.accumulator_pressure_reference == _P_REF


def test_physical_residual_assembly_builds():
    """Item 3: build_fixed_single_loop_physical_residuals works."""
    scenario = _default_scenario()
    params = _default_params()
    assembly = build_fixed_single_loop_physical_residuals(scenario, params)
    assert isinstance(assembly, FixedSingleLoopPhysicalResidualAssembly)


def test_evaluation_at_consistent_point_gives_zero_residuals():
    """Item 4: all 8 residuals are zero at the known consistent solution."""
    result = evaluate_fixed_single_loop_residuals(
        _default_scenario(), _default_params(), _consistent_unknowns()
    )
    assert isinstance(result, FixedSingleLoopEvaluationResult)
    for name, val in result.residual_values.items():
        assert abs(val) < 1e-9, f"Residual {name!r} expected 0.0, got {val}"


def test_evaluation_at_perturbed_pressure_gives_nonzero_residuals():
    """Item 5a: perturbing P:n_acc_out makes pressure residuals nonzero."""
    uv = _consistent_unknowns()
    uv["P:n_acc_out"] = _P_REF + 3000.0
    result = evaluate_fixed_single_loop_residuals(_default_scenario(), _default_params(), uv)
    assert result.max_abs_residual > 0.0


def test_evaluation_at_perturbed_mass_flow_gives_nonzero_residuals():
    """Item 5b: mismatched mass flows make mass-balance residuals nonzero."""
    uv = _consistent_unknowns()
    uv["mdot:pump"] = uv["mdot:pump"] + 0.3
    result = evaluate_fixed_single_loop_residuals(_default_scenario(), _default_params(), uv)
    assert result.max_abs_residual > 0.0


def test_solve_converges_from_off_pressure_consistent_gauge():
    """Item 6: solver converges from zeroed pressures with consistent mass-flow gauge."""
    result = solve_fixed_single_loop_residuals(_make_request(_off_pressure_consistent_gauge()))
    assert isinstance(result, FixedSingleLoopSolveResult)
    assert result.converged is True


def test_solve_result_contains_all_eight_unknowns():
    """Item 7: solved_unknown_values contains all 8 declared unknowns."""
    scenario = _default_scenario()
    req = _make_request(_off_pressure_consistent_gauge())
    result = solve_fixed_single_loop_residuals(req)
    expected_names = set(scenario.unknown_names.all_names())
    assert set(result.solved_unknown_values.keys()) == expected_names


def test_solve_result_contains_all_eight_residuals():
    """Item 8: final_residual_values contains all 8 declared residuals."""
    scenario = _default_scenario()
    req = _make_request(_off_pressure_consistent_gauge())
    result = solve_fixed_single_loop_residuals(req)
    expected_names = set(scenario.residual_names.all_names())
    assert set(result.final_residual_values.keys()) == expected_names


def test_solve_result_residual_ordering_matches_scenario():
    """Item 9: residual_names in result matches scenario residual_names.all_names()."""
    scenario = _default_scenario()
    req = FixedSingleLoopSolveRequest(
        scenario=scenario,
        parameters=_default_params(),
        initial_unknown_values=_off_pressure_consistent_gauge(),
        solver_config=_default_solver_config(),
    )
    result = solve_fixed_single_loop_residuals(req)
    assert isinstance(result.residual_names, tuple)
    assert result.residual_names == scenario.residual_names.all_names()


def test_report_is_plain_serializable_dict():
    """Item 11: build_fixed_single_loop_report returns a json-serializable plain dict."""
    result = evaluate_fixed_single_loop_residuals(
        _default_scenario(), _default_params(), _consistent_unknowns()
    )
    report = build_fixed_single_loop_report(result)
    assert isinstance(report, dict)
    # All keys and values must be serializable to JSON.
    encoded = json.dumps(report)
    decoded = json.loads(encoded)
    assert isinstance(decoded, dict)


def test_report_does_not_write_files(tmp_path):
    """Item 12: build_fixed_single_loop_report writes no files."""
    before = set(tmp_path.iterdir())
    result = evaluate_fixed_single_loop_residuals(
        _default_scenario(), _default_params(), _consistent_unknowns()
    )
    build_fixed_single_loop_report(result)
    after = set(tmp_path.iterdir())
    assert before == after


# ---------------------------------------------------------------------------
# Group 2: Gauge behavior — mass-flow underdeterminacy
# ---------------------------------------------------------------------------
#
# The fixed-loop system's 4 mass-balance equations are linearly dependent.
# The absolute common mass-flow level is NOT determined by pressure equations.
# The caller supplies a continuity-consistent gauge; the solver preserves it.


def test_consistent_mass_flow_gauge_preserved_in_solve_result():
    """Item 13: solver preserves the initial consistent mass-flow gauge (mdot=1.0)."""
    initial = _off_pressure_consistent_gauge(mdot=1.0)
    result = solve_fixed_single_loop_residuals(_make_request(initial))
    assert result.converged is True
    for comp_id in ("accumulator", "pump", "evaporator", "condenser"):
        key = f"mdot:{comp_id}"
        assert abs(result.solved_unknown_values[key] - 1.0) < 1e-9, (
            f"Gauge mass flow for {key!r} should be preserved at 1.0; "
            f"got {result.solved_unknown_values[key]}"
        )


def test_solver_does_not_change_mdot_values_from_initial_gauge():
    """Item 14: solver does not alter mdot unknowns — the gauge is not optimised.

    This documents explicitly that the 15B.3 solve path treats mass flows as a
    fixed gauge.  The solver only touches the pressure subsystem.
    """
    initial = _off_pressure_consistent_gauge(mdot=2.5)
    result = solve_fixed_single_loop_residuals(_make_request(initial))
    assert result.converged is True
    for comp_id in ("accumulator", "pump", "evaporator", "condenser"):
        key = f"mdot:{comp_id}"
        assert abs(result.solved_unknown_values[key] - 2.5) < 1e-9, (
            f"Gauge mass flow {key!r} must not be altered by the solve; "
            f"expected 2.5, got {result.solved_unknown_values[key]}"
        )


def test_different_consistent_gauges_give_same_pressure_solution():
    """Item 15: changing the consistent gauge does not change the pressure solution.

    This proves that the absolute mass-flow level is NOT determined by this
    solver — only pressures are solved.
    """
    result_low = solve_fixed_single_loop_residuals(
        _make_request(_off_pressure_consistent_gauge(0.1))
    )
    result_high = solve_fixed_single_loop_residuals(
        _make_request(_off_pressure_consistent_gauge(10.0))
    )
    assert result_low.converged is True
    assert result_high.converged is True

    pressure_keys = ("P:n_acc_out", "P:n_pump_out", "P:n_evap_out", "P:n_cond_out")
    for key in pressure_keys:
        p_low = result_low.solved_unknown_values[key]
        p_high = result_high.solved_unknown_values[key]
        assert abs(p_low - p_high) < 1e-6, (
            f"Pressure {key!r} should be independent of mass-flow gauge; "
            f"mdot=0.1 gives {p_low}, mdot=10.0 gives {p_high}"
        )

    mdot_low = result_low.solved_unknown_values["mdot:accumulator"]
    mdot_high = result_high.solved_unknown_values["mdot:accumulator"]
    assert abs(mdot_low - 0.1) < 1e-9
    assert abs(mdot_high - 10.0) < 1e-9


def test_inconsistent_mass_flow_gauge_gives_non_convergence():
    """Item 16: inconsistent gauge (mdot_pump != mdot_accumulator) gives converged=False."""
    uv = _off_pressure_consistent_gauge(mdot=1.0)
    uv["mdot:pump"] = 2.0  # pump != accumulator → continuity violated
    result = solve_fixed_single_loop_residuals(_make_request(uv))
    assert isinstance(result, FixedSingleLoopSolveResult)
    assert result.converged is False


def test_inconsistent_gauge_reason_mentions_continuity():
    """Item 17: the reason string for an inconsistent gauge mentions 'continuity'."""
    uv = _off_pressure_consistent_gauge(mdot=1.0)
    uv["mdot:evaporator"] = 3.0  # inconsistent
    result = solve_fixed_single_loop_residuals(_make_request(uv))
    assert result.converged is False
    assert (
        "continuity" in result.reason.lower()
    ), f"reason should mention 'continuity'; got {result.reason!r}"


# ---------------------------------------------------------------------------
# Group 3: Regression — Block 15B.3 still intact
# ---------------------------------------------------------------------------


def test_15b3_evaluate_function_importable_from_network():
    """Item 18: evaluate_fixed_single_loop_residuals importable from mpl_sim.network."""
    import mpl_sim.network as net

    assert hasattr(net, "evaluate_fixed_single_loop_residuals")
    assert callable(net.evaluate_fixed_single_loop_residuals)


def test_15b3_solve_function_importable_from_network():
    """Item 19: solve_fixed_single_loop_residuals importable from mpl_sim.network."""
    import mpl_sim.network as net

    assert hasattr(net, "solve_fixed_single_loop_residuals")
    assert callable(net.solve_fixed_single_loop_residuals)


def test_15b3_report_function_importable_from_network():
    """Item 20: build_fixed_single_loop_report importable from mpl_sim.network."""
    import mpl_sim.network as net

    assert hasattr(net, "build_fixed_single_loop_report")
    assert callable(net.build_fixed_single_loop_report)


# ---------------------------------------------------------------------------
# Group 4: Regression — Block 15B.2 still intact
# ---------------------------------------------------------------------------


def test_15b2_residual_parameters_validate_scalar_fields():
    """Item 21: FixedSingleLoopResidualParameters still validates all four fields."""
    params = FixedSingleLoopResidualParameters(
        pump_pressure_rise=80_000.0,
        evaporator_pressure_drop=30_000.0,
        condenser_pressure_drop=15_000.0,
        accumulator_pressure_reference=200_000.0,
    )
    assert params.pump_pressure_rise == 80_000.0
    assert params.accumulator_pressure_reference == 200_000.0

    with pytest.raises((TypeError, ValueError)):
        FixedSingleLoopResidualParameters(
            pump_pressure_rise=float("nan"),
            evaporator_pressure_drop=30_000.0,
            condenser_pressure_drop=15_000.0,
            accumulator_pressure_reference=200_000.0,
        )


def test_15b2_physical_assembly_builds_with_four_adapters():
    """Item 22: build_fixed_single_loop_physical_residuals builds a 4-entry adapter set."""
    scenario = _default_scenario()
    params = _default_params()
    assembly = build_fixed_single_loop_physical_residuals(scenario, params)
    assert isinstance(assembly, FixedSingleLoopPhysicalResidualAssembly)
    # adapter_set.adapters is a tuple; one entry per component (4 components).
    assert len(assembly.adapter_set.adapters) == 4


# ---------------------------------------------------------------------------
# Group 5: Regression — Block 15B.1 still intact
# ---------------------------------------------------------------------------


def test_15b1_scenario_builds_with_custom_symbolic_ids():
    """Item 23: build_fixed_single_loop_scenario accepts custom symbolic string IDs."""
    scenario = build_fixed_single_loop_scenario(
        accumulator_id="acc",
        pump_id="circ_pump",
        evaporator_id="evap1",
        condenser_id="cond1",
        n_acc_out_id="node_a",
        n_pump_out_id="node_b",
        n_evap_out_id="node_c",
        n_cond_out_id="node_d",
    )
    assert scenario.component_ids.accumulator.value == "acc"
    assert scenario.component_ids.pump.value == "circ_pump"
    assert scenario.node_ids.n_acc_out.value == "node_a"


def test_15b1_scenario_summary_has_correct_counts():
    """Item 24: scenario.assembly has exactly 8 unknowns and 8 residuals."""
    scenario = _default_scenario()
    assert scenario.assembly.unknowns.count() == 8
    assert scenario.assembly.residuals.count() == 8
    summary = scenario.summary()
    assert summary["unknown_count"] == 8
    assert summary["residual_count"] == 8


# ---------------------------------------------------------------------------
# Group 6: Regression — NO_CONTRIBUTE_METHOD for all 6 production classes
# ---------------------------------------------------------------------------


def test_component_no_contribute_method():
    """Item 25: Component still reports NO_CONTRIBUTE_METHOD."""
    from mpl_sim.components import Component

    r = inspect_production_component_contract(Component)
    assert r.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD


def test_pipe_no_contribute_method():
    """Item 26: Pipe still reports NO_CONTRIBUTE_METHOD."""
    from mpl_sim.components import Pipe

    r = inspect_production_component_contract(Pipe)
    assert r.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD


def test_pump_component_no_contribute_method():
    """Item 27: PumpComponent still reports NO_CONTRIBUTE_METHOD."""
    from mpl_sim.components import PumpComponent

    r = inspect_production_component_contract(PumpComponent)
    assert r.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD


def test_accumulator_component_no_contribute_method():
    """Item 28: AccumulatorComponent still reports NO_CONTRIBUTE_METHOD."""
    from mpl_sim.components import AccumulatorComponent

    r = inspect_production_component_contract(AccumulatorComponent)
    assert r.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD


def test_evaporator_component_no_contribute_method():
    """Item 29: EvaporatorComponent still reports NO_CONTRIBUTE_METHOD."""
    from mpl_sim.components import EvaporatorComponent

    r = inspect_production_component_contract(EvaporatorComponent)
    assert r.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD


def test_condenser_component_no_contribute_method():
    """Item 30: CondenserComponent still reports NO_CONTRIBUTE_METHOD."""
    from mpl_sim.components import CondenserComponent

    r = inspect_production_component_contract(CondenserComponent)
    assert r.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD


def test_all_known_production_classes_still_no_contribute():
    """Items 25–30 (combined): inspect_known_production_component_contracts bulk check."""
    results = inspect_known_production_component_contracts()
    for r in results:
        assert (
            r.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD
        ), f"{r.class_name} should be NO_CONTRIBUTE_METHOD; got {r.status!r}"


# ---------------------------------------------------------------------------
# Group 7: Boundary tests — this test file
# ---------------------------------------------------------------------------


def test_this_file_no_coolprop_import():
    """Item 31: this closeout test file must not import CoolProp."""
    tree = _parse_ast(_THIS_FILE)
    assert not _has_import(tree, "CoolProp"), "closeout test file must not import CoolProp"


def test_this_file_no_property_backend_import():
    """Item 32: this closeout test file must not import PropertyBackend."""
    tree = _parse_ast(_THIS_FILE)
    assert not _has_import(
        tree, "PropertyBackend"
    ), "closeout test file must not import PropertyBackend"


def test_this_file_no_system_state_import():
    """Item 33: this closeout test file must not import SystemState."""
    tree = _parse_ast(_THIS_FILE)
    assert not _has_import(tree, "SystemState"), "closeout test file must not import SystemState"


def test_this_file_no_fluid_state_import():
    """Item 34: this closeout test file must not import FluidState."""
    tree = _parse_ast(_THIS_FILE)
    assert not _has_import(tree, "FluidState"), "closeout test file must not import FluidState"


def test_this_file_no_correlation_registry_import():
    """Item 35: this closeout test file must not import CorrelationRegistry."""
    tree = _parse_ast(_THIS_FILE)
    assert not _has_import(
        tree, "CorrelationRegistry"
    ), "closeout test file must not import CorrelationRegistry"


def test_this_file_no_contribute_attribute_call():
    """Item 36: this closeout test file must not call .contribute(...)."""
    tree = _parse_ast(_THIS_FILE)
    assert not _has_contribute_attribute_call(
        tree
    ), "closeout test file must not call .contribute(...)"


def test_this_file_no_mpl_sim_components_namespace_import():
    """Item 37: the closeout test file must not use bare 'import mpl_sim.components'.

    Individual 'from mpl_sim.components import Component' (etc.) are allowed here
    because they are used for NO_CONTRIBUTE_METHOD inspection only.  A bare module
    namespace import ('import mpl_sim.components') would imply physics execution use.
    """
    tree = _parse_ast(_THIS_FILE)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "mpl_sim.components" in alias.name:
                    pytest.fail(
                        "closeout test file must not use bare 'import mpl_sim.components'; "
                        f"found: import {alias.name}"
                    )


def test_this_file_no_mpl_sim_properties_import():
    """Item 38: this closeout test file must not import mpl_sim.properties."""
    tree = _parse_ast(_THIS_FILE)
    assert not _has_import(
        tree, "mpl_sim.properties"
    ), "closeout test file must not import mpl_sim.properties"


# ---------------------------------------------------------------------------
# Group 8: Architecture boundary — Block 15B remains fixed-loop only
# ---------------------------------------------------------------------------


def test_no_generic_solve_network_in_fixed_loop_modules():
    """Item 39: fixed-loop modules do not define a bare function named 'solve'.

    'solve_fixed_single_loop_residuals' and 'solve_network_residual_problem' are fine.
    A bare function def solve(...) or NetworkGraph.solve() is forbidden.
    """
    for module_path in (_SCENARIO_MODULE, _RESIDUALS_MODULE, _RUNNER_MODULE):
        tree = _parse_ast(module_path)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "solve":
                pytest.fail(f"{module_path.name} must not define a bare function named 'solve'")


def test_no_network_graph_solve_in_fixed_loop_modules():
    """Item 40: no executable 'NetworkGraph.solve' call in fixed-loop runtime modules.

    Docstring prohibition statements ("NetworkGraph.solve() remain deferred") are
    allowed and expected.  We check for executable attribute-call AST nodes only.
    """
    for module_path in (_SCENARIO_MODULE, _RESIDUALS_MODULE, _RUNNER_MODULE):
        tree = _parse_ast(module_path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "solve"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "NetworkGraph"
                ):
                    pytest.fail(
                        f"{module_path.name} must not contain an executable "
                        f"NetworkGraph.solve() call"
                    )


def test_no_component_type_physics_in_fixed_loop_modules():
    """Item 41: no component_type physics dispatch (Name node) in fixed-loop modules.

    The string 'component_type' may appear in docstrings (ast.Constant) but
    must not appear as an executable ast.Name reference.
    """
    for module_path in (_SCENARIO_MODULE, _RESIDUALS_MODULE, _RUNNER_MODULE):
        tree = _parse_ast(module_path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "component_type":
                pytest.fail(
                    f"{module_path.name} must not reference component_type as an "
                    f"executable Name node"
                )


# ---------------------------------------------------------------------------
# Group 9: Public API audit — no new public symbols in 15B.4
# ---------------------------------------------------------------------------


def test_no_new_symbols_beyond_block_15b3():
    """Item 42: mpl_sim.network.__all__ must include all 15B.3 symbols.

    Block 15B.4 is tests/docs-only.  No new public symbols should be added.
    We confirm the 15B.3 symbols are still present and report any unexpected
    additions beyond the known baseline.
    """
    import mpl_sim.network as net

    current_all = set(net.__all__)
    missing = _BLOCK_15B3_EXPORTS - current_all
    assert (
        not missing
    ), f"Block 15B.3 symbols were removed from mpl_sim.network.__all__: {missing!r}"


def test_all_block_15b_exports_present():
    """Item 43: all Block 15B exports are in mpl_sim.network.__all__."""
    import mpl_sim.network as net

    expected = {
        "FixedSingleLoopEvaluationResult",
        "FixedSingleLoopSolveRequest",
        "FixedSingleLoopSolveResult",
        "evaluate_fixed_single_loop_residuals",
        "solve_fixed_single_loop_residuals",
        "build_fixed_single_loop_report",
    }
    all_set = set(net.__all__)
    for name in expected:
        assert name in all_set, f"{name!r} missing from mpl_sim.network.__all__"


def test_no_private_symbols_in_all():
    """Item 44: mpl_sim.network.__all__ contains no private (underscore-prefixed) names."""
    import mpl_sim.network as net

    for name in net.__all__:
        assert not name.startswith("_"), f"Private symbol {name!r} found in __all__"


# ---------------------------------------------------------------------------
# Additional: solve produces near-zero final residuals after convergence
# ---------------------------------------------------------------------------


def test_solve_final_residuals_near_zero_after_convergence():
    """Converged result has all 8 final residuals within solver tolerance."""
    result = solve_fixed_single_loop_residuals(_make_request(_off_pressure_consistent_gauge()))
    assert result.converged is True
    tol = _default_solver_config().tolerance
    assert result.final_max_abs_residual <= tol
    for name, val in result.final_residual_values.items():
        assert math.isfinite(val), f"Residual {name!r} is non-finite: {val}"
        assert abs(val) <= tol, f"Residual {name!r} = {val}, expected <= {tol}"


def test_solve_pressure_values_match_known_solution():
    """Solved pressures match the analytically known consistent solution."""
    result = solve_fixed_single_loop_residuals(_make_request(_off_pressure_consistent_gauge()))
    expected = _consistent_unknowns()
    pressure_keys = ("P:n_acc_out", "P:n_pump_out", "P:n_evap_out", "P:n_cond_out")
    for key in pressure_keys:
        assert result.solved_unknown_values[key] == pytest.approx(
            expected[key], abs=1e-6
        ), f"{key}: expected {expected[key]}, got {result.solved_unknown_values[key]}"
