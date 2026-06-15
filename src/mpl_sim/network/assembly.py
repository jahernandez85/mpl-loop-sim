"""Network state assembly — Phase 7C.

Maps a validated NetworkTopology into a deterministic StateLayout and a
zero-initialized SystemState.  Does not solve physics, call correlations,
call PropertyBackend, or import CoolProp.

Architecture constraints:
- MUST NOT import from solvers/, properties/, correlations/, calibration/.
- MUST NOT import CoolProp.
- MUST NOT compute physics or call component evaluation methods.
- MUST NOT mutate components, topology, geometry, or discretization.
- MUST NOT store FluidState, thermodynamic values, or property results.
- MUST NOT put values on Port or ComponentPort.
- Ports retain connectivity-only semantics; no values are added here.
- SystemState is zero-initialized; no physically meaningful guesses.
- State variable order is fully deterministic: nodes sorted by component_id
  (guaranteed by NetworkTopology), port names sorted alphabetically within
  each node.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from mpl_sim.components.base import Component
from mpl_sim.core.port import PortId
from mpl_sim.core.state import (
    InternalStateHandle,
    PortVariableHandle,
    StateLayout,
    StateVariableId,
    SystemState,
    VariableKind,
)
from mpl_sim.network.topology import NetworkTopology


class NetworkAssembly:
    """Immutable result of assembling a NetworkTopology into a StateLayout.

    Allocates one P/H/MDOT triple per port in the network, ordered
    deterministically: nodes by component_id (ascending), port names
    alphabetically within each node.  Internal state variables (if any) are
    appended after all port variables, ordered by component_id then state name.

    Each port gets its own independent state variables — the solver (Phase 8)
    enforces continuity equations between connected port pairs.  Use
    ``connected_port()`` to find the peer PortId for any connected port.

    Does not contain:
        solver objects, residual functions, property backends, correlations,
        thermodynamic values, or physically meaningful initial guesses.
    """

    def __init__(
        self,
        topology: NetworkTopology,
        layout: StateLayout,
        initial_state: SystemState,
        peer_map: dict[PortId, PortId],
    ) -> None:
        self._topology = topology
        self._layout = layout
        self._initial_state = initial_state
        self._peer_map: dict[PortId, PortId] = dict(peer_map)

    @property
    def topology(self) -> NetworkTopology:
        """The validated topology from which this assembly was built."""
        return self._topology

    @property
    def layout(self) -> StateLayout:
        """Deterministic variable layout for this network."""
        return self._layout

    @property
    def initial_state(self) -> SystemState:
        """Zero-initialized SystemState consistent with layout."""
        return self._initial_state

    def port_handle(self, port_id: PortId) -> PortVariableHandle:
        """Return the PortVariableHandle for ``port_id``.

        Delegates to layout.port_handle; raises KeyError if port absent.
        """
        return self._layout.port_handle(port_id)

    def internal_handle(self, component_id: str, name: str) -> InternalStateHandle:
        """Return the InternalStateHandle for the named internal state.

        Delegates to layout.internal_handle; raises KeyError if absent.
        """
        return self._layout.internal_handle(component_id, name)

    def connected_port(self, port_id: PortId) -> PortId | None:
        """Return the peer PortId if this port is connected, else None."""
        return self._peer_map.get(port_id)


def assemble_network(
    topology: NetworkTopology,
    components: Sequence[Component] | None = None,
) -> NetworkAssembly:
    """Assemble a validated NetworkTopology into a NetworkAssembly.

    Allocates state variables deterministically:
      1. Port variables (P, H, MDOT) for every port in the network, ordered
         by component_id (nodes already sorted by NetworkTopology) then
         port_name (sorted alphabetically within each node).
      2. Internal state variables per component, ordered by component_id then
         state name — only allocated when ``components`` is supplied and the
         component's ``internal_state_names()`` is non-empty.

    The topology is already validated by NetworkTopology.__init__; no further
    structural validation is performed here.

    Connection state sharing:
      Each port receives its own P/H/MDOT variables.  For connected port pairs
      (port_A ↔ port_B), the peer relationship is recorded in the assembly's
      peer map rather than by merging variable slots.  The solver (Phase 8)
      will add continuity equations from this map.  This is the V1 minimal
      deterministic mapping.

    Parameters
    ----------
    topology   : validated NetworkTopology (validation already occurred at
                 NetworkTopology construction time)
    components : optional Component sequence; used only to query
                 ``internal_state_names()``.  If omitted, no internal state
                 variables are allocated.  Component references are never
                 mutated and no evaluation methods are called.

    Returns
    -------
    NetworkAssembly with deterministic StateLayout and zero-initialized
    SystemState.
    """
    # Build component lookup for internal state names (structural query only;
    # no evaluation methods are called).
    comp_map: dict[str, Component] = {}
    if components is not None:
        for comp in components:
            cid: str = comp.component_id.name  # type: ignore[attr-defined]
            comp_map[cid] = comp

    # Build port peer map from connection declarations.
    # Both directions are recorded so either endpoint can find its peer.
    peer_map: dict[PortId, PortId] = {}
    for conn in topology.connections():
        from_pid = PortId(component_id=conn.from_component, port_name=conn.from_port)
        to_pid = PortId(component_id=conn.to_component, port_name=conn.to_port)
        peer_map[from_pid] = to_pid
        peer_map[to_pid] = from_pid

    # --- Pass 1: port variables (P, H, MDOT per port) ---
    # Nodes are already sorted by component_id by NetworkTopology.
    # Port names are sorted within each node for strict determinism
    # independent of the order returned by comp.ports().
    variables: list[StateVariableId] = []
    for node in topology.nodes():
        cid = node.component_id
        for port_id in sorted(node.port_ids, key=lambda p: p.port_name):
            pname = port_id.port_name
            variables.append(StateVariableId(VariableKind.P, cid, pname))
            variables.append(StateVariableId(VariableKind.H, cid, pname))
            variables.append(StateVariableId(VariableKind.MDOT, cid, pname))

    # --- Pass 2: internal state variables ---
    # Appended after all port variables; ordered by component_id then name.
    for node in topology.nodes():
        cid = node.component_id
        comp = comp_map.get(cid)
        if comp is not None:
            for name in comp.internal_state_names():
                variables.append(StateVariableId(VariableKind.INTERNAL, cid, name))

    layout = StateLayout(variables)
    initial_state = SystemState(layout, np.zeros(len(layout), dtype=np.float64))

    return NetworkAssembly(
        topology=topology,
        layout=layout,
        initial_state=initial_state,
        peer_map=peer_map,
    )
