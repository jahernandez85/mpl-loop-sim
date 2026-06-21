"""Network graph foundation — Phase 13E.

Lightweight, physics-free topology representation for configurable two-phase
thermal-loop architectures.

A NetworkGraph holds named fluid connection points (GraphNode) and named
component instances (ComponentInstance) placed between those points.  It
describes topology only — it does not solve, evaluate physics, look up
properties, or assemble residuals.

Exported types:
    GraphNodeId         — identifier for a named fluid connection point
    ComponentInstanceId — identifier for a named component instance
    GraphNode           — a named fluid connection point (no physical values)
    ComponentInstance   — a named component placed between two graph nodes
    NetworkGraph        — collection of nodes and component instances

Architecture constraints enforced here:
    MUST NOT import mpl_sim.closed_loop.
    MUST NOT import mpl_sim.components, solvers, properties, correlations,
        calibration, or hx_models.
    MUST NOT import CoolProp or any property engine.
    MUST NOT store FluidState, mdot, pressure, enthalpy, or solver unknowns.
    MUST NOT implement solve(), residual assembly, or property lookup.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Identity types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GraphNodeId:
    """Immutable identifier for a named fluid connection point in the graph.

    A fluid connection point is a named junction where components meet.
    It carries no thermodynamic values.

    Raises
    ------
    ValueError
        If value is an empty string.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise TypeError("GraphNodeId.value must be a string")
        if not self.value.strip():
            raise ValueError("GraphNodeId.value must be a non-empty string")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ComponentInstanceId:
    """Immutable identifier for a named component instance in the graph.

    Raises
    ------
    ValueError
        If value is an empty string.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise TypeError("ComponentInstanceId.value must be a string")
        if not self.value.strip():
            raise ValueError("ComponentInstanceId.value must be a non-empty string")

    def __str__(self) -> str:
        return self.value


# ---------------------------------------------------------------------------
# Graph element types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GraphNode:
    """A named fluid connection point in the network graph.

    Represents a topology junction where component inlets and outlets meet.
    Carries no thermodynamic values (no P, h, mdot, FluidState, quality, …).
    """

    node_id: GraphNodeId

    def __post_init__(self) -> None:
        if not isinstance(self.node_id, GraphNodeId):
            raise TypeError("GraphNode.node_id must be a GraphNodeId")


@dataclass(frozen=True)
class ComponentInstance:
    """A named component placed between two fluid connection points.

    Describes the topological position of a component: which node it draws
    from (inlet_node) and which node it delivers to (outlet_node).

    Does NOT execute the component, store physical state, or reference any
    physics layer.

    Fields
    ------
    instance_id    : unique identifier for this component instance
    component_type : string naming the component kind (e.g. "evaporator")
    inlet_node     : upstream fluid connection point
    outlet_node    : downstream fluid connection point

    Raises
    ------
    ValueError
        If component_type is empty, or inlet_node equals outlet_node
        (self-loop components are not allowed).
    """

    instance_id: ComponentInstanceId
    component_type: str
    inlet_node: GraphNodeId
    outlet_node: GraphNodeId

    def __post_init__(self) -> None:
        if not isinstance(self.instance_id, ComponentInstanceId):
            raise TypeError("ComponentInstance.instance_id must be a ComponentInstanceId")
        if not isinstance(self.component_type, str):
            raise TypeError("ComponentInstance.component_type must be a string")
        if not self.component_type.strip():
            raise ValueError(
                f"ComponentInstance {self.instance_id.value!r}: "
                "component_type must be a non-empty string"
            )
        if not isinstance(self.inlet_node, GraphNodeId):
            raise TypeError("ComponentInstance.inlet_node must be a GraphNodeId")
        if not isinstance(self.outlet_node, GraphNodeId):
            raise TypeError("ComponentInstance.outlet_node must be a GraphNodeId")
        if self.inlet_node == self.outlet_node:
            raise ValueError(
                f"ComponentInstance {self.instance_id.value!r}: "
                f"inlet_node and outlet_node must differ "
                f"(got {self.inlet_node.value!r} for both)"
            )


# ---------------------------------------------------------------------------
# NetworkGraph
# ---------------------------------------------------------------------------


class NetworkGraph:
    """Immutable, physics-free network topology graph.

    Holds a collection of named fluid connection points (GraphNode) and
    component instances (ComponentInstance) placed between those points.
    Node and instance order is preserved from the constructor arguments.

    Validation performed at construction:
    - IDs are non-empty strings (enforced by identity types above).
    - No duplicate node ids.
    - No duplicate component instance ids.
    - Every component inlet/outlet node exists in the graph.
    - Self-loop components are rejected (enforced by ComponentInstance).

    This is topology description only.  It does not:
    - store FluidState, mdot, pressure, enthalpy, or any solver values
    - implement solve() or any residual assembly
    - call correlations, property backends, or CoolProp
    - import mpl_sim.closed_loop, components, solvers, or physics layers

    Parameters
    ----------
    nodes     : sequence of GraphNode (insertion order preserved)
    instances : sequence of ComponentInstance (insertion order preserved)

    Raises
    ------
    ValueError
        On duplicate node ids, duplicate instance ids, or component instance
        referencing an unknown node.
    TypeError
        If nodes or instances contain objects of the wrong type.
    """

    def __init__(
        self,
        nodes: Sequence[GraphNode],
        instances: Sequence[ComponentInstance],
    ) -> None:
        node_list = list(nodes)
        inst_list = list(instances)

        # Validate node types and uniqueness.
        seen_node_ids: dict[str, int] = {}
        for i, node in enumerate(node_list):
            if not isinstance(node, GraphNode):
                raise TypeError(f"nodes[{i}] must be a GraphNode; got {type(node).__name__!r}")
            nid = node.node_id.value
            if nid in seen_node_ids:
                raise ValueError(f"Duplicate node id: {nid!r}")
            seen_node_ids[nid] = i

        node_id_set: frozenset[str] = frozenset(seen_node_ids)

        # Validate instance types, uniqueness, and node references.
        seen_inst_ids: dict[str, int] = {}
        for i, inst in enumerate(inst_list):
            if not isinstance(inst, ComponentInstance):
                raise TypeError(
                    f"instances[{i}] must be a ComponentInstance; " f"got {type(inst).__name__!r}"
                )
            iid = inst.instance_id.value
            if iid in seen_inst_ids:
                raise ValueError(f"Duplicate component instance id: {iid!r}")
            seen_inst_ids[iid] = i

            if inst.inlet_node.value not in node_id_set:
                raise ValueError(
                    f"ComponentInstance {iid!r}: "
                    f"inlet_node {inst.inlet_node.value!r} not found in graph nodes"
                )
            if inst.outlet_node.value not in node_id_set:
                raise ValueError(
                    f"ComponentInstance {iid!r}: "
                    f"outlet_node {inst.outlet_node.value!r} not found in graph nodes"
                )

        # Store as immutable tuples preserving insertion order.
        self._nodes: tuple[GraphNode, ...] = tuple(node_list)
        self._instances: tuple[ComponentInstance, ...] = tuple(inst_list)
        self.__dict__["_initialized"] = True

    def __setattr__(self, name: str, value: object) -> None:
        if self.__dict__.get("_initialized"):
            raise AttributeError("NetworkGraph is immutable after construction")
        super().__setattr__(name, value)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def nodes(self) -> tuple[GraphNode, ...]:
        """Insertion-order tuple of all graph nodes."""
        return self._nodes

    def instances(self) -> tuple[ComponentInstance, ...]:
        """Insertion-order tuple of all component instances."""
        return self._instances

    def node_ids(self) -> tuple[GraphNodeId, ...]:
        """Node identifiers in insertion order."""
        return tuple(n.node_id for n in self._nodes)

    def instance_ids(self) -> tuple[ComponentInstanceId, ...]:
        """Component instance identifiers in insertion order."""
        return tuple(inst.instance_id for inst in self._instances)

    def summary(self) -> dict[str, object]:
        """Topology summary with node and component counts and names only.

        Contains no physical values, FluidState, mdot, pressure, or enthalpy.
        Safe to inspect without a solver or property backend.
        """
        return {
            "node_count": len(self._nodes),
            "node_ids": [n.node_id.value for n in self._nodes],
            "instance_count": len(self._instances),
            "instance_ids": [inst.instance_id.value for inst in self._instances],
            "component_types": [inst.component_type for inst in self._instances],
        }

    # ------------------------------------------------------------------
    # Structural validation
    # ------------------------------------------------------------------

    def validate_closed_single_loop(self) -> None:
        """Check that the graph forms a single closed loop.

        A closed single loop requires:
        1. At least one component instance.
        2. Every node has exactly one incoming component (as outlet_node)
           and exactly one outgoing component (as inlet_node).
        3. Following the successor chain from any node visits every node
           exactly once and returns to the start.

        This is a structural/topological check only — no physics.

        Raises
        ------
        ValueError
            If the graph does not form a valid closed single loop.
        """
        if not self._instances:
            raise ValueError(
                "Cannot validate closed single loop: " "graph has no component instances"
            )
        if not self._nodes:
            raise ValueError("Cannot validate closed single loop: graph has no nodes")

        n_nodes = len(self._nodes)

        # Count per-node in-degree and out-degree.
        in_degree: dict[str, int] = {n.node_id.value: 0 for n in self._nodes}
        out_degree: dict[str, int] = {n.node_id.value: 0 for n in self._nodes}

        for inst in self._instances:
            out_degree[inst.inlet_node.value] = out_degree.get(inst.inlet_node.value, 0) + 1
            in_degree[inst.outlet_node.value] = in_degree.get(inst.outlet_node.value, 0) + 1

        errors: list[str] = []
        for node in self._nodes:
            nid = node.node_id.value
            ind = in_degree[nid]
            outd = out_degree[nid]
            if ind != 1:
                errors.append(
                    f"Node {nid!r} has {ind} incoming component(s) "
                    f"(expected exactly 1 for a closed single loop)"
                )
            if outd != 1:
                errors.append(
                    f"Node {nid!r} has {outd} outgoing component(s) "
                    f"(expected exactly 1 for a closed single loop)"
                )

        if errors:
            raise ValueError("Not a closed single loop: " + "; ".join(errors))

        # Build successor map: inlet_node → outlet_node (via the one component).
        successor: dict[str, str] = {}
        for inst in self._instances:
            successor[inst.inlet_node.value] = inst.outlet_node.value

        # Follow the chain from the first node; verify all nodes visited.
        start = self._nodes[0].node_id.value
        current = start
        visited: list[str] = []
        for _ in range(n_nodes):
            visited.append(current)
            current = successor[current]

        if current != start:
            raise ValueError(
                f"Not a closed single loop: " f"chain does not return to start node {start!r}"
            )
        if len(set(visited)) != n_nodes:
            raise ValueError(
                f"Not a closed single loop: cycle visits {len(set(visited))} "
                f"distinct node(s) but graph has {n_nodes}"
            )

    def __repr__(self) -> str:
        return f"NetworkGraph(" f"nodes={len(self._nodes)}, " f"instances={len(self._instances)})"
