# Core Concepts

This document explains the key abstractions in `mpl-loop-sim` and how they fit together.
Audience: researchers, PhD engineers, thermal-system model developers, future maintainers.

---

## Fluid State

```python
from mpl_sim.core import FluidState, PureFluid

fluid = PureFluid(name="R134a")
state = FluidState(P=800_000.0, h=250_000.0, identity=fluid)
```

`FluidState` is an immutable triple: `(P [Pa], h [J/kg], identity)`.

**It carries no derived properties.** Saturation temperature, density, viscosity, quality — none of these are fields on `FluidState`. If a correlation needs them, the caller supplies them explicitly through `geom_scalars`.

This is an intentional architectural decision (`[F3]`): derived properties must not be stored on state objects.

---

## Secondary Boundary Conditions

A `SecondaryFluidBC` describes what the secondary side does to the primary stream.

| BC class | Meaning | Required fields |
|---|---|---|
| `FixedHeatRate(Q)` | Prescribe total heat transfer [W]; Q > 0 heats primary. | `Q` |
| `SinkInletTempAndFlow(T_in, mdot_secondary, cp_secondary)` | Finite-capacity secondary stream enters at T_in. | `T_in` [K], `mdot_secondary` [kg/s], `cp_secondary` [J/kg/K] |
| `FixedWallTemp(T_wall)` | Primary convects to/from a wall at fixed temperature. | `T_wall` [K] (requires `htc_primary`, `A_ht`, `primary_T_in`) |
| `AmbientCoupling(T_ambient, UA_ambient)` | Primary loses/gains heat to ambient. | `T_ambient` [K], `UA_ambient` [W/K] |

Sign convention: `Q > 0` always means the primary stream gains heat (evaporator direction). `Q < 0` means the primary stream rejects heat (condenser direction).

---

## HX Model Strategies

An `HeatExchangerModel` computes `Q` and `dP_primary` from a `HXSolveRequest`.

```
HXSolveRequest  ─►  HeatExchangerModel.solve()  ─►  HXSolveResult
```

Three strategies are implemented:

| Strategy | Supported BCs | Notes |
|---|---|---|
| `EpsilonNTUModel` | All four | Lumped ε-NTU; stateless; no registry. |
| `LMTDModel` | `FixedWallTemp`, `AmbientCoupling` | Limited foundation; two-stream LMTD solving deferred. |
| `SegmentedMarchModel` | All four | Cell-by-cell enthalpy march; supports co-current and counterflow (one-pass or iterated). |

`HXSolveRequest` carries the inlet state, mass flow, secondary BC, geometry, discretization, and all injected correlations. `HXSolveResult` carries Q, outlet state, dP, `ValidityVerdict` records, and (for segmented paths) a `SegmentedProfile`.

---

## Correlations

A `Correlation` is a pure function: explicit scalar inputs in, scalar outputs out.

```
CorrelationInput  ─►  Correlation.evaluate()  ─►  CorrelationOutput
```

Key design rules:
- A correlation receives one immutable, role-typed `CorrelationInput`, which may
  contain `FluidState` values and declared scalar data. It never receives a
  whole `Component`, `Geometry`, `SystemState`, network, or solver object
  (`[F4]`, `[F11]`).
- A correlation **never calls** CoolProp or `PropertyBackend` (`[F6]`).
- Calibration multipliers are **never inside** a correlation (`[F5]`); they are applied after the call, by the HX model.
- Out-of-envelope inputs return a `ValidityVerdict` with `status=EXTRAPOLATED`; they never silently clamp.

Active closures:

| Role | Symbol | Reference |
|---|---|---|
| Single-phase HTC | `DittusBoelterHTC` | Dittus & Boelter (1930) |
| Single-phase HTC | `GnielinskiHTC` | Gnielinski (1976) |
| Boiling HTC | `ShahBoilingHTC` | Shah (1982) |
| Condensation HTC | `YanCondensationHTC` | Yan, Lio & Lin (1999) |
| Single-phase DP | `ChurchillFrictionGradient` | Churchill (1977) |
| Two-phase DP | `MSHTwoPhaseFrictionGradient` | Müller-Steinhagen & Heck (1986) |
| Volume-pressure law | `PcaVolumePressureLaw` | — |

---

## Components

`EvaporatorComponent` and `CondenserComponent` are immutable wrappers holding
component identity, ports, and geometry.
They delegate physics to an injected `HeatExchangerModel`.

```python
from mpl_sim.components import EvaporatorComponent, EvaporatorScenarioBinding

# Component: holds identity, ports, and geometry; scenario physics is injected.
component = EvaporatorComponent(component_id=..., geometry=...)

# Scenario: binds BC, model, discretization, and optional correlations.
scenario = EvaporatorScenarioBinding(
    secondary_bc=FixedHeatRate(Q=1000.0),
    model=EpsilonNTUModel(),
    discretization=DiscretizationSpec(mode=DiscretizationMode.LUMPED),
)

result = component.evaluate_scenario(inlet_state, primary_mdot=0.05, scenario=scenario)
```

Components do not know the network or their neighbours (`[F7]`).

---

## geom_scalars

`geom_scalars` is a flat `dict[str, float]` that carries all physical scalars the caller wants to make available to correlations. It is passed as-is to `HXSolveRequest`; the HX model and correlations pick out the keys they need.

Common keys:

| Key | Meaning | Unit |
|---|---|---|
| `G` | Mass flux | kg/m²/s |
| `x` | Vapour quality | — (0 to 1) |
| `D_h` | Hydraulic diameter | m |
| `L_cell` | Cell length | m |
| `A_ht` | Heat transfer area | m² |
| `Re` | Reynolds number | — |
| `Pr` | Prandtl number | — |
| `k` | Thermal conductivity | W/m/K |
| `n` | Dittus-Boelter Pr exponent | — |
| `rho_l`, `rho_v` | Liquid/vapour density | kg/m³ |
| `mu_l`, `mu_v` | Liquid/vapour viscosity | Pa·s |

Missing required keys cause a `ValueError` with the key name in the message — no silent fallback.

---

## Segmented Counterflow Path

`SegmentedMarchModel` with `SinkInletTempAndFlow` + `FlowArrangement.COUNTERFLOW` + `CounterflowIterationConfig(enabled=True)` runs a bounded fixed-point iteration:

1. Primary marches forward cell by cell (cell 0 to n-1).
2. Secondary integrates backward from the opposite end (cell n-1 to cell 0).
3. Repeat until the secondary temperature profile converges.

`HXSolveResult` carries `converged`, `residual`, and `iteration_count`. Non-convergence returns `converged=False` and never raises silently.

Required `geom_scalars` for this path: `G`, `x`, `D_h`, `L_cell`, `A_ht`, and the HTC correlation's own scalars (e.g. `Re`, `Pr`, `k`, `n` for `DittusBoelterHTC`).

---

## Residual / Unknown / Scaling Framework (Phase 13C)

`mpl_sim.closed_loop` exports four value objects for representing residuals and unknowns
as explicit, named, scaled quantities.

```python
from mpl_sim.closed_loop import (
    UnknownSpec,
    ResidualSpec,
    ResidualEvaluation,
    ResidualVector,
)

# Declare a scalar unknown with optional bounds.
q_cond_unknown = UnknownSpec(name="Q_cond", unit="W", lower=-5000.0, upper=-100.0)
mdot_unknown = UnknownSpec(name="primary_mdot", unit="kg/s", lower=0.001, upper=1.0)

# Declare a residual equation with a characteristic scale for non-dimensionalisation.
energy_spec = ResidualSpec(name="energy", unit="J/kg", scale=1000.0)
pressure_spec = ResidualSpec(name="pressure", unit="Pa", scale=100.0)

# Evaluate residuals at a given iterate.
energy_eval = ResidualEvaluation(spec=energy_spec, value=h_return - h_reference)
pressure_eval = ResidualEvaluation(spec=pressure_spec, value=pump_head - dP_total)

# Assemble a residual vector and query scaled norms.
vec = ResidualVector(evaluations=(energy_eval, pressure_eval))
print(vec.scaled_values())   # (value/scale, ...)  — one per residual
print(vec.max_abs_scaled())  # L-infinity norm of scaled residuals
print(vec.l2_scaled())       # Euclidean norm of scaled residuals
print(vec.is_converged(1e-6))  # True if max_abs_scaled() <= 1e-6
```

**What this is:**
- Pure value objects for representing named, scaled residuals and unknowns.
- A foundation for Phase 13D (coupled energy+pressure closure) and later network solving.

**What this is NOT:**
- A generic `solve(network)` call.
- A simultaneous energy+pressure nonlinear solver.
- Any network topology, graph, or parallel-branch logic.

Validation rules are strict: `name` and `unit` must be non-empty strings; `scale` must
be a finite, strictly-positive, non-bool float; `value` must be finite and non-bool;
`evaluations` must be non-empty and contain unique `spec.name` values;
`is_converged(tolerance)` requires finite, strictly-positive, non-bool tolerance.

---

## Coupled Fixed-Architecture Energy+Pressure Closure (Phase 13D)

`mpl_sim.closed_loop` exports a coupled closure that solves **both** `Q_cond` and
`primary_mdot` simultaneously so that:

```
energy_residual   = h_return - h_reference = 0   (energy closure)
pressure_residual = pump_head(mdot) - dP_total(mdot) = 0  (pressure closure)
```

**Solver strategy:** Option A — nested scalar bisection.
- Outer: bisect `primary_mdot` until pressure residual = 0.
- Inner: at each outer trial `mdot`, bisect `Q_cond` until energy residual = 0.

```python
from mpl_sim.closed_loop import (
    CoupledClosureConfig,
    MinimalCoupledClosureCase,
    PumpHeadCurve,
    solve_minimal_coupled_closure,
)

case = MinimalCoupledClosureCase(
    reference_state=reference_state,
    pump_head_curve=PumpHeadCurve(head_Pa=5625.0, slope_Pa_s_kg=100_000.0),
    evap_component=evap_component,
    evap_scenario=evap_scenario,          # dp_primary required
    evap_flow_area=0.01,                  # G_evap = mdot / evap_flow_area
    cond_component=cond_component,
    cond_scenario=cond_scenario,          # secondary_bc must be FixedHeatRate
    cond_flow_area=0.02,                  # G_cond = mdot / cond_flow_area
    q_cond_bounds=(-500.0, 0.0),          # inner bracket for Q_cond [W]
    mdot_bounds=(0.01, 0.50),             # outer bracket for primary_mdot [kg/s]
)
config = CoupledClosureConfig(
    energy_tolerance=1e-6,    # [J/kg]
    pressure_tolerance=0.01,  # [Pa]
    energy_scale=1000.0,      # for ResidualVector scaled norm
    pressure_scale=100.0,
    inner_max_iter=60,
    outer_max_iter=60,
)
result = solve_minimal_coupled_closure(case, config)

print(result.converged)             # True if both residuals below tolerance
print(result.solved_q_cond)         # condenser heat rate at solution [W]
print(result.solved_primary_mdot)   # mass flow at solution [kg/s]
print(result.energy_residual)       # h_return - h_reference [J/kg]
print(result.pressure_residual)     # pump_head - dP_total [Pa]
print(result.residual_vector.max_abs_scaled())  # L∞ norm of scaled residuals
print(result.dP_total)              # dP_evap + dP_cond [Pa]
print(result.pump_head)             # pump_head_curve.evaluate(solved_primary_mdot) [Pa]
```

`MinimalCoupledClosureResult` carries both residuals, a `ResidualVector` with
configured scales, pump head, dP breakdown, HX results, and full state history.

**What this is:**
- A coupled fixed-architecture closure (one evaporator, one condenser, one pump law).
- The first solver to drive both energy and pressure residuals to zero simultaneously.
- A direct preparation step toward the network graph (Phase 13E) and configurable
  solver (Phase 13F).

**What this is NOT:**
- A generic `solve(network)` call — architecture is fixed at one evaporator + one condenser.
- Arbitrary topology — no `Network`, `Node`, `Branch`, or `Junction` classes.
- Not a network solver. Does not support parallel evaporator branches, valves,
  manifolds, recuperators, or pre/post-heaters.
- Not validated against experimental data.

---

## Network Graph Foundation (Phase 13E)

`mpl_sim.network` exports a lightweight, physics-free graph representation
for two-phase thermal-loop topologies.

```python
from mpl_sim.network import (
    GraphNodeId,
    ComponentInstanceId,
    GraphNode,
    ComponentInstance,
    NetworkGraph,
)

# Define fluid connection points (named junctions, no physical values).
node_a = GraphNode(node_id=GraphNodeId("node_A"))
node_b = GraphNode(node_id=GraphNodeId("node_B"))

# Place a component between two nodes.
evap = ComponentInstance(
    instance_id=ComponentInstanceId("evap_1"),
    component_type="evaporator",
    inlet_node=GraphNodeId("node_A"),
    outlet_node=GraphNodeId("node_B"),
)

# Assemble a graph and inspect its topology.
graph = NetworkGraph(nodes=[node_a, node_b], instances=[evap])
print(graph.summary())   # node/component counts and names; no physical values
print(graph.nodes())     # (GraphNode(node_id=GraphNodeId(value='node_A')), ...)
print(graph.instances()) # (ComponentInstance(...),)

# Optional: check that the graph forms a closed single loop.
# graph.validate_closed_single_loop()  # raises ValueError if not a closed loop
```

**What this is:**
- Pure topology description: named fluid connection points and named component
  instances placed between those points.
- Physics-free: no `FluidState`, `mdot`, pressure, enthalpy, or solver values
  anywhere in the graph.
- Foundation for Phase 13F (network residual assembly) and Phase 13G
  (configurable network solver v1).

**What this is NOT:**
- Not a network solver — `NetworkGraph` has no `solve()` method.
- Does not assemble residuals or drive convergence.
- Does not support arbitrary topology simulation yet.
- Does not call CoolProp, property backends, or correlation registries.
- Does not implement physics: no HTC, ΔP, energy balance, or pressure closure.

Validation rules:
- IDs (`GraphNodeId`, `ComponentInstanceId`) must be non-empty strings.
- No duplicate node IDs within a graph.
- No duplicate component instance IDs within a graph.
- Every component's `inlet_node` and `outlet_node` must exist in the graph.
- Self-loop components (same inlet and outlet node) are rejected.

The existing Phase 7 network package (`NetworkTopology`, `NetworkNode`,
`NetworkConnection`, etc.) remains unchanged and is used by the solver
layer.  Phase 13E's graph types (`GraphNode`, `ComponentInstance`,
`NetworkGraph`) are a lighter abstraction that does not depend on
`Component` objects or physics layers.

---

## What is NOT implemented

| Capability | Status |
|---|---|
| Minimal fixed-architecture energy closure | Implemented in Phase 13A (`mpl_sim.closed_loop`) |
| Minimal fixed-architecture pressure closure | Implemented in Phase 13B (`mpl_sim.closed_loop`) |
| Residual/unknown/scaling framework | Implemented in Phase 13C (`mpl_sim.closed_loop`) |
| Coupled energy+pressure closure | Implemented in Phase 13D (`mpl_sim.closed_loop`) |
| Network graph / topology representation | Implemented in Phase 13E (`mpl_sim.network`) |
| Generic network solver (`solve(network)`) | Deferred (Phase 13F+) |
| Network residual assembly | Deferred (Phase 13F) |
| Configurable network solve | Deferred (Phase 13G) |
| Parallel evaporators, valves, manifolds, recuperator | Deferred (Phase 14+) |
| Property lookup (CoolProp/REFPROP) in HX/component layers | Not in scope for these layers |
| Moving-boundary model | Deferred |
| Automatic phase inference | Not planned for this layer |
| Validation against experimental data | Deferred (Phase 12+ validation harness) |
| Dynamic/transient simulation | Deferred |
| Remaining boiling/condensation HTC closures | Deferred |
| Homogeneous/Cicchitti, Kim-Mudawar 2013 DP | Deferred |
