"""Block 15A.2 — read-only unknown/state bridge tests.

Coverage items (required):

Construction:
 1.  builds from NetworkBindingContext + NetworkUnknownValues
 2.  also accepts plain Mapping[str, float]
 3.  rejects wrong context type
 4.  rejects missing unknown values
 5.  rejects extra unknown values
 6.  rejects non-finite values
 7.  rejects bool values

Immutability:
 8.  source unknown mapping mutation after construction does not affect view
 9.  exposed values mapping is read-only (MappingProxyType)
10.  binding_context is not mutated

Raw access:
11.  value(name) returns the exact scalar
12.  unknown name not declared by assembly is rejected
13.  wrong name type rejected
14.  empty name rejected

Component access:
15.  for_component(ComponentInstanceId) returns ComponentUnknownView
16.  component view exposes only unknowns mapped to that component
17.  unknown component ID rejected
18.  component with no mapped unknowns handled clearly (empty view)
19.  component view values are read-only and exact

Node access:
20.  for_node(GraphNodeId) returns NodeUnknownView
21.  node view exposes only unknowns mapped to that node
22.  unknown node ID rejected
23.  node with no mapped unknowns handled clearly (empty view)
24.  node view values are read-only and exact

Integration with 15A.1:
25.  bridge provider can use read-only view to produce ContributionRecordSet
26.  existing 15A.1 bridge behavior remains backward-compatible
27.  no bridge provider is required to use physical state objects

Boundary tests (import-line and AST based):
28.  no CoolProp import in readonly_state_bridge module
29.  no PropertyBackend import in readonly_state_bridge module
30.  no CorrelationRegistry import in readonly_state_bridge module
31.  no SystemState import in readonly_state_bridge module
32.  no FluidState import in readonly_state_bridge module
33.  no production component class imports in readonly_state_bridge module
34.  no contribute( call in readonly_state_bridge module (AST)
35.  no def contribute in readonly_state_bridge module (AST)
36.  no component_type physics inference in readonly_state_bridge module (AST)
37.  no solve(network) or NetworkGraph.solve definition in readonly_state_bridge module

Public API:
38.  new public symbols exported from mpl_sim.network
39.  no accidental broad exports (symbols individually accessible)

Regression:
40.  Phase 14G inspection still reports NO_CONTRIBUTE_METHOD for six production classes
41.  Block 15A.1 execute_production_bridge_contributions still importable/functional
"""

from __future__ import annotations

import ast
import math
import pathlib

import pytest

from mpl_sim.network import (
    ComponentBinding,
    ComponentInstance,
    ComponentInstanceId,
    ComponentUnknownView,
    ContributionRecord,
    ContributionRecordSet,
    ContributionResidualMap,
    GraphNode,
    GraphNodeId,
    NetworkBindingContext,
    NetworkGraph,
    NetworkUnknownValues,
    NodeUnknownView,
    ProductionBridgeExecutionContext,
    ProductionComponentBridgeBinding,
    ProductionComponentBridgeSet,
    ReadOnlyUnknownView,
    assemble_network_residuals,
    build_binding_context,
    build_component_contribution_from_production_bridge_execution,
    build_readonly_unknown_view,
    execute_production_bridge_contributions,
    inspect_known_production_component_contracts,
)
from mpl_sim.network.component_binding import ComponentStateMap
from mpl_sim.network.readonly_state_bridge import (
    ComponentUnknownView as _CompViewDirect,
)
from mpl_sim.network.readonly_state_bridge import (
    NodeUnknownView as _NodeViewDirect,
)
from mpl_sim.network.readonly_state_bridge import (
    ReadOnlyUnknownView as _ViewDirect,
)
from mpl_sim.network.readonly_state_bridge import (
    build_readonly_unknown_view as _build_direct,
)

# ---------------------------------------------------------------------------
# Source file path for boundary checks
# ---------------------------------------------------------------------------

_SRC = (
    pathlib.Path(__file__).parent.parent.parent
    / "src"
    / "mpl_sim"
    / "network"
    / "readonly_state_bridge.py"
)

# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

_EVAP_ID = ComponentInstanceId("evap")
_COND_ID = ComponentInstanceId("cond")
_N1_ID = GraphNodeId("n1")
_N2_ID = GraphNodeId("n2")


def _node(nid: str) -> GraphNode:
    return GraphNode(node_id=GraphNodeId(nid))


def _inst(iid: str, ctype: str, inlet: str, outlet: str) -> ComponentInstance:
    return ComponentInstance(
        instance_id=ComponentInstanceId(iid),
        component_type=ctype,
        inlet_node=GraphNodeId(inlet),
        outlet_node=GraphNodeId(outlet),
    )


def _toy_graph() -> NetworkGraph:
    return NetworkGraph(
        nodes=[_node("n1"), _node("n2")],
        instances=[
            _inst("evap", "evaporator", "n1", "n2"),
            _inst("cond", "condenser", "n2", "n1"),
        ],
    )


def _toy_binding_context_with_state_map() -> NetworkBindingContext:
    g = _toy_graph()
    asm = assemble_network_residuals(g)
    bindings = [
        ComponentBinding(instance_id=_EVAP_ID, binding_name="evaporator"),
        ComponentBinding(instance_id=_COND_ID, binding_name="condenser"),
    ]
    # Map mdot unknowns to components; pressure unknowns to nodes
    state_map = ComponentStateMap(
        unknown_to_component={
            "mdot:evap": _EVAP_ID,
            "mdot:cond": _COND_ID,
        },
        unknown_to_node={
            "P:n1": _N1_ID,
            "P:n2": _N2_ID,
        },
    )
    return build_binding_context(g, asm, bindings, state_map)


def _toy_binding_context_empty_state_map() -> NetworkBindingContext:
    """Binding context with no unknown-to-component/node mappings."""
    g = _toy_graph()
    asm = assemble_network_residuals(g)
    bindings = [
        ComponentBinding(instance_id=_EVAP_ID, binding_name="evaporator"),
        ComponentBinding(instance_id=_COND_ID, binding_name="condenser"),
    ]
    return build_binding_context(g, asm, bindings, ComponentStateMap())


def _toy_unknown_values() -> dict[str, float]:
    return {
        "mdot:evap": 0.05,
        "mdot:cond": 0.05,
        "P:n1": 1_000.0,
        "P:n2": 400.0,
    }


def _toy_view() -> ReadOnlyUnknownView:
    return build_readonly_unknown_view(
        _toy_binding_context_with_state_map(),
        _toy_unknown_values(),
    )


# ---------------------------------------------------------------------------
# 1–7: Construction
# ---------------------------------------------------------------------------


class TestReadOnlyUnknownViewConstruction:
    def test_builds_from_binding_context_and_network_unknown_values(self):
        """Item 1: builds from NetworkBindingContext + NetworkUnknownValues."""
        bc = _toy_binding_context_with_state_map()
        nuv = NetworkUnknownValues(values=_toy_unknown_values())
        view = build_readonly_unknown_view(bc, nuv)
        assert isinstance(view, ReadOnlyUnknownView)
        assert view.binding_context is bc

    def test_builds_from_plain_mapping(self):
        """Item 2: also accepts plain Mapping[str, float]."""
        bc = _toy_binding_context_with_state_map()
        view = build_readonly_unknown_view(bc, _toy_unknown_values())
        assert isinstance(view, ReadOnlyUnknownView)

    def test_rejects_wrong_context_type(self):
        """Item 3: rejects wrong context type."""
        with pytest.raises(TypeError, match="NetworkBindingContext"):
            build_readonly_unknown_view("not_a_context", _toy_unknown_values())

    def test_rejects_missing_unknown_values(self):
        """Item 4: rejects missing unknown values."""
        bc = _toy_binding_context_with_state_map()
        partial = {"mdot:evap": 0.05, "mdot:cond": 0.05}  # missing P:n1, P:n2
        with pytest.raises(ValueError, match="missing"):
            build_readonly_unknown_view(bc, partial)

    def test_rejects_extra_unknown_values(self):
        """Item 5: rejects extra unknown values."""
        bc = _toy_binding_context_with_state_map()
        extra = {**_toy_unknown_values(), "extra_unknown": 42.0}
        with pytest.raises(ValueError, match="extra"):
            build_readonly_unknown_view(bc, extra)

    def test_rejects_non_finite_values(self):
        """Item 6: rejects non-finite values."""
        bc = _toy_binding_context_with_state_map()
        bad = {**_toy_unknown_values(), "mdot:evap": float("inf")}
        with pytest.raises(ValueError, match="finite"):
            build_readonly_unknown_view(bc, bad)

    def test_rejects_nan_values(self):
        """Item 6: rejects NaN values."""
        bc = _toy_binding_context_with_state_map()
        bad = {**_toy_unknown_values(), "P:n1": float("nan")}
        with pytest.raises(ValueError, match="finite"):
            build_readonly_unknown_view(bc, bad)

    def test_rejects_bool_values(self):
        """Item 7: rejects bool values."""
        bc = _toy_binding_context_with_state_map()
        bad = {**_toy_unknown_values(), "mdot:evap": True}
        with pytest.raises(ValueError, match="bool"):
            build_readonly_unknown_view(bc, bad)

    def test_rejects_non_mapping_unknown_values(self):
        """Item 3/7: rejects non-Mapping unknown_values."""
        bc = _toy_binding_context_with_state_map()
        with pytest.raises(TypeError, match="Mapping"):
            build_readonly_unknown_view(bc, [0.05, 0.05, 1000.0, 400.0])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 8–10: Immutability
# ---------------------------------------------------------------------------


class TestReadOnlyUnknownViewImmutability:
    def test_source_mutation_does_not_affect_view(self):
        """Item 8: mutating source dict after construction does not affect view."""
        bc = _toy_binding_context_with_state_map()
        source = dict(_toy_unknown_values())
        view = build_readonly_unknown_view(bc, source)
        original_evap = view.value("mdot:evap")
        source["mdot:evap"] = 999.0
        assert view.value("mdot:evap") == pytest.approx(original_evap)

    def test_exposed_values_are_read_only(self):
        """Item 9: view.values is a read-only MappingProxyType."""
        view = _toy_view()
        with pytest.raises(TypeError):
            view.values["mdot:evap"] = 99.0  # type: ignore[index]

    def test_view_is_frozen_dataclass(self):
        """Item 9: view itself is frozen (cannot replace fields)."""
        view = _toy_view()
        with pytest.raises((TypeError, AttributeError)):
            view.values = {}  # type: ignore[misc]

    def test_binding_context_not_mutated(self):
        """Item 10: building a view does not modify the binding context."""
        bc = _toy_binding_context_with_state_map()
        n_before = len(bc.assembly.unknowns.names())
        build_readonly_unknown_view(bc, _toy_unknown_values())
        assert len(bc.assembly.unknowns.names()) == n_before


# ---------------------------------------------------------------------------
# 11–14: Raw access
# ---------------------------------------------------------------------------


class TestReadOnlyUnknownViewRawAccess:
    def test_value_returns_exact_scalar(self):
        """Item 11: value(name) returns the exact scalar."""
        view = _toy_view()
        assert view.value("mdot:evap") == pytest.approx(0.05)
        assert view.value("mdot:cond") == pytest.approx(0.05)
        assert view.value("P:n1") == pytest.approx(1_000.0)
        assert view.value("P:n2") == pytest.approx(400.0)

    def test_value_rejects_undeclared_name(self):
        """Item 12: unknown name not declared by assembly is rejected."""
        view = _toy_view()
        with pytest.raises(KeyError):
            view.value("not_declared")

    def test_value_rejects_wrong_name_type(self):
        """Item 13: wrong name type rejected."""
        view = _toy_view()
        with pytest.raises(TypeError, match="string"):
            view.value(42)  # type: ignore[arg-type]

    def test_value_rejects_empty_name(self):
        """Item 14: empty name rejected."""
        view = _toy_view()
        with pytest.raises(ValueError, match="non-empty"):
            view.value("")

    def test_value_rejects_whitespace_name(self):
        """Item 14: whitespace-only name rejected."""
        view = _toy_view()
        with pytest.raises(ValueError, match="non-empty"):
            view.value("   ")


# ---------------------------------------------------------------------------
# 15–19: Component access
# ---------------------------------------------------------------------------


class TestComponentAccess:
    def test_for_component_returns_component_view(self):
        """Item 15: for_component returns a ComponentUnknownView."""
        view = _toy_view()
        cv = view.for_component(_EVAP_ID)
        assert isinstance(cv, ComponentUnknownView)
        assert cv.component_id == _EVAP_ID

    def test_component_view_exposes_only_component_unknowns(self):
        """Item 16: component view exposes only unknowns mapped to that component."""
        view = _toy_view()
        cv = view.for_component(_EVAP_ID)
        # mdot:evap maps to evap; mdot:cond maps to cond; P:n1, P:n2 map to nodes
        assert "mdot:evap" in cv.unknown_values
        assert "mdot:cond" not in cv.unknown_values
        assert "P:n1" not in cv.unknown_values
        assert cv.value("mdot:evap") == pytest.approx(0.05)

    def test_cond_component_view_exposes_only_cond_unknowns(self):
        """Item 16: condenser view exposes only cond unknown."""
        view = _toy_view()
        cv = view.for_component(_COND_ID)
        assert "mdot:cond" in cv.unknown_values
        assert "mdot:evap" not in cv.unknown_values
        assert cv.value("mdot:cond") == pytest.approx(0.05)

    def test_for_component_rejects_unknown_id(self):
        """Item 17: unknown component ID rejected."""
        view = _toy_view()
        with pytest.raises(KeyError):
            view.for_component(ComponentInstanceId("no_such_component"))

    def test_for_component_rejects_wrong_type(self):
        """Item 17: wrong type for component_id rejected."""
        view = _toy_view()
        with pytest.raises(TypeError, match="ComponentInstanceId"):
            view.for_component("evap")  # type: ignore[arg-type]

    def test_component_with_no_mapped_unknowns(self):
        """Item 18: component with no mapped unknowns returns empty view."""
        bc = _toy_binding_context_empty_state_map()
        view = build_readonly_unknown_view(bc, _toy_unknown_values())
        cv = view.for_component(_EVAP_ID)
        assert isinstance(cv, ComponentUnknownView)
        assert len(cv.unknown_values) == 0
        assert cv.names() == ()

    def test_component_view_values_are_read_only(self):
        """Item 19: component view values mapping is read-only."""
        view = _toy_view()
        cv = view.for_component(_EVAP_ID)
        with pytest.raises(TypeError):
            cv.unknown_values["mdot:evap"] = 999.0  # type: ignore[index]

    def test_component_view_value_exact(self):
        """Item 19: component view values are exact (not copies or approximations)."""
        bc = _toy_binding_context_with_state_map()
        uvs = {**_toy_unknown_values(), "mdot:evap": 0.123456789}
        view = build_readonly_unknown_view(bc, uvs)
        cv = view.for_component(_EVAP_ID)
        assert cv.value("mdot:evap") == 0.123456789

    def test_component_view_rejects_unknown_name(self):
        """Item 16: component view rejects name not mapped to this component."""
        view = _toy_view()
        cv = view.for_component(_EVAP_ID)
        with pytest.raises(KeyError):
            cv.value("mdot:cond")

    def test_component_view_names_returns_sorted_tuple(self):
        """Item 16: ComponentUnknownView.names() returns sorted tuple."""
        view = _toy_view()
        cv = view.for_component(_EVAP_ID)
        names = cv.names()
        assert isinstance(names, tuple)
        assert "mdot:evap" in names


# ---------------------------------------------------------------------------
# 20–24: Node access
# ---------------------------------------------------------------------------


class TestNodeAccess:
    def test_for_node_returns_node_view(self):
        """Item 20: for_node returns a NodeUnknownView."""
        view = _toy_view()
        nv = view.for_node(_N1_ID)
        assert isinstance(nv, NodeUnknownView)
        assert nv.node_id == _N1_ID

    def test_node_view_exposes_only_node_unknowns(self):
        """Item 21: node view exposes only unknowns mapped to that node."""
        view = _toy_view()
        nv = view.for_node(_N1_ID)
        assert "P:n1" in nv.unknown_values
        assert "P:n2" not in nv.unknown_values
        assert "mdot:evap" not in nv.unknown_values
        assert nv.value("P:n1") == pytest.approx(1_000.0)

    def test_n2_node_view_exposes_only_n2_unknown(self):
        """Item 21: node n2 view exposes only P:n2."""
        view = _toy_view()
        nv = view.for_node(_N2_ID)
        assert "P:n2" in nv.unknown_values
        assert "P:n1" not in nv.unknown_values
        assert nv.value("P:n2") == pytest.approx(400.0)

    def test_for_node_rejects_unknown_id(self):
        """Item 22: unknown node ID rejected."""
        view = _toy_view()
        with pytest.raises(KeyError):
            view.for_node(GraphNodeId("no_such_node"))

    def test_for_node_rejects_wrong_type(self):
        """Item 22: wrong type for node_id rejected."""
        view = _toy_view()
        with pytest.raises(TypeError, match="GraphNodeId"):
            view.for_node("n1")  # type: ignore[arg-type]

    def test_node_with_no_mapped_unknowns(self):
        """Item 23: node with no mapped unknowns returns empty view."""
        bc = _toy_binding_context_empty_state_map()
        view = build_readonly_unknown_view(bc, _toy_unknown_values())
        nv = view.for_node(_N1_ID)
        assert isinstance(nv, NodeUnknownView)
        assert len(nv.unknown_values) == 0
        assert nv.names() == ()

    def test_node_view_values_are_read_only(self):
        """Item 24: node view values mapping is read-only."""
        view = _toy_view()
        nv = view.for_node(_N1_ID)
        with pytest.raises(TypeError):
            nv.unknown_values["P:n1"] = 999.0  # type: ignore[index]

    def test_node_view_value_exact(self):
        """Item 24: node view values are exact."""
        bc = _toy_binding_context_with_state_map()
        uvs = {**_toy_unknown_values(), "P:n1": 101325.987654321}
        view = build_readonly_unknown_view(bc, uvs)
        nv = view.for_node(_N1_ID)
        assert nv.value("P:n1") == 101325.987654321

    def test_node_view_rejects_unknown_name(self):
        """Item 21: node view rejects name not mapped to this node."""
        view = _toy_view()
        nv = view.for_node(_N1_ID)
        with pytest.raises(KeyError):
            nv.value("P:n2")

    def test_node_view_names_returns_sorted_tuple(self):
        """Item 21: NodeUnknownView.names() returns sorted tuple."""
        view = _toy_view()
        nv = view.for_node(_N1_ID)
        names = nv.names()
        assert isinstance(names, tuple)
        assert "P:n1" in names


# ---------------------------------------------------------------------------
# 25–27: Integration with 15A.1
# ---------------------------------------------------------------------------


class _StubBridgeWithView:
    """Controlled stub bridge that uses ReadOnlyUnknownView. NOT a real production component."""

    def __init__(self, component_id: ComponentInstanceId) -> None:
        self._component_id = component_id

    def produce_records(self, context: ProductionBridgeExecutionContext) -> ContributionRecordSet:
        view = build_readonly_unknown_view(context.binding_context, context.unknown_values)
        cv = view.for_component(self._component_id)
        mdot = cv.value(f"mdot:{self._component_id.value}")
        return ContributionRecordSet(
            records=(
                ContributionRecord(
                    component_id=self._component_id,
                    name="mass_balance",
                    value=mdot,
                ),
            )
        )


class TestIntegrationWith15A1:
    def _setup(self):
        bc = _toy_binding_context_with_state_map()
        uvs = _toy_unknown_values()
        bridge_set = ProductionComponentBridgeSet(
            bindings=(
                ProductionComponentBridgeBinding(
                    component_id=_EVAP_ID,
                    bridge=_StubBridgeWithView(_EVAP_ID),
                ),
                ProductionComponentBridgeBinding(
                    component_id=_COND_ID,
                    bridge=_StubBridgeWithView(_COND_ID),
                ),
            )
        )
        return bc, uvs, bridge_set

    def test_bridge_provider_can_use_view_to_produce_records(self):
        """Item 25: bridge provider uses read-only view to produce ContributionRecordSet."""
        bc, uvs, bridge_set = self._setup()
        result = execute_production_bridge_contributions(bc, bridge_set, uvs)
        assert isinstance(result, ContributionRecordSet)
        assert len(result.records) == 2

    def test_bridge_values_come_from_view(self):
        """Item 25: bridge reads exact values through the view."""
        bc, uvs, bridge_set = self._setup()
        result = execute_production_bridge_contributions(bc, bridge_set, uvs)
        evap_rec = next(r for r in result.records if r.component_id == _EVAP_ID)
        assert evap_rec.value == pytest.approx(uvs["mdot:evap"])

    def test_existing_15a1_bridge_behavior_backward_compatible(self):
        """Item 26: existing 15A.1 bridge behavior (without view) still works."""
        bc = _toy_binding_context_with_state_map()
        uvs = _toy_unknown_values()

        class LegacyBridge:
            def produce_records(
                self, ctx: ProductionBridgeExecutionContext
            ) -> ContributionRecordSet:
                return ContributionRecordSet(
                    records=(
                        ContributionRecord(
                            component_id=_EVAP_ID,
                            name="mass_balance",
                            value=ctx.unknown_values["mdot:evap"],
                        ),
                    )
                )

        class LegacyCondBridge:
            def produce_records(
                self, ctx: ProductionBridgeExecutionContext
            ) -> ContributionRecordSet:
                return ContributionRecordSet(
                    records=(
                        ContributionRecord(
                            component_id=_COND_ID,
                            name="mass_balance",
                            value=ctx.unknown_values["mdot:cond"],
                        ),
                    )
                )

        bridge_set = ProductionComponentBridgeSet(
            bindings=(
                ProductionComponentBridgeBinding(component_id=_EVAP_ID, bridge=LegacyBridge()),
                ProductionComponentBridgeBinding(component_id=_COND_ID, bridge=LegacyCondBridge()),
            )
        )
        result = execute_production_bridge_contributions(bc, bridge_set, uvs)
        assert isinstance(result, ContributionRecordSet)
        assert len(result.records) == 2

    def test_no_physical_state_objects_needed(self):
        """Item 27: bridge providers need no SystemState/FluidState."""
        bc = _toy_binding_context_with_state_map()
        uvs = _toy_unknown_values()
        # The view is built entirely from binding_context + plain floats
        view = build_readonly_unknown_view(bc, uvs)
        # No SystemState, FluidState, or property lookup required
        assert isinstance(view, ReadOnlyUnknownView)
        for name in ("mdot:evap", "mdot:cond", "P:n1", "P:n2"):
            assert math.isfinite(view.value(name))

    def test_convenience_wrapper_still_works(self):
        """Item 26: build_component_contribution_from_production_bridge_execution still works."""
        bc = _toy_binding_context_with_state_map()
        uvs = _toy_unknown_values()

        class SimpleBridge:
            def produce_records(
                self, ctx: ProductionBridgeExecutionContext
            ) -> ContributionRecordSet:
                return ContributionRecordSet(
                    records=(
                        ContributionRecord(
                            component_id=_EVAP_ID,
                            name="mass_balance",
                            value=ctx.unknown_values["mdot:evap"],
                        ),
                    )
                )

        class SimpleCondBridge:
            def produce_records(
                self, ctx: ProductionBridgeExecutionContext
            ) -> ContributionRecordSet:
                return ContributionRecordSet(
                    records=(
                        ContributionRecord(
                            component_id=_COND_ID,
                            name="mass_balance",
                            value=ctx.unknown_values["mdot:cond"],
                        ),
                    )
                )

        bridge_set = ProductionComponentBridgeSet(
            bindings=(
                ProductionComponentBridgeBinding(component_id=_EVAP_ID, bridge=SimpleBridge()),
                ProductionComponentBridgeBinding(component_id=_COND_ID, bridge=SimpleCondBridge()),
            )
        )
        residual_map = ContributionResidualMap(
            mapping={
                (_EVAP_ID, "mass_balance"): "mass_balance:n1",
                (_COND_ID, "mass_balance"): "mass_balance:n2",
            }
        )
        contrib = build_component_contribution_from_production_bridge_execution(
            _EVAP_ID, bc, bridge_set, residual_map, uvs
        )
        assert contrib is not None


# ---------------------------------------------------------------------------
# 28–37: Boundary tests
# ---------------------------------------------------------------------------


def _import_lines(source: str) -> list[str]:
    """Return only import-statement lines from source."""
    return [
        line
        for line in source.splitlines()
        if line.strip().startswith("import ") or line.strip().startswith("from ")
    ]


class TestBoundaryConstraints:
    def _parse_src(self) -> ast.Module:
        return ast.parse(_SRC.read_text(encoding="utf-8"))

    def _import_lines(self) -> list[str]:
        return _import_lines(_SRC.read_text(encoding="utf-8"))

    def test_no_coolprop_import(self):
        """Item 28: no CoolProp import in readonly_state_bridge module."""
        hits = [ln for ln in self._import_lines() if "CoolProp" in ln]
        assert not hits, f"CoolProp import found: {hits}"

    def test_no_property_backend_import(self):
        """Item 29: no PropertyBackend import in readonly_state_bridge module."""
        hits = [ln for ln in self._import_lines() if "PropertyBackend" in ln]
        assert not hits, f"PropertyBackend import found: {hits}"

    def test_no_correlation_registry_import(self):
        """Item 30: no CorrelationRegistry import in readonly_state_bridge module."""
        hits = [
            ln
            for ln in self._import_lines()
            if "CorrelationRegistry" in ln or "HeatExchangerModelRegistry" in ln
        ]
        assert not hits, f"Registry import found: {hits}"

    def test_no_system_state_import(self):
        """Item 31: no SystemState import in readonly_state_bridge module."""
        hits = [ln for ln in self._import_lines() if "SystemState" in ln]
        assert not hits, f"SystemState import found: {hits}"

    def test_no_fluid_state_import(self):
        """Item 32: no FluidState import in readonly_state_bridge module."""
        hits = [ln for ln in self._import_lines() if "FluidState" in ln]
        assert not hits, f"FluidState import found: {hits}"

    def test_no_production_component_imports(self):
        """Item 33: no production component or forbidden package imports."""
        forbidden = (
            "mpl_sim.components",
            "mpl_sim.properties",
            "mpl_sim.correlations",
            "mpl_sim.calibration",
            "mpl_sim.hx_models",
        )
        lines = self._import_lines()
        for pkg in forbidden:
            hits = [ln for ln in lines if pkg in ln]
            assert not hits, f"{pkg!r} must not be imported in readonly_state_bridge: {hits}"

    def test_no_contribute_call_in_module(self):
        """Item 34: no .contribute( attribute call in readonly_state_bridge (AST)."""
        tree = self._parse_src()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "contribute":
                    raise AssertionError(
                        "Found .contribute( call in readonly_state_bridge module source"
                    )

    def test_no_def_contribute_in_module(self):
        """Item 35: no method named 'contribute' defined in readonly_state_bridge (AST)."""
        tree = self._parse_src()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "contribute":
                raise AssertionError(
                    "Found 'def contribute' in readonly_state_bridge module source"
                )

    def test_no_component_type_attribute_access(self):
        """Item 36: no .component_type attribute access (physics inference) in module (AST)."""
        tree = self._parse_src()
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "component_type":
                raise AssertionError(
                    "Found .component_type access in readonly_state_bridge module — "
                    "physics must not be inferred from component_type"
                )

    def test_no_solve_function_defined(self):
        """Item 37: no function named 'solve' defined in readonly_state_bridge (AST)."""
        tree = self._parse_src()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "solve":
                raise AssertionError("Found 'def solve' in readonly_state_bridge module source")

    def test_no_networkgraph_solve_attribute_call(self):
        """Item 37: no NetworkGraph.solve() attribute call in readonly_state_bridge (AST)."""
        tree = self._parse_src()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "solve"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "NetworkGraph"
                ):
                    raise AssertionError("Found NetworkGraph.solve() call in readonly_state_bridge")


# ---------------------------------------------------------------------------
# 38–39: Public API
# ---------------------------------------------------------------------------


class TestPublicAPI:
    def test_new_symbols_exported_from_network(self):
        """Item 38: new symbols are exported from mpl_sim.network."""
        from mpl_sim import network

        assert hasattr(network, "ReadOnlyUnknownView")
        assert hasattr(network, "ComponentUnknownView")
        assert hasattr(network, "NodeUnknownView")
        assert hasattr(network, "build_readonly_unknown_view")

    def test_symbols_individually_accessible(self):
        """Item 39: each symbol is the correct type."""
        from mpl_sim.network import (
            ComponentUnknownView as COV,
        )
        from mpl_sim.network import (
            NodeUnknownView as NOV,
        )
        from mpl_sim.network import (
            ReadOnlyUnknownView as ROV,
        )
        from mpl_sim.network import (
            build_readonly_unknown_view as BRV,
        )

        assert ROV is ReadOnlyUnknownView
        assert COV is ComponentUnknownView
        assert NOV is NodeUnknownView
        assert callable(BRV)

    def test_direct_module_import_matches_network_export(self):
        """Item 39: direct module import and package export are the same objects."""
        assert _ViewDirect is ReadOnlyUnknownView
        assert _CompViewDirect is ComponentUnknownView
        assert _NodeViewDirect is NodeUnknownView
        assert _build_direct is build_readonly_unknown_view

    def test_new_symbols_in_all(self):
        """Item 39: new symbols appear in mpl_sim.network.__all__."""
        from mpl_sim import network

        all_exports = set(network.__all__)
        assert "ReadOnlyUnknownView" in all_exports
        assert "ComponentUnknownView" in all_exports
        assert "NodeUnknownView" in all_exports
        assert "build_readonly_unknown_view" in all_exports


# ---------------------------------------------------------------------------
# 40–41: Regression
# ---------------------------------------------------------------------------


class TestRegression:
    def test_phase14g_inspection_still_reports_no_contribute_method(self):
        """Item 40: Phase 14G inspection still reports NO_CONTRIBUTE_METHOD for six classes."""
        from mpl_sim.network import ProductionComponentContractStatus

        results = inspect_known_production_component_contracts()
        assert len(results) == 6
        for r in results:
            assert (
                r.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD
            ), f"{r.class_name} unexpectedly has status {r.status!r}"

    def test_15a1_execute_still_functional(self):
        """Item 41: Block 15A.1 execute_production_bridge_contributions still works."""
        bc = _toy_binding_context_with_state_map()
        uvs = _toy_unknown_values()

        class _StubBridge:
            def produce_records(
                self, ctx: ProductionBridgeExecutionContext
            ) -> ContributionRecordSet:
                return ContributionRecordSet(
                    records=(
                        ContributionRecord(
                            component_id=_EVAP_ID,
                            name="delta_P",
                            value=1.0,
                        ),
                    )
                )

        class _StubCondBridge:
            def produce_records(
                self, ctx: ProductionBridgeExecutionContext
            ) -> ContributionRecordSet:
                return ContributionRecordSet(
                    records=(
                        ContributionRecord(
                            component_id=_COND_ID,
                            name="delta_P",
                            value=2.0,
                        ),
                    )
                )

        bridge_set = ProductionComponentBridgeSet(
            bindings=(
                ProductionComponentBridgeBinding(component_id=_EVAP_ID, bridge=_StubBridge()),
                ProductionComponentBridgeBinding(component_id=_COND_ID, bridge=_StubCondBridge()),
            )
        )
        result = execute_production_bridge_contributions(bc, bridge_set, uvs)
        assert isinstance(result, ContributionRecordSet)
        assert len(result.records) == 2

    def test_15a1_view_does_not_need_contribute(self):
        """Item 41: no method named contribute exists on new view types."""
        view = _toy_view()
        assert not hasattr(view, "contribute")
        cv = view.for_component(_EVAP_ID)
        assert not hasattr(cv, "contribute")
        nv = view.for_node(_N1_ID)
        assert not hasattr(nv, "contribute")
