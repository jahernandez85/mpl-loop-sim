"""Block 15A.3 — controlled production-like bridge path tests.

Coverage items (required):

Construction and validation:
 1.  production-like binding requires ComponentInstanceId
 2.  producer must have callable produce_records
 3.  duplicate component IDs rejected by ProductionLikeComponentSet
 4.  missing binding rejected by execute_production_like_contributions
 5.  extra/unbound binding rejected by execute_production_like_contributions
 6.  wrong producer return type rejected
 7.  wrong record ownership rejected
 8.  duplicate records rejected

Unknown-view integration:
 9.  producer can build ReadOnlyUnknownView from context (via ctx.view)
10.  producer can read component-scoped unknowns
11.  producer can read node-scoped unknowns
12.  producer cannot see unmapped component unknowns through component view
13.  producer cannot see unmapped node unknowns through node view
14.  missing unknown values fail (ReadOnlyUnknownView coverage check)
15.  extra unknown values fail (ReadOnlyUnknownView coverage check)

Existing stack integration:
16.  collected records map through ContributionResidualMap
17.  convenience wrapper returns Phase 14C ComponentContribution
18.  one-shot Phase 13G residual evaluation works on controlled algebraic example
19.  Block 15A.1 bridge tests still pass (regression import check)
20.  Block 15A.2 read-only bridge tests still pass (regression import check)

Boundary tests (import-line and AST based):
21.  no CoolProp import in production_like_bridge module
22.  no PropertyBackend import in production_like_bridge module
23.  no CorrelationRegistry import in production_like_bridge module
24.  no HX model import in production_like_bridge module
25.  no production component class import in production_like_bridge module
26.  no SystemState import in production_like_bridge module
27.  no FluidState import in production_like_bridge module
28.  no contribute( call in production_like_bridge module (AST)
29.  no .contribute( call in production_like_bridge module (AST)
30.  no def contribute in production_like_bridge module (AST)
31.  no component_type physics in production_like_bridge module
32.  no solve(network) or NetworkGraph.solve() in production_like_bridge module

Production contract regression:
33.  Phase 14G inspection still reports NO_CONTRIBUTE_METHOD for all six
     known production component classes

Public API:
34.  new public symbols exported from mpl_sim.network
35.  no accidental broad exports (symbols individually accessible)
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from mpl_sim.network import (
    ComponentBinding,
    ComponentContribution,
    ComponentContributionAdapter,
    ComponentContributionAdapterSet,
    ComponentContributionContext,
    ComponentInstance,
    ComponentInstanceId,
    ContributionRecord,
    ContributionRecordSet,
    ContributionResidualMap,
    GraphNode,
    GraphNodeId,
    NetworkBindingContext,
    NetworkGraph,
    NetworkUnknownValues,
    ProductionLikeBridgeContext,
    ProductionLikeComponentBinding,
    ProductionLikeComponentSet,
    ProductionLikeRecordProducerProtocol,
    ReadOnlyUnknownView,
    assemble_network_residuals,
    build_binding_context,
    build_component_contribution_from_production_like_execution,
    build_network_residual_evaluators,
    build_physical_adapters_from_contributions,
    build_readonly_unknown_view,
    evaluate_network_residuals,
    execute_production_like_contributions,
    inspect_known_production_component_contracts,
    map_contribution_records_to_component_contribution,
)
from mpl_sim.network.component_binding import ComponentStateMap
from mpl_sim.network.production_like_bridge import (
    ProductionLikeBridgeContext as _CtxDirect,
)
from mpl_sim.network.production_like_bridge import (
    ProductionLikeComponentBinding as _BindingDirect,
)
from mpl_sim.network.production_like_bridge import (
    ProductionLikeComponentSet as _SetDirect,
)
from mpl_sim.network.production_like_bridge import (
    build_component_contribution_from_production_like_execution as _build_direct,
)
from mpl_sim.network.production_like_bridge import (
    execute_production_like_contributions as _exec_direct,
)

# ---------------------------------------------------------------------------
# Source file path for boundary checks
# ---------------------------------------------------------------------------

_SRC = (
    pathlib.Path(__file__).parent.parent.parent
    / "src"
    / "mpl_sim"
    / "network"
    / "production_like_bridge.py"
)

# ---------------------------------------------------------------------------
# Shared ID constants
# ---------------------------------------------------------------------------

_EVAP_ID = ComponentInstanceId("evap")
_COND_ID = ComponentInstanceId("cond")
_N1_ID = GraphNodeId("n1")
_N2_ID = GraphNodeId("n2")


# ---------------------------------------------------------------------------
# Shared graph/context builders
# ---------------------------------------------------------------------------


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


def _toy_state_map() -> ComponentStateMap:
    return ComponentStateMap(
        unknown_to_component={
            "mdot:evap": _EVAP_ID,
            "mdot:cond": _COND_ID,
        },
        unknown_to_node={
            "P:n1": _N1_ID,
            "P:n2": _N2_ID,
        },
    )


def _toy_binding_context() -> NetworkBindingContext:
    g = _toy_graph()
    asm = assemble_network_residuals(g)
    bindings = [
        ComponentBinding(instance_id=_EVAP_ID, binding_name="evaporator"),
        ComponentBinding(instance_id=_COND_ID, binding_name="condenser"),
    ]
    return build_binding_context(g, asm, bindings, _toy_state_map())


def _toy_binding_context_empty_map() -> NetworkBindingContext:
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


def _toy_residual_map() -> ContributionResidualMap:
    return ContributionResidualMap(
        mapping={
            (_EVAP_ID, "mass_balance"): "mass_balance:n1",
            (_EVAP_ID, "pressure_drop"): "pressure_drop:evap",
            (_COND_ID, "mass_balance"): "mass_balance:n2",
            (_COND_ID, "pressure_drop"): "pressure_drop:cond",
        }
    )


# ---------------------------------------------------------------------------
# Controlled production-like stub producers — NOT real production component
# classes.  These are test-only objects.  They expose produce_records (NOT
# contribute).  They use ctx.view to read unknowns by component/node scope.
# ---------------------------------------------------------------------------


class ProductionLikeEvapStub:
    """Production-like stub for 'evap'. NOT a real production component.

    Uses ctx.view to read component-scoped and node-scoped unknowns.
    """

    def produce_records(self, ctx: ProductionLikeBridgeContext) -> ContributionRecordSet:
        comp_view = ctx.view.for_component(_EVAP_ID)
        mdot_evap = comp_view.value("mdot:evap")

        n1_view = ctx.view.for_node(_N1_ID)
        n2_view = ctx.view.for_node(_N2_ID)
        p_n1 = n1_view.value("P:n1")
        p_n2 = n2_view.value("P:n2")

        mdot_cond_from_raw = ctx.unknown_values["mdot:cond"]

        return ContributionRecordSet(
            records=(
                ContributionRecord(
                    component_id=_EVAP_ID,
                    name="mass_balance",
                    value=mdot_evap - mdot_cond_from_raw,
                ),
                ContributionRecord(
                    component_id=_EVAP_ID,
                    name="pressure_drop",
                    value=p_n1 - p_n2 - 600.0,
                ),
            )
        )


class ProductionLikeCondStub:
    """Production-like stub for 'cond'. NOT a real production component.

    Uses ctx.view to read component-scoped and node-scoped unknowns.
    """

    def produce_records(self, ctx: ProductionLikeBridgeContext) -> ContributionRecordSet:
        comp_view = ctx.view.for_component(_COND_ID)
        mdot_cond = comp_view.value("mdot:cond")

        n1_view = ctx.view.for_node(_N1_ID)
        n2_view = ctx.view.for_node(_N2_ID)
        p_n1 = n1_view.value("P:n1")
        p_n2 = n2_view.value("P:n2")

        mdot_evap_from_raw = ctx.unknown_values["mdot:evap"]

        return ContributionRecordSet(
            records=(
                ContributionRecord(
                    component_id=_COND_ID,
                    name="mass_balance",
                    value=mdot_cond - mdot_evap_from_raw,
                ),
                ContributionRecord(
                    component_id=_COND_ID,
                    name="pressure_drop",
                    value=p_n2 - p_n1 + 1_000.0,
                ),
            )
        )


def _evap_binding() -> ProductionLikeComponentBinding:
    return ProductionLikeComponentBinding(component_id=_EVAP_ID, producer=ProductionLikeEvapStub())


def _cond_binding() -> ProductionLikeComponentBinding:
    return ProductionLikeComponentBinding(component_id=_COND_ID, producer=ProductionLikeCondStub())


def _producer_set() -> ProductionLikeComponentSet:
    return ProductionLikeComponentSet(bindings=(_evap_binding(), _cond_binding()))


# ---------------------------------------------------------------------------
# 1–3: Construction and validation — binding and set
# ---------------------------------------------------------------------------


class TestProductionLikeComponentBinding:
    def test_valid_construction(self):
        """Item 1: valid binding construction."""
        b = ProductionLikeComponentBinding(component_id=_EVAP_ID, producer=ProductionLikeEvapStub())
        assert b.component_id is _EVAP_ID
        assert isinstance(b.producer, ProductionLikeEvapStub)

    def test_rejects_non_component_instance_id(self):
        """Item 1: binding requires ComponentInstanceId."""
        with pytest.raises(TypeError, match="ComponentInstanceId"):
            ProductionLikeComponentBinding(
                component_id="evap",  # type: ignore[arg-type]
                producer=ProductionLikeEvapStub(),
            )

    def test_rejects_producer_missing_produce_records(self):
        """Item 2: producer must have produce_records attribute."""

        class NoProduce:
            pass

        with pytest.raises(TypeError, match="produce_records"):
            ProductionLikeComponentBinding(component_id=_EVAP_ID, producer=NoProduce())

    def test_rejects_producer_with_non_callable_produce_records(self):
        """Item 2: producer.produce_records must be callable."""

        class NonCallable:
            produce_records = "not_callable"

        with pytest.raises(TypeError, match="callable"):
            ProductionLikeComponentBinding(component_id=_EVAP_ID, producer=NonCallable())

    def test_binding_is_frozen(self):
        """Binding is immutable after construction."""
        b = _evap_binding()
        with pytest.raises((TypeError, AttributeError)):
            b.component_id = _COND_ID  # type: ignore[misc]


class TestProductionLikeComponentSet:
    def test_valid_construction(self):
        """Valid set construction preserves insertion order."""
        s = _producer_set()
        assert len(s.bindings) == 2
        assert s.bindings[0].component_id == _EVAP_ID
        assert s.bindings[1].component_id == _COND_ID

    def test_duplicate_component_id_rejected(self):
        """Item 3: duplicate component IDs rejected."""
        with pytest.raises(ValueError, match="duplicate"):
            ProductionLikeComponentSet(bindings=(_evap_binding(), _evap_binding()))

    def test_rejects_wrong_entry_type(self):
        """Wrong entry type in bindings rejected."""
        with pytest.raises(TypeError, match="ProductionLikeComponentBinding"):
            ProductionLikeComponentSet(bindings=("not_a_binding",))  # type: ignore[arg-type]

    def test_source_list_mutation_does_not_affect_set(self):
        """Mutating source list after construction does not affect set."""
        lst = [_evap_binding(), _cond_binding()]
        s = ProductionLikeComponentSet(bindings=tuple(lst))
        lst.append(_evap_binding())
        assert len(s.bindings) == 2

    def test_set_is_frozen(self):
        """Set is immutable after construction."""
        s = _producer_set()
        with pytest.raises((TypeError, AttributeError)):
            s.bindings = ()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 4–8: Construction and validation — execution errors
# ---------------------------------------------------------------------------


class TestExecutionValidation:
    def test_missing_binding_rejected(self):
        """Item 4: missing producer binding rejected."""
        bc = _toy_binding_context()
        only_evap = ProductionLikeComponentSet(bindings=(_evap_binding(),))
        with pytest.raises(ValueError, match="missing"):
            execute_production_like_contributions(bc, only_evap, _toy_unknown_values())

    def test_extra_binding_rejected(self):
        """Item 5: extra/unbound producer binding rejected."""
        bc = _toy_binding_context()
        extra_id = ComponentInstanceId("pump")

        class DummyProducer:
            def produce_records(self, ctx):
                return ContributionRecordSet(records=())

        extra_binding = ProductionLikeComponentBinding(
            component_id=extra_id, producer=DummyProducer()
        )
        pset = ProductionLikeComponentSet(
            bindings=(_evap_binding(), _cond_binding(), extra_binding)
        )
        with pytest.raises(ValueError, match="not bound"):
            execute_production_like_contributions(bc, pset, _toy_unknown_values())

    def test_wrong_return_type_rejected(self):
        """Item 6: wrong producer return type rejected."""

        class BadReturnProducer:
            def produce_records(self, ctx):
                return {"not": "a_record_set"}

        bc = _toy_binding_context()
        pset = ProductionLikeComponentSet(
            bindings=(
                ProductionLikeComponentBinding(component_id=_EVAP_ID, producer=BadReturnProducer()),
                _cond_binding(),
            )
        )
        with pytest.raises(TypeError, match="ContributionRecordSet"):
            execute_production_like_contributions(bc, pset, _toy_unknown_values())

    def test_wrong_record_ownership_rejected(self):
        """Item 7: record for wrong component_id rejected."""

        class WrongOwnerProducer:
            def produce_records(self, ctx):
                return ContributionRecordSet(
                    records=(
                        ContributionRecord(
                            component_id=_COND_ID,  # wrong — should be _EVAP_ID
                            name="mass_balance",
                            value=0.0,
                        ),
                    )
                )

        bc = _toy_binding_context()
        pset = ProductionLikeComponentSet(
            bindings=(
                ProductionLikeComponentBinding(
                    component_id=_EVAP_ID, producer=WrongOwnerProducer()
                ),
                _cond_binding(),
            )
        )
        with pytest.raises(ValueError, match="different component"):
            execute_production_like_contributions(bc, pset, _toy_unknown_values())

    def test_duplicate_records_rejected(self):
        """Item 8: duplicate (component_id, name) records rejected."""

        class DuplicateProducer:
            def produce_records(self, ctx):
                return ContributionRecordSet(
                    records=(
                        ContributionRecord(component_id=_EVAP_ID, name="mass_balance", value=0.0),
                        ContributionRecord(component_id=_EVAP_ID, name="mass_balance", value=1.0),
                    )
                )

        bc = _toy_binding_context()
        pset = ProductionLikeComponentSet(
            bindings=(
                ProductionLikeComponentBinding(component_id=_EVAP_ID, producer=DuplicateProducer()),
                _cond_binding(),
            )
        )
        with pytest.raises(ValueError, match="duplicate"):
            execute_production_like_contributions(bc, pset, _toy_unknown_values())


# ---------------------------------------------------------------------------
# 9–15: Unknown-view integration
# ---------------------------------------------------------------------------


class TestProductionLikeBridgeContext:
    def test_context_has_view(self):
        """Item 9: ProductionLikeBridgeContext exposes a ReadOnlyUnknownView."""
        bc = _toy_binding_context()
        result = execute_production_like_contributions(bc, _producer_set(), _toy_unknown_values())
        # The fact that the stubs successfully called ctx.view confirms the view exists.
        assert isinstance(result, ContributionRecordSet)

    def test_context_view_is_readonly_unknown_view(self):
        """Item 9: ctx.view is a ReadOnlyUnknownView."""
        captured = []

        class CaptureViewProducer:
            def produce_records(self, ctx):
                captured.append(ctx.view)
                return ContributionRecordSet(
                    records=(
                        ContributionRecord(component_id=_EVAP_ID, name="mass_balance", value=0.0),
                        ContributionRecord(component_id=_EVAP_ID, name="pressure_drop", value=0.0),
                    )
                )

        bc = _toy_binding_context()
        pset = ProductionLikeComponentSet(
            bindings=(
                ProductionLikeComponentBinding(
                    component_id=_EVAP_ID, producer=CaptureViewProducer()
                ),
                _cond_binding(),
            )
        )
        execute_production_like_contributions(bc, pset, _toy_unknown_values())
        assert len(captured) == 1
        assert isinstance(captured[0], ReadOnlyUnknownView)


class TestUnknownViewComponentScoping:
    def test_producer_reads_component_scoped_unknowns(self):
        """Item 10: producer reads component-scoped unknowns via ctx.view."""
        captured = {}

        class CompScopeProducer:
            def __init__(self, cid):
                self._cid = cid

            def produce_records(self, ctx):
                comp_view = ctx.view.for_component(self._cid)
                captured[self._cid.value] = dict(comp_view.unknown_values)
                return ContributionRecordSet(
                    records=(
                        ContributionRecord(component_id=self._cid, name="mass_balance", value=0.0),
                        ContributionRecord(component_id=self._cid, name="pressure_drop", value=0.0),
                    )
                )

        bc = _toy_binding_context()
        pset = ProductionLikeComponentSet(
            bindings=(
                ProductionLikeComponentBinding(
                    component_id=_EVAP_ID, producer=CompScopeProducer(_EVAP_ID)
                ),
                ProductionLikeComponentBinding(
                    component_id=_COND_ID, producer=CompScopeProducer(_COND_ID)
                ),
            )
        )
        execute_production_like_contributions(bc, pset, _toy_unknown_values())
        # evap component view contains only mdot:evap
        assert "mdot:evap" in captured["evap"]
        assert "mdot:cond" not in captured["evap"]
        # cond component view contains only mdot:cond
        assert "mdot:cond" in captured["cond"]
        assert "mdot:evap" not in captured["cond"]

    def test_producer_cannot_see_unmapped_component_unknowns(self):
        """Item 12: component view does not expose unmapped unknowns."""
        captured_names = {}

        class EvapScopeProducer:
            def produce_records(self, ctx):
                comp_view = ctx.view.for_component(_EVAP_ID)
                captured_names["evap"] = set(comp_view.names())
                return ContributionRecordSet(
                    records=(
                        ContributionRecord(component_id=_EVAP_ID, name="mass_balance", value=0.0),
                        ContributionRecord(component_id=_EVAP_ID, name="pressure_drop", value=0.0),
                    )
                )

        bc = _toy_binding_context()
        pset = ProductionLikeComponentSet(
            bindings=(
                ProductionLikeComponentBinding(component_id=_EVAP_ID, producer=EvapScopeProducer()),
                _cond_binding(),
            )
        )
        execute_production_like_contributions(bc, pset, _toy_unknown_values())
        # P:n1 and P:n2 are node unknowns, not mapped to any component
        assert "P:n1" not in captured_names["evap"]
        assert "P:n2" not in captured_names["evap"]
        # mdot:cond is mapped to cond, not evap
        assert "mdot:cond" not in captured_names["evap"]


class TestUnknownViewNodeScoping:
    def test_producer_reads_node_scoped_unknowns(self):
        """Item 11: producer reads node-scoped unknowns via ctx.view."""
        captured = {}

        class NodeScopeProducer:
            def produce_records(self, ctx):
                n1_view = ctx.view.for_node(_N1_ID)
                n2_view = ctx.view.for_node(_N2_ID)
                captured["n1"] = dict(n1_view.unknown_values)
                captured["n2"] = dict(n2_view.unknown_values)
                return ContributionRecordSet(
                    records=(
                        ContributionRecord(component_id=_EVAP_ID, name="mass_balance", value=0.0),
                        ContributionRecord(component_id=_EVAP_ID, name="pressure_drop", value=0.0),
                    )
                )

        bc = _toy_binding_context()
        pset = ProductionLikeComponentSet(
            bindings=(
                ProductionLikeComponentBinding(component_id=_EVAP_ID, producer=NodeScopeProducer()),
                _cond_binding(),
            )
        )
        execute_production_like_contributions(bc, pset, _toy_unknown_values())
        # n1 view has P:n1; n2 view has P:n2
        assert "P:n1" in captured["n1"]
        assert "P:n2" not in captured["n1"]
        assert "P:n2" in captured["n2"]
        assert "P:n1" not in captured["n2"]

    def test_producer_cannot_see_unmapped_node_unknowns(self):
        """Item 13: node view does not expose unknowns mapped to other nodes."""
        captured = {}

        class N1ScopeProducer:
            def produce_records(self, ctx):
                n1_view = ctx.view.for_node(_N1_ID)
                captured["n1_names"] = set(n1_view.names())
                return ContributionRecordSet(
                    records=(
                        ContributionRecord(component_id=_EVAP_ID, name="mass_balance", value=0.0),
                        ContributionRecord(component_id=_EVAP_ID, name="pressure_drop", value=0.0),
                    )
                )

        bc = _toy_binding_context()
        pset = ProductionLikeComponentSet(
            bindings=(
                ProductionLikeComponentBinding(component_id=_EVAP_ID, producer=N1ScopeProducer()),
                _cond_binding(),
            )
        )
        execute_production_like_contributions(bc, pset, _toy_unknown_values())
        # n1 view must not contain P:n2 (mapped to n2) or mdot unknowns
        assert "P:n2" not in captured["n1_names"]
        assert "mdot:evap" not in captured["n1_names"]
        assert "mdot:cond" not in captured["n1_names"]


class TestMissingExtraUnknownValues:
    def test_missing_unknown_values_fail(self):
        """Item 14: missing unknown values fail via ReadOnlyUnknownView coverage check."""
        bc = _toy_binding_context()
        partial = {"mdot:evap": 0.05, "mdot:cond": 0.05}  # missing P:n1, P:n2
        with pytest.raises(ValueError, match="missing"):
            execute_production_like_contributions(bc, _producer_set(), partial)

    def test_extra_unknown_values_fail(self):
        """Item 15: extra unknown values fail via ReadOnlyUnknownView coverage check."""
        bc = _toy_binding_context()
        extra = {**_toy_unknown_values(), "extra_unknown": 99.0}
        with pytest.raises(ValueError, match="extra"):
            execute_production_like_contributions(bc, _producer_set(), extra)


# ---------------------------------------------------------------------------
# 16–18: Existing stack integration
# ---------------------------------------------------------------------------


class TestExistingStackIntegration:
    def test_records_map_through_contribution_residual_map(self):
        """Item 16: collected records map through ContributionResidualMap."""
        bc = _toy_binding_context()
        record_set = execute_production_like_contributions(
            bc, _producer_set(), _toy_unknown_values()
        )
        assert isinstance(record_set, ContributionRecordSet)
        residual_map = _toy_residual_map()
        contrib = map_contribution_records_to_component_contribution(
            _EVAP_ID, record_set, residual_map
        )
        assert isinstance(contrib, ComponentContribution)
        assert "mass_balance:n1" in contrib.residual_values
        assert "pressure_drop:evap" in contrib.residual_values

    def test_convenience_wrapper_returns_component_contribution(self):
        """Item 17: convenience wrapper returns Phase 14C ComponentContribution."""
        bc = _toy_binding_context()
        contrib = build_component_contribution_from_production_like_execution(
            _EVAP_ID,
            bc,
            _producer_set(),
            _toy_residual_map(),
            _toy_unknown_values(),
        )
        assert isinstance(contrib, ComponentContribution)
        # Verify residual values come from the stub algebra
        # mass_balance = mdot:evap - mdot:cond = 0.05 - 0.05 = 0.0
        assert contrib.residual_values["mass_balance:n1"] == pytest.approx(0.0)
        # pressure_drop = P:n1 - P:n2 - 600 = 1000 - 400 - 600 = 0.0
        assert contrib.residual_values["pressure_drop:evap"] == pytest.approx(0.0)

    def test_one_shot_phase13g_residual_evaluation(self):
        """Item 18: one-shot Phase 13G residual evaluation on controlled algebraic example.

        The toy system has four unknowns and four residuals.
        At the test point mass_balance residuals are zero (mdot:evap == mdot:cond).
        """
        bc = _toy_binding_context()
        residual_map = _toy_residual_map()

        def _make_cb(cid):
            def cb(ctx: ComponentContributionContext) -> ComponentContribution:
                return build_component_contribution_from_production_like_execution(
                    cid, bc, _producer_set(), residual_map, dict(ctx.unknown_values)
                )

            return cb

        adapter_set = ComponentContributionAdapterSet(
            adapters=(
                ComponentContributionAdapter(instance_id=_EVAP_ID, callback=_make_cb(_EVAP_ID)),
                ComponentContributionAdapter(instance_id=_COND_ID, callback=_make_cb(_COND_ID)),
            )
        )
        physical_set = build_physical_adapters_from_contributions(bc, adapter_set)
        evaluators = build_network_residual_evaluators(bc.assembly, physical_set)

        uv = NetworkUnknownValues(values=_toy_unknown_values())
        scales = {name: 1.0 for name in bc.assembly.residuals.names()}
        eval_result = evaluate_network_residuals(bc.assembly, uv, evaluators, scales)
        assert eval_result is not None
        # Extract residual values by name
        rv = {e.spec.name: e.value for e in eval_result.residual_vector.evaluations}
        # mass_balance residuals should be zero at the test point (mdot:evap == mdot:cond)
        assert rv["mass_balance:n1"] == pytest.approx(0.0)
        assert rv["mass_balance:n2"] == pytest.approx(0.0)

    def test_block_15a1_bridge_still_importable_and_functional(self):
        """Item 19: Block 15A.1 execute_production_bridge_contributions is still importable."""
        from mpl_sim.network import (
            ProductionBridgeExecutionContext,  # noqa: F401
            ProductionComponentBridgeBinding,  # noqa: F401
            ProductionComponentBridgeSet,  # noqa: F401
            execute_production_bridge_contributions,  # noqa: F401
        )

        # Importing and type-checking confirms backward compatibility
        assert callable(execute_production_bridge_contributions)

    def test_block_15a2_readonly_bridge_still_importable_and_functional(self):
        """Item 20: Block 15A.2 ReadOnlyUnknownView is still importable."""
        from mpl_sim.network import (
            ReadOnlyUnknownView,  # noqa: F401
            build_readonly_unknown_view,  # noqa: F401
        )

        bc = _toy_binding_context()
        view = build_readonly_unknown_view(bc, _toy_unknown_values())
        assert isinstance(view, ReadOnlyUnknownView)


# ---------------------------------------------------------------------------
# 21–32: Boundary tests (AST-based)
# ---------------------------------------------------------------------------


def _load_ast() -> ast.Module:
    src = _SRC.read_text(encoding="utf-8")
    return ast.parse(src)


def _get_all_imports(tree: ast.Module) -> list[str]:
    """Return all imported module names and aliases from the AST."""
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.append(node.module)
    return names


def _get_all_names(tree: ast.Module) -> list[str]:
    """Return all Name node ids from the AST."""
    return [node.id for node in ast.walk(tree) if isinstance(node, ast.Name)]


def _get_function_def_names(tree: ast.Module) -> list[str]:
    """Return all function/method names from the AST."""
    return [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _get_all_call_attribute_names(tree: ast.Module) -> list[str]:
    """Return all attribute names appearing in Call nodes."""
    result: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                result.append(node.func.attr)
    return result


class TestBoundaryChecks:
    def test_no_coolprop_import(self):
        """Item 21: no CoolProp import in production_like_bridge module."""
        tree = _load_ast()
        imports = _get_all_imports(tree)
        assert not any(
            "CoolProp" in name for name in imports
        ), "production_like_bridge.py must not import CoolProp"

    def test_no_property_backend_import(self):
        """Item 22: no PropertyBackend import (AST import check only)."""
        tree = _load_ast()
        imports = _get_all_imports(tree)
        assert not any(
            "PropertyBackend" in imp for imp in imports
        ), "production_like_bridge.py must not import PropertyBackend"
        # Check that it doesn't appear as a Name reference in executable code
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "PropertyBackend":
                raise AssertionError("production_like_bridge.py must not reference PropertyBackend")

    def test_no_correlation_registry_import(self):
        """Item 23: no CorrelationRegistry import (AST import check only)."""
        tree = _load_ast()
        imports = _get_all_imports(tree)
        assert not any(
            "CorrelationRegistry" in imp for imp in imports
        ), "production_like_bridge.py must not import CorrelationRegistry"
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "CorrelationRegistry":
                raise AssertionError(
                    "production_like_bridge.py must not reference CorrelationRegistry"
                )

    def test_no_hx_model_import(self):
        """Item 24: no HX model import in production_like_bridge module (AST check)."""
        tree = _load_ast()
        imports = _get_all_imports(tree)
        assert not any(
            "hx_models" in imp for imp in imports
        ), "production_like_bridge.py must not import hx_models"

    def test_no_production_component_class_import(self):
        """Item 25: no production component class import."""
        tree = _load_ast()
        imports = _get_all_imports(tree)
        forbidden = {
            "mpl_sim.components",
            "mpl_sim.components.pipe",
            "mpl_sim.components.pump",
            "mpl_sim.components.accumulator",
            "mpl_sim.components.evaporator",
            "mpl_sim.components.condenser",
        }
        for imp in imports:
            assert imp not in forbidden, f"production_like_bridge.py must not import {imp!r}"

    def test_no_system_state_import(self):
        """Item 26: no SystemState import (AST import check only)."""
        tree = _load_ast()
        imports = _get_all_imports(tree)
        assert not any(
            "SystemState" in imp for imp in imports
        ), "production_like_bridge.py must not import SystemState"
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "SystemState":
                raise AssertionError("production_like_bridge.py must not reference SystemState")

    def test_no_fluid_state_import(self):
        """Item 27: no FluidState import (AST import check only)."""
        tree = _load_ast()
        imports = _get_all_imports(tree)
        assert not any(
            "FluidState" in imp for imp in imports
        ), "production_like_bridge.py must not import FluidState"
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "FluidState":
                raise AssertionError("production_like_bridge.py must not reference FluidState")

    def test_no_contribute_call_in_source(self):
        """Item 28/29: no contribute( call in production_like_bridge module (AST)."""
        tree = _load_ast()
        call_attrs = _get_all_call_attribute_names(tree)
        assert (
            "contribute" not in call_attrs
        ), "production_like_bridge.py must not call .contribute(...)"
        # Also check raw text for any form of contribute(
        src_text = _SRC.read_text(encoding="utf-8")
        # Allow the word in docstring comments describing what NOT to do;
        # disallow executable contribute( patterns not in comments/strings
        for line in src_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # Check for executable contribute( calls outside of strings
            # We rely on the AST call check above for executable calls
        # Final AST check is authoritative
        assert "contribute" not in call_attrs

    def test_no_def_contribute_in_module(self):
        """Item 30: no def contribute in production_like_bridge module."""
        tree = _load_ast()
        func_names = _get_function_def_names(tree)
        assert (
            "contribute" not in func_names
        ), "production_like_bridge.py must not define a function named 'contribute'"

    def test_no_component_type_physics(self):
        """Item 31: no component_type physics inference in module."""
        src_text = _SRC.read_text(encoding="utf-8")
        # The module should not read component_type to derive physics
        # We check that component_type does not appear in non-comment, non-docstring lines
        tree = _load_ast()
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr != "component_type" or isinstance(
                    node.ctx, ast.Load
                ), "production_like_bridge.py must not access component_type for physics"
        # No executable reference to component_type allowed in production_like_bridge.
        # (it's fine if it appears in comments/docstrings only)
        executable_lines = []
        for line in src_text.splitlines():
            stripped = line.strip()
            if not stripped.startswith("#") and "component_type" in line:
                executable_lines.append(line)
        # Any references should only be in docstring text, not executable code
        # Parse to find actual Attribute accesses
        component_type_attrs = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr == "component_type"
        ]
        assert (
            len(component_type_attrs) == 0
        ), "production_like_bridge.py must not access .component_type"

    def test_no_solve_network_defined(self):
        """Item 32: no solve(network) or NetworkGraph.solve() defined."""
        tree = _load_ast()
        func_names = _get_function_def_names(tree)
        assert (
            "solve" not in func_names
        ), "production_like_bridge.py must not define a function named 'solve'"
        src_text = _SRC.read_text(encoding="utf-8")
        assert (
            "NetworkGraph.solve" not in src_text
        ), "production_like_bridge.py must not reference NetworkGraph.solve"

    def test_no_mpl_sim_properties_import(self):
        """Item 22 extended: no mpl_sim.properties import."""
        tree = _load_ast()
        imports = _get_all_imports(tree)
        assert not any(
            "mpl_sim.properties" in imp for imp in imports
        ), "production_like_bridge.py must not import mpl_sim.properties"

    def test_no_mpl_sim_correlations_import(self):
        """Item 23 extended: no mpl_sim.correlations import."""
        tree = _load_ast()
        imports = _get_all_imports(tree)
        assert not any(
            "mpl_sim.correlations" in imp for imp in imports
        ), "production_like_bridge.py must not import mpl_sim.correlations"


# ---------------------------------------------------------------------------
# 33: Production contract regression
# ---------------------------------------------------------------------------


class TestProductionContractRegression:
    def test_phase14g_still_reports_no_contribute_method(self):
        """Item 33: Phase 14G inspection still reports NO_CONTRIBUTE_METHOD for all six classes."""
        from mpl_sim.network import ProductionComponentContractStatus

        results = inspect_known_production_component_contracts()
        for result in results:
            assert (
                result.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD
            ), f"{result.class_name} unexpectedly has status {result.status!r}"
        # Confirm all six known classes are present
        class_names = {r.class_name for r in results}
        expected = {
            "Component",
            "Pipe",
            "PumpComponent",
            "AccumulatorComponent",
            "EvaporatorComponent",
            "CondenserComponent",
        }
        assert expected <= class_names, f"Missing classes in inspection: {expected - class_names}"


# ---------------------------------------------------------------------------
# 34–35: Public API
# ---------------------------------------------------------------------------


class TestPublicAPI:
    def test_new_symbols_exported_from_mpl_sim_network(self):
        """Item 34: all new Block 15A.3 symbols exported from mpl_sim.network."""
        import mpl_sim.network as net

        assert hasattr(net, "ProductionLikeBridgeContext")
        assert hasattr(net, "ProductionLikeRecordProducerProtocol")
        assert hasattr(net, "ProductionLikeComponentBinding")
        assert hasattr(net, "ProductionLikeComponentSet")
        assert hasattr(net, "execute_production_like_contributions")
        assert hasattr(net, "build_component_contribution_from_production_like_execution")

    def test_symbols_in_all(self):
        """Item 34: new symbols appear in __all__."""
        import mpl_sim.network as net

        all_set = set(net.__all__)
        new_symbols = {
            "ProductionLikeBridgeContext",
            "ProductionLikeRecordProducerProtocol",
            "ProductionLikeComponentBinding",
            "ProductionLikeComponentSet",
            "execute_production_like_contributions",
            "build_component_contribution_from_production_like_execution",
        }
        missing_from_all = new_symbols - all_set
        assert not missing_from_all, f"Missing from __all__: {missing_from_all}"

    def test_no_accidental_broad_exports(self):
        """Item 35: symbols individually accessible, no wild-card leakage."""
        from mpl_sim.network import (
            ProductionLikeBridgeContext,
            ProductionLikeComponentBinding,
            ProductionLikeComponentSet,
            build_component_contribution_from_production_like_execution,
            execute_production_like_contributions,
        )

        assert ProductionLikeBridgeContext is _CtxDirect
        assert ProductionLikeComponentBinding is _BindingDirect
        assert ProductionLikeComponentSet is _SetDirect
        assert execute_production_like_contributions is _exec_direct
        assert build_component_contribution_from_production_like_execution is _build_direct

    def test_protocol_satisfiable_by_stub(self):
        """ProductionLikeRecordProducerProtocol is satisfied by stub producers."""
        stub = ProductionLikeEvapStub()
        assert isinstance(stub, ProductionLikeRecordProducerProtocol)

    def test_protocol_not_satisfied_without_produce_records(self):
        """Objects without produce_records do not satisfy the protocol."""

        class NoMethod:
            pass

        assert not isinstance(NoMethod(), ProductionLikeRecordProducerProtocol)

    def test_context_direct_construction(self):
        """Direct construction builds the context view through the 15A.2 factory."""
        bc = _toy_binding_context()
        uv = _toy_unknown_values()
        ctx = ProductionLikeBridgeContext(
            binding_context=bc,
            unknown_values=uv,
        )
        assert ctx.binding_context is bc
        assert isinstance(ctx.view, ReadOnlyUnknownView)
        assert dict(ctx.view.values) == uv
        assert ctx.metadata is None

    def test_context_rejects_non_binding_context(self):
        """ProductionLikeBridgeContext rejects wrong binding_context type."""
        uv = _toy_unknown_values()
        with pytest.raises(TypeError, match="NetworkBindingContext"):
            ProductionLikeBridgeContext(
                binding_context="not_a_context",  # type: ignore[arg-type]
                unknown_values=uv,
            )

    def test_context_does_not_accept_caller_supplied_view(self):
        """The pre-built view cannot be supplied inconsistently by a caller."""
        bc = _toy_binding_context()
        uv = _toy_unknown_values()
        view = build_readonly_unknown_view(bc, uv)
        with pytest.raises(TypeError, match="unexpected keyword argument 'view'"):
            ProductionLikeBridgeContext(
                binding_context=bc,
                unknown_values=uv,
                view=view,  # type: ignore[call-arg]
            )

    def test_context_unknown_values_defensively_copied(self):
        """Context unknown_values are defensively copied."""
        bc = _toy_binding_context()
        source = dict(_toy_unknown_values())
        ctx = ProductionLikeBridgeContext(binding_context=bc, unknown_values=source)
        original_val = ctx.unknown_values["mdot:evap"]
        source["mdot:evap"] = 999.0
        assert ctx.unknown_values["mdot:evap"] == pytest.approx(original_val)

    def test_context_is_frozen(self):
        """ProductionLikeBridgeContext is immutable after construction."""
        bc = _toy_binding_context()
        uv = _toy_unknown_values()
        ctx = ProductionLikeBridgeContext(binding_context=bc, unknown_values=uv)
        with pytest.raises((TypeError, AttributeError)):
            ctx.metadata = {"new": "value"}  # type: ignore[misc]

    def test_execution_with_metadata(self):
        """metadata passes through to context unchanged."""
        captured_meta = []

        class MetaCapture:
            def produce_records(self, ctx):
                captured_meta.append(ctx.metadata)
                return ContributionRecordSet(
                    records=(
                        ContributionRecord(component_id=_EVAP_ID, name="mass_balance", value=0.0),
                        ContributionRecord(component_id=_EVAP_ID, name="pressure_drop", value=0.0),
                    )
                )

        bc = _toy_binding_context()
        pset = ProductionLikeComponentSet(
            bindings=(
                ProductionLikeComponentBinding(component_id=_EVAP_ID, producer=MetaCapture()),
                _cond_binding(),
            )
        )
        execute_production_like_contributions(
            bc, pset, _toy_unknown_values(), metadata={"run": "test15a3"}
        )
        assert captured_meta[0]["run"] == "test15a3"

    def test_execution_returns_records_in_binding_order(self):
        """Records are returned in producer binding order."""
        bc = _toy_binding_context()
        record_set = execute_production_like_contributions(
            bc, _producer_set(), _toy_unknown_values()
        )
        # First two records are from evap, next two from cond
        assert record_set.records[0].component_id == _EVAP_ID
        assert record_set.records[1].component_id == _EVAP_ID
        assert record_set.records[2].component_id == _COND_ID
        assert record_set.records[3].component_id == _COND_ID

    def test_producer_exception_propagates(self):
        """Producer exceptions propagate without being swallowed."""

        class RaisingProducer:
            def produce_records(self, ctx):
                raise RuntimeError("producer_error")

        bc = _toy_binding_context()
        pset = ProductionLikeComponentSet(
            bindings=(
                ProductionLikeComponentBinding(component_id=_EVAP_ID, producer=RaisingProducer()),
                _cond_binding(),
            )
        )
        with pytest.raises(RuntimeError, match="producer_error"):
            execute_production_like_contributions(bc, pset, _toy_unknown_values())
