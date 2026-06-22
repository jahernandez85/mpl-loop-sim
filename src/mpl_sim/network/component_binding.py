"""Component binding and state-vector mapping foundation — Phase 14B.

Provides an explicit declaration layer that links NetworkGraph component
instances to caller-supplied binding labels, and maps residual/unknown names
used by the Phase 14A physical residual adapter context to component instances
and graph nodes.

What this module DOES
---------------------
- Defines ComponentBinding: immutable (instance_id, binding_name) declaration
  linking a ComponentInstanceId to a caller-supplied string label. Optional
  opaque metadata is defensively copied.
- Defines ComponentBindingSet: validated, ordered immutable collection of
  ComponentBinding entries. Rejects wrong types and duplicate instance IDs.
- Defines ComponentStateMap: explicit mapping from residual/unknown string keys
  to ComponentInstanceId or GraphNodeId values. Mappings are immutable and
  defensively copied. No numerical values are stored.
- Defines NetworkBindingContext: immutable context combining NetworkGraph,
  NetworkResidualAssembly, ComponentBindingSet, ComponentStateMap, and
  optional metadata. Does not execute anything.
- Defines build_binding_context: validates inputs and returns a
  NetworkBindingContext ready for use by future adapter construction.

What this module DOES NOT DO
-----------------------------
This is a binding and mapping declaration layer only.  It MUST NOT and
DOES NOT:
- Execute component instances or call any component method.
- Call the frozen component contribution method (contribute(...)).
- Look up fluid properties or call thermodynamic backends.
- Call CoolProp, PropertyBackend, or any property engine.
- Call CorrelationRegistry, HeatExchangerModelRegistry, or any registry.
- Attach physical state (FluidState, mdot, pressure, enthalpy) to graph nodes.
- Store numerical unknown values or solver state.
- Inspect component_type to generate physics or infer residual form.
- Implement solve(network) or any automatic residual construction.
- Import mpl_sim.solvers, mpl_sim.components, mpl_sim.properties,
  mpl_sim.correlations, mpl_sim.calibration, or mpl_sim.hx_models.

Architecture boundaries (MUST NOT)
-----------------------------------
- MUST NOT import mpl_sim.solvers, mpl_sim.components, mpl_sim.properties,
  mpl_sim.calibration, mpl_sim.hx_models, or CoolProp.
- MUST NOT import or invoke CorrelationRegistry or HeatExchangerModelRegistry.
- MUST NOT expose a solve(network) method on any type in this module.
- MUST NOT perform property lookup or component execution.
- MUST NOT mutate the caller-supplied graph, assembly, bindings, maps, or
  metadata.

Exported names
--------------
ComponentBinding         — frozen (instance_id, binding_name) declaration
ComponentBindingSet      — validated ordered collection of ComponentBinding
ComponentStateMap        — explicit unknown/residual name → ID mapping
NetworkBindingContext    — immutable context combining graph, assembly,
                           bindings, and state map
build_binding_context    — builder/validator returning NetworkBindingContext
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from mpl_sim.network.graph import ComponentInstanceId, GraphNodeId, NetworkGraph
from mpl_sim.network.residual_assembly import NetworkResidualAssembly

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_str_key(key: object, field_name: str) -> str:
    if not isinstance(key, str):
        raise TypeError(
            f"{field_name} keys must be non-empty strings; "
            f"got key of type {type(key).__name__!r}"
        )
    if not key.strip():
        raise ValueError(
            f"{field_name} keys must be non-empty, non-whitespace strings; got {key!r}"
        )
    return key


def _freeze_str_to_component_map(m: object, field_name: str) -> MappingProxyType:
    if not isinstance(m, Mapping):
        raise TypeError(f"{field_name} must be a Mapping; got {type(m).__name__!r}")
    result: dict[str, ComponentInstanceId] = {}
    for k, v in m.items():
        _validate_str_key(k, field_name)
        if not isinstance(v, ComponentInstanceId):
            raise TypeError(
                f"{field_name} values must be ComponentInstanceId; "
                f"got {type(v).__name__!r} for key {k!r}"
            )
        result[k] = v
    return MappingProxyType(result)


def _freeze_str_to_node_map(m: object, field_name: str) -> MappingProxyType:
    if not isinstance(m, Mapping):
        raise TypeError(f"{field_name} must be a Mapping; got {type(m).__name__!r}")
    result: dict[str, GraphNodeId] = {}
    for k, v in m.items():
        _validate_str_key(k, field_name)
        if not isinstance(v, GraphNodeId):
            raise TypeError(
                f"{field_name} values must be GraphNodeId; "
                f"got {type(v).__name__!r} for key {k!r}"
            )
        result[k] = v
    return MappingProxyType(result)


# ---------------------------------------------------------------------------
# ComponentBinding
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ComponentBinding:
    """Immutable declaration linking a component instance to a binding label.

    A ComponentBinding is a pure declaration — it carries an instance ID and
    a caller-supplied binding name only.  It does not execute the component,
    call any component method, look up properties, or store physical state.

    Fields
    ------
    instance_id  : identifies the component instance in the graph
    binding_name : non-empty string label supplied by the caller
    metadata     : optional caller-supplied metadata; defensively copied and
                   immutable after construction; None if not supplied

    Raises
    ------
    TypeError
        If instance_id is not a ComponentInstanceId.
        If binding_name is not a string.
        If metadata is not a Mapping (when supplied).
    ValueError
        If binding_name is empty or whitespace-only.
    """

    instance_id: ComponentInstanceId
    binding_name: str
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.instance_id, ComponentInstanceId):
            raise TypeError(
                "ComponentBinding.instance_id must be a ComponentInstanceId; "
                f"got {type(self.instance_id).__name__!r}"
            )
        if not isinstance(self.binding_name, str):
            raise TypeError(
                "ComponentBinding.binding_name must be a string; "
                f"got {type(self.binding_name).__name__!r}"
            )
        if not self.binding_name.strip():
            raise ValueError(
                "ComponentBinding.binding_name must be a non-empty, non-whitespace "
                f"string; got {self.binding_name!r}"
            )
        md = self.metadata
        if md is not None:
            if not isinstance(md, Mapping):
                raise TypeError(
                    "ComponentBinding.metadata must be a Mapping or None; "
                    f"got {type(md).__name__!r}"
                )
            object.__setattr__(self, "metadata", MappingProxyType(dict(md)))


# ---------------------------------------------------------------------------
# ComponentBindingSet
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ComponentBindingSet:
    """Validated, ordered, immutable collection of ComponentBinding entries.

    Preserves insertion order.  Rejects wrong entry types and duplicate
    component instance IDs.

    Fields
    ------
    bindings : tuple[ComponentBinding, ...]
        Ordered bindings, one per component instance.

    Methods
    -------
    instance_ids() : tuple[ComponentInstanceId, ...]
        Component instance IDs in insertion order.
    by_instance_id(instance_id) : ComponentBinding | None
        First binding matching the given instance ID, or None.

    Raises
    ------
    TypeError
        If any entry is not a ComponentBinding.
    ValueError
        If any two entries share the same instance_id.
    """

    bindings: tuple[ComponentBinding, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.bindings, tuple):
            object.__setattr__(self, "bindings", tuple(self.bindings))
        for i, b in enumerate(self.bindings):
            if not isinstance(b, ComponentBinding):
                raise TypeError(
                    f"ComponentBindingSet.bindings[{i}] must be a ComponentBinding; "
                    f"got {type(b).__name__!r}"
                )
        seen: set[str] = set()
        for b in self.bindings:
            iid = b.instance_id.value
            if iid in seen:
                raise ValueError(
                    "ComponentBindingSet: duplicate instance_id " f"{b.instance_id.value!r}"
                )
            seen.add(iid)

    def instance_ids(self) -> tuple[ComponentInstanceId, ...]:
        """Component instance IDs in insertion order."""
        return tuple(b.instance_id for b in self.bindings)

    def by_instance_id(self, instance_id: ComponentInstanceId) -> ComponentBinding | None:
        """Return the binding for the given instance ID, or None."""
        for b in self.bindings:
            if b.instance_id == instance_id:
                return b
        return None


# ---------------------------------------------------------------------------
# ComponentStateMap
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ComponentStateMap:
    """Explicit mapping from unknown/residual names to component/node IDs.

    Maps names used in residual adapters (e.g. ``"mdot:evap"``) to the
    ComponentInstanceId or GraphNodeId they refer to in the network graph.

    All mappings are declaration-only.  No numerical values, no FluidState,
    no physical solver state is stored here.  Mappings are immutable and
    defensively copied at construction.

    Fields
    ------
    unknown_to_component : Mapping[str, ComponentInstanceId]
        Maps unknown names to component instance IDs.  Default: empty.
    unknown_to_node : Mapping[str, GraphNodeId]
        Maps unknown names to graph node IDs.  Default: empty.
    residual_to_component : Mapping[str, ComponentInstanceId]
        Maps residual names to component instance IDs.  Default: empty.
    residual_to_node : Mapping[str, GraphNodeId]
        Maps residual names to graph node IDs.  Default: empty.

    Validation
    ----------
    - All mapping keys must be non-empty, non-whitespace strings.
    - ComponentInstanceId values must be ComponentInstanceId instances.
    - GraphNodeId values must be GraphNodeId instances.
    - Mappings are defensively copied; post-construction mutation of the source
      mapping does not affect this object.

    Does not store numerical values, FluidState, or physical state.
    """

    unknown_to_component: Mapping[str, ComponentInstanceId] = field(default_factory=dict)
    unknown_to_node: Mapping[str, GraphNodeId] = field(default_factory=dict)
    residual_to_component: Mapping[str, ComponentInstanceId] = field(default_factory=dict)
    residual_to_node: Mapping[str, GraphNodeId] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unknown_to_component",
            _freeze_str_to_component_map(
                self.unknown_to_component, "ComponentStateMap.unknown_to_component"
            ),
        )
        object.__setattr__(
            self,
            "unknown_to_node",
            _freeze_str_to_node_map(self.unknown_to_node, "ComponentStateMap.unknown_to_node"),
        )
        object.__setattr__(
            self,
            "residual_to_component",
            _freeze_str_to_component_map(
                self.residual_to_component,
                "ComponentStateMap.residual_to_component",
            ),
        )
        object.__setattr__(
            self,
            "residual_to_node",
            _freeze_str_to_node_map(self.residual_to_node, "ComponentStateMap.residual_to_node"),
        )


# ---------------------------------------------------------------------------
# NetworkBindingContext
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NetworkBindingContext:
    """Immutable context combining graph, assembly, bindings, and state map.

    Carries the complete binding and mapping declaration for future physical
    adapter construction.  Does not execute anything, does not store
    numerical values, and does not call property backends.

    Fields
    ------
    graph       : NetworkGraph topology
    assembly    : NetworkResidualAssembly (Phase 13F declarations)
    binding_set : ComponentBindingSet (component→label declarations)
    state_map   : ComponentStateMap (name→ID declarations)
    metadata    : optional caller-supplied metadata; immutable after construction

    Raises
    ------
    TypeError
        If any field has the wrong type.
        If metadata is not a Mapping (when supplied).
    """

    graph: NetworkGraph
    assembly: NetworkResidualAssembly
    binding_set: ComponentBindingSet
    state_map: ComponentStateMap
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.graph, NetworkGraph):
            raise TypeError(
                "NetworkBindingContext.graph must be a NetworkGraph; "
                f"got {type(self.graph).__name__!r}"
            )
        if not isinstance(self.assembly, NetworkResidualAssembly):
            raise TypeError(
                "NetworkBindingContext.assembly must be a NetworkResidualAssembly; "
                f"got {type(self.assembly).__name__!r}"
            )
        if not isinstance(self.binding_set, ComponentBindingSet):
            raise TypeError(
                "NetworkBindingContext.binding_set must be a ComponentBindingSet; "
                f"got {type(self.binding_set).__name__!r}"
            )
        if not isinstance(self.state_map, ComponentStateMap):
            raise TypeError(
                "NetworkBindingContext.state_map must be a ComponentStateMap; "
                f"got {type(self.state_map).__name__!r}"
            )
        md = self.metadata
        if md is not None:
            if not isinstance(md, Mapping):
                raise TypeError(
                    "NetworkBindingContext.metadata must be a Mapping or None; "
                    f"got {type(md).__name__!r}"
                )
            object.__setattr__(self, "metadata", MappingProxyType(dict(md)))

    def __repr__(self) -> str:
        n_unknowns = len(self.state_map.unknown_to_component) + len(self.state_map.unknown_to_node)
        n_residuals = len(self.state_map.residual_to_component) + len(
            self.state_map.residual_to_node
        )
        return (
            f"NetworkBindingContext("
            f"graph={self.graph!r}, "
            f"bindings={len(self.binding_set.bindings)}, "
            f"unknowns_mapped={n_unknowns}, "
            f"residuals_mapped={n_residuals})"
        )


# ---------------------------------------------------------------------------
# build_binding_context
# ---------------------------------------------------------------------------


def build_binding_context(
    graph: object,
    assembly: object,
    bindings: object,
    state_map: object,
    *,
    metadata: object = None,
) -> NetworkBindingContext:
    """Build and validate a NetworkBindingContext from explicit declarations.

    Validates that the supplied bindings cover the graph component instances
    exactly, that state-map references resolve to IDs present in the graph,
    and that every mapped name is declared by the supplied assembly. Returns
    an immutable NetworkBindingContext for future adapter construction.

    Parameters
    ----------
    graph
        Must be a NetworkGraph.
    assembly
        Must be a NetworkResidualAssembly (Phase 13F).
    bindings
        ComponentBindingSet or iterable of ComponentBinding.  One binding is
        expected per component instance in the graph (exact coverage).
    state_map
        ComponentStateMap mapping unknown/residual names to graph IDs.
        All referenced component IDs and node IDs must exist in the graph.
    metadata
        Optional Mapping[str, object] stored immutably on the context.

    Returns
    -------
    NetworkBindingContext
        Immutable context ready for future Phase 14C adapter construction.

    Raises
    ------
    TypeError
        If graph is not a NetworkGraph.
        If assembly is not a NetworkResidualAssembly.
        If any binding entry is not a ComponentBinding.
        If state_map is not a ComponentStateMap.
        If metadata is not a Mapping or None.
    ValueError
        If the binding set contains duplicate component instance IDs.
        If a binding refers to a component instance not in the graph.
        If the graph has component instances with no corresponding binding.
        If an unknown or residual map key is not declared by the assembly.
        If a state-map component ID is not in the graph.
        If a state-map node ID is not in the graph.

    Notes
    -----
    This function MUST NOT execute component physics, call property backends
    or registries, inspect component_type to generate physics, or attach
    physical state to graph nodes.  It is a pure declaration validator.
    """
    # --- validate graph ---
    if not isinstance(graph, NetworkGraph):
        raise TypeError(
            "build_binding_context: graph must be a NetworkGraph; " f"got {type(graph).__name__!r}"
        )

    # --- validate assembly ---
    if not isinstance(assembly, NetworkResidualAssembly):
        raise TypeError(
            "build_binding_context: assembly must be a NetworkResidualAssembly; "
            f"got {type(assembly).__name__!r}"
        )

    # --- normalize bindings to ComponentBindingSet ---
    if isinstance(bindings, ComponentBindingSet):
        binding_set = bindings
    else:
        try:
            binding_list = list(bindings)  # type: ignore[arg-type]
        except TypeError as exc:
            raise TypeError(
                "build_binding_context: bindings must be a ComponentBindingSet or "
                "iterable of ComponentBinding; "
                f"got {type(bindings).__name__!r}"
            ) from exc
        for i, b in enumerate(binding_list):
            if not isinstance(b, ComponentBinding):
                raise TypeError(
                    f"build_binding_context: bindings[{i}] must be a ComponentBinding; "
                    f"got {type(b).__name__!r}"
                )
        binding_set = ComponentBindingSet(bindings=tuple(binding_list))

    # --- validate state_map ---
    if not isinstance(state_map, ComponentStateMap):
        raise TypeError(
            "build_binding_context: state_map must be a ComponentStateMap; "
            f"got {type(state_map).__name__!r}"
        )

    # --- validate metadata ---
    if metadata is not None and not isinstance(metadata, Mapping):
        raise TypeError(
            "build_binding_context: metadata must be a Mapping or None; "
            f"got {type(metadata).__name__!r}"
        )

    # --- build reference sets from graph ---
    graph_instance_ids: frozenset[str] = frozenset(
        inst.instance_id.value for inst in graph.instances()
    )
    graph_node_ids: frozenset[str] = frozenset(node.node_id.value for node in graph.nodes())
    assembly_unknown_names = frozenset(assembly.unknowns.names())
    assembly_residual_names = frozenset(assembly.residuals.names())

    # --- validate binding coverage ---
    bound_ids: set[str] = {b.instance_id.value for b in binding_set.bindings}

    extra = bound_ids - graph_instance_ids
    if extra:
        raise ValueError(
            "build_binding_context: bindings refer to component instance IDs "
            f"not in graph: {sorted(extra)!r}"
        )

    missing = graph_instance_ids - bound_ids
    if missing:
        raise ValueError(
            "build_binding_context: graph component instances have no binding: "
            f"{sorted(missing)!r}"
        )

    # --- validate state_map names against assembly declarations ---
    mapped_unknown_names = frozenset(state_map.unknown_to_component) | frozenset(
        state_map.unknown_to_node
    )
    undeclared_unknowns = mapped_unknown_names - assembly_unknown_names
    if undeclared_unknowns:
        raise ValueError(
            "build_binding_context: state_map unknown names are not declared "
            f"by assembly: {sorted(undeclared_unknowns)!r}"
        )

    mapped_residual_names = frozenset(state_map.residual_to_component) | frozenset(
        state_map.residual_to_node
    )
    undeclared_residuals = mapped_residual_names - assembly_residual_names
    if undeclared_residuals:
        raise ValueError(
            "build_binding_context: state_map residual names are not declared "
            f"by assembly: {sorted(undeclared_residuals)!r}"
        )

    # --- validate state_map component references ---
    for key, cid in state_map.unknown_to_component.items():
        if cid.value not in graph_instance_ids:
            raise ValueError(
                "build_binding_context: state_map.unknown_to_component "
                f"key {key!r} references component instance {cid.value!r} "
                "not in graph"
            )

    for key, cid in state_map.residual_to_component.items():
        if cid.value not in graph_instance_ids:
            raise ValueError(
                "build_binding_context: state_map.residual_to_component "
                f"key {key!r} references component instance {cid.value!r} "
                "not in graph"
            )

    # --- validate state_map node references ---
    for key, nid in state_map.unknown_to_node.items():
        if nid.value not in graph_node_ids:
            raise ValueError(
                "build_binding_context: state_map.unknown_to_node "
                f"key {key!r} references node {nid.value!r} not in graph"
            )

    for key, nid in state_map.residual_to_node.items():
        if nid.value not in graph_node_ids:
            raise ValueError(
                "build_binding_context: state_map.residual_to_node "
                f"key {key!r} references node {nid.value!r} not in graph"
            )

    return NetworkBindingContext(
        graph=graph,
        assembly=assembly,
        binding_set=binding_set,
        state_map=state_map,
        metadata=metadata,  # type: ignore[arg-type]
    )
