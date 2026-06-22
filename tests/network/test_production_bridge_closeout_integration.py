"""Block 15A.4 — Production Bridge Closeout / Existing Residual-Stack Integration.

This is the closeout test for Block 15A.

These tests prove, with a controlled end-to-end path, that explicitly supplied
production-like record producers can feed the already-existing
Phase 14D → Phase 14C → Phase 14A → Phase 13G / 13H residual stack.

This checkpoint adds NO new physics, NO new runtime modules, and NO new
production component execution. It uses only existing APIs from Block 15A.3,
Block 15A.2, Block 15A.1, and prior Phase 14D/14C/14A/13G/13H modules.

Coverage items (required):

End-to-end explicit stack:
 1. production-like producers create contribution records via ReadOnlyUnknownView
 2. records map through ContributionResidualMap per component
 3. mapped contributions become Phase 14C ComponentContribution
 4. contribution adapters wrap into ComponentContributionAdapterSet
 5. build_physical_adapters_from_contributions produces PhysicalResidualAdapterSet
 6. build_network_residual_evaluators produces NetworkResidualEvaluator tuple
 7. Phase 13G evaluates residuals at the known solution point
 8. all residuals are zero at the known algebraic solution point
 9. residual ordering matches assembly declaration order

Solver compatibility (algebraic callback solve — NOT solve(network)):
10. Phase 13H converges on the controlled algebraic problem from an off-solution
    initial guess (callback-only; no production component execution)

Regression coverage:
11. Block 15A.1 bridge APIs still importable and functional
12. Block 15A.2 read-only state bridge APIs still importable and functional
13. Block 15A.3 production-like path APIs still importable and functional
14. Phase 14G: Component reports NO_CONTRIBUTE_METHOD
15. Phase 14G: Pipe reports NO_CONTRIBUTE_METHOD
16. Phase 14G: PumpComponent reports NO_CONTRIBUTE_METHOD
17. Phase 14G: AccumulatorComponent reports NO_CONTRIBUTE_METHOD
18. Phase 14G: EvaporatorComponent reports NO_CONTRIBUTE_METHOD
19. Phase 14G: CondenserComponent reports NO_CONTRIBUTE_METHOD

Boundary tests (AST/source-level):
20. test file source: no CoolProp import
21. test file source: no PropertyBackend import
22. test file source: no CorrelationRegistry import
23. test file source: no HX model import
24. test file source: no SystemState or FluidState import
25. test file source: no '.contribute(' attribute calls
26. test file source: no 'def contribute' definitions
27. test file source: no 'component_type' physics dispatch
28. test file source: no generic network-graph solve dispatch
29. production_like_bridge module: no CoolProp import (regression from 15A.3)

Public API:
30. no new symbols in mpl_sim.network beyond the known Block 15A.3 baseline
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
    ComponentInstance,
    ComponentInstanceId,
    ContributionRecord,
    ContributionRecordSet,
    ContributionResidualMap,
    GraphNode,
    GraphNodeId,
    NetworkBindingContext,
    NetworkGraph,
    NetworkSolveConfig,
    NetworkSolveResult,
    NetworkUnknownValues,
    ProductionComponentContractStatus,
    ProductionLikeBridgeContext,
    ProductionLikeComponentBinding,
    ProductionLikeComponentSet,
    assemble_network_residuals,
    build_binding_context,
    build_component_contribution_from_production_like_execution,
    build_network_residual_evaluators,
    build_physical_adapters_from_contributions,
    evaluate_network_residuals,
    execute_production_like_contributions,
    inspect_known_production_component_contracts,
    map_contribution_records_to_component_contribution,
    solve_network_residual_problem,
)
from mpl_sim.network.component_binding import ComponentStateMap

# ---------------------------------------------------------------------------
# Source paths for boundary checks
# ---------------------------------------------------------------------------

_THIS_FILE = pathlib.Path(__file__)
_BRIDGE_SRC = (
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

# Known algebraic solution for the controlled 4-unknown, 4-residual system.
#
# The system is defined by the stub algebra below:
#   mass_balance:n1   = mdot:evap - 0.1          → zero when mdot:evap = 0.1
#   mass_balance:n2   = mdot:cond - mdot:evap     → zero when mdot:cond == mdot:evap
#   pressure_drop:evap = P:n1 - 200.0            → zero when P:n1 = 200.0
#   pressure_drop:cond = P:n2 - P:n1 + 50.0      → zero when P:n1 - P:n2 = 50.0
#
# Unique solution: {mdot:evap=0.1, mdot:cond=0.1, P:n1=200.0, P:n2=150.0}
#
# Jacobian (residuals rows, unknowns cols in assembly order) is lower-triangular
# with all diagonal = 1 → det = 1, non-singular.
_SOLUTION = {
    "mdot:evap": 0.1,
    "mdot:cond": 0.1,
    "P:n1": 200.0,
    "P:n2": 150.0,
}

# Off-solution initial guess for the Phase 13H solver test.
_INITIAL_GUESS = {
    "mdot:evap": 0.05,
    "mdot:cond": 0.08,
    "P:n1": 220.0,
    "P:n2": 180.0,
}

# Expected assembly residual order for a (n1, n2) / (evap: n1→n2, cond: n2→n1) graph.
# assemble_network_residuals declares nodes first (mass_balance), then components
# (pressure_drop), both in graph-insertion order.
_EXPECTED_RESIDUAL_ORDER = [
    "mass_balance:n1",
    "mass_balance:n2",
    "pressure_drop:evap",
    "pressure_drop:cond",
]

# ---------------------------------------------------------------------------
# Controlled production-like stub producers
#
# These are test-only controlled stubs.  They are NOT real production component
# classes.  They expose produce_records (NOT contribute).  They use ctx.view
# (ReadOnlyUnknownView) to read component-scoped and node-scoped unknowns.
# ---------------------------------------------------------------------------


class CloseoutEvapStub:
    """Controlled production-like stub for 'evap'. NOT a real production component.

    Algebra (purely algebraic, no physics):
      mass_balance   = mdot:evap - 0.1   → zero when mdot:evap = 0.1
      pressure_drop  = P:n1 - 200.0      → zero when P:n1 = 200.0

    Reads unknowns exclusively through ctx.view (ReadOnlyUnknownView):
      - mdot:evap via component-scoped view
      - P:n1 via node-scoped view for n1
    """

    def produce_records(self, ctx: ProductionLikeBridgeContext) -> ContributionRecordSet:
        comp_view = ctx.view.for_component(_EVAP_ID)
        mdot_evap = comp_view.value("mdot:evap")

        n1_view = ctx.view.for_node(_N1_ID)
        p_n1 = n1_view.value("P:n1")

        return ContributionRecordSet(
            records=(
                ContributionRecord(
                    component_id=_EVAP_ID,
                    name="mass_balance",
                    value=mdot_evap - 0.1,
                ),
                ContributionRecord(
                    component_id=_EVAP_ID,
                    name="pressure_drop",
                    value=p_n1 - 200.0,
                ),
            )
        )


class CloseoutCondStub:
    """Controlled production-like stub for 'cond'. NOT a real production component.

    Algebra (purely algebraic, no physics):
      mass_balance   = mdot:cond - mdot:evap     → zero when mdot:cond == mdot:evap
      pressure_drop  = P:n2 - P:n1 + 50.0       → zero when P:n1 - P:n2 = 50.0

    Reads mdot:cond via component-scoped view; P:n1, P:n2 via node-scoped views;
    mdot:evap directly from ctx.unknown_values (raw map).
    """

    def produce_records(self, ctx: ProductionLikeBridgeContext) -> ContributionRecordSet:
        comp_view = ctx.view.for_component(_COND_ID)
        mdot_cond = comp_view.value("mdot:cond")

        mdot_evap = ctx.unknown_values["mdot:evap"]

        n1_view = ctx.view.for_node(_N1_ID)
        n2_view = ctx.view.for_node(_N2_ID)
        p_n1 = n1_view.value("P:n1")
        p_n2 = n2_view.value("P:n2")

        return ContributionRecordSet(
            records=(
                ContributionRecord(
                    component_id=_COND_ID,
                    name="mass_balance",
                    value=mdot_cond - mdot_evap,
                ),
                ContributionRecord(
                    component_id=_COND_ID,
                    name="pressure_drop",
                    value=p_n2 - p_n1 + 50.0,
                ),
            )
        )


# ---------------------------------------------------------------------------
# Shared graph / context builders
# ---------------------------------------------------------------------------


def _build_graph() -> NetworkGraph:
    return NetworkGraph(
        nodes=[GraphNode(node_id=_N1_ID), GraphNode(node_id=_N2_ID)],
        instances=[
            ComponentInstance(
                instance_id=_EVAP_ID,
                component_type="stub_evap",
                inlet_node=_N1_ID,
                outlet_node=_N2_ID,
            ),
            ComponentInstance(
                instance_id=_COND_ID,
                component_type="stub_cond",
                inlet_node=_N2_ID,
                outlet_node=_N1_ID,
            ),
        ],
    )


def _build_state_map() -> ComponentStateMap:
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


def _build_binding_context() -> NetworkBindingContext:
    graph = _build_graph()
    assembly = assemble_network_residuals(graph)
    bindings = [
        ComponentBinding(instance_id=_EVAP_ID, binding_name="evap_stub"),
        ComponentBinding(instance_id=_COND_ID, binding_name="cond_stub"),
    ]
    return build_binding_context(graph, assembly, bindings, _build_state_map())


def _build_producer_set() -> ProductionLikeComponentSet:
    return ProductionLikeComponentSet(
        bindings=(
            ProductionLikeComponentBinding(component_id=_EVAP_ID, producer=CloseoutEvapStub()),
            ProductionLikeComponentBinding(component_id=_COND_ID, producer=CloseoutCondStub()),
        )
    )


def _build_residual_map() -> ContributionResidualMap:
    return ContributionResidualMap(
        mapping={
            (_EVAP_ID, "mass_balance"): "mass_balance:n1",
            (_EVAP_ID, "pressure_drop"): "pressure_drop:evap",
            (_COND_ID, "mass_balance"): "mass_balance:n2",
            (_COND_ID, "pressure_drop"): "pressure_drop:cond",
        }
    )


def _build_contribution_adapter_set(
    bc: NetworkBindingContext,
    producer_set: ProductionLikeComponentSet,
    residual_map: ContributionResidualMap,
) -> ComponentContributionAdapterSet:
    """Wrap production-like execution in Phase 14C contribution adapter callbacks."""

    def _make_cb(cid: ComponentInstanceId):
        def callback(ctx):
            return build_component_contribution_from_production_like_execution(
                cid,
                bc,
                producer_set,
                residual_map,
                dict(ctx.unknown_values),
            )

        return callback

    return ComponentContributionAdapterSet(
        adapters=(
            ComponentContributionAdapter(instance_id=_EVAP_ID, callback=_make_cb(_EVAP_ID)),
            ComponentContributionAdapter(instance_id=_COND_ID, callback=_make_cb(_COND_ID)),
        )
    )


# ---------------------------------------------------------------------------
# Items 1–9: End-to-end explicit stack tests
# ---------------------------------------------------------------------------


class TestEndToEndExplicitStack:
    """End-to-end path from production-like producers to Phase 13G evaluation.

    Demonstrates the full controlled integration path:
      Block 15A.3 execute_production_like_contributions (producers use ReadOnlyUnknownView)
        → Phase 14D map_contribution_records_to_component_contribution (per component)
        → Phase 14C ComponentContributionAdapter + build_physical_adapters_from_contributions
        → Phase 14A build_network_residual_evaluators
        → Phase 13G evaluate_network_residuals

    This is NOT production component execution.
    This is NOT solve(network).
    This is NOT SystemState assembly.
    This is NOT FluidState construction.
    This is NOT automatic physics from component_type.
    Producers are controlled stubs.  Physics is explicit algebraic computation only.
    """

    def test_producers_create_contribution_records_via_unknown_view(self):
        """Item 1: production-like producers create contribution records via ReadOnlyUnknownView."""
        bc = _build_binding_context()
        record_set = execute_production_like_contributions(bc, _build_producer_set(), _SOLUTION)
        assert isinstance(record_set, ContributionRecordSet)
        assert len(record_set.records) == 4

    def test_evap_records_created_from_component_and_node_views(self):
        """Item 1 (detail): evap stub reads mdot:evap via component view, P:n1 via node view."""
        bc = _build_binding_context()
        record_set = execute_production_like_contributions(bc, _build_producer_set(), _SOLUTION)
        evap_records = [r for r in record_set.records if r.component_id == _EVAP_ID]
        assert len(evap_records) == 2
        names = {r.name for r in evap_records}
        assert names == {"mass_balance", "pressure_drop"}

    def test_cond_records_created(self):
        """Item 1 (detail): cond stub creates its own contribution records."""
        bc = _build_binding_context()
        record_set = execute_production_like_contributions(bc, _build_producer_set(), _SOLUTION)
        cond_records = [r for r in record_set.records if r.component_id == _COND_ID]
        assert len(cond_records) == 2
        names = {r.name for r in cond_records}
        assert names == {"mass_balance", "pressure_drop"}

    def test_records_map_through_contribution_residual_map(self):
        """Item 2: records map through ContributionResidualMap → ComponentContribution."""
        bc = _build_binding_context()
        record_set = execute_production_like_contributions(bc, _build_producer_set(), _SOLUTION)
        residual_map = _build_residual_map()

        evap_contrib = map_contribution_records_to_component_contribution(
            _EVAP_ID, record_set, residual_map
        )
        cond_contrib = map_contribution_records_to_component_contribution(
            _COND_ID, record_set, residual_map
        )

        assert isinstance(evap_contrib, ComponentContribution)
        assert isinstance(cond_contrib, ComponentContribution)
        assert "mass_balance:n1" in evap_contrib.residual_values
        assert "pressure_drop:evap" in evap_contrib.residual_values
        assert "mass_balance:n2" in cond_contrib.residual_values
        assert "pressure_drop:cond" in cond_contrib.residual_values

    def test_mapped_contribution_is_phase14c_component_contribution(self):
        """Item 3: the mapped result is a Phase 14C ComponentContribution."""
        bc = _build_binding_context()
        record_set = execute_production_like_contributions(bc, _build_producer_set(), _SOLUTION)
        residual_map = _build_residual_map()
        evap_contrib = map_contribution_records_to_component_contribution(
            _EVAP_ID, record_set, residual_map
        )
        assert isinstance(evap_contrib, ComponentContribution)
        assert hasattr(evap_contrib, "residual_values")

    def test_residuals_are_zero_at_solution_point(self):
        """Item 8: all residuals are zero at the known algebraic solution."""
        bc = _build_binding_context()
        record_set = execute_production_like_contributions(bc, _build_producer_set(), _SOLUTION)
        residual_map = _build_residual_map()

        evap_contrib = map_contribution_records_to_component_contribution(
            _EVAP_ID, record_set, residual_map
        )
        cond_contrib = map_contribution_records_to_component_contribution(
            _COND_ID, record_set, residual_map
        )

        assert evap_contrib.residual_values["mass_balance:n1"] == pytest.approx(0.0)
        assert evap_contrib.residual_values["pressure_drop:evap"] == pytest.approx(0.0)
        assert cond_contrib.residual_values["mass_balance:n2"] == pytest.approx(0.0)
        assert cond_contrib.residual_values["pressure_drop:cond"] == pytest.approx(0.0)

    def test_full_path_to_phase13g_evaluation(self):
        """Items 4–7: full path from contribution adapters through Phase 13G.

        Path: production-like execution wrapped in Phase 14C callbacks
          → build_physical_adapters_from_contributions (Phase 14C)
          → build_network_residual_evaluators (Phase 14A)
          → evaluate_network_residuals (Phase 13G)
        """
        bc = _build_binding_context()
        residual_map = _build_residual_map()
        producer_set = _build_producer_set()

        adapter_set = _build_contribution_adapter_set(bc, producer_set, residual_map)
        physical_set = build_physical_adapters_from_contributions(bc, adapter_set)
        evaluators = build_network_residual_evaluators(bc.assembly, physical_set)

        uv = NetworkUnknownValues(values=_SOLUTION)
        scales = {name: 1.0 for name in bc.assembly.residuals.names()}
        result = evaluate_network_residuals(bc.assembly, uv, evaluators, scales)

        rv = {e.spec.name: e.value for e in result.residual_vector.evaluations}
        assert rv["mass_balance:n1"] == pytest.approx(0.0)
        assert rv["mass_balance:n2"] == pytest.approx(0.0)
        assert rv["pressure_drop:evap"] == pytest.approx(0.0)
        assert rv["pressure_drop:cond"] == pytest.approx(0.0)

    def test_residual_ordering_follows_assembly_declaration_order(self):
        """Item 9: evaluation result residuals follow assembly declaration order.

        assemble_network_residuals declares nodes first (mass_balance:*),
        then components (pressure_drop:*), both in graph insertion order.
        """
        bc = _build_binding_context()
        residual_map = _build_residual_map()
        producer_set = _build_producer_set()

        adapter_set = _build_contribution_adapter_set(bc, producer_set, residual_map)
        physical_set = build_physical_adapters_from_contributions(bc, adapter_set)
        evaluators = build_network_residual_evaluators(bc.assembly, physical_set)

        uv = NetworkUnknownValues(values=_SOLUTION)
        scales = {name: 1.0 for name in bc.assembly.residuals.names()}
        result = evaluate_network_residuals(bc.assembly, uv, evaluators, scales)

        actual_order = [e.spec.name for e in result.evaluations]
        assert actual_order == _EXPECTED_RESIDUAL_ORDER

    def test_evaluation_result_at_off_solution_point_is_nonzero(self):
        """Sanity: residuals are not all zero at the off-solution initial guess."""
        bc = _build_binding_context()
        residual_map = _build_residual_map()
        producer_set = _build_producer_set()

        adapter_set = _build_contribution_adapter_set(bc, producer_set, residual_map)
        physical_set = build_physical_adapters_from_contributions(bc, adapter_set)
        evaluators = build_network_residual_evaluators(bc.assembly, physical_set)

        uv = NetworkUnknownValues(values=_INITIAL_GUESS)
        scales = {name: 1.0 for name in bc.assembly.residuals.names()}
        result = evaluate_network_residuals(bc.assembly, uv, evaluators, scales)

        assert result.max_abs_scaled > 0.0


# ---------------------------------------------------------------------------
# Item 10: Solver compatibility — algebraic callback solve
# ---------------------------------------------------------------------------


class TestAlgebraicSolverCompatibility:
    """Phase 13H callback-only algebraic solve test.

    IMPORTANT — this test:
      * uses the existing Phase 13H callback-only solver (solve_network_residual_problem);
      * solves a controlled, explicitly-supplied algebraic system;
      * does NOT execute production component classes;
      * does NOT call Component.contribute(...) or any method named contribute;
      * does NOT assemble SystemState or create FluidState;
      * does NOT call property backends, correlations, or CoolProp;
      * is NOT a generic network-graph solve (not solve_network_graph or similar);
      * is NOT physical single-loop network simulation.

    The system is a 4×4 purely algebraic residual problem whose unique
    solution is _SOLUTION.  Convergence proves that the production-like
    execution path composes correctly with the existing Phase 13H solver.
    """

    def test_phase13h_converges_from_initial_guess(self):
        """Item 10: Phase 13H converges to the known algebraic solution."""
        bc = _build_binding_context()
        residual_map = _build_residual_map()
        producer_set = _build_producer_set()

        adapter_set = _build_contribution_adapter_set(bc, producer_set, residual_map)
        physical_set = build_physical_adapters_from_contributions(bc, adapter_set)
        evaluators = build_network_residual_evaluators(bc.assembly, physical_set)

        scales = {name: 1.0 for name in bc.assembly.residuals.names()}
        config = NetworkSolveConfig(
            max_iterations=20,
            tolerance=1e-10,
            finite_difference_step=1e-6,
            damping=1.0,
        )

        solve_result = solve_network_residual_problem(
            bc.assembly,
            _INITIAL_GUESS,
            evaluators,
            scales,
            config,
        )

        assert solve_result.converged, (
            f"Phase 13H solver did not converge: {solve_result.reason!r}; "
            f"final max_abs_scaled={solve_result.final_evaluation.max_abs_scaled:.2e}"
        )

    def test_phase13h_final_values_match_algebraic_solution(self):
        """Item 10 (detail): converged values equal the known algebraic solution."""
        bc = _build_binding_context()
        residual_map = _build_residual_map()
        producer_set = _build_producer_set()

        adapter_set = _build_contribution_adapter_set(bc, producer_set, residual_map)
        physical_set = build_physical_adapters_from_contributions(bc, adapter_set)
        evaluators = build_network_residual_evaluators(bc.assembly, physical_set)

        scales = {name: 1.0 for name in bc.assembly.residuals.names()}
        config = NetworkSolveConfig(
            max_iterations=20,
            tolerance=1e-10,
            finite_difference_step=1e-6,
        )

        solve_result = solve_network_residual_problem(
            bc.assembly,
            _INITIAL_GUESS,
            evaluators,
            scales,
            config,
        )

        final_vals = dict(solve_result.final_unknown_values.values)
        assert final_vals["mdot:evap"] == pytest.approx(0.1, abs=1e-8)
        assert final_vals["mdot:cond"] == pytest.approx(0.1, abs=1e-8)
        assert final_vals["P:n1"] == pytest.approx(200.0, abs=1e-6)
        assert final_vals["P:n2"] == pytest.approx(150.0, abs=1e-6)

    def test_phase13h_all_final_residuals_near_zero(self):
        """Item 10 (detail): all residuals near zero at the converged point."""
        bc = _build_binding_context()
        residual_map = _build_residual_map()
        producer_set = _build_producer_set()

        adapter_set = _build_contribution_adapter_set(bc, producer_set, residual_map)
        physical_set = build_physical_adapters_from_contributions(bc, adapter_set)
        evaluators = build_network_residual_evaluators(bc.assembly, physical_set)

        scales = {name: 1.0 for name in bc.assembly.residuals.names()}
        config = NetworkSolveConfig(
            max_iterations=20,
            tolerance=1e-10,
            finite_difference_step=1e-6,
        )

        solve_result = solve_network_residual_problem(
            bc.assembly,
            _INITIAL_GUESS,
            evaluators,
            scales,
            config,
        )

        final_rv = {
            e.spec.name: e.value for e in solve_result.final_evaluation.residual_vector.evaluations
        }
        assert final_rv["mass_balance:n1"] == pytest.approx(0.0, abs=1e-9)
        assert final_rv["mass_balance:n2"] == pytest.approx(0.0, abs=1e-9)
        assert final_rv["pressure_drop:evap"] == pytest.approx(0.0, abs=1e-9)
        assert final_rv["pressure_drop:cond"] == pytest.approx(0.0, abs=1e-9)

    def test_phase13h_returns_network_solve_result(self):
        """Item 10 (detail): solve returns a NetworkSolveResult with full diagnostics."""
        bc = _build_binding_context()
        residual_map = _build_residual_map()
        producer_set = _build_producer_set()

        adapter_set = _build_contribution_adapter_set(bc, producer_set, residual_map)
        physical_set = build_physical_adapters_from_contributions(bc, adapter_set)
        evaluators = build_network_residual_evaluators(bc.assembly, physical_set)

        scales = {name: 1.0 for name in bc.assembly.residuals.names()}
        config = NetworkSolveConfig(max_iterations=20, tolerance=1e-10, finite_difference_step=1e-6)

        solve_result = solve_network_residual_problem(
            bc.assembly, _INITIAL_GUESS, evaluators, scales, config
        )

        assert isinstance(solve_result, NetworkSolveResult)
        assert isinstance(solve_result.iteration_count, int)
        assert solve_result.iteration_count >= 1


# ---------------------------------------------------------------------------
# Items 11–19: Regression coverage
# ---------------------------------------------------------------------------


class TestRegressionCoverage:
    """Regression: prior block APIs and production contract inspection."""

    def test_block15a1_bridge_apis_still_importable(self):
        """Item 11: Block 15A.1 APIs remain importable and callable."""
        from mpl_sim.network import (
            ProductionBridgeExecutionContext,  # noqa: F401
            ProductionComponentBridgeBinding,  # noqa: F401
            ProductionComponentBridgeSet,  # noqa: F401
            ProductionContributionBridgeProtocol,  # noqa: F401
            build_component_contribution_from_production_bridge_execution,
            execute_production_bridge_contributions,
        )

        assert callable(execute_production_bridge_contributions)
        assert callable(build_component_contribution_from_production_bridge_execution)

    def test_block15a2_readonly_bridge_apis_still_importable(self):
        """Item 12: Block 15A.2 APIs remain importable and functional."""
        from mpl_sim.network import (
            ComponentUnknownView,  # noqa: F401
            NodeUnknownView,  # noqa: F401
            ReadOnlyUnknownView,
            build_readonly_unknown_view,
        )

        bc = _build_binding_context()
        view = build_readonly_unknown_view(bc, _SOLUTION)
        assert isinstance(view, ReadOnlyUnknownView)

    def test_block15a3_production_like_apis_still_importable(self):
        """Item 13: Block 15A.3 APIs remain importable and functional."""
        from mpl_sim.network import (
            ProductionLikeBridgeContext,  # noqa: F401
            ProductionLikeComponentBinding,  # noqa: F401
            ProductionLikeComponentSet,  # noqa: F401
            ProductionLikeRecordProducerProtocol,  # noqa: F401
            build_component_contribution_from_production_like_execution,
            execute_production_like_contributions,
        )

        assert callable(execute_production_like_contributions)
        assert callable(build_component_contribution_from_production_like_execution)

    def test_phase14g_no_contribute_method_on_component(self):
        """Item 14: Component still reports NO_CONTRIBUTE_METHOD."""
        results = inspect_known_production_component_contracts()
        statuses = {r.class_name: r.status for r in results}
        assert statuses.get("Component") == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD

    def test_phase14g_no_contribute_method_on_pipe(self):
        """Item 15: Pipe still reports NO_CONTRIBUTE_METHOD."""
        results = inspect_known_production_component_contracts()
        statuses = {r.class_name: r.status for r in results}
        assert statuses.get("Pipe") == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD

    def test_phase14g_no_contribute_method_on_pump_component(self):
        """Item 16: PumpComponent still reports NO_CONTRIBUTE_METHOD."""
        results = inspect_known_production_component_contracts()
        statuses = {r.class_name: r.status for r in results}
        expected = ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD
        assert statuses.get("PumpComponent") == expected

    def test_phase14g_no_contribute_method_on_accumulator_component(self):
        """Item 17: AccumulatorComponent still reports NO_CONTRIBUTE_METHOD."""
        results = inspect_known_production_component_contracts()
        statuses = {r.class_name: r.status for r in results}
        assert (
            statuses.get("AccumulatorComponent")
            == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD
        )

    def test_phase14g_no_contribute_method_on_evaporator_component(self):
        """Item 18: EvaporatorComponent still reports NO_CONTRIBUTE_METHOD."""
        results = inspect_known_production_component_contracts()
        statuses = {r.class_name: r.status for r in results}
        assert (
            statuses.get("EvaporatorComponent")
            == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD
        )

    def test_phase14g_no_contribute_method_on_condenser_component(self):
        """Item 19: CondenserComponent still reports NO_CONTRIBUTE_METHOD."""
        results = inspect_known_production_component_contracts()
        statuses = {r.class_name: r.status for r in results}
        assert (
            statuses.get("CondenserComponent")
            == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD
        )


# ---------------------------------------------------------------------------
# Items 20–28: Boundary tests — this test file
# ---------------------------------------------------------------------------


def _load_this_file_ast() -> ast.Module:
    src = _THIS_FILE.read_text(encoding="utf-8")
    return ast.parse(src)


def _get_imports(tree: ast.Module) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.append(node.module)
    return names


def _get_call_attr_names(tree: ast.Module) -> list[str]:
    result: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                result.append(node.func.attr)
    return result


def _get_func_def_names(tree: ast.Module) -> list[str]:
    return [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


class TestBoundaryChecksThisFile:
    """Boundary checks on this test file's source code.

    These tests verify that this closeout test file does not import or call
    any forbidden APIs, consistent with the architecture invariants.
    """

    def test_no_coolprop_import(self):
        """Item 20: this test file does not import CoolProp."""
        tree = _load_this_file_ast()
        imports = _get_imports(tree)
        assert not any("CoolProp" in name for name in imports), "test file must not import CoolProp"

    def test_no_property_backend_import(self):
        """Item 21: this test file does not import PropertyBackend."""
        tree = _load_this_file_ast()
        imports = _get_imports(tree)
        assert not any(
            "PropertyBackend" in imp for imp in imports
        ), "test file must not import PropertyBackend"

    def test_no_correlation_registry_import(self):
        """Item 22: this test file does not import CorrelationRegistry."""
        tree = _load_this_file_ast()
        imports = _get_imports(tree)
        assert not any(
            "CorrelationRegistry" in imp for imp in imports
        ), "test file must not import CorrelationRegistry"

    def test_no_hx_model_import(self):
        """Item 23: this test file does not import hx_models."""
        tree = _load_this_file_ast()
        imports = _get_imports(tree)
        assert not any("hx_models" in imp for imp in imports), "test file must not import hx_models"

    def test_no_system_state_or_fluid_state_import(self):
        """Item 24: this test file does not import SystemState or FluidState."""
        tree = _load_this_file_ast()
        imports = _get_imports(tree)
        for imp in imports:
            assert (
                "SystemState" not in imp
            ), f"test file must not import SystemState (found {imp!r})"
            assert "FluidState" not in imp, f"test file must not import FluidState (found {imp!r})"

    def test_no_contribute_call(self):
        """Item 25: this test file has no .contribute( call."""
        tree = _load_this_file_ast()
        call_attrs = _get_call_attr_names(tree)
        assert "contribute" not in call_attrs, "test file must not call .contribute(...)"

    def test_no_def_contribute(self):
        """Item 26: this test file defines no function named 'contribute'."""
        tree = _load_this_file_ast()
        func_names = _get_func_def_names(tree)
        assert (
            "contribute" not in func_names
        ), "test file must not define a function named 'contribute'"

    def test_no_component_type_physics_dispatch(self):
        """Item 27: component_type is declaration-only, never read for physics dispatch."""
        tree = _load_this_file_ast()
        component_type_reads = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr == "component_type"
        ]
        assert (
            component_type_reads == []
        ), "test file must not read component_type to select or infer physics"

    def test_no_network_graph_solve_dispatch(self):
        """Item 28: no generic network-graph solve dispatch in this test file (AST check)."""
        tree = _load_this_file_ast()
        # Check for calls of the form <expr>.solve() where the callee attribute is 'solve'
        # on an object that could be a NetworkGraph — this is forbidden.
        # (solve_network_residual_problem is explicitly allowed.)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "solve":
                    # Any .solve() call on any object is a generic-solve pattern
                    pytest.fail(
                        "test file must not call .solve() on any object "
                        f"(found call at line {getattr(node, 'lineno', '?')})"
                    )
        # Also confirm no function named 'solve' is defined
        func_names = _get_func_def_names(tree)
        assert "solve" not in func_names, "test file must not define a function named 'solve'"


# ---------------------------------------------------------------------------
# Item 29: Boundary check — production_like_bridge module (regression from 15A.3)
# ---------------------------------------------------------------------------


class TestBoundaryChecksBridgeModule:
    """Regression: production_like_bridge module still respects architecture boundaries."""

    def _load_bridge_ast(self) -> ast.Module:
        src = _BRIDGE_SRC.read_text(encoding="utf-8")
        return ast.parse(src)

    def test_bridge_module_no_coolprop_import(self):
        """Item 29: production_like_bridge.py must not import CoolProp."""
        tree = self._load_bridge_ast()
        imports = _get_imports(tree)
        assert not any(
            "CoolProp" in name for name in imports
        ), "production_like_bridge.py must not import CoolProp"

    def test_bridge_module_no_contribute_method_defined(self):
        """Regression: production_like_bridge.py must not define a method named contribute."""
        tree = self._load_bridge_ast()
        func_names = _get_func_def_names(tree)
        assert (
            "contribute" not in func_names
        ), "production_like_bridge.py must not define a function named 'contribute'"

    def test_bridge_module_no_system_state_import(self):
        """Regression: production_like_bridge.py must not import SystemState."""
        tree = self._load_bridge_ast()
        imports = _get_imports(tree)
        assert not any("SystemState" in imp for imp in imports)

    def test_bridge_module_no_fluid_state_import(self):
        """Regression: production_like_bridge.py must not import FluidState."""
        tree = self._load_bridge_ast()
        imports = _get_imports(tree)
        assert not any("FluidState" in imp for imp in imports)


# ---------------------------------------------------------------------------
# Item 30: Public API — no new exports beyond known Block 15A.3 baseline
# ---------------------------------------------------------------------------


class TestPublicAPI:
    """No new public symbols exported from mpl_sim.network in this block."""

    def test_known_block15a3_symbols_present(self):
        """Block 15A.3 symbols remain present in mpl_sim.network."""
        import mpl_sim.network as net

        expected = [
            "ProductionLikeBridgeContext",
            "ProductionLikeRecordProducerProtocol",
            "ProductionLikeComponentBinding",
            "ProductionLikeComponentSet",
            "execute_production_like_contributions",
            "build_component_contribution_from_production_like_execution",
        ]
        for name in expected:
            assert hasattr(net, name), f"mpl_sim.network must export {name!r} (Block 15A.3 symbol)"

    def test_no_closeout_pipeline_module_exported(self):
        """Block 15A.4 adds no new runtime module — production_bridge_pipeline not added."""
        import mpl_sim.network as net

        assert not hasattr(
            net, "build_physical_adapters_from_production_like_execution"
        ), "Block 15A.4 must not add build_physical_adapters_from_production_like_execution"
        _long_name = "build_network_residual_evaluators_from_production_like_execution"
        assert not hasattr(net, _long_name), f"Block 15A.4 must not add {_long_name!r}"

    def test_block15a4_did_not_introduce_contribute_in_network(self):
        """Block 15A.4 must not introduce contribute(...) on any network type."""
        import mpl_sim.network as net

        for name in dir(net):
            obj = getattr(net, name)
            if hasattr(obj, "contribute"):
                pytest.fail(
                    f"mpl_sim.network.{name} has a 'contribute' attribute — "
                    "Block 15A.4 must not introduce contribute(...) on any type"
                )
