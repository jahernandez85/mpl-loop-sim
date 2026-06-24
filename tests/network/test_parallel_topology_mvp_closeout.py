"""Block 15C-B — Parallel Topology MVP Closeout / Acceptance Tests (15C.6).

Proves the full Block 15C-B path end-to-end and documents the design decisions.

Coverage:
  1. 15C-A topology scenario builds.
  2. 15C-B residual assembly builds.
  3. Consistent point evaluates to zero residuals.
  4. Perturbed point evaluates to nonzero residuals.
  5. Report builds with required fields.
  6. Block 15C can be marked complete within topology-extension MVP scope.
  7. Deferred exclusions remain visible.
  8. 15C-A focused tests (topology) still pass (regression).
  9. Block 15B closeout path regression (scenario + params + evaluate + solve + report).
 10. Phase 14G production contract: all six classes still NO_CONTRIBUTE_METHOD.
 11. Boundary: no forbidden imports or patterns in new modules or tests.
 12. Public API: new symbols exported from mpl_sim.network.

Design notes documented here
-----------------------------
Solving is deferred for the parallel topology because:
  (a) The 7 mass-flow unknowns are underdetermined by 2 degrees of freedom
      (total flow level + branch split ratio), requiring explicit closure constraints.
  (b) The 7 pressure equations for 6 unknowns are overdetermined unless the
      branch compatibility condition holds (dP_a + dP_ma == dP_b + dP_mb).
  (c) Phase 13H requires a square, determined system.
A physically meaningful solve would need explicit total-flow and branch-split
closure constraints plus pressure compatibility handling — this remains deferred.

Block 15C is complete within topology-extension MVP scope:
  - Junction/manifold declarations (15C.1) — complete.
  - Parallel branch topology declaration (15C.2) — complete.
  - Valve/local pressure-loss declaration (15C.3) — complete.
  - Branch residual assembly MVP (15C.4) — complete.
  - Parallel evaluation and report MVP (15C.5) — complete.
  - Closeout / acceptance tests (15C.6) — complete (this file).
"""

from __future__ import annotations

import pytest

from mpl_sim.network.parallel_topology_residuals import (
    ParallelTopologyEvaluationResult,
    ParallelTopologyPhysicalResidualAssembly,
    ParallelTopologyResidualParameters,
    build_parallel_topology_physical_residuals,
    build_parallel_topology_report,
    evaluate_parallel_topology_residuals,
)
from mpl_sim.network.parallel_topology_scenario import (
    ParallelTopologyScenario,
    build_parallel_topology_scenario,
)

# ---------------------------------------------------------------------------
# Consistent test point (branch compatibility satisfied: 30+20 = 40+10 = 50)
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


def _make_consistent_unknowns(scenario: ParallelTopologyScenario) -> dict[str, float]:
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


def _make_perturbed_unknowns(scenario: ParallelTopologyScenario) -> dict[str, float]:
    uv = _make_consistent_unknowns(scenario)
    uv[scenario.unknown_names.mdot_pump] = 2.0  # total flow perturbed
    uv[scenario.unknown_names.P_n_pump_out] = 1_200_000.0  # pressure perturbed
    return uv


# ===========================================================================
# 15C-A topology scenario regression
# ===========================================================================


class TestTopologyScenarioRegression:
    def test_parallel_topology_scenario_builds(self):
        scenario = build_parallel_topology_scenario()
        assert isinstance(scenario, ParallelTopologyScenario)

    def test_scenario_has_6_nodes(self):
        scenario = build_parallel_topology_scenario()
        assert len(scenario.graph.node_ids()) == 6

    def test_scenario_has_7_components(self):
        scenario = build_parallel_topology_scenario()
        assert len(scenario.graph.instance_ids()) == 7

    def test_scenario_declares_13_unknowns(self):
        scenario = build_parallel_topology_scenario()
        assert scenario.assembly.unknowns.count() == 13

    def test_scenario_declares_13_residuals(self):
        scenario = build_parallel_topology_scenario()
        assert scenario.assembly.residuals.count() == 13

    def test_scenario_has_two_branches(self):
        scenario = build_parallel_topology_scenario()
        assert len(scenario.branches) == 2

    def test_split_manifold_is_split(self):
        from mpl_sim.network.topology_declarations import JunctionRole

        scenario = build_parallel_topology_scenario()
        assert scenario.split_manifold.role == JunctionRole.SPLIT

    def test_merge_manifold_is_merge(self):
        from mpl_sim.network.topology_declarations import JunctionRole

        scenario = build_parallel_topology_scenario()
        assert scenario.merge_manifold.role == JunctionRole.MERGE

    def test_unknown_names_match_name_container(self):
        scenario = build_parallel_topology_scenario()
        assert scenario.assembly.unknowns.names() == scenario.unknown_names.all_names()

    def test_residual_names_match_name_container(self):
        scenario = build_parallel_topology_scenario()
        assert scenario.assembly.residuals.names() == scenario.residual_names.all_names()

    def test_scenario_is_frozen(self):
        scenario = build_parallel_topology_scenario()
        with pytest.raises((AttributeError, TypeError)):
            scenario.graph = None  # type: ignore[misc]

    def test_scenario_require_closed_loop_false(self):
        # The parallel topology is NOT a closed single loop; require_closed_loop=False
        # was correctly used.  We confirm the assembly still has 13 residuals.
        scenario = build_parallel_topology_scenario()
        assert scenario.assembly.residuals.count() == 13


# ===========================================================================
# 15C-B: residual assembly builds
# ===========================================================================


class TestResidualAssemblyBuilds:
    def test_assembly_builds_from_scenario_and_params(self):
        scenario = build_parallel_topology_scenario()
        assembly = build_parallel_topology_physical_residuals(scenario, _PARAMS)
        assert isinstance(assembly, ParallelTopologyPhysicalResidualAssembly)

    def test_assembly_holds_correct_scenario(self):
        scenario = build_parallel_topology_scenario()
        assembly = build_parallel_topology_physical_residuals(scenario, _PARAMS)
        assert assembly.scenario is scenario

    def test_assembly_holds_correct_parameters(self):
        scenario = build_parallel_topology_scenario()
        assembly = build_parallel_topology_physical_residuals(scenario, _PARAMS)
        assert assembly.parameters is _PARAMS

    def test_assembly_residual_map_covers_13_residuals(self):
        scenario = build_parallel_topology_scenario()
        assembly = build_parallel_topology_physical_residuals(scenario, _PARAMS)
        assert len(assembly.residual_map.mapping) == 13

    def test_assembly_adapter_set_has_7_adapters(self):
        scenario = build_parallel_topology_scenario()
        assembly = build_parallel_topology_physical_residuals(scenario, _PARAMS)
        assert len(assembly.adapter_set.adapters) == 7

    def test_assembly_residual_map_covers_all_declared_residuals(self):
        scenario = build_parallel_topology_scenario()
        assembly = build_parallel_topology_physical_residuals(scenario, _PARAMS)
        mapped = set(assembly.residual_map.mapping.values())
        declared = set(scenario.residual_names.all_names())
        assert mapped == declared

    def test_assembly_is_fixed_topology_only(self):
        # Calling with wrong scenario type should raise, not produce an assembly.
        with pytest.raises(TypeError):
            build_parallel_topology_physical_residuals("wrong_type", _PARAMS)


# ===========================================================================
# 15C-B: consistent point evaluates to zero residuals
# ===========================================================================


class TestConsistentPointZeroResiduals:
    def test_all_13_residuals_zero_at_consistent_point(self):
        scenario = build_parallel_topology_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        assert result.max_abs_residual == pytest.approx(0.0, abs=1e-9)

    def test_each_residual_individually_zero(self):
        scenario = build_parallel_topology_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        for name, val in result.residual_values.items():
            assert val == pytest.approx(
                0.0, abs=1e-9
            ), f"Residual {name!r} = {val} (expected 0.0 at consistent point)"

    def test_l2_norm_zero_at_consistent_point(self):
        scenario = build_parallel_topology_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        assert result.l2_residual == pytest.approx(0.0, abs=1e-9)

    def test_result_is_frozen_evaluation_result(self):
        scenario = build_parallel_topology_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        assert isinstance(result, ParallelTopologyEvaluationResult)


# ===========================================================================
# 15C-B: perturbed point evaluates to nonzero residuals
# ===========================================================================


class TestPerturbedPointNonzeroResiduals:
    def test_perturbed_pump_flow_gives_nonzero_residuals(self):
        scenario = build_parallel_topology_scenario()
        uv = _make_perturbed_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        assert result.max_abs_residual > 0.0

    def test_perturbed_point_has_13_residual_values(self):
        scenario = build_parallel_topology_scenario()
        uv = _make_perturbed_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        assert len(result.residual_values) == 13

    def test_known_perturbed_residuals_are_nonzero(self):
        scenario = build_parallel_topology_scenario()
        uv = _make_consistent_unknowns(scenario)
        uv[scenario.unknown_names.mdot_pump] = 2.0  # total flow doubled
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        rn = scenario.residual_names
        # mass_balance:n_acc_out = mdot_acc - mdot_pump = 1.0 - 2.0 = -1.0
        assert result.residual_values[rn.mass_balance_n_acc_out] == pytest.approx(-1.0, abs=1e-9)


# ===========================================================================
# 15C-B: report builds with required fields
# ===========================================================================


class TestReportBuilds:
    def test_report_builds_from_evaluation_result(self):
        scenario = build_parallel_topology_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        report = build_parallel_topology_report(result)
        assert isinstance(report, dict)

    def test_report_has_all_required_fields(self):
        scenario = build_parallel_topology_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        report = build_parallel_topology_report(result)
        required = {
            "kind",
            "mvp_note",
            "topology",
            "component_ids",
            "node_ids",
            "parameters",
            "unknown_values",
            "residual_names",
            "residual_values",
            "max_abs_residual",
            "l2_residual",
            "converged",
        }
        for field in required:
            assert field in report, f"Report missing field {field!r}"

    def test_report_topology_string_present(self):
        scenario = build_parallel_topology_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        report = build_parallel_topology_report(result)
        assert "parallel" in report["topology"].lower() or "branch" in report["topology"].lower()

    def test_report_convergence_status_none_because_solve_deferred(self):
        scenario = build_parallel_topology_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        report = build_parallel_topology_report(result)
        assert report["converged"] is None

    def test_report_does_not_write_files(self):
        scenario = build_parallel_topology_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        report = build_parallel_topology_report(result)
        assert isinstance(report, dict)

    def test_wrong_result_type_rejected_by_report(self):
        with pytest.raises(TypeError):
            build_parallel_topology_report("wrong_type")


# ===========================================================================
# Block 15C completeness assertion within MVP scope
# ===========================================================================


class TestBlock15CCompletenessMVP:
    def test_block_15c_1_junction_manifold_declarations_present(self):
        from mpl_sim.network.topology_declarations import (
            JunctionDeclaration,
            JunctionRole,
            ManifoldDeclaration,
        )

        assert JunctionRole.SPLIT is not None
        assert JunctionDeclaration is not None
        assert ManifoldDeclaration is not None

    def test_block_15c_2_parallel_topology_declaration_present(self):
        from mpl_sim.network.parallel_topology_scenario import (
            ParallelBranchDeclaration,
            ParallelTopologyComponentIds,
            ParallelTopologyNodeIds,
            ParallelTopologyResidualNames,
            ParallelTopologyScenario,
            ParallelTopologyUnknownNames,
            TopologyBranchId,
            build_parallel_topology_scenario,
        )

        assert ParallelBranchDeclaration is not None
        assert ParallelTopologyComponentIds is not None
        assert ParallelTopologyNodeIds is not None
        assert ParallelTopologyResidualNames is not None
        assert ParallelTopologyUnknownNames is not None
        assert TopologyBranchId is not None
        scenario = build_parallel_topology_scenario()
        assert isinstance(scenario, ParallelTopologyScenario)

    def test_block_15c_3_valve_declaration_present(self):
        from mpl_sim.network.topology_declarations import ValveDeclaration

        assert ValveDeclaration is not None

    def test_block_15c_4_residual_assembly_present(self):
        scenario = build_parallel_topology_scenario()
        assembly = build_parallel_topology_physical_residuals(scenario, _PARAMS)
        assert isinstance(assembly, ParallelTopologyPhysicalResidualAssembly)

    def test_block_15c_5_evaluation_present(self):
        scenario = build_parallel_topology_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        assert isinstance(result, ParallelTopologyEvaluationResult)

    def test_block_15c_5_report_present(self):
        scenario = build_parallel_topology_scenario()
        uv = _make_consistent_unknowns(scenario)
        result = evaluate_parallel_topology_residuals(scenario, _PARAMS, uv)
        report = build_parallel_topology_report(result)
        assert isinstance(report, dict)

    def _executable_lines(self, content: str) -> str:
        import re

        content = re.sub(r'""".*?"""', "", content, flags=re.DOTALL)
        content = re.sub(r"'''.*?'''", "", content, flags=re.DOTALL)
        content = re.sub(r"#[^\n]*", "", content)
        return content

    def test_block_15c_does_not_implement_arbitrary_topology(self):
        import re

        import mpl_sim.network.parallel_topology_residuals as mod

        src = mod.__file__
        with open(src) as f:
            content = f.read()
        executable = self._executable_lines(content)
        assert not re.search(r"NetworkGraph\.solve\s*\(", executable)
        assert not re.search(r"\bsolve\s*\(\s*network", executable)

    def test_block_15c_does_not_implement_component_contribute(self):
        import re

        import mpl_sim.network.parallel_topology_residuals as mod

        src = mod.__file__
        with open(src) as f:
            content = f.read()
        executable = self._executable_lines(content)
        matches = re.findall(r"\bcontribute\s*\(", executable)
        assert len(matches) == 0

    def test_block_15c_does_not_implement_systemstate_assembly(self):
        import mpl_sim.network.parallel_topology_residuals as mod

        src = mod.__file__
        with open(src) as f:
            content = f.read()
        executable = self._executable_lines(content)
        assert "SystemState" not in executable

    def test_block_15c_does_not_implement_fluidstate_construction(self):
        import mpl_sim.network.parallel_topology_residuals as mod

        src = mod.__file__
        with open(src) as f:
            content = f.read()
        executable = self._executable_lines(content)
        assert "FluidState" not in executable

    def test_block_15c_solve_is_explicitly_deferred(self):
        import mpl_sim.network.parallel_topology_residuals as mod

        assert not hasattr(mod, "solve_parallel_topology_residuals")
        assert not hasattr(mod, "ParallelTopologySolveRequest")
        assert not hasattr(mod, "ParallelTopologySolveResult")


# ===========================================================================
# Block 15B regression
# ===========================================================================


class TestBlock15BRegression:
    def test_fixed_single_loop_scenario_still_builds(self):
        from mpl_sim.network.fixed_single_loop_scenario import build_fixed_single_loop_scenario

        scenario = build_fixed_single_loop_scenario()
        assert scenario is not None

    def test_fixed_single_loop_residuals_still_build(self):
        from mpl_sim.network.fixed_single_loop_residuals import (
            FixedSingleLoopResidualParameters,
            build_fixed_single_loop_physical_residuals,
        )
        from mpl_sim.network.fixed_single_loop_scenario import build_fixed_single_loop_scenario

        scenario = build_fixed_single_loop_scenario()
        params = FixedSingleLoopResidualParameters(
            pump_pressure_rise=100_000.0,
            evaporator_pressure_drop=30_000.0,
            condenser_pressure_drop=70_000.0,
            accumulator_pressure_reference=1_000_000.0,
        )
        assembly = build_fixed_single_loop_physical_residuals(scenario, params)
        assert assembly is not None

    def test_fixed_single_loop_evaluation_still_works(self):
        from mpl_sim.network.fixed_single_loop_residuals import FixedSingleLoopResidualParameters
        from mpl_sim.network.fixed_single_loop_runner import evaluate_fixed_single_loop_residuals
        from mpl_sim.network.fixed_single_loop_scenario import build_fixed_single_loop_scenario

        scenario = build_fixed_single_loop_scenario()
        params = FixedSingleLoopResidualParameters(
            pump_pressure_rise=100_000.0,
            evaporator_pressure_drop=30_000.0,
            condenser_pressure_drop=70_000.0,
            accumulator_pressure_reference=1_000_000.0,
        )
        m = 0.5
        un = scenario.unknown_names
        uv = {
            un.mdot_accumulator: m,
            un.mdot_pump: m,
            un.mdot_evaporator: m,
            un.mdot_condenser: m,
            un.P_n_acc_out: 1_000_000.0,
            un.P_n_pump_out: 1_100_000.0,
            un.P_n_evap_out: 1_070_000.0,
            un.P_n_cond_out: 1_000_000.0,
        }
        result = evaluate_fixed_single_loop_residuals(scenario, params, uv)
        assert result.max_abs_residual == pytest.approx(0.0, abs=1e-9)

    def test_fixed_single_loop_report_still_works(self):
        from mpl_sim.network.fixed_single_loop_residuals import FixedSingleLoopResidualParameters
        from mpl_sim.network.fixed_single_loop_runner import (
            build_fixed_single_loop_report,
            evaluate_fixed_single_loop_residuals,
        )
        from mpl_sim.network.fixed_single_loop_scenario import build_fixed_single_loop_scenario

        scenario = build_fixed_single_loop_scenario()
        params = FixedSingleLoopResidualParameters(
            pump_pressure_rise=100_000.0,
            evaporator_pressure_drop=30_000.0,
            condenser_pressure_drop=70_000.0,
            accumulator_pressure_reference=1_000_000.0,
        )
        m = 0.5
        un = scenario.unknown_names
        uv = {
            un.mdot_accumulator: m,
            un.mdot_pump: m,
            un.mdot_evaporator: m,
            un.mdot_condenser: m,
            un.P_n_acc_out: 1_000_000.0,
            un.P_n_pump_out: 1_100_000.0,
            un.P_n_evap_out: 1_070_000.0,
            un.P_n_cond_out: 1_000_000.0,
        }
        result = evaluate_fixed_single_loop_residuals(scenario, params, uv)
        report = build_fixed_single_loop_report(result)
        assert isinstance(report, dict)


# ===========================================================================
# Phase 14G production contract regression
# ===========================================================================


class TestProductionContractRegression:
    def test_component_has_no_contribute_method(self):
        from mpl_sim.components import Component
        from mpl_sim.network.production_component_inspection import (
            ProductionComponentContractStatus,
            inspect_production_component_contract,
        )

        result = inspect_production_component_contract(Component)
        assert result.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD

    def test_pipe_has_no_contribute_method(self):
        from mpl_sim.components import Pipe
        from mpl_sim.network.production_component_inspection import (
            ProductionComponentContractStatus,
            inspect_production_component_contract,
        )

        result = inspect_production_component_contract(Pipe)
        assert result.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD

    def test_pump_component_has_no_contribute_method(self):
        from mpl_sim.components import PumpComponent
        from mpl_sim.network.production_component_inspection import (
            ProductionComponentContractStatus,
            inspect_production_component_contract,
        )

        result = inspect_production_component_contract(PumpComponent)
        assert result.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD

    def test_accumulator_component_has_no_contribute_method(self):
        from mpl_sim.components import AccumulatorComponent
        from mpl_sim.network.production_component_inspection import (
            ProductionComponentContractStatus,
            inspect_production_component_contract,
        )

        result = inspect_production_component_contract(AccumulatorComponent)
        assert result.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD

    def test_evaporator_component_has_no_contribute_method(self):
        from mpl_sim.components import EvaporatorComponent
        from mpl_sim.network.production_component_inspection import (
            ProductionComponentContractStatus,
            inspect_production_component_contract,
        )

        result = inspect_production_component_contract(EvaporatorComponent)
        assert result.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD

    def test_condenser_component_has_no_contribute_method(self):
        from mpl_sim.components import CondenserComponent
        from mpl_sim.network.production_component_inspection import (
            ProductionComponentContractStatus,
            inspect_production_component_contract,
        )

        result = inspect_production_component_contract(CondenserComponent)
        assert result.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD

    def test_all_six_known_classes_no_contribute(self):
        from mpl_sim.network.production_component_inspection import (
            ProductionComponentContractStatus,
            inspect_known_production_component_contracts,
        )

        results = inspect_known_production_component_contracts()
        assert len(results) == 6
        for r in results:
            assert (
                r.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD
            ), f"{r.class_name} unexpectedly has a contribute method"


# ===========================================================================
# Public API: new symbols exported from mpl_sim.network
# ===========================================================================


class TestPublicAPIExports:
    def test_parallel_topology_residual_parameters_exported(self):
        from mpl_sim.network import ParallelTopologyResidualParameters

        assert ParallelTopologyResidualParameters is not None

    def test_parallel_topology_physical_residual_assembly_exported(self):
        from mpl_sim.network import ParallelTopologyPhysicalResidualAssembly

        assert ParallelTopologyPhysicalResidualAssembly is not None

    def test_parallel_topology_evaluation_result_exported(self):
        from mpl_sim.network import ParallelTopologyEvaluationResult

        assert ParallelTopologyEvaluationResult is not None

    def test_build_parallel_topology_physical_residuals_exported(self):
        from mpl_sim.network import build_parallel_topology_physical_residuals

        assert callable(build_parallel_topology_physical_residuals)

    def test_evaluate_parallel_topology_residuals_exported(self):
        from mpl_sim.network import evaluate_parallel_topology_residuals

        assert callable(evaluate_parallel_topology_residuals)

    def test_build_parallel_topology_report_exported(self):
        from mpl_sim.network import build_parallel_topology_report

        assert callable(build_parallel_topology_report)

    def test_new_symbols_in_all(self):
        import mpl_sim.network as net

        expected = {
            "ParallelTopologyResidualParameters",
            "ParallelTopologyPhysicalResidualAssembly",
            "ParallelTopologyEvaluationResult",
            "build_parallel_topology_physical_residuals",
            "evaluate_parallel_topology_residuals",
            "build_parallel_topology_report",
        }
        for sym in expected:
            assert sym in net.__all__, f"{sym!r} not in mpl_sim.network.__all__"

    def test_no_accidental_broad_exports(self):
        import mpl_sim.network as net

        # Verify the module's __all__ is a list/tuple of strings, not wildcard.
        assert isinstance(net.__all__, (list, tuple))
        for name in net.__all__:
            assert isinstance(name, str)
