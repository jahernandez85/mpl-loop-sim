"""Parallel branch topology scenario declaration — Block 15C.2.

Provides explicit topology, unknown, and residual declarations for a minimal
fixed two-branch parallel network:

    accumulator -> pump -> [branch_a / branch_b] -> [merge_a / merge_b] -> condenser -> accumulator

where:
    n_pump_out  is the split point (both branches draw from this node)
    n_merge_out is the merge point (both merge elements deliver to this node)

This is a declaration-only module.  It does not execute production component
physics, does not assemble SystemState, does not create FluidState, does not
call CoolProp, PropertyBackend, correlations, or HX models.

Block 15C-B is responsible for parallel branch residual assembly and physical
flow split evaluation.  Arbitrary-topology physical simulation and generic
solve(network) / NetworkGraph.solve() remain deferred.

Exported names
--------------
TopologyBranchId                 — immutable identifier for a topology branch
ParallelBranchDeclaration        — symbolic declaration for one parallel branch
ParallelTopologyComponentIds     — frozen container of 7 component instance IDs
ParallelTopologyNodeIds          — frozen container of 6 graph node IDs
ParallelTopologyUnknownNames     — frozen container of 13 explicit unknown names
ParallelTopologyResidualNames    — frozen container of 13 explicit residual names
ParallelTopologyScenario         — immutable assembled scenario object
build_parallel_topology_scenario — deterministic factory returning
                                   ParallelTopologyScenario

Architecture constraints enforced here
---------------------------------------
MUST NOT import mpl_sim.components, mpl_sim.properties, mpl_sim.correlations,
    mpl_sim.calibration, mpl_sim.hx_models, mpl_sim.closed_loop, or mpl_sim.solvers.
MUST NOT import CoolProp or any property engine.
MUST NOT store FluidState, SystemState, mdot values, pressure values, or
    enthalpy values.
MUST NOT call contribute(...) or define a method named contribute.
MUST NOT call PropertyBackend, CorrelationRegistry, or HeatExchangerModelRegistry.
MUST NOT implement solve(network) or NetworkGraph.solve().
MUST NOT execute production component physics.
MUST NOT infer physics from component_type.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from mpl_sim.network.component_binding import (
    ComponentBinding,
    ComponentBindingSet,
    ComponentStateMap,
    NetworkBindingContext,
    build_binding_context,
)
from mpl_sim.network.graph import (
    ComponentInstance,
    ComponentInstanceId,
    GraphNode,
    GraphNodeId,
    NetworkGraph,
)
from mpl_sim.network.residual_assembly import (
    NetworkResidualAssembly,
    assemble_network_residuals,
)
from mpl_sim.network.topology_declarations import JunctionRole, ManifoldDeclaration

# ---------------------------------------------------------------------------
# TopologyBranchId
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TopologyBranchId:
    """Immutable identifier for a named parallel topology branch.

    Raises
    ------
    TypeError
        If value is not a str.
    ValueError
        If value is empty or whitespace-only.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise TypeError(
                "TopologyBranchId.value must be a str; " f"got {type(self.value).__name__!r}"
            )
        if not self.value.strip():
            raise ValueError("TopologyBranchId.value must be non-empty; " f"got {self.value!r}")

    def __str__(self) -> str:
        return self.value


# ---------------------------------------------------------------------------
# ParallelBranchDeclaration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParallelBranchDeclaration:
    """Symbolic declaration for one branch in a parallel topology.

    Carries the branch identifier, the shared inlet node (split node), the
    branch-specific outlet node, the branch component ID, and the symbolic
    merge component ID that carries flow from this branch outlet to the
    common merge node.

    This is a topology annotation only.  No physics, no residuals, no
    equations are stored here.

    Fields
    ------
    branch_id         : TopologyBranchId identifying this branch
    inlet_node        : GraphNodeId of the shared split node
    outlet_node       : GraphNodeId of this branch's outlet
    component_id      : ComponentInstanceId of the branch element
    merge_component_id: ComponentInstanceId of the merge element for this branch

    Raises
    ------
    TypeError
        If any field has the wrong type.
    ValueError
        If inlet_node equals outlet_node.
    """

    branch_id: TopologyBranchId
    inlet_node: GraphNodeId
    outlet_node: GraphNodeId
    component_id: ComponentInstanceId
    merge_component_id: ComponentInstanceId

    def __post_init__(self) -> None:
        if not isinstance(self.branch_id, TopologyBranchId):
            raise TypeError(
                "ParallelBranchDeclaration.branch_id must be a TopologyBranchId; "
                f"got {type(self.branch_id).__name__!r}"
            )
        if not isinstance(self.inlet_node, GraphNodeId):
            raise TypeError(
                "ParallelBranchDeclaration.inlet_node must be a GraphNodeId; "
                f"got {type(self.inlet_node).__name__!r}"
            )
        if not isinstance(self.outlet_node, GraphNodeId):
            raise TypeError(
                "ParallelBranchDeclaration.outlet_node must be a GraphNodeId; "
                f"got {type(self.outlet_node).__name__!r}"
            )
        if self.inlet_node == self.outlet_node:
            raise ValueError(
                "ParallelBranchDeclaration.inlet_node and outlet_node must differ; "
                f"both are {self.inlet_node.value!r}"
            )
        if not isinstance(self.component_id, ComponentInstanceId):
            raise TypeError(
                "ParallelBranchDeclaration.component_id must be a ComponentInstanceId; "
                f"got {type(self.component_id).__name__!r}"
            )
        if not isinstance(self.merge_component_id, ComponentInstanceId):
            raise TypeError(
                "ParallelBranchDeclaration.merge_component_id must be a ComponentInstanceId; "
                f"got {type(self.merge_component_id).__name__!r}"
            )


# ---------------------------------------------------------------------------
# ParallelTopologyComponentIds
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParallelTopologyComponentIds:
    """Frozen container of the seven component instance IDs in the parallel topology.

    Logical roles (labels only — no physics attached):
      accumulator : reservoir / accumulator role
      pump        : circulation pump role
      branch_a    : parallel branch A element
      branch_b    : parallel branch B element
      merge_a     : merge element for branch A (branch A outlet to merge node)
      merge_b     : merge element for branch B (branch B outlet to merge node)
      condenser   : primary condenser role

    All seven IDs must be distinct ComponentInstanceId objects.
    """

    accumulator: ComponentInstanceId
    pump: ComponentInstanceId
    branch_a: ComponentInstanceId
    branch_b: ComponentInstanceId
    merge_a: ComponentInstanceId
    merge_b: ComponentInstanceId
    condenser: ComponentInstanceId

    def __post_init__(self) -> None:
        fields = (
            ("accumulator", self.accumulator),
            ("pump", self.pump),
            ("branch_a", self.branch_a),
            ("branch_b", self.branch_b),
            ("merge_a", self.merge_a),
            ("merge_b", self.merge_b),
            ("condenser", self.condenser),
        )
        for field_name, value in fields:
            if not isinstance(value, ComponentInstanceId):
                raise TypeError(
                    f"ParallelTopologyComponentIds.{field_name} must be a "
                    f"ComponentInstanceId; got {type(value).__name__!r}"
                )
        ids = [v.value for _, v in fields]
        if len(set(ids)) != 7:
            raise ValueError(
                "ParallelTopologyComponentIds: all seven component IDs must be "
                f"distinct; got {ids!r}"
            )

    def all_ids(self) -> tuple[ComponentInstanceId, ...]:
        """All seven component IDs in declaration order."""
        return (
            self.accumulator,
            self.pump,
            self.branch_a,
            self.branch_b,
            self.merge_a,
            self.merge_b,
            self.condenser,
        )


# ---------------------------------------------------------------------------
# ParallelTopologyNodeIds
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParallelTopologyNodeIds:
    """Frozen container of the six graph node IDs in the parallel topology.

    Logical roles (labels only — no physics attached):
      n_acc_out   : accumulator outlet / pump inlet
      n_pump_out  : pump outlet / split point (both branches draw from here)
      n_a_out     : branch A outlet
      n_b_out     : branch B outlet
      n_merge_out : merge point / condenser inlet (both merge elements deliver here)
      n_cond_out  : condenser outlet / accumulator inlet

    All six IDs must be distinct GraphNodeId objects.
    """

    n_acc_out: GraphNodeId
    n_pump_out: GraphNodeId
    n_a_out: GraphNodeId
    n_b_out: GraphNodeId
    n_merge_out: GraphNodeId
    n_cond_out: GraphNodeId

    def __post_init__(self) -> None:
        fields = (
            ("n_acc_out", self.n_acc_out),
            ("n_pump_out", self.n_pump_out),
            ("n_a_out", self.n_a_out),
            ("n_b_out", self.n_b_out),
            ("n_merge_out", self.n_merge_out),
            ("n_cond_out", self.n_cond_out),
        )
        for field_name, value in fields:
            if not isinstance(value, GraphNodeId):
                raise TypeError(
                    f"ParallelTopologyNodeIds.{field_name} must be a "
                    f"GraphNodeId; got {type(value).__name__!r}"
                )
        ids = [v.value for _, v in fields]
        if len(set(ids)) != 6:
            raise ValueError(
                "ParallelTopologyNodeIds: all six node IDs must be distinct; " f"got {ids!r}"
            )

    def all_ids(self) -> tuple[GraphNodeId, ...]:
        """All six node IDs in declaration order."""
        return (
            self.n_acc_out,
            self.n_pump_out,
            self.n_a_out,
            self.n_b_out,
            self.n_merge_out,
            self.n_cond_out,
        )


# ---------------------------------------------------------------------------
# ParallelTopologyUnknownNames
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParallelTopologyUnknownNames:
    """Frozen container of 13 explicit unknown name strings.

    Names are declaration-only string labels.  No physical values are attached.
    Ordering matches assemble_network_residuals convention:
      first the 7 mass-flow unknowns (component insertion order),
      then the 6 pressure unknowns (node insertion order).

    Component insertion order: accumulator, pump, branch_a, branch_b,
                                merge_a, merge_b, condenser
    Node insertion order:      n_acc_out, n_pump_out, n_a_out, n_b_out,
                                n_merge_out, n_cond_out
    """

    mdot_accumulator: str
    mdot_pump: str
    mdot_branch_a: str
    mdot_branch_b: str
    mdot_merge_a: str
    mdot_merge_b: str
    mdot_condenser: str
    P_n_acc_out: str
    P_n_pump_out: str
    P_n_a_out: str
    P_n_b_out: str
    P_n_merge_out: str
    P_n_cond_out: str

    def __post_init__(self) -> None:
        fields = (
            ("mdot_accumulator", self.mdot_accumulator),
            ("mdot_pump", self.mdot_pump),
            ("mdot_branch_a", self.mdot_branch_a),
            ("mdot_branch_b", self.mdot_branch_b),
            ("mdot_merge_a", self.mdot_merge_a),
            ("mdot_merge_b", self.mdot_merge_b),
            ("mdot_condenser", self.mdot_condenser),
            ("P_n_acc_out", self.P_n_acc_out),
            ("P_n_pump_out", self.P_n_pump_out),
            ("P_n_a_out", self.P_n_a_out),
            ("P_n_b_out", self.P_n_b_out),
            ("P_n_merge_out", self.P_n_merge_out),
            ("P_n_cond_out", self.P_n_cond_out),
        )
        for field_name, value in fields:
            if not isinstance(value, str):
                raise TypeError(
                    f"ParallelTopologyUnknownNames.{field_name} must be a str; "
                    f"got {type(value).__name__!r}"
                )
            if not value.strip():
                raise ValueError(
                    f"ParallelTopologyUnknownNames.{field_name} must be "
                    f"non-empty; got {value!r}"
                )
        names = self.all_names()
        if len(set(names)) != len(names):
            raise ValueError(
                "ParallelTopologyUnknownNames: all unknown names must be "
                f"distinct; got {list(names)!r}"
            )

    def all_names(self) -> tuple[str, ...]:
        """All 13 unknown names in declaration order."""
        return (
            self.mdot_accumulator,
            self.mdot_pump,
            self.mdot_branch_a,
            self.mdot_branch_b,
            self.mdot_merge_a,
            self.mdot_merge_b,
            self.mdot_condenser,
            self.P_n_acc_out,
            self.P_n_pump_out,
            self.P_n_a_out,
            self.P_n_b_out,
            self.P_n_merge_out,
            self.P_n_cond_out,
        )


# ---------------------------------------------------------------------------
# ParallelTopologyResidualNames
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParallelTopologyResidualNames:
    """Frozen container of 13 explicit residual name strings.

    Names are declaration-only string labels.  No physical values are attached.
    Ordering matches assemble_network_residuals convention:
      first the 6 mass-balance residuals (node insertion order),
      then the 7 pressure-drop residuals (component insertion order).

    Node insertion order:      n_acc_out, n_pump_out, n_a_out, n_b_out,
                                n_merge_out, n_cond_out
    Component insertion order: accumulator, pump, branch_a, branch_b,
                                merge_a, merge_b, condenser
    """

    mass_balance_n_acc_out: str
    mass_balance_n_pump_out: str
    mass_balance_n_a_out: str
    mass_balance_n_b_out: str
    mass_balance_n_merge_out: str
    mass_balance_n_cond_out: str
    pressure_drop_accumulator: str
    pressure_drop_pump: str
    pressure_drop_branch_a: str
    pressure_drop_branch_b: str
    pressure_drop_merge_a: str
    pressure_drop_merge_b: str
    pressure_drop_condenser: str

    def __post_init__(self) -> None:
        fields = (
            ("mass_balance_n_acc_out", self.mass_balance_n_acc_out),
            ("mass_balance_n_pump_out", self.mass_balance_n_pump_out),
            ("mass_balance_n_a_out", self.mass_balance_n_a_out),
            ("mass_balance_n_b_out", self.mass_balance_n_b_out),
            ("mass_balance_n_merge_out", self.mass_balance_n_merge_out),
            ("mass_balance_n_cond_out", self.mass_balance_n_cond_out),
            ("pressure_drop_accumulator", self.pressure_drop_accumulator),
            ("pressure_drop_pump", self.pressure_drop_pump),
            ("pressure_drop_branch_a", self.pressure_drop_branch_a),
            ("pressure_drop_branch_b", self.pressure_drop_branch_b),
            ("pressure_drop_merge_a", self.pressure_drop_merge_a),
            ("pressure_drop_merge_b", self.pressure_drop_merge_b),
            ("pressure_drop_condenser", self.pressure_drop_condenser),
        )
        for field_name, value in fields:
            if not isinstance(value, str):
                raise TypeError(
                    f"ParallelTopologyResidualNames.{field_name} must be a str; "
                    f"got {type(value).__name__!r}"
                )
            if not value.strip():
                raise ValueError(
                    f"ParallelTopologyResidualNames.{field_name} must be "
                    f"non-empty; got {value!r}"
                )
        names = self.all_names()
        if len(set(names)) != len(names):
            raise ValueError(
                "ParallelTopologyResidualNames: all residual names must be "
                f"distinct; got {list(names)!r}"
            )

    def all_names(self) -> tuple[str, ...]:
        """All 13 residual names in declaration order."""
        return (
            self.mass_balance_n_acc_out,
            self.mass_balance_n_pump_out,
            self.mass_balance_n_a_out,
            self.mass_balance_n_b_out,
            self.mass_balance_n_merge_out,
            self.mass_balance_n_cond_out,
            self.pressure_drop_accumulator,
            self.pressure_drop_pump,
            self.pressure_drop_branch_a,
            self.pressure_drop_branch_b,
            self.pressure_drop_merge_a,
            self.pressure_drop_merge_b,
            self.pressure_drop_condenser,
        )


# ---------------------------------------------------------------------------
# ParallelTopologyScenario
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParallelTopologyScenario:
    """Immutable fixed two-branch parallel topology scenario declaration.

    Contains all structural declarations for the fixed parallel network:
        accumulator -> pump -> [branch_a/branch_b] -> [merge_a/merge_b] -> condenser -> accumulator

    This object is declaration-only.  It does not contain FluidState,
    SystemState, physical state values, property backend objects, or
    production component objects.

    Fields
    ------
    graph           : NetworkGraph (6 nodes, 7 components)
    assembly        : NetworkResidualAssembly (13 unknowns, 13 residuals)
    binding_context : NetworkBindingContext (explicit bindings and state map)
    component_ids   : ParallelTopologyComponentIds (7 component instance IDs)
    node_ids        : ParallelTopologyNodeIds (6 graph node IDs)
    unknown_names   : ParallelTopologyUnknownNames (13 explicit unknown names)
    residual_names  : ParallelTopologyResidualNames (13 explicit residual names)
    branches        : tuple of exactly two ParallelBranchDeclaration objects
    split_manifold  : ManifoldDeclaration for the SPLIT junction
    merge_manifold  : ManifoldDeclaration for the MERGE junction
    metadata        : optional caller-supplied metadata; defensively copied
    """

    graph: NetworkGraph
    assembly: NetworkResidualAssembly
    binding_context: NetworkBindingContext
    component_ids: ParallelTopologyComponentIds
    node_ids: ParallelTopologyNodeIds
    unknown_names: ParallelTopologyUnknownNames
    residual_names: ParallelTopologyResidualNames
    branches: tuple[ParallelBranchDeclaration, ...]
    split_manifold: ManifoldDeclaration
    merge_manifold: ManifoldDeclaration
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.graph, NetworkGraph):
            raise TypeError(
                "ParallelTopologyScenario.graph must be a NetworkGraph; "
                f"got {type(self.graph).__name__!r}"
            )
        if not isinstance(self.assembly, NetworkResidualAssembly):
            raise TypeError(
                "ParallelTopologyScenario.assembly must be a "
                "NetworkResidualAssembly; "
                f"got {type(self.assembly).__name__!r}"
            )
        if not isinstance(self.binding_context, NetworkBindingContext):
            raise TypeError(
                "ParallelTopologyScenario.binding_context must be a "
                "NetworkBindingContext; "
                f"got {type(self.binding_context).__name__!r}"
            )
        if not isinstance(self.component_ids, ParallelTopologyComponentIds):
            raise TypeError(
                "ParallelTopologyScenario.component_ids must be a "
                "ParallelTopologyComponentIds; "
                f"got {type(self.component_ids).__name__!r}"
            )
        if not isinstance(self.node_ids, ParallelTopologyNodeIds):
            raise TypeError(
                "ParallelTopologyScenario.node_ids must be a "
                "ParallelTopologyNodeIds; "
                f"got {type(self.node_ids).__name__!r}"
            )
        if not isinstance(self.unknown_names, ParallelTopologyUnknownNames):
            raise TypeError(
                "ParallelTopologyScenario.unknown_names must be a "
                "ParallelTopologyUnknownNames; "
                f"got {type(self.unknown_names).__name__!r}"
            )
        if not isinstance(self.residual_names, ParallelTopologyResidualNames):
            raise TypeError(
                "ParallelTopologyScenario.residual_names must be a "
                "ParallelTopologyResidualNames; "
                f"got {type(self.residual_names).__name__!r}"
            )
        if self.binding_context.graph is not self.graph:
            raise ValueError(
                "ParallelTopologyScenario.binding_context.graph must reference "
                "the scenario graph"
            )
        if self.binding_context.assembly is not self.assembly:
            raise ValueError(
                "ParallelTopologyScenario.binding_context.assembly must reference "
                "the scenario assembly"
            )

        graph_component_ids = self.graph.instance_ids()
        if graph_component_ids != self.component_ids.all_ids():
            raise ValueError(
                "ParallelTopologyScenario.component_ids must match graph component "
                "IDs in declaration order"
            )
        graph_node_ids = self.graph.node_ids()
        if graph_node_ids != self.node_ids.all_ids():
            raise ValueError(
                "ParallelTopologyScenario.node_ids must match graph node IDs in "
                "declaration order"
            )
        if self.assembly.unknowns.names() != self.unknown_names.all_names():
            raise ValueError(
                "ParallelTopologyScenario.unknown_names must match assembly unknown "
                "names in declaration order"
            )
        if self.assembly.residuals.names() != self.residual_names.all_names():
            raise ValueError(
                "ParallelTopologyScenario.residual_names must match assembly residual "
                "names in declaration order"
            )

        # Revalidate the public binding context rather than trusting that callers
        # used build_binding_context to construct it.
        build_binding_context(
            self.graph,
            self.assembly,
            self.binding_context.binding_set,
            self.binding_context.state_map,
            metadata=self.binding_context.metadata,
        )
        mapped_unknown_names = set(self.binding_context.state_map.unknown_to_component) | set(
            self.binding_context.state_map.unknown_to_node
        )
        if mapped_unknown_names != set(self.unknown_names.all_names()):
            raise ValueError(
                "ParallelTopologyScenario.binding_context must map every declared "
                "unknown exactly once"
            )
        mapped_residual_names = set(self.binding_context.state_map.residual_to_component) | set(
            self.binding_context.state_map.residual_to_node
        )
        if mapped_residual_names != set(self.residual_names.all_names()):
            raise ValueError(
                "ParallelTopologyScenario.binding_context must map every declared "
                "residual exactly once"
            )

        # Normalize and validate branches tuple.
        branches = self.branches
        if not isinstance(branches, tuple):
            try:
                branches = tuple(branches)
            except TypeError:
                raise TypeError(
                    "ParallelTopologyScenario.branches must be a sequence of "
                    "ParallelBranchDeclaration; "
                    f"got {type(self.branches).__name__!r}"
                )
            object.__setattr__(self, "branches", branches)
        if len(branches) < 2:
            raise ValueError(
                "ParallelTopologyScenario.branches must have at least two entries; "
                f"got {len(branches)}"
            )
        for i, b in enumerate(branches):
            if not isinstance(b, ParallelBranchDeclaration):
                raise TypeError(
                    f"ParallelTopologyScenario.branches[{i}] must be a "
                    "ParallelBranchDeclaration; "
                    f"got {type(b).__name__!r}"
                )
        # Validate unique branch IDs.
        seen_branch_ids: set[str] = set()
        for b in branches:
            bid = b.branch_id.value
            if bid in seen_branch_ids:
                raise ValueError(
                    "ParallelTopologyScenario.branches must have distinct branch IDs; "
                    f"duplicate: {bid!r}"
                )
            seen_branch_ids.add(bid)
        expected_branches = (
            ParallelBranchDeclaration(
                branch_id=TopologyBranchId("a"),
                inlet_node=self.node_ids.n_pump_out,
                outlet_node=self.node_ids.n_a_out,
                component_id=self.component_ids.branch_a,
                merge_component_id=self.component_ids.merge_a,
            ),
            ParallelBranchDeclaration(
                branch_id=TopologyBranchId("b"),
                inlet_node=self.node_ids.n_pump_out,
                outlet_node=self.node_ids.n_b_out,
                component_id=self.component_ids.branch_b,
                merge_component_id=self.component_ids.merge_b,
            ),
        )
        if branches != expected_branches:
            raise ValueError(
                "ParallelTopologyScenario.branches must match the fixed two-branch "
                "graph declaration"
            )
        if not isinstance(self.split_manifold, ManifoldDeclaration):
            raise TypeError(
                "ParallelTopologyScenario.split_manifold must be a "
                "ManifoldDeclaration; "
                f"got {type(self.split_manifold).__name__!r}"
            )
        if not isinstance(self.merge_manifold, ManifoldDeclaration):
            raise TypeError(
                "ParallelTopologyScenario.merge_manifold must be a "
                "ManifoldDeclaration; "
                f"got {type(self.merge_manifold).__name__!r}"
            )
        expected_split = ManifoldDeclaration(
            manifold_id=f"split_manifold:{self.node_ids.n_pump_out.value}",
            role=JunctionRole.SPLIT,
            common_node=self.node_ids.n_pump_out,
            branch_nodes=(self.node_ids.n_a_out, self.node_ids.n_b_out),
            branch_labels=("a", "b"),
        )
        if self.split_manifold != expected_split:
            raise ValueError(
                "ParallelTopologyScenario.split_manifold must match the fixed "
                "parallel split declaration"
            )
        expected_merge = ManifoldDeclaration(
            manifold_id=f"merge_manifold:{self.node_ids.n_merge_out.value}",
            role=JunctionRole.MERGE,
            common_node=self.node_ids.n_merge_out,
            branch_nodes=(self.node_ids.n_a_out, self.node_ids.n_b_out),
            branch_labels=("a", "b"),
        )
        if self.merge_manifold != expected_merge:
            raise ValueError(
                "ParallelTopologyScenario.merge_manifold must match the fixed "
                "parallel merge declaration"
            )
        md = self.metadata
        if md is not None:
            if not isinstance(md, Mapping):
                raise TypeError(
                    "ParallelTopologyScenario.metadata must be a Mapping or None; "
                    f"got {type(md).__name__!r}"
                )
            object.__setattr__(self, "metadata", MappingProxyType(dict(md)))

    def summary(self) -> dict[str, object]:
        """Structural summary with labels only.  No physical values."""
        return {
            "topology": (
                "accumulator -> pump -> [branch_a/branch_b] "
                "-> [merge_a/merge_b] -> condenser -> accumulator"
            ),
            "branch_count": len(self.branches),
            "branch_ids": [b.branch_id.value for b in self.branches],
            "component_ids": {
                "accumulator": self.component_ids.accumulator.value,
                "pump": self.component_ids.pump.value,
                "branch_a": self.component_ids.branch_a.value,
                "branch_b": self.component_ids.branch_b.value,
                "merge_a": self.component_ids.merge_a.value,
                "merge_b": self.component_ids.merge_b.value,
                "condenser": self.component_ids.condenser.value,
            },
            "node_ids": {
                "n_acc_out": self.node_ids.n_acc_out.value,
                "n_pump_out": self.node_ids.n_pump_out.value,
                "n_a_out": self.node_ids.n_a_out.value,
                "n_b_out": self.node_ids.n_b_out.value,
                "n_merge_out": self.node_ids.n_merge_out.value,
                "n_cond_out": self.node_ids.n_cond_out.value,
            },
            "unknown_count": self.assembly.unknowns.count(),
            "unknown_names": list(self.assembly.unknowns.names()),
            "residual_count": self.assembly.residuals.count(),
            "residual_names": list(self.assembly.residuals.names()),
        }


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------


def build_parallel_topology_scenario(
    *,
    accumulator_id: str = "accumulator",
    pump_id: str = "pump",
    branch_a_id: str = "branch_a",
    branch_b_id: str = "branch_b",
    merge_a_id: str = "merge_a",
    merge_b_id: str = "merge_b",
    condenser_id: str = "condenser",
    n_acc_out_id: str = "n_acc_out",
    n_pump_out_id: str = "n_pump_out",
    n_a_out_id: str = "n_a_out",
    n_b_out_id: str = "n_b_out",
    n_merge_out_id: str = "n_merge_out",
    n_cond_out_id: str = "n_cond_out",
    metadata: Mapping[str, object] | None = None,
) -> ParallelTopologyScenario:
    """Build a deterministic fixed two-branch parallel topology scenario declaration.

    Creates and validates all declarations for the parallel network:
        accumulator -> pump -> [branch_a/branch_b] -> [merge_a/merge_b]
            -> condenser -> accumulator

    All ID parameters are symbolic string labels only.  No physical values,
    no property defaults, no CoolProp, no PropertyBackend, no correlations.

    Graph topology (7 components, 6 nodes):
      Components (insertion order):
        accumulator : n_cond_out -> n_acc_out
        pump        : n_acc_out  -> n_pump_out
        branch_a    : n_pump_out -> n_a_out
        branch_b    : n_pump_out -> n_b_out
        merge_a     : n_a_out   -> n_merge_out
        merge_b     : n_b_out   -> n_merge_out
        condenser   : n_merge_out -> n_cond_out
      Nodes (insertion order):
        n_acc_out, n_pump_out, n_a_out, n_b_out, n_merge_out, n_cond_out

    The assembly declares 13 unknowns (7 mdot + 6 P) and 13 residuals
    (6 mass_balance + 7 pressure_drop) in deterministic graph-insertion order.

    Parameters
    ----------
    accumulator_id : str   Label for the accumulator/reservoir component.
    pump_id        : str   Label for the pump component.
    branch_a_id    : str   Label for parallel branch A element.
    branch_b_id    : str   Label for parallel branch B element.
    merge_a_id     : str   Label for merge element for branch A.
    merge_b_id     : str   Label for merge element for branch B.
    condenser_id   : str   Label for the condenser component.
    n_acc_out_id   : str   Label for the accumulator outlet / pump inlet node.
    n_pump_out_id  : str   Label for the pump outlet / split node.
    n_a_out_id     : str   Label for the branch A outlet node.
    n_b_out_id     : str   Label for the branch B outlet node.
    n_merge_out_id : str   Label for the merge outlet / condenser inlet node.
    n_cond_out_id  : str   Label for the condenser outlet / accumulator inlet node.
    metadata       : Mapping[str, object] | None
                           Optional caller-supplied metadata stored on the scenario.

    Returns
    -------
    ParallelTopologyScenario
        Immutable scenario with graph, assembly, binding context, component IDs,
        node IDs, unknown names, residual names, branch declarations, and
        manifold declarations.

    Raises
    ------
    TypeError
        If any ID parameter is not a str.
        If metadata is not a Mapping or None.
    ValueError
        If any ID is empty or whitespace-only.
        If component IDs are not all distinct.
        If node IDs are not all distinct.
    """
    # Validate component ID string parameters.
    _component_params: dict[str, str] = {
        "accumulator_id": accumulator_id,
        "pump_id": pump_id,
        "branch_a_id": branch_a_id,
        "branch_b_id": branch_b_id,
        "merge_a_id": merge_a_id,
        "merge_b_id": merge_b_id,
        "condenser_id": condenser_id,
    }
    for param_name, param_value in _component_params.items():
        if not isinstance(param_value, str):
            raise TypeError(
                f"build_parallel_topology_scenario: {param_name} must be a "
                f"str; got {type(param_value).__name__!r}"
            )
        if not param_value.strip():
            raise ValueError(
                f"build_parallel_topology_scenario: {param_name} must be "
                f"non-empty; got {param_value!r}"
            )

    # Validate node ID string parameters.
    _node_params: dict[str, str] = {
        "n_acc_out_id": n_acc_out_id,
        "n_pump_out_id": n_pump_out_id,
        "n_a_out_id": n_a_out_id,
        "n_b_out_id": n_b_out_id,
        "n_merge_out_id": n_merge_out_id,
        "n_cond_out_id": n_cond_out_id,
    }
    for param_name, param_value in _node_params.items():
        if not isinstance(param_value, str):
            raise TypeError(
                f"build_parallel_topology_scenario: {param_name} must be a "
                f"str; got {type(param_value).__name__!r}"
            )
        if not param_value.strip():
            raise ValueError(
                f"build_parallel_topology_scenario: {param_name} must be "
                f"non-empty; got {param_value!r}"
            )

    # Validate uniqueness before constructing typed objects.
    _component_id_values = [
        accumulator_id,
        pump_id,
        branch_a_id,
        branch_b_id,
        merge_a_id,
        merge_b_id,
        condenser_id,
    ]
    if len(set(_component_id_values)) != 7:
        raise ValueError(
            "build_parallel_topology_scenario: all component IDs must be "
            f"distinct; got {_component_id_values!r}"
        )

    _node_id_values = [
        n_acc_out_id,
        n_pump_out_id,
        n_a_out_id,
        n_b_out_id,
        n_merge_out_id,
        n_cond_out_id,
    ]
    if len(set(_node_id_values)) != 6:
        raise ValueError(
            "build_parallel_topology_scenario: all node IDs must be distinct; "
            f"got {_node_id_values!r}"
        )

    if metadata is not None and not isinstance(metadata, Mapping):
        raise TypeError(
            "build_parallel_topology_scenario: metadata must be a Mapping or "
            f"None; got {type(metadata).__name__!r}"
        )

    # Build typed ID objects.
    _acc_cid = ComponentInstanceId(accumulator_id)
    _pump_cid = ComponentInstanceId(pump_id)
    _br_a_cid = ComponentInstanceId(branch_a_id)
    _br_b_cid = ComponentInstanceId(branch_b_id)
    _mg_a_cid = ComponentInstanceId(merge_a_id)
    _mg_b_cid = ComponentInstanceId(merge_b_id)
    _cond_cid = ComponentInstanceId(condenser_id)

    _n_acc_out = GraphNodeId(n_acc_out_id)
    _n_pump_out = GraphNodeId(n_pump_out_id)
    _n_a_out = GraphNodeId(n_a_out_id)
    _n_b_out = GraphNodeId(n_b_out_id)
    _n_merge_out = GraphNodeId(n_merge_out_id)
    _n_cond_out = GraphNodeId(n_cond_out_id)

    # Build ID containers.
    component_ids = ParallelTopologyComponentIds(
        accumulator=_acc_cid,
        pump=_pump_cid,
        branch_a=_br_a_cid,
        branch_b=_br_b_cid,
        merge_a=_mg_a_cid,
        merge_b=_mg_b_cid,
        condenser=_cond_cid,
    )
    node_ids = ParallelTopologyNodeIds(
        n_acc_out=_n_acc_out,
        n_pump_out=_n_pump_out,
        n_a_out=_n_a_out,
        n_b_out=_n_b_out,
        n_merge_out=_n_merge_out,
        n_cond_out=_n_cond_out,
    )

    # Build unknown and residual name containers.
    # Names use the same f-string convention as assemble_network_residuals:
    #   mdot:<instance_id>       for mass-flow unknowns
    #   P:<node_id>              for pressure unknowns
    #   mass_balance:<node_id>   for mass-balance residuals
    #   pressure_drop:<inst_id>  for pressure-drop residuals
    unknown_names = ParallelTopologyUnknownNames(
        mdot_accumulator=f"mdot:{accumulator_id}",
        mdot_pump=f"mdot:{pump_id}",
        mdot_branch_a=f"mdot:{branch_a_id}",
        mdot_branch_b=f"mdot:{branch_b_id}",
        mdot_merge_a=f"mdot:{merge_a_id}",
        mdot_merge_b=f"mdot:{merge_b_id}",
        mdot_condenser=f"mdot:{condenser_id}",
        P_n_acc_out=f"P:{n_acc_out_id}",
        P_n_pump_out=f"P:{n_pump_out_id}",
        P_n_a_out=f"P:{n_a_out_id}",
        P_n_b_out=f"P:{n_b_out_id}",
        P_n_merge_out=f"P:{n_merge_out_id}",
        P_n_cond_out=f"P:{n_cond_out_id}",
    )
    residual_names = ParallelTopologyResidualNames(
        mass_balance_n_acc_out=f"mass_balance:{n_acc_out_id}",
        mass_balance_n_pump_out=f"mass_balance:{n_pump_out_id}",
        mass_balance_n_a_out=f"mass_balance:{n_a_out_id}",
        mass_balance_n_b_out=f"mass_balance:{n_b_out_id}",
        mass_balance_n_merge_out=f"mass_balance:{n_merge_out_id}",
        mass_balance_n_cond_out=f"mass_balance:{n_cond_out_id}",
        pressure_drop_accumulator=f"pressure_drop:{accumulator_id}",
        pressure_drop_pump=f"pressure_drop:{pump_id}",
        pressure_drop_branch_a=f"pressure_drop:{branch_a_id}",
        pressure_drop_branch_b=f"pressure_drop:{branch_b_id}",
        pressure_drop_merge_a=f"pressure_drop:{merge_a_id}",
        pressure_drop_merge_b=f"pressure_drop:{merge_b_id}",
        pressure_drop_condenser=f"pressure_drop:{condenser_id}",
    )

    # Build graph.
    # Topology:
    #   accumulator : n_cond_out  -> n_acc_out
    #   pump        : n_acc_out   -> n_pump_out
    #   branch_a    : n_pump_out  -> n_a_out
    #   branch_b    : n_pump_out  -> n_b_out
    #   merge_a     : n_a_out     -> n_merge_out
    #   merge_b     : n_b_out     -> n_merge_out
    #   condenser   : n_merge_out -> n_cond_out
    _nodes = [
        GraphNode(_n_acc_out),
        GraphNode(_n_pump_out),
        GraphNode(_n_a_out),
        GraphNode(_n_b_out),
        GraphNode(_n_merge_out),
        GraphNode(_n_cond_out),
    ]
    _instances = [
        ComponentInstance(
            instance_id=_acc_cid,
            component_type="accumulator",
            inlet_node=_n_cond_out,
            outlet_node=_n_acc_out,
        ),
        ComponentInstance(
            instance_id=_pump_cid,
            component_type="pump",
            inlet_node=_n_acc_out,
            outlet_node=_n_pump_out,
        ),
        ComponentInstance(
            instance_id=_br_a_cid,
            component_type="branch_element",
            inlet_node=_n_pump_out,
            outlet_node=_n_a_out,
        ),
        ComponentInstance(
            instance_id=_br_b_cid,
            component_type="branch_element",
            inlet_node=_n_pump_out,
            outlet_node=_n_b_out,
        ),
        ComponentInstance(
            instance_id=_mg_a_cid,
            component_type="merge_element",
            inlet_node=_n_a_out,
            outlet_node=_n_merge_out,
        ),
        ComponentInstance(
            instance_id=_mg_b_cid,
            component_type="merge_element",
            inlet_node=_n_b_out,
            outlet_node=_n_merge_out,
        ),
        ComponentInstance(
            instance_id=_cond_cid,
            component_type="condenser",
            inlet_node=_n_merge_out,
            outlet_node=_n_cond_out,
        ),
    ]
    graph = NetworkGraph(nodes=_nodes, instances=_instances)

    # Assemble residuals (parallel topology: no closed-loop constraint).
    assembly = assemble_network_residuals(
        graph,
        require_closed_loop=False,
        include_pressure_unknowns=True,
        include_pressure_residuals=True,
    )

    # Build component bindings (one per component instance).
    _bindings = ComponentBindingSet(
        bindings=(
            ComponentBinding(instance_id=_acc_cid, binding_name="accumulator"),
            ComponentBinding(instance_id=_pump_cid, binding_name="pump"),
            ComponentBinding(instance_id=_br_a_cid, binding_name="branch_a"),
            ComponentBinding(instance_id=_br_b_cid, binding_name="branch_b"),
            ComponentBinding(instance_id=_mg_a_cid, binding_name="merge_a"),
            ComponentBinding(instance_id=_mg_b_cid, binding_name="merge_b"),
            ComponentBinding(instance_id=_cond_cid, binding_name="condenser"),
        )
    )

    # Build state map.
    _state_map = ComponentStateMap(
        unknown_to_component={
            unknown_names.mdot_accumulator: _acc_cid,
            unknown_names.mdot_pump: _pump_cid,
            unknown_names.mdot_branch_a: _br_a_cid,
            unknown_names.mdot_branch_b: _br_b_cid,
            unknown_names.mdot_merge_a: _mg_a_cid,
            unknown_names.mdot_merge_b: _mg_b_cid,
            unknown_names.mdot_condenser: _cond_cid,
        },
        unknown_to_node={
            unknown_names.P_n_acc_out: _n_acc_out,
            unknown_names.P_n_pump_out: _n_pump_out,
            unknown_names.P_n_a_out: _n_a_out,
            unknown_names.P_n_b_out: _n_b_out,
            unknown_names.P_n_merge_out: _n_merge_out,
            unknown_names.P_n_cond_out: _n_cond_out,
        },
        residual_to_node={
            residual_names.mass_balance_n_acc_out: _n_acc_out,
            residual_names.mass_balance_n_pump_out: _n_pump_out,
            residual_names.mass_balance_n_a_out: _n_a_out,
            residual_names.mass_balance_n_b_out: _n_b_out,
            residual_names.mass_balance_n_merge_out: _n_merge_out,
            residual_names.mass_balance_n_cond_out: _n_cond_out,
        },
        residual_to_component={
            residual_names.pressure_drop_accumulator: _acc_cid,
            residual_names.pressure_drop_pump: _pump_cid,
            residual_names.pressure_drop_branch_a: _br_a_cid,
            residual_names.pressure_drop_branch_b: _br_b_cid,
            residual_names.pressure_drop_merge_a: _mg_a_cid,
            residual_names.pressure_drop_merge_b: _mg_b_cid,
            residual_names.pressure_drop_condenser: _cond_cid,
        },
    )

    # Build binding context (validates coverage and ID references).
    binding_context = build_binding_context(
        graph,
        assembly,
        _bindings,
        _state_map,
        metadata=None,
    )

    # Build manifold declarations.
    split_manifold = ManifoldDeclaration(
        manifold_id=f"split_manifold:{n_pump_out_id}",
        role=JunctionRole.SPLIT,
        common_node=_n_pump_out,
        branch_nodes=(_n_a_out, _n_b_out),
        branch_labels=("a", "b"),
    )
    merge_manifold = ManifoldDeclaration(
        manifold_id=f"merge_manifold:{n_merge_out_id}",
        role=JunctionRole.MERGE,
        common_node=_n_merge_out,
        branch_nodes=(_n_a_out, _n_b_out),
        branch_labels=("a", "b"),
    )

    # Build branch declarations.
    _branch_a = ParallelBranchDeclaration(
        branch_id=TopologyBranchId("a"),
        inlet_node=_n_pump_out,
        outlet_node=_n_a_out,
        component_id=_br_a_cid,
        merge_component_id=_mg_a_cid,
    )
    _branch_b = ParallelBranchDeclaration(
        branch_id=TopologyBranchId("b"),
        inlet_node=_n_pump_out,
        outlet_node=_n_b_out,
        component_id=_br_b_cid,
        merge_component_id=_mg_b_cid,
    )

    return ParallelTopologyScenario(
        graph=graph,
        assembly=assembly,
        binding_context=binding_context,
        component_ids=component_ids,
        node_ids=node_ids,
        unknown_names=unknown_names,
        residual_names=residual_names,
        branches=(_branch_a, _branch_b),
        split_manifold=split_manifold,
        merge_manifold=merge_manifold,
        metadata=metadata,
    )
