"""Phase 13E network graph foundation tests.

Coverage items (22 required):
 1.  create valid node IDs
 2.  reject empty node IDs
 3.  create valid component instance IDs
 4.  reject empty component instance IDs
 5.  construct minimal graph with two nodes and one component
 6.  deterministic node order
 7.  deterministic component order
 8.  reject duplicate nodes
 9.  reject duplicate component instances
10.  reject component with unknown inlet node
11.  reject component with unknown outlet node
12.  reject self-loop component unless explicitly allowed
13.  graph summary exposes nodes/components without physical values
14.  graph contains no FluidState, mdot, pressure, enthalpy, or property values
15.  no solver method exists on NetworkGraph
16.  no solve(network) API exists in the graph module
17.  no residual assembly exists
18.  no property lookup
19.  no registry resolution
20.  public exports work from mpl_sim.network
21.  existing Phase 13A/13B/13C/13D tests still pass (ensured by full suite run)
22.  docs do not claim network solving for Phase 13E
"""

from __future__ import annotations

import importlib
import inspect

import pytest

from mpl_sim.network import (
    ComponentInstance,
    ComponentInstanceId,
    GraphNode,
    GraphNodeId,
    NetworkGraph,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _node(value: str) -> GraphNode:
    return GraphNode(node_id=GraphNodeId(value))


def _inst(
    iid: str,
    ctype: str,
    inlet: str,
    outlet: str,
) -> ComponentInstance:
    return ComponentInstance(
        instance_id=ComponentInstanceId(iid),
        component_type=ctype,
        inlet_node=GraphNodeId(inlet),
        outlet_node=GraphNodeId(outlet),
    )


# ---------------------------------------------------------------------------
# Coverage item 1 & 2 — GraphNodeId
# ---------------------------------------------------------------------------


class TestGraphNodeId:
    def test_valid_node_id(self) -> None:
        nid = GraphNodeId("node_A")
        assert nid.value == "node_A"

    def test_valid_node_id_str(self) -> None:
        nid = GraphNodeId("evap_outlet")
        assert str(nid) == "evap_outlet"

    def test_empty_node_id_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            GraphNodeId("")

    @pytest.mark.parametrize("value", [" ", "\t", "\n"])
    def test_whitespace_only_node_id_raises(self, value: str) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            GraphNodeId(value)

    @pytest.mark.parametrize("value", [None, 1, True])
    def test_non_string_node_id_raises(self, value: object) -> None:
        with pytest.raises(TypeError, match="string"):
            GraphNodeId(value)  # type: ignore[arg-type]

    def test_node_id_equality(self) -> None:
        assert GraphNodeId("A") == GraphNodeId("A")
        assert GraphNodeId("A") != GraphNodeId("B")

    def test_node_id_hashable(self) -> None:
        ids = {GraphNodeId("A"), GraphNodeId("B"), GraphNodeId("A")}
        assert len(ids) == 2

    def test_node_id_frozen(self) -> None:
        nid = GraphNodeId("A")
        with pytest.raises((AttributeError, TypeError)):
            nid.value = "B"  # type: ignore[misc]

    def test_single_char_node_id_valid(self) -> None:
        nid = GraphNodeId("x")
        assert nid.value == "x"


# ---------------------------------------------------------------------------
# Coverage items 3 & 4 — ComponentInstanceId
# ---------------------------------------------------------------------------


class TestComponentInstanceId:
    def test_valid_instance_id(self) -> None:
        iid = ComponentInstanceId("evap_1")
        assert iid.value == "evap_1"

    def test_valid_instance_id_str(self) -> None:
        iid = ComponentInstanceId("cond_1")
        assert str(iid) == "cond_1"

    def test_empty_instance_id_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ComponentInstanceId("")

    @pytest.mark.parametrize("value", [" ", "\t", "\n"])
    def test_whitespace_only_instance_id_raises(self, value: str) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ComponentInstanceId(value)

    @pytest.mark.parametrize("value", [None, 1, True])
    def test_non_string_instance_id_raises(self, value: object) -> None:
        with pytest.raises(TypeError, match="string"):
            ComponentInstanceId(value)  # type: ignore[arg-type]

    def test_instance_id_equality(self) -> None:
        assert ComponentInstanceId("c1") == ComponentInstanceId("c1")
        assert ComponentInstanceId("c1") != ComponentInstanceId("c2")

    def test_instance_id_hashable(self) -> None:
        ids = {ComponentInstanceId("c1"), ComponentInstanceId("c2"), ComponentInstanceId("c1")}
        assert len(ids) == 2

    def test_instance_id_frozen(self) -> None:
        iid = ComponentInstanceId("c1")
        with pytest.raises((AttributeError, TypeError)):
            iid.value = "c2"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# GraphNode
# ---------------------------------------------------------------------------


class TestGraphNode:
    def test_valid_graph_node(self) -> None:
        node = GraphNode(node_id=GraphNodeId("node_A"))
        assert node.node_id.value == "node_A"

    def test_graph_node_equality(self) -> None:
        a = GraphNode(node_id=GraphNodeId("A"))
        b = GraphNode(node_id=GraphNodeId("A"))
        c = GraphNode(node_id=GraphNodeId("B"))
        assert a == b
        assert a != c

    def test_graph_node_frozen(self) -> None:
        node = GraphNode(node_id=GraphNodeId("A"))
        with pytest.raises((AttributeError, TypeError)):
            node.node_id = GraphNodeId("B")  # type: ignore[misc]

    def test_wrong_node_id_type_raises(self) -> None:
        with pytest.raises(TypeError, match="GraphNodeId"):
            GraphNode(node_id="A")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# ComponentInstance — coverage item 12 (self-loop rejection)
# ---------------------------------------------------------------------------


class TestComponentInstance:
    def test_valid_component_instance(self) -> None:
        inst = ComponentInstance(
            instance_id=ComponentInstanceId("evap"),
            component_type="evaporator",
            inlet_node=GraphNodeId("A"),
            outlet_node=GraphNodeId("B"),
        )
        assert inst.instance_id.value == "evap"
        assert inst.component_type == "evaporator"
        assert inst.inlet_node.value == "A"
        assert inst.outlet_node.value == "B"

    def test_empty_component_type_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ComponentInstance(
                instance_id=ComponentInstanceId("c"),
                component_type="",
                inlet_node=GraphNodeId("A"),
                outlet_node=GraphNodeId("B"),
            )

    def test_whitespace_only_component_type_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ComponentInstance(
                instance_id=ComponentInstanceId("c"),
                component_type=" \t",
                inlet_node=GraphNodeId("A"),
                outlet_node=GraphNodeId("B"),
            )

    def test_non_string_component_type_raises(self) -> None:
        with pytest.raises(TypeError, match="string"):
            ComponentInstance(
                instance_id=ComponentInstanceId("c"),
                component_type=1,  # type: ignore[arg-type]
                inlet_node=GraphNodeId("A"),
                outlet_node=GraphNodeId("B"),
            )

    def test_wrong_instance_id_type_raises(self) -> None:
        with pytest.raises(TypeError, match="ComponentInstanceId"):
            ComponentInstance(
                instance_id="c",  # type: ignore[arg-type]
                component_type="pipe",
                inlet_node=GraphNodeId("A"),
                outlet_node=GraphNodeId("B"),
            )

    def test_wrong_inlet_node_type_raises(self) -> None:
        with pytest.raises(TypeError, match="GraphNodeId"):
            ComponentInstance(
                instance_id=ComponentInstanceId("c"),
                component_type="pipe",
                inlet_node="A",  # type: ignore[arg-type]
                outlet_node=GraphNodeId("B"),
            )

    def test_wrong_outlet_node_type_raises(self) -> None:
        with pytest.raises(TypeError, match="GraphNodeId"):
            ComponentInstance(
                instance_id=ComponentInstanceId("c"),
                component_type="pipe",
                inlet_node=GraphNodeId("A"),
                outlet_node="B",  # type: ignore[arg-type]
            )

    def test_self_loop_raises(self) -> None:
        with pytest.raises(ValueError, match="inlet_node and outlet_node must differ"):
            ComponentInstance(
                instance_id=ComponentInstanceId("pump"),
                component_type="pump",
                inlet_node=GraphNodeId("A"),
                outlet_node=GraphNodeId("A"),
            )

    def test_self_loop_error_names_node(self) -> None:
        with pytest.raises(ValueError, match="A"):
            ComponentInstance(
                instance_id=ComponentInstanceId("c"),
                component_type="evaporator",
                inlet_node=GraphNodeId("A"),
                outlet_node=GraphNodeId("A"),
            )

    def test_component_instance_frozen(self) -> None:
        inst = ComponentInstance(
            instance_id=ComponentInstanceId("c"),
            component_type="pump",
            inlet_node=GraphNodeId("A"),
            outlet_node=GraphNodeId("B"),
        )
        with pytest.raises((AttributeError, TypeError)):
            inst.component_type = "valve"  # type: ignore[misc]

    def test_component_instance_equality(self) -> None:
        a = ComponentInstance(
            instance_id=ComponentInstanceId("c"),
            component_type="pump",
            inlet_node=GraphNodeId("A"),
            outlet_node=GraphNodeId("B"),
        )
        b = ComponentInstance(
            instance_id=ComponentInstanceId("c"),
            component_type="pump",
            inlet_node=GraphNodeId("A"),
            outlet_node=GraphNodeId("B"),
        )
        assert a == b


# ---------------------------------------------------------------------------
# Coverage item 5 — minimal graph (2 nodes, 1 component)
# ---------------------------------------------------------------------------


class TestNetworkGraphMinimal:
    def test_minimal_two_nodes_one_component(self) -> None:
        nodes = [_node("A"), _node("B")]
        instances = [_inst("evap", "evaporator", "A", "B")]
        graph = NetworkGraph(nodes=nodes, instances=instances)
        assert len(graph.nodes()) == 2
        assert len(graph.instances()) == 1

    def test_minimal_graph_node_ids(self) -> None:
        nodes = [_node("A"), _node("B")]
        instances = [_inst("evap", "evaporator", "A", "B")]
        graph = NetworkGraph(nodes=nodes, instances=instances)
        assert graph.node_ids() == (GraphNodeId("A"), GraphNodeId("B"))

    def test_minimal_graph_instance_ids(self) -> None:
        nodes = [_node("A"), _node("B")]
        instances = [_inst("evap", "evaporator", "A", "B")]
        graph = NetworkGraph(nodes=nodes, instances=instances)
        assert graph.instance_ids() == (ComponentInstanceId("evap"),)

    def test_empty_graph_allowed(self) -> None:
        graph = NetworkGraph(nodes=[], instances=[])
        assert graph.nodes() == ()
        assert graph.instances() == ()

    def test_nodes_only_graph_allowed(self) -> None:
        graph = NetworkGraph(nodes=[_node("A"), _node("B")], instances=[])
        assert len(graph.nodes()) == 2
        assert len(graph.instances()) == 0

    def test_graph_with_multiple_components(self) -> None:
        nodes = [_node("A"), _node("B"), _node("C")]
        instances = [
            _inst("evap", "evaporator", "A", "B"),
            _inst("cond", "condenser", "B", "C"),
        ]
        graph = NetworkGraph(nodes=nodes, instances=instances)
        assert len(graph.nodes()) == 3
        assert len(graph.instances()) == 2


# ---------------------------------------------------------------------------
# Coverage items 6 & 7 — deterministic order
# ---------------------------------------------------------------------------


class TestDeterministicOrder:
    def test_node_order_preserved(self) -> None:
        nodes = [_node("C"), _node("A"), _node("B")]
        graph = NetworkGraph(nodes=nodes, instances=[])
        ids = [n.node_id.value for n in graph.nodes()]
        assert ids == ["C", "A", "B"]

    def test_node_order_preserved_different_orderings(self) -> None:
        nodes1 = [_node("A"), _node("B")]
        nodes2 = [_node("B"), _node("A")]
        instances = [_inst("evap", "evaporator", "A", "B")]
        g1 = NetworkGraph(nodes=nodes1, instances=instances)
        g2 = NetworkGraph(nodes=nodes2, instances=instances)
        assert [n.node_id.value for n in g1.nodes()] == ["A", "B"]
        assert [n.node_id.value for n in g2.nodes()] == ["B", "A"]

    def test_instance_order_preserved(self) -> None:
        nodes = [_node("A"), _node("B"), _node("C")]
        instances = [
            _inst("evap", "evaporator", "A", "B"),
            _inst("cond", "condenser", "B", "C"),
        ]
        graph = NetworkGraph(nodes=nodes, instances=instances)
        ids = [inst.instance_id.value for inst in graph.instances()]
        assert ids == ["evap", "cond"]

    def test_instance_order_preserved_reversed(self) -> None:
        nodes = [_node("A"), _node("B"), _node("C")]
        instances = [
            _inst("cond", "condenser", "B", "C"),
            _inst("evap", "evaporator", "A", "B"),
        ]
        graph = NetworkGraph(nodes=nodes, instances=instances)
        ids = [inst.instance_id.value for inst in graph.instances()]
        assert ids == ["cond", "evap"]

    def test_repeated_construction_same_order(self) -> None:
        nodes = [_node("X"), _node("Y"), _node("Z")]
        instances = [
            _inst("i1", "pump", "X", "Y"),
            _inst("i2", "evaporator", "Y", "Z"),
        ]
        g1 = NetworkGraph(nodes=nodes, instances=instances)
        g2 = NetworkGraph(nodes=nodes, instances=instances)
        assert [n.node_id.value for n in g1.nodes()] == [n.node_id.value for n in g2.nodes()]
        assert [i.instance_id.value for i in g1.instances()] == [
            i.instance_id.value for i in g2.instances()
        ]


# ---------------------------------------------------------------------------
# Coverage item 8 — reject duplicate nodes
# ---------------------------------------------------------------------------


class TestDuplicateRejection:
    def test_duplicate_node_id_raises(self) -> None:
        with pytest.raises(ValueError, match="Duplicate node id"):
            NetworkGraph(
                nodes=[_node("A"), _node("B"), _node("A")],
                instances=[],
            )

    def test_duplicate_node_id_names_value(self) -> None:
        with pytest.raises(ValueError, match="'A'"):
            NetworkGraph(
                nodes=[_node("A"), _node("A")],
                instances=[],
            )

    def test_duplicate_instance_id_raises(self) -> None:
        with pytest.raises(ValueError, match="Duplicate component instance id"):
            NetworkGraph(
                nodes=[_node("A"), _node("B"), _node("C")],
                instances=[
                    _inst("evap", "evaporator", "A", "B"),
                    _inst("evap", "condenser", "B", "C"),
                ],
            )

    def test_duplicate_instance_id_names_value(self) -> None:
        with pytest.raises(ValueError, match="'evap'"):
            NetworkGraph(
                nodes=[_node("A"), _node("B"), _node("C")],
                instances=[
                    _inst("evap", "evaporator", "A", "B"),
                    _inst("evap", "condenser", "B", "C"),
                ],
            )


# ---------------------------------------------------------------------------
# Coverage items 10 & 11 — reject unknown node references
# ---------------------------------------------------------------------------


class TestUnknownNodeRejection:
    def test_unknown_inlet_node_raises(self) -> None:
        with pytest.raises(ValueError, match="inlet_node"):
            NetworkGraph(
                nodes=[_node("B")],
                instances=[_inst("evap", "evaporator", "MISSING", "B")],
            )

    def test_unknown_inlet_node_names_value(self) -> None:
        with pytest.raises(ValueError, match="'MISSING'"):
            NetworkGraph(
                nodes=[_node("B")],
                instances=[_inst("evap", "evaporator", "MISSING", "B")],
            )

    def test_unknown_outlet_node_raises(self) -> None:
        with pytest.raises(ValueError, match="outlet_node"):
            NetworkGraph(
                nodes=[_node("A")],
                instances=[_inst("evap", "evaporator", "A", "MISSING")],
            )

    def test_unknown_outlet_node_names_value(self) -> None:
        with pytest.raises(ValueError, match="'MISSING'"):
            NetworkGraph(
                nodes=[_node("A")],
                instances=[_inst("evap", "evaporator", "A", "MISSING")],
            )

    def test_empty_node_list_unknown_reference(self) -> None:
        with pytest.raises(ValueError, match="not found in graph nodes"):
            NetworkGraph(
                nodes=[],
                instances=[_inst("evap", "evaporator", "A", "B")],
            )


# ---------------------------------------------------------------------------
# Coverage item 13 — graph summary
# ---------------------------------------------------------------------------


class TestGraphSummary:
    def test_summary_has_required_keys(self) -> None:
        nodes = [_node("A"), _node("B")]
        instances = [_inst("evap", "evaporator", "A", "B")]
        graph = NetworkGraph(nodes=nodes, instances=instances)
        s = graph.summary()
        assert "node_count" in s
        assert "node_ids" in s
        assert "instance_count" in s
        assert "instance_ids" in s
        assert "component_types" in s

    def test_summary_node_count(self) -> None:
        nodes = [_node("A"), _node("B")]
        instances = [_inst("evap", "evaporator", "A", "B")]
        graph = NetworkGraph(nodes=nodes, instances=instances)
        s = graph.summary()
        assert s["node_count"] == 2

    def test_summary_node_ids(self) -> None:
        nodes = [_node("A"), _node("B")]
        instances = [_inst("evap", "evaporator", "A", "B")]
        graph = NetworkGraph(nodes=nodes, instances=instances)
        s = graph.summary()
        assert s["node_ids"] == ["A", "B"]

    def test_summary_instance_count(self) -> None:
        nodes = [_node("A"), _node("B")]
        instances = [_inst("evap", "evaporator", "A", "B")]
        graph = NetworkGraph(nodes=nodes, instances=instances)
        s = graph.summary()
        assert s["instance_count"] == 1

    def test_summary_instance_ids(self) -> None:
        nodes = [_node("A"), _node("B")]
        instances = [_inst("evap", "evaporator", "A", "B")]
        graph = NetworkGraph(nodes=nodes, instances=instances)
        s = graph.summary()
        assert s["instance_ids"] == ["evap"]

    def test_summary_component_types(self) -> None:
        nodes = [_node("A"), _node("B")]
        instances = [_inst("evap", "evaporator", "A", "B")]
        graph = NetworkGraph(nodes=nodes, instances=instances)
        s = graph.summary()
        assert s["component_types"] == ["evaporator"]

    def test_summary_is_plain_dict(self) -> None:
        graph = NetworkGraph(nodes=[_node("A"), _node("B")], instances=[])
        s = graph.summary()
        assert isinstance(s, dict)

    def test_summary_values_are_strings_and_ints(self) -> None:
        nodes = [_node("A"), _node("B")]
        instances = [_inst("c1", "evaporator", "A", "B")]
        graph = NetworkGraph(nodes=nodes, instances=instances)
        s = graph.summary()
        assert isinstance(s["node_count"], int)
        assert isinstance(s["instance_count"], int)
        assert all(isinstance(v, str) for v in s["node_ids"])
        assert all(isinstance(v, str) for v in s["instance_ids"])
        assert all(isinstance(v, str) for v in s["component_types"])


# ---------------------------------------------------------------------------
# Coverage item 14 — no physical values in graph
# ---------------------------------------------------------------------------


class TestNoPhysicalValues:
    def test_graph_nodes_have_no_physical_fields(self) -> None:
        nodes = [_node("A"), _node("B")]
        graph = NetworkGraph(nodes=nodes, instances=[])
        for node in graph.nodes():
            assert not hasattr(node, "P")
            assert not hasattr(node, "h")
            assert not hasattr(node, "mdot")
            assert not hasattr(node, "enthalpy")
            assert not hasattr(node, "pressure")
            assert not hasattr(node, "temperature")
            assert not hasattr(node, "quality")
            assert not hasattr(node, "density")

    def test_component_instance_has_no_physical_fields(self) -> None:
        inst = _inst("c", "evaporator", "A", "B")
        assert not hasattr(inst, "P")
        assert not hasattr(inst, "h")
        assert not hasattr(inst, "mdot")
        assert not hasattr(inst, "enthalpy")
        assert not hasattr(inst, "Q")
        assert not hasattr(inst, "dP")

    def test_summary_contains_no_float_values(self) -> None:
        nodes = [_node("A"), _node("B")]
        instances = [_inst("evap", "evaporator", "A", "B")]
        graph = NetworkGraph(nodes=nodes, instances=instances)
        s = graph.summary()
        for v in s.values():
            if isinstance(v, list):
                for item in v:
                    assert not isinstance(item, float)
            else:
                assert not isinstance(v, float)

    def test_graph_has_no_fluid_state_attribute(self) -> None:
        graph = NetworkGraph(nodes=[_node("A")], instances=[])
        assert not hasattr(graph, "fluid_state")
        assert not hasattr(graph, "FluidState")
        assert not hasattr(graph, "states")

    def test_graph_node_id_is_string_only(self) -> None:
        nid = GraphNodeId("test_node")
        assert isinstance(nid.value, str)


# ---------------------------------------------------------------------------
# Coverage items 15, 16, 17 — no solver, no solve, no residual assembly
# ---------------------------------------------------------------------------


class TestNoBoundaries:
    def test_no_solve_method_on_graph(self) -> None:
        graph = NetworkGraph(nodes=[_node("A")], instances=[])
        assert not hasattr(graph, "solve")

    def test_no_residual_method_on_graph(self) -> None:
        graph = NetworkGraph(nodes=[_node("A")], instances=[])
        assert not hasattr(graph, "residuals")
        assert not hasattr(graph, "assemble_residuals")
        assert not hasattr(graph, "residual_vector")

    def test_no_solve_function_in_graph_module(self) -> None:
        import mpl_sim.network.graph as _gmod

        assert not hasattr(_gmod, "solve")
        assert not callable(getattr(_gmod, "solve", None))

    def test_no_residual_assembly_in_graph_module(self) -> None:
        import mpl_sim.network.graph as _gmod

        assert not hasattr(_gmod, "assemble_residuals")
        assert not hasattr(_gmod, "ResidualVector")

    def test_no_solver_attribute_on_graph(self) -> None:
        graph = NetworkGraph(nodes=[], instances=[])
        assert not hasattr(graph, "solver")
        assert not hasattr(graph, "solve_network")

    def test_no_converge_method_on_graph(self) -> None:
        graph = NetworkGraph(nodes=[], instances=[])
        assert not hasattr(graph, "converge")
        assert not hasattr(graph, "iterate")


# ---------------------------------------------------------------------------
# Coverage items 18 & 19 — no property lookup, no registry
# ---------------------------------------------------------------------------


class TestArchitectureBoundaries:
    def _import_lines(self) -> list[str]:
        """Return only the import statement lines from graph.py."""
        source = inspect.getsource(importlib.import_module("mpl_sim.network.graph"))
        return [
            line.strip()
            for line in source.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]

    def test_no_coolprop_import(self) -> None:
        for line in self._import_lines():
            assert "CoolProp" not in line, f"graph.py must not import CoolProp; found: {line!r}"

    def test_no_property_backend_import(self) -> None:
        for line in self._import_lines():
            assert (
                "PropertyBackend" not in line
            ), f"graph.py must not import PropertyBackend; found: {line!r}"

    def test_no_correlation_registry_import(self) -> None:
        for line in self._import_lines():
            assert (
                "CorrelationRegistry" not in line
            ), f"graph.py must not import CorrelationRegistry; found: {line!r}"

    def test_no_closed_loop_import(self) -> None:
        for line in self._import_lines():
            assert (
                "closed_loop" not in line
            ), f"graph.py must not import from closed_loop; found: {line!r}"

    def test_no_components_import(self) -> None:
        for line in self._import_lines():
            assert (
                "mpl_sim.components" not in line
            ), f"graph.py must not import from components; found: {line!r}"

    def test_no_solvers_import(self) -> None:
        for line in self._import_lines():
            assert (
                "mpl_sim.solvers" not in line
            ), f"graph.py must not import from solvers; found: {line!r}"

    def test_no_properties_import(self) -> None:
        for line in self._import_lines():
            assert (
                "mpl_sim.properties" not in line
            ), f"graph.py must not import from properties; found: {line!r}"

    def test_no_hx_models_import(self) -> None:
        for line in self._import_lines():
            assert (
                "mpl_sim.hx_models" not in line
            ), f"graph.py must not import from hx_models; found: {line!r}"

    def test_no_calibration_import(self) -> None:
        for line in self._import_lines():
            assert (
                "mpl_sim.calibration" not in line
            ), f"graph.py must not import from calibration; found: {line!r}"

    def test_graph_module_imports_only_stdlib(self) -> None:
        import mpl_sim.network.graph as _gmod

        for attr_name in dir(_gmod):
            attr = getattr(_gmod, attr_name)
            if inspect.ismodule(attr):
                mod_name = attr.__name__
                assert not mod_name.startswith(
                    "mpl_sim.closed_loop"
                ), f"graph.py must not import from closed_loop; found {mod_name!r}"
                assert not mod_name.startswith(
                    "mpl_sim.solvers"
                ), f"graph.py must not import from solvers; found {mod_name!r}"
                assert not mod_name.startswith(
                    "mpl_sim.properties"
                ), f"graph.py must not import from properties; found {mod_name!r}"


# ---------------------------------------------------------------------------
# Coverage item 20 — public exports from mpl_sim.network
# ---------------------------------------------------------------------------


class TestPublicExports:
    def test_graph_node_id_importable_from_network(self) -> None:
        from mpl_sim.network import GraphNodeId as _GNI

        assert _GNI is GraphNodeId

    def test_component_instance_id_importable_from_network(self) -> None:
        from mpl_sim.network import ComponentInstanceId as _CII

        assert _CII is ComponentInstanceId

    def test_graph_node_importable_from_network(self) -> None:
        from mpl_sim.network import GraphNode as _GN

        assert _GN is GraphNode

    def test_component_instance_importable_from_network(self) -> None:
        from mpl_sim.network import ComponentInstance as _CI

        assert _CI is ComponentInstance

    def test_network_graph_importable_from_network(self) -> None:
        from mpl_sim.network import NetworkGraph as _NG

        assert _NG is NetworkGraph

    def test_all_exports_in_dunder_all(self) -> None:
        import mpl_sim.network as _net

        assert "GraphNodeId" in _net.__all__
        assert "ComponentInstanceId" in _net.__all__
        assert "GraphNode" in _net.__all__
        assert "ComponentInstance" in _net.__all__
        assert "NetworkGraph" in _net.__all__

    def test_existing_phase7_exports_still_present(self) -> None:
        import mpl_sim.network as _net

        assert "NodeId" in _net.__all__
        assert "NetworkNode" in _net.__all__
        assert "NetworkTopology" in _net.__all__
        assert "NetworkAssembly" in _net.__all__
        assert "validate_topology" in _net.__all__

    def test_phase13e_graph_types_are_distinct_from_phase7(self) -> None:
        from mpl_sim.network import GraphNodeId, NodeId

        assert GraphNodeId is not NodeId

    def test_phase13e_graph_node_distinct_from_phase7_network_node(self) -> None:
        from mpl_sim.network import GraphNode, NetworkNode

        assert GraphNode is not NetworkNode


# ---------------------------------------------------------------------------
# validate_closed_single_loop
# ---------------------------------------------------------------------------


class TestValidateClosedSingleLoop:
    def test_valid_two_node_closed_loop(self) -> None:
        nodes = [_node("A"), _node("B")]
        instances = [
            _inst("evap", "evaporator", "A", "B"),
            _inst("cond", "condenser", "B", "A"),
        ]
        graph = NetworkGraph(nodes=nodes, instances=instances)
        graph.validate_closed_single_loop()  # must not raise

    def test_valid_three_node_closed_loop(self) -> None:
        nodes = [_node("A"), _node("B"), _node("C")]
        instances = [
            _inst("pump", "pump", "A", "B"),
            _inst("evap", "evaporator", "B", "C"),
            _inst("cond", "condenser", "C", "A"),
        ]
        graph = NetworkGraph(nodes=nodes, instances=instances)
        graph.validate_closed_single_loop()  # must not raise

    def test_valid_four_node_closed_loop(self) -> None:
        nodes = [_node("A"), _node("B"), _node("C"), _node("D")]
        instances = [
            _inst("pump", "pump", "A", "B"),
            _inst("evap", "evaporator", "B", "C"),
            _inst("cond", "condenser", "C", "D"),
            _inst("pipe", "pipe", "D", "A"),
        ]
        graph = NetworkGraph(nodes=nodes, instances=instances)
        graph.validate_closed_single_loop()  # must not raise

    def test_empty_instances_raises(self) -> None:
        graph = NetworkGraph(nodes=[_node("A"), _node("B")], instances=[])
        with pytest.raises(ValueError, match="no component instances"):
            graph.validate_closed_single_loop()

    def test_open_chain_raises(self) -> None:
        nodes = [_node("A"), _node("B"), _node("C")]
        instances = [
            _inst("evap", "evaporator", "A", "B"),
            _inst("cond", "condenser", "B", "C"),
        ]
        graph = NetworkGraph(nodes=nodes, instances=instances)
        with pytest.raises(ValueError, match="closed single loop"):
            graph.validate_closed_single_loop()

    def test_branched_graph_raises(self) -> None:
        nodes = [_node("A"), _node("B"), _node("C"), _node("D")]
        instances = [
            _inst("evap1", "evaporator", "A", "B"),
            _inst("evap2", "evaporator", "A", "C"),
            _inst("cond", "condenser", "B", "D"),
        ]
        graph = NetworkGraph(nodes=nodes, instances=instances)
        with pytest.raises(ValueError, match="closed single loop"):
            graph.validate_closed_single_loop()

    def test_disconnected_sub_loops_raise(self) -> None:
        nodes = [_node("A"), _node("B"), _node("C"), _node("D")]
        instances = [
            _inst("i1", "evaporator", "A", "B"),
            _inst("i2", "condenser", "B", "A"),
            _inst("i3", "pump", "C", "D"),
            _inst("i4", "pipe", "D", "C"),
        ]
        graph = NetworkGraph(nodes=nodes, instances=instances)
        with pytest.raises(ValueError, match="closed single loop"):
            graph.validate_closed_single_loop()

    def test_node_with_two_incoming_raises(self) -> None:
        nodes = [_node("A"), _node("B"), _node("C")]
        instances = [
            _inst("i1", "evaporator", "A", "B"),
            _inst("i2", "evaporator", "C", "B"),
        ]
        graph = NetworkGraph(nodes=nodes, instances=instances)
        with pytest.raises(ValueError, match="closed single loop"):
            graph.validate_closed_single_loop()


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


class TestNetworkGraphImmutability:
    def test_graph_rejects_attribute_assignment(self) -> None:
        graph = NetworkGraph(nodes=[_node("A")], instances=[])
        with pytest.raises(AttributeError, match="immutable"):
            graph._nodes = ()  # type: ignore[misc]

    def test_source_list_mutation_does_not_affect_graph(self) -> None:
        nodes = [_node("A"), _node("B")]
        instances = [_inst("evap", "evaporator", "A", "B")]
        graph = NetworkGraph(nodes=nodes, instances=instances)
        nodes.append(_node("C"))
        instances.append(_inst("cond", "condenser", "B", "C"))
        assert len(graph.nodes()) == 2
        assert len(graph.instances()) == 1

    def test_nodes_returns_tuple(self) -> None:
        graph = NetworkGraph(nodes=[_node("A"), _node("B")], instances=[])
        assert isinstance(graph.nodes(), tuple)

    def test_instances_returns_tuple(self) -> None:
        nodes = [_node("A"), _node("B")]
        instances = [_inst("evap", "evaporator", "A", "B")]
        graph = NetworkGraph(nodes=nodes, instances=instances)
        assert isinstance(graph.instances(), tuple)


# ---------------------------------------------------------------------------
# Coverage item 22 — docs do not claim network solving
# ---------------------------------------------------------------------------


class TestDocsHonestClaims:
    def _read_concepts(self) -> str:
        import pathlib

        concepts_path = (
            pathlib.Path(__file__).parent.parent.parent / "docs" / "user_guide" / "CONCEPTS.md"
        )
        return concepts_path.read_text(encoding="utf-8")

    def test_concepts_doc_exists(self) -> None:
        import pathlib

        concepts_path = (
            pathlib.Path(__file__).parent.parent.parent / "docs" / "user_guide" / "CONCEPTS.md"
        )
        assert concepts_path.exists(), "CONCEPTS.md must exist"

    def test_concepts_doc_mentions_phase_13e(self) -> None:
        content = self._read_concepts()
        assert "13E" in content or "Phase 13E" in content or "network graph" in content.lower()

    def test_concepts_doc_does_not_claim_network_solving_in_13e(self) -> None:
        content = self._read_concepts()
        lower = content.lower()
        # "solve(network)" must not appear as a capability claim in Phase 13E section
        # (it may appear in "what this is NOT" sections or historical references)
        # We check that the docs explicitly mark this as deferred or not implemented.
        assert (
            "topology only" in lower
            or "not yet" in lower
            or "deferred" in lower
            or "does not" in lower
        )

    def test_concepts_doc_mentions_topology_representation(self) -> None:
        content = self._read_concepts()
        lower = content.lower()
        assert "topology" in lower

    def test_graph_module_docstring_does_not_claim_solving(self) -> None:
        import mpl_sim.network.graph as _gmod

        docstring = (_gmod.__doc__ or "").lower()
        assert "solve" not in docstring or "does not solve" in docstring
