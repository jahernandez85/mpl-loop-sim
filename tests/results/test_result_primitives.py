"""Tests for result primitives — Phase 9A.

Covers: ResultStatus, ResultMessage, ResultMetadata, ResultBundle.
No CoolProp, properties, correlations, components, network, or solvers imported.
"""

from __future__ import annotations

import types

import pytest

from mpl_sim.results.primitives import (
    ResultBundle,
    ResultMessage,
    ResultMetadata,
    ResultStatus,
)

# ---------------------------------------------------------------------------
# Import isolation guard
# ---------------------------------------------------------------------------


def test_no_forbidden_imports() -> None:
    import ast

    import mpl_sim.results.primitives as mod

    src = mod.__file__
    assert src is not None
    with open(src, encoding="utf-8") as f:
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


# ---------------------------------------------------------------------------
# ResultStatus
# ---------------------------------------------------------------------------


class TestResultStatus:
    def test_all_values_present(self) -> None:
        names = {s.name for s in ResultStatus}
        assert "OK" in names
        assert "WARNING" in names
        assert "FAILED" in names
        assert "INVALID" in names
        assert "NOT_EVALUATED" in names

    def test_is_enum(self) -> None:
        import enum

        assert isinstance(ResultStatus.OK, enum.Enum)

    def test_deterministic_ordering(self) -> None:
        values = list(ResultStatus)
        assert values == list(ResultStatus)  # same order each time


# ---------------------------------------------------------------------------
# ResultMessage
# ---------------------------------------------------------------------------


class TestResultMessage:
    def test_basic_construction(self) -> None:
        msg = ResultMessage(status=ResultStatus.OK, text="All good")
        assert msg.status is ResultStatus.OK
        assert msg.text == "All good"
        assert msg.code is None
        assert msg.source is None

    def test_with_optional_fields(self) -> None:
        msg = ResultMessage(
            status=ResultStatus.WARNING,
            text="Something off",
            code="W001",
            source="my_module",
        )
        assert msg.code == "W001"
        assert msg.source == "my_module"

    def test_empty_text_rejected(self) -> None:
        with pytest.raises(ValueError, match="text must be non-empty"):
            ResultMessage(status=ResultStatus.OK, text="")

    def test_empty_code_rejected(self) -> None:
        with pytest.raises(ValueError, match="code must be non-empty"):
            ResultMessage(status=ResultStatus.OK, text="ok", code="")

    def test_empty_source_rejected(self) -> None:
        with pytest.raises(ValueError, match="source must be non-empty"):
            ResultMessage(status=ResultStatus.OK, text="ok", source="")

    def test_immutable(self) -> None:
        msg = ResultMessage(status=ResultStatus.OK, text="hi")
        with pytest.raises(Exception):
            msg.text = "changed"  # type: ignore[misc]

    def test_equality(self) -> None:
        a = ResultMessage(status=ResultStatus.OK, text="hi")
        b = ResultMessage(status=ResultStatus.OK, text="hi")
        assert a == b

    def test_hash_stable(self) -> None:
        msg = ResultMessage(status=ResultStatus.OK, text="hi")
        assert hash(msg) == hash(msg)


# ---------------------------------------------------------------------------
# ResultMetadata
# ---------------------------------------------------------------------------


class TestResultMetadata:
    def test_basic_construction(self) -> None:
        meta = ResultMetadata(producer="solver_v1", schema_version="1.0.0")
        assert meta.producer == "solver_v1"
        assert meta.schema_version == "1.0.0"
        assert meta.timestamp is None
        assert meta.tags == ()

    def test_with_all_fields(self) -> None:
        meta = ResultMetadata(
            producer="solver_v1",
            schema_version="1.0.0",
            timestamp="2026-01-01T00:00:00Z",
            tags=("a", "b"),
        )
        assert meta.timestamp == "2026-01-01T00:00:00Z"
        assert meta.tags == ("a", "b")

    def test_empty_producer_rejected(self) -> None:
        with pytest.raises(ValueError, match="producer must be non-empty"):
            ResultMetadata(producer="", schema_version="1.0.0")

    def test_empty_schema_version_rejected(self) -> None:
        with pytest.raises(ValueError, match="schema_version must be non-empty"):
            ResultMetadata(producer="p", schema_version="")

    def test_empty_timestamp_rejected(self) -> None:
        with pytest.raises(ValueError, match="timestamp must be non-empty"):
            ResultMetadata(producer="p", schema_version="1.0.0", timestamp="")

    def test_empty_tag_rejected(self) -> None:
        with pytest.raises(ValueError, match="tags entries must be non-empty"):
            ResultMetadata(producer="p", schema_version="1.0.0", tags=("good", ""))

    def test_tags_coerced_to_tuple(self) -> None:
        meta = ResultMetadata(producer="p", schema_version="1", tags=["x", "y"])  # type: ignore[arg-type]
        assert isinstance(meta.tags, tuple)
        assert meta.tags == ("x", "y")

    def test_immutable(self) -> None:
        meta = ResultMetadata(producer="p", schema_version="1.0.0")
        with pytest.raises(Exception):
            meta.producer = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ResultBundle
# ---------------------------------------------------------------------------


class TestResultBundle:
    def _meta(self) -> ResultMetadata:
        return ResultMetadata(producer="test", schema_version="1.0.0")

    def test_basic_construction(self) -> None:
        bundle = ResultBundle(
            status=ResultStatus.OK,
            metadata=self._meta(),
        )
        assert bundle.status is ResultStatus.OK
        assert bundle.messages == ()
        assert dict(bundle.payload) == {}

    def test_with_messages_and_payload(self) -> None:
        msg = ResultMessage(status=ResultStatus.WARNING, text="watch out")
        bundle = ResultBundle(
            status=ResultStatus.WARNING,
            metadata=self._meta(),
            messages=[msg],
            payload={"key": 1.0},
        )
        assert bundle.messages == (msg,)
        assert bundle.payload["key"] == 1.0

    def test_payload_is_immutable_proxy(self) -> None:
        bundle = ResultBundle(
            status=ResultStatus.OK,
            metadata=self._meta(),
            payload={"x": 1},
        )
        assert isinstance(bundle.payload, types.MappingProxyType)
        with pytest.raises(TypeError):
            bundle.payload["x"] = 99  # type: ignore[index]

    def test_payload_source_mutation_isolated(self) -> None:
        source: dict = {"x": 1}
        bundle = ResultBundle(
            status=ResultStatus.OK,
            metadata=self._meta(),
            payload=source,
        )
        source["x"] = 999
        assert bundle.payload["x"] == 1  # bundle is unaffected

    def test_messages_tuple_coercion(self) -> None:
        msg = ResultMessage(status=ResultStatus.OK, text="hi")
        bundle = ResultBundle(
            status=ResultStatus.OK,
            metadata=self._meta(),
            messages=[msg],
        )
        assert isinstance(bundle.messages, tuple)

    def test_messages_source_mutation_isolated(self) -> None:
        msg = ResultMessage(status=ResultStatus.OK, text="hi")
        msgs = [msg]
        bundle = ResultBundle(
            status=ResultStatus.OK,
            metadata=self._meta(),
            messages=msgs,
        )
        msgs.clear()
        assert len(bundle.messages) == 1

    def test_equality(self) -> None:
        meta = self._meta()
        a = ResultBundle(status=ResultStatus.OK, metadata=meta, payload={"v": 1})
        b = ResultBundle(status=ResultStatus.OK, metadata=meta, payload={"v": 1})
        assert a == b

    def test_inequality_status(self) -> None:
        meta = self._meta()
        a = ResultBundle(status=ResultStatus.OK, metadata=meta)
        b = ResultBundle(status=ResultStatus.FAILED, metadata=meta)
        assert a != b

    def test_none_payload_treated_as_empty(self) -> None:
        bundle = ResultBundle(
            status=ResultStatus.OK,
            metadata=self._meta(),
            payload=None,
        )
        assert dict(bundle.payload) == {}

    def test_proxy_payload_accepted(self) -> None:
        proxy = types.MappingProxyType({"z": 42})
        bundle = ResultBundle(
            status=ResultStatus.OK,
            metadata=self._meta(),
            payload=proxy,
        )
        assert bundle.payload["z"] == 42
