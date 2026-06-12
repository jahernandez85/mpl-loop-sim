"""properties — PropertyBackend contract and concrete implementations.

Phase 2A: abstract interface only.
Phase 2B: CoolPropBackend (the only place CoolProp may be imported).

NOTE: This subpackage is the ONLY place in mpl_sim that may import CoolProp.
"""

from mpl_sim.properties.backend import (
    BackendCapability,
    PhaseLabel,
    PropertyBackend,
    PropertyName,
    PropertyResult,
    QueryStatus,
    ValidRange,
)

__all__ = [
    "BackendCapability",
    "PhaseLabel",
    "PropertyBackend",
    "PropertyName",
    "PropertyResult",
    "QueryStatus",
    "ValidRange",
]
