"""Schema serialization primitives — Phase 9B.

Immutable, data-only primitives for schema versioning and serialized objects.
No physics, no correlations, no CoolProp, no network, no components, no solvers.

Architecture constraints:
- MUST NOT import CoolProp, properties, correlations, calibration.
- MUST NOT import network, components, geometry, or solvers.
- MUST NOT compute physics or call any backend.
- Standard library only (plus typing).
"""

from __future__ import annotations

import enum
import types
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# SchemaVersion
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SchemaVersion:
    """Immutable semantic version for a serialized schema.

    Fields:
        major : non-negative integer; bump on breaking change.
        minor : non-negative integer; bump on backward-compatible addition.
        patch : non-negative integer; bump on backward-compatible fix.
    """

    major: int
    minor: int
    patch: int

    def __post_init__(self) -> None:
        fields = (("major", self.major), ("minor", self.minor), ("patch", self.patch))
        for field_name, val in fields:
            if not isinstance(val, int):
                raise TypeError(f"SchemaVersion.{field_name} must be int; got {type(val).__name__}")
            if val < 0:
                raise ValueError(f"SchemaVersion.{field_name} must be >= 0; got {val!r}")

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    @classmethod
    def parse(cls, version_str: str) -> SchemaVersion:
        """Parse a "major.minor.patch" string into a SchemaVersion."""
        parts = version_str.split(".")
        if len(parts) != 3:
            raise ValueError(
                f"SchemaVersion.parse expects 'major.minor.patch'; got {version_str!r}"
            )
        try:
            return cls(major=int(parts[0]), minor=int(parts[1]), patch=int(parts[2]))
        except ValueError as exc:
            raise ValueError(
                f"SchemaVersion.parse: non-integer component in {version_str!r}"
            ) from exc


# ---------------------------------------------------------------------------
# SerializationFormat
# ---------------------------------------------------------------------------


class SerializationFormat(enum.Enum):
    """Closed vocabulary of supported serialization wire formats."""

    JSON = "JSON"
    DICT = "DICT"


# ---------------------------------------------------------------------------
# SchemaValidationResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SchemaValidationResult:
    """Immutable result of a schema validation check.

    Fields:
        valid  : True when all checks passed.
        errors : tuple of non-empty error description strings.
    """

    valid: bool
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "errors", tuple(self.errors))

    @classmethod
    def ok(cls) -> SchemaValidationResult:
        return cls(valid=True, errors=())

    @classmethod
    def fail(cls, *errors: str) -> SchemaValidationResult:
        return cls(valid=False, errors=tuple(errors))


# ---------------------------------------------------------------------------
# SerializedObject
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SerializedObject:
    """Immutable serialized artifact with schema identity and payload.

    Fields:
        schema_name    : non-empty name identifying the schema (e.g. "SolverReport").
        schema_version : SchemaVersion of the serialized form.
        payload        : immutable mapping from str keys to JSON-compatible values.
                         Defensively copied; external mutation does not affect this.
        content_hash   : optional non-empty SHA-256 hex digest of the canonical payload.
    """

    schema_name: str
    schema_version: SchemaVersion
    payload: types.MappingProxyType
    content_hash: str | None = None

    def __init__(
        self,
        schema_name: str,
        schema_version: SchemaVersion,
        payload: dict | types.MappingProxyType,
        content_hash: str | None = None,
    ) -> None:
        if not schema_name:
            raise ValueError("SerializedObject.schema_name must be non-empty")
        if content_hash is not None and not content_hash:
            raise ValueError("SerializedObject.content_hash must be non-empty when provided")
        object.__setattr__(self, "schema_name", schema_name)
        object.__setattr__(self, "schema_version", schema_version)
        # Defensively copy payload into an immutable proxy.
        if isinstance(payload, types.MappingProxyType):
            raw = dict(payload)
        else:
            raw = dict(payload)
        object.__setattr__(self, "payload", types.MappingProxyType(raw))
        object.__setattr__(self, "content_hash", content_hash)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SerializedObject):
            return NotImplemented
        return (
            self.schema_name == other.schema_name
            and self.schema_version == other.schema_version
            and dict(self.payload) == dict(other.payload)
            and self.content_hash == other.content_hash
        )

    def __hash__(self) -> int:
        return hash((self.schema_name, self.schema_version, self.content_hash))
