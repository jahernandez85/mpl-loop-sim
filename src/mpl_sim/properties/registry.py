"""PropertyBackendRegistry — startup-time registry for PropertyBackend constructors.

Phase 2C: registry, BackendSelection value object, and default factory.

([F6], [F13], INTERFACE_SPEC §3.4, ARCHITECTURE_MASTER §3)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from mpl_sim.core.fluid_identity import FluidIdentity, PureFluid
from mpl_sim.properties.backend import PropertyBackend


@dataclass(frozen=True)
class BackendSelection:
    """Binding of a FluidIdentity to a named property backend.

    Immutable and hashable so it can participate in future
    ReproducibilityTuple serialization (SCHEMA_SPEC §5.2).
    """

    identity: FluidIdentity
    backend_name: str


class PropertyBackendRegistry:
    """Startup-time registry mapping backend names to backend constructors.

    Populated once before the solve loop and never mutated mid-solve.
    (INTERFACE_SPEC §3.4, ARCHITECTURE_MASTER §3)
    """

    def __init__(self) -> None:
        self._constructors: dict[str, Callable[[], PropertyBackend]] = {}
        self._cache: dict[tuple[str, FluidIdentity], PropertyBackend] = {}

    def register(self, name: str, constructor: Callable[[], PropertyBackend]) -> None:
        """Register *constructor* under *name*.

        Raises ValueError if *name* is already registered.
        """
        if name in self._constructors:
            raise ValueError(
                f"Backend {name!r} is already registered; "
                "use a distinct name or create a new registry"
            )
        self._constructors[name] = constructor

    def is_registered(self, name: str) -> bool:
        """Return True if *name* has been registered."""
        return name in self._constructors

    def resolve(self, name: str) -> PropertyBackend:
        """Construct and return a fresh backend instance for *name*.

        Raises KeyError if *name* is not registered.
        """
        if name not in self._constructors:
            available = list(self._constructors)
            raise KeyError(f"Unknown backend {name!r}. Registered backends: {available}")
        return self._constructors[name]()

    def instance_for(self, identity: FluidIdentity, backend_name: str) -> PropertyBackend:
        """Return a cached backend instance for *(identity, backend_name)*.

        Each unique (identity, backend_name) pair maps to exactly one instance
        per registry lifetime. Raises KeyError if *backend_name* is not registered.
        """
        if backend_name not in self._constructors:
            available = list(self._constructors)
            raise KeyError(f"Unknown backend {backend_name!r}. Registered backends: {available}")
        cache_key = (backend_name, identity)
        if cache_key not in self._cache:
            self._cache[cache_key] = self._constructors[backend_name]()
        return self._cache[cache_key]

    def backend_names(self) -> list[str]:
        """Return a list of all registered backend names."""
        return list(self._constructors)


def default_backend_name_for(identity: FluidIdentity) -> str:
    """Return the default backend name for *identity*.

    Raises TypeError for Mixture and CustomFluid — there is no default
    multi-component backend in V1; the caller must explicitly name a backend.
    """
    if isinstance(identity, PureFluid):
        return "coolprop"
    raise TypeError(
        f"No default backend for {type(identity).__name__} in V1; "
        "explicitly specify a backend name"
    )


def create_default_property_backend_registry() -> PropertyBackendRegistry:
    """Return a registry pre-populated with the standard V1 backends.

    Registered backends:
      "coolprop" → CoolPropBackend (lazy import; CoolProp not loaded until first use)

    Mixture and CustomFluid identities are not silently routed to CoolProp.
    Use default_backend_name_for() to resolve the correct backend name for a
    given FluidIdentity, which will raise explicitly for unsupported identity types.
    """
    registry = PropertyBackendRegistry()

    def _make_coolprop() -> PropertyBackend:
        from mpl_sim.properties.coolprop_backend import CoolPropBackend  # noqa: PLC0415

        return CoolPropBackend()

    registry.register("coolprop", _make_coolprop)
    return registry
