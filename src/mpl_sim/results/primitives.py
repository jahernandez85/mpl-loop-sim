"""Generic result primitives — Phase 9A.

Immutable, data-only primitives for simulation results, validation, and
serialization.  No physics, no correlations, no CoolProp, no network,
no components, no solvers.

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
# ResultStatus
# ---------------------------------------------------------------------------


class ResultStatus(enum.Enum):
    """Closed vocabulary of result/check outcome states."""

    OK = "OK"
    WARNING = "WARNING"
    FAILED = "FAILED"
    INVALID = "INVALID"
    NOT_EVALUATED = "NOT_EVALUATED"


# ---------------------------------------------------------------------------
# ResultMessage
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultMessage:
    """Immutable message attached to a result.

    Fields:
        status : severity / outcome of this message.
        text   : non-empty human-readable description.
        code   : optional non-empty machine-readable code (e.g. "E001").
        source : optional non-empty identifier of the producer (e.g. module name).
    """

    status: ResultStatus
    text: str
    code: str | None = None
    source: str | None = None

    def __post_init__(self) -> None:
        if not self.text:
            raise ValueError("ResultMessage.text must be non-empty")
        if self.code is not None and not self.code:
            raise ValueError("ResultMessage.code must be non-empty when provided")
        if self.source is not None and not self.source:
            raise ValueError("ResultMessage.source must be non-empty when provided")


# ---------------------------------------------------------------------------
# ResultMetadata
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultMetadata:
    """Immutable metadata about who produced a result and when.

    Fields:
        producer       : non-empty name of the producing module/system.
        schema_version : non-empty version string (e.g. "1.0.0").
        timestamp      : optional ISO-8601 timestamp string; never auto-generated.
        tags           : immutable tuple of non-empty tag strings.
    """

    producer: str
    schema_version: str
    timestamp: str | None = None
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.producer:
            raise ValueError("ResultMetadata.producer must be non-empty")
        if not self.schema_version:
            raise ValueError("ResultMetadata.schema_version must be non-empty")
        if self.timestamp is not None and not self.timestamp:
            raise ValueError("ResultMetadata.timestamp must be non-empty when provided")
        # Coerce tags to tuple for immutability, validate entries.
        object.__setattr__(self, "tags", tuple(self.tags))
        for tag in self.tags:
            if not tag:
                raise ValueError("ResultMetadata.tags entries must be non-empty")


# ---------------------------------------------------------------------------
# ResultBundle
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResultBundle:
    """Immutable container for a simulation or check result.

    Fields:
        status   : overall ResultStatus.
        metadata : ResultMetadata describing the producer.
        messages : immutable tuple of ResultMessage objects.
        payload  : immutable mapping of string keys to JSON-compatible values.
                   Defensively copied; external mutation of the source mapping
                   does not affect this object.
    """

    status: ResultStatus
    metadata: ResultMetadata
    messages: tuple[ResultMessage, ...]
    payload: types.MappingProxyType

    def __init__(
        self,
        status: ResultStatus,
        metadata: ResultMetadata,
        messages: tuple[ResultMessage, ...] | list[ResultMessage] = (),
        payload: dict | types.MappingProxyType | None = None,
    ) -> None:
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "metadata", metadata)
        object.__setattr__(self, "messages", tuple(messages))
        # Defensively copy payload into an immutable proxy.
        raw: dict
        if payload is None:
            raw = {}
        elif isinstance(payload, types.MappingProxyType):
            raw = dict(payload)
        else:
            raw = dict(payload)
        object.__setattr__(self, "payload", types.MappingProxyType(raw))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ResultBundle):
            return NotImplemented
        return (
            self.status == other.status
            and self.metadata == other.metadata
            and self.messages == other.messages
            and dict(self.payload) == dict(other.payload)
        )

    def __hash__(self) -> int:
        return hash((self.status, self.metadata, self.messages))
