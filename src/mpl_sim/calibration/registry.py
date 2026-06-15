"""Calibration registry — Phase 5A.

Startup-time name-keyed registry of named CalibrationSet objects.
Distinct from CorrelationRegistry and PropertyBackendRegistry.

Architectural rules enforced here:
- No import of CoolProp, properties, correlations, geometry, discretization,
  components, network, or solvers.
"""

from __future__ import annotations

from mpl_sim.calibration.primitives import CalibrationSet


class CalibrationRegistry:
    """Name-keyed registry of CalibrationSet objects.

    Rules:
    - Each name must be unique within the registry.
    - Registering a duplicate name raises ValueError.
    - Resolving an unregistered name raises KeyError.
    - Names are returned in deterministic (sorted) order.
    """

    def __init__(self) -> None:
        self._registry: dict[str, CalibrationSet] = {}

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def register(self, name: str, calibration_set: CalibrationSet) -> None:
        """Register *calibration_set* under *name*.

        Raises
        ------
        ValueError
            If *name* is empty, or if *name* is already registered.
        TypeError
            If *calibration_set* is not a :class:`CalibrationSet` instance.
        """
        if not name:
            raise ValueError("CalibrationRegistry: name must be non-empty")
        if not isinstance(calibration_set, CalibrationSet):
            raise TypeError(
                f"CalibrationRegistry: expected CalibrationSet, " f"got {type(calibration_set)!r}"
            )
        if name in self._registry:
            raise ValueError(
                f"CalibrationRegistry: name {name!r} is already registered. "
                f"Duplicate names are not allowed."
            )
        self._registry[name] = calibration_set

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def resolve(self, name: str) -> CalibrationSet:
        """Return the CalibrationSet registered under *name*.

        Raises
        ------
        KeyError
            If *name* is not registered.
        """
        try:
            return self._registry[name]
        except KeyError:
            raise KeyError(
                f"CalibrationRegistry: name {name!r} is not registered. "
                f"Available names: {sorted(self._registry)!r}"
            ) from None

    def names(self) -> tuple[str, ...]:
        """Return all registered names in deterministic (sorted) order."""
        return tuple(sorted(self._registry))

    def __len__(self) -> int:
        return len(self._registry)

    def is_registered(self, name: str) -> bool:
        """Return True if *name* is registered."""
        return name in self._registry
