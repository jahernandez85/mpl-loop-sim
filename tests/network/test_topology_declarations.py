"""Block 15C.1 + Block 15C.3 — Topology Declaration tests.

Tests for junction/manifold declaration foundation (15C.1) and valve/local
pressure-loss element declaration (15C.3).

No production component physics are executed.  No SystemState is assembled.
No FluidState is created.  No forbidden imports in the source modules.

Coverage:

15C.1 — JunctionDeclaration:
 1. split junction declaration builds
 2. merge junction declaration builds
 3. junction declaration with two branch labels builds
 4. junction declaration with more than two branch labels builds
 5. junction declaration is frozen (immutable)
 6. metadata is defensively copied (mutation of source does not affect stored proxy)
 7. metadata proxy is read-only (cannot set items)
 8. duplicate branch labels rejected
 9. fewer than two branch labels rejected
10. empty junction_id rejected
11. whitespace-only junction_id rejected
12. wrong type for junction_id rejected
13. wrong type for role rejected
14. wrong type for branch_labels item rejected
15. empty branch label item rejected
16. whitespace-only branch label item rejected
17. wrong type for metadata rejected
18. no physical values are stored (no equations, no residuals)

15C.1 — ManifoldDeclaration:
19. split manifold declaration builds
20. merge manifold declaration builds
21. manifold with two branches builds
22. manifold is frozen (immutable)
23. metadata is defensively copied
24. metadata proxy is read-only
25. duplicate branch labels rejected
26. duplicate branch node IDs rejected
27. common_node ID appearing in branch_nodes rejected
28. mismatched branch_nodes / branch_labels lengths rejected
29. fewer than two branch nodes rejected
30. empty manifold_id rejected
31. whitespace-only manifold_id rejected
32. wrong type for manifold_id rejected
33. wrong type for role rejected
34. wrong type for common_node rejected
35. wrong type for branch_nodes item rejected
36. empty branch label rejected
37. wrong type for branch label item rejected
38. wrong type for metadata rejected

15C.3 — ValveDeclaration:
39. valve declaration builds with explicit inlet/outlet nodes
40. valve declaration with optional residual_name builds
41. valve declaration without residual_name (None) builds
42. valve declaration is frozen (immutable)
43. metadata is defensively copied
44. metadata proxy is read-only
45. wrong type for valve_id rejected
46. wrong type for inlet_node rejected
47. wrong type for outlet_node rejected
48. inlet_node equals outlet_node rejected
49. wrong type for residual_name rejected
50. empty residual_name rejected
51. whitespace-only residual_name rejected
52. wrong type for metadata rejected
53. no pressure-loss equation or coefficient is stored
54. no physical flow coefficient is stored

Boundary tests (AST-based):
55. topology_declarations module: no import of CoolProp
56. topology_declarations module: no import of PropertyBackend
57. topology_declarations module: no import of CorrelationRegistry
58. topology_declarations module: no import of mpl_sim.components
59. topology_declarations module: no import of mpl_sim.properties
60. topology_declarations module: no import of SystemState
61. topology_declarations module: no import of FluidState
62. topology_declarations module: no contribute attribute call
63. this test file: no import of CoolProp
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from mpl_sim.network.graph import ComponentInstanceId, GraphNodeId
from mpl_sim.network.topology_declarations import (
    JunctionDeclaration,
    JunctionRole,
    ManifoldDeclaration,
    ValveDeclaration,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _node(s: str) -> GraphNodeId:
    return GraphNodeId(s)


def _cid(s: str) -> ComponentInstanceId:
    return ComponentInstanceId(s)


# ---------------------------------------------------------------------------
# 15C.1 — JunctionDeclaration
# ---------------------------------------------------------------------------


class TestJunctionDeclaration:
    def test_split_builds(self) -> None:
        jd = JunctionDeclaration(
            junction_id="split_1",
            role=JunctionRole.SPLIT,
            branch_labels=("a", "b"),
        )
        assert jd.junction_id == "split_1"
        assert jd.role is JunctionRole.SPLIT
        assert jd.branch_labels == ("a", "b")
        assert jd.metadata is None

    def test_merge_builds(self) -> None:
        jd = JunctionDeclaration(
            junction_id="merge_1",
            role=JunctionRole.MERGE,
            branch_labels=("x", "y"),
        )
        assert jd.role is JunctionRole.MERGE

    def test_two_branch_labels(self) -> None:
        jd = JunctionDeclaration("j1", JunctionRole.SPLIT, ("a", "b"))
        assert len(jd.branch_labels) == 2

    def test_more_than_two_branch_labels(self) -> None:
        jd = JunctionDeclaration("j1", JunctionRole.SPLIT, ("a", "b", "c"))
        assert len(jd.branch_labels) == 3

    def test_frozen(self) -> None:
        jd = JunctionDeclaration("j1", JunctionRole.SPLIT, ("a", "b"))
        with pytest.raises((AttributeError, TypeError)):
            jd.junction_id = "other"  # type: ignore[misc]

    def test_metadata_defensive_copy(self) -> None:
        src: dict[str, object] = {"k": 1}
        jd = JunctionDeclaration("j1", JunctionRole.SPLIT, ("a", "b"), metadata=src)
        src["k"] = 999
        assert jd.metadata is not None
        assert jd.metadata["k"] == 1

    def test_metadata_proxy_readonly(self) -> None:
        jd = JunctionDeclaration("j1", JunctionRole.SPLIT, ("a", "b"), metadata={"k": 1})
        with pytest.raises(TypeError):
            jd.metadata["new"] = "x"  # type: ignore[index]

    def test_duplicate_branch_labels_rejected(self) -> None:
        with pytest.raises(ValueError, match="distinct"):
            JunctionDeclaration("j1", JunctionRole.SPLIT, ("a", "a"))

    def test_fewer_than_two_labels_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least two"):
            JunctionDeclaration("j1", JunctionRole.SPLIT, ("a",))

    def test_empty_junction_id_rejected(self) -> None:
        with pytest.raises(ValueError):
            JunctionDeclaration("", JunctionRole.SPLIT, ("a", "b"))

    def test_whitespace_only_junction_id_rejected(self) -> None:
        with pytest.raises(ValueError):
            JunctionDeclaration("   ", JunctionRole.SPLIT, ("a", "b"))

    def test_wrong_type_junction_id_rejected(self) -> None:
        with pytest.raises(TypeError):
            JunctionDeclaration(123, JunctionRole.SPLIT, ("a", "b"))  # type: ignore[arg-type]

    def test_wrong_type_role_rejected(self) -> None:
        with pytest.raises(TypeError, match="JunctionRole"):
            JunctionDeclaration("j1", "SPLIT", ("a", "b"))  # type: ignore[arg-type]

    def test_wrong_type_branch_label_item_rejected(self) -> None:
        with pytest.raises(TypeError):
            JunctionDeclaration("j1", JunctionRole.SPLIT, (1, "b"))  # type: ignore[arg-type]

    def test_empty_branch_label_rejected(self) -> None:
        with pytest.raises(ValueError):
            JunctionDeclaration("j1", JunctionRole.SPLIT, ("", "b"))

    def test_whitespace_branch_label_rejected(self) -> None:
        with pytest.raises(ValueError):
            JunctionDeclaration("j1", JunctionRole.SPLIT, ("  ", "b"))

    def test_wrong_type_metadata_rejected(self) -> None:
        with pytest.raises(TypeError, match="Mapping"):
            JunctionDeclaration("j1", JunctionRole.SPLIT, ("a", "b"), metadata=["bad"])  # type: ignore[arg-type]

    def test_no_physical_values_stored(self) -> None:
        jd = JunctionDeclaration("j1", JunctionRole.SPLIT, ("a", "b"))
        assert not hasattr(jd, "pressure_drop")
        assert not hasattr(jd, "mass_flow_split")
        assert not hasattr(jd, "kv")
        assert not hasattr(jd, "equation")


# ---------------------------------------------------------------------------
# 15C.1 — ManifoldDeclaration
# ---------------------------------------------------------------------------


class TestManifoldDeclaration:
    def _split_manifold(self) -> ManifoldDeclaration:
        return ManifoldDeclaration(
            manifold_id="split_m1",
            role=JunctionRole.SPLIT,
            common_node=_node("n_pump_out"),
            branch_nodes=(_node("n_a_in"), _node("n_b_in")),
            branch_labels=("a", "b"),
        )

    def test_split_builds(self) -> None:
        m = self._split_manifold()
        assert m.manifold_id == "split_m1"
        assert m.role is JunctionRole.SPLIT
        assert m.common_node == _node("n_pump_out")
        assert len(m.branch_nodes) == 2
        assert m.branch_labels == ("a", "b")
        assert m.metadata is None

    def test_merge_builds(self) -> None:
        m = ManifoldDeclaration(
            manifold_id="merge_m1",
            role=JunctionRole.MERGE,
            common_node=_node("n_merge_out"),
            branch_nodes=(_node("n_a_out"), _node("n_b_out")),
            branch_labels=("a", "b"),
        )
        assert m.role is JunctionRole.MERGE

    def test_two_branch_nodes_builds(self) -> None:
        m = self._split_manifold()
        assert len(m.branch_nodes) == 2

    def test_frozen(self) -> None:
        m = self._split_manifold()
        with pytest.raises((AttributeError, TypeError)):
            m.manifold_id = "other"  # type: ignore[misc]

    def test_metadata_defensive_copy(self) -> None:
        src: dict[str, object] = {"k": 1}
        m = ManifoldDeclaration(
            "m1",
            JunctionRole.SPLIT,
            _node("n_c"),
            (_node("n_a"), _node("n_b")),
            ("a", "b"),
            metadata=src,
        )
        src["k"] = 999
        assert m.metadata is not None
        assert m.metadata["k"] == 1

    def test_metadata_proxy_readonly(self) -> None:
        m = ManifoldDeclaration(
            "m1",
            JunctionRole.SPLIT,
            _node("n_c"),
            (_node("n_a"), _node("n_b")),
            ("a", "b"),
            metadata={"k": 1},
        )
        with pytest.raises(TypeError):
            m.metadata["new"] = "x"  # type: ignore[index]

    def test_duplicate_branch_labels_rejected(self) -> None:
        with pytest.raises(ValueError, match="distinct"):
            ManifoldDeclaration(
                "m1",
                JunctionRole.SPLIT,
                _node("n_c"),
                (_node("n_a"), _node("n_b")),
                ("a", "a"),
            )

    def test_duplicate_branch_node_ids_rejected(self) -> None:
        with pytest.raises(ValueError, match="distinct"):
            ManifoldDeclaration(
                "m1",
                JunctionRole.SPLIT,
                _node("n_c"),
                (_node("n_a"), _node("n_a")),
                ("a", "b"),
            )

    def test_common_node_in_branch_nodes_rejected(self) -> None:
        with pytest.raises(ValueError, match="must not appear"):
            ManifoldDeclaration(
                "m1",
                JunctionRole.SPLIT,
                _node("n_a"),
                (_node("n_a"), _node("n_b")),
                ("a", "b"),
            )

    def test_mismatched_branch_lengths_rejected(self) -> None:
        with pytest.raises(ValueError, match="same length"):
            ManifoldDeclaration(
                "m1",
                JunctionRole.SPLIT,
                _node("n_c"),
                (_node("n_a"), _node("n_b")),
                ("a",),
            )

    def test_fewer_than_two_branch_nodes_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least two"):
            ManifoldDeclaration(
                "m1",
                JunctionRole.SPLIT,
                _node("n_c"),
                (_node("n_a"),),
                ("a",),
            )

    def test_empty_manifold_id_rejected(self) -> None:
        with pytest.raises(ValueError):
            ManifoldDeclaration(
                "",
                JunctionRole.SPLIT,
                _node("n_c"),
                (_node("n_a"), _node("n_b")),
                ("a", "b"),
            )

    def test_whitespace_manifold_id_rejected(self) -> None:
        with pytest.raises(ValueError):
            ManifoldDeclaration(
                "  ",
                JunctionRole.SPLIT,
                _node("n_c"),
                (_node("n_a"), _node("n_b")),
                ("a", "b"),
            )

    def test_wrong_type_manifold_id_rejected(self) -> None:
        with pytest.raises(TypeError):
            ManifoldDeclaration(
                123,  # type: ignore[arg-type]
                JunctionRole.SPLIT,
                _node("n_c"),
                (_node("n_a"), _node("n_b")),
                ("a", "b"),
            )

    def test_wrong_type_role_rejected(self) -> None:
        with pytest.raises(TypeError, match="JunctionRole"):
            ManifoldDeclaration(
                "m1",
                "SPLIT",  # type: ignore[arg-type]
                _node("n_c"),
                (_node("n_a"), _node("n_b")),
                ("a", "b"),
            )

    def test_wrong_type_common_node_rejected(self) -> None:
        with pytest.raises(TypeError, match="GraphNodeId"):
            ManifoldDeclaration(
                "m1",
                JunctionRole.SPLIT,
                "n_c",  # type: ignore[arg-type]
                (_node("n_a"), _node("n_b")),
                ("a", "b"),
            )

    def test_wrong_type_branch_node_item_rejected(self) -> None:
        with pytest.raises(TypeError, match="GraphNodeId"):
            ManifoldDeclaration(
                "m1",
                JunctionRole.SPLIT,
                _node("n_c"),
                ("n_a", _node("n_b")),  # type: ignore[arg-type]
                ("a", "b"),
            )

    def test_empty_branch_label_rejected(self) -> None:
        with pytest.raises(ValueError):
            ManifoldDeclaration(
                "m1",
                JunctionRole.SPLIT,
                _node("n_c"),
                (_node("n_a"), _node("n_b")),
                ("", "b"),
            )

    def test_wrong_type_branch_label_item_rejected(self) -> None:
        with pytest.raises(TypeError):
            ManifoldDeclaration(
                "m1",
                JunctionRole.SPLIT,
                _node("n_c"),
                (_node("n_a"), _node("n_b")),
                (1, "b"),  # type: ignore[arg-type]
            )

    def test_wrong_type_metadata_rejected(self) -> None:
        with pytest.raises(TypeError, match="Mapping"):
            ManifoldDeclaration(
                "m1",
                JunctionRole.SPLIT,
                _node("n_c"),
                (_node("n_a"), _node("n_b")),
                ("a", "b"),
                metadata=["bad"],  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# 15C.3 — ValveDeclaration
# ---------------------------------------------------------------------------


class TestValveDeclaration:
    def test_valve_builds_with_inlet_outlet(self) -> None:
        v = ValveDeclaration(
            valve_id=_cid("valve_1"),
            inlet_node=_node("n_in"),
            outlet_node=_node("n_out"),
        )
        assert v.valve_id == _cid("valve_1")
        assert v.inlet_node == _node("n_in")
        assert v.outlet_node == _node("n_out")
        assert v.residual_name is None
        assert v.metadata is None

    def test_valve_with_residual_name_builds(self) -> None:
        v = ValveDeclaration(
            valve_id=_cid("valve_1"),
            inlet_node=_node("n_in"),
            outlet_node=_node("n_out"),
            residual_name="pressure_loss:valve_1",
        )
        assert v.residual_name == "pressure_loss:valve_1"

    def test_valve_without_residual_name(self) -> None:
        v = ValveDeclaration(
            valve_id=_cid("v1"),
            inlet_node=_node("n_in"),
            outlet_node=_node("n_out"),
            residual_name=None,
        )
        assert v.residual_name is None

    def test_frozen(self) -> None:
        v = ValveDeclaration(
            valve_id=_cid("v1"),
            inlet_node=_node("n_in"),
            outlet_node=_node("n_out"),
        )
        with pytest.raises((AttributeError, TypeError)):
            v.valve_id = _cid("other")  # type: ignore[misc]

    def test_metadata_defensive_copy(self) -> None:
        src: dict[str, object] = {"tag": "A"}
        v = ValveDeclaration(_cid("v1"), _node("n_in"), _node("n_out"), metadata=src)
        src["tag"] = "B"
        assert v.metadata is not None
        assert v.metadata["tag"] == "A"

    def test_metadata_proxy_readonly(self) -> None:
        v = ValveDeclaration(_cid("v1"), _node("n_in"), _node("n_out"), metadata={"k": 1})
        with pytest.raises(TypeError):
            v.metadata["new"] = "x"  # type: ignore[index]

    def test_wrong_type_valve_id_rejected(self) -> None:
        with pytest.raises(TypeError, match="ComponentInstanceId"):
            ValveDeclaration(
                valve_id="valve_1",  # type: ignore[arg-type]
                inlet_node=_node("n_in"),
                outlet_node=_node("n_out"),
            )

    def test_wrong_type_inlet_node_rejected(self) -> None:
        with pytest.raises(TypeError, match="GraphNodeId"):
            ValveDeclaration(
                valve_id=_cid("v1"),
                inlet_node="n_in",  # type: ignore[arg-type]
                outlet_node=_node("n_out"),
            )

    def test_wrong_type_outlet_node_rejected(self) -> None:
        with pytest.raises(TypeError, match="GraphNodeId"):
            ValveDeclaration(
                valve_id=_cid("v1"),
                inlet_node=_node("n_in"),
                outlet_node="n_out",  # type: ignore[arg-type]
            )

    def test_inlet_equals_outlet_rejected(self) -> None:
        with pytest.raises(ValueError, match="must differ"):
            ValveDeclaration(
                valve_id=_cid("v1"),
                inlet_node=_node("n_same"),
                outlet_node=_node("n_same"),
            )

    def test_wrong_type_residual_name_rejected(self) -> None:
        with pytest.raises(TypeError):
            ValveDeclaration(
                valve_id=_cid("v1"),
                inlet_node=_node("n_in"),
                outlet_node=_node("n_out"),
                residual_name=123,  # type: ignore[arg-type]
            )

    def test_empty_residual_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ValveDeclaration(
                valve_id=_cid("v1"),
                inlet_node=_node("n_in"),
                outlet_node=_node("n_out"),
                residual_name="",
            )

    def test_whitespace_residual_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ValveDeclaration(
                valve_id=_cid("v1"),
                inlet_node=_node("n_in"),
                outlet_node=_node("n_out"),
                residual_name="   ",
            )

    def test_wrong_type_metadata_rejected(self) -> None:
        with pytest.raises(TypeError, match="Mapping"):
            ValveDeclaration(
                _cid("v1"),
                _node("n_in"),
                _node("n_out"),
                metadata=["bad"],  # type: ignore[arg-type]
            )

    def test_no_pressure_loss_equation_stored(self) -> None:
        v = ValveDeclaration(_cid("v1"), _node("n_in"), _node("n_out"))
        assert not hasattr(v, "equation")
        assert not hasattr(v, "pressure_loss_law")
        assert not hasattr(v, "delta_P")

    def test_no_flow_coefficient_stored(self) -> None:
        v = ValveDeclaration(_cid("v1"), _node("n_in"), _node("n_out"))
        assert not hasattr(v, "kv")
        assert not hasattr(v, "cv")
        assert not hasattr(v, "flow_coefficient")
        assert not hasattr(v, "opening")


# ---------------------------------------------------------------------------
# Boundary tests — AST / import-level
# ---------------------------------------------------------------------------

_DECL_MODULE = (
    pathlib.Path(__file__).parent.parent.parent
    / "src"
    / "mpl_sim"
    / "network"
    / "topology_declarations.py"
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


class TestTopologyDeclarationsBoundary:
    def test_no_coolprop_import(self) -> None:
        assert not _has_import(_parse_ast(_DECL_MODULE), "CoolProp")

    def test_no_property_backend_import(self) -> None:
        assert not _has_import(_parse_ast(_DECL_MODULE), "PropertyBackend")

    def test_no_correlation_registry_import(self) -> None:
        assert not _has_import(_parse_ast(_DECL_MODULE), "CorrelationRegistry")

    def test_no_components_import(self) -> None:
        assert not _has_import(_parse_ast(_DECL_MODULE), "mpl_sim.components")

    def test_no_properties_import(self) -> None:
        assert not _has_import(_parse_ast(_DECL_MODULE), "mpl_sim.properties")

    def test_no_system_state_import(self) -> None:
        assert not _has_import(_parse_ast(_DECL_MODULE), "SystemState")

    def test_no_fluid_state_import(self) -> None:
        assert not _has_import(_parse_ast(_DECL_MODULE), "FluidState")

    def test_no_contribute_attribute_calls(self) -> None:
        assert not _has_contribute_attribute_call(_parse_ast(_DECL_MODULE))

    def test_this_file_no_coolprop_import(self) -> None:
        assert not _has_import(_parse_ast(_THIS_FILE), "CoolProp")
