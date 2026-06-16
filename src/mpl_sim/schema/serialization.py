"""Canonical serialization utilities — Phase 9B.

Provides deterministic JSON-compatible canonicalization and SHA-256 hashing
for schema serialized objects.

Architecture constraints:
- MUST NOT import CoolProp, properties, correlations, calibration.
- MUST NOT import network, components, geometry, or solvers.
- MUST NOT compute physics or call any backend.
- Standard library only (json, hashlib, types).
"""

from __future__ import annotations

import hashlib
import json
import types
from typing import Any

from mpl_sim.schema.primitives import SchemaVersion, SerializedObject

# ---------------------------------------------------------------------------
# Primitive type set accepted by the serializer
# ---------------------------------------------------------------------------

_SCALAR_TYPES = (bool, int, float, str, type(None))


def to_primitive(obj: Any) -> Any:
    """Recursively convert *obj* to a JSON-compatible primitive.

    Accepted input types:
        bool, int, float, str, None
        dict  (keys must be str; values are recursively converted)
        list, tuple  (elements recursively converted; tuples become lists)
        SchemaVersion (converted to its string form)

    Non-serializable objects raise TypeError.
    NaN and infinity floats are accepted as-is (callers may reject them).
    """
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, _SCALAR_TYPES):
        return obj
    if isinstance(obj, SchemaVersion):
        return str(obj)
    if isinstance(obj, (list, tuple)):
        return [to_primitive(item) for item in obj]
    if isinstance(obj, (dict, types.MappingProxyType)):
        result: dict[str, Any] = {}
        for k, v in obj.items():
            if not isinstance(k, str):
                raise TypeError(f"to_primitive: dict keys must be str; got {type(k).__name__!r}")
            result[k] = to_primitive(v)
        return result
    raise TypeError(
        f"to_primitive: unsupported type {type(obj).__name__!r}; "
        "only bool/int/float/str/None/dict/list/tuple/SchemaVersion are accepted"
    )


def canonicalize(obj: Any) -> str:
    """Return a deterministic JSON string for *obj*.

    - dict keys are sorted at every nesting level.
    - Compact encoding (no extra whitespace).
    - NaN/infinity floats are rejected by the standard json encoder and will
      raise ValueError.
    """
    primitive = to_primitive(obj)
    return json.dumps(primitive, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_hash(obj: Any) -> str:
    """Return the hex-encoded SHA-256 digest of the canonical JSON of *obj*.

    The canonicalization algorithm is: sorted-key compact JSON (UTF-8),
    as produced by :func:`canonicalize`.  This is recorded in
    SerializedObject.content_hash so a future reader can reproduce the hash.
    """
    canonical = canonicalize(obj)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def make_serialized_object(
    schema_name: str,
    schema_version: SchemaVersion,
    payload: dict | types.MappingProxyType,
    *,
    include_hash: bool = True,
) -> SerializedObject:
    """Build a :class:`SerializedObject` from a raw payload dict.

    Args:
        schema_name    : the schema identifier string.
        schema_version : the schema version.
        payload        : the raw Python mapping to serialize.
        include_hash   : when True (default), compute and attach a content hash.

    Returns:
        An immutable :class:`SerializedObject`.
    """
    primitive_payload = to_primitive(payload)
    if not isinstance(primitive_payload, dict):
        raise TypeError("make_serialized_object: payload must be a mapping")
    hash_value: str | None = None
    if include_hash:
        hash_value = content_hash(primitive_payload)
    return SerializedObject(
        schema_name=schema_name,
        schema_version=schema_version,
        payload=primitive_payload,
        content_hash=hash_value,
    )
