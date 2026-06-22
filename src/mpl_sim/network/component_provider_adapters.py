"""Minimal component-like contribution provider adapter — Phase 14F.

Provides a minimal, controlled adapter layer for **component-like contribution
providers**.  These providers are controlled objects that expose a small safe
interface (``produce_records``) to produce Phase 14D ``ContributionRecordSet``
objects from explicit unknown values.

This module moves one step beyond the raw toy callbacks of Phase 14E.  Rather
than plain callable functions, providers are objects with an explicit named
method.  The method name is ``produce_records`` — it is deliberately NOT named
``contribute`` and does NOT call ``Component.contribute(...)``.

What this module DOES
---------------------
- Defines ComponentProviderExecutionContext: immutable context passed to
  provider objects; carries the NetworkBindingContext, defensively copied
  unknown-value mapping, and optional metadata.  Does not assemble SystemState,
  compute properties, execute real component classes, or look up properties.
- Defines ComponentContributionProviderProtocol: a typing.Protocol for
  controlled component-like providers.  Requires one method:
  ``produce_records(context: ComponentProviderExecutionContext) ->
  ContributionRecordSet``.  The protocol method is NOT named ``contribute``.
- Defines ComponentContributionProviderBinding: frozen binding of a
  ComponentInstanceId to a provider object.  Validates the provider exposes
  a callable ``produce_records`` method.  Does not import or require production
  component base classes.
- Defines ComponentContributionProviderSet: validated, ordered, immutable
  collection of ComponentContributionProviderBinding entries; rejects wrong
  types and duplicate component IDs.
- Defines execute_component_provider_contributions: drives the full provider
  execution loop.  Validates binding coverage (exact match required), constructs
  a shared ComponentProviderExecutionContext, invokes each provider's
  ``produce_records`` method, validates return types and record ownership,
  checks for duplicates, and returns a ContributionRecordSet.
- Defines build_component_contribution_from_provider_execution: convenience
  wrapper calling execute_component_provider_contributions then Phase 14D
  map_contribution_records_to_component_contribution to produce a Phase 14C
  ComponentContribution.

What this module DOES NOT DO
-----------------------------
This is a controlled provider adapter layer only.  It MUST NOT and DOES NOT:
- Call or execute existing real component classes.
- Call the ``contribute(...)`` method on any object.
- Define a method named ``contribute`` in any production type.
- Assemble SystemState, FluidState, or any physical state.
- Compute or look up thermodynamic properties.
- Call CoolProp, PropertyBackend, or any property engine.
- Call CorrelationRegistry, HeatExchangerModelRegistry, or any registry.
- Attach physical state (FluidState, mdot, pressure, enthalpy) to graph nodes.
- Infer or generate physics from component_type.
- Implement solve(network) or automatic residual construction from component type.
- Import mpl_sim.solvers, mpl_sim.components, mpl_sim.properties,
  mpl_sim.correlations, mpl_sim.calibration, or mpl_sim.hx_models.

Architecture boundaries (MUST NOT)
-----------------------------------
- MUST NOT import mpl_sim.solvers, mpl_sim.components, mpl_sim.properties,
  mpl_sim.calibration, mpl_sim.hx_models, or CoolProp.
- MUST NOT import or invoke CorrelationRegistry or HeatExchangerModelRegistry.
- MUST NOT expose a solve(network) method on any type in this module.
- MUST NOT perform property lookup, real component execution, or contribute(...)
  calls.
- MUST NOT define a method named ``contribute`` in any new production code.
- MUST NOT mutate the caller-supplied binding context, unknown values, metadata,
  provider set, or contribution records.

Exported names
--------------
ComponentProviderExecutionContext             — immutable context passed to providers
ComponentContributionProviderProtocol        — typing.Protocol for safe providers
ComponentContributionProviderBinding         — frozen (component_id, provider) binding
ComponentContributionProviderSet             — validated ordered collection of bindings
execute_component_provider_contributions     — drive providers → ContributionRecordSet
build_component_contribution_from_provider_execution — convenience wrapper to ComponentContribution
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from mpl_sim.network.component_binding import NetworkBindingContext
from mpl_sim.network.contribution_adapters import ComponentContribution
from mpl_sim.network.contribution_contract import (
    ContributionRecord,
    ContributionRecordSet,
    map_contribution_records_to_component_contribution,
)
from mpl_sim.network.graph import ComponentInstanceId

# ---------------------------------------------------------------------------
# ComponentProviderExecutionContext
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ComponentProviderExecutionContext:
    """Immutable context passed to component-like contribution providers.

    Carries the binding context, the current unknown-value mapping, and
    optional caller metadata.  Does not assemble SystemState, compute
    properties, execute component physics, call property backends, or
    attach state to graph nodes.

    This is a provider-oriented execution context.  It is passed to
    controlled provider objects via their ``produce_records`` method —
    not to real component classes and not to any ``contribute(...)`` method.

    Fields
    ------
    binding_context : NetworkBindingContext from Phase 14B; immutable
    unknown_values  : read-only mapping; defensively copied at construction
    metadata        : optional caller-supplied metadata; defensively copied;
                      None if not supplied

    Validation
    ----------
    - binding_context must be a NetworkBindingContext.
    - unknown_values must be a Mapping; defensively copied.
    - metadata must be a Mapping or None; defensively copied.
    """

    binding_context: NetworkBindingContext
    unknown_values: Mapping[str, float]
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.binding_context, NetworkBindingContext):
            raise TypeError(
                "ComponentProviderExecutionContext.binding_context must be a "
                f"NetworkBindingContext; got {type(self.binding_context).__name__!r}"
            )
        uv = self.unknown_values
        if not isinstance(uv, Mapping):
            raise TypeError(
                "ComponentProviderExecutionContext.unknown_values must be a Mapping; "
                f"got {type(uv).__name__!r}"
            )
        object.__setattr__(self, "unknown_values", MappingProxyType(dict(uv)))
        md = self.metadata
        if md is not None:
            if not isinstance(md, Mapping):
                raise TypeError(
                    "ComponentProviderExecutionContext.metadata must be a Mapping "
                    f"or None; got {type(md).__name__!r}"
                )
            object.__setattr__(self, "metadata", MappingProxyType(dict(md)))


# ---------------------------------------------------------------------------
# ComponentContributionProviderProtocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ComponentContributionProviderProtocol(Protocol):
    """Structural protocol for controlled component-like contribution providers.

    A component-like contribution provider is a controlled object that exposes
    a single safe method: ``produce_records``.  The method receives an immutable
    ``ComponentProviderExecutionContext`` and returns a ``ContributionRecordSet``.

    The method is deliberately NOT named ``contribute`` and MUST NOT call
    ``Component.contribute(...)``.

    Any object with a callable ``produce_records`` attribute satisfies this
    protocol.  No base-class inheritance is required.  No production component
    class is imported or executed.

    Protocol method
    ---------------
    produce_records(context: ComponentProviderExecutionContext) -> ContributionRecordSet
    """

    def produce_records(
        self, context: ComponentProviderExecutionContext
    ) -> ContributionRecordSet: ...


# ---------------------------------------------------------------------------
# ComponentContributionProviderBinding
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ComponentContributionProviderBinding:
    """Frozen binding of a component instance ID to a contribution provider.

    Declares that the given provider is responsible for producing contribution
    records for the named component instance.  The provider must expose a
    callable ``produce_records`` method.

    The provider is NOT a real production component class.  No production
    component base class is imported.  The method is NOT named ``contribute``.

    Fields
    ------
    component_id : ComponentInstanceId identifying the component in the graph
    provider     : controlled object exposing a callable produce_records method

    Validation
    ----------
    - component_id must be a ComponentInstanceId.
    - provider must have a ``produce_records`` attribute.
    - provider.produce_records must be callable.
    """

    component_id: ComponentInstanceId
    provider: object

    def __post_init__(self) -> None:
        if not isinstance(self.component_id, ComponentInstanceId):
            raise TypeError(
                "ComponentContributionProviderBinding.component_id must be a "
                f"ComponentInstanceId; got {type(self.component_id).__name__!r}"
            )
        if not hasattr(self.provider, "produce_records"):
            raise TypeError(
                "ComponentContributionProviderBinding.provider must expose a "
                "callable 'produce_records' method; "
                f"{type(self.provider).__name__!r} has no attribute 'produce_records'"
            )
        if not callable(getattr(self.provider, "produce_records")):
            raise TypeError(
                "ComponentContributionProviderBinding.provider.produce_records "
                f"must be callable; got non-callable on "
                f"{type(self.provider).__name__!r}"
            )


# ---------------------------------------------------------------------------
# ComponentContributionProviderSet
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ComponentContributionProviderSet:
    """Validated, ordered, immutable collection of provider bindings.

    Preserves insertion order.  Rejects wrong entry types and duplicate
    component instance IDs.  Internal state is immutable after construction;
    mutating the source list does not affect this object.

    Fields
    ------
    bindings : tuple[ComponentContributionProviderBinding, ...]
        Ordered provider bindings, one per component instance.

    Validation
    ----------
    - Every entry must be a ComponentContributionProviderBinding.
    - No two bindings may share a component instance ID.
    """

    bindings: tuple[ComponentContributionProviderBinding, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.bindings, tuple):
            object.__setattr__(self, "bindings", tuple(self.bindings))
        for i, b in enumerate(self.bindings):
            if not isinstance(b, ComponentContributionProviderBinding):
                raise TypeError(
                    f"ComponentContributionProviderSet.bindings[{i}] must be a "
                    f"ComponentContributionProviderBinding; got {type(b).__name__!r}"
                )
        seen: set[str] = set()
        for b in self.bindings:
            iid = b.component_id.value
            if iid in seen:
                raise ValueError(
                    "ComponentContributionProviderSet: duplicate component_id "
                    f"{b.component_id.value!r}"
                )
            seen.add(iid)


# ---------------------------------------------------------------------------
# execute_component_provider_contributions
# ---------------------------------------------------------------------------


def execute_component_provider_contributions(
    binding_context: object,
    provider_set: object,
    unknown_values: object,
    *,
    metadata: object = None,
) -> ContributionRecordSet:
    """Execute all provider objects and return a ContributionRecordSet.

    Validates binding coverage (exact match required between provider component
    IDs and bound component IDs in the binding context), constructs a shared
    ComponentProviderExecutionContext, invokes each provider's
    ``produce_records`` method in binding order, validates all outputs, and
    returns the assembled records.

    Each provider must return a ``ContributionRecordSet`` containing only
    records for its bound component_id.

    Parameters
    ----------
    binding_context
        NetworkBindingContext from Phase 14B.  Provides the bound component
        instances against which provider coverage is validated.
    provider_set
        ComponentContributionProviderSet or iterable of
        ComponentContributionProviderBinding.  Exact coverage required: every
        bound component must have exactly one provider, and every provider must
        reference a bound component.
    unknown_values
        Mapping from unknown name to current float value.  Defensively copied
        into the shared ComponentProviderExecutionContext.
    metadata
        Optional Mapping[str, object] passed into the context.  Defensively
        copied.  None by default.

    Returns
    -------
    ContributionRecordSet
        Ordered records produced by all providers, in binding order (and within
        each provider, in the order the provider produced them).

    Raises
    ------
    TypeError
        If binding_context is not a NetworkBindingContext.
        If unknown_values is not a Mapping.
        If metadata is not a Mapping or None.
        If any provider binding entry is not a ComponentContributionProviderBinding.
        If a provider returns a non-ContributionRecordSet.
    ValueError
        If any provider references a component not bound in the context (extra).
        If any bound component has no provider (missing).
        If a record belongs to a different component_id than the binding.
        If duplicate (component_id, name) pairs occur across all outputs.

    Notes
    -----
    This function MUST NOT execute real component classes, call contribute(...)
    on any component, assemble SystemState, inspect component_type to generate
    physics, call property backends or registries, or attach physical state to
    graph nodes.  All contribution logic is via controlled provider objects.
    """
    # --- validate binding_context ---
    if not isinstance(binding_context, NetworkBindingContext):
        raise TypeError(
            "execute_component_provider_contributions: binding_context must be a "
            f"NetworkBindingContext; got {type(binding_context).__name__!r}"
        )

    # --- validate unknown_values ---
    if not isinstance(unknown_values, Mapping):
        raise TypeError(
            "execute_component_provider_contributions: unknown_values must be a "
            f"Mapping; got {type(unknown_values).__name__!r}"
        )

    # --- validate metadata ---
    if metadata is not None and not isinstance(metadata, Mapping):
        raise TypeError(
            "execute_component_provider_contributions: metadata must be a "
            f"Mapping or None; got {type(metadata).__name__!r}"
        )

    # --- normalize provider_set ---
    if isinstance(provider_set, ComponentContributionProviderSet):
        pset = provider_set
    else:
        try:
            provider_list = list(provider_set)  # type: ignore[arg-type]
        except TypeError as exc:
            raise TypeError(
                "execute_component_provider_contributions: provider_set must be a "
                "ComponentContributionProviderSet or iterable of "
                "ComponentContributionProviderBinding; "
                f"got {type(provider_set).__name__!r}"
            ) from exc
        for i, b in enumerate(provider_list):
            if not isinstance(b, ComponentContributionProviderBinding):
                raise TypeError(
                    f"execute_component_provider_contributions: provider_set[{i}] "
                    f"must be a ComponentContributionProviderBinding; "
                    f"got {type(b).__name__!r}"
                )
        pset = ComponentContributionProviderSet(bindings=tuple(provider_list))

    # --- validate exact coverage ---
    bound_ids: frozenset[str] = frozenset(
        b.instance_id.value for b in binding_context.binding_set.bindings
    )
    provider_ids: frozenset[str] = frozenset(b.component_id.value for b in pset.bindings)

    missing = bound_ids - provider_ids
    if missing:
        raise ValueError(
            "execute_component_provider_contributions: missing providers for "
            f"bound components: {sorted(missing)!r}"
        )

    extra = provider_ids - bound_ids
    if extra:
        raise ValueError(
            "execute_component_provider_contributions: providers reference "
            f"components not bound in binding_context: {sorted(extra)!r}"
        )

    # --- build shared context ---
    ctx = ComponentProviderExecutionContext(
        binding_context=binding_context,
        unknown_values=unknown_values,
        metadata=metadata,
    )

    # --- execute each provider in binding order ---
    all_records: list[ContributionRecord] = []
    seen_keys: set[tuple[str, str]] = set()

    for binding in pset.bindings:
        result = binding.provider.produce_records(ctx)

        if not isinstance(result, ContributionRecordSet):
            raise TypeError(
                f"execute_component_provider_contributions: provider for "
                f"{binding.component_id.value!r} must return a "
                f"ContributionRecordSet; got {type(result).__name__!r}"
            )

        for record in result.records:
            if record.component_id != binding.component_id:
                raise ValueError(
                    f"execute_component_provider_contributions: provider for "
                    f"{binding.component_id.value!r} returned a record for a "
                    f"different component {record.component_id.value!r}"
                )
            key = (record.component_id.value, record.name)
            if key in seen_keys:
                raise ValueError(
                    "execute_component_provider_contributions: duplicate "
                    f"(component_id, name) pair "
                    f"({record.component_id.value!r}, {record.name!r})"
                )
            seen_keys.add(key)
            all_records.append(record)

    return ContributionRecordSet(records=tuple(all_records))


# ---------------------------------------------------------------------------
# build_component_contribution_from_provider_execution
# ---------------------------------------------------------------------------


def build_component_contribution_from_provider_execution(
    component_id: object,
    binding_context: object,
    provider_set: object,
    residual_map: object,
    unknown_values: object,
    *,
    allowed_residual_names: frozenset[str] | set[str] | None = None,
    metadata: object = None,
) -> ComponentContribution:
    """Convenience wrapper: provider execution → Phase 14D mapping → ComponentContribution.

    Executes all provider objects via execute_component_provider_contributions,
    then calls Phase 14D map_contribution_records_to_component_contribution to
    translate the records for the requested component_id into a Phase 14C
    ComponentContribution.

    This is a thin convenience wrapper only.  It introduces no new evaluation
    path.  All input validation is delegated to the called functions.

    Parameters
    ----------
    component_id
        ComponentInstanceId of the component whose contribution to return.
    binding_context
        NetworkBindingContext from Phase 14B.
    provider_set
        ComponentContributionProviderSet or iterable of
        ComponentContributionProviderBinding.
    residual_map
        ContributionResidualMap for translating contribution names to residual names.
    unknown_values
        Mapping from unknown name to current float value.
    allowed_residual_names
        Optional set of declared residual names.  If supplied, mapped residual
        names not in this set are rejected.
    metadata
        Optional Mapping[str, object] passed to the execution context.

    Returns
    -------
    ComponentContribution
        Phase 14C contribution result for the requested component.

    Notes
    -----
    This function MUST NOT execute real component classes, call contribute(...)
    on any component, assemble SystemState, inspect component_type to generate
    physics, call property backends or registries, or attach physical state to
    graph nodes.
    """
    record_set = execute_component_provider_contributions(
        binding_context,
        provider_set,
        unknown_values,
        metadata=metadata,
    )
    return map_contribution_records_to_component_contribution(
        component_id,
        record_set,
        residual_map,
        allowed_residual_names=allowed_residual_names,
    )
