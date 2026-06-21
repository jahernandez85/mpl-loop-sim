"""Phase 13F network residual assembly foundation tests.

Coverage items (24 required):
 1.  assembling unknowns from a minimal graph
 2.  one mass-flow unknown per component instance
 3.  one pressure unknown per graph node (with include_pressure_unknowns=True)
 4.  mass-flow unknown names are deterministic
 5.  pressure unknown names are deterministic
 6.  one mass-balance residual per node
 7.  optional pressure residual per component instance
 8.  residual names are deterministic
 9.  unknown/residual units are correct
10.  assembly summary contains counts/names only
11.  assembly contains no numerical physical values
12.  assembly rejects non-NetworkGraph input
13.  assembly rejects empty graph (no nodes or no instances)
14.  optional closed-loop-required mode rejects open path
15.  optional closed-loop-required mode accepts simple closed cycle
16.  no solve method exists on NetworkResidualAssembly
17.  no residual evaluation values are produced
18.  no component execution (architecture boundary)
19.  no property lookup (architecture boundary)
20.  no registry resolution (architecture boundary)
21.  no FluidState, mdot value, pressure value, enthalpy value stored
22.  public exports work from mpl_sim.network
23.  existing Phase 13A/13B/13C/13D/13E tests still pass (ensured by full suite)
24.  docs do not claim network solving for Phase 13F
"""

from __future__ import annotations

import inspect

import pytest

from mpl_sim.network import (
    ComponentInstance,
    ComponentInstanceId,
    GraphNode,
    GraphNodeId,
    NetworkGraph,
    NetworkResidualAssembly,
    NetworkResidualDeclaration,
    NetworkResidualSet,
    NetworkUnknownDeclaration,
    NetworkUnknownSet,
    assemble_network_residuals,
)

# ---------------------------------------------------------------------------
# Shared graph-building helpers
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


def _minimal_graph() -> NetworkGraph:
    """Two-node, one-component graph (open path)."""
    return NetworkGraph(
        nodes=[_node("node_a"), _node("node_b")],
        instances=[_inst("evap", "evaporator", "node_a", "node_b")],
    )


def _two_component_graph() -> NetworkGraph:
    """Three-node, two-component graph (open path)."""
    return NetworkGraph(
        nodes=[_node("node_a"), _node("node_b"), _node("node_c")],
        instances=[
            _inst("evap", "evaporator", "node_a", "node_b"),
            _inst("cond", "condenser", "node_b", "node_c"),
        ],
    )


def _closed_loop_graph() -> NetworkGraph:
    """Two-node, two-component closed single loop."""
    return NetworkGraph(
        nodes=[_node("node_a"), _node("node_b")],
        instances=[
            _inst("evap", "evaporator", "node_a", "node_b"),
            _inst("cond", "condenser", "node_b", "node_a"),
        ],
    )


def _four_node_closed_loop() -> NetworkGraph:
    """Four-node, four-component closed single loop."""
    return NetworkGraph(
        nodes=[_node("A"), _node("B"), _node("C"), _node("D")],
        instances=[
            _inst("comp1", "evaporator", "A", "B"),
            _inst("comp2", "pump", "B", "C"),
            _inst("comp3", "condenser", "C", "D"),
            _inst("comp4", "valve", "D", "A"),
        ],
    )


# ---------------------------------------------------------------------------
# Coverage item 1 — assembling unknowns from a minimal graph
# ---------------------------------------------------------------------------


class TestAssembleMinimalGraph:
    def test_returns_assembly(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        assert isinstance(assembly, NetworkResidualAssembly)

    def test_assembly_has_unknown_set(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        assert isinstance(assembly.unknowns, NetworkUnknownSet)

    def test_assembly_has_residual_set(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        assert isinstance(assembly.residuals, NetworkResidualSet)

    def test_all_declarations_are_declaration_types(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        for u in assembly.unknowns.unknowns:
            assert isinstance(u, NetworkUnknownDeclaration)
        for r in assembly.residuals.residuals:
            assert isinstance(r, NetworkResidualDeclaration)


# ---------------------------------------------------------------------------
# Coverage item 2 — one mass-flow unknown per component instance
# ---------------------------------------------------------------------------


class TestMassFlowUnknowns:
    def test_one_mdot_unknown_for_one_component(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        mdot_names = [n for n in assembly.unknowns.names() if n.startswith("mdot:")]
        assert len(mdot_names) == 1

    def test_mdot_unknown_matches_instance_id(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        assert "mdot:evap" in assembly.unknowns.names()

    def test_two_mdot_unknowns_for_two_components(self) -> None:
        graph = _two_component_graph()
        assembly = assemble_network_residuals(graph)
        mdot_names = [n for n in assembly.unknowns.names() if n.startswith("mdot:")]
        assert len(mdot_names) == 2

    def test_mdot_unknowns_match_instance_ids(self) -> None:
        graph = _two_component_graph()
        assembly = assemble_network_residuals(graph)
        names = assembly.unknowns.names()
        assert "mdot:evap" in names
        assert "mdot:cond" in names

    def test_four_mdot_unknowns_for_four_components(self) -> None:
        graph = _four_node_closed_loop()
        assembly = assemble_network_residuals(graph)
        mdot_names = [n for n in assembly.unknowns.names() if n.startswith("mdot:")]
        assert len(mdot_names) == 4


# ---------------------------------------------------------------------------
# Coverage item 3 — one pressure unknown per graph node
# ---------------------------------------------------------------------------


class TestPressureUnknowns:
    def test_one_pressure_unknown_per_node_default_enabled(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        p_names = [n for n in assembly.unknowns.names() if n.startswith("P:")]
        assert len(p_names) == 2  # two nodes

    def test_pressure_unknown_names_match_node_ids(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        names = assembly.unknowns.names()
        assert "P:node_a" in names
        assert "P:node_b" in names

    def test_no_pressure_unknowns_when_disabled(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph, include_pressure_unknowns=False)
        p_names = [n for n in assembly.unknowns.names() if n.startswith("P:")]
        assert len(p_names) == 0

    def test_total_unknowns_without_pressure(self) -> None:
        graph = _two_component_graph()
        assembly = assemble_network_residuals(graph, include_pressure_unknowns=False)
        assert assembly.unknowns.count() == 2  # one per component only

    def test_three_pressure_unknowns_for_three_nodes(self) -> None:
        graph = _two_component_graph()
        assembly = assemble_network_residuals(graph)
        p_names = [n for n in assembly.unknowns.names() if n.startswith("P:")]
        assert len(p_names) == 3


# ---------------------------------------------------------------------------
# Coverage items 4 & 5 — deterministic ordering
# ---------------------------------------------------------------------------


class TestDeterministicOrdering:
    def test_mass_flow_unknown_names_are_deterministic(self) -> None:
        graph = _two_component_graph()
        names_1 = assemble_network_residuals(graph).unknowns.names()
        names_2 = assemble_network_residuals(graph).unknowns.names()
        assert names_1 == names_2

    def test_pressure_unknown_names_are_deterministic(self) -> None:
        graph = _two_component_graph()
        names_1 = assemble_network_residuals(graph).unknowns.names()
        names_2 = assemble_network_residuals(graph).unknowns.names()
        assert names_1 == names_2

    def test_mdot_unknowns_follow_instance_insertion_order(self) -> None:
        graph = _two_component_graph()
        assembly = assemble_network_residuals(graph)
        names = assembly.unknowns.names()
        evap_idx = names.index("mdot:evap")
        cond_idx = names.index("mdot:cond")
        assert evap_idx < cond_idx

    def test_pressure_unknowns_follow_node_insertion_order(self) -> None:
        graph = _two_component_graph()
        assembly = assemble_network_residuals(graph)
        names = assembly.unknowns.names()
        pa_idx = names.index("P:node_a")
        pb_idx = names.index("P:node_b")
        pc_idx = names.index("P:node_c")
        assert pa_idx < pb_idx < pc_idx

    def test_residual_names_are_deterministic(self) -> None:
        graph = _two_component_graph()
        names_1 = assemble_network_residuals(graph).residuals.names()
        names_2 = assemble_network_residuals(graph).residuals.names()
        assert names_1 == names_2

    def test_same_graph_different_calls_same_assembly(self) -> None:
        graph = _four_node_closed_loop()
        a1 = assemble_network_residuals(graph)
        a2 = assemble_network_residuals(graph)
        assert a1.unknowns.names() == a2.unknowns.names()
        assert a1.residuals.names() == a2.residuals.names()


# ---------------------------------------------------------------------------
# Coverage item 6 — one mass-balance residual per node
# ---------------------------------------------------------------------------


class TestMassBalanceResiduals:
    def test_one_mass_balance_per_node_minimal(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        mb_names = [n for n in assembly.residuals.names() if n.startswith("mass_balance:")]
        assert len(mb_names) == 2  # two nodes

    def test_mass_balance_names_match_node_ids(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        names = assembly.residuals.names()
        assert "mass_balance:node_a" in names
        assert "mass_balance:node_b" in names

    def test_three_mass_balance_residuals_for_three_nodes(self) -> None:
        graph = _two_component_graph()
        assembly = assemble_network_residuals(graph)
        mb_names = [n for n in assembly.residuals.names() if n.startswith("mass_balance:")]
        assert len(mb_names) == 3

    def test_mass_balance_residuals_follow_node_insertion_order(self) -> None:
        graph = _two_component_graph()
        assembly = assemble_network_residuals(graph)
        mb_names = [n for n in assembly.residuals.names() if n.startswith("mass_balance:")]
        assert mb_names == ["mass_balance:node_a", "mass_balance:node_b", "mass_balance:node_c"]


# ---------------------------------------------------------------------------
# Coverage item 7 — optional pressure residual per component instance
# ---------------------------------------------------------------------------


class TestPressureResiduals:
    def test_one_pressure_residual_per_component_default(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        pd_names = [n for n in assembly.residuals.names() if n.startswith("pressure_drop:")]
        assert len(pd_names) == 1

    def test_pressure_residual_name_matches_instance_id(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        assert "pressure_drop:evap" in assembly.residuals.names()

    def test_two_pressure_residuals_for_two_components(self) -> None:
        graph = _two_component_graph()
        assembly = assemble_network_residuals(graph)
        pd_names = [n for n in assembly.residuals.names() if n.startswith("pressure_drop:")]
        assert len(pd_names) == 2

    def test_no_pressure_residuals_when_disabled(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph, include_pressure_residuals=False)
        pd_names = [n for n in assembly.residuals.names() if n.startswith("pressure_drop:")]
        assert len(pd_names) == 0

    def test_residual_count_without_pressure_residuals(self) -> None:
        graph = _two_component_graph()
        assembly = assemble_network_residuals(graph, include_pressure_residuals=False)
        assert assembly.residuals.count() == 3  # one per node only


# ---------------------------------------------------------------------------
# Coverage item 9 — correct units
# ---------------------------------------------------------------------------


class TestUnits:
    def test_mdot_unknown_unit_is_kg_per_s(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        for u in assembly.unknowns.unknowns:
            if u.name.startswith("mdot:"):
                assert u.unit == "kg/s"

    def test_pressure_unknown_unit_is_Pa(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        for u in assembly.unknowns.unknowns:
            if u.name.startswith("P:"):
                assert u.unit == "Pa"

    def test_mass_balance_residual_unit_is_kg_per_s(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        for r in assembly.residuals.residuals:
            if r.name.startswith("mass_balance:"):
                assert r.unit == "kg/s"

    def test_pressure_drop_residual_unit_is_Pa(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        for r in assembly.residuals.residuals:
            if r.name.startswith("pressure_drop:"):
                assert r.unit == "Pa"

    def test_all_declaration_units_are_non_empty_strings(self) -> None:
        graph = _four_node_closed_loop()
        assembly = assemble_network_residuals(graph)
        for u in assembly.unknowns.unknowns:
            assert isinstance(u.unit, str)
            assert u.unit.strip()
        for r in assembly.residuals.residuals:
            assert isinstance(r.unit, str)
            assert r.unit.strip()


# ---------------------------------------------------------------------------
# Coverage item 10 — summary contains counts/names only
# ---------------------------------------------------------------------------


class TestAssemblySummary:
    def test_summary_returns_dict(self) -> None:
        graph = _minimal_graph()
        summary = assemble_network_residuals(graph).summary()
        assert isinstance(summary, dict)

    def test_summary_has_required_keys(self) -> None:
        graph = _minimal_graph()
        summary = assemble_network_residuals(graph).summary()
        assert "unknown_count" in summary
        assert "unknown_names" in summary
        assert "residual_count" in summary
        assert "residual_names" in summary

    def test_summary_unknown_count_matches_count_method(self) -> None:
        graph = _two_component_graph()
        assembly = assemble_network_residuals(graph)
        summary = assembly.summary()
        assert summary["unknown_count"] == assembly.unknowns.count()

    def test_summary_residual_count_matches_count_method(self) -> None:
        graph = _two_component_graph()
        assembly = assemble_network_residuals(graph)
        summary = assembly.summary()
        assert summary["residual_count"] == assembly.residuals.count()

    def test_summary_names_match_names_method(self) -> None:
        graph = _two_component_graph()
        assembly = assemble_network_residuals(graph)
        summary = assembly.summary()
        assert summary["unknown_names"] == list(assembly.unknowns.names())
        assert summary["residual_names"] == list(assembly.residuals.names())

    def test_summary_contains_no_numeric_values(self) -> None:
        graph = _two_component_graph()
        summary = assemble_network_residuals(graph).summary()
        # Only the count integers and string lists are allowed; no floats.
        for key, val in summary.items():
            if key.endswith("_count"):
                assert isinstance(val, int)
            elif key.endswith("_names"):
                assert isinstance(val, list)
                for item in val:
                    assert isinstance(item, str)


# ---------------------------------------------------------------------------
# Coverage item 11 — assembly contains no numerical physical values
# ---------------------------------------------------------------------------


class TestNoPhysicalValues:
    def test_unknown_declaration_has_no_value_attribute(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        for u in assembly.unknowns.unknowns:
            assert not hasattr(u, "value")

    def test_residual_declaration_has_no_value_attribute(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        for r in assembly.residuals.residuals:
            assert not hasattr(r, "value")

    def test_assembly_has_no_mdot_attribute(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        assert not hasattr(assembly, "mdot")

    def test_assembly_has_no_pressure_value_attribute(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        assert not hasattr(assembly, "pressure")
        assert not hasattr(assembly, "P")

    def test_assembly_has_no_enthalpy_attribute(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        assert not hasattr(assembly, "enthalpy")
        assert not hasattr(assembly, "h")

    def test_assembly_has_no_fluid_state_attribute(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        assert not hasattr(assembly, "fluid_state")
        assert not hasattr(assembly, "FluidState")

    def test_declaration_has_no_scale_attribute(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        for u in assembly.unknowns.unknowns:
            assert not hasattr(u, "scale")
        for r in assembly.residuals.residuals:
            assert not hasattr(r, "scale")

    def test_declaration_has_no_lower_upper_bounds(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        for u in assembly.unknowns.unknowns:
            assert not hasattr(u, "lower")
            assert not hasattr(u, "upper")

    def test_unknown_set_has_no_values_field(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        assert not hasattr(assembly.unknowns, "values")

    def test_residual_set_has_no_values_field(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        assert not hasattr(assembly.residuals, "values")


# ---------------------------------------------------------------------------
# Coverage item 12 — assembly rejects non-NetworkGraph input
# ---------------------------------------------------------------------------


class TestRejectsNonNetworkGraph:
    @pytest.mark.parametrize(
        "bad_input",
        [
            None,
            "graph",
            42,
            {},
            [],
            object(),
        ],
    )
    def test_rejects_non_network_graph(self, bad_input: object) -> None:
        with pytest.raises(TypeError, match="NetworkGraph"):
            assemble_network_residuals(bad_input)  # type: ignore[arg-type]

    def test_error_message_names_type(self) -> None:
        with pytest.raises(TypeError, match="NetworkGraph"):
            assemble_network_residuals("not a graph")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Coverage item 13 — assembly rejects empty graph
# ---------------------------------------------------------------------------


class TestRejectsEmptyGraph:
    def test_rejects_graph_with_no_nodes_and_no_instances(self) -> None:
        graph = NetworkGraph(nodes=[], instances=[])
        with pytest.raises(ValueError, match="node"):
            assemble_network_residuals(graph)

    def test_rejects_graph_with_nodes_but_no_instances(self) -> None:
        graph = NetworkGraph(nodes=[_node("only_node")], instances=[])
        with pytest.raises(ValueError, match="instance"):
            assemble_network_residuals(graph)


# ---------------------------------------------------------------------------
# Coverage items 14 & 15 — closed-loop validation mode
# ---------------------------------------------------------------------------


class TestClosedLoopValidation:
    def test_open_path_rejected_when_require_closed_loop(self) -> None:
        graph = _minimal_graph()  # open: A→B, no return
        with pytest.raises(ValueError):
            assemble_network_residuals(graph, require_closed_loop=True)

    def test_simple_closed_cycle_accepted(self) -> None:
        graph = _closed_loop_graph()
        assembly = assemble_network_residuals(graph, require_closed_loop=True)
        assert isinstance(assembly, NetworkResidualAssembly)

    def test_four_node_closed_loop_accepted(self) -> None:
        graph = _four_node_closed_loop()
        assembly = assemble_network_residuals(graph, require_closed_loop=True)
        assert isinstance(assembly, NetworkResidualAssembly)

    def test_open_topology_accepted_when_not_required(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph, require_closed_loop=False)
        assert isinstance(assembly, NetworkResidualAssembly)

    def test_open_topology_accepted_by_default(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        assert isinstance(assembly, NetworkResidualAssembly)

    def test_disconnected_graph_rejected_when_require_closed_loop(self) -> None:
        # Two separate single-hop paths (not a single loop).
        graph = NetworkGraph(
            nodes=[_node("A"), _node("B"), _node("C"), _node("D")],
            instances=[
                _inst("c1", "evap", "A", "B"),
                _inst("c2", "cond", "C", "D"),
            ],
        )
        with pytest.raises(ValueError):
            assemble_network_residuals(graph, require_closed_loop=True)


# ---------------------------------------------------------------------------
# Explicit option validation
# ---------------------------------------------------------------------------


class TestOptionValidation:
    @pytest.mark.parametrize(
        ("option_name", "option_value"),
        [
            ("require_closed_loop", 1),
            ("include_pressure_unknowns", "yes"),
            ("include_pressure_residuals", None),
        ],
    )
    def test_non_boolean_option_rejected(self, option_name: str, option_value: object) -> None:
        graph = _minimal_graph()
        with pytest.raises(TypeError, match=rf"{option_name} must be a bool"):
            assemble_network_residuals(graph, **{option_name: option_value})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Coverage item 16 — no solve method exists
# ---------------------------------------------------------------------------


class TestNoSolveMethod:
    def test_assembly_has_no_solve_method(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        assert not hasattr(assembly, "solve")

    def test_unknown_set_has_no_solve_method(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        assert not hasattr(assembly.unknowns, "solve")

    def test_residual_set_has_no_solve_method(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        assert not hasattr(assembly.residuals, "solve")

    def test_assembly_module_has_no_solve_network_function(self) -> None:
        import mpl_sim.network.residual_assembly as mod

        assert not hasattr(mod, "solve_network")
        assert not hasattr(mod, "solve")


# ---------------------------------------------------------------------------
# Coverage item 17 — no residual evaluation values produced
# ---------------------------------------------------------------------------


class TestNoEvaluationValues:
    def test_declaration_has_only_name_and_unit(self) -> None:
        decl = NetworkUnknownDeclaration(name="mdot:x", unit="kg/s")
        fields = {f.name for f in decl.__dataclass_fields__.values()}
        assert fields == {"name", "unit"}

    def test_residual_declaration_has_only_name_and_unit(self) -> None:
        decl = NetworkResidualDeclaration(name="mass_balance:x", unit="kg/s")
        fields = {f.name for f in decl.__dataclass_fields__.values()}
        assert fields == {"name", "unit"}

    def test_assembly_does_not_have_residual_vector(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        assert not hasattr(assembly, "residual_vector")
        assert not hasattr(assembly, "evaluations")

    def test_assembly_does_not_have_is_converged(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        assert not hasattr(assembly, "is_converged")
        assert not hasattr(assembly, "max_abs_scaled")


# ---------------------------------------------------------------------------
# Coverage items 18, 19, 20 — architecture boundary checks
# ---------------------------------------------------------------------------


class TestArchitectureBoundaries:
    def _import_lines(self) -> list[str]:
        """Return only the executable import lines from residual_assembly.py."""
        import mpl_sim.network.residual_assembly as mod

        source = inspect.getsource(mod)
        return [
            line.strip()
            for line in source.splitlines()
            if (line.strip().startswith("import ") or line.strip().startswith("from "))
            and not line.strip().startswith("#")
        ]

    def test_no_coolprop_import(self) -> None:
        for line in self._import_lines():
            assert "CoolProp" not in line, f"Forbidden import: {line!r}"

    def test_no_property_backend_import(self) -> None:
        for line in self._import_lines():
            assert "PropertyBackend" not in line, f"Forbidden import: {line!r}"

    def test_no_correlation_registry_import(self) -> None:
        for line in self._import_lines():
            assert "CorrelationRegistry" not in line, f"Forbidden import: {line!r}"

    def test_no_closed_loop_import(self) -> None:
        for line in self._import_lines():
            assert "closed_loop" not in line, f"Forbidden import: {line!r}"

    def test_no_mpl_sim_solvers_import(self) -> None:
        for line in self._import_lines():
            assert "mpl_sim.solvers" not in line, f"Forbidden import: {line!r}"

    def test_no_mpl_sim_components_import(self) -> None:
        for line in self._import_lines():
            assert "mpl_sim.components" not in line, f"Forbidden import: {line!r}"

    def test_no_mpl_sim_hx_models_import(self) -> None:
        for line in self._import_lines():
            assert "mpl_sim.hx_models" not in line, f"Forbidden import: {line!r}"

    def test_no_contribute_call(self) -> None:
        import mpl_sim.network.residual_assembly as mod

        source = inspect.getsource(mod)
        # Only check executable lines (not docstrings / comments).
        code_lines = [
            line
            for line in source.splitlines()
            if not line.strip().startswith('"""')
            and not line.strip().startswith("'")
            and not line.strip().startswith("#")
            and "contribute(" in line
        ]
        assert code_lines == [], f"Found contribute( call: {code_lines}"

    def test_module_imports_only_stdlib_and_graph(self) -> None:
        import mpl_sim.network.residual_assembly as mod

        allowed_prefixes = (
            "__future__",
            "dataclasses",
            "mpl_sim.network.graph",
            "mpl_sim.network.residual_assembly",
        )
        for name, obj in vars(mod).items():
            if isinstance(obj, type(inspect)):
                assert any(
                    obj.__name__.startswith(p) for p in allowed_prefixes
                ), f"Unexpected module import: {obj.__name__!r}"

    def test_no_fluid_state_import_line(self) -> None:
        for line in self._import_lines():
            assert "FluidState" not in line, f"Forbidden import: {line!r}"

    def test_no_system_state_import_line(self) -> None:
        for line in self._import_lines():
            assert "SystemState" not in line, f"Forbidden import: {line!r}"


# ---------------------------------------------------------------------------
# Coverage item 21 — frozen / immutability
# ---------------------------------------------------------------------------


class TestImmutability:
    def test_unknown_declaration_is_frozen(self) -> None:
        decl = NetworkUnknownDeclaration(name="mdot:x", unit="kg/s")
        with pytest.raises((AttributeError, TypeError)):
            decl.name = "other"  # type: ignore[misc]

    def test_residual_declaration_is_frozen(self) -> None:
        decl = NetworkResidualDeclaration(name="mass_balance:x", unit="kg/s")
        with pytest.raises((AttributeError, TypeError)):
            decl.name = "other"  # type: ignore[misc]

    def test_unknown_set_is_frozen(self) -> None:
        us = NetworkUnknownSet(unknowns=(NetworkUnknownDeclaration(name="mdot:x", unit="kg/s"),))
        with pytest.raises((AttributeError, TypeError)):
            us.unknowns = ()  # type: ignore[misc]

    def test_residual_set_is_frozen(self) -> None:
        rs = NetworkResidualSet(
            residuals=(NetworkResidualDeclaration(name="mass_balance:x", unit="kg/s"),)
        )
        with pytest.raises((AttributeError, TypeError)):
            rs.residuals = ()  # type: ignore[misc]

    def test_assembly_is_frozen(self) -> None:
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        with pytest.raises((AttributeError, TypeError)):
            assembly.unknowns = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Coverage item 22 — public exports from mpl_sim.network
# ---------------------------------------------------------------------------


class TestPublicExports:
    def test_all_phase_13f_types_in_network_all(self) -> None:
        import mpl_sim.network as pkg

        expected = {
            "NetworkUnknownDeclaration",
            "NetworkResidualDeclaration",
            "NetworkUnknownSet",
            "NetworkResidualSet",
            "NetworkResidualAssembly",
            "assemble_network_residuals",
        }
        assert expected.issubset(set(pkg.__all__))

    def test_import_unknown_declaration_from_network(self) -> None:
        from mpl_sim.network import NetworkUnknownDeclaration as T

        assert T is NetworkUnknownDeclaration

    def test_import_residual_declaration_from_network(self) -> None:
        from mpl_sim.network import NetworkResidualDeclaration as T

        assert T is NetworkResidualDeclaration

    def test_import_unknown_set_from_network(self) -> None:
        from mpl_sim.network import NetworkUnknownSet as T

        assert T is NetworkUnknownSet

    def test_import_residual_set_from_network(self) -> None:
        from mpl_sim.network import NetworkResidualSet as T

        assert T is NetworkResidualSet

    def test_import_assembly_from_network(self) -> None:
        from mpl_sim.network import NetworkResidualAssembly as T

        assert T is NetworkResidualAssembly

    def test_import_factory_from_network(self) -> None:
        from mpl_sim.network import assemble_network_residuals as f

        assert callable(f)

    def test_phase_13e_exports_still_present(self) -> None:
        import mpl_sim.network as pkg

        phase_13e = {
            "GraphNodeId",
            "ComponentInstanceId",
            "GraphNode",
            "ComponentInstance",
            "NetworkGraph",
        }
        assert phase_13e.issubset(set(pkg.__all__))


# ---------------------------------------------------------------------------
# Coverage item 24 — docs do not claim network solving
# ---------------------------------------------------------------------------


class TestDocsHonestClaims:
    def _read_concepts(self) -> str:
        import pathlib

        concepts = (
            pathlib.Path(__file__).parent.parent.parent / "docs" / "user_guide" / "CONCEPTS.md"
        )
        return concepts.read_text(encoding="utf-8")

    def test_concepts_does_not_claim_solve_network(self) -> None:
        text = self._read_concepts()
        phase_13f = text.split("## Network Residual Assembly Foundation (Phase 13F)", 1)[1]
        phase_13f = phase_13f.split("\n---", 1)[0].lower()
        assert "not a network solver" in phase_13f
        assert "does not evaluate residuals numerically" in phase_13f

    def test_concepts_mentions_phase_13f_does_not_solve(self) -> None:
        text = self._read_concepts()
        assert "does not solve" in text.lower() or "not a network solver" in text.lower()

    def test_concepts_mentions_phase_13f(self) -> None:
        text = self._read_concepts()
        assert "Phase 13F" in text or "13F" in text

    def test_concepts_still_has_phase_13e_section(self) -> None:
        text = self._read_concepts()
        assert "Phase 13E" in text


# ---------------------------------------------------------------------------
# Additional structural tests for declaration-type validation
# ---------------------------------------------------------------------------


class TestDeclarationValidation:
    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            NetworkUnknownDeclaration(name="", unit="kg/s")

    def test_whitespace_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            NetworkUnknownDeclaration(name="  ", unit="kg/s")

    def test_empty_unit_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            NetworkUnknownDeclaration(name="mdot:x", unit="")

    def test_non_string_name_rejected(self) -> None:
        with pytest.raises(TypeError, match="string"):
            NetworkUnknownDeclaration(name=42, unit="kg/s")  # type: ignore[arg-type]

    def test_residual_empty_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            NetworkResidualDeclaration(name="", unit="kg/s")

    def test_residual_empty_unit_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            NetworkResidualDeclaration(name="mass_balance:x", unit="")


class TestSetValidation:
    def test_duplicate_unknown_names_rejected(self) -> None:
        d1 = NetworkUnknownDeclaration(name="mdot:x", unit="kg/s")
        d2 = NetworkUnknownDeclaration(name="mdot:x", unit="kg/s")
        with pytest.raises(ValueError, match="duplicate"):
            NetworkUnknownSet(unknowns=(d1, d2))

    def test_duplicate_residual_names_rejected(self) -> None:
        r1 = NetworkResidualDeclaration(name="mass_balance:x", unit="kg/s")
        r2 = NetworkResidualDeclaration(name="mass_balance:x", unit="kg/s")
        with pytest.raises(ValueError, match="duplicate"):
            NetworkResidualSet(residuals=(r1, r2))

    def test_wrong_type_in_unknown_set_rejected(self) -> None:
        with pytest.raises(TypeError, match="NetworkUnknownDeclaration"):
            NetworkUnknownSet(unknowns=("not a declaration",))  # type: ignore[arg-type]

    def test_wrong_type_in_residual_set_rejected(self) -> None:
        with pytest.raises(TypeError, match="NetworkResidualDeclaration"):
            NetworkResidualSet(residuals=("not a declaration",))  # type: ignore[arg-type]

    def test_empty_unknown_set_is_valid(self) -> None:
        us = NetworkUnknownSet(unknowns=())
        assert us.count() == 0

    def test_empty_residual_set_is_valid(self) -> None:
        rs = NetworkResidualSet(residuals=())
        assert rs.count() == 0


class TestTotalCounts:
    def test_total_unknowns_minimal_all_included(self) -> None:
        # 1 component → 1 mdot; 2 nodes → 2 P = 3 total
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        assert assembly.unknowns.count() == 3

    def test_total_residuals_minimal_all_included(self) -> None:
        # 2 nodes → 2 mass_balance; 1 component → 1 pressure_drop = 3 total
        graph = _minimal_graph()
        assembly = assemble_network_residuals(graph)
        assert assembly.residuals.count() == 3

    def test_total_unknowns_two_component_all_included(self) -> None:
        # 2 components → 2 mdot; 3 nodes → 3 P = 5 total
        graph = _two_component_graph()
        assembly = assemble_network_residuals(graph)
        assert assembly.unknowns.count() == 5

    def test_total_residuals_two_component_all_included(self) -> None:
        # 3 nodes → 3 mass_balance; 2 components → 2 pressure_drop = 5 total
        graph = _two_component_graph()
        assembly = assemble_network_residuals(graph)
        assert assembly.residuals.count() == 5

    def test_total_unknowns_no_pressure(self) -> None:
        # 2 components → 2 mdot only
        graph = _two_component_graph()
        assembly = assemble_network_residuals(
            graph, include_pressure_unknowns=False, include_pressure_residuals=False
        )
        assert assembly.unknowns.count() == 2

    def test_total_residuals_no_pressure(self) -> None:
        # 3 nodes → 3 mass_balance only
        graph = _two_component_graph()
        assembly = assemble_network_residuals(
            graph, include_pressure_unknowns=False, include_pressure_residuals=False
        )
        assert assembly.residuals.count() == 3
