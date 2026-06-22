"""Controlled production-like bridge path — Block 15A.3.

Provides a narrow, explicit helper/protocol layer for controlled
production-like stub objects that read unknown values through the existing
Block 15A.2 ``ReadOnlyUnknownView`` and produce ``ContributionRecordSet``
records for delivery into the existing Phase 14D/14C path.

This checkpoint is called "production-like" because the stub objects exposed
here:

* are bound to an explicit component instance ID;
* can read scoped unknowns via ``ReadOnlyUnknownView`` (Block 15A.2);
* return explicit ``ContributionRecordSet`` records;
* represent the shape that future production adapters will take;

but they are NOT real production component classes and are NOT pretended to be.

What this module DOES
---------------------
- Defines ``ProductionLikeBridgeContext``: immutable context passed to
  production-like record producers.  Carries a ``NetworkBindingContext``,
  defensively copied read-only unknown values, a pre-built
  ``ReadOnlyUnknownView`` (Block 15A.2) for component- and node-scoped
  access, and optional defensively copied metadata.  Does not assemble
  ``SystemState``, does not create ``FluidState``, does not call any property
  backend.  Construction validates exact coverage of assembly-declared unknowns
  via ``ReadOnlyUnknownView`` — a stricter guarantee than the plain Block 15A.1
  bridge context.
- Defines ``ProductionLikeRecordProducerProtocol``: a ``typing.Protocol`` for
  controlled production-like stub objects.  Requires one callable method:
  ``produce_records(context: ProductionLikeBridgeContext) ->
  ContributionRecordSet``.  The method is deliberately NOT named ``contribute``
  and MUST NOT call any ``Component.contribute(...)`` method.
- Defines ``ProductionLikeComponentBinding``: frozen binding of a
  ``ComponentInstanceId`` to a production-like producer.  Validates that the
  producer exposes a callable ``produce_records`` method.  Does not import or
  require production component base classes.
- Defines ``ProductionLikeComponentSet``: validated, ordered, immutable
  collection of ``ProductionLikeComponentBinding`` entries.  Rejects wrong
  types and duplicate component instance IDs.  Immutable after construction.
- Defines ``execute_production_like_contributions``: drives the full
  production-like execution loop.  Validates exact producer coverage, constructs
  a shared ``ProductionLikeBridgeContext`` (which validates exact unknown
  coverage), invokes each producer's ``produce_records`` method in binding
  order, validates return types and record ownership, checks for duplicates,
  propagates producer exceptions, and returns a ``ContributionRecordSet``.
- Defines ``build_component_contribution_from_production_like_execution``:
  convenience wrapper calling ``execute_production_like_contributions`` then
  Phase 14D ``map_contribution_records_to_component_contribution`` to produce a
  Phase 14C ``ComponentContribution``.

What this module DOES NOT DO
-----------------------------
This is a controlled production-like bridge path only.  It MUST NOT and
DOES NOT:
- Execute real production component classes (``Component``, ``Pipe``, etc.).
- Import production component classes.
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
- Implement arbitrary-topology physical simulation.

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
  producer set, or contribution records.

Block 15A.3 status
------------------
This checkpoint adds a controlled production-like stub/adapter path that
makes the Block 15A.1 bridge boundary more concrete by exposing the Block
15A.2 ``ReadOnlyUnknownView`` directly inside the execution context.
Production-like objects are explicitly supplied by the caller and use
``produce_records(...)`` — not ``contribute(...)``.  It does not execute real
production components, assemble ``SystemState``, create ``FluidState``, or call
properties, correlations, or HX models.  Block 15B physical single-loop network
simulation and arbitrary-topology physical simulation remain deferred.

Exported names
--------------
ProductionLikeBridgeContext
    — immutable context passed to production-like producers; includes a
      pre-built ReadOnlyUnknownView
ProductionLikeRecordProducerProtocol
    — typing.Protocol for safe production-like producer objects
ProductionLikeComponentBinding
    — frozen (component_id, producer) binding
ProductionLikeComponentSet
    — validated ordered collection of bindings
execute_production_like_contributions
    — drive producers → ContributionRecordSet
build_component_contribution_from_production_like_execution
    — convenience wrapper to ComponentContribution
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
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
from mpl_sim.network.readonly_state_bridge import ReadOnlyUnknownView, build_readonly_unknown_view

# ---------------------------------------------------------------------------
# ProductionLikeBridgeContext
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProductionLikeBridgeContext:
    """Immutable context passed to production-like record producers.

    Carries the binding context, the current unknown-value mapping, a
    pre-built ``ReadOnlyUnknownView`` for component- and node-scoped access,
    and optional caller metadata.

    Does not assemble SystemState, compute properties, execute component
    physics, call property backends, or attach state to graph nodes.

    Unlike the plain Block 15A.1 ``ProductionBridgeExecutionContext``, this
    context pre-builds and stores a ``ReadOnlyUnknownView`` at construction
    time.  Construction therefore requires that all assembly-declared unknowns
    are present in ``unknown_values`` and that no extra unknowns are supplied —
    the ``ReadOnlyUnknownView`` validates exact coverage.

    This is the Block 15A.3 production-like execution context.  It is passed
    to controlled production-like stub objects via their ``produce_records``
    method — not to real production component classes and not to any
    ``contribute(...)`` method.

    Fields
    ------
    binding_context : NetworkBindingContext from Phase 14B; immutable
    unknown_values  : read-only mapping; defensively copied at construction;
                      must cover exactly all assembly-declared unknowns
    view            : ReadOnlyUnknownView built from binding_context and
                      unknown_values; available for component/node scoping
    metadata        : optional caller-supplied metadata; defensively copied;
                      None if not supplied

    Validation
    ----------
    - binding_context must be a NetworkBindingContext.
    - unknown_values must be a Mapping; defensively copied to MappingProxyType.
    - unknown_values must cover exactly all assembly-declared unknowns (no
      missing, no extra); enforced by ReadOnlyUnknownView construction.
    - All unknown values must be finite and non-bool.
    - metadata must be a Mapping or None; defensively copied to MappingProxyType.
    """

    binding_context: NetworkBindingContext
    unknown_values: Mapping[str, float]
    view: ReadOnlyUnknownView = field(init=False)
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.binding_context, NetworkBindingContext):
            raise TypeError(
                "ProductionLikeBridgeContext.binding_context must be a "
                f"NetworkBindingContext; got {type(self.binding_context).__name__!r}"
            )
        uv = self.unknown_values
        if not isinstance(uv, Mapping):
            raise TypeError(
                "ProductionLikeBridgeContext.unknown_values must be a Mapping; "
                f"got {type(uv).__name__!r}"
            )
        view = build_readonly_unknown_view(self.binding_context, uv)
        object.__setattr__(self, "unknown_values", MappingProxyType(dict(view.values)))
        object.__setattr__(self, "view", view)
        md = self.metadata
        if md is not None:
            if not isinstance(md, Mapping):
                raise TypeError(
                    "ProductionLikeBridgeContext.metadata must be a Mapping "
                    f"or None; got {type(md).__name__!r}"
                )
            object.__setattr__(self, "metadata", MappingProxyType(dict(md)))


# ---------------------------------------------------------------------------
# ProductionLikeRecordProducerProtocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ProductionLikeRecordProducerProtocol(Protocol):
    """Structural protocol for controlled production-like stub producer objects.

    A production-like stub producer is a controlled object that exposes a
    single safe method: ``produce_records``.  The method receives an immutable
    ``ProductionLikeBridgeContext`` (which includes a pre-built
    ``ReadOnlyUnknownView``) and returns a ``ContributionRecordSet``.

    The method is deliberately NOT named ``contribute`` and MUST NOT call
    ``Component.contribute(...)``.  Production-like objects used at the Block
    15A.3 boundary are controlled stubs or future adapters — not real
    production component instances.

    Any object with a callable ``produce_records`` attribute satisfies this
    protocol.  No base-class inheritance is required.  No production component
    class is imported or executed.

    Protocol method
    ---------------
    produce_records(context: ProductionLikeBridgeContext) -> ContributionRecordSet
    """

    def produce_records(self, context: ProductionLikeBridgeContext) -> ContributionRecordSet: ...


# ---------------------------------------------------------------------------
# ProductionLikeComponentBinding
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProductionLikeComponentBinding:
    """Frozen binding of a component instance ID to a production-like producer.

    Declares that the given production-like producer is responsible for
    producing contribution records for the named component instance at the
    Block 15A.3 production-like bridge path.  The producer must expose a
    callable ``produce_records`` method.

    The producer is NOT a real production component class.  No production
    component base class is imported.  The method is NOT named ``contribute``.

    Fields
    ------
    component_id : ComponentInstanceId identifying the component in the graph
    producer     : controlled object exposing a callable produce_records method

    Validation
    ----------
    - component_id must be a ComponentInstanceId.
    - producer must have a ``produce_records`` attribute.
    - producer.produce_records must be callable.
    """

    component_id: ComponentInstanceId
    producer: object

    def __post_init__(self) -> None:
        if not isinstance(self.component_id, ComponentInstanceId):
            raise TypeError(
                "ProductionLikeComponentBinding.component_id must be a "
                f"ComponentInstanceId; got {type(self.component_id).__name__!r}"
            )
        if not hasattr(self.producer, "produce_records"):
            raise TypeError(
                "ProductionLikeComponentBinding.producer must expose a callable "
                "'produce_records' method; "
                f"{type(self.producer).__name__!r} has no attribute 'produce_records'"
            )
        if not callable(getattr(self.producer, "produce_records")):
            raise TypeError(
                "ProductionLikeComponentBinding.producer.produce_records must be "
                f"callable; got non-callable on {type(self.producer).__name__!r}"
            )


# ---------------------------------------------------------------------------
# ProductionLikeComponentSet
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProductionLikeComponentSet:
    """Validated, ordered, immutable collection of production-like bindings.

    Preserves insertion order.  Rejects wrong entry types and duplicate
    component instance IDs.  Internal state is immutable after construction;
    mutating the source list does not affect this object.

    Fields
    ------
    bindings : tuple[ProductionLikeComponentBinding, ...]
        Ordered producer bindings, one per component instance.

    Validation
    ----------
    - Every entry must be a ProductionLikeComponentBinding.
    - No two bindings may share a component instance ID.
    """

    bindings: tuple[ProductionLikeComponentBinding, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.bindings, tuple):
            object.__setattr__(self, "bindings", tuple(self.bindings))
        for i, b in enumerate(self.bindings):
            if not isinstance(b, ProductionLikeComponentBinding):
                raise TypeError(
                    f"ProductionLikeComponentSet.bindings[{i}] must be a "
                    f"ProductionLikeComponentBinding; got {type(b).__name__!r}"
                )
        seen: set[str] = set()
        for b in self.bindings:
            iid = b.component_id.value
            if iid in seen:
                raise ValueError(
                    "ProductionLikeComponentSet: duplicate component_id "
                    f"{b.component_id.value!r}"
                )
            seen.add(iid)


# ---------------------------------------------------------------------------
# execute_production_like_contributions
# ---------------------------------------------------------------------------


def execute_production_like_contributions(
    binding_context: object,
    producer_set: object,
    unknown_values: object,
    *,
    metadata: object = None,
) -> ContributionRecordSet:
    """Execute all production-like producers and return a ContributionRecordSet.

    Validates binding coverage (exact match required between producer component
    IDs and bound component IDs in the binding context), constructs a shared
    ``ProductionLikeBridgeContext`` (which validates exact assembly unknown
    coverage via ``ReadOnlyUnknownView``), invokes each producer's
    ``produce_records`` method in binding order, validates all outputs, and
    returns the assembled records.

    Each producer must return a ``ContributionRecordSet`` containing only
    records for its bound ``component_id``.

    Parameters
    ----------
    binding_context
        ``NetworkBindingContext`` from Phase 14B.  Provides the bound component
        instances against which producer coverage is validated, and the assembly
        declarations against which unknown_values coverage is validated.
    producer_set
        ``ProductionLikeComponentSet`` or iterable of
        ``ProductionLikeComponentBinding``.  Exact coverage required: every
        bound component must have exactly one producer binding, and every
        producer binding must reference a bound component.
    unknown_values
        Mapping from unknown name to current float value.  Must cover exactly
        all assembly-declared unknowns (no missing, no extra; all finite,
        non-bool).  Defensively copied into the shared
        ``ProductionLikeBridgeContext``.
    metadata
        Optional ``Mapping[str, object]`` passed into the context.
        Defensively copied.  None by default.

    Returns
    -------
    ContributionRecordSet
        Ordered records produced by all producers, in binding order (and
        within each producer, in the order the producer returned them).

    Raises
    ------
    TypeError
        If ``binding_context`` is not a ``NetworkBindingContext``.
        If ``unknown_values`` is not a Mapping.
        If ``metadata`` is not a Mapping or None.
        If any producer binding entry is not a ``ProductionLikeComponentBinding``.
        If a producer returns a non-``ContributionRecordSet``.
    ValueError
        If any producer references a component not bound in the context (extra).
        If any bound component has no producer binding (missing).
        If any unknown is missing from or extra in the assembly declarations.
        If any unknown value is non-finite or bool.
        If a record belongs to a different ``component_id`` than the binding.
        If duplicate (component_id, name) pairs occur across all outputs.

    Notes
    -----
    This function MUST NOT execute real production component classes, call
    ``contribute(...)`` on any object, assemble SystemState, inspect
    ``component_type`` to generate physics, call property backends or
    registries, or attach physical state to graph nodes.  All contribution
    logic is via controlled production-like producers exposing ``produce_records``.

    Block 15A.3: producers are controlled stubs, not real production component
    instances.  Physical production-component execution remains deferred to
    later Block 15A/15B work.
    """
    # --- validate binding_context ---
    if not isinstance(binding_context, NetworkBindingContext):
        raise TypeError(
            "execute_production_like_contributions: binding_context must be a "
            f"NetworkBindingContext; got {type(binding_context).__name__!r}"
        )

    # --- validate unknown_values is a Mapping (coverage validated below via view) ---
    if not isinstance(unknown_values, Mapping):
        raise TypeError(
            "execute_production_like_contributions: unknown_values must be a "
            f"Mapping; got {type(unknown_values).__name__!r}"
        )

    # --- validate metadata ---
    if metadata is not None and not isinstance(metadata, Mapping):
        raise TypeError(
            "execute_production_like_contributions: metadata must be a "
            f"Mapping or None; got {type(metadata).__name__!r}"
        )

    # --- normalize producer_set ---
    if isinstance(producer_set, ProductionLikeComponentSet):
        pset = producer_set
    else:
        try:
            producer_list = list(producer_set)  # type: ignore[arg-type]
        except TypeError as exc:
            raise TypeError(
                "execute_production_like_contributions: producer_set must be a "
                "ProductionLikeComponentSet or iterable of "
                "ProductionLikeComponentBinding; "
                f"got {type(producer_set).__name__!r}"
            ) from exc
        for i, b in enumerate(producer_list):
            if not isinstance(b, ProductionLikeComponentBinding):
                raise TypeError(
                    f"execute_production_like_contributions: producer_set[{i}] "
                    "must be a ProductionLikeComponentBinding; "
                    f"got {type(b).__name__!r}"
                )
        pset = ProductionLikeComponentSet(bindings=tuple(producer_list))

    # --- validate exact producer coverage against bound components ---
    bound_ids: frozenset[str] = frozenset(
        b.instance_id.value for b in binding_context.binding_set.bindings
    )
    producer_ids: frozenset[str] = frozenset(b.component_id.value for b in pset.bindings)

    missing = bound_ids - producer_ids
    if missing:
        raise ValueError(
            "execute_production_like_contributions: missing producer bindings "
            f"for bound components: {sorted(missing)!r}"
        )

    extra = producer_ids - bound_ids
    if extra:
        raise ValueError(
            "execute_production_like_contributions: producer bindings reference "
            f"components not bound in binding_context: {sorted(extra)!r}"
        )

    # --- build shared context (validates exact unknown coverage via ReadOnlyUnknownView) ---
    ctx = ProductionLikeBridgeContext(
        binding_context=binding_context,
        unknown_values=dict(unknown_values),  # type: ignore[arg-type]
        metadata=metadata,  # type: ignore[arg-type]
    )

    # --- execute each producer in binding order ---
    all_records: list[ContributionRecord] = []
    seen_keys: set[tuple[str, str]] = set()

    for binding in pset.bindings:
        result = binding.producer.produce_records(ctx)

        if not isinstance(result, ContributionRecordSet):
            raise TypeError(
                "execute_production_like_contributions: producer for "
                f"{binding.component_id.value!r} must return a "
                f"ContributionRecordSet; got {type(result).__name__!r}"
            )

        for record in result.records:
            if record.component_id != binding.component_id:
                raise ValueError(
                    "execute_production_like_contributions: producer for "
                    f"{binding.component_id.value!r} returned a record for a "
                    f"different component {record.component_id.value!r}"
                )
            key = (record.component_id.value, record.name)
            if key in seen_keys:
                raise ValueError(
                    "execute_production_like_contributions: duplicate "
                    f"(component_id, name) pair "
                    f"({record.component_id.value!r}, {record.name!r})"
                )
            seen_keys.add(key)
            all_records.append(record)

    return ContributionRecordSet(records=tuple(all_records))


# ---------------------------------------------------------------------------
# build_component_contribution_from_production_like_execution
# ---------------------------------------------------------------------------


def build_component_contribution_from_production_like_execution(
    component_id: object,
    binding_context: object,
    producer_set: object,
    residual_map: object,
    unknown_values: object,
    *,
    allowed_residual_names: frozenset[str] | set[str] | None = None,
    metadata: object = None,
) -> ComponentContribution:
    """Convenience wrapper: production-like execution → Phase 14D mapping → ComponentContribution.

    Executes all producers via ``execute_production_like_contributions``,
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
    producer_set
        ``ProductionLikeComponentSet`` or iterable of
        ``ProductionLikeComponentBinding``.
    residual_map
        ``ContributionResidualMap`` for translating contribution names to
        residual names.
    unknown_values
        Mapping from unknown name to current float value.  Must cover exactly
        all assembly-declared unknowns.
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

    Block 15A.3: producers are controlled stubs, not real production
    component instances.
    """
    record_set = execute_production_like_contributions(
        binding_context,
        producer_set,
        unknown_values,
        metadata=metadata,
    )
    return map_contribution_records_to_component_contribution(
        component_id,
        record_set,
        residual_map,
        allowed_residual_names=allowed_residual_names,
    )
