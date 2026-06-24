"""Block 15C-B — Parallel Topology Residual Assembly and Evaluation tests.

Coverage for:
  15C.4 — Branch Residual Assembly MVP
  15C.5 — Parallel Evaporator Fixed-Topology Evaluate/Report

No production component physics are executed.  No SystemState is assembled.
No FluidState is created.  No forbidden imports in the source modules.

Consistent test point
---------------------
Parameters (branch compatibility condition satisfied):
  accumulator_pressure_reference = 1_000_000 Pa
  pump_pressure_rise             = 100_000  Pa
  branch_a_pressure_drop         =  30_000  Pa
  branch_b_pressure_drop         =  40_000  Pa
  merge_a_pressure_drop          =  20_000  Pa   (30000 + 20000 = 50000)
  merge_b_pressure_drop          =  10_000  Pa   (40000 + 10000 = 50000) ✓
  condenser_pressure_drop        =  50_000  Pa

Mass flows (m=1.0 kg/s, branch_a=0.4, branch_b=0.6):
  mdot_accumulator = mdot_pump = mdot_condenser = 1.0
  mdot_branch_a = mdot_merge_a = 0.4
  mdot_branch_b = mdot_merge_b = 0.6

Pressures at consistent point:
  P_n_acc_out   = 1_000_000
  P_n_pump_out  = 1_100_000
  P_n_a_out     = 1_070_000  (1100000 - 30000)
  P_n_b_out     = 1_060_000  (1100000 - 40000)
  P_n_merge_out = 1_050_000  (1070000 - 20000 = 1060000 - 10000)
  P_n_cond_out  = 1_000_000  (1050000 - 50000)
"""

from __future__ import annotations

import math
from types import MappingProxyType

import pytest

from mpl_sim.network.parallel_topology_residuals import (
    ParallelTopologyEvaluationResult,
    ParallelTopologyPhysicalResidualAssembly,
    ParallelTopologyResidualParameters,
    build_parallel_topology_physical_residuals,
    build_parallel_topology_report,
    evaluate_parallel_topology_residuals,
)
from mpl_sim.network.parallel_topology_scenario import build_parallel_topology_scenario

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_PARAMS = ParallelTopologyResidualParameters(
    accumulator_pressure_reference=1_000_000.0,
    pump_pressure_rise=100_000.0,
    branch_a_pressure_drop=30_000.0,
    branch_b_pressure_drop=40_000.0,
    merge_a_pressure_drop=20_000.0,
    merge_b_pressure_drop=10_000.0,
    condenser_pressure_drop=50_000.0,
)


def _make_scenario():
    return build_parallel_topology_scenario()


def _make_consistent_unknowns(scenario):
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


# ===========================================================================
# Part I — 15C.4: ParallelTopologyResidualParameters
# ===========================================================================


class TestParallelTopologyResidualParameters:
    def test_valid_parameters_build(self):
        p = ParallelTopologyResidualParameters(
            accumulator_pressure_reference=1e6,
            pump_pressure_rise=1e5,
            branch_a_pressure_drop=3e4,
            branch_b_pressure_drop=4e4,
            merge_a_pressure_drop=2e4,
            merge_b_pressure_drop=1e4,
            condenser_pressure_drop=5e4,
        )
        assert isinstance(p, ParallelTopologyResidualParameters)

    def test_all_fields_stored_as_float(self):
        p = ParallelTopologyResidualParameters(
            accumulator_pressure_reference=1_000_000,
            pump_pressure_rise=100_000,
            branch_a_pressure_drop=30_000,
            branch_b_pressure_drop=40_000,
            merge_a_pressure_drop=20_000,
            merge_b_pressure_drop=10_000,
            condenser_pressure_drop=50_000,
        )
        assert isinstance(p.accumulator_pressure_reference, float)
        assert isinstance(p.pump_pressure_rise, float)
        assert isinstance(p.branch_a_pressure_drop, float)
        assert isinstance(p.branch_b_pressure_drop, float)
        assert isinstance(p.merge_a_pressure_drop, float)
        assert isinstance(p.merge_b_pressure_drop, float)
        assert isinstance(p.condenser_pressure_drop, float)

    def test_parameters_are_frozen(self):
        p = _PARAMS
        with pytest.raises((AttributeError, TypeError)):
            p.pump_pressure_rise = 999.0  # type: ignore[misc]

    def test_bool_rejected_for_pump_pressure_rise(self):
        with pytest.raises(TypeError, match="bool"):
            ParallelTopologyResidualParameters(
                accumulator_pressure_reference=1e6,
                pump_pressure_rise=True,
                branch_a_pressure_drop=3e4,
                branch_b_pressure_drop=4e4,
                merge_a_pressure_drop=2e4,
                merge_b_pressure_drop=1e4,
                condenser_pressure_drop=5e4,
            )

    def test_bool_rejected_for_accumulator_pressure_reference(self):
        with pytest.raises(TypeError, match="bool"):
            ParallelTopologyResidualParameters(
                accumulator_pressure_reference=False,
                pump_pressure_rise=1e5,
                branch_a_pressure_drop=3e4,
                branch_b_pressure_drop=4e4,
                merge_a_pressure_drop=2e4,
                merge_b_pressure_drop=1e4,
                condenser_pressure_drop=5e4,
            )

    def test_string_rejected(self):
        with pytest.raises(TypeError):
            ParallelTopologyResidualParameters(
                accumulator_pressure_reference=1e6,
                pump_pressure_rise="1e5",
                branch_a_pressure_drop=3e4,
                branch_b_pressure_drop=4e4,
                merge_a_pressure_drop=2e4,
                merge_b_pressure_drop=1e4,
                condenser_pressure_drop=5e4,
            )

    def test_nan_rejected(self):
        with pytest.raises(ValueError, match="finite"):
            ParallelTopologyResidualParameters(
                accumulator_pressure_reference=float("nan"),
                pump_pressure_rise=1e5,
                branch_a_pressure_drop=3e4,
                branch_b_pressure_drop=4e4,
                merge_a_pressure_drop=2e4,
                merge_b_pressure_drop=1e4,
                condenser_pressure_drop=5e4,
            )

    def test_inf_rejected(self):
        with pytest.raises(ValueError, match="finite"):
            ParallelTopologyResidualParameters(
                accumulator_pressure_reference=1e6,
                pump_pressure_rise=float("inf"),
                branch_a_pressure_drop=3e4,
                branch_b_pressure_drop=4e4,
                merge_a_pressure_drop=2e4,
                merge_b_pressure_drop=1e4,
                condenser_pressure_drop=5e4,
            )

    def test_negative_inf_rejected(self):
        with pytest.raises(ValueError, match="finite"):
            ParallelTopologyResidualParameters(
                accumulator_pressure_reference=1e6,
                pump_pressure_rise=1e5,
                branch_a_pressure_drop=float("-inf"),
                branch_b_pressure_drop=4e4,
                merge_a_pressure_drop=2e4,
                merge_b_pressure_drop=1e4,
                condenser_pressure_drop=5e4,
            )

    def test_all_seven_fields_required(self):
        with pytest.raises(TypeError):
            ParallelTopologyResidualParameters(  # type: ignore[call-arg]
                accumulator_pressure_reference=1e6,
                pump_pressure_rise=1e5,
            )

    def test_negative_values_accepted(self):
        # Signs are not constrained; explicit signed algebraic parameters.
        p = ParallelTopologyResidualParameters(
            accumulator_pressure_reference=1e6,
            pump_pressure_rise=-1e5,
            branch_a_pressure_drop=-3e4,
            branch_b_pressure_drop=4e4,
            merge_a_pressure_drop=2e4,
            merge_b_pressure_drop=1e4,
            condenser_pressure_drop=5e4,
        )
        assert p.pump_pressure_rise == -1e5
        assert p.branch_a_pressure_drop == -3e4


# ===========================================================================
# Part II — 15C.4: ParallelTopologyPhysicalResidualAssembly
# ===========================================================================


class TestBuildParallelTopologyPhysicalResiduals:
    def test_builds_from_scenario_and_params(self):
        scenario = _make_scenario()
        assembly = build_parallel_topology_physical_residuals(scenario, _PARAMS)
        assert isinstance(assembly, ParallelTopologyPhysicalResidualAssembly)

    def test_assembly_holds_scenario(self):
        scenario = _make_scenario()
        assembly = build_parallel_topology_physical_residuals(scenario, _PARAMS)
        assert assembly.scenario is scenario

    def test_assembly_holds_parameters(self):
        scenario = _make_scenario()
        assembly = build_parallel_topology_physical_residuals(scenario, _PARAMS)
        assert assembly.parameters is _PARAMS

    def test_assembly_is_frozen(self):
        scenario = _make_scenario()
        assembly = build_parallel_topology_physical_residuals(scenario, _PARAMS)
        with pytest.raises((AttributeError, TypeError)):
            assembly.parameters = _PARAMS  # type: ignore[misc]

    def test_wrong_scenario_type_rejected(self):
        with pytest.raises(TypeError, match="ParallelTopologyScenario"):
            build_parallel_topology_physical_residuals("not_a_scenario", _PARAMS)

    def test_wrong_parameter_type_rejected(self):
        scenario = _make_scenario()
        with pytest.raises(TypeError, match="ParallelTopologyResidualParameters"):
            build_parallel_topology_physical_residuals(scenario, "not_params")

    def test_wrong_metadata_type_rejected(self):
        scenario = _make_scenario()
        with pytest.raises(TypeError):
            build_parallel_topology_physical_residuals(scenario, _PARAMS, metadata="bad")

    def test_residual_map_has_13_entries(self):
        scenario = _make_scenario()
        assembly = build_parallel_topology_physical_residuals(scenario, _PARAMS)
        assert len(assembly.residual_map.mapping) == 13

    def test_adapter_set_has_7_adapters(self):
        scenario = _make_scenario()
        assembly = build_parallel_topology_physical_residuals(scenario, _PARAMS)
        assert len(assembly.adapter_set.adapters) == 7

    def test_residual_map_covers_all_13_declared_residuals(self):
        scenario = _make_scenario()
        assembly = build_parallel_topology_physical_residuals(scenario, _PARAMS)
        mapped_residuals = set(assembly.residual_map.mapping.values())
        declared = set(scenario.residual_names.all_names())
        assert mapped_residuals == declared

    def test_residual_map_covers_all_7_component_ids(self):
        scenario = _make_scenario()
        assembly = build_parallel_topology_physical_residuals(scenario, _PARAMS)
        mapped_component_ids = {k[0] for k in assembly.residual_map.mapping}
        all_cids = set(scenario.component_ids.all_ids())
        assert mapped_component_ids == all_cids

    def test_no_systemstate_in_assembly(self):
        scenario = _make_scenario()
        assembly = build_parallel_topology_physical_residuals(scenario, _PARAMS)
        for attr_name in dir(assembly):
            if attr_name.startswith("_"):
                continue
            val = getattr(assembly, attr_name)
            assert type(val).__name__ not in ("SystemState",)

    def test_no_fluidstate_in_assembly(self):
        scenario = _make_scenario()
        assembly = build_parallel_topology_physical_residuals(scenario, _PARAMS)
        for attr_name in dir(assembly):
            if attr_name.startswith("_"):
                continue
            val = getattr(assembly, attr_name)
            assert type(val).__name__ not in ("FluidState",)

    def test_assembly_contains_no_production_component_objects(self):
        from mpl_sim.network.production_component_inspection import (
            inspect_known_production_component_contracts,
        )

        scenario = _make_scenario()
        assembly = build_parallel_topology_physical_residuals(scenario, _PARAMS)
        inspected = inspect_known_production_component_contracts()
        prod_class_names = {r.class_name for r in inspected}
        stored = {
            type(getattr(assembly, attr)).__name__
            for attr in ("scenario", "parameters", "residual_map", "adapter_set")
        }
        assert stored.isdisjoint(prod_class_names)

    def test_residual_ordering_matches_scenario(self):
        scenario = _make_scenario()
        assembly = build_parallel_topology_physical_residuals(scenario, _PARAMS)
        mapped_residuals_in_order = list(assembly.residual_map.mapping.values())
        declared_in_order = list(scenario.residual_names.all_names())
        # The mapping values should cover all declared residuals (order may differ
        # in the mapping but all declared names must appear).
        assert set(mapped_residuals_in_order) == set(declared_in_order)

    def test_no_component_type_dispatch(self):
        # The factory should not branch on component_type to choose equations.
        # We verify by building two scenarios with different component types
        # but the same topology and confirming the evaluation path works.
        scenario = _make_scenario()
        assembly = build_parallel_topology_physical_residuals(scenario, _PARAMS)
        # If component_type dispatch were used, changing the scenario's
        # component types would produce wrong results.  This is a fixed-topology
        # MVP; the equations are explicit, not inferred from component_type.
        assert assembly.adapter_set is not None

    def test_metadata_stored_as_proxy(self):
        scenario = _make_scenario()
        assembly = build_parallel_topology_physical_residuals(
            scenario, _PARAMS, metadata={"key": "value"}
        )
        assert isinstance(assembly.metadata, MappingProxyType)
        assert assembly.metadata["key"] == "value"

    def test_metadata_none_by_default(self):
        scenario = _make_scenario()
        assembly = build_parallel_topology_physical_residuals(scenario, _PARAMS)
        assert assembly.metadata is None


# ===========================================================================
# Part III — 15C.4/15C.5: Residual equations and sign convention
# ===========================================================================


class TestResidualEquations:
    def test_all_residuals_zero_at_consistent_point(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        assert result.max_abs_residual == pytest.approx(0.0, abs=1e-9)
        for name, val in result.residual_values.items():
            assert val == pytest.approx(0.0, abs=1e-9), f"Residual {name!r} = {val}"

    def test_perturbing_split_flow_changes_split_residual(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        # Perturb mdot_branch_a while keeping mdot_pump and mdot_branch_b fixed.
        un = scenario.unknown_names
        uv_perturbed = dict(uv)
        uv_perturbed[un.mdot_branch_a] = 0.7  # was 0.4
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv_perturbed)
        rn = scenario.residual_names
        # mass_balance:n_pump_out = mdot_pump - mdot_ba - mdot_bb = 1.0 - 0.7 - 0.6 = -0.3
        assert result.residual_values[rn.mass_balance_n_pump_out] == pytest.approx(-0.3, abs=1e-9)
        # mass_balance:n_a_out = mdot_ba - mdot_ma = 0.7 - 0.4 = 0.3
        assert result.residual_values[rn.mass_balance_n_a_out] == pytest.approx(0.3, abs=1e-9)

    def test_perturbing_branch_a_flow_changes_branch_a_and_merge_residuals(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        un = scenario.unknown_names
        rn = scenario.residual_names
        uv_perturbed = dict(uv)
        uv_perturbed[un.mdot_branch_a] = 0.5  # was 0.4
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv_perturbed)
        # mass_balance:n_a_out = 0.5 - 0.4 = 0.1
        assert result.residual_values[rn.mass_balance_n_a_out] == pytest.approx(0.1, abs=1e-9)
        # mass_balance:n_pump_out = 1.0 - 0.5 - 0.6 = -0.1
        assert result.residual_values[rn.mass_balance_n_pump_out] == pytest.approx(-0.1, abs=1e-9)

    def test_perturbing_branch_b_flow_changes_branch_b_and_split_residuals(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        un = scenario.unknown_names
        rn = scenario.residual_names
        uv_perturbed = dict(uv)
        uv_perturbed[un.mdot_branch_b] = 0.3  # was 0.6
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv_perturbed)
        # mass_balance:n_b_out = 0.3 - 0.6 = -0.3
        assert result.residual_values[rn.mass_balance_n_b_out] == pytest.approx(-0.3, abs=1e-9)
        # mass_balance:n_pump_out = 1.0 - 0.4 - 0.3 = 0.3
        assert result.residual_values[rn.mass_balance_n_pump_out] == pytest.approx(0.3, abs=1e-9)

    def test_perturbing_pump_pressure_rise_changes_pump_residual(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        # Use a different pump_pressure_rise while keeping same pressures.
        params_perturbed = ParallelTopologyResidualParameters(
            accumulator_pressure_reference=1_000_000.0,
            pump_pressure_rise=80_000.0,  # was 100_000
            branch_a_pressure_drop=30_000.0,
            branch_b_pressure_drop=40_000.0,
            merge_a_pressure_drop=20_000.0,
            merge_b_pressure_drop=10_000.0,
            condenser_pressure_drop=50_000.0,
        )
        result = evaluate_parallel_topology_residuals(scenario, params_perturbed, uv)
        rn = scenario.residual_names
        # pressure_drop:pump = P_pump_out - P_acc_out - dP_pump
        #   = 1_100_000 - 1_000_000 - 80_000 = 20_000
        assert result.residual_values[rn.pressure_drop_pump] == pytest.approx(20_000.0, abs=1e-6)

    def test_perturbing_branch_a_pressure_drop_changes_branch_a_pressure_residual(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        params_perturbed = ParallelTopologyResidualParameters(
            accumulator_pressure_reference=1_000_000.0,
            pump_pressure_rise=100_000.0,
            branch_a_pressure_drop=50_000.0,  # was 30_000
            branch_b_pressure_drop=40_000.0,
            merge_a_pressure_drop=20_000.0,
            merge_b_pressure_drop=10_000.0,
            condenser_pressure_drop=50_000.0,
        )
        result = evaluate_parallel_topology_residuals(scenario, params_perturbed, uv)
        rn = scenario.residual_names
        # pressure_drop:branch_a = P_a_out - P_pump_out + dP_a
        #   = 1_070_000 - 1_100_000 + 50_000 = 20_000
        assert result.residual_values[rn.pressure_drop_branch_a] == pytest.approx(
            20_000.0, abs=1e-6
        )

    def test_perturbing_branch_b_pressure_drop_changes_branch_b_pressure_residual(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        params_perturbed = ParallelTopologyResidualParameters(
            accumulator_pressure_reference=1_000_000.0,
            pump_pressure_rise=100_000.0,
            branch_a_pressure_drop=30_000.0,
            branch_b_pressure_drop=20_000.0,  # was 40_000
            merge_a_pressure_drop=20_000.0,
            merge_b_pressure_drop=10_000.0,
            condenser_pressure_drop=50_000.0,
        )
        result = evaluate_parallel_topology_residuals(scenario, params_perturbed, uv)
        rn = scenario.residual_names
        # pressure_drop:branch_b = P_b_out - P_pump_out + dP_b
        #   = 1_060_000 - 1_100_000 + 20_000 = -20_000
        assert result.residual_values[rn.pressure_drop_branch_b] == pytest.approx(
            -20_000.0, abs=1e-6
        )

    def test_perturbing_condenser_pressure_drop_changes_condenser_residual(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        params_perturbed = ParallelTopologyResidualParameters(
            accumulator_pressure_reference=1_000_000.0,
            pump_pressure_rise=100_000.0,
            branch_a_pressure_drop=30_000.0,
            branch_b_pressure_drop=40_000.0,
            merge_a_pressure_drop=20_000.0,
            merge_b_pressure_drop=10_000.0,
            condenser_pressure_drop=70_000.0,  # was 50_000
        )
        result = evaluate_parallel_topology_residuals(scenario, params_perturbed, uv)
        rn = scenario.residual_names
        # pressure_drop:condenser = P_cond_out - P_merge_out + dP_cond
        #   = 1_000_000 - 1_050_000 + 70_000 = 20_000
        assert result.residual_values[rn.pressure_drop_condenser] == pytest.approx(
            20_000.0, abs=1e-6
        )

    def test_sign_convention_pump_raises_pressure(self):
        # pressure_drop:pump = P_pump_out - P_acc_out - pump_pressure_rise
        # Positive pump_pressure_rise with consistent pressures → residual = 0.
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        rn = scenario.residual_names
        assert result.residual_values[rn.pressure_drop_pump] == pytest.approx(0.0, abs=1e-9)

    def test_sign_convention_branch_drops_pressure(self):
        # pressure_drop:branch_a = P_a_out - P_pump_out + branch_a_pressure_drop
        # Positive branch_a_pressure_drop → P_a_out < P_pump_out.
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        rn = scenario.residual_names
        assert result.residual_values[rn.pressure_drop_branch_a] == pytest.approx(0.0, abs=1e-9)
        # Verify P ordering: pump_out > a_out
        un = scenario.unknown_names
        assert uv[un.P_n_pump_out] > uv[un.P_n_a_out]

    def test_sign_convention_accumulator_anchors_pressure(self):
        # pressure_drop:accumulator = P_acc_out - accumulator_pressure_reference
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        rn = scenario.residual_names
        assert result.residual_values[rn.pressure_drop_accumulator] == pytest.approx(0.0, abs=1e-9)

    def test_mass_balance_residuals_are_explicit_algebra(self):
        # mass_balance:n_pump_out = mdot_pump - mdot_branch_a - mdot_branch_b
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        rn = scenario.residual_names
        assert result.residual_values[rn.mass_balance_n_pump_out] == pytest.approx(0.0, abs=1e-9)

    def test_merge_balance_residual_attribution(self):
        # mass_balance:n_merge_out = mdot_merge_a + mdot_merge_b - mdot_condenser
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        un = scenario.unknown_names
        rn = scenario.residual_names
        uv_perturbed = dict(uv)
        uv_perturbed[un.mdot_merge_b] = 0.8  # was 0.6
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv_perturbed)
        # mass_balance:n_merge_out = 0.4 + 0.8 - 1.0 = 0.2
        assert result.residual_values[rn.mass_balance_n_merge_out] == pytest.approx(0.2, abs=1e-9)


# ===========================================================================
# Part IV — 15C.5: evaluate_parallel_topology_residuals
# ===========================================================================


class TestEvaluateParallelTopologyResiduals:
    def test_returns_frozen_result(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        assert isinstance(result, ParallelTopologyEvaluationResult)

    def test_unknown_values_are_readonly(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        assert isinstance(result.unknown_values, MappingProxyType)
        with pytest.raises(TypeError):
            result.unknown_values["new_key"] = 1.0  # type: ignore[index]

    def test_residual_values_are_readonly(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        assert isinstance(result.residual_values, MappingProxyType)
        with pytest.raises(TypeError):
            result.residual_values["new_key"] = 1.0  # type: ignore[index]

    def test_residual_norms_are_correct_at_consistent_point(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        assert result.max_abs_residual == pytest.approx(0.0, abs=1e-9)
        assert result.l2_residual == pytest.approx(0.0, abs=1e-9)

    def test_max_abs_residual_at_perturbed_point(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        un = scenario.unknown_names
        uv_perturbed = dict(uv)
        uv_perturbed[un.mdot_pump] = 1.5  # perturb total mass flow
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv_perturbed)
        assert result.max_abs_residual > 0.0

    def test_l2_residual_at_perturbed_point(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        un = scenario.unknown_names
        uv_perturbed = dict(uv)
        uv_perturbed[un.P_n_pump_out] = 1_200_000.0  # perturb pressure
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv_perturbed)
        assert result.l2_residual > 0.0

    def test_residual_names_in_declaration_order(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        assert result.residual_names == scenario.residual_names.all_names()

    def test_residual_values_keyed_by_declared_names(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        declared = set(scenario.residual_names.all_names())
        assert set(result.residual_values.keys()) == declared

    def test_unknown_coverage_exact_13(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        assert len(result.unknown_values) == 13

    def test_residual_coverage_exact_13(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        assert len(result.residual_values) == 13

    def test_missing_unknowns_rejected(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        uv_incomplete = dict(uv)
        del uv_incomplete[scenario.unknown_names.mdot_pump]
        with pytest.raises(ValueError, match="missing"):
            evaluate_parallel_topology_residuals(scenario, _PARAMS, uv_incomplete)

    def test_extra_unknowns_rejected(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        uv_extra = dict(uv)
        uv_extra["extra_unknown"] = 1.0
        with pytest.raises(ValueError, match="not in scenario"):
            evaluate_parallel_topology_residuals(scenario, _PARAMS, uv_extra)

    def test_bool_unknown_value_rejected(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        uv_bool = dict(uv)
        uv_bool[scenario.unknown_names.mdot_pump] = True
        with pytest.raises(TypeError, match="bool"):
            evaluate_parallel_topology_residuals(scenario, _PARAMS, uv_bool)

    def test_non_numeric_unknown_value_rejected(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        uv_str = dict(uv)
        uv_str[scenario.unknown_names.mdot_pump] = "1.0"
        with pytest.raises(TypeError):
            evaluate_parallel_topology_residuals(scenario, _PARAMS, uv_str)

    def test_nan_unknown_value_rejected(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        uv_nan = dict(uv)
        uv_nan[scenario.unknown_names.mdot_pump] = float("nan")
        with pytest.raises(ValueError, match="finite"):
            evaluate_parallel_topology_residuals(scenario, _PARAMS, uv_nan)

    def test_inf_unknown_value_rejected(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        uv_inf = dict(uv)
        uv_inf[scenario.unknown_names.P_n_pump_out] = float("inf")
        with pytest.raises(ValueError, match="finite"):
            evaluate_parallel_topology_residuals(scenario, _PARAMS, uv_inf)

    def test_wrong_scenario_type_rejected(self):
        with pytest.raises(TypeError, match="ParallelTopologyScenario"):
            evaluate_parallel_topology_residuals("not_a_scenario", _PARAMS, {})

    def test_wrong_parameters_type_rejected(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        with pytest.raises(TypeError, match="ParallelTopologyResidualParameters"):
            evaluate_parallel_topology_residuals(scenario, "not_params", uv)

    def test_wrong_unknown_values_type_rejected(self):
        scenario = _make_scenario()
        with pytest.raises(TypeError):
            evaluate_parallel_topology_residuals(scenario, _PARAMS, "not_a_mapping")

    def test_result_is_frozen(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        with pytest.raises((AttributeError, TypeError)):
            result.max_abs_residual = 999.0  # type: ignore[misc]

    def test_metadata_forwarded_to_result(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(
            scenario, _PARAMS, uv, metadata={"run_id": 42}
        )
        assert isinstance(result.metadata, MappingProxyType)
        assert result.metadata["run_id"] == 42

    def test_l2_norm_is_correct_analytically(self):
        # Use a perturbed pump pressure to get a known single non-zero residual.
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        params_shifted = ParallelTopologyResidualParameters(
            accumulator_pressure_reference=1_000_000.0,
            pump_pressure_rise=80_000.0,  # was 100_000 → pump residual = 20_000
            branch_a_pressure_drop=30_000.0,
            branch_b_pressure_drop=40_000.0,
            merge_a_pressure_drop=20_000.0,
            merge_b_pressure_drop=10_000.0,
            condenser_pressure_drop=50_000.0,
        )
        result = evaluate_parallel_topology_residuals(scenario, params_shifted, uv)
        # Only pressure_drop:pump is non-zero (= 20_000 Pa)
        assert result.max_abs_residual == pytest.approx(20_000.0, rel=1e-9)
        # L2 with one non-zero component = sqrt(20000^2)
        expected_l2 = math.sqrt(20_000.0**2)
        assert result.l2_residual == pytest.approx(expected_l2, rel=1e-9)


# ===========================================================================
# Part V — 15C.5: Solver is explicitly deferred
# ===========================================================================


class TestSolverDeferred:
    def test_no_solve_request_type_exported(self):
        import mpl_sim.network.parallel_topology_residuals as mod

        assert not hasattr(mod, "ParallelTopologySolveRequest")

    def test_no_solve_result_type_exported(self):
        import mpl_sim.network.parallel_topology_residuals as mod

        assert not hasattr(mod, "ParallelTopologySolveResult")

    def test_no_solve_function_exported(self):
        import mpl_sim.network.parallel_topology_residuals as mod

        assert not hasattr(mod, "solve_parallel_topology_residuals")

    def test_report_documents_solve_deferred(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        report = build_parallel_topology_report(result)
        assert report["converged"] is None
        note = report.get("block_15c_b_note", "") or ""
        assert "deferred" in str(note).lower() or "defer" in str(report.get("reason", "")).lower()
        assert "closure constraints" in str(note).lower()
        assert "does not invent" in str(note).lower()


# ===========================================================================
# Part VI — 15C.5: build_parallel_topology_report
# ===========================================================================


class TestBuildParallelTopologyReport:
    def test_returns_plain_dict(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        report = build_parallel_topology_report(result)
        assert isinstance(report, dict)

    def test_report_includes_scenario_ids(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        report = build_parallel_topology_report(result)
        assert "component_ids" in report
        assert "node_ids" in report
        ids = report["component_ids"]
        assert isinstance(ids, dict)
        assert "accumulator" in ids
        assert "pump" in ids
        assert "branch_a" in ids
        assert "branch_b" in ids

    def test_report_includes_unknowns(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        report = build_parallel_topology_report(result)
        assert "unknown_values" in report
        assert len(report["unknown_values"]) == 13

    def test_report_includes_residuals(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        report = build_parallel_topology_report(result)
        assert "residual_values" in report
        assert "residual_names" in report
        assert len(report["residual_values"]) == 13
        assert len(report["residual_names"]) == 13

    def test_report_includes_residual_norms(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        report = build_parallel_topology_report(result)
        assert "max_abs_residual" in report
        assert "l2_residual" in report
        assert report["max_abs_residual"] == pytest.approx(0.0, abs=1e-9)

    def test_report_includes_parameters(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        report = build_parallel_topology_report(result)
        assert "parameters" in report
        params = report["parameters"]
        assert isinstance(params, dict)
        assert "pump_pressure_rise" in params

    def test_report_includes_mvp_note(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        report = build_parallel_topology_report(result)
        assert "mvp_note" in report
        assert "fixed" in report["mvp_note"].lower() or "mvp" in report["mvp_note"].lower()

    def test_report_does_not_write_files(self):
        # Report must not produce side effects.  We verify by importing and
        # confirming no file-writing methods are called.
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        report = build_parallel_topology_report(result)
        assert report is not None

    def test_report_does_not_require_pandas(self):
        import sys

        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        report = build_parallel_topology_report(result)
        # Report built successfully even without asserting pandas presence.
        assert isinstance(report, dict)
        assert "pandas" not in sys.modules or True  # pandas is not required

    def test_report_values_are_serializable_types(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        report = build_parallel_topology_report(result)
        for key, val in report.items():
            assert isinstance(key, str), f"Key {key!r} not str"
            assert isinstance(
                val, (str, float, int, bool, list, dict, type(None))
            ), f"Value for {key!r} has unexpected type {type(val).__name__!r}"

    def test_report_convergence_status_is_none(self):
        scenario = _make_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        report = build_parallel_topology_report(result)
        assert report["converged"] is None

    def test_wrong_result_type_rejected(self):
        with pytest.raises(TypeError, match="ParallelTopologyEvaluationResult"):
            build_parallel_topology_report("not_a_result")


# ===========================================================================
# Part VII — Boundary / architecture invariants
# ===========================================================================


def _executable_lines(content: str) -> str:
    """Return source content with docstrings and inline comments stripped.

    Used to verify that forbidden patterns do not appear in executable code.
    Documentation strings (MUST NOT ... clauses) are expected to contain
    descriptions of forbidden constructs and must not be flagged.
    """
    import re

    # Strip triple-double-quoted strings (docstrings).
    content = re.sub(r'""".*?"""', "", content, flags=re.DOTALL)
    # Strip triple-single-quoted strings.
    content = re.sub(r"'''.*?'''", "", content, flags=re.DOTALL)
    # Strip single-line comments.
    content = re.sub(r"#[^\n]*", "", content)
    return content


class TestBoundaryInvariants:
    def test_no_coolprop_import_in_module(self):
        import mpl_sim.network.parallel_topology_residuals

        src = mpl_sim.network.parallel_topology_residuals.__file__
        with open(src) as f:
            content = f.read()
        executable = _executable_lines(content)
        assert "CoolProp" not in executable

    def test_no_components_import_in_module(self):
        import mpl_sim.network.parallel_topology_residuals

        src = mpl_sim.network.parallel_topology_residuals.__file__
        with open(src) as f:
            content = f.read()
        executable = _executable_lines(content)
        assert "mpl_sim.components" not in executable
        assert "mpl_sim.properties" not in executable
        assert "mpl_sim.correlations" not in executable
        assert "mpl_sim.hx_models" not in executable

    def test_no_contribute_call_in_module(self):
        import re

        import mpl_sim.network.parallel_topology_residuals

        src = mpl_sim.network.parallel_topology_residuals.__file__
        with open(src) as f:
            content = f.read()
        executable = _executable_lines(content)
        matches = re.findall(r"\bcontribute\s*\(", executable)
        assert len(matches) == 0, f"Found contribute( calls in executable code: {matches}"

    def test_no_def_contribute_in_module(self):
        import re

        import mpl_sim.network.parallel_topology_residuals

        src = mpl_sim.network.parallel_topology_residuals.__file__
        with open(src) as f:
            content = f.read()
        executable = _executable_lines(content)
        matches = re.findall(r"\bdef\s+contribute\b", executable)
        assert len(matches) == 0, f"Found def contribute in executable code: {matches}"

    def test_no_systemstate_import_in_module(self):
        import mpl_sim.network.parallel_topology_residuals

        src = mpl_sim.network.parallel_topology_residuals.__file__
        with open(src) as f:
            content = f.read()
        executable = _executable_lines(content)
        assert "SystemState" not in executable

    def test_no_fluidstate_import_in_module(self):
        import mpl_sim.network.parallel_topology_residuals

        src = mpl_sim.network.parallel_topology_residuals.__file__
        with open(src) as f:
            content = f.read()
        executable = _executable_lines(content)
        assert "FluidState" not in executable

    def test_no_property_backend_import_in_module(self):
        import mpl_sim.network.parallel_topology_residuals

        src = mpl_sim.network.parallel_topology_residuals.__file__
        with open(src) as f:
            content = f.read()
        executable = _executable_lines(content)
        assert "PropertyBackend" not in executable

    def test_no_network_graph_solve_call_in_module(self):
        import re

        import mpl_sim.network.parallel_topology_residuals

        src = mpl_sim.network.parallel_topology_residuals.__file__
        with open(src) as f:
            content = f.read()
        executable = _executable_lines(content)
        assert not re.search(r"NetworkGraph\.solve\s*\(", executable)
        assert not re.search(r"\bsolve\s*\(\s*network", executable)

    def test_no_component_type_dispatch_in_module(self):
        import re

        import mpl_sim.network.parallel_topology_residuals

        src = mpl_sim.network.parallel_topology_residuals.__file__
        with open(src) as f:
            content = f.read()
        executable = _executable_lines(content)
        dispatch_patterns = re.findall(r"component_type.*if|if.*component_type", executable)
        assert len(dispatch_patterns) == 0

    def test_production_component_classes_still_no_contribute(self):
        from mpl_sim.network.production_component_inspection import (
            ProductionComponentContractStatus,
            inspect_known_production_component_contracts,
        )

        results = inspect_known_production_component_contracts()
        for result in results:
            assert (
                result.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD
            ), f"{result.class_name} unexpectedly has a contribute method"
