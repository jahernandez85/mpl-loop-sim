"""Read-only unknown/state bridge layer — Block 15A.2.

Provides typed, validated, read-only view objects that let controlled bridge
providers access declared network unknown values through the existing
NetworkBindingContext and ComponentStateMap without assembling SystemState,
creating FluidState, or executing real production components.

What this module DOES
---------------------
- Defines ReadOnlyUnknownView: a frozen, validated read-only view of the full
  network unknown-value vector, scoped to the declared unknowns in a
  NetworkBindingContext.  Exposes values by raw unknown name; provides
  component-scoped and node-scoped sub-views.  Validates exact coverage,
  finiteness, and non-bool on construction.
- Defines ComponentUnknownView: read-only component-scoped view exposing only
  unknowns mapped to a specific ComponentInstanceId via ComponentStateMap.
- Defines NodeUnknownView: read-only node-scoped view exposing only unknowns
  mapped to a specific GraphNodeId via ComponentStateMap.
- Defines build_readonly_unknown_view: type-flexible factory accepting both
  NetworkUnknownValues and plain Mapping[str, float]; validates exact coverage
  and value validity; returns ReadOnlyUnknownView.

What this module DOES NOT DO
-----------------------------
- Does NOT assemble SystemState or create FluidState.
- Does NOT attach physical values to NetworkGraph, GraphNode, or
  ComponentInstance.
- Does NOT infer physical meaning from component_type.
- Does NOT infer automatic residuals from unknown names.
- Does NOT execute real production components.
- Does NOT import Pipe, PumpComponent, AccumulatorComponent,
  EvaporatorComponent, or CondenserComponent.
- Does NOT define or call any method named contribute.
- Does NOT call CoolProp, PropertyBackend, or any property engine.
- Does NOT call CorrelationRegistry or any registry.
- Does NOT implement solve(network) or NetworkGraph.solve().
- Does NOT import mpl_sim.properties, mpl_sim.components,
  mpl_sim.correlations, mpl_sim.calibration, or mpl_sim.hx_models.

Architecture boundaries (MUST NOT)
-----------------------------------
- MUST NOT import mpl_sim.solvers, mpl_sim.components, mpl_sim.properties,
  mpl_sim.calibration, mpl_sim.hx_models, or CoolProp.
- MUST NOT import or invoke CorrelationRegistry or HeatExchangerModelRegistry.
- MUST NOT expose a solve(network) method on any type in this module.
- MUST NOT define a method named contribute anywhere in this module.
- MUST NOT perform property lookup, real component execution, or any
  contribute(...) calls.
- MUST NOT infer physics from component_type.
- MUST NOT mutate caller-supplied binding context, unknown values, or metadata.

Block 15A.2 status
------------------
This checkpoint adds a read-only unknown-vector view bridge layer.  It makes
Block 15A.1 more useful by giving bridge providers a safe way to read
unknown-vector values by component/node mapping.  It does not enable real
production component execution.  Block 15B physical single-loop network
simulation and arbitrary-topology physical simulation remain deferred.

Exported names
--------------
ReadOnlyUnknownView
    — frozen validated read-only view of the full unknown vector
ComponentUnknownView
    — read-only component-scoped unknown view
NodeUnknownView
    — read-only node-scoped unknown view
build_readonly_unknown_view
    — type-flexible factory returning ReadOnlyUnknownView
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from mpl_sim.network.component_binding import NetworkBindingContext
from mpl_sim.network.graph import ComponentInstanceId, GraphNodeId
from mpl_sim.network.residual_evaluation import NetworkUnknownValues

# ---------------------------------------------------------------------------
# ComponentUnknownView
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ComponentUnknownView:
    """Read-only component-scoped view of declared unknown values.

    Exposes only the unknowns mapped to this component instance in
    ComponentStateMap.unknown_to_component.  Values are immutable.

    Fields
    ------
    component_id   : ComponentInstanceId for this view
    unknown_values : read-only mapping from unknown name to float value

    Methods
    -------
    value(name)  : return the scalar for a declared unknown name
    names()      : tuple of unknown names available in this view
    """

    component_id: ComponentInstanceId
    unknown_values: Mapping[str, float]

    def __post_init__(self) -> None:
        if not isinstance(self.component_id, ComponentInstanceId):
            raise TypeError(
                "ComponentUnknownView.component_id must be a ComponentInstanceId; "
                f"got {type(self.component_id).__name__!r}"
            )
        raw = self.unknown_values
        if not hasattr(raw, "items"):
            raise TypeError(
                "ComponentUnknownView.unknown_values must be a Mapping; "
                f"got {type(raw).__name__!r}"
            )
        object.__setattr__(self, "unknown_values", MappingProxyType(dict(raw)))

    def value(self, name: str) -> float:
        """Return the scalar value for the given declared unknown name.

        Raises
        ------
        TypeError  if name is not a string.
        ValueError if name is empty or whitespace-only.
        KeyError   if name is not mapped to this component.
        """
        if not isinstance(name, str):
            raise TypeError(
                "ComponentUnknownView.value: name must be a string; " f"got {type(name).__name__!r}"
            )
        if not name.strip():
            raise ValueError(f"ComponentUnknownView.value: name must be non-empty; got {name!r}")
        if name not in self.unknown_values:
            raise KeyError(
                f"ComponentUnknownView.value: unknown name {name!r} is not mapped "
                f"to component {self.component_id.value!r}; "
                f"available: {sorted(self.unknown_values)!r}"
            )
        return self.unknown_values[name]  # type: ignore[return-value]

    def names(self) -> tuple[str, ...]:
        """Unknown names available in this component view, in stable order."""
        return tuple(sorted(self.unknown_values))


# ---------------------------------------------------------------------------
# NodeUnknownView
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NodeUnknownView:
    """Read-only node-scoped view of declared unknown values.

    Exposes only the unknowns mapped to this graph node in
    ComponentStateMap.unknown_to_node.  Values are immutable.

    Fields
    ------
    node_id        : GraphNodeId for this view
    unknown_values : read-only mapping from unknown name to float value

    Methods
    -------
    value(name)  : return the scalar for a declared unknown name
    names()      : tuple of unknown names available in this view
    """

    node_id: GraphNodeId
    unknown_values: Mapping[str, float]

    def __post_init__(self) -> None:
        if not isinstance(self.node_id, GraphNodeId):
            raise TypeError(
                "NodeUnknownView.node_id must be a GraphNodeId; "
                f"got {type(self.node_id).__name__!r}"
            )
        raw = self.unknown_values
        if not hasattr(raw, "items"):
            raise TypeError(
                "NodeUnknownView.unknown_values must be a Mapping; " f"got {type(raw).__name__!r}"
            )
        object.__setattr__(self, "unknown_values", MappingProxyType(dict(raw)))

    def value(self, name: str) -> float:
        """Return the scalar value for the given declared unknown name.

        Raises
        ------
        TypeError  if name is not a string.
        ValueError if name is empty or whitespace-only.
        KeyError   if name is not mapped to this node.
        """
        if not isinstance(name, str):
            raise TypeError(
                "NodeUnknownView.value: name must be a string; " f"got {type(name).__name__!r}"
            )
        if not name.strip():
            raise ValueError(f"NodeUnknownView.value: name must be non-empty; got {name!r}")
        if name not in self.unknown_values:
            raise KeyError(
                f"NodeUnknownView.value: unknown name {name!r} is not mapped "
                f"to node {self.node_id.value!r}; "
                f"available: {sorted(self.unknown_values)!r}"
            )
        return self.unknown_values[name]  # type: ignore[return-value]

    def names(self) -> tuple[str, ...]:
        """Unknown names available in this node view, in stable order."""
        return tuple(sorted(self.unknown_values))


# ---------------------------------------------------------------------------
# ReadOnlyUnknownView
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReadOnlyUnknownView:
    """Frozen validated read-only view of the full network unknown-value vector.

    Validates that all assembly-declared unknowns are present, that no extra
    unknowns are present, and that all values are finite and non-bool.
    Provides raw access by unknown name, and component-scoped/node-scoped
    sub-views via the binding context's ComponentStateMap.

    Does NOT assemble SystemState, does NOT create FluidState, does NOT call
    CoolProp or PropertyBackend, does NOT infer physics from component_type,
    does NOT execute production components, does NOT define or call contribute.

    Fields
    ------
    binding_context : NetworkBindingContext (Phase 14B); immutable
    values          : read-only Mapping[str, float]; all declared unknowns

    Methods
    -------
    value(name)                 : return scalar for a declared unknown name
    for_component(component_id) : return ComponentUnknownView for a component
    for_node(node_id)           : return NodeUnknownView for a node
    """

    binding_context: NetworkBindingContext
    values: Mapping[str, float]

    def __post_init__(self) -> None:
        if not isinstance(self.binding_context, NetworkBindingContext):
            raise TypeError(
                "ReadOnlyUnknownView.binding_context must be a "
                "NetworkBindingContext; "
                f"got {type(self.binding_context).__name__!r}"
            )
        raw = self.values
        if not hasattr(raw, "items"):
            raise TypeError(
                "ReadOnlyUnknownView.values must be a Mapping; " f"got {type(raw).__name__!r}"
            )
        try:
            copied: dict[str, float] = dict(raw)
        except (TypeError, ValueError) as exc:
            raise TypeError(
                "ReadOnlyUnknownView.values could not be converted to a mapping"
            ) from exc
        # Validate key types and value types/finiteness before storing
        for name, val in copied.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError(
                    "ReadOnlyUnknownView.values: all keys must be non-empty "
                    f"strings; got {name!r}"
                )
            if isinstance(val, bool):
                raise ValueError(
                    f"ReadOnlyUnknownView.values: value for {name!r} must not "
                    f"be bool; got {val!r}"
                )
            if not isinstance(val, (int, float)):
                raise TypeError(
                    f"ReadOnlyUnknownView.values: value for {name!r} must be "
                    f"numeric; got {type(val).__name__!r}"
                )
            if not math.isfinite(float(val)):
                raise ValueError(
                    f"ReadOnlyUnknownView.values: value for {name!r} must be "
                    f"finite; got {val!r}"
                )
        # Store as immutable proxy before coverage checks
        object.__setattr__(self, "values", MappingProxyType(copied))
        proxy: Mapping[str, float] = self.values

        # Validate exact coverage against assembly declarations
        declared: frozenset[str] = frozenset(self.binding_context.assembly.unknowns.names())
        present: frozenset[str] = frozenset(proxy.keys())

        missing = declared - present
        if missing:
            raise ValueError(
                "ReadOnlyUnknownView: missing values for assembly-declared "
                f"unknowns: {sorted(missing)!r}"
            )

        extra = present - declared
        if extra:
            raise ValueError(
                "ReadOnlyUnknownView: extra unknown names not declared by "
                f"assembly: {sorted(extra)!r}"
            )

    def value(self, name: str) -> float:
        """Return the scalar value for the given declared unknown name.

        Raises
        ------
        TypeError  if name is not a string.
        ValueError if name is empty or whitespace-only.
        KeyError   if name is not declared in the assembly.
        """
        if not isinstance(name, str):
            raise TypeError(
                "ReadOnlyUnknownView.value: name must be a string; " f"got {type(name).__name__!r}"
            )
        if not name.strip():
            raise ValueError(f"ReadOnlyUnknownView.value: name must be non-empty; got {name!r}")
        if name not in self.values:
            raise KeyError(
                f"ReadOnlyUnknownView.value: unknown name {name!r} is not "
                "declared by the assembly"
            )
        return self.values[name]  # type: ignore[return-value]

    def for_component(self, component_id: object) -> ComponentUnknownView:
        """Return a read-only view of unknowns mapped to the given component.

        Raises
        ------
        TypeError  if component_id is not a ComponentInstanceId.
        KeyError   if component_id is not in the binding context.
        """
        if not isinstance(component_id, ComponentInstanceId):
            raise TypeError(
                "ReadOnlyUnknownView.for_component: component_id must be a "
                "ComponentInstanceId; "
                f"got {type(component_id).__name__!r}"
            )
        bound_ids = frozenset(
            b.instance_id.value for b in self.binding_context.binding_set.bindings
        )
        if component_id.value not in bound_ids:
            raise KeyError(
                "ReadOnlyUnknownView.for_component: component "
                f"{component_id.value!r} is not in the binding context"
            )
        comp_values: dict[str, float] = {
            name: self.values[name]  # type: ignore[assignment]
            for name, cid in self.binding_context.state_map.unknown_to_component.items()
            if cid == component_id
        }
        return ComponentUnknownView(
            component_id=component_id,
            unknown_values=MappingProxyType(comp_values),
        )

    def for_node(self, node_id: object) -> NodeUnknownView:
        """Return a read-only view of unknowns mapped to the given node.

        Raises
        ------
        TypeError  if node_id is not a GraphNodeId.
        KeyError   if node_id is not in the binding context's graph.
        """
        if not isinstance(node_id, GraphNodeId):
            raise TypeError(
                "ReadOnlyUnknownView.for_node: node_id must be a GraphNodeId; "
                f"got {type(node_id).__name__!r}"
            )
        graph_node_ids = frozenset(
            node.node_id.value for node in self.binding_context.graph.nodes()
        )
        if node_id.value not in graph_node_ids:
            raise KeyError(
                f"ReadOnlyUnknownView.for_node: node {node_id.value!r} is not "
                "in the binding context's graph"
            )
        node_values: dict[str, float] = {
            name: self.values[name]  # type: ignore[assignment]
            for name, nid in self.binding_context.state_map.unknown_to_node.items()
            if nid == node_id
        }
        return NodeUnknownView(
            node_id=node_id,
            unknown_values=MappingProxyType(node_values),
        )


# ---------------------------------------------------------------------------
# build_readonly_unknown_view
# ---------------------------------------------------------------------------


def build_readonly_unknown_view(
    binding_context: object,
    unknown_values: object,
) -> ReadOnlyUnknownView:
    """Build a validated ReadOnlyUnknownView from a binding context and values.

    Accepts both NetworkUnknownValues and plain Mapping[str, float] as the
    unknown-value source.  Validates types before delegating exact-coverage
    and value-validity checks to ReadOnlyUnknownView.

    Parameters
    ----------
    binding_context
        NetworkBindingContext from Phase 14B.  Provides the assembly
        declarations that define which unknown names are valid.
    unknown_values
        NetworkUnknownValues (Phase 13G) or plain Mapping[str, float].
        All assembly-declared unknowns must be present; no extra unknowns
        are allowed; all values must be finite and non-bool.

    Returns
    -------
    ReadOnlyUnknownView
        Frozen, validated read-only view of the unknown-value vector.

    Raises
    ------
    TypeError
        If binding_context is not a NetworkBindingContext.
        If unknown_values is not a NetworkUnknownValues or Mapping.
    ValueError
        If any assembly-declared unknown name is missing from the values.
        If any extra unknown name is not declared by the assembly.
        If any value is non-finite or bool.

    Notes
    -----
    This function MUST NOT execute component physics, call property backends,
    assemble SystemState, create FluidState, or attach state to graph nodes.
    It is a pure declaration validator and view factory.
    """
    if not isinstance(binding_context, NetworkBindingContext):
        raise TypeError(
            "build_readonly_unknown_view: binding_context must be a "
            "NetworkBindingContext; "
            f"got {type(binding_context).__name__!r}"
        )

    if isinstance(unknown_values, NetworkUnknownValues):
        raw: dict[str, float] = dict(unknown_values.values)
    elif isinstance(unknown_values, Mapping):
        raw = dict(unknown_values)
    else:
        raise TypeError(
            "build_readonly_unknown_view: unknown_values must be a "
            "NetworkUnknownValues or Mapping[str, float]; "
            f"got {type(unknown_values).__name__!r}"
        )

    return ReadOnlyUnknownView(
        binding_context=binding_context,  # type: ignore[arg-type]
        values=raw,
    )
