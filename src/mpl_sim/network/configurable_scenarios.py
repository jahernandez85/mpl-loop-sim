"""Configurable scenario declaration foundation — Block 15E-A.

Provides explicit, configurable scenario declarations for simple loop and
two-branch MPL-like network scenarios without hardcoding every scenario in
a dedicated builder function.

This is a declaration/assembly module only.  It does not execute production
component physics, evaluate physical residuals, infer closures from roles,
assemble SystemState, construct FluidState, call CoolProp or PropertyBackend,
call correlations or HX models, or add generic solve(network) /
NetworkGraph.solve().

Roles are declaration metadata only.  They do not trigger physical equations,
do not instantiate production components, and do not imply physical defaults.

Exported names
--------------
ScenarioComponentRole          — declarative role enum (metadata only)
ScenarioComponentSpec          — frozen component declaration
ScenarioNodeSpec               — frozen node declaration
ScenarioConnectionSpec         — frozen connection declaration
ScenarioBranchSpec             — frozen branch declaration
ConfigurableScenarioSpec       — frozen validated scenario spec
ConfigurableScenarioBuildResult — immutable build result
build_configurable_scenario    — deterministic builder
build_configurable_scenario_report — plain serializable report

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
MUST NOT infer physics from component roles.
MUST NOT infer closures automatically from roles.
"""

from __future__ import annotations

import enum
import json
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

# ---------------------------------------------------------------------------
# Module-level limitations constant
# ---------------------------------------------------------------------------

_LIMITATIONS: tuple[str, ...] = (
    "declaration-only; no physical residual formulas evaluated",
    "closures not inferred automatically from component roles",
    "production component execution not performed",
    "SystemState not assembled; FluidState not constructed",
    "solve(network) and NetworkGraph.solve() not implemented",
    "not property-backed, not correlation-backed, not HX-backed",
    "roles are metadata only; no physics dispatched from role",
)

# ---------------------------------------------------------------------------
# ScenarioComponentRole
# ---------------------------------------------------------------------------


class ScenarioComponentRole(enum.Enum):
    """Declarative role for a configurable scenario component.

    Values are declaration metadata only.  They do not trigger physical
    equations, do not instantiate production components, do not imply
    physical defaults, and do not infer closures automatically.
    """

    ACCUMULATOR = "accumulator"
    PUMP = "pump"
    EVAPORATOR = "evaporator"
    CONDENSER = "condenser"
    PIPE = "pipe"
    VALVE = "valve"
    JUNCTION = "junction"
    MANIFOLD = "manifold"
    GENERIC = "generic"


# ---------------------------------------------------------------------------
# ScenarioComponentSpec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScenarioComponentSpec:
    """Frozen declaration for one component in a configurable scenario.

    Fields
    ------
    component_id : str                         — explicit non-empty ID
    role         : ScenarioComponentRole        — declarative role (metadata only)
    metadata     : Mapping[str, object] | None  — optional; defensively copied
    tags         : tuple[str, ...]              — optional declarative string tags
    """

    component_id: str
    role: ScenarioComponentRole
    metadata: Mapping[str, object] | None = None
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.component_id, str):
            raise TypeError(
                "ScenarioComponentSpec.component_id must be a str; "
                f"got {type(self.component_id).__name__!r}"
            )
        if not self.component_id.strip():
            raise ValueError(
                "ScenarioComponentSpec.component_id must be non-empty; "
                f"got {self.component_id!r}"
            )
        if not isinstance(self.role, ScenarioComponentRole):
            raise TypeError(
                "ScenarioComponentSpec.role must be a ScenarioComponentRole; "
                f"got {type(self.role).__name__!r}"
            )
        tags = self.tags
        if not isinstance(tags, tuple):
            try:
                object.__setattr__(self, "tags", tuple(tags))
            except TypeError as exc:
                raise TypeError(
                    "ScenarioComponentSpec.tags must be an iterable of non-empty strings"
                ) from exc
            tags = self.tags
        for i, tag in enumerate(tags):
            if not isinstance(tag, str):
                raise TypeError(
                    f"ScenarioComponentSpec.tags[{i}] must be a str; " f"got {type(tag).__name__!r}"
                )
            if not tag.strip():
                raise ValueError(f"ScenarioComponentSpec.tags[{i}] must be non-empty")
        md = self.metadata
        if md is not None:
            if not isinstance(md, Mapping):
                raise TypeError(
                    "ScenarioComponentSpec.metadata must be a Mapping or None; "
                    f"got {type(md).__name__!r}"
                )
            object.__setattr__(self, "metadata", MappingProxyType(dict(md)))


# ---------------------------------------------------------------------------
# ScenarioNodeSpec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScenarioNodeSpec:
    """Frozen declaration for one node in a configurable scenario.

    Fields
    ------
    node_id  : str                         — explicit non-empty ID
    metadata : Mapping[str, object] | None  — optional; defensively copied
    """

    node_id: str
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.node_id, str):
            raise TypeError(
                "ScenarioNodeSpec.node_id must be a str; " f"got {type(self.node_id).__name__!r}"
            )
        if not self.node_id.strip():
            raise ValueError("ScenarioNodeSpec.node_id must be non-empty; " f"got {self.node_id!r}")
        md = self.metadata
        if md is not None:
            if not isinstance(md, Mapping):
                raise TypeError(
                    "ScenarioNodeSpec.metadata must be a Mapping or None; "
                    f"got {type(md).__name__!r}"
                )
            object.__setattr__(self, "metadata", MappingProxyType(dict(md)))


# ---------------------------------------------------------------------------
# ScenarioConnectionSpec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScenarioConnectionSpec:
    """Frozen declaration for one component connection in a configurable scenario.

    Maps a declared component to its inlet and outlet nodes.

    Fields
    ------
    component_id   : str         — component instance ID
    inlet_node_id  : str         — inlet graph node ID
    outlet_node_id : str         — outlet graph node ID
    label          : str | None  — optional connection label
    """

    component_id: str
    inlet_node_id: str
    outlet_node_id: str
    label: str | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("component_id", self.component_id),
            ("inlet_node_id", self.inlet_node_id),
            ("outlet_node_id", self.outlet_node_id),
        ):
            if not isinstance(value, str):
                raise TypeError(
                    f"ScenarioConnectionSpec.{field_name} must be a str; "
                    f"got {type(value).__name__!r}"
                )
            if not value.strip():
                raise ValueError(
                    f"ScenarioConnectionSpec.{field_name} must be non-empty; " f"got {value!r}"
                )
        if self.label is not None and not isinstance(self.label, str):
            raise TypeError(
                "ScenarioConnectionSpec.label must be a str or None; "
                f"got {type(self.label).__name__!r}"
            )
        if self.inlet_node_id == self.outlet_node_id:
            raise ValueError(
                "ScenarioConnectionSpec.inlet_node_id and outlet_node_id must differ; "
                f"both are {self.inlet_node_id!r}"
            )


# ---------------------------------------------------------------------------
# ScenarioBranchSpec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScenarioBranchSpec:
    """Frozen declaration for one parallel branch in a configurable scenario.

    Topology annotation only — no physics, no residuals, no equations.

    Fields
    ------
    branch_id      : str                         — non-empty unique branch ID
    inlet_node_id  : str                         — shared split node ID
    outlet_node_id : str                         — shared merge node ID
    component_ids  : tuple[str, ...]             — ordered component IDs on branch
    metadata       : Mapping[str, object] | None  — optional; defensively copied
    """

    branch_id: str
    inlet_node_id: str
    outlet_node_id: str
    component_ids: tuple[str, ...]
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("branch_id", self.branch_id),
            ("inlet_node_id", self.inlet_node_id),
            ("outlet_node_id", self.outlet_node_id),
        ):
            if not isinstance(value, str):
                raise TypeError(
                    f"ScenarioBranchSpec.{field_name} must be a str; "
                    f"got {type(value).__name__!r}"
                )
            if not value.strip():
                raise ValueError(
                    f"ScenarioBranchSpec.{field_name} must be non-empty; " f"got {value!r}"
                )
        component_ids = self.component_ids
        if not isinstance(component_ids, tuple):
            object.__setattr__(self, "component_ids", tuple(component_ids))
            component_ids = self.component_ids
        if not component_ids:
            raise ValueError("ScenarioBranchSpec.component_ids must be non-empty")
        seen_component_ids: dict[str, int] = {}
        for i, cid in enumerate(component_ids):
            if not isinstance(cid, str):
                raise TypeError(
                    f"ScenarioBranchSpec.component_ids[{i}] must be a str; "
                    f"got {type(cid).__name__!r}"
                )
            if not cid.strip():
                raise ValueError(
                    f"ScenarioBranchSpec.component_ids[{i}] must be non-empty; " f"got {cid!r}"
                )
            if cid in seen_component_ids:
                raise ValueError(
                    "ScenarioBranchSpec.component_ids contains duplicate component ID "
                    f"{cid!r} at indices {seen_component_ids[cid]} and {i}"
                )
            seen_component_ids[cid] = i
        if self.inlet_node_id == self.outlet_node_id:
            raise ValueError(
                "ScenarioBranchSpec.inlet_node_id and outlet_node_id must differ; "
                f"both are {self.inlet_node_id!r}"
            )
        md = self.metadata
        if md is not None:
            if not isinstance(md, Mapping):
                raise TypeError(
                    "ScenarioBranchSpec.metadata must be a Mapping or None; "
                    f"got {type(md).__name__!r}"
                )
            object.__setattr__(self, "metadata", MappingProxyType(dict(md)))


# ---------------------------------------------------------------------------
# ConfigurableScenarioSpec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfigurableScenarioSpec:
    """Frozen, validated configurable scenario specification.

    Validates uniqueness, cross-references, and structural consistency of all
    declared components, nodes, connections, and branches at construction time.

    No physics, no property values, no residual formulas, no closure inference.

    Fields
    ------
    scenario_id : str                             — non-empty scenario identifier
    components  : tuple[ScenarioComponentSpec, ...] — ordered component declarations
    nodes       : tuple[ScenarioNodeSpec, ...]    — ordered node declarations
    connections : tuple[ScenarioConnectionSpec, ...] — ordered connection declarations
    branches    : tuple[ScenarioBranchSpec, ...]  — optional branch declarations
    metadata    : Mapping[str, object] | None     — optional; defensively copied
    """

    scenario_id: str
    components: tuple[ScenarioComponentSpec, ...]
    nodes: tuple[ScenarioNodeSpec, ...]
    connections: tuple[ScenarioConnectionSpec, ...]
    branches: tuple[ScenarioBranchSpec, ...] = ()
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        # Validate scenario_id.
        if not isinstance(self.scenario_id, str):
            raise TypeError(
                "ConfigurableScenarioSpec.scenario_id must be a str; "
                f"got {type(self.scenario_id).__name__!r}"
            )
        if not self.scenario_id.strip():
            raise ValueError(
                "ConfigurableScenarioSpec.scenario_id must be non-empty; "
                f"got {self.scenario_id!r}"
            )

        # Normalize sequences to tuples.
        components = self.components
        if not isinstance(components, tuple):
            object.__setattr__(self, "components", tuple(components))
            components = self.components
        nodes = self.nodes
        if not isinstance(nodes, tuple):
            object.__setattr__(self, "nodes", tuple(nodes))
            nodes = self.nodes
        connections = self.connections
        if not isinstance(connections, tuple):
            object.__setattr__(self, "connections", tuple(connections))
            connections = self.connections
        branches = self.branches
        if not isinstance(branches, tuple):
            object.__setattr__(self, "branches", tuple(branches))
            branches = self.branches

        # Validate element types.
        for i, comp in enumerate(components):
            if not isinstance(comp, ScenarioComponentSpec):
                raise TypeError(
                    f"ConfigurableScenarioSpec.components[{i}] must be a "
                    "ScenarioComponentSpec; "
                    f"got {type(comp).__name__!r}"
                )
        for i, node in enumerate(nodes):
            if not isinstance(node, ScenarioNodeSpec):
                raise TypeError(
                    f"ConfigurableScenarioSpec.nodes[{i}] must be a "
                    "ScenarioNodeSpec; "
                    f"got {type(node).__name__!r}"
                )
        for i, conn in enumerate(connections):
            if not isinstance(conn, ScenarioConnectionSpec):
                raise TypeError(
                    f"ConfigurableScenarioSpec.connections[{i}] must be a "
                    "ScenarioConnectionSpec; "
                    f"got {type(conn).__name__!r}"
                )
        for i, branch in enumerate(branches):
            if not isinstance(branch, ScenarioBranchSpec):
                raise TypeError(
                    f"ConfigurableScenarioSpec.branches[{i}] must be a "
                    "ScenarioBranchSpec; "
                    f"got {type(branch).__name__!r}"
                )

        # Validate component ID uniqueness and build known-set.
        known_component_ids: dict[str, int] = {}
        for i, comp in enumerate(components):
            cid = comp.component_id
            if cid in known_component_ids:
                raise ValueError(
                    "ConfigurableScenarioSpec.components: duplicate component_id "
                    f"{cid!r} at indices {known_component_ids[cid]} and {i}"
                )
            known_component_ids[cid] = i

        # Validate node ID uniqueness and build known-set.
        known_node_ids: dict[str, int] = {}
        for i, node in enumerate(nodes):
            nid = node.node_id
            if nid in known_node_ids:
                raise ValueError(
                    "ConfigurableScenarioSpec.nodes: duplicate node_id "
                    f"{nid!r} at indices {known_node_ids[nid]} and {i}"
                )
            known_node_ids[nid] = i

        # Validate connections reference known components/nodes; no duplicate component_id.
        seen_connection_cids: dict[str, int] = {}
        for i, conn in enumerate(connections):
            cid = conn.component_id
            if cid not in known_component_ids:
                raise ValueError(
                    f"ConfigurableScenarioSpec.connections[{i}].component_id "
                    f"{cid!r} does not reference a declared component"
                )
            if cid in seen_connection_cids:
                raise ValueError(
                    "ConfigurableScenarioSpec.connections: duplicate component_id "
                    f"{cid!r} at connection indices {seen_connection_cids[cid]} and {i}"
                )
            seen_connection_cids[cid] = i
            inlet = conn.inlet_node_id
            if inlet not in known_node_ids:
                raise ValueError(
                    f"ConfigurableScenarioSpec.connections[{i}].inlet_node_id "
                    f"{inlet!r} does not reference a declared node"
                )
            outlet = conn.outlet_node_id
            if outlet not in known_node_ids:
                raise ValueError(
                    f"ConfigurableScenarioSpec.connections[{i}].outlet_node_id "
                    f"{outlet!r} does not reference a declared node"
                )
        missing_connection_cids = set(known_component_ids) - set(seen_connection_cids)
        if missing_connection_cids:
            raise ValueError(
                "ConfigurableScenarioSpec.connections: every declared component must "
                "have exactly one connection; missing component IDs "
                f"{sorted(missing_connection_cids)!r}"
            )

        # Validate branches: unique IDs; referenced nodes/components exist.
        seen_branch_ids: dict[str, int] = {}
        for i, branch in enumerate(branches):
            bid = branch.branch_id
            if bid in seen_branch_ids:
                raise ValueError(
                    "ConfigurableScenarioSpec.branches: duplicate branch_id "
                    f"{bid!r} at indices {seen_branch_ids[bid]} and {i}"
                )
            seen_branch_ids[bid] = i
            if branch.inlet_node_id not in known_node_ids:
                raise ValueError(
                    f"ConfigurableScenarioSpec.branches[{i}].inlet_node_id "
                    f"{branch.inlet_node_id!r} does not reference a declared node"
                )
            if branch.outlet_node_id not in known_node_ids:
                raise ValueError(
                    f"ConfigurableScenarioSpec.branches[{i}].outlet_node_id "
                    f"{branch.outlet_node_id!r} does not reference a declared node"
                )
            for j, cid in enumerate(branch.component_ids):
                if cid not in known_component_ids:
                    raise ValueError(
                        f"ConfigurableScenarioSpec.branches[{i}].component_ids[{j}] "
                        f"{cid!r} does not reference a declared component"
                    )
            branch_connections = [
                connections[seen_connection_cids[cid]] for cid in branch.component_ids
            ]
            expected_inlet = branch.inlet_node_id
            for j, conn in enumerate(branch_connections):
                if conn.inlet_node_id != expected_inlet:
                    raise ValueError(
                        f"ConfigurableScenarioSpec.branches[{i}].component_ids[{j}] "
                        f"{conn.component_id!r} does not continue the declared branch "
                        f"path from node {expected_inlet!r}"
                    )
                expected_inlet = conn.outlet_node_id
            if expected_inlet != branch.outlet_node_id:
                raise ValueError(
                    f"ConfigurableScenarioSpec.branches[{i}] component path ends at "
                    f"{expected_inlet!r}, not declared outlet_node_id "
                    f"{branch.outlet_node_id!r}"
                )

        # Defensive metadata copy.
        md = self.metadata
        if md is not None:
            if not isinstance(md, Mapping):
                raise TypeError(
                    "ConfigurableScenarioSpec.metadata must be a Mapping or None; "
                    f"got {type(md).__name__!r}"
                )
            object.__setattr__(self, "metadata", MappingProxyType(dict(md)))


# ---------------------------------------------------------------------------
# ConfigurableScenarioBuildResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfigurableScenarioBuildResult:
    """Immutable build result from build_configurable_scenario.

    Carries all structural declarations derived from a ConfigurableScenarioSpec.

    This object is declaration-only.  It does not contain FluidState,
    SystemState, physical state values, property backend objects, or
    production component objects.

    Fields
    ------
    spec            : ConfigurableScenarioSpec            — validated spec
    graph           : NetworkGraph                        — built from spec
    assembly        : NetworkResidualAssembly             — from graph
    binding_context : NetworkBindingContext               — from graph + assembly
    unknown_names   : tuple[str, ...]                     — deterministic names
    residual_names  : tuple[str, ...]                     — deterministic names
    component_ids   : tuple[ComponentInstanceId, ...]     — in spec insertion order
    node_ids        : tuple[GraphNodeId, ...]             — in spec insertion order
    branch_ids      : tuple[str, ...]                     — in spec order
    limitations     : tuple[str, ...]                     — what this does NOT provide
    metadata        : Mapping[str, object] | None         — optional; defensively copied
    """

    spec: ConfigurableScenarioSpec
    graph: NetworkGraph
    assembly: NetworkResidualAssembly
    binding_context: NetworkBindingContext
    unknown_names: tuple[str, ...]
    residual_names: tuple[str, ...]
    component_ids: tuple[ComponentInstanceId, ...]
    node_ids: tuple[GraphNodeId, ...]
    branch_ids: tuple[str, ...]
    limitations: tuple[str, ...]
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.spec, ConfigurableScenarioSpec):
            raise TypeError(
                "ConfigurableScenarioBuildResult.spec must be a "
                "ConfigurableScenarioSpec; "
                f"got {type(self.spec).__name__!r}"
            )
        if not isinstance(self.graph, NetworkGraph):
            raise TypeError(
                "ConfigurableScenarioBuildResult.graph must be a NetworkGraph; "
                f"got {type(self.graph).__name__!r}"
            )
        if not isinstance(self.assembly, NetworkResidualAssembly):
            raise TypeError(
                "ConfigurableScenarioBuildResult.assembly must be a "
                "NetworkResidualAssembly; "
                f"got {type(self.assembly).__name__!r}"
            )
        if not isinstance(self.binding_context, NetworkBindingContext):
            raise TypeError(
                "ConfigurableScenarioBuildResult.binding_context must be a "
                "NetworkBindingContext; "
                f"got {type(self.binding_context).__name__!r}"
            )
        for seq_name, seq_value in (
            ("unknown_names", self.unknown_names),
            ("residual_names", self.residual_names),
            ("branch_ids", self.branch_ids),
            ("limitations", self.limitations),
        ):
            if not isinstance(seq_value, tuple):
                raise TypeError(
                    f"ConfigurableScenarioBuildResult.{seq_name} must be a tuple; "
                    f"got {type(seq_value).__name__!r}"
                )
        for seq_name, seq_value in (
            ("component_ids", self.component_ids),
            ("node_ids", self.node_ids),
        ):
            if not isinstance(seq_value, tuple):
                raise TypeError(
                    f"ConfigurableScenarioBuildResult.{seq_name} must be a tuple; "
                    f"got {type(seq_value).__name__!r}"
                )
        md = self.metadata
        if md is not None:
            if not isinstance(md, Mapping):
                raise TypeError(
                    "ConfigurableScenarioBuildResult.metadata must be a Mapping or "
                    f"None; got {type(md).__name__!r}"
                )
            object.__setattr__(self, "metadata", MappingProxyType(dict(md)))


# ---------------------------------------------------------------------------
# build_configurable_scenario
# ---------------------------------------------------------------------------


def build_configurable_scenario(
    spec: ConfigurableScenarioSpec,
    *,
    require_closed_loop: bool = False,
    metadata: Mapping[str, object] | None = None,
) -> ConfigurableScenarioBuildResult:
    """Build a deterministic configurable scenario declaration from a spec.

    Converts a ConfigurableScenarioSpec into a NetworkGraph, a
    NetworkResidualAssembly, and a NetworkBindingContext using the existing
    graph/assembly/binding infrastructure.

    Unknown naming convention (inherited from residual_assembly):
      mdot:<component_id>       for mass-flow unknowns (component insertion order)
      P:<node_id>               for pressure unknowns (node insertion order)

    Residual naming convention:
      mass_balance:<node_id>    for mass-balance residuals (node insertion order)
      pressure_drop:<component_id> for pressure-drop residuals (component order)

    Component insertion order follows spec.components order.
    Node insertion order follows spec.nodes order.

    This function does not evaluate residuals, call closures, infer physics
    from roles, execute production components, or solve.

    Parameters
    ----------
    spec               : ConfigurableScenarioSpec — validated scenario spec
    require_closed_loop : bool                    — pass to assemble_network_residuals
    metadata           : Mapping | None           — optional result metadata

    Returns
    -------
    ConfigurableScenarioBuildResult — immutable build result

    Raises
    ------
    TypeError
        If spec is not a ConfigurableScenarioSpec.
        If metadata is not a Mapping or None.
    ValueError
        If require_closed_loop=True and the topology is not a single closed loop.
    """
    if not isinstance(spec, ConfigurableScenarioSpec):
        raise TypeError(
            "build_configurable_scenario: spec must be a ConfigurableScenarioSpec; "
            f"got {type(spec).__name__!r}"
        )
    if metadata is not None and not isinstance(metadata, Mapping):
        raise TypeError(
            "build_configurable_scenario: metadata must be a Mapping or None; "
            f"got {type(metadata).__name__!r}"
        )

    # Build lookup map from component_id to its connection spec.
    connection_map: dict[str, ScenarioConnectionSpec] = {
        conn.component_id: conn for conn in spec.connections
    }

    # Build typed node objects in spec insertion order.
    node_id_objects: dict[str, GraphNodeId] = {
        node.node_id: GraphNodeId(node.node_id) for node in spec.nodes
    }
    graph_nodes: list[GraphNode] = [GraphNode(node_id_objects[node.node_id]) for node in spec.nodes]

    # Build typed component ID objects in spec insertion order.
    component_id_objects: dict[str, ComponentInstanceId] = {
        comp.component_id: ComponentInstanceId(comp.component_id) for comp in spec.components
    }

    # Build ComponentInstance list in component spec order.
    graph_instances: list[ComponentInstance] = []
    for comp in spec.components:
        cid = comp.component_id
        conn = connection_map[cid]
        graph_instances.append(
            ComponentInstance(
                instance_id=component_id_objects[cid],
                component_type=comp.role.value,
                inlet_node=node_id_objects[conn.inlet_node_id],
                outlet_node=node_id_objects[conn.outlet_node_id],
            )
        )

    # Build NetworkGraph.
    graph = NetworkGraph(nodes=graph_nodes, instances=graph_instances)

    # Assemble residuals.
    assembly = assemble_network_residuals(
        graph,
        require_closed_loop=require_closed_loop,
        include_pressure_unknowns=True,
        include_pressure_residuals=True,
    )

    # Extract unknown and residual names (deterministic from graph insertion order).
    unknown_names: tuple[str, ...] = assembly.unknowns.names()
    residual_names: tuple[str, ...] = assembly.residuals.names()

    # Build component bindings (one per component, in spec order).
    bindings = ComponentBindingSet(
        bindings=tuple(
            ComponentBinding(
                instance_id=component_id_objects[comp.component_id],
                binding_name=comp.component_id,
            )
            for comp in spec.components
        )
    )

    # Build state map using deterministic naming convention.
    state_map = ComponentStateMap(
        unknown_to_component={
            f"mdot:{comp.component_id}": component_id_objects[comp.component_id]
            for comp in spec.components
        },
        unknown_to_node={f"P:{node.node_id}": node_id_objects[node.node_id] for node in spec.nodes},
        residual_to_node={
            f"mass_balance:{node.node_id}": node_id_objects[node.node_id] for node in spec.nodes
        },
        residual_to_component={
            f"pressure_drop:{comp.component_id}": component_id_objects[comp.component_id]
            for comp in spec.components
        },
    )

    # Build binding context (validates coverage and ID references).
    binding_context = build_binding_context(
        graph,
        assembly,
        bindings,
        state_map,
        metadata=None,
    )

    # Build ordered result tuples.
    component_ids: tuple[ComponentInstanceId, ...] = tuple(
        component_id_objects[comp.component_id] for comp in spec.components
    )
    node_ids: tuple[GraphNodeId, ...] = tuple(node_id_objects[node.node_id] for node in spec.nodes)
    branch_ids: tuple[str, ...] = tuple(b.branch_id for b in spec.branches)

    return ConfigurableScenarioBuildResult(
        spec=spec,
        graph=graph,
        assembly=assembly,
        binding_context=binding_context,
        unknown_names=unknown_names,
        residual_names=residual_names,
        component_ids=component_ids,
        node_ids=node_ids,
        branch_ids=branch_ids,
        limitations=_LIMITATIONS,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# build_configurable_scenario_report
# ---------------------------------------------------------------------------


def build_configurable_scenario_report(
    result: ConfigurableScenarioBuildResult,
) -> dict[str, object]:
    """Build a plain serializable report for a ConfigurableScenarioBuildResult.

    Returns a plain dict with only JSON-serializable values (str, int, bool,
    list, dict, None).  No file writes.  No pandas.  No physical state values.

    The report includes ``status: "declaration_only"`` and ``no_solve: True``
    to document that no physical equations were evaluated or solved.

    Parameters
    ----------
    result : ConfigurableScenarioBuildResult

    Returns
    -------
    dict[str, object] — JSON-serializable report

    Raises
    ------
    TypeError
        If result is not a ConfigurableScenarioBuildResult.
    """
    if not isinstance(result, ConfigurableScenarioBuildResult):
        raise TypeError(
            "build_configurable_scenario_report: result must be a "
            "ConfigurableScenarioBuildResult; "
            f"got {type(result).__name__!r}"
        )
    spec = result.spec
    report: dict[str, object] = {
        "scenario_id": spec.scenario_id,
        "status": "declaration_only",
        "no_solve": True,
        "component_count": len(spec.components),
        "node_count": len(spec.nodes),
        "connection_count": len(spec.connections),
        "branch_count": len(spec.branches),
        "component_ids": [comp.component_id for comp in spec.components],
        "node_ids": [node.node_id for node in spec.nodes],
        "branch_ids": list(result.branch_ids),
        "component_roles": {comp.component_id: comp.role.value for comp in spec.components},
        "unknown_count": result.assembly.unknowns.count(),
        "unknown_names": list(result.unknown_names),
        "residual_count": result.assembly.residuals.count(),
        "residual_names": list(result.residual_names),
        "limitations": list(result.limitations),
        "closure_domains_available_later": [
            "hydraulic (Block 15D-A)",
            "thermal (Block 15D-B)",
        ],
    }
    # Verify JSON-serializability before returning.
    json.dumps(report)
    return report
