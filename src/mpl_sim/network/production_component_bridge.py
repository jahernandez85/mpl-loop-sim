"""Production component bridge boundary — Block 15A.1.

Provides the **first controlled bridge boundary** toward future production
component contribution execution.  This module is structurally identical in
safety posture to Phase 14F (``component_provider_adapters``), but is named and
documented as the Block 15A.1 production-component bridge seam.

The bridge boundary does NOT execute existing production component classes.
It does NOT define or call a method named ``contribute``.  It does NOT assemble
``SystemState`` or ``FluidState``.  It does NOT call CoolProp, PropertyBackend,
correlations, or any registry.  It creates the *seam* where future production
adapters can be plugged in, without pretending that real production components
are ready.

The six known production component classes (``Component``, ``Pipe``,
``PumpComponent``, ``AccumulatorComponent``, ``EvaporatorComponent``,
``CondenserComponent``) do NOT currently implement ``contribute(...)`` — as
verified by Phase 14G inspection.  Therefore this module does NOT attempt to
adapt any existing ``contribute`` implementation.

What this module DOES
---------------------
- Defines ``ProductionBridgeExecutionContext``: immutable context passed to
  bridge objects.  Carries a ``NetworkBindingContext``, defensively copied
  read-only unknown values, and optional defensively copied metadata.  Does not
  store ``SystemState``, does not create ``FluidState``, does not call any
  property backend.
- Defines ``ProductionContributionBridgeProtocol``: a ``typing.Protocol`` for
  controlled production-bridge objects.  Requires one callable method:
  ``produce_records(context: ProductionBridgeExecutionContext) ->
  ContributionRecordSet``.  The method is deliberately NOT named ``contribute``
  and does NOT call any ``Component.contribute(...)`` method.
- Defines ``ProductionComponentBridgeBinding``: frozen binding of a
  ``ComponentInstanceId`` to a bridge object.  Validates that the bridge object
  exposes a callable ``produce_records`` method.  Does not import or require
  production component base classes.
- Defines ``ProductionComponentBridgeSet``: validated, ordered, immutable
  collection of ``ProductionComponentBridgeBinding`` entries.  Rejects wrong
  types and duplicate component instance IDs.  Immutable after construction.
- Defines ``execute_production_bridge_contributions``: drives the full bridge
  execution loop.  Validates exact binding coverage, constructs a shared
  ``ProductionBridgeExecutionContext``, invokes each bridge object's
  ``produce_records`` method in binding order, validates return types and record
  ownership, checks for duplicates, propagates bridge exceptions, and returns a
  ``ContributionRecordSet``.
- Defines ``build_component_contribution_from_production_bridge_execution``:
  convenience wrapper calling ``execute_production_bridge_contributions`` then
  Phase 14D ``map_contribution_records_to_component_contribution`` to produce a
  Phase 14C ``ComponentContribution``.

What this module DOES NOT DO
-----------------------------
This is a controlled bridge boundary layer only.  It MUST NOT and DOES NOT:
- Execute real production component classes (``Component``, ``Pipe``, etc.).
- Call or define a method named ``contribute`` on any object or type.
- Assemble ``SystemState``, ``FluidState``, or any physical state.
- Compute or look up thermodynamic properties.
- Call CoolProp, PropertyBackend, or any property engine.
- Call CorrelationRegistry, HeatExchangerModelRegistry, or any registry.
- Attach physical state to graph nodes.
- Infer or generate physics from ``component_type``.
- Implement ``solve(network)`` or automatic residual construction.
- Import ``mpl_sim.solvers``, ``mpl_sim.components``, ``mpl_sim.properties``,
  ``mpl_sim.correlations``, ``mpl_sim.calibration``, or ``mpl_sim.hx_models``.
- Implement Block 15B physical single-loop simulation.

Architecture boundaries (MUST NOT)
-----------------------------------
- MUST NOT import ``mpl_sim.solvers``, ``mpl_sim.components``,
  ``mpl_sim.properties``, ``mpl_sim.calibration``, ``mpl_sim.hx_models``,
  or CoolProp.
- MUST NOT import or invoke ``CorrelationRegistry`` or
  ``HeatExchangerModelRegistry``.
- MUST NOT expose a ``solve(network)`` method on any type in this module.
- MUST NOT define a method named ``contribute`` anywhere in this module.
- MUST NOT perform property lookup, real component execution, or
  ``contribute(...)`` calls.
- MUST NOT mutate caller-supplied binding context, unknown values, metadata,
  bridge set, or contribution records.

Block 15A.1 status
------------------
This checkpoint introduces the bridge *boundary* only.  Real production
component objects are not wired through it.  Bridge objects used in tests are
controlled stubs that expose ``produce_records`` — they are not real production
components and are not pretended to be.  Physical production-component execution
remains deferred to later Block 15A/15B work.

Exported names
--------------
ProductionBridgeExecutionContext
    — immutable context passed to bridge objects
ProductionContributionBridgeProtocol
    — typing.Protocol for safe bridge objects
ProductionComponentBridgeBinding
    — frozen (component_id, bridge) binding
ProductionComponentBridgeSet
    — validated ordered collection of bindings
execute_production_bridge_contributions
    — drive bridge objects → ContributionRecordSet
build_component_contribution_from_production_bridge_execution
    — convenience wrapper to ComponentContribution
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
# ProductionBridgeExecutionContext
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProductionBridgeExecutionContext:
    """Immutable context passed to production-component bridge objects.

    Carries the binding context, the current unknown-value mapping, and
    optional caller metadata.  Does not assemble SystemState, compute
    properties, execute component physics, call property backends, or
    attach state to graph nodes.

    This is the Block 15A.1 bridge execution context.  It is passed to
    controlled bridge objects via their ``produce_records`` method — not to
    real production component classes and not to any ``contribute(...)`` method.

    Fields
    ------
    binding_context : NetworkBindingContext from Phase 14B; immutable
    unknown_values  : read-only mapping; defensively copied at construction
    metadata        : optional caller-supplied metadata; defensively copied;
                      None if not supplied

    Validation
    ----------
    - binding_context must be a NetworkBindingContext.
    - unknown_values must be a Mapping; defensively copied to MappingProxyType.
    - metadata must be a Mapping or None; defensively copied to MappingProxyType.
    """

    binding_context: NetworkBindingContext
    unknown_values: Mapping[str, float]
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.binding_context, NetworkBindingContext):
            raise TypeError(
                "ProductionBridgeExecutionContext.binding_context must be a "
                f"NetworkBindingContext; got {type(self.binding_context).__name__!r}"
            )
        uv = self.unknown_values
        if not isinstance(uv, Mapping):
            raise TypeError(
                "ProductionBridgeExecutionContext.unknown_values must be a Mapping; "
                f"got {type(uv).__name__!r}"
            )
        object.__setattr__(self, "unknown_values", MappingProxyType(dict(uv)))
        md = self.metadata
        if md is not None:
            if not isinstance(md, Mapping):
                raise TypeError(
                    "ProductionBridgeExecutionContext.metadata must be a Mapping "
                    f"or None; got {type(md).__name__!r}"
                )
            object.__setattr__(self, "metadata", MappingProxyType(dict(md)))


# ---------------------------------------------------------------------------
# ProductionContributionBridgeProtocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ProductionContributionBridgeProtocol(Protocol):
    """Structural protocol for controlled production-component bridge objects.

    A production-component bridge object is a controlled object that exposes
    a single safe method: ``produce_records``.  The method receives an immutable
    ``ProductionBridgeExecutionContext`` and returns a ``ContributionRecordSet``.

    The method is deliberately NOT named ``contribute`` and MUST NOT call
    ``Component.contribute(...)``.  Bridge objects used at the Block 15A.1
    boundary are controlled stubs or future adapters — not real production
    component instances.

    Any object with a callable ``produce_records`` attribute satisfies this
    protocol.  No base-class inheritance is required.  No production component
    class is imported or executed.

    Protocol method
    ---------------
    produce_records(context: ProductionBridgeExecutionContext) -> ContributionRecordSet
    """

    def produce_records(
        self, context: ProductionBridgeExecutionContext
    ) -> ContributionRecordSet: ...


# ---------------------------------------------------------------------------
# ProductionComponentBridgeBinding
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProductionComponentBridgeBinding:
    """Frozen binding of a component instance ID to a production-bridge object.

    Declares that the given bridge object is responsible for producing
    contribution records for the named component instance at the Block 15A.1
    bridge boundary.  The bridge object must expose a callable ``produce_records``
    method.

    The bridge object is NOT a real production component class.  No production
    component base class is imported.  The method is NOT named ``contribute``.

    Fields
    ------
    component_id : ComponentInstanceId identifying the component in the graph
    bridge       : controlled object exposing a callable produce_records method

    Validation
    ----------
    - component_id must be a ComponentInstanceId.
    - bridge must have a ``produce_records`` attribute.
    - bridge.produce_records must be callable.
    """

    component_id: ComponentInstanceId
    bridge: object

    def __post_init__(self) -> None:
        if not isinstance(self.component_id, ComponentInstanceId):
            raise TypeError(
                "ProductionComponentBridgeBinding.component_id must be a "
                f"ComponentInstanceId; got {type(self.component_id).__name__!r}"
            )
        if not hasattr(self.bridge, "produce_records"):
            raise TypeError(
                "ProductionComponentBridgeBinding.bridge must expose a callable "
                "'produce_records' method; "
                f"{type(self.bridge).__name__!r} has no attribute 'produce_records'"
            )
        if not callable(getattr(self.bridge, "produce_records")):
            raise TypeError(
                "ProductionComponentBridgeBinding.bridge.produce_records must be "
                f"callable; got non-callable on {type(self.bridge).__name__!r}"
            )


# ---------------------------------------------------------------------------
# ProductionComponentBridgeSet
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProductionComponentBridgeSet:
    """Validated, ordered, immutable collection of production-bridge bindings.

    Preserves insertion order.  Rejects wrong entry types and duplicate
    component instance IDs.  Internal state is immutable after construction;
    mutating the source list does not affect this object.

    Fields
    ------
    bindings : tuple[ProductionComponentBridgeBinding, ...]
        Ordered bridge bindings, one per component instance.

    Validation
    ----------
    - Every entry must be a ProductionComponentBridgeBinding.
    - No two bindings may share a component instance ID.
    """

    bindings: tuple[ProductionComponentBridgeBinding, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.bindings, tuple):
            object.__setattr__(self, "bindings", tuple(self.bindings))
        for i, b in enumerate(self.bindings):
            if not isinstance(b, ProductionComponentBridgeBinding):
                raise TypeError(
                    f"ProductionComponentBridgeSet.bindings[{i}] must be a "
                    f"ProductionComponentBridgeBinding; got {type(b).__name__!r}"
                )
        seen: set[str] = set()
        for b in self.bindings:
            iid = b.component_id.value
            if iid in seen:
                raise ValueError(
                    "ProductionComponentBridgeSet: duplicate component_id "
                    f"{b.component_id.value!r}"
                )
            seen.add(iid)


# ---------------------------------------------------------------------------
# execute_production_bridge_contributions
# ---------------------------------------------------------------------------


def execute_production_bridge_contributions(
    binding_context: object,
    bridge_set: object,
    unknown_values: object,
    *,
    metadata: object = None,
) -> ContributionRecordSet:
    """Execute all bridge objects and return a ContributionRecordSet.

    Validates binding coverage (exact match required between bridge component
    IDs and bound component IDs in the binding context), constructs a shared
    ``ProductionBridgeExecutionContext``, invokes each bridge object's
    ``produce_records`` method in binding order, validates all outputs, and
    returns the assembled records.

    Each bridge object must return a ``ContributionRecordSet`` containing only
    records for its bound ``component_id``.

    Parameters
    ----------
    binding_context
        ``NetworkBindingContext`` from Phase 14B.  Provides the bound component
        instances against which bridge coverage is validated.
    bridge_set
        ``ProductionComponentBridgeSet`` or iterable of
        ``ProductionComponentBridgeBinding``.  Exact coverage required: every
        bound component must have exactly one bridge binding, and every bridge
        binding must reference a bound component.
    unknown_values
        Mapping from unknown name to current float value.  Defensively copied
        into the shared ``ProductionBridgeExecutionContext``.
    metadata
        Optional ``Mapping[str, object]`` passed into the context.  Defensively
        copied.  None by default.

    Returns
    -------
    ContributionRecordSet
        Ordered records produced by all bridge objects, in binding order (and
        within each bridge object, in the order the bridge produced them).

    Raises
    ------
    TypeError
        If ``binding_context`` is not a ``NetworkBindingContext``.
        If ``unknown_values`` is not a Mapping.
        If ``metadata`` is not a Mapping or None.
        If any bridge binding entry is not a ``ProductionComponentBridgeBinding``.
        If a bridge object returns a non-``ContributionRecordSet``.
    ValueError
        If any bridge references a component not bound in the context (extra).
        If any bound component has no bridge binding (missing).
        If a record belongs to a different ``component_id`` than the binding.
        If duplicate (component_id, name) pairs occur across all outputs.

    Notes
    -----
    This function MUST NOT execute real production component classes, call
    ``contribute(...)`` on any object, assemble SystemState, inspect
    ``component_type`` to generate physics, call property backends or
    registries, or attach physical state to graph nodes.  All contribution logic
    is via controlled bridge objects exposing ``produce_records``.

    Block 15A.1: bridge objects are controlled stubs, not real production
    component instances.  Physical production-component execution remains
    deferred to later Block 15A/15B work.
    """
    # --- validate binding_context ---
    if not isinstance(binding_context, NetworkBindingContext):
        raise TypeError(
            "execute_production_bridge_contributions: binding_context must be a "
            f"NetworkBindingContext; got {type(binding_context).__name__!r}"
        )

    # --- validate unknown_values ---
    if not isinstance(unknown_values, Mapping):
        raise TypeError(
            "execute_production_bridge_contributions: unknown_values must be a "
            f"Mapping; got {type(unknown_values).__name__!r}"
        )

    # --- validate metadata ---
    if metadata is not None and not isinstance(metadata, Mapping):
        raise TypeError(
            "execute_production_bridge_contributions: metadata must be a "
            f"Mapping or None; got {type(metadata).__name__!r}"
        )

    # --- normalize bridge_set ---
    if isinstance(bridge_set, ProductionComponentBridgeSet):
        bset = bridge_set
    else:
        try:
            bridge_list = list(bridge_set)  # type: ignore[arg-type]
        except TypeError as exc:
            raise TypeError(
                "execute_production_bridge_contributions: bridge_set must be a "
                "ProductionComponentBridgeSet or iterable of "
                "ProductionComponentBridgeBinding; "
                f"got {type(bridge_set).__name__!r}"
            ) from exc
        for i, b in enumerate(bridge_list):
            if not isinstance(b, ProductionComponentBridgeBinding):
                raise TypeError(
                    f"execute_production_bridge_contributions: bridge_set[{i}] "
                    f"must be a ProductionComponentBridgeBinding; "
                    f"got {type(b).__name__!r}"
                )
        bset = ProductionComponentBridgeSet(bindings=tuple(bridge_list))

    # --- validate exact coverage ---
    bound_ids: frozenset[str] = frozenset(
        b.instance_id.value for b in binding_context.binding_set.bindings
    )
    bridge_ids: frozenset[str] = frozenset(b.component_id.value for b in bset.bindings)

    missing = bound_ids - bridge_ids
    if missing:
        raise ValueError(
            "execute_production_bridge_contributions: missing bridge bindings for "
            f"bound components: {sorted(missing)!r}"
        )

    extra = bridge_ids - bound_ids
    if extra:
        raise ValueError(
            "execute_production_bridge_contributions: bridge bindings reference "
            f"components not bound in binding_context: {sorted(extra)!r}"
        )

    # --- build shared context ---
    ctx = ProductionBridgeExecutionContext(
        binding_context=binding_context,
        unknown_values=unknown_values,
        metadata=metadata,
    )

    # --- execute each bridge in binding order ---
    all_records: list[ContributionRecord] = []
    seen_keys: set[tuple[str, str]] = set()

    for binding in bset.bindings:
        result = binding.bridge.produce_records(ctx)

        if not isinstance(result, ContributionRecordSet):
            raise TypeError(
                f"execute_production_bridge_contributions: bridge for "
                f"{binding.component_id.value!r} must return a "
                f"ContributionRecordSet; got {type(result).__name__!r}"
            )

        for record in result.records:
            if record.component_id != binding.component_id:
                raise ValueError(
                    f"execute_production_bridge_contributions: bridge for "
                    f"{binding.component_id.value!r} returned a record for a "
                    f"different component {record.component_id.value!r}"
                )
            key = (record.component_id.value, record.name)
            if key in seen_keys:
                raise ValueError(
                    "execute_production_bridge_contributions: duplicate "
                    f"(component_id, name) pair "
                    f"({record.component_id.value!r}, {record.name!r})"
                )
            seen_keys.add(key)
            all_records.append(record)

    return ContributionRecordSet(records=tuple(all_records))


# ---------------------------------------------------------------------------
# build_component_contribution_from_production_bridge_execution
# ---------------------------------------------------------------------------


def build_component_contribution_from_production_bridge_execution(
    component_id: object,
    binding_context: object,
    bridge_set: object,
    residual_map: object,
    unknown_values: object,
    *,
    allowed_residual_names: frozenset[str] | set[str] | None = None,
    metadata: object = None,
) -> ComponentContribution:
    """Convenience wrapper: bridge execution → Phase 14D mapping → ComponentContribution.

    Executes all bridge objects via ``execute_production_bridge_contributions``,
    then calls Phase 14D ``map_contribution_records_to_component_contribution``
    to translate the records for the requested ``component_id`` into a Phase 14C
    ``ComponentContribution``.

    This is a thin convenience wrapper only.  It introduces no new evaluation
    path.  All input validation is delegated to the called functions.

    Parameters
    ----------
    component_id
        ``ComponentInstanceId`` of the component whose contribution to return.
    binding_context
        ``NetworkBindingContext`` from Phase 14B.
    bridge_set
        ``ProductionComponentBridgeSet`` or iterable of
        ``ProductionComponentBridgeBinding``.
    residual_map
        ``ContributionResidualMap`` for translating contribution names to
        residual names.
    unknown_values
        Mapping from unknown name to current float value.
    allowed_residual_names
        Optional set of declared residual names.  If supplied, mapped residual
        names not in this set are rejected.
    metadata
        Optional ``Mapping[str, object]`` passed to the execution context.

    Returns
    -------
    ComponentContribution
        Phase 14C contribution result for the requested component.

    Notes
    -----
    This function MUST NOT execute real production component classes, call
    ``contribute(...)`` on any object, assemble SystemState, inspect
    ``component_type`` to generate physics, call property backends or
    registries, or attach physical state to graph nodes.

    Block 15A.1: bridge objects are controlled stubs, not real production
    component instances.
    """
    record_set = execute_production_bridge_contributions(
        binding_context,
        bridge_set,
        unknown_values,
        metadata=metadata,
    )
    return map_contribution_records_to_component_contribution(
        component_id,
        record_set,
        residual_map,
        allowed_residual_names=allowed_residual_names,
    )
