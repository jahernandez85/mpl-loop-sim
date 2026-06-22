"""Controlled toy component execution harness — Phase 14E.

Provides a minimal, controlled execution harness for **toy component contribution
functions only**.  Toy executors are caller-supplied functions that produce explicit
scalar contributions for a named component instance.  Their outputs are converted into
Phase 14D ``ContributionRecordSet`` objects, which can then be translated into Phase 14C
``ComponentContribution`` objects via Phase 14D mapping.

What this module DOES
---------------------
- Defines ToyComponentExecutionContext: immutable context passed to toy executor
  callbacks; carries the NetworkBindingContext, defensively copied unknown-value
  mapping, and optional metadata.  Does not assemble SystemState, compute
  properties, execute real component classes, or look up fluid properties.
- Defines ToyComponentExecutor: frozen binding of a ComponentInstanceId to a
  caller-supplied explicit toy callback.  The callback is the only executable
  element — no real component class is referenced.  Callback may return either
  a Mapping[str, float] (contribution name → float) or a ContributionRecordSet
  for the same component.
- Defines ToyComponentExecutorSet: validated, ordered, immutable collection of
  ToyComponentExecutor entries; rejects wrong types and duplicate component IDs.
- Defines execute_toy_component_contributions: drives the full toy execution loop.
  Validates binding coverage (exact match required), constructs a shared
  ToyComponentExecutionContext, invokes each toy callback in executor order,
  validates and converts outputs to ContributionRecord objects, checks for
  duplicates, and returns a ContributionRecordSet.
- Defines build_component_contribution_from_toy_execution: convenience wrapper
  that calls execute_toy_component_contributions and then calls Phase 14D
  map_contribution_records_to_component_contribution to produce a Phase 14C
  ComponentContribution.  This is a thin wrapper only — it introduces no new
  evaluation path.

What this module DOES NOT DO
-----------------------------
This is a toy execution harness only.  It MUST NOT and DOES NOT:
- Call or execute existing real component classes.
- Call the frozen component contribution method (contribute(...)).
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
- MUST NOT perform property lookup, real component execution, or contribute(...) calls.
- MUST NOT mutate the caller-supplied binding context, unknown values, metadata,
  executors, or contribution records.

Exported names
--------------
ToyComponentExecutionContext        — immutable context passed to toy callbacks
ToyComponentExecutor                — frozen (component_id, callback) toy binding
ToyComponentExecutorSet             — validated ordered collection of toy executors
execute_toy_component_contributions — drive toy callbacks → ContributionRecordSet
build_component_contribution_from_toy_execution — convenience wrapper to ComponentContribution
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from mpl_sim.network.component_binding import NetworkBindingContext
from mpl_sim.network.contribution_adapters import ComponentContribution
from mpl_sim.network.contribution_contract import (
    ContributionRecord,
    ContributionRecordSet,
    map_contribution_records_to_component_contribution,
)
from mpl_sim.network.graph import ComponentInstanceId

# ---------------------------------------------------------------------------
# ToyComponentExecutionContext
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToyComponentExecutionContext:
    """Immutable context passed to ToyComponentExecutor callbacks.

    Carries the binding context (graph + assembly + component binding
    declarations), the current unknown-value mapping, and optional caller
    metadata.  Does not assemble SystemState, compute properties, execute
    component physics, call property backends, or attach state to graph nodes.

    This is a toy-only execution context.  It is passed to caller-supplied
    explicit toy functions — not to real component classes and not to any
    contribute(...) method.

    Fields
    ------
    binding_context : NetworkBindingContext from Phase 14B; provides graph,
                      assembly, and binding declarations; immutable
    unknown_values  : read-only mapping from unknown name to current float
                      value; defensively copied at construction
    metadata        : optional caller-supplied metadata; defensively copied
                      and immutable after construction; None if not supplied

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
                "ToyComponentExecutionContext.binding_context must be a "
                f"NetworkBindingContext; got {type(self.binding_context).__name__!r}"
            )
        uv = self.unknown_values
        if not isinstance(uv, Mapping):
            raise TypeError(
                "ToyComponentExecutionContext.unknown_values must be a Mapping; "
                f"got {type(uv).__name__!r}"
            )
        object.__setattr__(self, "unknown_values", MappingProxyType(dict(uv)))
        md = self.metadata
        if md is not None:
            if not isinstance(md, Mapping):
                raise TypeError(
                    "ToyComponentExecutionContext.metadata must be a Mapping or None; "
                    f"got {type(md).__name__!r}"
                )
            object.__setattr__(self, "metadata", MappingProxyType(dict(md)))


# ---------------------------------------------------------------------------
# ToyComponentExecutor
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToyComponentExecutor:
    """Frozen binding of a component instance ID to an explicit toy callback.

    The callback receives a ToyComponentExecutionContext and returns either a
    Mapping[str, float] (contribution name → value) or a ContributionRecordSet
    for the bound component.  Returning a ContributionRecordSet is accepted
    provided every record in it belongs to this executor's component_id.

    This is a toy-only executor.  The callback is explicitly caller-supplied and
    is NOT the existing component contribute(...) API.  No real component class
    is referenced or executed.

    Callback signature (either):
        callback(context: ToyComponentExecutionContext) -> Mapping[str, float]
        callback(context: ToyComponentExecutionContext) -> ContributionRecordSet

    Fields
    ------
    component_id : ComponentInstanceId identifying the component in the graph
    callback     : callable receiving ToyComponentExecutionContext and returning
                   Mapping[str, float] or ContributionRecordSet

    Validation
    ----------
    - component_id must be a ComponentInstanceId.
    - callback must be callable.
    """

    component_id: ComponentInstanceId
    callback: Callable[
        [ToyComponentExecutionContext],
        Mapping[str, float] | ContributionRecordSet,
    ]

    def __post_init__(self) -> None:
        if not isinstance(self.component_id, ComponentInstanceId):
            raise TypeError(
                "ToyComponentExecutor.component_id must be a ComponentInstanceId; "
                f"got {type(self.component_id).__name__!r}"
            )
        if not callable(self.callback):
            raise TypeError(
                "ToyComponentExecutor.callback must be callable; "
                f"got {type(self.callback).__name__!r}"
            )


# ---------------------------------------------------------------------------
# ToyComponentExecutorSet
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToyComponentExecutorSet:
    """Validated, ordered, immutable collection of ToyComponentExecutor entries.

    Preserves insertion order.  Rejects wrong entry types and duplicate
    component instance IDs.

    Fields
    ------
    executors : tuple[ToyComponentExecutor, ...]
        Ordered executors, one per component instance.

    Validation
    ----------
    - Every entry must be a ToyComponentExecutor.
    - No two executors may share a component instance ID.
    """

    executors: tuple[ToyComponentExecutor, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.executors, tuple):
            object.__setattr__(self, "executors", tuple(self.executors))
        for i, e in enumerate(self.executors):
            if not isinstance(e, ToyComponentExecutor):
                raise TypeError(
                    f"ToyComponentExecutorSet.executors[{i}] must be a "
                    f"ToyComponentExecutor; got {type(e).__name__!r}"
                )
        seen: set[str] = set()
        for e in self.executors:
            iid = e.component_id.value
            if iid in seen:
                raise ValueError(
                    "ToyComponentExecutorSet: duplicate component_id " f"{e.component_id.value!r}"
                )
            seen.add(iid)


# ---------------------------------------------------------------------------
# execute_toy_component_contributions
# ---------------------------------------------------------------------------


def execute_toy_component_contributions(
    binding_context: object,
    executors: object,
    unknown_values: object,
    *,
    metadata: object = None,
) -> ContributionRecordSet:
    """Execute all toy component callbacks and return a ContributionRecordSet.

    Validates binding coverage (exact match required between executor component
    IDs and bound component IDs in the binding context), constructs a shared
    ToyComponentExecutionContext, invokes each toy callback in executor order,
    validates and converts all outputs, and returns the assembled records.

    Toy callbacks may return either:
    - a Mapping[str, float]: contribution name → finite numeric value; each
      entry becomes one ContributionRecord for the executor's component.
    - a ContributionRecordSet: must contain only records for the executor's
      component_id; used as-is.

    Parameters
    ----------
    binding_context
        NetworkBindingContext from Phase 14B.  Provides the bound component
        instances against which executor coverage is validated.
    executors
        ToyComponentExecutorSet or iterable of ToyComponentExecutor.  Exact
        coverage required: every bound component must have exactly one executor,
        and every executor must reference a bound component.
    unknown_values
        Mapping from unknown name to current float value.  Defensively copied
        into the shared ToyComponentExecutionContext.
    metadata
        Optional Mapping[str, object] passed into the context.  Defensively
        copied.  None by default.

    Returns
    -------
    ContributionRecordSet
        Ordered collection of ContributionRecord objects produced by all toy
        callbacks, in executor order (and within each callback, in the order
        the callback produced them).

    Raises
    ------
    TypeError
        If binding_context is not a NetworkBindingContext.
        If unknown_values is not a Mapping.
        If metadata is not a Mapping or None.
        If any executor entry is not a ToyComponentExecutor.
        If a callback returns an unsupported type.
        If a mapping output key is not a string.
        If a mapping output value is bool, non-numeric, nan, or infinite.
    ValueError
        If any executor references a component not bound in the context (extra).
        If any bound component has no executor (missing).
        If a mapping output key is empty or whitespace.
        If a ContributionRecordSet output contains a record for a different
        component_id than the executor's.
        If duplicate (component_id, name) pairs occur across all outputs.

    Notes
    -----
    This function MUST NOT execute real component classes, call contribute(...)
    on any component, assemble SystemState, inspect component_type to generate
    physics, call property backends or registries, or attach physical state to
    graph nodes.  All contribution logic is caller-supplied through explicit
    toy callbacks.
    """
    # --- validate binding_context ---
    if not isinstance(binding_context, NetworkBindingContext):
        raise TypeError(
            "execute_toy_component_contributions: binding_context must be a "
            f"NetworkBindingContext; got {type(binding_context).__name__!r}"
        )

    # --- validate unknown_values ---
    if not isinstance(unknown_values, Mapping):
        raise TypeError(
            "execute_toy_component_contributions: unknown_values must be a "
            f"Mapping; got {type(unknown_values).__name__!r}"
        )

    # --- validate metadata ---
    if metadata is not None and not isinstance(metadata, Mapping):
        raise TypeError(
            "execute_toy_component_contributions: metadata must be a "
            f"Mapping or None; got {type(metadata).__name__!r}"
        )

    # --- normalize executors to ToyComponentExecutorSet ---
    if isinstance(executors, ToyComponentExecutorSet):
        executor_set = executors
    else:
        try:
            executor_list = list(executors)  # type: ignore[arg-type]
        except TypeError as exc:
            raise TypeError(
                "execute_toy_component_contributions: executors must be a "
                "ToyComponentExecutorSet or iterable of ToyComponentExecutor; "
                f"got {type(executors).__name__!r}"
            ) from exc
        for i, e in enumerate(executor_list):
            if not isinstance(e, ToyComponentExecutor):
                raise TypeError(
                    f"execute_toy_component_contributions: executors[{i}] must "
                    f"be a ToyComponentExecutor; got {type(e).__name__!r}"
                )
        executor_set = ToyComponentExecutorSet(executors=tuple(executor_list))

    # --- validate exact coverage against binding_context ---
    bound_ids: frozenset[str] = frozenset(
        b.instance_id.value for b in binding_context.binding_set.bindings
    )
    exec_ids: frozenset[str] = frozenset(e.component_id.value for e in executor_set.executors)

    missing = bound_ids - exec_ids
    if missing:
        raise ValueError(
            "execute_toy_component_contributions: missing toy executors for "
            f"bound components: {sorted(missing)!r}"
        )

    extra = exec_ids - bound_ids
    if extra:
        raise ValueError(
            "execute_toy_component_contributions: toy executors reference "
            f"components not bound in binding_context: {sorted(extra)!r}"
        )

    # --- build shared context ---
    ctx = ToyComponentExecutionContext(
        binding_context=binding_context,
        unknown_values=unknown_values,
        metadata=metadata,
    )

    # --- execute each toy callback in executor order ---
    all_records: list[ContributionRecord] = []
    seen_keys: set[tuple[str, str]] = set()

    for executor in executor_set.executors:
        result = executor.callback(ctx)

        if isinstance(result, ContributionRecordSet):
            # All records must belong to this executor's component.
            for record in result.records:
                if record.component_id != executor.component_id:
                    raise ValueError(
                        f"execute_toy_component_contributions: toy executor for "
                        f"{executor.component_id.value!r} returned a "
                        f"ContributionRecordSet containing a record for a "
                        f"different component {record.component_id.value!r}"
                    )
                key = (record.component_id.value, record.name)
                if key in seen_keys:
                    raise ValueError(
                        "execute_toy_component_contributions: duplicate "
                        f"(component_id, name) pair "
                        f"({record.component_id.value!r}, {record.name!r})"
                    )
                seen_keys.add(key)
                all_records.append(record)

        elif isinstance(result, Mapping):
            for name, value in result.items():
                # Validate contribution name.
                if not isinstance(name, str):
                    raise TypeError(
                        f"execute_toy_component_contributions: toy executor for "
                        f"{executor.component_id.value!r} returned a mapping "
                        f"with a non-string key: {type(name).__name__!r}"
                    )
                if not name.strip():
                    raise ValueError(
                        f"execute_toy_component_contributions: toy executor for "
                        f"{executor.component_id.value!r} returned a mapping "
                        f"with an empty or whitespace-only key: {name!r}"
                    )
                # Validate contribution value.
                if isinstance(value, bool):
                    raise TypeError(
                        f"execute_toy_component_contributions: toy executor for "
                        f"{executor.component_id.value!r}: contribution "
                        f"{name!r} value must not be bool; got {value!r}"
                    )
                if not isinstance(value, (int, float)):
                    raise TypeError(
                        f"execute_toy_component_contributions: toy executor for "
                        f"{executor.component_id.value!r}: contribution "
                        f"{name!r} value must be a finite numeric (int or float); "
                        f"got {type(value).__name__!r}"
                    )
                if not math.isfinite(value):
                    raise ValueError(
                        f"execute_toy_component_contributions: toy executor for "
                        f"{executor.component_id.value!r}: contribution "
                        f"{name!r} value must be finite; got {value!r}"
                    )
                key = (executor.component_id.value, name)
                if key in seen_keys:
                    raise ValueError(
                        "execute_toy_component_contributions: duplicate "
                        f"contribution name {name!r} for component "
                        f"{executor.component_id.value!r}"
                    )
                seen_keys.add(key)
                all_records.append(
                    ContributionRecord(
                        component_id=executor.component_id,
                        name=name,
                        value=float(value),
                    )
                )

        else:
            raise TypeError(
                f"execute_toy_component_contributions: toy executor for "
                f"{executor.component_id.value!r} must return a "
                f"Mapping[str, float] or ContributionRecordSet; "
                f"got {type(result).__name__!r}"
            )

    return ContributionRecordSet(records=tuple(all_records))


# ---------------------------------------------------------------------------
# build_component_contribution_from_toy_execution
# ---------------------------------------------------------------------------


def build_component_contribution_from_toy_execution(
    component_id: object,
    binding_context: object,
    executors: object,
    residual_map: object,
    unknown_values: object,
    *,
    allowed_residual_names: frozenset[str] | set[str] | None = None,
    metadata: object = None,
) -> ComponentContribution:
    """Convenience wrapper: toy execution → Phase 14D mapping → ComponentContribution.

    Executes all toy component callbacks via execute_toy_component_contributions,
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
    executors
        ToyComponentExecutorSet or iterable of ToyComponentExecutor.
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
    record_set = execute_toy_component_contributions(
        binding_context,
        executors,
        unknown_values,
        metadata=metadata,
    )
    return map_contribution_records_to_component_contribution(
        component_id,
        record_set,
        residual_map,
        allowed_residual_names=allowed_residual_names,
    )
