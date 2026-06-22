"""Minimal component contribution adapter foundation — Phase 14C.

Provides an explicit adapter layer that represents caller-supplied component
contribution callbacks and converts their outputs into Phase 14A physical
residual adapters.

What this module DOES
---------------------
- Defines ComponentContributionContext: immutable context passed to explicit
  contribution callbacks; carries the NetworkBindingContext, the current
  unknown-value mapping, and optional caller metadata. Does not assemble
  SystemState, compute properties, or execute real component classes.
- Defines ComponentContribution: frozen result from one contribution callback;
  contains residual-name → float pairs contributed by one component instance;
  keys are validated non-empty strings; values are validated finite non-bool
  numerics; mapping is defensively copied into an immutable MappingProxyType.
- Defines ComponentContributionAdapter: frozen binding of a ComponentInstanceId
  to a caller-supplied explicit contribution callback. This is NOT the existing
  component contribute(...) API. No real component class is executed.
- Defines ComponentContributionAdapterSet: validated ordered collection of
  ComponentContributionAdapter entries; rejects wrong types and duplicate IDs.
- Defines build_physical_adapters_from_contributions: converts explicit
  contribution adapters + NetworkBindingContext into a PhysicalResidualAdapterSet
  compatible with Phase 14A build_network_residual_evaluators and Phase 13G/13H.
  Generated adapter callbacks invoke all contribution callbacks at evaluation
  time, validate residual-name coverage, and return the requested residual value.

What this module DOES NOT DO
-----------------------------
This is a contribution-adapter foundation only.  It MUST NOT and DOES NOT:
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
- MUST NOT perform property lookup, component execution, or contribute(...) calls.
- MUST NOT mutate the caller-supplied binding context, adapters, or metadata.

Exported names
--------------
ComponentContributionContext            — immutable context passed to callbacks
ComponentContribution                   — frozen residual-value result from one callback
ComponentContributionAdapter            — frozen (instance_id, callback) binding
ComponentContributionAdapterSet         — validated ordered collection of adapters
build_physical_adapters_from_contributions — converts adapters into PhysicalResidualAdapterSet
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from mpl_sim.network.component_binding import NetworkBindingContext
from mpl_sim.network.graph import ComponentInstanceId
from mpl_sim.network.physical_adapters import (
    PhysicalResidualAdapter,
    PhysicalResidualAdapterSet,
    PhysicalResidualContext,
)

# ---------------------------------------------------------------------------
# ComponentContributionContext
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ComponentContributionContext:
    """Immutable context passed to ComponentContributionAdapter callbacks.

    Carries the binding context (graph + assembly + component binding
    declarations), the current unknown-value mapping, and optional caller
    metadata.  Does not assemble SystemState, compute properties, execute
    component physics, or call property backends.

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
                "ComponentContributionContext.binding_context must be a "
                f"NetworkBindingContext; got {type(self.binding_context).__name__!r}"
            )
        uv = self.unknown_values
        if not isinstance(uv, Mapping):
            raise TypeError(
                "ComponentContributionContext.unknown_values must be a Mapping; "
                f"got {type(uv).__name__!r}"
            )
        object.__setattr__(self, "unknown_values", MappingProxyType(dict(uv)))
        md = self.metadata
        if md is not None:
            if not isinstance(md, Mapping):
                raise TypeError(
                    "ComponentContributionContext.metadata must be a Mapping or None; "
                    f"got {type(md).__name__!r}"
                )
            object.__setattr__(self, "metadata", MappingProxyType(dict(md)))


# ---------------------------------------------------------------------------
# ComponentContribution
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ComponentContribution:
    """Immutable result of one component contribution callback.

    Contains the residual-name → float pairs contributed by one component
    instance for a given evaluation.  Keys must be non-empty, non-whitespace
    strings.  Values must be finite numeric (int or float, not bool).  The
    mapping is defensively copied into an immutable MappingProxyType.

    Fields
    ------
    residual_values : immutable mapping from residual name to float value

    Validation
    ----------
    - residual_values must be a Mapping.
    - Every key must be a non-empty, non-whitespace string.
    - Every value must be a finite numeric (int or float); bool is rejected.
    - Mapping is defensively copied; post-construction mutation of the source
      mapping does not affect this object.
    """

    residual_values: Mapping[str, float]

    def __post_init__(self) -> None:
        rv = self.residual_values
        if not isinstance(rv, Mapping):
            raise TypeError(
                "ComponentContribution.residual_values must be a Mapping; "
                f"got {type(rv).__name__!r}"
            )
        validated: dict[str, float] = {}
        for k, v in rv.items():
            if not isinstance(k, str):
                raise TypeError(
                    "ComponentContribution.residual_values keys must be strings; "
                    f"got key of type {type(k).__name__!r}"
                )
            if not k.strip():
                raise ValueError(
                    "ComponentContribution.residual_values keys must be non-empty, "
                    f"non-whitespace strings; got {k!r}"
                )
            if isinstance(v, bool):
                raise TypeError(
                    f"ComponentContribution.residual_values[{k!r}] must not be bool; " f"got {v!r}"
                )
            if not isinstance(v, (int, float)):
                raise TypeError(
                    f"ComponentContribution.residual_values[{k!r}] must be a finite "
                    f"numeric (int or float); got {type(v).__name__!r}"
                )
            if not math.isfinite(v):
                raise ValueError(
                    f"ComponentContribution.residual_values[{k!r}] must be finite; " f"got {v!r}"
                )
            validated[k] = float(v)
        object.__setattr__(self, "residual_values", MappingProxyType(validated))


# ---------------------------------------------------------------------------
# ComponentContributionAdapter
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ComponentContributionAdapter:
    """Frozen binding of a component instance ID to an explicit contribution callback.

    The callback receives a ComponentContributionContext and returns a
    ComponentContribution containing this component's residual contributions.

    This is NOT the existing component contribute(...) API.  The callback is
    caller-supplied and explicit.  No real component class is executed.

    Callback signature:
        callback(context: ComponentContributionContext) -> ComponentContribution

    Fields
    ------
    instance_id : ComponentInstanceId identifying the component in the graph
    callback    : callable receiving ComponentContributionContext and returning
                  ComponentContribution

    Validation
    ----------
    - instance_id must be a ComponentInstanceId.
    - callback must be callable.
    """

    instance_id: ComponentInstanceId
    callback: Callable[[ComponentContributionContext], ComponentContribution]

    def __post_init__(self) -> None:
        if not isinstance(self.instance_id, ComponentInstanceId):
            raise TypeError(
                "ComponentContributionAdapter.instance_id must be a "
                f"ComponentInstanceId; got {type(self.instance_id).__name__!r}"
            )
        if not callable(self.callback):
            raise TypeError(
                "ComponentContributionAdapter.callback must be callable; "
                f"got {type(self.callback).__name__!r}"
            )


# ---------------------------------------------------------------------------
# ComponentContributionAdapterSet
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ComponentContributionAdapterSet:
    """Validated, ordered collection of ComponentContributionAdapter entries.

    Preserves insertion order.  Rejects wrong entry types and duplicate
    component instance IDs.

    Fields
    ------
    adapters : tuple[ComponentContributionAdapter, ...]
        Ordered adapters, one per component instance.

    Validation
    ----------
    - Every entry must be a ComponentContributionAdapter.
    - No two adapters may share a component instance ID.
    """

    adapters: tuple[ComponentContributionAdapter, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.adapters, tuple):
            object.__setattr__(self, "adapters", tuple(self.adapters))
        for i, a in enumerate(self.adapters):
            if not isinstance(a, ComponentContributionAdapter):
                raise TypeError(
                    f"ComponentContributionAdapterSet.adapters[{i}] must be a "
                    f"ComponentContributionAdapter; got {type(a).__name__!r}"
                )
        seen: set[str] = set()
        for a in self.adapters:
            iid = a.instance_id.value
            if iid in seen:
                raise ValueError(
                    "ComponentContributionAdapterSet: duplicate instance_id "
                    f"{a.instance_id.value!r}"
                )
            seen.add(iid)


# ---------------------------------------------------------------------------
# build_physical_adapters_from_contributions
# ---------------------------------------------------------------------------


def build_physical_adapters_from_contributions(
    binding_context: object,
    contribution_adapters: object,
    *,
    metadata: object = None,
) -> PhysicalResidualAdapterSet:
    """Convert explicit component contribution adapters into a PhysicalResidualAdapterSet.

    Validates that the contribution adapters exactly cover the components bound
    in the NetworkBindingContext (no missing, no extra).  Generates one
    PhysicalResidualAdapter per residual declared in the assembly, in assembly
    declaration order.

    Generated adapter callbacks (at evaluation time):
      1. receive a PhysicalResidualContext from Phase 14A;
      2. build a ComponentContributionContext from the binding context and the
         current unknown values;
      3. call all explicit contribution callbacks in the adapter set;
      4. validate that all returned residual names are declared by the assembly
         (undeclared names cause a ValueError);
      5. return the requested residual value, or raise if no contribution
         callback provided it.

    Parameters
    ----------
    binding_context
        NetworkBindingContext from Phase 14B.  Provides graph, assembly,
        binding set, and state map.  Must not be mutated.
    contribution_adapters
        ComponentContributionAdapterSet or iterable of
        ComponentContributionAdapter.  Exact coverage is required: missing and
        extra adapters (relative to binding_context.binding_set) are rejected.
    metadata
        Optional Mapping[str, object] passed to each ComponentContributionContext
        at evaluation time.  Defensively copied once at call time.  None by
        default.

    Returns
    -------
    PhysicalResidualAdapterSet
        One PhysicalResidualAdapter per assembly residual declaration, in
        assembly declaration order.  Each adapter's callback calls all
        contribution callbacks when invoked.

    Raises
    ------
    TypeError
        If binding_context is not a NetworkBindingContext.
        If metadata is not a Mapping or None.
        If any contribution adapter entry is not a ComponentContributionAdapter.
    ValueError
        If any bound component instance has no contribution adapter (missing).
        If any contribution adapter references a component not bound in the
        binding context (extra/unbound).
        At evaluation time: if any contribution callback returns a residual name
        not declared by the assembly (undeclared).
        At evaluation time: if a required residual value is not provided by any
        contribution callback (missing residual).
        At evaluation time: if a residual name is provided by more than one
        contribution callback (duplicate).
    TypeError (at evaluation time)
        If any contribution callback does not return a ComponentContribution.

    Notes
    -----
    This function MUST NOT execute real component classes, call contribute(...)
    on any component, assemble SystemState, inspect component_type to generate
    physics, call property backends or registries, or attach physical state to
    graph nodes.  All contribution logic is caller-supplied through explicit
    callbacks.
    """
    # --- validate binding_context ---
    if not isinstance(binding_context, NetworkBindingContext):
        raise TypeError(
            "build_physical_adapters_from_contributions: binding_context must be a "
            f"NetworkBindingContext; got {type(binding_context).__name__!r}"
        )

    # --- validate and freeze metadata ---
    if metadata is not None and not isinstance(metadata, Mapping):
        raise TypeError(
            "build_physical_adapters_from_contributions: metadata must be a "
            f"Mapping or None; got {type(metadata).__name__!r}"
        )
    metadata_proxy: MappingProxyType | None = (
        MappingProxyType(dict(metadata)) if metadata is not None else None  # type: ignore[arg-type]
    )

    # --- normalize contribution_adapters ---
    if isinstance(contribution_adapters, ComponentContributionAdapterSet):
        adapter_set = contribution_adapters
    else:
        try:
            adapter_list = list(contribution_adapters)  # type: ignore[arg-type]
        except TypeError as exc:
            raise TypeError(
                "build_physical_adapters_from_contributions: contribution_adapters "
                "must be a ComponentContributionAdapterSet or iterable of "
                "ComponentContributionAdapter; "
                f"got {type(contribution_adapters).__name__!r}"
            ) from exc
        for i, a in enumerate(adapter_list):
            if not isinstance(a, ComponentContributionAdapter):
                raise TypeError(
                    f"build_physical_adapters_from_contributions: "
                    f"contribution_adapters[{i}] must be a "
                    f"ComponentContributionAdapter; got {type(a).__name__!r}"
                )
        adapter_set = ComponentContributionAdapterSet(adapters=tuple(adapter_list))

    # --- validate exact coverage against binding_context ---
    bound_ids: frozenset[str] = frozenset(
        b.instance_id.value for b in binding_context.binding_set.bindings
    )
    contrib_ids: frozenset[str] = frozenset(a.instance_id.value for a in adapter_set.adapters)

    missing = bound_ids - contrib_ids
    if missing:
        raise ValueError(
            "build_physical_adapters_from_contributions: missing contribution "
            f"adapters for bound components: {sorted(missing)!r}"
        )

    extra = contrib_ids - bound_ids
    if extra:
        raise ValueError(
            "build_physical_adapters_from_contributions: contribution adapters "
            "reference components not bound in binding_context: "
            f"{sorted(extra)!r}"
        )

    # --- prepare for adapter generation ---
    assembly = binding_context.assembly
    assembly_residual_names: frozenset[str] = frozenset(assembly.residuals.names())
    ordered_adapters: tuple[ComponentContributionAdapter, ...] = adapter_set.adapters

    # --- generate one PhysicalResidualAdapter per assembly residual in order ---
    physical_adapters: list[PhysicalResidualAdapter] = []
    for res_decl in assembly.residuals.residuals:
        physical_adapters.append(
            PhysicalResidualAdapter(
                residual_name=res_decl.name,
                callback=_make_contribution_callback(
                    residual_name=res_decl.name,
                    binding_context=binding_context,
                    contribution_adapters=ordered_adapters,
                    assembly_residual_names=assembly_residual_names,
                    metadata_proxy=metadata_proxy,
                ),
            )
        )

    return PhysicalResidualAdapterSet(adapters=tuple(physical_adapters))


def _make_contribution_callback(
    residual_name: str,
    binding_context: NetworkBindingContext,
    contribution_adapters: tuple[ComponentContributionAdapter, ...],
    assembly_residual_names: frozenset[str],
    metadata_proxy: MappingProxyType | None,
) -> Callable[[PhysicalResidualContext], float]:
    """Return a PhysicalResidualAdapter callback that drives contribution evaluation."""

    def callback(physical_ctx: PhysicalResidualContext) -> float:
        ctx = ComponentContributionContext(
            binding_context=binding_context,
            unknown_values=physical_ctx.unknown_values,
            metadata=metadata_proxy,
        )
        merged: dict[str, float] = {}
        for contrib_adapter in contribution_adapters:
            result = contrib_adapter.callback(ctx)
            if not isinstance(result, ComponentContribution):
                raise TypeError(
                    f"Contribution callback for component "
                    f"{contrib_adapter.instance_id.value!r} must return a "
                    f"ComponentContribution; got {type(result).__name__!r}"
                )
            for name, value in result.residual_values.items():
                if name not in assembly_residual_names:
                    raise ValueError(
                        f"Contribution callback for component "
                        f"{contrib_adapter.instance_id.value!r} returned undeclared "
                        f"residual name {name!r}; declared names: "
                        f"{sorted(assembly_residual_names)!r}"
                    )
                if name in merged:
                    raise ValueError(
                        f"Residual name {name!r} provided by multiple contribution " f"callbacks"
                    )
                merged[name] = value
        if residual_name not in merged:
            raise ValueError(
                f"Required residual {residual_name!r} was not provided by any "
                f"contribution callback"
            )
        return merged[residual_name]

    return callback
