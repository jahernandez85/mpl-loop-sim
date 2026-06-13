"""Correlation registry — Phase 3B.

Startup-time name-keyed registry of stateless correlation instances, grouped
by role.  Distinct from PropertyBackendRegistry; lives entirely within the
correlations layer.

Architectural rules enforced here:
- No import of CoolProp, properties/, geometry/, components/, network/,
  calibration/, or solvers/.
- A correlation without a ValidityEnvelope is inadmissible (§14.2).
- Names must be unique across all roles.
"""

from __future__ import annotations

from mpl_sim.correlations.contract import (
    Correlation,
    CorrelationRole,
    ValidityEnvelope,
)


class CorrelationRegistry:
    """Name-keyed registry of stateless correlation instances.

    Rules:
    - Each name is unique across the entire registry (regardless of role).
    - Every registered correlation must expose a non-None ValidityEnvelope.
    - The registry does not own or mutate the correlation instance.
    """

    def __init__(self) -> None:
        self._registry: dict[str, Correlation] = {}

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def register(self, name: str, correlation: Correlation) -> None:
        """Register a correlation under *name*.

        Raises
        ------
        TypeError
            If *correlation* is not a :class:`Correlation` instance.
        ValueError
            If *name* is already registered, or if the correlation does
            not expose a valid :class:`ValidityEnvelope`.
        """
        if not isinstance(correlation, Correlation):
            raise TypeError(f"Expected a Correlation instance, got {type(correlation)!r}")

        if not isinstance(correlation.role(), CorrelationRole):
            raise ValueError(
                f"correlation.role() must return a CorrelationRole, "
                f"got {type(correlation.role())!r}"
            )

        envelope: ValidityEnvelope | None = correlation.envelope()
        if not isinstance(envelope, ValidityEnvelope):
            raise ValueError(
                f"Correlation {name!r} must expose a ValidityEnvelope; "
                f"got {type(envelope)!r}.  A closure without an envelope is "
                f"inadmissible (CORRELATION_CONTRACT §14.2)."
            )
        if not envelope.fluid_families:
            raise ValueError(
                f"Correlation {name!r}: ValidityEnvelope.fluid_families is "
                f"empty — at least one FluidFamilySpec is required."
            )
        if not envelope.bounds:
            raise ValueError(
                f"Correlation {name!r}: ValidityEnvelope.bounds is empty — "
                f"at least one Bound is required."
            )

        if name in self._registry:
            raise ValueError(
                f"A correlation named {name!r} is already registered.  "
                f"Duplicate names are not allowed."
            )

        self._registry[name] = correlation

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def resolve(self, name: str) -> Correlation:
        """Return the correlation registered under *name*.

        Raises
        ------
        KeyError
            If *name* is not registered.
        """
        try:
            return self._registry[name]
        except KeyError:
            raise KeyError(
                f"No correlation named {name!r} is registered.  "
                f"Available names: {sorted(self._registry)!r}"
            ) from None

    def is_registered(self, name: str) -> bool:
        """Return True if *name* is registered."""
        return name in self._registry

    def by_role(self, role: CorrelationRole) -> dict[str, Correlation]:
        """Return a mapping of name -> correlation for all correlations with *role*."""
        return {name: corr for name, corr in self._registry.items() if corr.role() == role}

    def correlation_names(self) -> tuple[str, ...]:
        """Return all registered names as a sorted tuple."""
        return tuple(sorted(self._registry))

    def roles(self) -> set[CorrelationRole]:
        """Return the set of roles currently represented in the registry."""
        return {corr.role() for corr in self._registry.values()}


def create_empty_correlation_registry() -> CorrelationRegistry:
    """Factory that returns a fresh, empty CorrelationRegistry."""
    return CorrelationRegistry()
