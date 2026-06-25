"""Fixed-equivalence tests for Block 15E-A.

Proves that configurable scenario declarations can reproduce the same
structural shape (node/component counts, unknown/residual names, graph
connectivity) as the existing fixed 15B single-loop and 15C two-branch
parallel scenarios.

These tests do NOT:
- Evaluate physical residuals.
- Infer or apply closures.
- Instantiate production components.
- Call CoolProp, PropertyBackend, or correlations.
- Assemble SystemState or FluidState.
- Add generic solve(network) or NetworkGraph.solve().

The configurable builder uses the same component/node IDs and ordering
as the fixed builders when given matching parameters, so the generated
unknown/residual names are identical.
"""

from __future__ import annotations

from mpl_sim.network.configurable_scenarios import (
    ConfigurableScenarioBuildResult,
    ConfigurableScenarioSpec,
    ScenarioBranchSpec,
    ScenarioComponentRole,
    ScenarioComponentSpec,
    ScenarioConnectionSpec,
    ScenarioNodeSpec,
    build_configurable_scenario,
    build_configurable_scenario_report,
)
from mpl_sim.network.fixed_single_loop_scenario import build_fixed_single_loop_scenario
from mpl_sim.network.parallel_topology_scenario import build_parallel_topology_scenario


def _graph_edges(graph: object) -> tuple[tuple[str, str, str], ...]:
    """Return ordered (component ID, inlet node ID, outlet node ID) edges."""
    return tuple(
        (
            instance.instance_id.value,
            instance.inlet_node.value,
            instance.outlet_node.value,
        )
        for instance in graph.instances()
    )


# ---------------------------------------------------------------------------
# Helpers: build configurable specs with same default IDs as fixed builders
# ---------------------------------------------------------------------------


def _configurable_single_loop() -> ConfigurableScenarioBuildResult:
    """Configurable single-loop with default IDs matching build_fixed_single_loop_scenario."""
    spec = ConfigurableScenarioSpec(
        scenario_id="configurable_single_loop",
        components=(
            ScenarioComponentSpec("accumulator", ScenarioComponentRole.ACCUMULATOR),
            ScenarioComponentSpec("pump", ScenarioComponentRole.PUMP),
            ScenarioComponentSpec("evaporator", ScenarioComponentRole.EVAPORATOR),
            ScenarioComponentSpec("condenser", ScenarioComponentRole.CONDENSER),
        ),
        nodes=(
            ScenarioNodeSpec("n_acc_out"),
            ScenarioNodeSpec("n_pump_out"),
            ScenarioNodeSpec("n_evap_out"),
            ScenarioNodeSpec("n_cond_out"),
        ),
        connections=(
            ScenarioConnectionSpec("accumulator", "n_cond_out", "n_acc_out"),
            ScenarioConnectionSpec("pump", "n_acc_out", "n_pump_out"),
            ScenarioConnectionSpec("evaporator", "n_pump_out", "n_evap_out"),
            ScenarioConnectionSpec("condenser", "n_evap_out", "n_cond_out"),
        ),
    )
    return build_configurable_scenario(spec)


def _configurable_two_branch() -> ConfigurableScenarioBuildResult:
    """Configurable two-branch with default IDs matching build_parallel_topology_scenario."""
    spec = ConfigurableScenarioSpec(
        scenario_id="configurable_two_branch",
        components=(
            ScenarioComponentSpec("accumulator", ScenarioComponentRole.ACCUMULATOR),
            ScenarioComponentSpec("pump", ScenarioComponentRole.PUMP),
            ScenarioComponentSpec("branch_a", ScenarioComponentRole.GENERIC),
            ScenarioComponentSpec("branch_b", ScenarioComponentRole.GENERIC),
            ScenarioComponentSpec("merge_a", ScenarioComponentRole.GENERIC),
            ScenarioComponentSpec("merge_b", ScenarioComponentRole.GENERIC),
            ScenarioComponentSpec("condenser", ScenarioComponentRole.CONDENSER),
        ),
        nodes=(
            ScenarioNodeSpec("n_acc_out"),
            ScenarioNodeSpec("n_pump_out"),
            ScenarioNodeSpec("n_a_out"),
            ScenarioNodeSpec("n_b_out"),
            ScenarioNodeSpec("n_merge_out"),
            ScenarioNodeSpec("n_cond_out"),
        ),
        connections=(
            ScenarioConnectionSpec("accumulator", "n_cond_out", "n_acc_out"),
            ScenarioConnectionSpec("pump", "n_acc_out", "n_pump_out"),
            ScenarioConnectionSpec("branch_a", "n_pump_out", "n_a_out"),
            ScenarioConnectionSpec("branch_b", "n_pump_out", "n_b_out"),
            ScenarioConnectionSpec("merge_a", "n_a_out", "n_merge_out"),
            ScenarioConnectionSpec("merge_b", "n_b_out", "n_merge_out"),
            ScenarioConnectionSpec("condenser", "n_merge_out", "n_cond_out"),
        ),
        branches=(
            ScenarioBranchSpec("a", "n_pump_out", "n_merge_out", ("branch_a", "merge_a")),
            ScenarioBranchSpec("b", "n_pump_out", "n_merge_out", ("branch_b", "merge_b")),
        ),
    )
    return build_configurable_scenario(spec)


# ===========================================================================
# Single-loop structural equivalence
# ===========================================================================


class TestSingleLoopEquivalence:
    """Configurable single-loop structurally matches fixed 15B loop."""

    def test_component_count_matches(self) -> None:
        cfg = _configurable_single_loop()
        fixed = build_fixed_single_loop_scenario()
        assert len(list(cfg.graph.instance_ids())) == len(list(fixed.graph.instance_ids()))

    def test_node_count_matches(self) -> None:
        cfg = _configurable_single_loop()
        fixed = build_fixed_single_loop_scenario()
        assert len(list(cfg.graph.node_ids())) == len(list(fixed.graph.node_ids()))

    def test_unknown_count_matches(self) -> None:
        cfg = _configurable_single_loop()
        fixed = build_fixed_single_loop_scenario()
        assert cfg.assembly.unknowns.count() == fixed.assembly.unknowns.count()

    def test_residual_count_matches(self) -> None:
        cfg = _configurable_single_loop()
        fixed = build_fixed_single_loop_scenario()
        assert cfg.assembly.residuals.count() == fixed.assembly.residuals.count()

    def test_unknown_names_match(self) -> None:
        cfg = _configurable_single_loop()
        fixed = build_fixed_single_loop_scenario()
        assert cfg.unknown_names == fixed.assembly.unknowns.names()

    def test_residual_names_match(self) -> None:
        cfg = _configurable_single_loop()
        fixed = build_fixed_single_loop_scenario()
        assert cfg.residual_names == fixed.assembly.residuals.names()

    def test_component_ids_match(self) -> None:
        cfg = _configurable_single_loop()
        fixed = build_fixed_single_loop_scenario()
        assert cfg.component_ids == fixed.graph.instance_ids()

    def test_node_ids_match(self) -> None:
        cfg = _configurable_single_loop()
        fixed = build_fixed_single_loop_scenario()
        assert cfg.node_ids == fixed.graph.node_ids()

    def test_graph_connectivity_matches(self) -> None:
        cfg = _configurable_single_loop()
        fixed = build_fixed_single_loop_scenario()
        assert _graph_edges(cfg.graph) == _graph_edges(fixed.graph)

    def test_configurable_unknown_names_contain_mdot_accumulator(self) -> None:
        cfg = _configurable_single_loop()
        assert "mdot:accumulator" in cfg.unknown_names

    def test_configurable_unknown_names_contain_pressure_nodes(self) -> None:
        cfg = _configurable_single_loop()
        for nid in ("n_acc_out", "n_pump_out", "n_evap_out", "n_cond_out"):
            assert f"P:{nid}" in cfg.unknown_names

    def test_configurable_residual_names_contain_mass_balance(self) -> None:
        cfg = _configurable_single_loop()
        for nid in ("n_acc_out", "n_pump_out", "n_evap_out", "n_cond_out"):
            assert f"mass_balance:{nid}" in cfg.residual_names

    def test_configurable_residual_names_contain_pressure_drop(self) -> None:
        cfg = _configurable_single_loop()
        for cid in ("accumulator", "pump", "evaporator", "condenser"):
            assert f"pressure_drop:{cid}" in cfg.residual_names

    def test_no_branches_for_single_loop(self) -> None:
        cfg = _configurable_single_loop()
        assert cfg.branch_ids == ()

    def test_fixed_single_loop_scenario_still_builds(self) -> None:
        fixed = build_fixed_single_loop_scenario()
        assert fixed.assembly.unknowns.count() == 8

    def test_no_physical_residuals_evaluated(self) -> None:
        cfg = _configurable_single_loop()
        assert not hasattr(cfg, "residual_values")
        assert not hasattr(cfg, "evaluated_residuals")

    def test_no_closures_inferred(self) -> None:
        cfg = _configurable_single_loop()
        assert not hasattr(cfg, "hydraulic_closures")
        assert not hasattr(cfg, "thermal_closures")

    def test_no_production_component_objects(self) -> None:
        from mpl_sim.network.configurable_scenarios import ConfigurableScenarioBuildResult

        cfg = _configurable_single_loop()
        assert isinstance(cfg, ConfigurableScenarioBuildResult)
        assert not hasattr(cfg, "component_objects")

    def test_configurable_and_fixed_binding_unknown_names_match(self) -> None:
        cfg = _configurable_single_loop()
        fixed = build_fixed_single_loop_scenario()
        cfg_unknown_set = set(cfg.binding_context.state_map.unknown_to_component) | set(
            cfg.binding_context.state_map.unknown_to_node
        )
        fixed_unknown_set = set(fixed.binding_context.state_map.unknown_to_component) | set(
            fixed.binding_context.state_map.unknown_to_node
        )
        assert cfg_unknown_set == fixed_unknown_set

    def test_configurable_and_fixed_binding_residual_names_match(self) -> None:
        cfg = _configurable_single_loop()
        fixed = build_fixed_single_loop_scenario()
        cfg_residual_set = set(cfg.binding_context.state_map.residual_to_node) | set(
            cfg.binding_context.state_map.residual_to_component
        )
        fixed_residual_set = set(fixed.binding_context.state_map.residual_to_node) | set(
            fixed.binding_context.state_map.residual_to_component
        )
        assert cfg_residual_set == fixed_residual_set


# ===========================================================================
# Two-branch structural equivalence
# ===========================================================================


class TestTwoBranchEquivalence:
    """Configurable two-branch structurally matches fixed 15C parallel topology."""

    def test_component_count_matches(self) -> None:
        cfg = _configurable_two_branch()
        fixed = build_parallel_topology_scenario()
        assert len(list(cfg.graph.instance_ids())) == len(list(fixed.graph.instance_ids()))

    def test_node_count_matches(self) -> None:
        cfg = _configurable_two_branch()
        fixed = build_parallel_topology_scenario()
        assert len(list(cfg.graph.node_ids())) == len(list(fixed.graph.node_ids()))

    def test_unknown_count_matches(self) -> None:
        cfg = _configurable_two_branch()
        fixed = build_parallel_topology_scenario()
        assert cfg.assembly.unknowns.count() == fixed.assembly.unknowns.count()

    def test_residual_count_matches(self) -> None:
        cfg = _configurable_two_branch()
        fixed = build_parallel_topology_scenario()
        assert cfg.assembly.residuals.count() == fixed.assembly.residuals.count()

    def test_unknown_names_match(self) -> None:
        cfg = _configurable_two_branch()
        fixed = build_parallel_topology_scenario()
        assert cfg.unknown_names == fixed.assembly.unknowns.names()

    def test_residual_names_match(self) -> None:
        cfg = _configurable_two_branch()
        fixed = build_parallel_topology_scenario()
        assert cfg.residual_names == fixed.assembly.residuals.names()

    def test_component_ids_match(self) -> None:
        cfg = _configurable_two_branch()
        fixed = build_parallel_topology_scenario()
        assert cfg.component_ids == fixed.graph.instance_ids()

    def test_node_ids_match(self) -> None:
        cfg = _configurable_two_branch()
        fixed = build_parallel_topology_scenario()
        assert cfg.node_ids == fixed.graph.node_ids()

    def test_graph_connectivity_matches(self) -> None:
        cfg = _configurable_two_branch()
        fixed = build_parallel_topology_scenario()
        assert _graph_edges(cfg.graph) == _graph_edges(fixed.graph)

    def test_branch_ids_declared(self) -> None:
        cfg = _configurable_two_branch()
        assert "a" in cfg.branch_ids
        assert "b" in cfg.branch_ids

    def test_unknown_names_cover_all_7_components(self) -> None:
        cfg = _configurable_two_branch()
        for cid in (
            "accumulator",
            "pump",
            "branch_a",
            "branch_b",
            "merge_a",
            "merge_b",
            "condenser",
        ):
            assert f"mdot:{cid}" in cfg.unknown_names

    def test_unknown_names_cover_all_6_nodes(self) -> None:
        cfg = _configurable_two_branch()
        for nid in ("n_acc_out", "n_pump_out", "n_a_out", "n_b_out", "n_merge_out", "n_cond_out"):
            assert f"P:{nid}" in cfg.unknown_names

    def test_residual_names_cover_all_6_nodes(self) -> None:
        cfg = _configurable_two_branch()
        for nid in ("n_acc_out", "n_pump_out", "n_a_out", "n_b_out", "n_merge_out", "n_cond_out"):
            assert f"mass_balance:{nid}" in cfg.residual_names

    def test_residual_names_cover_all_7_components(self) -> None:
        cfg = _configurable_two_branch()
        for cid in (
            "accumulator",
            "pump",
            "branch_a",
            "branch_b",
            "merge_a",
            "merge_b",
            "condenser",
        ):
            assert f"pressure_drop:{cid}" in cfg.residual_names

    def test_fixed_parallel_topology_still_builds(self) -> None:
        fixed = build_parallel_topology_scenario()
        assert fixed.assembly.unknowns.count() == 13

    def test_no_closures_inferred_from_role(self) -> None:
        cfg = _configurable_two_branch()
        assert not hasattr(cfg, "hydraulic_closures")

    def test_configurable_and_fixed_binding_unknown_names_match(self) -> None:
        cfg = _configurable_two_branch()
        fixed = build_parallel_topology_scenario()
        cfg_set = set(cfg.binding_context.state_map.unknown_to_component) | set(
            cfg.binding_context.state_map.unknown_to_node
        )
        fixed_set = set(fixed.binding_context.state_map.unknown_to_component) | set(
            fixed.binding_context.state_map.unknown_to_node
        )
        assert cfg_set == fixed_set

    def test_configurable_and_fixed_binding_residual_names_match(self) -> None:
        cfg = _configurable_two_branch()
        fixed = build_parallel_topology_scenario()
        cfg_set = set(cfg.binding_context.state_map.residual_to_node) | set(
            cfg.binding_context.state_map.residual_to_component
        )
        fixed_set = set(fixed.binding_context.state_map.residual_to_node) | set(
            fixed.binding_context.state_map.residual_to_component
        )
        assert cfg_set == fixed_set


# ===========================================================================
# Closure coexistence test
# ===========================================================================


class TestClosureCoexistence:
    """Configurable scenario report can coexist with closure report (15D-C)."""

    def test_configurable_report_coexists_with_combined_closure_residuals(self) -> None:
        from mpl_sim.network.closure_integration import (
            build_combined_closure_residuals,
        )
        from mpl_sim.network.hydraulic_closures import (
            ImposedMassFlowClosure,
            build_hydraulic_closure_residuals,
        )
        from mpl_sim.network.thermal_closures import (
            FixedHeatRateClosure,
            build_thermal_closure_residuals,
        )

        cfg_result = _configurable_single_loop()
        cfg_report = build_configurable_scenario_report(cfg_result)
        assert cfg_report["status"] == "declaration_only"
        assert cfg_report["no_solve"] is True

        # ImposedMassFlowClosure(unknown_name, imposed_value, residual_name)
        h_closure = ImposedMassFlowClosure("mdot_total", 1.0, "r_mdot_imposed")
        h_set = build_hydraulic_closure_residuals([h_closure])

        t_closure = FixedHeatRateClosure("q_evap", 5000.0, "r_q_evap")
        t_set = build_thermal_closure_residuals([t_closure])

        combined_set = build_combined_closure_residuals(hydraulic=h_set, thermal=t_set)
        # Verify we can build the combined set alongside a configurable scenario report.
        assert combined_set.hydraulic_count == 1
        assert combined_set.thermal_count == 1
        assert cfg_report["no_solve"] is True

    def test_configurable_limitations_document_deferred_closures(self) -> None:
        cfg = _configurable_single_loop()
        combined = " ".join(cfg.limitations).lower()
        assert "closure" in combined

    def test_configurable_report_closure_domains_available_later(self) -> None:
        cfg = _configurable_single_loop()
        report = build_configurable_scenario_report(cfg)
        domains = report.get("closure_domains_available_later", [])
        assert isinstance(domains, list)
        assert len(domains) >= 1  # type: ignore[arg-type]


# ===========================================================================
# Regression: prior block scenarios still build
# ===========================================================================


class TestRegressionPriorScenarios:
    def test_fixed_single_loop_scenario_builds(self) -> None:
        fixed = build_fixed_single_loop_scenario()
        assert fixed.assembly.unknowns.count() == 8
        assert fixed.assembly.residuals.count() == 8

    def test_fixed_parallel_topology_scenario_builds(self) -> None:
        fixed = build_parallel_topology_scenario()
        assert fixed.assembly.unknowns.count() == 13
        assert fixed.assembly.residuals.count() == 13

    def test_both_fixed_and_configurable_build_independently(self) -> None:
        fixed_loop = build_fixed_single_loop_scenario()
        fixed_parallel = build_parallel_topology_scenario()
        cfg_loop = _configurable_single_loop()
        cfg_parallel = _configurable_two_branch()

        assert fixed_loop.assembly.unknowns.count() == 8
        assert fixed_parallel.assembly.unknowns.count() == 13
        assert cfg_loop.assembly.unknowns.count() == 8
        assert cfg_parallel.assembly.unknowns.count() == 13

    def test_configurable_and_fixed_are_independent_objects(self) -> None:
        cfg = _configurable_single_loop()
        fixed = build_fixed_single_loop_scenario()
        assert cfg.graph is not fixed.graph
        assert cfg.assembly is not fixed.assembly

    def test_production_component_inspection_still_no_contribute(self) -> None:
        from mpl_sim.network.production_component_inspection import (
            ProductionComponentContractStatus,
            inspect_known_production_component_contracts,
        )

        # Returns tuple[ProductionComponentInspectionResult, ...], not a dict.
        results = inspect_known_production_component_contracts()
        assert isinstance(results, tuple)
        assert len(results) >= 1
        for result in results:
            assert (
                result.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD
            ), f"{result.class_name} unexpectedly has a contribute method"

    def test_15dc_closure_integration_still_works(self) -> None:
        from mpl_sim.network.closure_integration import (
            build_combined_closure_residuals,
        )
        from mpl_sim.network.hydraulic_closures import (
            ImposedMassFlowClosure,
            build_hydraulic_closure_residuals,
        )

        # ImposedMassFlowClosure(unknown_name, imposed_value, residual_name)
        h = ImposedMassFlowClosure("mdot", 1.0, "r_mdot")
        h_set = build_hydraulic_closure_residuals([h])
        combined = build_combined_closure_residuals(hydraulic=h_set)
        assert combined.hydraulic_count == 1

    def test_boundary_no_systemstate_or_fluidstate_imported(self) -> None:
        import re

        import mpl_sim.network.configurable_scenarios as mod

        src = getattr(mod, "__file__", "")
        if src:
            with open(src) as f:
                text = f.read()
            import_lines = [ln for ln in text.splitlines() if re.match(r"^\s*(import|from)\s+", ln)]
            for ln in import_lines:
                assert "SystemState" not in ln
                assert "FluidState" not in ln

    def test_boundary_no_solve_method_on_any_new_type(self) -> None:
        from mpl_sim.network import configurable_scenarios as mod

        for name in dir(mod):
            obj = getattr(mod, name)
            if isinstance(obj, type):
                assert not hasattr(obj, "solve"), f"{name} must not have a solve() method"
