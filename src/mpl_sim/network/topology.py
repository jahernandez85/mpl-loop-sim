"""Network topology primitives -- Phase 7A / 10I.

Identity primitives (NetworkId, NodeId, ConnectionId) and the immutable
topology objects (NetworkNode, NetworkConnection, NetworkTopology).

Phase 10I adds:
- PressureReferenceWiring: identity-only pointer to an ACCUMULATOR-kind
  component that sets the system pressure reference.  No pressure value is
  stored; only component_id and port_name are recorded.
- NetworkTopology accepts an optional pressure_references parameter.  When
  supplied, exactly-one-ACCUMULATOR validation is enforced.  When omitted
  (None), the check is skipped for backward compatibility with tests that
  use Pipe-only networks.

Architecture constraints:
- MUST NOT import from solvers/, properties/, correlations/, calibration/.
- MUST NOT import CoolProp.
- MUST NOT compute physics, call correlations, call property backends.
- Components are inspected for structural identity only (component_id, kind,
  ports); no physical evaluation methods are called.
- SystemState is never stored, allocated, or mutated here.
- Ports retain connectivity-only semantics; no thermodynamic values are added.
- No pressure value is stored in PressureReferenceWiring.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from mpl_sim.components.base import Component, ComponentKind
from mpl_sim.core.port import PortId

# ---------------------------------------------------------------------------
# Phase 10I -- PressureReferenceWiring
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PressureReferenceWiring:
    """Identity-only pointer to the accumulator that sets the pressure reference.

    Carries only the component id and port name -- no pressure value.
    The Network is responsible for ensuring the referenced component is of
    kind ACCUMULATOR and is present in the topology.

    Fields:
        component_id : name of the ACCUMULATOR-kind component
        port_name    : name of the port on that component
    """

    component_id: str
    port_name: str

    def __post_init__(self) -> None:
        if not self.component_id:
            raise ValueError("PressureReferenceWiring.component_id must be non-empty")
        if not self.port_name:
            raise ValueError("PressureReferenceWiring.port_name must be non-empty")


# ---------------------------------------------------------------------------
# Identity primitives
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NetworkId:
    """Immutable, hashable identity for a network."""

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("NetworkId.value must be non-empty")


@dataclass(frozen=True)
class NodeId:
    """Immutable, hashable identity for a topology node."""

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("NodeId.value must be non-empty")


@dataclass(frozen=True)
class ConnectionId:
    """Immutable, hashable identity for a topology connection."""

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("ConnectionId.value must be non-empty")


# ---------------------------------------------------------------------------
# Topology data objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NetworkNode:
    """Immutable node in the network topology graph.

    Represents one component's structural presence in the topology.
    Carries no thermodynamic values (no P, h, mdot, T, x, rho, mu, …).
    """

    node_id: NodeId
    component_id: str  # component name string
    component_kind: ComponentKind
    port_ids: tuple[PortId, ...]


@dataclass(frozen=True)
class NetworkConnection:
    """Immutable directed-edge declaration in the topology graph.

    Carries no thermodynamic values.  The 'from'/'to' labels are
    conventions; the architecture permits reverse flow (roles are
    annotations, not hard constraints — INTERFACE_SPEC §4.1).

    Fields:
        connection_id  : unique identifier for this connection
        from_component : name of the source component
        from_port      : port name on the source component
        to_component   : name of the destination component
        to_port        : port name on the destination component
        label          : optional human-readable annotation
    """

    connection_id: ConnectionId
    from_component: str
    from_port: str
    to_component: str
    to_port: str
    label: str | None = None


# ---------------------------------------------------------------------------
# NetworkTopology
# ---------------------------------------------------------------------------


class NetworkTopology:
    """Immutable assembly of component and connection declarations.

    Assembles Component objects into a validated, queryable topology graph.
    Components are inspected for structural identity (component_id, kind,
    ports) and then released -- the topology stores only immutable node and
    connection data objects after construction.

    Does NOT:
    - store SystemState or allocate solver vectors
    - call any physical evaluation method on components
    - import or call solvers, properties, correlations, or calibration
    - import CoolProp
    - mutate components
    - store pressure values in pressure_references

    Parameters
    ----------
    network_id          : NetworkId
    components          : Component objects (inspected structurally; not mutated)
    connections         : NetworkConnection declarations
    pressure_references : optional sequence of PressureReferenceWiring.
                          When supplied, exactly one entry must reference an
                          ACCUMULATOR-kind component in the topology.
                          When None (default), pressure-reference validation
                          is skipped (backward compatible with Pipe-only tests).

    Raises
    ------
    ValueError
        On duplicate component ids, invalid connection references,
        incompatible port roles, self-connections, over-connected ports,
        or invalid pressure-reference wiring (when supplied).
    """

    def __init__(
        self,
        network_id: NetworkId,
        components: Sequence[Component],
        connections: Sequence[NetworkConnection],
        pressure_references: Sequence[PressureReferenceWiring] | None = None,
    ) -> None:
        # Snapshot inputs so later mutations to source lists have no effect.
        comp_list: list[Component] = list(components)
        conn_list: list[NetworkConnection] = list(connections)
        pref_list: list[PressureReferenceWiring] = (
            list(pressure_references) if pressure_references is not None else []
        )

        # Build component map -- catches duplicate component ids immediately.
        comp_map: dict[str, Component] = {}
        for comp in comp_list:
            # All concrete Component implementations carry component_id as a
            # frozen dataclass field (Phase 6A contract).
            cid: str = comp.component_id.name  # type: ignore[attr-defined]
            if cid in comp_map:
                raise ValueError(f"Duplicate component id: {cid!r}")
            comp_map[cid] = comp

        # Full structural validation (late import breaks the circular dep
        # between topology <-> validation within the same package).
        from mpl_sim.network.validation import validate_topology

        result = validate_topology(
            comp_map,
            conn_list,
            pressure_references=pref_list if pressure_references is not None else None,
        )
        if not result.is_valid:
            errors_str = "; ".join(result.errors)
            raise ValueError(f"Invalid topology: {errors_str}")

        # Build sorted, deterministic node list -- extract immutable data
        # from components so the topology does not hold Component references.
        raw_nodes: list[NetworkNode] = []
        for cid, comp in comp_map.items():
            raw_nodes.append(
                NetworkNode(
                    node_id=NodeId(value=cid),
                    component_id=cid,
                    component_kind=comp.kind(),
                    port_ids=tuple(port.id for port in comp.ports()),
                )
            )
        raw_nodes.sort(key=lambda n: n.component_id)

        # Freeze all internal state before setting _initialized.
        self._network_id = network_id
        self._nodes: tuple[NetworkNode, ...] = tuple(raw_nodes)
        self._connections: tuple[NetworkConnection, ...] = tuple(conn_list)
        self._pressure_references: tuple[PressureReferenceWiring, ...] = tuple(pref_list)
        # Sentinel that makes __setattr__ reject further writes.
        self.__dict__["_initialized"] = True

    def __setattr__(self, name: str, value: object) -> None:
        if self.__dict__.get("_initialized"):
            raise AttributeError("NetworkTopology is immutable after construction")
        super().__setattr__(name, value)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def network_id(self) -> NetworkId:
        return self._network_id

    @property
    def pressure_references(self) -> tuple[PressureReferenceWiring, ...]:
        """Identity-only pressure-reference wirings (empty when not declared)."""
        return self._pressure_references

    # ------------------------------------------------------------------
    # Graph queries
    # ------------------------------------------------------------------

    def nodes(self) -> tuple[NetworkNode, ...]:
        """Deterministic (sorted by component_id) listing of all nodes."""
        return self._nodes

    def connections(self) -> tuple[NetworkConnection, ...]:
        """Insertion-order listing of all connections."""
        return self._connections

    def connections_for_component(self, component_id: str) -> tuple[NetworkConnection, ...]:
        """All connections where component_id appears as from or to."""
        return tuple(
            c
            for c in self._connections
            if c.from_component == component_id or c.to_component == component_id
        )

    def connections_for_port(
        self, component_id: str, port_name: str
    ) -> tuple[NetworkConnection, ...]:
        """All connections involving a specific component port."""
        return tuple(
            c
            for c in self._connections
            if (c.from_component == component_id and c.from_port == port_name)
            or (c.to_component == component_id and c.to_port == port_name)
        )

    def isolated_components(self) -> tuple[str, ...]:
        """Sorted component ids that appear in no connection."""
        connected: set[str] = set()
        for c in self._connections:
            connected.add(c.from_component)
            connected.add(c.to_component)
        return tuple(sorted(n.component_id for n in self._nodes if n.component_id not in connected))
