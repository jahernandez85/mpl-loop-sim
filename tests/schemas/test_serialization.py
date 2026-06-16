"""Tests for schema serialization utilities — Phase 9B.

Covers: to_primitive, canonicalize, content_hash, make_serialized_object.
No CoolProp, properties, correlations, components, network, or solvers imported.
"""

from __future__ import annotations

import json
import types

import pytest

from mpl_sim.schema.primitives import SchemaVersion, SerializedObject
from mpl_sim.schema.serialization import (
    canonicalize,
    content_hash,
    make_serialized_object,
    to_primitive,
)

# ---------------------------------------------------------------------------
# Import isolation guard
# ---------------------------------------------------------------------------


def test_serialization_no_forbidden_imports() -> None:
    import ast

    import mpl_sim.schema.serialization as mod

    with open(mod.__file__, encoding="utf-8") as f:  # type: ignore[arg-type]
        text = f.read()
    tree = ast.parse(text)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.append(node.module)
    forbidden_prefixes = [
        "CoolProp",
        "coolprop",
        "mpl_sim.properties",
        "mpl_sim.correlations",
        "mpl_sim.components",
        "mpl_sim.network",
        "mpl_sim.solvers",
    ]
    for imp in imported:
        for prefix in forbidden_prefixes:
            assert not imp.startswith(prefix), f"Forbidden import: {imp!r}"


# ---------------------------------------------------------------------------
# to_primitive
# ---------------------------------------------------------------------------


class TestToPrimitive:
    def test_none(self) -> None:
        assert to_primitive(None) is None

    def test_bool(self) -> None:
        assert to_primitive(True) is True
        assert to_primitive(False) is False

    def test_int(self) -> None:
        assert to_primitive(42) == 42

    def test_float(self) -> None:
        assert to_primitive(3.14) == 3.14

    def test_str(self) -> None:
        assert to_primitive("hello") == "hello"

    def test_list(self) -> None:
        assert to_primitive([1, 2, 3]) == [1, 2, 3]

    def test_tuple_becomes_list(self) -> None:
        assert to_primitive((1, 2)) == [1, 2]

    def test_nested_dict(self) -> None:
        result = to_primitive({"a": {"b": 1}})
        assert result == {"a": {"b": 1}}

    def test_mapping_proxy(self) -> None:
        proxy = types.MappingProxyType({"x": 1})
        result = to_primitive(proxy)
        assert result == {"x": 1}

    def test_schema_version(self) -> None:
        sv = SchemaVersion(1, 2, 3)
        assert to_primitive(sv) == "1.2.3"

    def test_non_str_dict_key_rejected(self) -> None:
        with pytest.raises(TypeError, match="dict keys must be str"):
            to_primitive({1: "a"})

    def test_unsupported_type_rejected(self) -> None:
        class Weird:
            pass

        with pytest.raises(TypeError, match="unsupported type"):
            to_primitive(Weird())

    def test_nested_list_of_dicts(self) -> None:
        obj = [{"a": 1}, {"b": 2}]
        assert to_primitive(obj) == [{"a": 1}, {"b": 2}]


# ---------------------------------------------------------------------------
# canonicalize
# ---------------------------------------------------------------------------


class TestCanonicalize:
    def test_simple_dict(self) -> None:
        result = canonicalize({"b": 2, "a": 1})
        parsed = json.loads(result)
        assert parsed == {"a": 1, "b": 2}

    def test_keys_sorted(self) -> None:
        # Same dict in different insertion orders → identical canonical string.
        d1 = {"z": 3, "a": 1, "m": 2}
        d2 = {"a": 1, "m": 2, "z": 3}
        assert canonicalize(d1) == canonicalize(d2)

    def test_nested_keys_sorted(self) -> None:
        d = {"outer": {"z": 1, "a": 2}}
        result = json.loads(canonicalize(d))
        assert list(result["outer"].keys()) == ["a", "z"]

    def test_compact_no_spaces(self) -> None:
        result = canonicalize({"a": 1})
        assert " " not in result

    def test_deterministic_across_calls(self) -> None:
        obj = {"x": [1, 2], "y": {"q": True}}
        assert canonicalize(obj) == canonicalize(obj)

    def test_nan_rejected(self) -> None:
        import math

        with pytest.raises(ValueError):
            canonicalize({"x": math.nan})

    def test_infinity_rejected(self) -> None:
        import math

        with pytest.raises(ValueError):
            canonicalize({"x": math.inf})

    def test_none_value(self) -> None:
        result = canonicalize({"a": None})
        assert '"a":null' in result

    def test_list_preserved_order(self) -> None:
        result = json.loads(canonicalize([3, 1, 2]))
        assert result == [3, 1, 2]


# ---------------------------------------------------------------------------
# content_hash
# ---------------------------------------------------------------------------


class TestContentHash:
    def test_returns_hex_string(self) -> None:
        h = content_hash({"a": 1})
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex

    def test_deterministic(self) -> None:
        obj = {"x": [1, 2, 3], "y": "hello"}
        assert content_hash(obj) == content_hash(obj)

    def test_dict_insertion_order_independent(self) -> None:
        d1 = {"z": 3, "a": 1}
        d2 = {"a": 1, "z": 3}
        assert content_hash(d1) == content_hash(d2)

    def test_different_content_different_hash(self) -> None:
        assert content_hash({"a": 1}) != content_hash({"a": 2})

    def test_empty_dict(self) -> None:
        h = content_hash({})
        assert len(h) == 64


# ---------------------------------------------------------------------------
# make_serialized_object
# ---------------------------------------------------------------------------


class TestMakeSerializedObject:
    def _sv(self) -> SchemaVersion:
        return SchemaVersion(1, 0, 0)

    def test_basic(self) -> None:
        obj = make_serialized_object("Test", self._sv(), {"k": 1})
        assert isinstance(obj, SerializedObject)
        assert obj.schema_name == "Test"
        assert obj.payload["k"] == 1

    def test_hash_included_by_default(self) -> None:
        obj = make_serialized_object("Test", self._sv(), {"k": 1})
        assert obj.content_hash is not None
        assert len(obj.content_hash) == 64

    def test_hash_excluded_when_requested(self) -> None:
        obj = make_serialized_object("Test", self._sv(), {"k": 1}, include_hash=False)
        assert obj.content_hash is None

    def test_deterministic_hash(self) -> None:
        a = make_serialized_object("Test", self._sv(), {"k": 1})
        b = make_serialized_object("Test", self._sv(), {"k": 1})
        assert a.content_hash == b.content_hash

    def test_repeated_serialization_same_output(self) -> None:
        payload = {"z": 3, "a": 1}
        a = make_serialized_object("Test", self._sv(), payload)
        b = make_serialized_object("Test", self._sv(), payload)
        assert a == b

    def test_non_mapping_payload_rejected(self) -> None:
        with pytest.raises(TypeError):
            make_serialized_object("Test", self._sv(), [1, 2, 3])  # type: ignore[arg-type]
