"""Topology declaration objects — Block 15C.1 and Block 15C.3.

Provides symbolic declaration objects for junction/manifold topology roles
and valve/local pressure-loss elements.

This is a declaration-only module.  It does not implement physics, pressure-loss
equations, valve equations, flow-split laws, energy balance equations, or any
correlation/property calls.

15C.1 — Junction / Manifold Declaration Foundation
    JunctionRole         — SPLIT or MERGE role enum
    JunctionDeclaration  — symbolic split/merge junction with branch labels
    ManifoldDeclaration  — named manifold with explicit branch port nodes

15C.3 — Valve / Local Pressure-Loss Element Declaration
    ValveDeclaration     — symbolic valve element (inlet node, outlet node,
                           optional symbolic residual name)

Architecture constraints enforced here
---------------------------------------
MUST NOT import mpl_sim.components, mpl_sim.properties, mpl_sim.correlations,
    mpl_sim.calibration, mpl_sim.hx_models, mpl_sim.closed_loop, mpl_sim.solvers.
MUST NOT import CoolProp or any property engine.
MUST NOT store FluidState, SystemState, mdot values, pressure values, or
    enthalpy values.
MUST NOT call contribute(...) or define a method named contribute.
MUST NOT call PropertyBackend, CorrelationRegistry, or HeatExchangerModelRegistry.
MUST NOT implement solve(network) or NetworkGraph.solve().
MUST NOT execute production component physics.
MUST NOT store pressure-loss laws, Kv/Cv coefficients, or valve equations.
MUST NOT infer physics from component_type.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from mpl_sim.network.graph import ComponentInstanceId, GraphNodeId

# ---------------------------------------------------------------------------
# 15C.1 — Junction role
# ---------------------------------------------------------------------------


class JunctionRole(enum.Enum):
    """Role of a junction or manifold in the network topology.

    SPLIT : one common inlet node feeds multiple branch outlet nodes.
    MERGE : multiple branch inlet nodes feed one common outlet node.

    This is a symbolic label only.  No mass-flow split laws, no pressure
    equations, and no energy balance are attached to this enum.
    """

    SPLIT = "split"
    MERGE = "merge"


# ---------------------------------------------------------------------------
# 15C.1 — JunctionDeclaration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class JunctionDeclaration:
    """Symbolic declaration of a split or merge junction.

    Carries a junction identifier, a role (SPLIT or MERGE), and explicit
    symbolic branch labels.  This is a topology annotation only.

    Fields
    ------
    junction_id   : non-empty string identifier for this junction
    role          : JunctionRole (SPLIT or MERGE)
    branch_labels : at least two unique non-empty strings naming the branches
    metadata      : optional caller-supplied metadata; defensively copied

    Raises
    ------
    TypeError
        If junction_id is not a str.
        If role is not a JunctionRole.
        If branch_labels is not a sequence of str.
        If metadata is not a Mapping (when supplied).
    ValueError
        If junction_id is empty or whitespace-only.
        If fewer than two branch labels are supplied.
        If any branch label is empty or whitespace-only.
        If any two branch labels are duplicated.
    """

    junction_id: str
    role: JunctionRole
    branch_labels: tuple[str, ...]
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.junction_id, str):
            raise TypeError(
                "JunctionDeclaration.junction_id must be a str; "
                f"got {type(self.junction_id).__name__!r}"
            )
        if not self.junction_id.strip():
            raise ValueError(
                "JunctionDeclaration.junction_id must be non-empty; " f"got {self.junction_id!r}"
            )
        if not isinstance(self.role, JunctionRole):
            raise TypeError(
                "JunctionDeclaration.role must be a JunctionRole; "
                f"got {type(self.role).__name__!r}"
            )
        # Normalize branch_labels to tuple and validate.
        labels = self.branch_labels
        if not isinstance(labels, tuple):
            try:
                labels = tuple(labels)
            except TypeError:
                raise TypeError(
                    "JunctionDeclaration.branch_labels must be a sequence of str; "
                    f"got {type(self.branch_labels).__name__!r}"
                )
            object.__setattr__(self, "branch_labels", labels)
        if len(labels) < 2:
            raise ValueError(
                "JunctionDeclaration.branch_labels must have at least two entries; "
                f"got {len(labels)}"
            )
        for i, lbl in enumerate(labels):
            if not isinstance(lbl, str):
                raise TypeError(
                    f"JunctionDeclaration.branch_labels[{i}] must be a str; "
                    f"got {type(lbl).__name__!r}"
                )
            if not lbl.strip():
                raise ValueError(
                    f"JunctionDeclaration.branch_labels[{i}] must be non-empty; " f"got {lbl!r}"
                )
        seen: set[str] = set()
        for lbl in labels:
            if lbl in seen:
                raise ValueError(
                    "JunctionDeclaration.branch_labels must all be distinct; "
                    f"duplicate label: {lbl!r}"
                )
            seen.add(lbl)
        md = self.metadata
        if md is not None:
            if not isinstance(md, Mapping):
                raise TypeError(
                    "JunctionDeclaration.metadata must be a Mapping or None; "
                    f"got {type(md).__name__!r}"
                )
            object.__setattr__(self, "metadata", MappingProxyType(dict(md)))


# ---------------------------------------------------------------------------
# 15C.1 — ManifoldDeclaration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ManifoldDeclaration:
    """Symbolic declaration of a named manifold with explicit branch port nodes.

    A manifold is a multi-port junction:
      SPLIT role : ``common_node`` is the single inlet; ``branch_nodes`` are the outlets.
      MERGE role : ``branch_nodes`` are the inlets; ``common_node`` is the single outlet.

    This is a topology annotation only.  No mass-flow split laws, pressure-loss
    equations, or energy balance equations are stored here.

    Fields
    ------
    manifold_id   : non-empty string identifier
    role          : JunctionRole (SPLIT or MERGE)
    common_node   : GraphNodeId of the single-port side
    branch_nodes  : at least two distinct GraphNodeId objects (one per branch port)
    branch_labels : unique non-empty string labels, one per branch node
    metadata      : optional caller-supplied metadata; defensively copied

    Raises
    ------
    TypeError
        If manifold_id is not a str.
        If role is not a JunctionRole.
        If common_node is not a GraphNodeId.
        If any entry in branch_nodes is not a GraphNodeId.
        If any entry in branch_labels is not a str.
        If metadata is not a Mapping (when supplied).
    ValueError
        If manifold_id is empty or whitespace-only.
        If fewer than two branch nodes are supplied.
        If len(branch_nodes) != len(branch_labels).
        If any branch label is empty or whitespace-only.
        If any two branch labels are duplicated.
        If any two branch node IDs are duplicated.
        If common_node appears in branch_nodes.
    """

    manifold_id: str
    role: JunctionRole
    common_node: GraphNodeId
    branch_nodes: tuple[GraphNodeId, ...]
    branch_labels: tuple[str, ...]
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.manifold_id, str):
            raise TypeError(
                "ManifoldDeclaration.manifold_id must be a str; "
                f"got {type(self.manifold_id).__name__!r}"
            )
        if not self.manifold_id.strip():
            raise ValueError(
                "ManifoldDeclaration.manifold_id must be non-empty; " f"got {self.manifold_id!r}"
            )
        if not isinstance(self.role, JunctionRole):
            raise TypeError(
                "ManifoldDeclaration.role must be a JunctionRole; "
                f"got {type(self.role).__name__!r}"
            )
        if not isinstance(self.common_node, GraphNodeId):
            raise TypeError(
                "ManifoldDeclaration.common_node must be a GraphNodeId; "
                f"got {type(self.common_node).__name__!r}"
            )
        # Normalize branch_nodes to tuple.
        bnodes = self.branch_nodes
        if not isinstance(bnodes, tuple):
            try:
                bnodes = tuple(bnodes)
            except TypeError:
                raise TypeError(
                    "ManifoldDeclaration.branch_nodes must be a sequence of GraphNodeId; "
                    f"got {type(self.branch_nodes).__name__!r}"
                )
            object.__setattr__(self, "branch_nodes", bnodes)
        if len(bnodes) < 2:
            raise ValueError(
                "ManifoldDeclaration.branch_nodes must have at least two entries; "
                f"got {len(bnodes)}"
            )
        for i, bn in enumerate(bnodes):
            if not isinstance(bn, GraphNodeId):
                raise TypeError(
                    f"ManifoldDeclaration.branch_nodes[{i}] must be a GraphNodeId; "
                    f"got {type(bn).__name__!r}"
                )
        # Normalize branch_labels to tuple.
        blabels = self.branch_labels
        if not isinstance(blabels, tuple):
            try:
                blabels = tuple(blabels)
            except TypeError:
                raise TypeError(
                    "ManifoldDeclaration.branch_labels must be a sequence of str; "
                    f"got {type(self.branch_labels).__name__!r}"
                )
            object.__setattr__(self, "branch_labels", blabels)
        if len(blabels) != len(bnodes):
            raise ValueError(
                "ManifoldDeclaration.branch_labels and branch_nodes must have "
                f"the same length; got {len(blabels)} labels and {len(bnodes)} nodes"
            )
        for i, lbl in enumerate(blabels):
            if not isinstance(lbl, str):
                raise TypeError(
                    f"ManifoldDeclaration.branch_labels[{i}] must be a str; "
                    f"got {type(lbl).__name__!r}"
                )
            if not lbl.strip():
                raise ValueError(
                    f"ManifoldDeclaration.branch_labels[{i}] must be non-empty; " f"got {lbl!r}"
                )
        # Validate duplicate branch labels.
        seen_labels: set[str] = set()
        for lbl in blabels:
            if lbl in seen_labels:
                raise ValueError(
                    "ManifoldDeclaration.branch_labels must all be distinct; "
                    f"duplicate label: {lbl!r}"
                )
            seen_labels.add(lbl)
        # Validate duplicate branch node IDs.
        seen_node_ids: set[str] = set()
        for bn in bnodes:
            nid = bn.value
            if nid in seen_node_ids:
                raise ValueError(
                    "ManifoldDeclaration.branch_nodes must all have distinct IDs; "
                    f"duplicate node ID: {nid!r}"
                )
            seen_node_ids.add(nid)
        # common_node must not appear in branch_nodes.
        if self.common_node.value in seen_node_ids:
            raise ValueError(
                "ManifoldDeclaration.common_node must not appear in branch_nodes; "
                f"common_node ID {self.common_node.value!r} is duplicated"
            )
        md = self.metadata
        if md is not None:
            if not isinstance(md, Mapping):
                raise TypeError(
                    "ManifoldDeclaration.metadata must be a Mapping or None; "
                    f"got {type(md).__name__!r}"
                )
            object.__setattr__(self, "metadata", MappingProxyType(dict(md)))


# ---------------------------------------------------------------------------
# 15C.3 — ValveDeclaration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValveDeclaration:
    """Symbolic declaration of a valve or local pressure-loss element.

    Carries connectivity (inlet node, outlet node) and an optional symbolic
    residual name.  This is a topology annotation only.

    No pressure-loss equation, Kv/Cv coefficient, opening command, flow
    coefficient, or property call is stored here.  Physical valve/local-loss
    residuals belong to Block 15C-B or later.

    Fields
    ------
    valve_id      : ComponentInstanceId identifying this valve instance
    inlet_node    : upstream graph node
    outlet_node   : downstream graph node (must differ from inlet_node)
    residual_name : optional symbolic residual name string; no equation attached
    metadata      : optional caller-supplied metadata; defensively copied

    Raises
    ------
    TypeError
        If valve_id is not a ComponentInstanceId.
        If inlet_node is not a GraphNodeId.
        If outlet_node is not a GraphNodeId.
        If residual_name is not a str (when supplied).
        If metadata is not a Mapping (when supplied).
    ValueError
        If inlet_node equals outlet_node.
        If residual_name is empty or whitespace-only (when supplied).
    """

    valve_id: ComponentInstanceId
    inlet_node: GraphNodeId
    outlet_node: GraphNodeId
    residual_name: str | None = None
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.valve_id, ComponentInstanceId):
            raise TypeError(
                "ValveDeclaration.valve_id must be a ComponentInstanceId; "
                f"got {type(self.valve_id).__name__!r}"
            )
        if not isinstance(self.inlet_node, GraphNodeId):
            raise TypeError(
                "ValveDeclaration.inlet_node must be a GraphNodeId; "
                f"got {type(self.inlet_node).__name__!r}"
            )
        if not isinstance(self.outlet_node, GraphNodeId):
            raise TypeError(
                "ValveDeclaration.outlet_node must be a GraphNodeId; "
                f"got {type(self.outlet_node).__name__!r}"
            )
        if self.inlet_node == self.outlet_node:
            raise ValueError(
                "ValveDeclaration.inlet_node and outlet_node must differ; "
                f"both are {self.inlet_node.value!r}"
            )
        rn = self.residual_name
        if rn is not None:
            if not isinstance(rn, str):
                raise TypeError(
                    "ValveDeclaration.residual_name must be a str or None; "
                    f"got {type(rn).__name__!r}"
                )
            if not rn.strip():
                raise ValueError(
                    "ValveDeclaration.residual_name must be non-empty when supplied; " f"got {rn!r}"
                )
        md = self.metadata
        if md is not None:
            if not isinstance(md, Mapping):
                raise TypeError(
                    "ValveDeclaration.metadata must be a Mapping or None; "
                    f"got {type(md).__name__!r}"
                )
            object.__setattr__(self, "metadata", MappingProxyType(dict(md)))
