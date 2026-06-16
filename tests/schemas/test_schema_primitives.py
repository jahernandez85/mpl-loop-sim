"""Tests for schema primitives — Phase 9B.

Covers: SchemaVersion, SerializationFormat, SchemaValidationResult,
SerializedObject.
No CoolProp, properties, correlations, components, network, or solvers imported.
"""

from __future__ import annotations

import types

import pytest

from mpl_sim.schema.primitives import (
    SchemaValidationResult,
    SchemaVersion,
    SerializationFormat,
    SerializedObject,
)

# ---------------------------------------------------------------------------
# Import isolation guard
# ---------------------------------------------------------------------------


def _check_no_forbidden_imports(module_path: str) -> None:
    import ast

    with open(module_path, encoding="utf-8") as f:
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
            assert not imp.startswith(prefix), f"Forbidden import found: {imp!r}"


def test_primitives_no_forbidden_imports() -> None:
    import mpl_sim.schema.primitives as mod

    _check_no_forbidden_imports(mod.__file__)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# SchemaVersion
# ---------------------------------------------------------------------------


class TestSchemaVersion:
    def test_basic_construction(self) -> None:
        sv = SchemaVersion(major=1, minor=2, patch=3)
        assert sv.major == 1
        assert sv.minor == 2
        assert sv.patch == 3

    def test_str_representation(self) -> None:
        assert str(SchemaVersion(1, 0, 0)) == "1.0.0"
        assert str(SchemaVersion(2, 3, 4)) == "2.3.4"

    def test_parse_roundtrip(self) -> None:
        sv = SchemaVersion(1, 0, 0)
        assert SchemaVersion.parse(str(sv)) == sv

    def test_parse_valid(self) -> None:
        sv = SchemaVersion.parse("3.1.4")
        assert sv == SchemaVersion(3, 1, 4)

    def test_parse_invalid_format(self) -> None:
        with pytest.raises(ValueError, match="expects 'major.minor.patch'"):
            SchemaVersion.parse("1.0")

    def test_parse_non_integer(self) -> None:
        with pytest.raises(ValueError):
            SchemaVersion.parse("1.x.0")

    def test_negative_major_rejected(self) -> None:
        with pytest.raises(ValueError, match="major must be >= 0"):
            SchemaVersion(major=-1, minor=0, patch=0)

    def test_negative_minor_rejected(self) -> None:
        with pytest.raises(ValueError, match="minor must be >= 0"):
            SchemaVersion(major=0, minor=-1, patch=0)

    def test_negative_patch_rejected(self) -> None:
        with pytest.raises(ValueError, match="patch must be >= 0"):
            SchemaVersion(major=0, minor=0, patch=-1)

    def test_zero_version_allowed(self) -> None:
        sv = SchemaVersion(0, 0, 0)
        assert str(sv) == "0.0.0"

    def test_immutable(self) -> None:
        sv = SchemaVersion(1, 0, 0)
        with pytest.raises(Exception):
            sv.major = 2  # type: ignore[misc]

    def test_equality_and_hash(self) -> None:
        a = SchemaVersion(1, 0, 0)
        b = SchemaVersion(1, 0, 0)
        assert a == b
        assert hash(a) == hash(b)

    def test_inequality(self) -> None:
        assert SchemaVersion(1, 0, 0) != SchemaVersion(1, 0, 1)


# ---------------------------------------------------------------------------
# SerializationFormat
# ---------------------------------------------------------------------------


class TestSerializationFormat:
    def test_all_values_present(self) -> None:
        names = {f.name for f in SerializationFormat}
        assert "JSON" in names
        assert "DICT" in names

    def test_is_enum(self) -> None:
        import enum

        assert isinstance(SerializationFormat.JSON, enum.Enum)


# ---------------------------------------------------------------------------
# SchemaValidationResult
# ---------------------------------------------------------------------------


class TestSchemaValidationResult:
    def test_ok_factory(self) -> None:
        result = SchemaValidationResult.ok()
        assert result.valid is True
        assert result.errors == ()

    def test_fail_factory(self) -> None:
        result = SchemaValidationResult.fail("bad field", "missing key")
        assert result.valid is False
        assert "bad field" in result.errors
        assert "missing key" in result.errors

    def test_errors_coerced_to_tuple(self) -> None:
        result = SchemaValidationResult(valid=False, errors=["e1", "e2"])  # type: ignore[arg-type]
        assert isinstance(result.errors, tuple)

    def test_immutable(self) -> None:
        result = SchemaValidationResult.ok()
        with pytest.raises(Exception):
            result.valid = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SerializedObject
# ---------------------------------------------------------------------------


class TestSerializedObject:
    def _sv(self) -> SchemaVersion:
        return SchemaVersion(1, 0, 0)

    def test_basic_construction(self) -> None:
        obj = SerializedObject(
            schema_name="TestSchema",
            schema_version=self._sv(),
            payload={"key": "value"},
        )
        assert obj.schema_name == "TestSchema"
        assert obj.schema_version == self._sv()
        assert obj.payload["key"] == "value"
        assert obj.content_hash is None

    def test_empty_schema_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="schema_name must be non-empty"):
            SerializedObject(
                schema_name="",
                schema_version=self._sv(),
                payload={},
            )

    def test_empty_content_hash_rejected(self) -> None:
        with pytest.raises(ValueError, match="content_hash must be non-empty"):
            SerializedObject(
                schema_name="X",
                schema_version=self._sv(),
                payload={},
                content_hash="",
            )

    def test_payload_is_immutable_proxy(self) -> None:
        obj = SerializedObject(
            schema_name="X",
            schema_version=self._sv(),
            payload={"a": 1},
        )
        assert isinstance(obj.payload, types.MappingProxyType)
        with pytest.raises(TypeError):
            obj.payload["a"] = 99  # type: ignore[index]

    def test_payload_source_mutation_isolated(self) -> None:
        source = {"x": 10}
        obj = SerializedObject(schema_name="X", schema_version=self._sv(), payload=source)
        source["x"] = 999
        assert obj.payload["x"] == 10

    def test_proxy_payload_accepted(self) -> None:
        proxy = types.MappingProxyType({"z": 42})
        obj = SerializedObject(schema_name="X", schema_version=self._sv(), payload=proxy)
        assert obj.payload["z"] == 42

    def test_with_content_hash(self) -> None:
        obj = SerializedObject(
            schema_name="X",
            schema_version=self._sv(),
            payload={"n": 1},
            content_hash="abc123",
        )
        assert obj.content_hash == "abc123"

    def test_equality(self) -> None:
        sv = self._sv()
        a = SerializedObject(schema_name="X", schema_version=sv, payload={"k": 1})
        b = SerializedObject(schema_name="X", schema_version=sv, payload={"k": 1})
        assert a == b

    def test_immutable(self) -> None:
        obj = SerializedObject(schema_name="X", schema_version=self._sv(), payload={})
        with pytest.raises(Exception):
            obj.schema_name = "Y"  # type: ignore[misc]
