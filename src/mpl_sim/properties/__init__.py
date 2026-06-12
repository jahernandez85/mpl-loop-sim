"""properties — PropertyBackend contract and concrete implementations.

Phase 2A: abstract interface only.
Phase 2B: CoolPropBackend (the only place CoolProp may be imported).
Phase 2C: PropertyBackendRegistry, BackendSelection, and default factory.

NOTE: This subpackage is the ONLY place in mpl_sim that may import CoolProp.
CoolPropBackend is loaded lazily so that a bare ``import mpl_sim.properties``
does not pull in CoolProp (satisfies the Phase 2A import-boundary test).
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
from mpl_sim.properties.registry import (
    BackendSelection,
    PropertyBackendRegistry,
    create_default_property_backend_registry,
    default_backend_name_for,
)

__all__ = [
    "BackendCapability",
    "BackendSelection",
    "CoolPropBackend",
    "PhaseLabel",
    "PropertyBackend",
    "PropertyBackendRegistry",
    "PropertyName",
    "PropertyResult",
    "QueryStatus",
    "ValidRange",
    "create_default_property_backend_registry",
    "default_backend_name_for",
]


def __getattr__(name: str) -> object:
    if name == "CoolPropBackend":
        from mpl_sim.properties.coolprop_backend import (  # noqa: PLC0415
            CoolPropBackend,
        )

        return CoolPropBackend
    raise AttributeError(f"module 'mpl_sim.properties' has no attribute {name!r}")
