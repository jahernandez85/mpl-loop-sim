"""Tests for Block 15E-A: configurable scenario declaration foundation.

Covers:
  - ScenarioComponentRole enum
  - ScenarioComponentSpec validation
  - ScenarioNodeSpec validation
  - ScenarioConnectionSpec validation
  - ScenarioBranchSpec validation
  - ConfigurableScenarioSpec cross-reference and uniqueness validation
  - build_configurable_scenario build results
  - build_configurable_scenario_report output

Architecture boundary assertions:
  - No CoolProp imports
  - No PropertyBackend imports
  - No SystemState or FluidState in the module under test
  - No contribute() calls
  - No component_type physics dispatch
  - No generic solve(network) or NetworkGraph.solve()
"""

from __future__ import annotations

import json
import types

import pytest

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
from mpl_sim.network.graph import ComponentInstanceId, GraphNodeId

# ---------------------------------------------------------------------------
# Helpers: minimal specs
# ---------------------------------------------------------------------------


def _minimal_single_loop_spec(scenario_id: str = "loop") -> ConfigurableScenarioSpec:
    """Minimal single-loop spec: acc -> pump -> evap -> cond -> acc."""
    return ConfigurableScenarioSpec(
        scenario_id=scenario_id,
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


def _minimal_two_branch_spec() -> ConfigurableScenarioSpec:
    """Minimal two-branch parallel spec."""
    return ConfigurableScenarioSpec(
        scenario_id="two_branch",
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


# ===========================================================================
# ScenarioComponentRole
# ===========================================================================


class TestScenarioComponentRole:
    def test_all_expected_members_present(self) -> None:
        names = {m.name for m in ScenarioComponentRole}
        assert names == {
            "ACCUMULATOR",
            "PUMP",
            "EVAPORATOR",
            "CONDENSER",
            "PIPE",
            "VALVE",
            "JUNCTION",
            "MANIFOLD",
            "GENERIC",
        }

    def test_values_are_lowercase_strings(self) -> None:
        for member in ScenarioComponentRole:
            assert isinstance(member.value, str)
            assert member.value == member.value.lower()

    def test_accumulator_value(self) -> None:
        assert ScenarioComponentRole.ACCUMULATOR.value == "accumulator"

    def test_pump_value(self) -> None:
        assert ScenarioComponentRole.PUMP.value == "pump"

    def test_generic_value(self) -> None:
        assert ScenarioComponentRole.GENERIC.value == "generic"


# ===========================================================================
# ScenarioComponentSpec
# ===========================================================================


class TestScenarioComponentSpec:
    def test_valid_construction(self) -> None:
        spec = ScenarioComponentSpec("acc", ScenarioComponentRole.ACCUMULATOR)
        assert spec.component_id == "acc"
        assert spec.role is ScenarioComponentRole.ACCUMULATOR
        assert spec.metadata is None
        assert spec.tags == ()

    def test_empty_id_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ScenarioComponentSpec("", ScenarioComponentRole.PUMP)

    def test_whitespace_id_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ScenarioComponentSpec("   ", ScenarioComponentRole.PUMP)

    def test_non_str_id_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="str"):
            ScenarioComponentSpec(123, ScenarioComponentRole.PUMP)  # type: ignore[arg-type]

    def test_invalid_role_type_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="ScenarioComponentRole"):
            ScenarioComponentSpec("acc", "accumulator")  # type: ignore[arg-type]

    def test_invalid_role_none_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="ScenarioComponentRole"):
            ScenarioComponentSpec("acc", None)  # type: ignore[arg-type]

    def test_metadata_defensive_copy(self) -> None:
        original = {"key": "value"}
        spec = ScenarioComponentSpec("acc", ScenarioComponentRole.ACCUMULATOR, metadata=original)
        original["key"] = "changed"
        assert spec.metadata is not None
        assert spec.metadata["key"] == "value"

    def test_metadata_read_only(self) -> None:
        spec = ScenarioComponentSpec("acc", ScenarioComponentRole.ACCUMULATOR, metadata={"k": 1})
        with pytest.raises((TypeError, AttributeError)):
            spec.metadata["k"] = 99  # type: ignore[index]

    def test_metadata_is_mapping_proxy(self) -> None:
        spec = ScenarioComponentSpec("acc", ScenarioComponentRole.ACCUMULATOR, metadata={"k": 1})
        assert isinstance(spec.metadata, types.MappingProxyType)

    def test_metadata_none_accepted(self) -> None:
        spec = ScenarioComponentSpec("acc", ScenarioComponentRole.ACCUMULATOR, metadata=None)
        assert spec.metadata is None

    def test_tags_normalized_from_list(self) -> None:
        spec = ScenarioComponentSpec(
            "acc", ScenarioComponentRole.ACCUMULATOR, tags=["t1", "t2"]  # type: ignore[arg-type]
        )
        assert spec.tags == ("t1", "t2")

    def test_tags_default_empty_tuple(self) -> None:
        spec = ScenarioComponentSpec("acc", ScenarioComponentRole.ACCUMULATOR)
        assert spec.tags == ()

    def test_tags_reject_non_string_element(self) -> None:
        with pytest.raises(TypeError, match=r"tags\[1\].*str"):
            ScenarioComponentSpec(
                "acc",
                ScenarioComponentRole.ACCUMULATOR,
                tags=("valid", 2),  # type: ignore[arg-type]
            )

    def test_tags_reject_empty_element(self) -> None:
        with pytest.raises(ValueError, match=r"tags\[0\].*non-empty"):
            ScenarioComponentSpec("acc", ScenarioComponentRole.ACCUMULATOR, tags=("",))

    def test_frozen_immutable(self) -> None:
        spec = ScenarioComponentSpec("acc", ScenarioComponentRole.ACCUMULATOR)
        with pytest.raises((AttributeError, TypeError)):
            spec.component_id = "other"  # type: ignore[misc]

    def test_all_roles_constructible(self) -> None:
        for role in ScenarioComponentRole:
            s = ScenarioComponentSpec(f"c_{role.name}", role)
            assert s.role is role


# ===========================================================================
# ScenarioNodeSpec
# ===========================================================================


class TestScenarioNodeSpec:
    def test_valid_construction(self) -> None:
        spec = ScenarioNodeSpec("n_out")
        assert spec.node_id == "n_out"
        assert spec.metadata is None

    def test_empty_id_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ScenarioNodeSpec("")

    def test_whitespace_id_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ScenarioNodeSpec("   ")

    def test_non_str_id_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="str"):
            ScenarioNodeSpec(42)  # type: ignore[arg-type]

    def test_metadata_defensive_copy(self) -> None:
        original = {"desc": "inlet"}
        spec = ScenarioNodeSpec("n", metadata=original)
        original["desc"] = "changed"
        assert spec.metadata is not None
        assert spec.metadata["desc"] == "inlet"

    def test_metadata_read_only(self) -> None:
        spec = ScenarioNodeSpec("n", metadata={"k": 1})
        with pytest.raises((TypeError, AttributeError)):
            spec.metadata["k"] = 99  # type: ignore[index]

    def test_metadata_is_mapping_proxy(self) -> None:
        spec = ScenarioNodeSpec("n", metadata={"k": 1})
        assert isinstance(spec.metadata, types.MappingProxyType)

    def test_frozen_immutable(self) -> None:
        spec = ScenarioNodeSpec("n_out")
        with pytest.raises((AttributeError, TypeError)):
            spec.node_id = "other"  # type: ignore[misc]


# ===========================================================================
# ScenarioConnectionSpec
# ===========================================================================


class TestScenarioConnectionSpec:
    def test_valid_construction(self) -> None:
        conn = ScenarioConnectionSpec("pump", "n_in", "n_out")
        assert conn.component_id == "pump"
        assert conn.inlet_node_id == "n_in"
        assert conn.outlet_node_id == "n_out"
        assert conn.label is None

    def test_valid_with_label(self) -> None:
        conn = ScenarioConnectionSpec("pump", "n_in", "n_out", label="pump_conn")
        assert conn.label == "pump_conn"

    def test_empty_component_id_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ScenarioConnectionSpec("", "n_in", "n_out")

    def test_empty_inlet_node_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ScenarioConnectionSpec("pump", "", "n_out")

    def test_empty_outlet_node_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ScenarioConnectionSpec("pump", "n_in", "")

    def test_non_str_component_id_raises(self) -> None:
        with pytest.raises(TypeError, match="str"):
            ScenarioConnectionSpec(1, "n_in", "n_out")  # type: ignore[arg-type]

    def test_self_loop_raises(self) -> None:
        with pytest.raises(ValueError, match="must differ"):
            ScenarioConnectionSpec("pump", "n", "n")

    def test_frozen_immutable(self) -> None:
        conn = ScenarioConnectionSpec("pump", "n_in", "n_out")
        with pytest.raises((AttributeError, TypeError)):
            conn.component_id = "other"  # type: ignore[misc]


# ===========================================================================
# ScenarioBranchSpec
# ===========================================================================


class TestScenarioBranchSpec:
    def test_valid_construction(self) -> None:
        branch = ScenarioBranchSpec("a", "n_split", "n_merge", ("comp_a",))
        assert branch.branch_id == "a"
        assert branch.inlet_node_id == "n_split"
        assert branch.outlet_node_id == "n_merge"
        assert branch.component_ids == ("comp_a",)
        assert branch.metadata is None

    def test_empty_branch_id_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ScenarioBranchSpec("", "n_split", "n_merge", ("c",))

    def test_empty_inlet_node_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ScenarioBranchSpec("a", "", "n_merge", ("c",))

    def test_empty_outlet_node_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ScenarioBranchSpec("a", "n_split", "", ("c",))

    def test_empty_component_ids_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ScenarioBranchSpec("a", "n_split", "n_merge", ())

    def test_component_ids_normalized_from_list(self) -> None:
        branch = ScenarioBranchSpec("a", "n_split", "n_merge", ["c1", "c2"])  # type: ignore[arg-type]
        assert branch.component_ids == ("c1", "c2")

    def test_self_loop_boundary_raises(self) -> None:
        with pytest.raises(ValueError, match="must differ"):
            ScenarioBranchSpec("a", "n", "n", ("c",))

    def test_duplicate_component_ids_raise(self) -> None:
        with pytest.raises(ValueError, match="duplicate component ID"):
            ScenarioBranchSpec("a", "n_split", "n_merge", ("c", "c"))

    def test_metadata_defensive_copy(self) -> None:
        original = {"info": "test"}
        branch = ScenarioBranchSpec("a", "n_split", "n_merge", ("c",), metadata=original)
        original["info"] = "changed"
        assert branch.metadata is not None
        assert branch.metadata["info"] == "test"

    def test_metadata_read_only(self) -> None:
        branch = ScenarioBranchSpec("a", "n_split", "n_merge", ("c",), metadata={"k": 1})
        with pytest.raises((TypeError, AttributeError)):
            branch.metadata["k"] = 99  # type: ignore[index]

    def test_frozen_immutable(self) -> None:
        branch = ScenarioBranchSpec("a", "n_split", "n_merge", ("c",))
        with pytest.raises((AttributeError, TypeError)):
            branch.branch_id = "b"  # type: ignore[misc]


# ===========================================================================
# ConfigurableScenarioSpec validation
# ===========================================================================


class TestConfigurableScenarioSpec:
    def test_minimal_valid_construction(self) -> None:
        spec = _minimal_single_loop_spec()
        assert spec.scenario_id == "loop"
        assert len(spec.components) == 4
        assert len(spec.nodes) == 4
        assert len(spec.connections) == 4
        assert spec.branches == ()

    def test_empty_scenario_id_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ConfigurableScenarioSpec(
                scenario_id="",
                components=(ScenarioComponentSpec("a", ScenarioComponentRole.GENERIC),),
                nodes=(ScenarioNodeSpec("n1"), ScenarioNodeSpec("n2")),
                connections=(ScenarioConnectionSpec("a", "n1", "n2"),),
            )

    def test_duplicate_component_ids_raises(self) -> None:
        comp = ScenarioComponentSpec("acc", ScenarioComponentRole.ACCUMULATOR)
        with pytest.raises(ValueError, match="duplicate component_id"):
            ConfigurableScenarioSpec(
                scenario_id="s",
                components=(comp, comp),
                nodes=(ScenarioNodeSpec("n1"), ScenarioNodeSpec("n2")),
                connections=(ScenarioConnectionSpec("acc", "n1", "n2"),),
            )

    def test_duplicate_node_ids_raises(self) -> None:
        node = ScenarioNodeSpec("n")
        with pytest.raises(ValueError, match="duplicate node_id"):
            ConfigurableScenarioSpec(
                scenario_id="s",
                components=(ScenarioComponentSpec("c", ScenarioComponentRole.GENERIC),),
                nodes=(node, node, ScenarioNodeSpec("n2")),
                connections=(ScenarioConnectionSpec("c", "n", "n2"),),
            )

    def test_connection_unknown_component_raises(self) -> None:
        with pytest.raises(ValueError, match="does not reference a declared component"):
            ConfigurableScenarioSpec(
                scenario_id="s",
                components=(ScenarioComponentSpec("a", ScenarioComponentRole.GENERIC),),
                nodes=(ScenarioNodeSpec("n1"), ScenarioNodeSpec("n2")),
                connections=(ScenarioConnectionSpec("unknown_comp", "n1", "n2"),),
            )

    def test_connection_unknown_inlet_node_raises(self) -> None:
        with pytest.raises(ValueError, match="does not reference a declared node"):
            ConfigurableScenarioSpec(
                scenario_id="s",
                components=(ScenarioComponentSpec("a", ScenarioComponentRole.GENERIC),),
                nodes=(ScenarioNodeSpec("n1"), ScenarioNodeSpec("n2")),
                connections=(ScenarioConnectionSpec("a", "unknown_node", "n2"),),
            )

    def test_connection_unknown_outlet_node_raises(self) -> None:
        with pytest.raises(ValueError, match="does not reference a declared node"):
            ConfigurableScenarioSpec(
                scenario_id="s",
                components=(ScenarioComponentSpec("a", ScenarioComponentRole.GENERIC),),
                nodes=(ScenarioNodeSpec("n1"), ScenarioNodeSpec("n2")),
                connections=(ScenarioConnectionSpec("a", "n1", "unknown_node"),),
            )

    def test_duplicate_connection_component_raises(self) -> None:
        with pytest.raises(ValueError, match="duplicate component_id"):
            ConfigurableScenarioSpec(
                scenario_id="s",
                components=(
                    ScenarioComponentSpec("a", ScenarioComponentRole.GENERIC),
                    ScenarioComponentSpec("b", ScenarioComponentRole.GENERIC),
                ),
                nodes=(ScenarioNodeSpec("n1"), ScenarioNodeSpec("n2"), ScenarioNodeSpec("n3")),
                connections=(
                    ScenarioConnectionSpec("a", "n1", "n2"),
                    ScenarioConnectionSpec("a", "n2", "n3"),
                ),
            )

    def test_missing_component_connection_raises(self) -> None:
        with pytest.raises(ValueError, match="missing component IDs"):
            ConfigurableScenarioSpec(
                scenario_id="s",
                components=(
                    ScenarioComponentSpec("a", ScenarioComponentRole.GENERIC),
                    ScenarioComponentSpec("b", ScenarioComponentRole.GENERIC),
                ),
                nodes=(ScenarioNodeSpec("n1"), ScenarioNodeSpec("n2")),
                connections=(ScenarioConnectionSpec("a", "n1", "n2"),),
            )

    def test_components_ordering_preserved(self) -> None:
        spec = _minimal_single_loop_spec()
        ids = [c.component_id for c in spec.components]
        assert ids == ["accumulator", "pump", "evaporator", "condenser"]

    def test_nodes_ordering_preserved(self) -> None:
        spec = _minimal_single_loop_spec()
        ids = [n.node_id for n in spec.nodes]
        assert ids == ["n_acc_out", "n_pump_out", "n_evap_out", "n_cond_out"]

    def test_lists_normalized_to_tuples(self) -> None:
        spec = ConfigurableScenarioSpec(
            scenario_id="s",
            components=[ScenarioComponentSpec("a", ScenarioComponentRole.GENERIC)],  # type: ignore[arg-type]
            nodes=[ScenarioNodeSpec("n1"), ScenarioNodeSpec("n2")],  # type: ignore[arg-type]
            connections=[ScenarioConnectionSpec("a", "n1", "n2")],  # type: ignore[arg-type]
        )
        assert isinstance(spec.components, tuple)
        assert isinstance(spec.nodes, tuple)
        assert isinstance(spec.connections, tuple)
        assert isinstance(spec.branches, tuple)

    def test_duplicate_branch_ids_raises(self) -> None:
        with pytest.raises(ValueError, match="duplicate branch_id"):
            ConfigurableScenarioSpec(
                scenario_id="s",
                components=(
                    ScenarioComponentSpec("a", ScenarioComponentRole.GENERIC),
                    ScenarioComponentSpec("b", ScenarioComponentRole.GENERIC),
                ),
                nodes=(
                    ScenarioNodeSpec("n1"),
                    ScenarioNodeSpec("n2"),
                    ScenarioNodeSpec("n3"),
                ),
                connections=(
                    ScenarioConnectionSpec("a", "n1", "n2"),
                    ScenarioConnectionSpec("b", "n2", "n3"),
                ),
                branches=(
                    ScenarioBranchSpec("x", "n1", "n3", ("a", "b")),
                    ScenarioBranchSpec("x", "n1", "n3", ("a", "b")),
                ),
            )

    def test_branch_unknown_inlet_node_raises(self) -> None:
        with pytest.raises(ValueError, match="does not reference a declared node"):
            ConfigurableScenarioSpec(
                scenario_id="s",
                components=(ScenarioComponentSpec("a", ScenarioComponentRole.GENERIC),),
                nodes=(ScenarioNodeSpec("n1"), ScenarioNodeSpec("n2")),
                connections=(ScenarioConnectionSpec("a", "n1", "n2"),),
                branches=(ScenarioBranchSpec("br", "no_such_node", "n2", ("a",)),),
            )

    def test_branch_unknown_outlet_node_raises(self) -> None:
        with pytest.raises(ValueError, match="does not reference a declared node"):
            ConfigurableScenarioSpec(
                scenario_id="s",
                components=(ScenarioComponentSpec("a", ScenarioComponentRole.GENERIC),),
                nodes=(ScenarioNodeSpec("n1"), ScenarioNodeSpec("n2")),
                connections=(ScenarioConnectionSpec("a", "n1", "n2"),),
                branches=(ScenarioBranchSpec("br", "n1", "no_such_node", ("a",)),),
            )

    def test_branch_unknown_component_raises(self) -> None:
        with pytest.raises(ValueError, match="does not reference a declared component"):
            ConfigurableScenarioSpec(
                scenario_id="s",
                components=(ScenarioComponentSpec("a", ScenarioComponentRole.GENERIC),),
                nodes=(ScenarioNodeSpec("n1"), ScenarioNodeSpec("n2")),
                connections=(ScenarioConnectionSpec("a", "n1", "n2"),),
                branches=(ScenarioBranchSpec("br", "n1", "n2", ("no_such_comp",)),),
            )

    def test_branch_component_order_must_follow_connections(self) -> None:
        with pytest.raises(ValueError, match="does not continue"):
            ConfigurableScenarioSpec(
                scenario_id="s",
                components=(
                    ScenarioComponentSpec("a", ScenarioComponentRole.GENERIC),
                    ScenarioComponentSpec("b", ScenarioComponentRole.GENERIC),
                ),
                nodes=(
                    ScenarioNodeSpec("n1"),
                    ScenarioNodeSpec("n2"),
                    ScenarioNodeSpec("n3"),
                ),
                connections=(
                    ScenarioConnectionSpec("a", "n1", "n2"),
                    ScenarioConnectionSpec("b", "n2", "n3"),
                ),
                branches=(ScenarioBranchSpec("br", "n1", "n3", ("b", "a")),),
            )

    def test_branch_component_path_must_end_at_declared_outlet(self) -> None:
        with pytest.raises(ValueError, match="component path ends"):
            ConfigurableScenarioSpec(
                scenario_id="s",
                components=(ScenarioComponentSpec("a", ScenarioComponentRole.GENERIC),),
                nodes=(
                    ScenarioNodeSpec("n1"),
                    ScenarioNodeSpec("n2"),
                    ScenarioNodeSpec("n3"),
                ),
                connections=(ScenarioConnectionSpec("a", "n1", "n2"),),
                branches=(ScenarioBranchSpec("br", "n1", "n3", ("a",)),),
            )

    def test_metadata_defensive_copy(self) -> None:
        original = {"k": "v"}
        spec = ConfigurableScenarioSpec(
            scenario_id="s",
            components=(ScenarioComponentSpec("a", ScenarioComponentRole.GENERIC),),
            nodes=(ScenarioNodeSpec("n1"), ScenarioNodeSpec("n2")),
            connections=(ScenarioConnectionSpec("a", "n1", "n2"),),
            metadata=original,
        )
        original["k"] = "changed"
        assert spec.metadata is not None
        assert spec.metadata["k"] == "v"

    def test_spec_frozen_immutable(self) -> None:
        spec = _minimal_single_loop_spec()
        with pytest.raises((AttributeError, TypeError)):
            spec.scenario_id = "other"  # type: ignore[misc]

    def test_two_branch_spec_valid(self) -> None:
        spec = _minimal_two_branch_spec()
        assert len(spec.components) == 7
        assert len(spec.nodes) == 6
        assert len(spec.connections) == 7
        assert len(spec.branches) == 2


# ===========================================================================
# build_configurable_scenario — single-loop build results
# ===========================================================================


class TestBuildConfigurableScenarioSingleLoop:
    def test_builds_successfully(self) -> None:
        spec = _minimal_single_loop_spec()
        result = build_configurable_scenario(spec)
        assert isinstance(result, ConfigurableScenarioBuildResult)

    def test_graph_node_count(self) -> None:
        spec = _minimal_single_loop_spec()
        result = build_configurable_scenario(spec)
        assert len(list(result.graph.node_ids())) == 4

    def test_graph_component_count(self) -> None:
        spec = _minimal_single_loop_spec()
        result = build_configurable_scenario(spec)
        assert len(list(result.graph.instance_ids())) == 4

    def test_unknown_count(self) -> None:
        spec = _minimal_single_loop_spec()
        result = build_configurable_scenario(spec)
        assert result.assembly.unknowns.count() == 8

    def test_residual_count(self) -> None:
        spec = _minimal_single_loop_spec()
        result = build_configurable_scenario(spec)
        assert result.assembly.residuals.count() == 8

    def test_unknown_names_deterministic(self) -> None:
        spec = _minimal_single_loop_spec()
        r1 = build_configurable_scenario(spec)
        r2 = build_configurable_scenario(spec)
        assert r1.unknown_names == r2.unknown_names

    def test_residual_names_deterministic(self) -> None:
        spec = _minimal_single_loop_spec()
        r1 = build_configurable_scenario(spec)
        r2 = build_configurable_scenario(spec)
        assert r1.residual_names == r2.residual_names

    def test_unknown_names_follow_convention(self) -> None:
        spec = _minimal_single_loop_spec()
        result = build_configurable_scenario(spec)
        names = result.unknown_names
        assert "mdot:accumulator" in names
        assert "mdot:pump" in names
        assert "mdot:evaporator" in names
        assert "mdot:condenser" in names
        assert "P:n_acc_out" in names
        assert "P:n_pump_out" in names
        assert "P:n_evap_out" in names
        assert "P:n_cond_out" in names

    def test_residual_names_follow_convention(self) -> None:
        spec = _minimal_single_loop_spec()
        result = build_configurable_scenario(spec)
        names = result.residual_names
        assert "mass_balance:n_acc_out" in names
        assert "mass_balance:n_pump_out" in names
        assert "mass_balance:n_evap_out" in names
        assert "mass_balance:n_cond_out" in names
        assert "pressure_drop:accumulator" in names
        assert "pressure_drop:pump" in names
        assert "pressure_drop:evaporator" in names
        assert "pressure_drop:condenser" in names

    def test_unknown_names_is_tuple(self) -> None:
        result = build_configurable_scenario(_minimal_single_loop_spec())
        assert isinstance(result.unknown_names, tuple)

    def test_residual_names_is_tuple(self) -> None:
        result = build_configurable_scenario(_minimal_single_loop_spec())
        assert isinstance(result.residual_names, tuple)

    def test_component_ids_in_spec_order(self) -> None:
        spec = _minimal_single_loop_spec()
        result = build_configurable_scenario(spec)
        assert result.component_ids[0] == ComponentInstanceId("accumulator")
        assert result.component_ids[1] == ComponentInstanceId("pump")
        assert result.component_ids[2] == ComponentInstanceId("evaporator")
        assert result.component_ids[3] == ComponentInstanceId("condenser")

    def test_node_ids_in_spec_order(self) -> None:
        spec = _minimal_single_loop_spec()
        result = build_configurable_scenario(spec)
        assert result.node_ids[0] == GraphNodeId("n_acc_out")
        assert result.node_ids[1] == GraphNodeId("n_pump_out")
        assert result.node_ids[2] == GraphNodeId("n_evap_out")
        assert result.node_ids[3] == GraphNodeId("n_cond_out")

    def test_branch_ids_empty_for_single_loop(self) -> None:
        result = build_configurable_scenario(_minimal_single_loop_spec())
        assert result.branch_ids == ()

    def test_result_immutable(self) -> None:
        result = build_configurable_scenario(_minimal_single_loop_spec())
        with pytest.raises((AttributeError, TypeError)):
            result.unknown_names = ()  # type: ignore[misc]

    def test_limitations_is_tuple_of_strings(self) -> None:
        result = build_configurable_scenario(_minimal_single_loop_spec())
        assert isinstance(result.limitations, tuple)
        assert all(isinstance(s, str) for s in result.limitations)
        assert len(result.limitations) >= 1

    def test_limitations_mention_declaration_only(self) -> None:
        result = build_configurable_scenario(_minimal_single_loop_spec())
        combined = " ".join(result.limitations).lower()
        assert "declaration" in combined or "no physical" in combined

    def test_require_closed_loop_true_passes_for_loop(self) -> None:
        spec = _minimal_single_loop_spec()
        result = build_configurable_scenario(spec, require_closed_loop=True)
        assert result.assembly.unknowns.count() == 8

    def test_spec_preserved_on_result(self) -> None:
        spec = _minimal_single_loop_spec()
        result = build_configurable_scenario(spec)
        assert result.spec is spec

    def test_binding_context_references_graph(self) -> None:
        result = build_configurable_scenario(_minimal_single_loop_spec())
        assert result.binding_context.graph is result.graph

    def test_binding_context_references_assembly(self) -> None:
        result = build_configurable_scenario(_minimal_single_loop_spec())
        assert result.binding_context.assembly is result.assembly

    def test_invalid_spec_type_raises(self) -> None:
        with pytest.raises(TypeError, match="ConfigurableScenarioSpec"):
            build_configurable_scenario("not a spec")  # type: ignore[arg-type]


# ===========================================================================
# build_configurable_scenario — two-branch build results
# ===========================================================================


class TestBuildConfigurableScenarioTwoBranch:
    def test_builds_successfully(self) -> None:
        spec = _minimal_two_branch_spec()
        result = build_configurable_scenario(spec)
        assert isinstance(result, ConfigurableScenarioBuildResult)

    def test_graph_node_count(self) -> None:
        result = build_configurable_scenario(_minimal_two_branch_spec())
        assert len(list(result.graph.node_ids())) == 6

    def test_graph_component_count(self) -> None:
        result = build_configurable_scenario(_minimal_two_branch_spec())
        assert len(list(result.graph.instance_ids())) == 7

    def test_unknown_count(self) -> None:
        result = build_configurable_scenario(_minimal_two_branch_spec())
        assert result.assembly.unknowns.count() == 13

    def test_residual_count(self) -> None:
        result = build_configurable_scenario(_minimal_two_branch_spec())
        assert result.assembly.residuals.count() == 13

    def test_branch_ids_present(self) -> None:
        result = build_configurable_scenario(_minimal_two_branch_spec())
        assert result.branch_ids == ("a", "b")

    def test_unknown_names_deterministic(self) -> None:
        spec = _minimal_two_branch_spec()
        r1 = build_configurable_scenario(spec)
        r2 = build_configurable_scenario(spec)
        assert r1.unknown_names == r2.unknown_names

    def test_residual_names_deterministic(self) -> None:
        spec = _minimal_two_branch_spec()
        r1 = build_configurable_scenario(spec)
        r2 = build_configurable_scenario(spec)
        assert r1.residual_names == r2.residual_names

    def test_unknown_names_cover_all_components_and_nodes(self) -> None:
        spec = _minimal_two_branch_spec()
        result = build_configurable_scenario(spec)
        names = result.unknown_names
        for comp in spec.components:
            assert f"mdot:{comp.component_id}" in names
        for node in spec.nodes:
            assert f"P:{node.node_id}" in names

    def test_residual_names_cover_all_nodes_and_components(self) -> None:
        spec = _minimal_two_branch_spec()
        result = build_configurable_scenario(spec)
        names = result.residual_names
        for node in spec.nodes:
            assert f"mass_balance:{node.node_id}" in names
        for comp in spec.components:
            assert f"pressure_drop:{comp.component_id}" in names


# ===========================================================================
# build_configurable_scenario_report
# ===========================================================================


class TestBuildConfigurableScenarioReport:
    def _result(self) -> ConfigurableScenarioBuildResult:
        return build_configurable_scenario(_minimal_single_loop_spec())

    def test_report_is_dict(self) -> None:
        report = build_configurable_scenario_report(self._result())
        assert isinstance(report, dict)

    def test_report_json_serializable(self) -> None:
        report = build_configurable_scenario_report(self._result())
        encoded = json.dumps(report)
        assert isinstance(encoded, str)

    def test_report_has_no_solve(self) -> None:
        report = build_configurable_scenario_report(self._result())
        assert report["no_solve"] is True

    def test_report_status_declaration_only(self) -> None:
        report = build_configurable_scenario_report(self._result())
        assert report["status"] == "declaration_only"

    def test_report_has_limitations(self) -> None:
        report = build_configurable_scenario_report(self._result())
        assert "limitations" in report
        assert isinstance(report["limitations"], list)
        assert len(report["limitations"]) >= 1  # type: ignore[arg-type]

    def test_report_has_unknown_count(self) -> None:
        report = build_configurable_scenario_report(self._result())
        assert report["unknown_count"] == 8

    def test_report_has_residual_count(self) -> None:
        report = build_configurable_scenario_report(self._result())
        assert report["residual_count"] == 8

    def test_report_has_scenario_id(self) -> None:
        report = build_configurable_scenario_report(self._result())
        assert report["scenario_id"] == "loop"

    def test_report_has_component_ids(self) -> None:
        report = build_configurable_scenario_report(self._result())
        assert "component_ids" in report
        assert isinstance(report["component_ids"], list)

    def test_report_has_node_ids(self) -> None:
        report = build_configurable_scenario_report(self._result())
        assert "node_ids" in report
        assert isinstance(report["node_ids"], list)

    def test_report_has_component_roles(self) -> None:
        report = build_configurable_scenario_report(self._result())
        assert "component_roles" in report
        roles = report["component_roles"]
        assert isinstance(roles, dict)
        assert roles["accumulator"] == "accumulator"

    def test_report_has_unknown_names(self) -> None:
        report = build_configurable_scenario_report(self._result())
        assert "unknown_names" in report
        assert isinstance(report["unknown_names"], list)

    def test_report_has_residual_names(self) -> None:
        report = build_configurable_scenario_report(self._result())
        assert "residual_names" in report
        assert isinstance(report["residual_names"], list)

    def test_report_mentions_closure_domains(self) -> None:
        report = build_configurable_scenario_report(self._result())
        assert "closure_domains_available_later" in report

    def test_report_invalid_input_raises(self) -> None:
        with pytest.raises(TypeError, match="ConfigurableScenarioBuildResult"):
            build_configurable_scenario_report("not a result")  # type: ignore[arg-type]

    def test_two_branch_report_json_serializable(self) -> None:
        result = build_configurable_scenario(_minimal_two_branch_spec())
        report = build_configurable_scenario_report(result)
        encoded = json.dumps(report)
        assert isinstance(encoded, str)

    def test_two_branch_report_has_branches(self) -> None:
        result = build_configurable_scenario(_minimal_two_branch_spec())
        report = build_configurable_scenario_report(result)
        assert report["branch_count"] == 2
        assert report["branch_ids"] == ["a", "b"]


# ===========================================================================
# Architecture boundary assertions
# ===========================================================================


class TestArchitectureBoundaries:
    def _module_executable_lines(self) -> list[str]:
        """Return non-comment, non-docstring lines from the module source."""
        import mpl_sim.network.configurable_scenarios as mod

        src = getattr(mod, "__file__", "")
        if not src:
            return []
        lines = []
        in_docstring = False
        docstring_char = None
        with open(src) as f:
            for raw_line in f:
                line = raw_line.strip()
                # Skip blank lines and pure single-line comments.
                if not line or line.startswith("#"):
                    continue
                # Track triple-quoted docstrings.
                for dq in ('"""', "'''"):
                    if dq in line:
                        count = line.count(dq)
                        if in_docstring and docstring_char == dq:
                            in_docstring = count % 2 == 0
                            docstring_char = None if not in_docstring else dq
                        elif not in_docstring and count % 2 == 1:
                            in_docstring = True
                            docstring_char = dq
                        break
                if in_docstring:
                    continue
                lines.append(line)
        return lines

    def test_no_coolprop_import_in_executable_code(self) -> None:
        import mpl_sim.network.configurable_scenarios as mod

        assert "CoolProp" not in dir(mod)
        assert not hasattr(mod, "CoolProp")
        src = getattr(mod, "__file__", "")
        if src:
            with open(src) as f:
                text = f.read()
            import re

            # Match only import lines, not documentation.
            import_lines = [ln for ln in text.splitlines() if re.match(r"^\s*(import|from)\s+", ln)]
            for ln in import_lines:
                assert "CoolProp" not in ln, f"CoolProp found in import: {ln!r}"
                assert "PropertyBackend" not in ln, f"PropertyBackend found in import: {ln!r}"

    def test_no_systemstate_or_fluidstate_in_executable_code(self) -> None:
        import mpl_sim.network.configurable_scenarios as mod

        assert not hasattr(mod, "SystemState")
        assert not hasattr(mod, "FluidState")
        src = getattr(mod, "__file__", "")
        if src:
            with open(src) as f:
                text = f.read()
            import re

            import_lines = [ln for ln in text.splitlines() if re.match(r"^\s*(import|from)\s+", ln)]
            for ln in import_lines:
                assert "SystemState" not in ln, f"SystemState found in import: {ln!r}"
                assert "FluidState" not in ln, f"FluidState found in import: {ln!r}"

    def test_no_contribute_defined_in_module(self) -> None:
        import mpl_sim.network.configurable_scenarios as mod

        assert not hasattr(mod, "contribute")
        src = getattr(mod, "__file__", "")
        if src:
            with open(src) as f:
                text = f.read()
            import re

            # Only match actual def contribute lines (not docstring mentions).
            defs = re.findall(r"^\s*def contribute\b", text, re.MULTILINE)
            assert not defs, f"def contribute found in module: {defs}"

    def test_result_has_no_solve_method(self) -> None:
        result = build_configurable_scenario(_minimal_single_loop_spec())
        assert not hasattr(result, "solve")

    def test_spec_has_no_solve_method(self) -> None:
        spec = _minimal_single_loop_spec()
        assert not hasattr(spec, "solve")

    def test_graph_has_no_solve_method(self) -> None:
        result = build_configurable_scenario(_minimal_single_loop_spec())
        assert not hasattr(result.graph, "solve")

    def test_roles_do_not_dispatch_physics(self) -> None:
        for role in ScenarioComponentRole:
            spec_comp = ScenarioComponentSpec(f"c_{role.name}", role)
            assert spec_comp.role is role
            assert not hasattr(spec_comp, "evaluate")
            assert not hasattr(spec_comp, "contribute")
