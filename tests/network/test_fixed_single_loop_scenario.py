"""Block 15B.1 — Fixed Single-Loop Scenario Declaration MVP tests.

These tests verify the declaration-only fixed single-loop scenario module.
No production component physics are executed.  No SystemState is assembled.
No FluidState is created.  No CoolProp, PropertyBackend, correlations, or
HX models are called.

Coverage items:

Scenario construction:
 1. default fixed single-loop scenario builds successfully
 2. returned object is FixedSingleLoopScenario
 3. scenario contains a NetworkGraph
 4. scenario contains a NetworkResidualAssembly
 5. scenario contains a NetworkBindingContext
 6. component IDs are explicit and deterministic
 7. node IDs are explicit and deterministic
 8. unknown names are explicit and deterministic
 9. residual names are explicit and deterministic
10. residual ordering is deterministic

Immutability / defensive behavior:
11. scenario object is frozen
12. component ID container is frozen
13. node ID container is frozen
14. unknown name container is frozen
15. residual name container is frozen
16. metadata is defensively copied
17. metadata proxy is read-only

Validation — duplicate rejection:
18. duplicate component IDs rejected by factory
19. duplicate node IDs rejected by factory
20. duplicate component IDs rejected by container
21. duplicate node IDs rejected by container
22. duplicate unknown names rejected by container
23. duplicate residual names rejected by container

Validation — empty / whitespace:
24. empty component ID rejected
25. whitespace component ID rejected
26. empty node ID rejected
27. whitespace node ID rejected
28. empty unknown name rejected in container
29. empty residual name rejected in container

Validation — wrong types:
30. wrong type for component ID rejected by factory
31. wrong type for node ID rejected by factory
32. wrong type for graph in scenario rejected
33. wrong type for assembly in scenario rejected
34. wrong type for metadata rejected

Compatibility with existing stack:
35. scenario compatible with NetworkUnknownValues
36. exact unknown coverage enforced by build_readonly_unknown_view
37. build_readonly_unknown_view succeeds with correct unknown values
38. component-scoped view works via state map
39. node-scoped view works via state map
40. scenario binding context is compatible with toy producers (no physics)

Graph / topology:
41. graph has exactly 4 nodes
42. graph has exactly 4 component instances
43. graph validates as closed single loop
44. default component types are symbolic labels only
45. summary returns dict without physical values

Boundary tests (AST / import-level):
46. fixed_single_loop_scenario module: no CoolProp import
47. fixed_single_loop_scenario module: no PropertyBackend import
48. fixed_single_loop_scenario module: no CorrelationRegistry import
49. fixed_single_loop_scenario module: no hx_models import
50. fixed_single_loop_scenario module: no SystemState import
51. fixed_single_loop_scenario module: no FluidState import
52. fixed_single_loop_scenario module: no mpl_sim.components import
53. fixed_single_loop_scenario module: no mpl_sim.properties import
54. fixed_single_loop_scenario module: no contribute attribute-call nodes
55. fixed_single_loop_scenario module: no solve(network) pattern
56. this test file: no CoolProp import
57. this test file: no PropertyBackend import
58. this test file: no contribute attribute-call nodes

Production contract regression:
59. Component reports NO_CONTRIBUTE_METHOD
60. Pipe reports NO_CONTRIBUTE_METHOD
61. PumpComponent reports NO_CONTRIBUTE_METHOD
62. AccumulatorComponent reports NO_CONTRIBUTE_METHOD
63. EvaporatorComponent reports NO_CONTRIBUTE_METHOD
64. CondenserComponent reports NO_CONTRIBUTE_METHOD

Public API:
65. new symbols exported from mpl_sim.network
66. new symbols in __all__ list
67. no private symbols leaked in __all__
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from mpl_sim.network import (
    ComponentInstanceId,
    ContributionRecord,
    ContributionRecordSet,
    GraphNodeId,
    NetworkBindingContext,
    NetworkGraph,
    NetworkResidualAssembly,
    NetworkUnknownValues,
    ProductionComponentContractStatus,
    ProductionLikeComponentBinding,
    ProductionLikeComponentSet,
    build_readonly_unknown_view,
    execute_production_like_contributions,
    inspect_known_production_component_contracts,
)
from mpl_sim.network.fixed_single_loop_scenario import (
    FixedSingleLoopComponentIds,
    FixedSingleLoopNodeIds,
    FixedSingleLoopResidualNames,
    FixedSingleLoopScenario,
    FixedSingleLoopUnknownNames,
    build_fixed_single_loop_scenario,
)

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_SCENARIO_MODULE = (
    pathlib.Path(__file__).parent.parent.parent
    / "src"
    / "mpl_sim"
    / "network"
    / "fixed_single_loop_scenario.py"
)
_THIS_FILE = pathlib.Path(__file__)


def _read_source(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse_ast(path: pathlib.Path) -> ast.Module:
    return ast.parse(_read_source(path))


def _has_import(tree: ast.Module, name: str) -> bool:
    """Return True if any import statement references the given name."""
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
    """Return True if any ast.Call invokes an attribute named 'contribute'."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "contribute":
                return True
    return False


# ---------------------------------------------------------------------------
# Group 1: Scenario construction
# ---------------------------------------------------------------------------


def test_default_scenario_builds_successfully():
    scenario = build_fixed_single_loop_scenario()
    assert scenario is not None


def test_returns_fixed_single_loop_scenario_type():
    scenario = build_fixed_single_loop_scenario()
    assert isinstance(scenario, FixedSingleLoopScenario)


def test_scenario_contains_network_graph():
    scenario = build_fixed_single_loop_scenario()
    assert isinstance(scenario.graph, NetworkGraph)


def test_scenario_contains_network_residual_assembly():
    scenario = build_fixed_single_loop_scenario()
    assert isinstance(scenario.assembly, NetworkResidualAssembly)


def test_scenario_contains_network_binding_context():
    scenario = build_fixed_single_loop_scenario()
    assert isinstance(scenario.binding_context, NetworkBindingContext)


def test_component_ids_are_explicit_and_deterministic():
    s1 = build_fixed_single_loop_scenario()
    s2 = build_fixed_single_loop_scenario()
    assert s1.component_ids.accumulator == s2.component_ids.accumulator
    assert s1.component_ids.pump == s2.component_ids.pump
    assert s1.component_ids.evaporator == s2.component_ids.evaporator
    assert s1.component_ids.condenser == s2.component_ids.condenser


def test_node_ids_are_explicit_and_deterministic():
    s1 = build_fixed_single_loop_scenario()
    s2 = build_fixed_single_loop_scenario()
    assert s1.node_ids.n_acc_out == s2.node_ids.n_acc_out
    assert s1.node_ids.n_pump_out == s2.node_ids.n_pump_out
    assert s1.node_ids.n_evap_out == s2.node_ids.n_evap_out
    assert s1.node_ids.n_cond_out == s2.node_ids.n_cond_out


def test_unknown_names_are_explicit_and_deterministic():
    s1 = build_fixed_single_loop_scenario()
    s2 = build_fixed_single_loop_scenario()
    assert s1.unknown_names.all_names() == s2.unknown_names.all_names()


def test_residual_names_are_explicit_and_deterministic():
    s1 = build_fixed_single_loop_scenario()
    s2 = build_fixed_single_loop_scenario()
    assert s1.residual_names.all_names() == s2.residual_names.all_names()


def test_residual_ordering_is_deterministic():
    scenario = build_fixed_single_loop_scenario()
    names = scenario.residual_names.all_names()
    assembly_names = scenario.assembly.residuals.names()
    assert names == assembly_names


# ---------------------------------------------------------------------------
# Group 2: Default values and topology
# ---------------------------------------------------------------------------


def test_default_component_ids_match_labels():
    scenario = build_fixed_single_loop_scenario()
    assert scenario.component_ids.accumulator.value == "accumulator"
    assert scenario.component_ids.pump.value == "pump"
    assert scenario.component_ids.evaporator.value == "evaporator"
    assert scenario.component_ids.condenser.value == "condenser"


def test_default_node_ids_match_labels():
    scenario = build_fixed_single_loop_scenario()
    assert scenario.node_ids.n_acc_out.value == "n_acc_out"
    assert scenario.node_ids.n_pump_out.value == "n_pump_out"
    assert scenario.node_ids.n_evap_out.value == "n_evap_out"
    assert scenario.node_ids.n_cond_out.value == "n_cond_out"


def test_default_unknown_names_match_expected():
    scenario = build_fixed_single_loop_scenario()
    un = scenario.unknown_names
    assert un.mdot_accumulator == "mdot:accumulator"
    assert un.mdot_pump == "mdot:pump"
    assert un.mdot_evaporator == "mdot:evaporator"
    assert un.mdot_condenser == "mdot:condenser"
    assert un.P_n_acc_out == "P:n_acc_out"
    assert un.P_n_pump_out == "P:n_pump_out"
    assert un.P_n_evap_out == "P:n_evap_out"
    assert un.P_n_cond_out == "P:n_cond_out"


def test_default_residual_names_match_expected():
    scenario = build_fixed_single_loop_scenario()
    rn = scenario.residual_names
    assert rn.mass_balance_n_acc_out == "mass_balance:n_acc_out"
    assert rn.mass_balance_n_pump_out == "mass_balance:n_pump_out"
    assert rn.mass_balance_n_evap_out == "mass_balance:n_evap_out"
    assert rn.mass_balance_n_cond_out == "mass_balance:n_cond_out"
    assert rn.pressure_drop_accumulator == "pressure_drop:accumulator"
    assert rn.pressure_drop_pump == "pressure_drop:pump"
    assert rn.pressure_drop_evaporator == "pressure_drop:evaporator"
    assert rn.pressure_drop_condenser == "pressure_drop:condenser"


def test_custom_ids_propagate_correctly():
    scenario = build_fixed_single_loop_scenario(
        accumulator_id="res",
        pump_id="ccp",
        evaporator_id="evap_hx",
        condenser_id="cond_hx",
        n_acc_out_id="na",
        n_pump_out_id="nb",
        n_evap_out_id="nc",
        n_cond_out_id="nd",
    )
    assert scenario.component_ids.accumulator.value == "res"
    assert scenario.unknown_names.mdot_pump == "mdot:ccp"
    assert scenario.residual_names.pressure_drop_evaporator == "pressure_drop:evap_hx"
    assert scenario.node_ids.n_cond_out.value == "nd"


# ---------------------------------------------------------------------------
# Group 3: Graph / topology
# ---------------------------------------------------------------------------


def test_graph_has_four_nodes():
    scenario = build_fixed_single_loop_scenario()
    assert len(scenario.graph.nodes()) == 4


def test_graph_has_four_component_instances():
    scenario = build_fixed_single_loop_scenario()
    assert len(scenario.graph.instances()) == 4


def test_graph_validates_as_closed_single_loop():
    scenario = build_fixed_single_loop_scenario()
    scenario.graph.validate_closed_single_loop()  # must not raise


def test_graph_node_ids_match_node_id_container():
    scenario = build_fixed_single_loop_scenario()
    graph_node_ids = {n.node_id.value for n in scenario.graph.nodes()}
    container_node_ids = {nid.value for nid in scenario.node_ids.all_ids()}
    assert graph_node_ids == container_node_ids


def test_graph_instance_ids_match_component_id_container():
    scenario = build_fixed_single_loop_scenario()
    graph_inst_ids = {inst.instance_id.value for inst in scenario.graph.instances()}
    container_ids = {cid.value for cid in scenario.component_ids.all_ids()}
    assert graph_inst_ids == container_ids


def test_component_types_are_symbolic_labels():
    scenario = build_fixed_single_loop_scenario()
    types = {inst.component_type for inst in scenario.graph.instances()}
    assert types == {"accumulator", "pump", "evaporator", "condenser"}


def test_assembly_has_eight_unknowns():
    scenario = build_fixed_single_loop_scenario()
    assert scenario.assembly.unknowns.count() == 8


def test_assembly_has_eight_residuals():
    scenario = build_fixed_single_loop_scenario()
    assert scenario.assembly.residuals.count() == 8


def test_summary_returns_dict_without_physical_values():
    scenario = build_fixed_single_loop_scenario()
    summary = scenario.summary()
    assert isinstance(summary, dict)
    assert "topology" in summary
    assert "component_ids" in summary
    assert "node_ids" in summary
    assert "unknown_count" in summary
    assert "residual_count" in summary
    assert summary["unknown_count"] == 8
    assert summary["residual_count"] == 8


# ---------------------------------------------------------------------------
# Group 4: Immutability / defensive behavior
# ---------------------------------------------------------------------------


def test_scenario_is_frozen():
    scenario = build_fixed_single_loop_scenario()
    with pytest.raises((AttributeError, TypeError)):
        scenario.graph = None  # type: ignore[misc]


def test_component_ids_container_is_frozen():
    scenario = build_fixed_single_loop_scenario()
    with pytest.raises((AttributeError, TypeError)):
        scenario.component_ids.pump = None  # type: ignore[misc]


def test_node_ids_container_is_frozen():
    scenario = build_fixed_single_loop_scenario()
    with pytest.raises((AttributeError, TypeError)):
        scenario.node_ids.n_acc_out = None  # type: ignore[misc]


def test_unknown_names_container_is_frozen():
    scenario = build_fixed_single_loop_scenario()
    with pytest.raises((AttributeError, TypeError)):
        scenario.unknown_names.mdot_pump = "x"  # type: ignore[misc]


def test_residual_names_container_is_frozen():
    scenario = build_fixed_single_loop_scenario()
    with pytest.raises((AttributeError, TypeError)):
        scenario.residual_names.pressure_drop_pump = "x"  # type: ignore[misc]


def test_metadata_is_defensively_copied():
    meta = {"key": "original"}
    scenario = build_fixed_single_loop_scenario(metadata=meta)
    meta["key"] = "mutated"
    assert scenario.metadata is not None
    assert scenario.metadata["key"] == "original"


def test_metadata_proxy_is_read_only():
    scenario = build_fixed_single_loop_scenario(metadata={"k": "v"})
    assert scenario.metadata is not None
    with pytest.raises(TypeError):
        scenario.metadata["new_key"] = "oops"  # type: ignore[index]


def test_no_metadata_by_default():
    scenario = build_fixed_single_loop_scenario()
    assert scenario.metadata is None


# ---------------------------------------------------------------------------
# Group 5: Validation — duplicate rejection
# ---------------------------------------------------------------------------


def test_duplicate_component_ids_rejected_by_factory():
    with pytest.raises(ValueError, match="distinct"):
        build_fixed_single_loop_scenario(pump_id="accumulator")


def test_two_duplicate_component_ids_rejected_by_factory():
    with pytest.raises(ValueError, match="distinct"):
        build_fixed_single_loop_scenario(evaporator_id="pump", condenser_id="pump")


def test_duplicate_node_ids_rejected_by_factory():
    with pytest.raises(ValueError, match="distinct"):
        build_fixed_single_loop_scenario(n_pump_out_id="n_acc_out")


def test_duplicate_component_ids_rejected_by_container():
    cid = ComponentInstanceId("x")
    with pytest.raises(ValueError, match="distinct"):
        FixedSingleLoopComponentIds(
            accumulator=cid,
            pump=cid,
            evaporator=ComponentInstanceId("evap"),
            condenser=ComponentInstanceId("cond"),
        )


def test_duplicate_node_ids_rejected_by_container():
    nid = GraphNodeId("n_x")
    with pytest.raises(ValueError, match="distinct"):
        FixedSingleLoopNodeIds(
            n_acc_out=nid,
            n_pump_out=nid,
            n_evap_out=GraphNodeId("n_evap_out"),
            n_cond_out=GraphNodeId("n_cond_out"),
        )


def test_duplicate_unknown_names_rejected_by_container():
    with pytest.raises(ValueError, match="distinct"):
        FixedSingleLoopUnknownNames(
            mdot_accumulator="mdot:x",
            mdot_pump="mdot:x",
            mdot_evaporator="mdot:evap",
            mdot_condenser="mdot:cond",
            P_n_acc_out="P:n_acc_out",
            P_n_pump_out="P:n_pump_out",
            P_n_evap_out="P:n_evap_out",
            P_n_cond_out="P:n_cond_out",
        )


def test_duplicate_residual_names_rejected_by_container():
    with pytest.raises(ValueError, match="distinct"):
        FixedSingleLoopResidualNames(
            mass_balance_n_acc_out="mass_balance:n_acc_out",
            mass_balance_n_pump_out="mass_balance:n_acc_out",
            mass_balance_n_evap_out="mass_balance:n_evap_out",
            mass_balance_n_cond_out="mass_balance:n_cond_out",
            pressure_drop_accumulator="pressure_drop:acc",
            pressure_drop_pump="pressure_drop:pump",
            pressure_drop_evaporator="pressure_drop:evap",
            pressure_drop_condenser="pressure_drop:cond",
        )


# ---------------------------------------------------------------------------
# Group 6: Validation — empty / whitespace
# ---------------------------------------------------------------------------


def test_empty_accumulator_id_rejected():
    with pytest.raises(ValueError):
        build_fixed_single_loop_scenario(accumulator_id="")


def test_whitespace_pump_id_rejected():
    with pytest.raises(ValueError):
        build_fixed_single_loop_scenario(pump_id="   ")


def test_empty_node_id_rejected():
    with pytest.raises(ValueError):
        build_fixed_single_loop_scenario(n_acc_out_id="")


def test_whitespace_node_id_rejected():
    with pytest.raises(ValueError):
        build_fixed_single_loop_scenario(n_pump_out_id="  ")


def test_empty_unknown_name_rejected_in_container():
    with pytest.raises(ValueError):
        FixedSingleLoopUnknownNames(
            mdot_accumulator="",
            mdot_pump="mdot:pump",
            mdot_evaporator="mdot:evap",
            mdot_condenser="mdot:cond",
            P_n_acc_out="P:a",
            P_n_pump_out="P:b",
            P_n_evap_out="P:c",
            P_n_cond_out="P:d",
        )


def test_empty_residual_name_rejected_in_container():
    with pytest.raises(ValueError):
        FixedSingleLoopResidualNames(
            mass_balance_n_acc_out="",
            mass_balance_n_pump_out="mass_balance:b",
            mass_balance_n_evap_out="mass_balance:c",
            mass_balance_n_cond_out="mass_balance:d",
            pressure_drop_accumulator="pressure_drop:acc",
            pressure_drop_pump="pressure_drop:pump",
            pressure_drop_evaporator="pressure_drop:evap",
            pressure_drop_condenser="pressure_drop:cond",
        )


# ---------------------------------------------------------------------------
# Group 7: Validation — wrong types
# ---------------------------------------------------------------------------


def test_wrong_type_component_id_rejected_by_factory():
    with pytest.raises(TypeError):
        build_fixed_single_loop_scenario(accumulator_id=42)  # type: ignore[arg-type]


def test_wrong_type_node_id_rejected_by_factory():
    with pytest.raises(TypeError):
        build_fixed_single_loop_scenario(n_acc_out_id=99)  # type: ignore[arg-type]


def test_wrong_type_for_graph_in_scenario_rejected():
    scenario = build_fixed_single_loop_scenario()
    with pytest.raises(TypeError, match="NetworkGraph"):
        FixedSingleLoopScenario(
            graph="not_a_graph",  # type: ignore[arg-type]
            assembly=scenario.assembly,
            binding_context=scenario.binding_context,
            component_ids=scenario.component_ids,
            node_ids=scenario.node_ids,
            unknown_names=scenario.unknown_names,
            residual_names=scenario.residual_names,
        )


def test_wrong_type_for_assembly_in_scenario_rejected():
    scenario = build_fixed_single_loop_scenario()
    with pytest.raises(TypeError, match="NetworkResidualAssembly"):
        FixedSingleLoopScenario(
            graph=scenario.graph,
            assembly="not_an_assembly",  # type: ignore[arg-type]
            binding_context=scenario.binding_context,
            component_ids=scenario.component_ids,
            node_ids=scenario.node_ids,
            unknown_names=scenario.unknown_names,
            residual_names=scenario.residual_names,
        )


def test_wrong_type_for_metadata_rejected_by_factory():
    with pytest.raises(TypeError, match="Mapping"):
        build_fixed_single_loop_scenario(metadata="not a mapping")  # type: ignore[arg-type]


def test_wrong_type_for_component_ids_in_container_rejected():
    with pytest.raises(TypeError):
        FixedSingleLoopComponentIds(
            accumulator="not_a_cid",  # type: ignore[arg-type]
            pump=ComponentInstanceId("pump"),
            evaporator=ComponentInstanceId("evap"),
            condenser=ComponentInstanceId("cond"),
        )


def test_wrong_type_for_node_ids_in_container_rejected():
    with pytest.raises(TypeError):
        FixedSingleLoopNodeIds(
            n_acc_out="not_a_nid",  # type: ignore[arg-type]
            n_pump_out=GraphNodeId("b"),
            n_evap_out=GraphNodeId("c"),
            n_cond_out=GraphNodeId("d"),
        )


def test_wrong_type_for_unknown_name_rejected():
    with pytest.raises(TypeError):
        FixedSingleLoopUnknownNames(
            mdot_accumulator=123,  # type: ignore[arg-type]
            mdot_pump="mdot:pump",
            mdot_evaporator="mdot:evap",
            mdot_condenser="mdot:cond",
            P_n_acc_out="P:a",
            P_n_pump_out="P:b",
            P_n_evap_out="P:c",
            P_n_cond_out="P:d",
        )


def test_wrong_type_for_residual_name_rejected():
    with pytest.raises(TypeError):
        FixedSingleLoopResidualNames(
            mass_balance_n_acc_out=0,  # type: ignore[arg-type]
            mass_balance_n_pump_out="mass_balance:b",
            mass_balance_n_evap_out="mass_balance:c",
            mass_balance_n_cond_out="mass_balance:d",
            pressure_drop_accumulator="pressure_drop:acc",
            pressure_drop_pump="pressure_drop:pump",
            pressure_drop_evaporator="pressure_drop:evap",
            pressure_drop_condenser="pressure_drop:cond",
        )


# ---------------------------------------------------------------------------
# Group 8: Compatibility with existing stack
# ---------------------------------------------------------------------------


def test_compatible_with_network_unknown_values():
    scenario = build_fixed_single_loop_scenario()
    unknown_map = {name: 1.0 for name in scenario.assembly.unknowns.names()}
    uv = NetworkUnknownValues(unknown_map)
    assert isinstance(uv, NetworkUnknownValues)
    assert len(uv.values) == 8


def test_build_readonly_unknown_view_succeeds():
    scenario = build_fixed_single_loop_scenario()
    unknown_map = {name: 1.0 for name in scenario.assembly.unknowns.names()}
    uv = NetworkUnknownValues(unknown_map)
    view = build_readonly_unknown_view(scenario.binding_context, uv)
    assert view is not None


def test_exact_unknown_coverage_enforced_missing_unknown():
    scenario = build_fixed_single_loop_scenario()
    names = list(scenario.assembly.unknowns.names())
    incomplete = {name: 1.0 for name in names[:-1]}  # missing last unknown
    with pytest.raises((ValueError, KeyError)):
        build_readonly_unknown_view(scenario.binding_context, incomplete)


def test_component_scoped_view_works():
    scenario = build_fixed_single_loop_scenario()
    unknown_map = {name: 2.0 for name in scenario.assembly.unknowns.names()}
    uv = NetworkUnknownValues(unknown_map)
    view = build_readonly_unknown_view(scenario.binding_context, uv)
    comp_view = view.for_component(scenario.component_ids.pump)
    assert comp_view is not None
    pump_mdot_name = scenario.unknown_names.mdot_pump
    assert comp_view.value(pump_mdot_name) == 2.0


def test_node_scoped_view_works():
    scenario = build_fixed_single_loop_scenario()
    unknown_map = {name: 3.0 for name in scenario.assembly.unknowns.names()}
    uv = NetworkUnknownValues(unknown_map)
    view = build_readonly_unknown_view(scenario.binding_context, uv)
    node_view = view.for_node(scenario.node_ids.n_pump_out)
    assert node_view is not None
    pressure_name = scenario.unknown_names.P_n_pump_out
    assert node_view.value(pressure_name) == 3.0


def test_scenario_with_toy_producers_no_physics():
    """Scenario binding context is compatible with toy producers from Block 15A.3."""
    scenario = build_fixed_single_loop_scenario()
    unknown_map = {name: 0.5 for name in scenario.assembly.unknowns.names()}

    class _ToyProducer:
        def __init__(self, cid: ComponentInstanceId) -> None:
            self._cid = cid

        def produce_records(self, ctx: object) -> ContributionRecordSet:
            return ContributionRecordSet(
                records=(
                    ContributionRecord(
                        component_id=self._cid,
                        name="pressure_drop",
                        value=0.0,
                        unit="Pa",
                    ),
                )
            )

    producers = ProductionLikeComponentSet(
        bindings=(
            ProductionLikeComponentBinding(
                component_id=scenario.component_ids.accumulator,
                producer=_ToyProducer(scenario.component_ids.accumulator),
            ),
            ProductionLikeComponentBinding(
                component_id=scenario.component_ids.pump,
                producer=_ToyProducer(scenario.component_ids.pump),
            ),
            ProductionLikeComponentBinding(
                component_id=scenario.component_ids.evaporator,
                producer=_ToyProducer(scenario.component_ids.evaporator),
            ),
            ProductionLikeComponentBinding(
                component_id=scenario.component_ids.condenser,
                producer=_ToyProducer(scenario.component_ids.condenser),
            ),
        )
    )

    records = execute_production_like_contributions(
        scenario.binding_context,
        producers,
        unknown_map,
    )
    assert isinstance(records, ContributionRecordSet)
    assert len(records.records) == 4


def test_unknown_names_in_scenario_match_assembly():
    scenario = build_fixed_single_loop_scenario()
    assert set(scenario.unknown_names.all_names()) == set(scenario.assembly.unknowns.names())


def test_residual_names_in_scenario_match_assembly():
    scenario = build_fixed_single_loop_scenario()
    assert set(scenario.residual_names.all_names()) == set(scenario.assembly.residuals.names())


# ---------------------------------------------------------------------------
# Group 9: Boundary tests — AST / import-level
# ---------------------------------------------------------------------------


def test_scenario_module_no_coolprop_import():
    tree = _parse_ast(_SCENARIO_MODULE)
    assert not _has_import(tree, "CoolProp")


def test_scenario_module_no_property_backend_import():
    tree = _parse_ast(_SCENARIO_MODULE)
    assert not _has_import(tree, "PropertyBackend")


def test_scenario_module_no_correlation_registry_import():
    tree = _parse_ast(_SCENARIO_MODULE)
    assert not _has_import(tree, "CorrelationRegistry")


def test_scenario_module_no_hx_models_import():
    tree = _parse_ast(_SCENARIO_MODULE)
    assert not _has_import(tree, "hx_models")


def test_scenario_module_no_system_state_import():
    tree = _parse_ast(_SCENARIO_MODULE)
    assert not _has_import(tree, "SystemState")


def test_scenario_module_no_fluid_state_import():
    tree = _parse_ast(_SCENARIO_MODULE)
    assert not _has_import(tree, "FluidState")


def test_scenario_module_no_mpl_sim_components_import():
    tree = _parse_ast(_SCENARIO_MODULE)
    assert not _has_import(tree, "mpl_sim.components")


def test_scenario_module_no_mpl_sim_properties_import():
    tree = _parse_ast(_SCENARIO_MODULE)
    assert not _has_import(tree, "mpl_sim.properties")


def test_scenario_module_no_contribute_attribute_calls():
    tree = _parse_ast(_SCENARIO_MODULE)
    assert not _has_contribute_attribute_call(tree)


def test_scenario_module_no_solve_network_pattern():
    """No .solve() or bare solve() call appears as executable AST in the module."""
    tree = _parse_ast(_SCENARIO_MODULE)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "solve":
                pytest.fail("Found .solve() attribute call in scenario module")
            if isinstance(func, ast.Name) and func.id == "solve":
                pytest.fail("Found bare solve() call in scenario module")


def test_this_file_no_coolprop_import():
    tree = _parse_ast(_THIS_FILE)
    assert not _has_import(tree, "CoolProp")


def test_this_file_no_property_backend_import():
    tree = _parse_ast(_THIS_FILE)
    assert not _has_import(tree, "PropertyBackend")


def test_this_file_no_contribute_attribute_calls():
    tree = _parse_ast(_THIS_FILE)
    assert not _has_contribute_attribute_call(tree)


# ---------------------------------------------------------------------------
# Group 10: Production contract regression
# ---------------------------------------------------------------------------


def _get_statuses() -> dict[str, str]:
    results = inspect_known_production_component_contracts()
    return {r.class_name: r.status for r in results}


def test_component_no_contribute_method():
    assert (
        _get_statuses().get("Component") == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD
    )


def test_pipe_no_contribute_method():
    assert _get_statuses().get("Pipe") == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD


def test_pump_component_no_contribute_method():
    assert (
        _get_statuses().get("PumpComponent")
        == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD
    )


def test_accumulator_component_no_contribute_method():
    assert (
        _get_statuses().get("AccumulatorComponent")
        == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD
    )


def test_evaporator_component_no_contribute_method():
    assert (
        _get_statuses().get("EvaporatorComponent")
        == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD
    )


def test_condenser_component_no_contribute_method():
    assert (
        _get_statuses().get("CondenserComponent")
        == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD
    )


# ---------------------------------------------------------------------------
# Group 11: Public API
# ---------------------------------------------------------------------------

_EXPECTED_15B1_SYMBOLS = {
    "FixedSingleLoopComponentIds",
    "FixedSingleLoopNodeIds",
    "FixedSingleLoopUnknownNames",
    "FixedSingleLoopResidualNames",
    "FixedSingleLoopScenario",
    "build_fixed_single_loop_scenario",
}


def test_new_symbols_exported_from_mpl_sim_network():
    import mpl_sim.network as net

    for symbol in _EXPECTED_15B1_SYMBOLS:
        assert hasattr(net, symbol), f"mpl_sim.network missing symbol: {symbol}"


def test_new_symbols_in_all_list():
    import mpl_sim.network as net

    for symbol in _EXPECTED_15B1_SYMBOLS:
        assert symbol in net.__all__, f"mpl_sim.network.__all__ missing: {symbol}"


def test_no_private_symbols_in_all():
    import mpl_sim.network as net

    for name in net.__all__:
        assert not name.startswith("_"), f"private symbol in __all__: {name!r}"
