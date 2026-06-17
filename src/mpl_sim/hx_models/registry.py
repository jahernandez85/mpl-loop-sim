"""HeatExchangerModelRegistry — Phase 11A.

Startup-time name-keyed registry of HeatExchangerModel instances.
Separate from CorrelationRegistry; resolves strategy objects, not closures.

Architectural constraints:
  - No import of CoolProp, properties/, components/, network/, or solvers/.
  - No CorrelationRegistry dependency.
  - Names must be unique.
  - Empty names are rejected.
  - Unknown names raise KeyError on resolve.
"""

from __future__ import annotations

from mpl_sim.hx_models.base import HeatExchangerModel


class HeatExchangerModelRegistry:
    """Name-keyed registry of HeatExchangerModel strategy instances.

    Rules:
      - Each name is unique across the entire registry.
      - Names must be non-empty strings.
      - The registry does not own or mutate the model instance.
    """

    def __init__(self) -> None:
        self._registry: dict[str, HeatExchangerModel] = {}

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def register(self, name: str, model: HeatExchangerModel) -> None:
        """Register a HX model under *name*.

        Parameters
        ----------
        name  : non-empty unique registration name
        model : HeatExchangerModel instance

        Raises
        ------
        TypeError
            If *model* is not a HeatExchangerModel instance.
        ValueError
            If *name* is empty or already registered.
        """
        if not isinstance(model, HeatExchangerModel):
            raise TypeError(f"Expected a HeatExchangerModel instance, got {type(model)!r}")
        if not name:
            raise ValueError("HeatExchangerModelRegistry: name must be non-empty")
        if name in self._registry:
            raise ValueError(
                f"A HX model named {name!r} is already registered.  "
                f"Duplicate names are not allowed."
            )
        self._registry[name] = model

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def resolve(self, name: str) -> HeatExchangerModel:
        """Return the HX model registered under *name*.

        Raises
        ------
        KeyError
            If *name* is not registered.
        """
        try:
            return self._registry[name]
        except KeyError:
            raise KeyError(
                f"No HX model named {name!r} is registered.  "
                f"Available names: {sorted(self._registry)!r}"
            ) from None

    def is_registered(self, name: str) -> bool:
        """Return True if *name* is registered."""
        return name in self._registry

    def model_names(self) -> tuple[str, ...]:
        """Return all registered names as a sorted tuple."""
        return tuple(sorted(self._registry))


def create_empty_hx_model_registry() -> HeatExchangerModelRegistry:
    """Factory that returns a fresh, empty HeatExchangerModelRegistry."""
    return HeatExchangerModelRegistry()
