"""Block 15C.2 — Parallel Branch Topology Scenario Declaration tests.

Tests for the fixed two-branch parallel topology scenario module.

No production component physics are executed.  No SystemState is assembled.
No FluidState is created.  No forbidden imports in the source modules.

Coverage:

Scenario construction:
 1. default parallel topology scenario builds successfully
 2. returned object is ParallelTopologyScenario
 3. scenario contains a NetworkGraph
 4. scenario contains a NetworkResidualAssembly
 5. scenario contains a NetworkBindingContext
 6. scenario has exactly two branches
 7. branch IDs are deterministic
 8. component IDs are explicit and deterministic
 9. node IDs are explicit and deterministic
10. unknown names are explicit and deterministic (13 total)
11. residual names are explicit and deterministic (13 total)
12. unknown ordering is deterministic (mdot first, then P)
13. residual ordering is deterministic (mass_balance first, then pressure_drop)
14. split manifold is a ManifoldDeclaration with SPLIT role
15. merge manifold is a ManifoldDeclaration with MERGE role

Graph topology:
16. graph has exactly 6 nodes
17. graph has exactly 7 component instances
18. split node (n_pump_out) has out-degree 2 (two branches draw from it)
19. merge node (n_merge_out) has in-degree 2 (two merge elements deliver to it)
20. graph summary contains no physical values

Assembly declarations:
21. assembly has exactly 13 unknowns
22. assembly has exactly 13 residuals
23. unknown names in assembly match name container
24. residual names in assembly match name container

Immutability / defensive behavior:
25. scenario object is frozen
26. component ID container is frozen
27. node ID container is frozen
28. unknown name container is frozen
29. residual name container is frozen
30. metadata is defensively copied
31. metadata proxy is read-only

Compatibility with existing stack:
32. binding context is compatible with NetworkUnknownValues
33. build_readonly_unknown_view succeeds with all unknowns set to 0.0
34. component-scoped view works via state map for accumulator
35. node-scoped view works via state map for n_pump_out
36. scenario compatible with toy producer pattern (no physics)

TopologyBranchId:
37. TopologyBranchId builds with non-empty string
38. empty TopologyBranchId rejected
39. whitespace TopologyBranchId rejected
40. wrong type for TopologyBranchId rejected

ParallelBranchDeclaration:
41. ParallelBranchDeclaration builds with valid inputs
42. ParallelBranchDeclaration is frozen
43. inlet_node equals outlet_node rejected
44. wrong type for branch_id rejected
45. wrong type for inlet_node rejected
46. wrong type for outlet_node rejected
47. wrong type for component_id rejected
48. wrong type for merge_component_id rejected

Validation — duplicate/insufficient rejection:
49. fewer than two branches in scenario rejected
50. duplicate branch IDs in scenario rejected
51. duplicate component IDs rejected by factory
52. duplicate node IDs rejected by factory
53. duplicate unknown names rejected by container
54. duplicate residual names rejected by container
55. empty component ID rejected by factory
56. empty node ID rejected by factory
57. wrong type for component ID rejected by factory
58. wrong type for node ID rejected by factory
59. wrong type for metadata rejected
60. mismatched binding-context graph rejected
61. mismatched component IDs rejected
62. mismatched node IDs rejected
63. mismatched unknown names rejected
64. mismatched residual names rejected
65. mismatched branch declaration rejected
66. mismatched split manifold rejected

Custom ID scenario:
67. build_parallel_topology_scenario with custom IDs builds correctly
68. custom scenario unknown names use custom component/node IDs
69. custom scenario binding context validates

Boundary tests (AST-based):
70. parallel_topology_scenario module: no import of CoolProp
71. parallel_topology_scenario module: no import of PropertyBackend
72. parallel_topology_scenario module: no import of CorrelationRegistry
73. parallel_topology_scenario module: no import of SystemState
74. parallel_topology_scenario module: no import of FluidState
75. parallel_topology_scenario module: no import of mpl_sim.components
76. parallel_topology_scenario module: no import of mpl_sim.properties
77. parallel_topology_scenario module: no contribute attribute call
78. parallel_topology_scenario module: no solve(network) or NetworkGraph.solve()
79. this test file: no import of CoolProp

Phase 14G regression:
80. Component has NO_CONTRIBUTE_METHOD status (regression from Phase 14G)
81. Pipe has NO_CONTRIBUTE_METHOD status (regression from Phase 14G)
"""

from __future__ import annotations

import ast
import dataclasses
import pathlib

import pytest

from mpl_sim.network.graph import ComponentInstanceId, GraphNodeId, NetworkGraph
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
from mpl_sim.network.readonly_state_bridge import build_readonly_unknown_view
from mpl_sim.network.residual_assembly import NetworkResidualAssembly
from mpl_sim.network.residual_evaluation import NetworkUnknownValues
from mpl_sim.network.topology_declarations import JunctionRole, ManifoldDeclaration

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _node(s: str) -> GraphNodeId:
    return GraphNodeId(s)


def _cid(s: str) -> ComponentInstanceId:
    return ComponentInstanceId(s)


def _default_scenario() -> ParallelTopologyScenario:
    return build_parallel_topology_scenario()


# ---------------------------------------------------------------------------
# Scenario construction
# ---------------------------------------------------------------------------


class TestParallelTopologyScenarioBuild:
    def test_default_builds(self) -> None:
        s = _default_scenario()
        assert s is not None

    def test_returns_parallel_topology_scenario(self) -> None:
        s = _default_scenario()
        assert isinstance(s, ParallelTopologyScenario)

    def test_has_network_graph(self) -> None:
        s = _default_scenario()
        assert isinstance(s.graph, NetworkGraph)

    def test_has_residual_assembly(self) -> None:
        s = _default_scenario()
        assert isinstance(s.assembly, NetworkResidualAssembly)

    def test_has_binding_context(self) -> None:
        from mpl_sim.network.component_binding import NetworkBindingContext

        s = _default_scenario()
        assert isinstance(s.binding_context, NetworkBindingContext)

    def test_has_exactly_two_branches(self) -> None:
        s = _default_scenario()
        assert len(s.branches) == 2

    def test_branch_ids_deterministic(self) -> None:
        s1 = _default_scenario()
        s2 = _default_scenario()
        ids1 = tuple(b.branch_id.value for b in s1.branches)
        ids2 = tuple(b.branch_id.value for b in s2.branches)
        assert ids1 == ids2

    def test_component_ids_explicit_and_deterministic(self) -> None:
        s = _default_scenario()
        cids = s.component_ids
        assert isinstance(cids, ParallelTopologyComponentIds)
        assert cids.accumulator.value == "accumulator"
        assert cids.pump.value == "pump"
        assert cids.branch_a.value == "branch_a"
        assert cids.branch_b.value == "branch_b"
        assert cids.merge_a.value == "merge_a"
        assert cids.merge_b.value == "merge_b"
        assert cids.condenser.value == "condenser"

    def test_node_ids_explicit_and_deterministic(self) -> None:
        s = _default_scenario()
        nids = s.node_ids
        assert isinstance(nids, ParallelTopologyNodeIds)
        assert nids.n_acc_out.value == "n_acc_out"
        assert nids.n_pump_out.value == "n_pump_out"
        assert nids.n_a_out.value == "n_a_out"
        assert nids.n_b_out.value == "n_b_out"
        assert nids.n_merge_out.value == "n_merge_out"
        assert nids.n_cond_out.value == "n_cond_out"

    def test_unknown_names_deterministic(self) -> None:
        s = _default_scenario()
        un = s.unknown_names
        assert isinstance(un, ParallelTopologyUnknownNames)
        names = un.all_names()
        assert len(names) == 13
        assert len(set(names)) == 13  # all distinct

    def test_residual_names_deterministic(self) -> None:
        s = _default_scenario()
        rn = s.residual_names
        assert isinstance(rn, ParallelTopologyResidualNames)
        names = rn.all_names()
        assert len(names) == 13
        assert len(set(names)) == 13  # all distinct

    def test_unknown_ordering_mdot_first_then_P(self) -> None:
        s = _default_scenario()
        names = list(s.assembly.unknowns.names())
        mdot_names = [n for n in names if n.startswith("mdot:")]
        p_names = [n for n in names if n.startswith("P:")]
        assert len(mdot_names) == 7
        assert len(p_names) == 6
        mdot_indices = [names.index(n) for n in mdot_names]
        p_indices = [names.index(n) for n in p_names]
        assert max(mdot_indices) < min(p_indices)

    def test_residual_ordering_mass_balance_first_then_pressure_drop(self) -> None:
        s = _default_scenario()
        names = list(s.assembly.residuals.names())
        mb_names = [n for n in names if n.startswith("mass_balance:")]
        pd_names = [n for n in names if n.startswith("pressure_drop:")]
        assert len(mb_names) == 6
        assert len(pd_names) == 7
        mb_indices = [names.index(n) for n in mb_names]
        pd_indices = [names.index(n) for n in pd_names]
        assert max(mb_indices) < min(pd_indices)

    def test_split_manifold_is_manifold_declaration(self) -> None:
        s = _default_scenario()
        assert isinstance(s.split_manifold, ManifoldDeclaration)
        assert s.split_manifold.role is JunctionRole.SPLIT

    def test_merge_manifold_is_manifold_declaration(self) -> None:
        s = _default_scenario()
        assert isinstance(s.merge_manifold, ManifoldDeclaration)
        assert s.merge_manifold.role is JunctionRole.MERGE


# ---------------------------------------------------------------------------
# Graph topology
# ---------------------------------------------------------------------------


class TestParallelTopologyGraph:
    def test_graph_has_six_nodes(self) -> None:
        s = _default_scenario()
        assert len(s.graph.nodes()) == 6

    def test_graph_has_seven_components(self) -> None:
        s = _default_scenario()
        assert len(s.graph.instances()) == 7

    def test_split_node_has_out_degree_2(self) -> None:
        s = _default_scenario()
        split_nid = s.node_ids.n_pump_out.value
        out_degree = sum(1 for inst in s.graph.instances() if inst.inlet_node.value == split_nid)
        assert out_degree == 2

    def test_merge_node_has_in_degree_2(self) -> None:
        s = _default_scenario()
        merge_nid = s.node_ids.n_merge_out.value
        in_degree = sum(1 for inst in s.graph.instances() if inst.outlet_node.value == merge_nid)
        assert in_degree == 2

    def test_graph_summary_has_no_physical_values(self) -> None:
        s = _default_scenario()
        summary = s.graph.summary()
        assert isinstance(summary, dict)
        # Only symbolic counts and names — no numeric physical values
        for v in summary.values():
            assert not isinstance(v, float)


# ---------------------------------------------------------------------------
# Assembly declarations
# ---------------------------------------------------------------------------


class TestParallelTopologyAssembly:
    def test_assembly_has_13_unknowns(self) -> None:
        s = _default_scenario()
        assert s.assembly.unknowns.count() == 13

    def test_assembly_has_13_residuals(self) -> None:
        s = _default_scenario()
        assert s.assembly.residuals.count() == 13

    def test_assembly_unknown_names_match_container(self) -> None:
        s = _default_scenario()
        assembly_names = set(s.assembly.unknowns.names())
        container_names = set(s.unknown_names.all_names())
        assert assembly_names == container_names

    def test_assembly_residual_names_match_container(self) -> None:
        s = _default_scenario()
        assembly_names = set(s.assembly.residuals.names())
        container_names = set(s.residual_names.all_names())
        assert assembly_names == container_names


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


class TestParallelTopologyImmutability:
    def test_scenario_frozen(self) -> None:
        s = _default_scenario()
        with pytest.raises((AttributeError, TypeError)):
            s.graph = None  # type: ignore[assignment]

    def test_component_ids_frozen(self) -> None:
        s = _default_scenario()
        with pytest.raises((AttributeError, TypeError)):
            s.component_ids.accumulator = _cid("other")  # type: ignore[misc]

    def test_node_ids_frozen(self) -> None:
        s = _default_scenario()
        with pytest.raises((AttributeError, TypeError)):
            s.node_ids.n_acc_out = _node("other")  # type: ignore[misc]

    def test_unknown_names_frozen(self) -> None:
        s = _default_scenario()
        with pytest.raises((AttributeError, TypeError)):
            s.unknown_names.mdot_accumulator = "other"  # type: ignore[misc]

    def test_residual_names_frozen(self) -> None:
        s = _default_scenario()
        with pytest.raises((AttributeError, TypeError)):
            s.residual_names.pressure_drop_pump = "other"  # type: ignore[misc]

    def test_metadata_defensive_copy(self) -> None:
        src: dict[str, object] = {"tag": "x"}
        s = build_parallel_topology_scenario(metadata=src)
        src["tag"] = "y"
        assert s.metadata is not None
        assert s.metadata["tag"] == "x"

    def test_metadata_proxy_readonly(self) -> None:
        s = build_parallel_topology_scenario(metadata={"k": 1})
        with pytest.raises(TypeError):
            s.metadata["new"] = "v"  # type: ignore[index]


# ---------------------------------------------------------------------------
# Compatibility with existing stack
# ---------------------------------------------------------------------------


class TestParallelTopologyStackCompatibility:
    def _all_zero_values(self, s: ParallelTopologyScenario) -> dict[str, float]:
        return {name: 0.0 for name in s.assembly.unknowns.names()}

    def test_compatible_with_network_unknown_values(self) -> None:
        s = _default_scenario()
        values = self._all_zero_values(s)
        uv = NetworkUnknownValues(values)
        assert uv is not None

    def test_build_readonly_unknown_view_succeeds(self) -> None:
        s = _default_scenario()
        values = self._all_zero_values(s)
        view = build_readonly_unknown_view(s.binding_context, values)
        assert view is not None

    def test_component_scoped_view_for_accumulator(self) -> None:
        from mpl_sim.network.readonly_state_bridge import ComponentUnknownView

        s = _default_scenario()
        values = self._all_zero_values(s)
        view = build_readonly_unknown_view(s.binding_context, values)
        comp_view = view.for_component(s.component_ids.accumulator)
        assert isinstance(comp_view, ComponentUnknownView)

    def test_node_scoped_view_for_n_pump_out(self) -> None:
        from mpl_sim.network.readonly_state_bridge import NodeUnknownView

        s = _default_scenario()
        values = self._all_zero_values(s)
        view = build_readonly_unknown_view(s.binding_context, values)
        node_view = view.for_node(s.node_ids.n_pump_out)
        assert isinstance(node_view, NodeUnknownView)

    def test_toy_producer_pattern_no_physics(self) -> None:
        from mpl_sim.network.readonly_state_bridge import ReadOnlyUnknownView

        s = _default_scenario()
        values = self._all_zero_values(s)
        view = build_readonly_unknown_view(s.binding_context, values)
        assert isinstance(view, ReadOnlyUnknownView)
        # Verify we can read any unknown by name from the view.
        acc_mdot = view.value(s.unknown_names.mdot_accumulator)
        assert acc_mdot == 0.0


# ---------------------------------------------------------------------------
# TopologyBranchId
# ---------------------------------------------------------------------------


class TestTopologyBranchId:
    def test_builds_with_nonempty_string(self) -> None:
        bid = TopologyBranchId("branch_alpha")
        assert bid.value == "branch_alpha"

    def test_empty_rejected(self) -> None:
        with pytest.raises(ValueError):
            TopologyBranchId("")

    def test_whitespace_rejected(self) -> None:
        with pytest.raises(ValueError):
            TopologyBranchId("   ")

    def test_wrong_type_rejected(self) -> None:
        with pytest.raises(TypeError):
            TopologyBranchId(123)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# ParallelBranchDeclaration
# ---------------------------------------------------------------------------


class TestParallelBranchDeclaration:
    def test_builds_with_valid_inputs(self) -> None:
        bd = ParallelBranchDeclaration(
            branch_id=TopologyBranchId("a"),
            inlet_node=_node("n_in"),
            outlet_node=_node("n_out"),
            component_id=_cid("branch_a"),
            merge_component_id=_cid("merge_a"),
        )
        assert bd.branch_id.value == "a"
        assert bd.inlet_node.value == "n_in"
        assert bd.outlet_node.value == "n_out"

    def test_frozen(self) -> None:
        bd = ParallelBranchDeclaration(
            TopologyBranchId("a"),
            _node("n_in"),
            _node("n_out"),
            _cid("branch_a"),
            _cid("merge_a"),
        )
        with pytest.raises((AttributeError, TypeError)):
            bd.branch_id = TopologyBranchId("b")  # type: ignore[misc]

    def test_inlet_equals_outlet_rejected(self) -> None:
        with pytest.raises(ValueError, match="must differ"):
            ParallelBranchDeclaration(
                TopologyBranchId("a"),
                _node("n_same"),
                _node("n_same"),
                _cid("branch_a"),
                _cid("merge_a"),
            )

    def test_wrong_type_branch_id_rejected(self) -> None:
        with pytest.raises(TypeError, match="TopologyBranchId"):
            ParallelBranchDeclaration(
                "a",  # type: ignore[arg-type]
                _node("n_in"),
                _node("n_out"),
                _cid("branch_a"),
                _cid("merge_a"),
            )

    def test_wrong_type_inlet_node_rejected(self) -> None:
        with pytest.raises(TypeError, match="GraphNodeId"):
            ParallelBranchDeclaration(
                TopologyBranchId("a"),
                "n_in",  # type: ignore[arg-type]
                _node("n_out"),
                _cid("branch_a"),
                _cid("merge_a"),
            )

    def test_wrong_type_outlet_node_rejected(self) -> None:
        with pytest.raises(TypeError, match="GraphNodeId"):
            ParallelBranchDeclaration(
                TopologyBranchId("a"),
                _node("n_in"),
                "n_out",  # type: ignore[arg-type]
                _cid("branch_a"),
                _cid("merge_a"),
            )

    def test_wrong_type_component_id_rejected(self) -> None:
        with pytest.raises(TypeError, match="ComponentInstanceId"):
            ParallelBranchDeclaration(
                TopologyBranchId("a"),
                _node("n_in"),
                _node("n_out"),
                "branch_a",  # type: ignore[arg-type]
                _cid("merge_a"),
            )

    def test_wrong_type_merge_component_id_rejected(self) -> None:
        with pytest.raises(TypeError, match="ComponentInstanceId"):
            ParallelBranchDeclaration(
                TopologyBranchId("a"),
                _node("n_in"),
                _node("n_out"),
                _cid("branch_a"),
                "merge_a",  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# Validation — duplicate / insufficient
# ---------------------------------------------------------------------------


class TestParallelTopologyValidation:
    def test_fewer_than_two_branches_rejected(self) -> None:
        s = _default_scenario()
        with pytest.raises(ValueError, match="at least two"):
            dataclasses.replace(s, branches=s.branches[:1])

    def test_duplicate_branch_ids_rejected(self) -> None:
        s = _default_scenario()
        dup_branches = (s.branches[0], s.branches[0])
        with pytest.raises(ValueError, match="distinct"):
            dataclasses.replace(s, branches=dup_branches)

    def test_duplicate_component_ids_rejected_by_factory(self) -> None:
        with pytest.raises(ValueError, match="distinct"):
            build_parallel_topology_scenario(branch_a_id="accumulator")

    def test_duplicate_node_ids_rejected_by_factory(self) -> None:
        with pytest.raises(ValueError, match="distinct"):
            build_parallel_topology_scenario(n_a_out_id="n_acc_out")

    def test_duplicate_unknown_names_rejected_by_container(self) -> None:
        with pytest.raises(ValueError, match="distinct"):
            ParallelTopologyUnknownNames(
                mdot_accumulator="mdot:accumulator",
                mdot_pump="mdot:accumulator",  # duplicate
                mdot_branch_a="mdot:branch_a",
                mdot_branch_b="mdot:branch_b",
                mdot_merge_a="mdot:merge_a",
                mdot_merge_b="mdot:merge_b",
                mdot_condenser="mdot:condenser",
                P_n_acc_out="P:n_acc_out",
                P_n_pump_out="P:n_pump_out",
                P_n_a_out="P:n_a_out",
                P_n_b_out="P:n_b_out",
                P_n_merge_out="P:n_merge_out",
                P_n_cond_out="P:n_cond_out",
            )

    def test_duplicate_residual_names_rejected_by_container(self) -> None:
        with pytest.raises(ValueError, match="distinct"):
            ParallelTopologyResidualNames(
                mass_balance_n_acc_out="mass_balance:n_acc_out",
                mass_balance_n_pump_out="mass_balance:n_acc_out",  # duplicate
                mass_balance_n_a_out="mass_balance:n_a_out",
                mass_balance_n_b_out="mass_balance:n_b_out",
                mass_balance_n_merge_out="mass_balance:n_merge_out",
                mass_balance_n_cond_out="mass_balance:n_cond_out",
                pressure_drop_accumulator="pressure_drop:accumulator",
                pressure_drop_pump="pressure_drop:pump",
                pressure_drop_branch_a="pressure_drop:branch_a",
                pressure_drop_branch_b="pressure_drop:branch_b",
                pressure_drop_merge_a="pressure_drop:merge_a",
                pressure_drop_merge_b="pressure_drop:merge_b",
                pressure_drop_condenser="pressure_drop:condenser",
            )

    def test_empty_component_id_rejected_by_factory(self) -> None:
        with pytest.raises(ValueError):
            build_parallel_topology_scenario(pump_id="")

    def test_empty_node_id_rejected_by_factory(self) -> None:
        with pytest.raises(ValueError):
            build_parallel_topology_scenario(n_a_out_id="")

    def test_wrong_type_component_id_rejected_by_factory(self) -> None:
        with pytest.raises(TypeError):
            build_parallel_topology_scenario(pump_id=123)  # type: ignore[arg-type]

    def test_wrong_type_node_id_rejected_by_factory(self) -> None:
        with pytest.raises(TypeError):
            build_parallel_topology_scenario(n_a_out_id=42)  # type: ignore[arg-type]

    def test_wrong_type_metadata_rejected(self) -> None:
        with pytest.raises(TypeError):
            build_parallel_topology_scenario(metadata=["bad"])  # type: ignore[arg-type]

    def test_mismatched_binding_context_graph_rejected(self) -> None:
        s = _default_scenario()
        other = build_parallel_topology_scenario(accumulator_id="other_accumulator")
        with pytest.raises(ValueError, match="binding_context.graph"):
            dataclasses.replace(s, binding_context=other.binding_context)

    def test_mismatched_component_ids_rejected(self) -> None:
        s = _default_scenario()
        other = build_parallel_topology_scenario(accumulator_id="other_accumulator")
        with pytest.raises(ValueError, match="component_ids"):
            dataclasses.replace(s, component_ids=other.component_ids)

    def test_mismatched_node_ids_rejected(self) -> None:
        s = _default_scenario()
        other = build_parallel_topology_scenario(n_acc_out_id="other_n_acc_out")
        with pytest.raises(ValueError, match="node_ids"):
            dataclasses.replace(s, node_ids=other.node_ids)

    def test_mismatched_unknown_names_rejected(self) -> None:
        s = _default_scenario()
        bad_names = dataclasses.replace(
            s.unknown_names,
            mdot_accumulator="mdot:other_accumulator",
        )
        with pytest.raises(ValueError, match="unknown_names"):
            dataclasses.replace(s, unknown_names=bad_names)

    def test_mismatched_residual_names_rejected(self) -> None:
        s = _default_scenario()
        bad_names = dataclasses.replace(
            s.residual_names,
            pressure_drop_accumulator="pressure_drop:other_accumulator",
        )
        with pytest.raises(ValueError, match="residual_names"):
            dataclasses.replace(s, residual_names=bad_names)

    def test_mismatched_branch_declaration_rejected(self) -> None:
        s = _default_scenario()
        bad_branch = dataclasses.replace(
            s.branches[0],
            outlet_node=s.node_ids.n_b_out,
        )
        with pytest.raises(ValueError, match="branches"):
            dataclasses.replace(s, branches=(bad_branch, s.branches[1]))

    def test_mismatched_split_manifold_rejected(self) -> None:
        s = _default_scenario()
        bad_manifold = dataclasses.replace(
            s.split_manifold,
            manifold_id="wrong_split",
        )
        with pytest.raises(ValueError, match="split_manifold"):
            dataclasses.replace(s, split_manifold=bad_manifold)


# ---------------------------------------------------------------------------
# Custom ID scenario
# ---------------------------------------------------------------------------


class TestParallelTopologyCustomIds:
    def test_custom_ids_build_correctly(self) -> None:
        s = build_parallel_topology_scenario(
            accumulator_id="acc",
            pump_id="pmp",
            branch_a_id="br_a",
            branch_b_id="br_b",
            merge_a_id="mg_a",
            merge_b_id="mg_b",
            condenser_id="cnd",
            n_acc_out_id="na",
            n_pump_out_id="np",
            n_a_out_id="n_ao",
            n_b_out_id="n_bo",
            n_merge_out_id="nm",
            n_cond_out_id="nc",
        )
        assert s.component_ids.accumulator.value == "acc"
        assert s.component_ids.pump.value == "pmp"
        assert s.node_ids.n_pump_out.value == "np"

    def test_custom_scenario_unknown_names_use_custom_ids(self) -> None:
        s = build_parallel_topology_scenario(
            accumulator_id="my_acc",
            pump_id="my_pump",
            branch_a_id="my_branch_a",
            branch_b_id="my_branch_b",
            merge_a_id="my_merge_a",
            merge_b_id="my_merge_b",
            condenser_id="my_cond",
            n_acc_out_id="my_n_acc",
            n_pump_out_id="my_n_pump",
            n_a_out_id="my_n_a",
            n_b_out_id="my_n_b",
            n_merge_out_id="my_n_merge",
            n_cond_out_id="my_n_cond",
        )
        assert s.unknown_names.mdot_accumulator == "mdot:my_acc"
        assert s.unknown_names.P_n_pump_out == "P:my_n_pump"
        assert s.residual_names.mass_balance_n_merge_out == "mass_balance:my_n_merge"

    def test_custom_scenario_binding_context_validates(self) -> None:
        from mpl_sim.network.component_binding import NetworkBindingContext

        s = build_parallel_topology_scenario(
            accumulator_id="acc2",
            pump_id="pump2",
            branch_a_id="ba2",
            branch_b_id="bb2",
            merge_a_id="ma2",
            merge_b_id="mb2",
            condenser_id="cond2",
            n_acc_out_id="na2",
            n_pump_out_id="np2",
            n_a_out_id="nao2",
            n_b_out_id="nbo2",
            n_merge_out_id="nm2",
            n_cond_out_id="nc2",
        )
        assert isinstance(s.binding_context, NetworkBindingContext)


# ---------------------------------------------------------------------------
# Boundary tests — AST / import-level
# ---------------------------------------------------------------------------

_SCENARIO_MODULE = (
    pathlib.Path(__file__).parent.parent.parent
    / "src"
    / "mpl_sim"
    / "network"
    / "parallel_topology_scenario.py"
)
_THIS_FILE = pathlib.Path(__file__)


def _parse_ast(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


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


class TestParallelTopologyScenarioBoundary:
    def test_no_coolprop_import(self) -> None:
        assert not _has_import(_parse_ast(_SCENARIO_MODULE), "CoolProp")

    def test_no_property_backend_import(self) -> None:
        assert not _has_import(_parse_ast(_SCENARIO_MODULE), "PropertyBackend")

    def test_no_correlation_registry_import(self) -> None:
        assert not _has_import(_parse_ast(_SCENARIO_MODULE), "CorrelationRegistry")

    def test_no_system_state_import(self) -> None:
        assert not _has_import(_parse_ast(_SCENARIO_MODULE), "SystemState")

    def test_no_fluid_state_import(self) -> None:
        assert not _has_import(_parse_ast(_SCENARIO_MODULE), "FluidState")

    def test_no_components_import(self) -> None:
        assert not _has_import(_parse_ast(_SCENARIO_MODULE), "mpl_sim.components")

    def test_no_properties_import(self) -> None:
        assert not _has_import(_parse_ast(_SCENARIO_MODULE), "mpl_sim.properties")

    def test_no_contribute_attribute_calls(self) -> None:
        assert not _has_contribute_attribute_call(_parse_ast(_SCENARIO_MODULE))

    def test_no_solve_network_or_graph_solve(self) -> None:
        tree = _parse_ast(_SCENARIO_MODULE)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "solve":
                    pytest.fail("Found .solve() attribute call in parallel topology module")
                if isinstance(func, ast.Name) and func.id == "solve":
                    pytest.fail("Found bare solve() call in parallel topology module")

    def test_this_file_no_coolprop_import(self) -> None:
        assert not _has_import(_parse_ast(_THIS_FILE), "CoolProp")


# ---------------------------------------------------------------------------
# Phase 14G regression — production component contract inspection
# ---------------------------------------------------------------------------


class TestPhase14GRegression:
    def test_component_has_no_contribute_method(self) -> None:
        from mpl_sim.components.base import Component
        from mpl_sim.network.production_component_inspection import (
            ProductionComponentContractStatus,
            inspect_production_component_contract,
        )

        result = inspect_production_component_contract(Component)
        assert result.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD

    def test_pipe_has_no_contribute_method(self) -> None:
        from mpl_sim.components.pipe import Pipe
        from mpl_sim.network.production_component_inspection import (
            ProductionComponentContractStatus,
            inspect_production_component_contract,
        )

        result = inspect_production_component_contract(Pipe)
        assert result.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD
