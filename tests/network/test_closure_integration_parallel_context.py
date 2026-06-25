"""Block 15D-C — Closure Integration: Parallel Context Integration tests.

Proves that Block 15D-C combined closure layer integrates correctly with:
  1. Block 15C-A two-branch parallel topology (scenario still builds).
  2. Block 15C-B fixed topology residuals (evaluate at consistent point).
  3. Block 15D-A hydraulic closures (evaluate at consistent point).
  4. Block 15D-B thermal closures (evaluate at consistent point).
  5. Combined closure set evaluates over a unified unknown mapping.
  6. Known consistent point yields zero combined closure residuals.
  7. Perturbing a hydraulic unknown gives nonzero hydraulic residuals.
  8. Perturbing a thermal unknown gives nonzero thermal residuals.
  9. Topology residuals and closure residuals remain SEPARATE subsystems.
     No combined physical solve is performed or claimed.
 10. Report is plain serializable dict.
 11. Architecture boundary: no forbidden imports.

Note on separation of residual subsystems
------------------------------------------
The 15C-B topology residuals are structural (mass-balance + pressure equations
for the fixed network topology).  The 15D-A/15D-B closure residuals are
declarative algebraic closure constraints.  In this block they are evaluated
separately and are NOT combined into a single solved system.  A combined
physical solve remains deferred.

Consistent test point
----------------------
Topology parameters (Block 15C-B compatible):
  accumulator_pressure_reference = 1_000_000 Pa
  pump_pressure_rise             =   100_000 Pa
  branch_a_pressure_drop         =    30_000 Pa
  branch_b_pressure_drop         =    40_000 Pa
  merge_a_pressure_drop          =    20_000 Pa  (path A: 30+20=50 kPa)
  merge_b_pressure_drop          =    10_000 Pa  (path B: 40+10=50 kPa ✓)
  condenser_pressure_drop        =    50_000 Pa

Mass flows:
  mdot_accumulator = mdot_pump = mdot_condenser = 1.0 kg/s
  mdot_branch_a = mdot_merge_a = 0.4 kg/s
  mdot_branch_b = mdot_merge_b = 0.6 kg/s

Nodal pressures:
  P_n_acc_out   = 1_000_000 Pa
  P_n_pump_out  = 1_100_000 Pa
  P_n_a_out     = 1_070_000 Pa (1100000 - 30000)
  P_n_b_out     = 1_060_000 Pa (1100000 - 40000)
  P_n_merge_out = 1_050_000 Pa (1070000 - 20000 = 1060000 - 10000)
  P_n_cond_out  = 1_000_000 Pa (1050000 - 50000)

Hydraulic closure design (DOFs + demonstration closures):
  DOF 1 — ImposedMassFlowClosure(mdot_pump, 1.0)         → r = 0
  DOF 2 — ImposedBranchSplitClosure(mdot_pump, mdot_branch_a, 0.4) → r = 0
  Ref   — ImposedPressureClosure(P_n_acc_out, 1_000_000) → r = 0
  Drop  — LinearPressureDropClosure(P_n_pump_out, P_n_a_out, mdot_branch_a, 75000)
           P_in - P_out - R*m = 1_100_000 - 1_070_000 - 75000*0.4 = 0 ✓
  Compat — PressureCompatibilityClosure(mdot_branch_a, mdot_branch_b,
             R_a=125000, R_b=50000/0.6)
           125000*0.4 - (50000/0.6)*0.6 = 50000 - 50000 = 0 ✓

Thermal closure design (for branch A element):
  q_branch_a = 4000.0 W
  mdot_branch_a = 0.4 kg/s
  h_in_a = 200_000.0 J/kg
  h_out_a = 210_000.0 J/kg
  FixedHeatRateClosure(q_branch_a, 4000.0)          → r = 0
  EnthalpyFlowHeatRateClosure(q_branch_a, mdot_branch_a, h_in_a, h_out_a)
    r = q - mdot*(h_out - h_in) = 4000 - 0.4*10000 = 0 ✓

Architecture invariants confirmed in this file
-----------------------------------------------
No CoolProp, no PropertyBackend, no CorrelationRegistry.
No HX model imports or calls.
No production component execution.
No SystemState, no FluidState.
No contribute( calls or definitions.
No generic solve(network) or NetworkGraph.solve().
No least-squares or root-finding.
No file writing.
No pandas.
"""

from __future__ import annotations

import json
import math

import pytest

from mpl_sim.network.closure_integration import (
    CombinedClosureResidualSet,
    build_combined_closure_report,
    build_combined_closure_residuals,
    evaluate_combined_closure_residuals,
    evaluate_combined_closure_sufficiency,
)
from mpl_sim.network.hydraulic_closure_diagnostics import make_two_branch_parallel_diagnostic
from mpl_sim.network.hydraulic_closures import (
    ImposedBranchSplitClosure,
    ImposedMassFlowClosure,
    ImposedPressureClosure,
    LinearPressureDropClosure,
    PressureCompatibilityClosure,
    build_hydraulic_closure_residuals,
)
from mpl_sim.network.parallel_topology_residuals import (
    ParallelTopologyResidualParameters,
    build_parallel_topology_report,
    evaluate_parallel_topology_residuals,
)
from mpl_sim.network.parallel_topology_scenario import build_parallel_topology_scenario
from mpl_sim.network.thermal_closure_diagnostics import make_basic_thermal_loop_diagnostic
from mpl_sim.network.thermal_closures import (
    EnthalpyFlowHeatRateClosure,
    FixedHeatRateClosure,
    build_thermal_closure_residuals,
)

# ---------------------------------------------------------------------------
# Consistent test point shared across all tests
# ---------------------------------------------------------------------------

_TOPOLOGY_PARAMS = ParallelTopologyResidualParameters(
    accumulator_pressure_reference=1_000_000.0,
    pump_pressure_rise=100_000.0,
    branch_a_pressure_drop=30_000.0,
    branch_b_pressure_drop=40_000.0,
    merge_a_pressure_drop=20_000.0,
    merge_b_pressure_drop=10_000.0,
    condenser_pressure_drop=50_000.0,
)

_CONSISTENT_UNKNOWNS = {
    # 13 topology unknowns (mass flows + pressures)
    "mdot_accumulator": 1.0,
    "mdot_pump": 1.0,
    "mdot_branch_a": 0.4,
    "mdot_branch_b": 0.6,
    "mdot_merge_a": 0.4,
    "mdot_merge_b": 0.6,
    "mdot_condenser": 1.0,
    "P_n_acc_out": 1_000_000.0,
    "P_n_pump_out": 1_100_000.0,
    "P_n_a_out": 1_070_000.0,
    "P_n_b_out": 1_060_000.0,
    "P_n_merge_out": 1_050_000.0,
    "P_n_cond_out": 1_000_000.0,
    # Thermal unknowns for branch A element
    "q_branch_a": 4_000.0,
    "h_in_a": 200_000.0,
    "h_out_a": 210_000.0,
}

# Hydraulic closure residual names use distinct prefixes to avoid any name
# collision with topology residuals.
_R_TOTAL_FLOW = "r_cl_total_flow"
_R_BRANCH_SPLIT = "r_cl_branch_split"
_R_PRESSURE_REF = "r_cl_pressure_ref"
_R_BRANCH_DROP = "r_cl_branch_a_drop"
_R_COMPAT = "r_cl_compat"
_R_HEAT_RATE = "r_cl_heat_rate"
_R_ENTHALPY_FLOW = "r_cl_enthalpy_flow"

# R_b = (path_b_drop) / mdot_b = (40000+10000)/0.6
_R_B = 50_000.0 / 0.6


def _make_topology_unknowns() -> dict[str, float]:
    """Return colon-format unknown dict derived from scenario names."""
    scenario = build_parallel_topology_scenario()
    un = scenario.unknown_names
    return {
        un.mdot_accumulator: 1.0,
        un.mdot_pump: 1.0,
        un.mdot_branch_a: 0.4,
        un.mdot_branch_b: 0.6,
        un.mdot_merge_a: 0.4,
        un.mdot_merge_b: 0.6,
        un.mdot_condenser: 1.0,
        un.P_n_acc_out: 1_000_000.0,
        un.P_n_pump_out: 1_100_000.0,
        un.P_n_a_out: 1_070_000.0,
        un.P_n_b_out: 1_060_000.0,
        un.P_n_merge_out: 1_050_000.0,
        un.P_n_cond_out: 1_000_000.0,
    }


def _build_hydraulic_set():
    return build_hydraulic_closure_residuals(
        [
            ImposedMassFlowClosure("mdot_pump", 1.0, _R_TOTAL_FLOW),
            ImposedBranchSplitClosure("mdot_pump", "mdot_branch_a", 0.4, _R_BRANCH_SPLIT),
            ImposedPressureClosure("P_n_acc_out", 1_000_000.0, _R_PRESSURE_REF),
            LinearPressureDropClosure(
                "P_n_pump_out", "P_n_a_out", "mdot_branch_a", 75_000.0, _R_BRANCH_DROP
            ),
            PressureCompatibilityClosure(
                "mdot_branch_a", "mdot_branch_b", 125_000.0, _R_B, _R_COMPAT
            ),
        ]
    )


def _build_thermal_set():
    return build_thermal_closure_residuals(
        [
            FixedHeatRateClosure("q_branch_a", 4_000.0, _R_HEAT_RATE),
            EnthalpyFlowHeatRateClosure(
                "q_branch_a", "mdot_branch_a", "h_in_a", "h_out_a", _R_ENTHALPY_FLOW
            ),
        ]
    )


# ---------------------------------------------------------------------------
# 15C-A scenario still builds (regression)
# ---------------------------------------------------------------------------


def test_15c_a_parallel_topology_scenario_builds():
    scenario = build_parallel_topology_scenario()
    assert scenario is not None
    assert scenario.graph is not None
    assert len(scenario.unknown_names.all_names()) == 13
    assert len(scenario.residual_names.all_names()) == 13


# ---------------------------------------------------------------------------
# 15C-B topology residuals still evaluate (regression)
# ---------------------------------------------------------------------------


def test_15c_b_topology_residuals_evaluate_at_consistent_point():
    scenario = build_parallel_topology_scenario()
    result = evaluate_parallel_topology_residuals(
        scenario, _TOPOLOGY_PARAMS, _make_topology_unknowns()
    )
    for name, value in result.residual_values.items():
        assert math.isfinite(value), f"Residual {name!r} is not finite: {value}"
    assert result.max_abs_residual == pytest.approx(0.0, abs=1e-9)


def test_15c_b_topology_report_still_works():
    scenario = build_parallel_topology_scenario()
    result = evaluate_parallel_topology_residuals(
        scenario, _TOPOLOGY_PARAMS, _make_topology_unknowns()
    )
    report = build_parallel_topology_report(result)
    assert isinstance(report, dict)
    json.dumps(report)


# ---------------------------------------------------------------------------
# 15D-A hydraulic closures evaluate at consistent point
# ---------------------------------------------------------------------------


def test_hydraulic_closure_set_evaluates():
    h_set = _build_hydraulic_set()
    residuals = h_set.evaluate_all(_CONSISTENT_UNKNOWNS)
    for name, value in residuals.items():
        assert math.isfinite(value), f"Hydraulic residual {name!r} is not finite"


def test_hydraulic_closures_zero_at_consistent_point():
    h_set = _build_hydraulic_set()
    residuals = h_set.evaluate_all(_CONSISTENT_UNKNOWNS)
    assert residuals[_R_TOTAL_FLOW] == pytest.approx(0.0, abs=1e-9)
    assert residuals[_R_BRANCH_SPLIT] == pytest.approx(0.0, abs=1e-9)
    assert residuals[_R_PRESSURE_REF] == pytest.approx(0.0, abs=1e-9)
    assert residuals[_R_BRANCH_DROP] == pytest.approx(0.0, abs=1e-9)
    assert residuals[_R_COMPAT] == pytest.approx(0.0, abs=1e-6)


# ---------------------------------------------------------------------------
# 15D-B thermal closures evaluate at consistent point
# ---------------------------------------------------------------------------


def test_thermal_closure_set_evaluates():
    t_set = _build_thermal_set()
    residuals = t_set.evaluate_all(_CONSISTENT_UNKNOWNS)
    for name, value in residuals.items():
        assert math.isfinite(value), f"Thermal residual {name!r} is not finite"


def test_thermal_closures_zero_at_consistent_point():
    t_set = _build_thermal_set()
    residuals = t_set.evaluate_all(_CONSISTENT_UNKNOWNS)
    assert residuals[_R_HEAT_RATE] == pytest.approx(0.0, abs=1e-9)
    assert residuals[_R_ENTHALPY_FLOW] == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Combined closure set builds and evaluates
# ---------------------------------------------------------------------------


def test_combined_closure_set_builds():
    h_set = _build_hydraulic_set()
    t_set = _build_thermal_set()
    combined = build_combined_closure_residuals(hydraulic=h_set, thermal=t_set)
    assert isinstance(combined, CombinedClosureResidualSet)


def test_combined_closure_set_has_both_domains():
    h_set = _build_hydraulic_set()
    t_set = _build_thermal_set()
    combined = build_combined_closure_residuals(hydraulic=h_set, thermal=t_set)
    assert combined.hydraulic_count == len(h_set.closures)
    assert combined.thermal_count == len(t_set.closures)


def test_combined_closure_residual_names_hydraulic_first():
    h_set = _build_hydraulic_set()
    t_set = _build_thermal_set()
    combined = build_combined_closure_residuals(hydraulic=h_set, thermal=t_set)
    names = combined.residual_names
    h_names = h_set.residual_names
    t_names = t_set.residual_names
    assert names[: len(h_names)] == h_names
    assert names[len(h_names) :] == t_names


# ---------------------------------------------------------------------------
# Known consistent point gives zero combined closure residuals
# ---------------------------------------------------------------------------


def test_combined_closure_evaluation_returns_result():
    h_set = _build_hydraulic_set()
    t_set = _build_thermal_set()
    combined = build_combined_closure_residuals(hydraulic=h_set, thermal=t_set)
    result = evaluate_combined_closure_residuals(combined, _CONSISTENT_UNKNOWNS)
    assert result is not None


def test_combined_closure_zero_max_abs_at_consistent_point():
    h_set = _build_hydraulic_set()
    t_set = _build_thermal_set()
    combined = build_combined_closure_residuals(hydraulic=h_set, thermal=t_set)
    result = evaluate_combined_closure_residuals(combined, _CONSISTENT_UNKNOWNS)
    assert result.max_absolute_residual == pytest.approx(0.0, abs=1e-6)


def test_combined_closure_zero_l2_at_consistent_point():
    h_set = _build_hydraulic_set()
    t_set = _build_thermal_set()
    combined = build_combined_closure_residuals(hydraulic=h_set, thermal=t_set)
    result = evaluate_combined_closure_residuals(combined, _CONSISTENT_UNKNOWNS)
    assert result.l2_residual_norm == pytest.approx(0.0, abs=1e-6)


def test_combined_closure_all_residuals_zero_at_consistent_point():
    h_set = _build_hydraulic_set()
    t_set = _build_thermal_set()
    combined = build_combined_closure_residuals(hydraulic=h_set, thermal=t_set)
    result = evaluate_combined_closure_residuals(combined, _CONSISTENT_UNKNOWNS)
    for name, value in result.combined_residuals.items():
        assert value == pytest.approx(0.0, abs=1e-6), f"Residual {name!r} = {value}"


# ---------------------------------------------------------------------------
# Perturbing a hydraulic unknown changes hydraulic residuals
# ---------------------------------------------------------------------------


def test_perturbing_hydraulic_mdot_pump_changes_total_flow_residual():
    h_set = _build_hydraulic_set()
    t_set = _build_thermal_set()
    combined = build_combined_closure_residuals(hydraulic=h_set, thermal=t_set)
    perturbed = dict(_CONSISTENT_UNKNOWNS)
    perturbed["mdot_pump"] = 1.1
    result = evaluate_combined_closure_residuals(combined, perturbed)
    assert abs(result.hydraulic_residuals[_R_TOTAL_FLOW]) > 1e-6


def test_perturbing_hydraulic_mdot_pump_does_not_change_thermal_residuals():
    h_set = _build_hydraulic_set()
    t_set = _build_thermal_set()
    combined = build_combined_closure_residuals(hydraulic=h_set, thermal=t_set)
    perturbed = dict(_CONSISTENT_UNKNOWNS)
    perturbed["mdot_pump"] = 1.1
    result = evaluate_combined_closure_residuals(combined, perturbed)
    # thermal residuals are not zero (mdot_branch_a is 0.4 but mdot_pump
    # branch split residual uses mdot_pump, not mdot_branch_a; enthalpy closure
    # uses mdot_branch_a directly — so the enthalpy closure is still zero)
    assert result.thermal_residuals[_R_HEAT_RATE] == pytest.approx(0.0, abs=1e-9)


def test_perturbing_hydraulic_pressure_changes_hydraulic_residuals():
    h_set = _build_hydraulic_set()
    combined = build_combined_closure_residuals(hydraulic=h_set)
    perturbed = dict(_CONSISTENT_UNKNOWNS)
    perturbed["P_n_acc_out"] = 999_000.0
    result = evaluate_combined_closure_residuals(combined, perturbed)
    assert abs(result.hydraulic_residuals[_R_PRESSURE_REF]) > 1e-3


# ---------------------------------------------------------------------------
# Perturbing a thermal unknown changes thermal residuals
# ---------------------------------------------------------------------------


def test_perturbing_thermal_heat_rate_changes_thermal_residual():
    h_set = _build_hydraulic_set()
    t_set = _build_thermal_set()
    combined = build_combined_closure_residuals(hydraulic=h_set, thermal=t_set)
    perturbed = dict(_CONSISTENT_UNKNOWNS)
    perturbed["q_branch_a"] = 5_000.0
    result = evaluate_combined_closure_residuals(combined, perturbed)
    assert abs(result.thermal_residuals[_R_HEAT_RATE]) > 1e-6


def test_perturbing_thermal_heat_rate_does_not_change_hydraulic_residuals():
    h_set = _build_hydraulic_set()
    t_set = _build_thermal_set()
    combined = build_combined_closure_residuals(hydraulic=h_set, thermal=t_set)
    perturbed = dict(_CONSISTENT_UNKNOWNS)
    perturbed["q_branch_a"] = 5_000.0
    result = evaluate_combined_closure_residuals(combined, perturbed)
    assert result.hydraulic_residuals[_R_TOTAL_FLOW] == pytest.approx(0.0, abs=1e-9)
    assert result.hydraulic_residuals[_R_PRESSURE_REF] == pytest.approx(0.0, abs=1e-9)


def test_perturbing_thermal_enthalpy_changes_enthalpy_flow_residual():
    h_set = _build_hydraulic_set()
    t_set = _build_thermal_set()
    combined = build_combined_closure_residuals(hydraulic=h_set, thermal=t_set)
    perturbed = dict(_CONSISTENT_UNKNOWNS)
    perturbed["h_out_a"] = 215_000.0
    result = evaluate_combined_closure_residuals(combined, perturbed)
    assert abs(result.thermal_residuals[_R_ENTHALPY_FLOW]) > 1e-6


# ---------------------------------------------------------------------------
# Combined diagnostics at consistent point
# ---------------------------------------------------------------------------


def test_combined_sufficiency_at_consistent_point():
    h_set = _build_hydraulic_set()
    t_set = _build_thermal_set()
    combined = build_combined_closure_residuals(hydraulic=h_set, thermal=t_set)
    h_diag = make_two_branch_parallel_diagnostic()
    t_diag = make_basic_thermal_loop_diagnostic()
    result = evaluate_combined_closure_sufficiency(
        combined, hydraulic_diagnostic=h_diag, thermal_diagnostic=t_diag
    )
    assert result.is_sufficient is True
    assert result.hydraulic_result.is_sufficient is True
    assert result.thermal_result.is_sufficient is True


# ---------------------------------------------------------------------------
# No solve is claimed
# ---------------------------------------------------------------------------


def test_no_solve_claimed_in_result():
    h_set = _build_hydraulic_set()
    combined = build_combined_closure_residuals(hydraulic=h_set)
    result = evaluate_combined_closure_residuals(combined, _CONSISTENT_UNKNOWNS)
    result_type_name = type(result).__name__
    assert "Solve" not in result_type_name
    assert "solve" not in result_type_name.lower()


def test_no_solve_claimed_in_report():
    h_set = _build_hydraulic_set()
    t_set = _build_thermal_set()
    combined = build_combined_closure_residuals(hydraulic=h_set, thermal=t_set)
    result = evaluate_combined_closure_residuals(combined, _CONSISTENT_UNKNOWNS)
    report = build_combined_closure_report(result)
    assert report["no_solve"] is True
    assert report["status"] == "evaluation_only"


# ---------------------------------------------------------------------------
# Topology residuals and closure residuals are separate subsystems
# ---------------------------------------------------------------------------


def test_topology_and_closure_residuals_are_separate():
    scenario = build_parallel_topology_scenario()
    topo_result = evaluate_parallel_topology_residuals(
        scenario, _TOPOLOGY_PARAMS, _make_topology_unknowns()
    )

    h_set = _build_hydraulic_set()
    t_set = _build_thermal_set()
    combined = build_combined_closure_residuals(hydraulic=h_set, thermal=t_set)
    closure_result = evaluate_combined_closure_residuals(combined, _CONSISTENT_UNKNOWNS)

    topo_names = set(topo_result.residual_values.keys())
    closure_names = set(closure_result.combined_residuals.keys())
    assert topo_names.isdisjoint(closure_names), (
        f"Topology and closure residual names should not overlap; "
        f"overlap: {topo_names & closure_names}"
    )


# ---------------------------------------------------------------------------
# Combined report is plain serializable data
# ---------------------------------------------------------------------------


def test_combined_report_is_plain_dict():
    h_set = _build_hydraulic_set()
    t_set = _build_thermal_set()
    combined = build_combined_closure_residuals(hydraulic=h_set, thermal=t_set)
    result = evaluate_combined_closure_residuals(combined, _CONSISTENT_UNKNOWNS)
    report = build_combined_closure_report(result)
    assert isinstance(report, dict)


def test_combined_report_json_serializable():
    h_set = _build_hydraulic_set()
    t_set = _build_thermal_set()
    combined = build_combined_closure_residuals(hydraulic=h_set, thermal=t_set)
    result = evaluate_combined_closure_residuals(combined, _CONSISTENT_UNKNOWNS)
    diag = evaluate_combined_closure_sufficiency(
        combined,
        hydraulic_diagnostic=make_two_branch_parallel_diagnostic(),
        thermal_diagnostic=make_basic_thermal_loop_diagnostic(),
    )
    report = build_combined_closure_report(result, diag)
    serialized = json.dumps(report)
    restored = json.loads(serialized)
    assert isinstance(restored, dict)
    assert restored["block"] == "15D-C"


def test_combined_report_contains_topology_residuals_section_optional():
    scenario = build_parallel_topology_scenario()
    topo_result = evaluate_parallel_topology_residuals(
        scenario, _TOPOLOGY_PARAMS, _make_topology_unknowns()
    )
    topo_report = build_parallel_topology_report(topo_result)

    h_set = _build_hydraulic_set()
    t_set = _build_thermal_set()
    combined = build_combined_closure_residuals(hydraulic=h_set, thermal=t_set)
    result = evaluate_combined_closure_residuals(combined, _CONSISTENT_UNKNOWNS)
    closure_report = build_combined_closure_report(result)

    combined_overview: dict[str, object] = {
        "topology_report": topo_report,
        "closure_report": closure_report,
        "note": (
            "Topology and closure residuals are evaluated separately and are "
            "NOT combined into a single solved system.  This is NOT a claim "
            "of a complete physical solve."
        ),
    }
    serialized = json.dumps(combined_overview)
    assert isinstance(serialized, str)


# ---------------------------------------------------------------------------
# Boundary: no forbidden patterns in closure_integration.py and this file
# ---------------------------------------------------------------------------


def _get_executable_import_lines(filepath: str) -> list[str]:
    with open(filepath, encoding="utf-8") as fh:
        lines = fh.readlines()
    return [
        line.rstrip()
        for line in lines
        if line.strip().startswith(("import ", "from ")) and not line.strip().startswith("#")
    ]


def test_boundary_no_coolprop_import_in_closure_integration():
    import mpl_sim.network.closure_integration as ci

    import_lines = _get_executable_import_lines(ci.__file__)
    import_text = "\n".join(import_lines)
    assert "CoolProp" not in import_text
    assert "PropertyBackend" not in import_text
    assert "CorrelationRegistry" not in import_text


def test_boundary_no_systemstate_or_fluidstate_import_in_closure_integration():
    import mpl_sim.network.closure_integration as ci

    import_lines = _get_executable_import_lines(ci.__file__)
    import_text = "\n".join(import_lines)
    assert "SystemState" not in import_text
    assert "FluidState" not in import_text


def test_boundary_no_component_type_dispatch_in_closure_integration():
    import mpl_sim.network.closure_integration as ci

    import_lines = _get_executable_import_lines(ci.__file__)
    import_text = "\n".join(import_lines)
    assert "component_type" not in import_text


def test_boundary_no_solve_implementation_in_closure_integration():
    import mpl_sim.network.closure_integration as ci

    with open(ci.__file__, encoding="utf-8") as fh:
        text = fh.read()
    assert "def solve(" not in text
    assert "fsolve" not in text
    assert "least_squares" not in text
    assert "lstsq" not in text


def test_boundary_no_hx_model_import_in_closure_integration():
    import mpl_sim.network.closure_integration as ci

    import_lines = _get_executable_import_lines(ci.__file__)
    import_text = "\n".join(import_lines)
    assert "hx_models" not in import_text


def test_boundary_no_pandas_import_in_closure_integration():
    import mpl_sim.network.closure_integration as ci

    import_lines = _get_executable_import_lines(ci.__file__)
    import_text = "\n".join(import_lines)
    assert "pandas" not in import_text


def test_boundary_no_contribute_in_closure_integration():
    import mpl_sim.network.closure_integration as ci

    with open(ci.__file__, encoding="utf-8") as fh:
        text = fh.read()
    assert ".contribute(" not in text
    assert "def contribute" not in text


def test_boundary_no_production_components_imported():
    import mpl_sim.network.closure_integration as ci

    import_lines = _get_executable_import_lines(ci.__file__)
    import_text = "\n".join(import_lines)
    assert "mpl_sim.components" not in import_text
    assert "PumpComponent" not in import_text
    assert "EvaporatorComponent" not in import_text
    assert "CondenserComponent" not in import_text
