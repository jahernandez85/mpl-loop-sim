"""Fixed single-loop scenario declaration — Block 15B.1.

Provides explicit topology, unknown, and residual declarations for a minimal
fixed single-loop network:

    accumulator → pump → evaporator → condenser → accumulator

This is a declaration-only module.  It does not execute production component
physics, does not assemble SystemState, does not create FluidState, does not
call CoolProp, PropertyBackend, correlations, or HX models.

Block 15B.2 and later are responsible for physical residual assembly.
Arbitrary-topology physical simulation and generic solve(network) /
NetworkGraph.solve() remain deferred.

Exported names
--------------
FixedSingleLoopComponentIds      — frozen container of 4 component instance IDs
FixedSingleLoopNodeIds           — frozen container of 4 graph node IDs
FixedSingleLoopUnknownNames      — frozen container of 8 explicit unknown name strings
FixedSingleLoopResidualNames     — frozen container of 8 explicit residual name strings
FixedSingleLoopScenario          — immutable assembled scenario object
build_fixed_single_loop_scenario — deterministic factory returning FixedSingleLoopScenario

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

# ---------------------------------------------------------------------------
# Component ID container
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FixedSingleLoopComponentIds:
    """Frozen container of the four component instance IDs in the fixed loop.

    Logical roles (labels only — no physics attached):
      accumulator : reservoir / accumulator role
      pump        : circulation pump role
      evaporator  : primary evaporator role
      condenser   : primary condenser role

    All four IDs must be distinct ComponentInstanceId objects.
    """

    accumulator: ComponentInstanceId
    pump: ComponentInstanceId
    evaporator: ComponentInstanceId
    condenser: ComponentInstanceId

    def __post_init__(self) -> None:
        for field_name, value in (
            ("accumulator", self.accumulator),
            ("pump", self.pump),
            ("evaporator", self.evaporator),
            ("condenser", self.condenser),
        ):
            if not isinstance(value, ComponentInstanceId):
                raise TypeError(
                    f"FixedSingleLoopComponentIds.{field_name} must be a "
                    f"ComponentInstanceId; got {type(value).__name__!r}"
                )
        ids = [
            self.accumulator.value,
            self.pump.value,
            self.evaporator.value,
            self.condenser.value,
        ]
        if len(set(ids)) != 4:
            raise ValueError(
                "FixedSingleLoopComponentIds: all four component IDs must be "
                f"distinct; got {ids!r}"
            )

    def all_ids(self) -> tuple[ComponentInstanceId, ...]:
        """All four component IDs in declaration order."""
        return (self.accumulator, self.pump, self.evaporator, self.condenser)


# ---------------------------------------------------------------------------
# Node ID container
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FixedSingleLoopNodeIds:
    """Frozen container of the four graph node IDs in the fixed loop.

    Logical roles (labels only — no physics attached):
      n_acc_out  : outlet of accumulator / inlet of pump
      n_pump_out : outlet of pump / inlet of evaporator
      n_evap_out : outlet of evaporator / inlet of condenser
      n_cond_out : outlet of condenser / inlet of accumulator

    All four IDs must be distinct GraphNodeId objects.
    """

    n_acc_out: GraphNodeId
    n_pump_out: GraphNodeId
    n_evap_out: GraphNodeId
    n_cond_out: GraphNodeId

    def __post_init__(self) -> None:
        for field_name, value in (
            ("n_acc_out", self.n_acc_out),
            ("n_pump_out", self.n_pump_out),
            ("n_evap_out", self.n_evap_out),
            ("n_cond_out", self.n_cond_out),
        ):
            if not isinstance(value, GraphNodeId):
                raise TypeError(
                    f"FixedSingleLoopNodeIds.{field_name} must be a "
                    f"GraphNodeId; got {type(value).__name__!r}"
                )
        ids = [
            self.n_acc_out.value,
            self.n_pump_out.value,
            self.n_evap_out.value,
            self.n_cond_out.value,
        ]
        if len(set(ids)) != 4:
            raise ValueError(
                "FixedSingleLoopNodeIds: all four node IDs must be distinct; " f"got {ids!r}"
            )

    def all_ids(self) -> tuple[GraphNodeId, ...]:
        """All four node IDs in declaration order."""
        return (self.n_acc_out, self.n_pump_out, self.n_evap_out, self.n_cond_out)


# ---------------------------------------------------------------------------
# Unknown name container
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FixedSingleLoopUnknownNames:
    """Frozen container of 8 explicit unknown name strings.

    Names are declaration-only string labels.  No physical values are attached.
    Ordering matches assemble_network_residuals convention:
      first the 4 mass-flow unknowns (component insertion order),
      then the 4 pressure unknowns (node insertion order).
    """

    mdot_accumulator: str
    mdot_pump: str
    mdot_evaporator: str
    mdot_condenser: str
    P_n_acc_out: str
    P_n_pump_out: str
    P_n_evap_out: str
    P_n_cond_out: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("mdot_accumulator", self.mdot_accumulator),
            ("mdot_pump", self.mdot_pump),
            ("mdot_evaporator", self.mdot_evaporator),
            ("mdot_condenser", self.mdot_condenser),
            ("P_n_acc_out", self.P_n_acc_out),
            ("P_n_pump_out", self.P_n_pump_out),
            ("P_n_evap_out", self.P_n_evap_out),
            ("P_n_cond_out", self.P_n_cond_out),
        ):
            if not isinstance(value, str):
                raise TypeError(
                    f"FixedSingleLoopUnknownNames.{field_name} must be a str; "
                    f"got {type(value).__name__!r}"
                )
            if not value.strip():
                raise ValueError(
                    f"FixedSingleLoopUnknownNames.{field_name} must be " f"non-empty; got {value!r}"
                )
        names = self.all_names()
        if len(set(names)) != len(names):
            raise ValueError(
                "FixedSingleLoopUnknownNames: all unknown names must be "
                f"distinct; got {list(names)!r}"
            )

    def all_names(self) -> tuple[str, ...]:
        """All 8 unknown names in declaration order."""
        return (
            self.mdot_accumulator,
            self.mdot_pump,
            self.mdot_evaporator,
            self.mdot_condenser,
            self.P_n_acc_out,
            self.P_n_pump_out,
            self.P_n_evap_out,
            self.P_n_cond_out,
        )


# ---------------------------------------------------------------------------
# Residual name container
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FixedSingleLoopResidualNames:
    """Frozen container of 8 explicit residual name strings.

    Names are declaration-only string labels.  No physical values are attached.
    Ordering matches assemble_network_residuals convention:
      first the 4 mass-balance residuals (node insertion order),
      then the 4 pressure-drop residuals (component insertion order).
    """

    mass_balance_n_acc_out: str
    mass_balance_n_pump_out: str
    mass_balance_n_evap_out: str
    mass_balance_n_cond_out: str
    pressure_drop_accumulator: str
    pressure_drop_pump: str
    pressure_drop_evaporator: str
    pressure_drop_condenser: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("mass_balance_n_acc_out", self.mass_balance_n_acc_out),
            ("mass_balance_n_pump_out", self.mass_balance_n_pump_out),
            ("mass_balance_n_evap_out", self.mass_balance_n_evap_out),
            ("mass_balance_n_cond_out", self.mass_balance_n_cond_out),
            ("pressure_drop_accumulator", self.pressure_drop_accumulator),
            ("pressure_drop_pump", self.pressure_drop_pump),
            ("pressure_drop_evaporator", self.pressure_drop_evaporator),
            ("pressure_drop_condenser", self.pressure_drop_condenser),
        ):
            if not isinstance(value, str):
                raise TypeError(
                    f"FixedSingleLoopResidualNames.{field_name} must be a str; "
                    f"got {type(value).__name__!r}"
                )
            if not value.strip():
                raise ValueError(
                    f"FixedSingleLoopResidualNames.{field_name} must be "
                    f"non-empty; got {value!r}"
                )
        names = self.all_names()
        if len(set(names)) != len(names):
            raise ValueError(
                "FixedSingleLoopResidualNames: all residual names must be "
                f"distinct; got {list(names)!r}"
            )

    def all_names(self) -> tuple[str, ...]:
        """All 8 residual names in declaration order."""
        return (
            self.mass_balance_n_acc_out,
            self.mass_balance_n_pump_out,
            self.mass_balance_n_evap_out,
            self.mass_balance_n_cond_out,
            self.pressure_drop_accumulator,
            self.pressure_drop_pump,
            self.pressure_drop_evaporator,
            self.pressure_drop_condenser,
        )


# ---------------------------------------------------------------------------
# Scenario container
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FixedSingleLoopScenario:
    """Immutable fixed single-loop scenario declaration.

    Contains all structural declarations for the fixed minimal loop:
        accumulator → pump → evaporator → condenser → accumulator

    This object is declaration-only.  It does not contain FluidState,
    SystemState, physical state values, property backend objects, or
    production component objects.

    Fields
    ------
    graph           : NetworkGraph (4 nodes, 4 components, closed single loop)
    assembly        : NetworkResidualAssembly (8 unknowns, 8 residuals)
    binding_context : NetworkBindingContext (explicit bindings and state map)
    component_ids   : FixedSingleLoopComponentIds (4 component instance IDs)
    node_ids        : FixedSingleLoopNodeIds (4 graph node IDs)
    unknown_names   : FixedSingleLoopUnknownNames (8 explicit unknown names)
    residual_names  : FixedSingleLoopResidualNames (8 explicit residual names)
    metadata        : optional caller-supplied metadata; defensively copied
    """

    graph: NetworkGraph
    assembly: NetworkResidualAssembly
    binding_context: NetworkBindingContext
    component_ids: FixedSingleLoopComponentIds
    node_ids: FixedSingleLoopNodeIds
    unknown_names: FixedSingleLoopUnknownNames
    residual_names: FixedSingleLoopResidualNames
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.graph, NetworkGraph):
            raise TypeError(
                "FixedSingleLoopScenario.graph must be a NetworkGraph; "
                f"got {type(self.graph).__name__!r}"
            )
        if not isinstance(self.assembly, NetworkResidualAssembly):
            raise TypeError(
                "FixedSingleLoopScenario.assembly must be a "
                "NetworkResidualAssembly; "
                f"got {type(self.assembly).__name__!r}"
            )
        if not isinstance(self.binding_context, NetworkBindingContext):
            raise TypeError(
                "FixedSingleLoopScenario.binding_context must be a "
                "NetworkBindingContext; "
                f"got {type(self.binding_context).__name__!r}"
            )
        if not isinstance(self.component_ids, FixedSingleLoopComponentIds):
            raise TypeError(
                "FixedSingleLoopScenario.component_ids must be a "
                "FixedSingleLoopComponentIds; "
                f"got {type(self.component_ids).__name__!r}"
            )
        if not isinstance(self.node_ids, FixedSingleLoopNodeIds):
            raise TypeError(
                "FixedSingleLoopScenario.node_ids must be a "
                "FixedSingleLoopNodeIds; "
                f"got {type(self.node_ids).__name__!r}"
            )
        if not isinstance(self.unknown_names, FixedSingleLoopUnknownNames):
            raise TypeError(
                "FixedSingleLoopScenario.unknown_names must be a "
                "FixedSingleLoopUnknownNames; "
                f"got {type(self.unknown_names).__name__!r}"
            )
        if not isinstance(self.residual_names, FixedSingleLoopResidualNames):
            raise TypeError(
                "FixedSingleLoopScenario.residual_names must be a "
                "FixedSingleLoopResidualNames; "
                f"got {type(self.residual_names).__name__!r}"
            )
        md = self.metadata
        if md is not None:
            if not isinstance(md, Mapping):
                raise TypeError(
                    "FixedSingleLoopScenario.metadata must be a Mapping or "
                    f"None; got {type(md).__name__!r}"
                )
            object.__setattr__(self, "metadata", MappingProxyType(dict(md)))

    def summary(self) -> dict[str, object]:
        """Structural summary with labels only.  No physical values."""
        return {
            "topology": "accumulator -> pump -> evaporator -> condenser -> accumulator",
            "component_ids": {
                "accumulator": self.component_ids.accumulator.value,
                "pump": self.component_ids.pump.value,
                "evaporator": self.component_ids.evaporator.value,
                "condenser": self.component_ids.condenser.value,
            },
            "node_ids": {
                "n_acc_out": self.node_ids.n_acc_out.value,
                "n_pump_out": self.node_ids.n_pump_out.value,
                "n_evap_out": self.node_ids.n_evap_out.value,
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


def build_fixed_single_loop_scenario(
    *,
    accumulator_id: str = "accumulator",
    pump_id: str = "pump",
    evaporator_id: str = "evaporator",
    condenser_id: str = "condenser",
    n_acc_out_id: str = "n_acc_out",
    n_pump_out_id: str = "n_pump_out",
    n_evap_out_id: str = "n_evap_out",
    n_cond_out_id: str = "n_cond_out",
    metadata: Mapping[str, object] | None = None,
) -> FixedSingleLoopScenario:
    """Build a deterministic fixed single-loop scenario declaration.

    Creates and validates all declarations for the fixed minimal loop:
        accumulator → pump → evaporator → condenser → accumulator

    All ID parameters are symbolic string labels only.  No physical values,
    no property defaults, no CoolProp, no PropertyBackend, no correlations.

    Parameters
    ----------
    accumulator_id : str
        Label for the accumulator/reservoir component instance.
    pump_id : str
        Label for the pump component instance.
    evaporator_id : str
        Label for the evaporator component instance.
    condenser_id : str
        Label for the condenser component instance.
    n_acc_out_id : str
        Label for the node at the accumulator outlet / pump inlet.
    n_pump_out_id : str
        Label for the node at the pump outlet / evaporator inlet.
    n_evap_out_id : str
        Label for the node at the evaporator outlet / condenser inlet.
    n_cond_out_id : str
        Label for the node at the condenser outlet / accumulator inlet.
    metadata : Mapping[str, object] | None
        Optional caller-supplied metadata stored on the scenario.

    Returns
    -------
    FixedSingleLoopScenario
        Immutable scenario with graph, assembly, binding context,
        component IDs, node IDs, unknown names, and residual names.

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
    _component_params = {
        "accumulator_id": accumulator_id,
        "pump_id": pump_id,
        "evaporator_id": evaporator_id,
        "condenser_id": condenser_id,
    }
    for param_name, param_value in _component_params.items():
        if not isinstance(param_value, str):
            raise TypeError(
                f"build_fixed_single_loop_scenario: {param_name} must be a "
                f"str; got {type(param_value).__name__!r}"
            )
        if not param_value.strip():
            raise ValueError(
                f"build_fixed_single_loop_scenario: {param_name} must be "
                f"non-empty; got {param_value!r}"
            )

    # Validate node ID string parameters.
    _node_params = {
        "n_acc_out_id": n_acc_out_id,
        "n_pump_out_id": n_pump_out_id,
        "n_evap_out_id": n_evap_out_id,
        "n_cond_out_id": n_cond_out_id,
    }
    for param_name, param_value in _node_params.items():
        if not isinstance(param_value, str):
            raise TypeError(
                f"build_fixed_single_loop_scenario: {param_name} must be a "
                f"str; got {type(param_value).__name__!r}"
            )
        if not param_value.strip():
            raise ValueError(
                f"build_fixed_single_loop_scenario: {param_name} must be "
                f"non-empty; got {param_value!r}"
            )

    # Validate uniqueness before constructing typed objects.
    _component_id_values = [accumulator_id, pump_id, evaporator_id, condenser_id]
    if len(set(_component_id_values)) != 4:
        raise ValueError(
            "build_fixed_single_loop_scenario: all component IDs must be "
            f"distinct; got {_component_id_values!r}"
        )

    _node_id_values = [n_acc_out_id, n_pump_out_id, n_evap_out_id, n_cond_out_id]
    if len(set(_node_id_values)) != 4:
        raise ValueError(
            "build_fixed_single_loop_scenario: all node IDs must be distinct; "
            f"got {_node_id_values!r}"
        )

    if metadata is not None and not isinstance(metadata, Mapping):
        raise TypeError(
            "build_fixed_single_loop_scenario: metadata must be a Mapping or "
            f"None; got {type(metadata).__name__!r}"
        )

    # Build typed ID objects.
    _acc_cid = ComponentInstanceId(accumulator_id)
    _pump_cid = ComponentInstanceId(pump_id)
    _evap_cid = ComponentInstanceId(evaporator_id)
    _cond_cid = ComponentInstanceId(condenser_id)

    _n_acc_out = GraphNodeId(n_acc_out_id)
    _n_pump_out = GraphNodeId(n_pump_out_id)
    _n_evap_out = GraphNodeId(n_evap_out_id)
    _n_cond_out = GraphNodeId(n_cond_out_id)

    component_ids = FixedSingleLoopComponentIds(
        accumulator=_acc_cid,
        pump=_pump_cid,
        evaporator=_evap_cid,
        condenser=_cond_cid,
    )
    node_ids = FixedSingleLoopNodeIds(
        n_acc_out=_n_acc_out,
        n_pump_out=_n_pump_out,
        n_evap_out=_n_evap_out,
        n_cond_out=_n_cond_out,
    )

    # Build unknown and residual name containers.
    unknown_names = FixedSingleLoopUnknownNames(
        mdot_accumulator=f"mdot:{accumulator_id}",
        mdot_pump=f"mdot:{pump_id}",
        mdot_evaporator=f"mdot:{evaporator_id}",
        mdot_condenser=f"mdot:{condenser_id}",
        P_n_acc_out=f"P:{n_acc_out_id}",
        P_n_pump_out=f"P:{n_pump_out_id}",
        P_n_evap_out=f"P:{n_evap_out_id}",
        P_n_cond_out=f"P:{n_cond_out_id}",
    )
    residual_names = FixedSingleLoopResidualNames(
        mass_balance_n_acc_out=f"mass_balance:{n_acc_out_id}",
        mass_balance_n_pump_out=f"mass_balance:{n_pump_out_id}",
        mass_balance_n_evap_out=f"mass_balance:{n_evap_out_id}",
        mass_balance_n_cond_out=f"mass_balance:{n_cond_out_id}",
        pressure_drop_accumulator=f"pressure_drop:{accumulator_id}",
        pressure_drop_pump=f"pressure_drop:{pump_id}",
        pressure_drop_evaporator=f"pressure_drop:{evaporator_id}",
        pressure_drop_condenser=f"pressure_drop:{condenser_id}",
    )

    # Build graph.
    # Loop: accumulator → pump → evaporator → condenser → accumulator
    _nodes = [
        GraphNode(_n_acc_out),
        GraphNode(_n_pump_out),
        GraphNode(_n_evap_out),
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
            instance_id=_evap_cid,
            component_type="evaporator",
            inlet_node=_n_pump_out,
            outlet_node=_n_evap_out,
        ),
        ComponentInstance(
            instance_id=_cond_cid,
            component_type="condenser",
            inlet_node=_n_evap_out,
            outlet_node=_n_cond_out,
        ),
    ]
    graph = NetworkGraph(nodes=_nodes, instances=_instances)

    # Assemble residuals with closed-loop validation.
    assembly = assemble_network_residuals(
        graph,
        require_closed_loop=True,
        include_pressure_unknowns=True,
        include_pressure_residuals=True,
    )

    # Build component bindings.
    _bindings = ComponentBindingSet(
        bindings=(
            ComponentBinding(instance_id=_acc_cid, binding_name="accumulator"),
            ComponentBinding(instance_id=_pump_cid, binding_name="pump"),
            ComponentBinding(instance_id=_evap_cid, binding_name="evaporator"),
            ComponentBinding(instance_id=_cond_cid, binding_name="condenser"),
        )
    )

    # Build state map: maps all assembly unknown/residual names to IDs.
    _state_map = ComponentStateMap(
        unknown_to_component={
            unknown_names.mdot_accumulator: _acc_cid,
            unknown_names.mdot_pump: _pump_cid,
            unknown_names.mdot_evaporator: _evap_cid,
            unknown_names.mdot_condenser: _cond_cid,
        },
        unknown_to_node={
            unknown_names.P_n_acc_out: _n_acc_out,
            unknown_names.P_n_pump_out: _n_pump_out,
            unknown_names.P_n_evap_out: _n_evap_out,
            unknown_names.P_n_cond_out: _n_cond_out,
        },
        residual_to_node={
            residual_names.mass_balance_n_acc_out: _n_acc_out,
            residual_names.mass_balance_n_pump_out: _n_pump_out,
            residual_names.mass_balance_n_evap_out: _n_evap_out,
            residual_names.mass_balance_n_cond_out: _n_cond_out,
        },
        residual_to_component={
            residual_names.pressure_drop_accumulator: _acc_cid,
            residual_names.pressure_drop_pump: _pump_cid,
            residual_names.pressure_drop_evaporator: _evap_cid,
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

    return FixedSingleLoopScenario(
        graph=graph,
        assembly=assembly,
        binding_context=binding_context,
        component_ids=component_ids,
        node_ids=node_ids,
        unknown_names=unknown_names,
        residual_names=residual_names,
        metadata=metadata,
    )
