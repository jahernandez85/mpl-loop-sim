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

## Network Residual Assembly Foundation (Phase 13F)

`mpl_sim.network` exports lightweight, declaration-only types that map a
`NetworkGraph` topology into explicit structural unknown and residual
declarations.  **This is a specification layer only — it does not solve,
evaluate residuals numerically, or execute component physics.**

```python
from mpl_sim.network import (
    NetworkUnknownDeclaration,
    NetworkResidualDeclaration,
    NetworkUnknownSet,
    NetworkResidualSet,
    NetworkResidualAssembly,
    assemble_network_residuals,
)

# Given a NetworkGraph (from Phase 13E), assemble structural declarations.
assembly = assemble_network_residuals(graph)

# Inspect declared unknowns (names and units only — no values).
print(assembly.unknowns.names())
# e.g. ('mdot:evap', 'mdot:cond', 'P:node_a', 'P:node_b', 'P:node_c')

# Inspect declared residuals.
print(assembly.residuals.names())
# e.g. ('mass_balance:node_a', 'mass_balance:node_b', 'mass_balance:node_c',
#        'pressure_drop:evap', 'pressure_drop:cond')

# Summary: counts and names only.
print(assembly.summary())
# {'unknown_count': 5, 'unknown_names': [...],
#  'residual_count': 5, 'residual_names': [...]}

# Optional: require a closed single loop before assembling.
assembly = assemble_network_residuals(graph, require_closed_loop=True)

# Optional: suppress pressure unknowns/residuals.
assembly = assemble_network_residuals(
    graph,
    include_pressure_unknowns=False,
    include_pressure_residuals=False,
)
```

**What this is:**
- Structural unknown declarations: one mass-flow unknown per component
  instance (``"mdot:<id>"``, kg/s), and optionally one pressure unknown per
  node (``"P:<id>"``, Pa).
- Structural residual declarations: one mass-conservation residual per node
  (``"mass_balance:<id>"``, kg/s), and optionally one pressure-compatibility
  residual per component instance (``"pressure_drop:<id>"``, Pa).
- Assembly order is deterministic (graph insertion order).
- A summary with counts and names only — no physical values anywhere.
- Foundation for Phase 13G (configurable network solver v1) and later
  component family integration.

**What this is NOT:**
- Not a network solver — ``NetworkResidualAssembly`` has no ``solve()`` method.
- Does not evaluate residuals numerically.
- Does not execute component physics.
- Does not call CoolProp, property backends, or correlation registries.
- Does not store ``FluidState``, ``mdot`` values, pressure values, enthalpy
  values, quality, temperature, or any physical state.
- Does not yet support arbitrary topology simulation.
- Does not implement the full network solver path (deferred to Phase 13G).

---

## Network Residual Evaluation Foundation (Phase 13G)

`mpl_sim.network` exports a lightweight, explicit residual evaluation layer
that evaluates declared network residuals from a supplied value map and
supplied callback functions.  **This is an evaluation layer only — it does
not solve the network, execute component physics, or look up fluid properties.**

```python
from mpl_sim.network import (
    NetworkUnknownValues,
    NetworkResidualEvaluator,
    NetworkResidualEvaluationResult,
    evaluate_network_residuals,
    assemble_network_residuals,
)

# Start from a NetworkResidualAssembly (Phase 13F).
assembly = assemble_network_residuals(graph)

# Provide explicit numeric values for every declared unknown.
unknown_values = NetworkUnknownValues(
    values={
        "mdot:evap": 0.05,   # kg/s
        "mdot:cond": 0.05,   # kg/s
        "P:n1": 100_000.0,   # Pa
        "P:n2":  99_000.0,   # Pa
    }
)

# Provide one explicit callback per declared residual.
# Callbacks receive the full unknown-value mapping and return a float.
evaluators = [
    NetworkResidualEvaluator(
        name="mass_balance:n1",
        callback=lambda v: v["mdot:evap"] - v["mdot:cond"],
    ),
    NetworkResidualEvaluator(
        name="mass_balance:n2",
        callback=lambda v: v["mdot:cond"] - v["mdot:evap"],
    ),
    NetworkResidualEvaluator(
        name="pressure_drop:evap",
        callback=lambda v: v["P:n1"] - v["P:n2"] - 600.0,
    ),
    NetworkResidualEvaluator(
        name="pressure_drop:cond",
        callback=lambda v: v["P:n2"] - v["P:n1"] + 1000.0,
    ),
]

# Provide explicit characteristic scales for each residual.
scales = {
    "mass_balance:n1":    0.01,   # kg/s
    "mass_balance:n2":    0.01,
    "pressure_drop:evap": 100.0,  # Pa
    "pressure_drop:cond": 100.0,
}

# Evaluate — returns a NetworkResidualEvaluationResult.
result = evaluate_network_residuals(assembly, unknown_values, evaluators, scales)

print(result.max_abs_scaled)      # 4.0  (L-inf norm)
print(result.l2_scaled)           # 4.0  (L2 norm)
print(result.scaled_values)       # (0.0, 0.0, 4.0, 0.0)
print(result.residual_vector)     # ResidualVector (Phase 13C)
```

**What this is:**
- An explicit evaluation layer: accepts declared residuals (Phase 13F), an
  explicit unknown-value map (`NetworkUnknownValues`), explicit callback
  functions (`NetworkResidualEvaluator`), and explicit scales.
- Evaluates each callback with the supplied values and builds a `ResidualVector`
  (Phase 13C) in assembly declaration order.
- Reports `max_abs_scaled` (L-infinity norm) and `l2_scaled` (Euclidean norm)
  of the scaled residuals.
- All validation is strict: missing/extra unknowns, missing/extra evaluators,
  missing/extra scales, non-finite values, and bool values are all rejected.
- Callback exceptions propagate without being swallowed.
- A preparation step toward a future configurable network solver (Phase 13H).

**What this is NOT:**
- Not a network solver — `evaluate_network_residuals` does not iterate toward
  a zero, does not call `solve(network)`, and does not drive convergence.
- Does not execute components automatically — callbacks are supplied by the
  caller and may represent any explicit computation.
- Does not look up fluid properties — no CoolProp, no `PropertyBackend`.
- Does not attach physical state to graph nodes.
- Does not infer residuals automatically from component physics.
- Does not implement hidden physical defaults.

---

## Configurable Network Solver v1 (Phase 13H)

`mpl_sim.network` exports a minimal configurable algebraic residual solver
that iterates explicit unknown values to reduce explicit residual callbacks.
**This is a mathematical solve layer over explicit declarations and explicit
callbacks — it does not construct residuals from physical components.**

```python
from mpl_sim.network import (
    NetworkSolveConfig,
    NetworkSolveResult,
    solve_network_residual_problem,
)

# Configure the solver.
config = NetworkSolveConfig(
    max_iterations=100,
    tolerance=1e-10,
    finite_difference_step=1e-6,
)

# Provide the assembly (Phase 13F), initial values, explicit callbacks,
# and explicit scales (Phase 13G), then solve.
result = solve_network_residual_problem(
    assembly,       # NetworkResidualAssembly from Phase 13F
    initial_values, # NetworkUnknownValues or dict[str, float]
    evaluators,     # list of NetworkResidualEvaluator (Phase 13G)
    scales,         # dict[str, float] — one scale per residual
    config,
)

print(result.converged)              # True if final max_abs_scaled <= tolerance
print(result.iteration_count)        # number of Newton iterations performed
print(result.reason)                 # human-readable status string
print(result.final_unknown_values)   # NetworkUnknownValues at solution
print(result.final_evaluation)       # NetworkResidualEvaluationResult (Phase 13G)
print(result.initial_evaluation)     # evaluation at the initial guess
```

**Solver method:** Damped finite-difference Newton.

- Forward finite differences build the n×n Jacobian at each iterate.
- Gaussian elimination with partial pivoting solves the linear system.
- Update: `x_new = x + damping * dx`.
- Convergence criterion: `max_abs_scaled <= tolerance`.
- Singular Jacobian detection: returns `converged=False` with a descriptive
  reason rather than raising.
- Only square systems (`n_unknowns == n_residuals`) are accepted.

**Validation rules:**

- `max_iterations`: positive integer, bool rejected.
- `tolerance`: finite, positive, non-bool.
- `finite_difference_step`: finite, positive, non-bool.
- `damping`: finite, in (0, 1], non-bool. Default 1.0 (full Newton step).
- Assembly must be a `NetworkResidualAssembly`.
- Initial values must be `NetworkUnknownValues` or a `Mapping[str, float]`.
- Evaluators and scales are validated by `evaluate_network_residuals` (Phase 13G).

**What this is:**

- A configurable algebraic residual solver over Phase 13G evaluation.
- Drives `max_abs_scaled` below `tolerance` by updating explicit unknowns.
- Uses explicit callback functions supplied by the caller.
- A preparation step toward physical residual construction (Phase 14+).

**What this is NOT:**

- Does not construct residuals from physical components automatically.
- Does not execute component instances or call component physics.
- Does not perform property lookup (no thermodynamic backends).
- Does not attach physical state to graph nodes.
- Does not implement the full MPL simulator — this is an algebraic layer.
- Not validated against experimental data.

---

## Physical Residual Adapter Foundation (Phase 14A)

`mpl_sim.network` exports an explicit adapter layer that converts
caller-supplied physical component residual callbacks into Phase 13G/13H-
compatible `NetworkResidualEvaluator` objects.  **This is an adapter
foundation only — it does NOT constitute a full physical network simulator.**

```python
from mpl_sim.network import (
    PhysicalResidualContext,
    PhysicalResidualAdapter,
    PhysicalResidualAdapterSet,
    build_network_residual_evaluators,
)

# Each adapter binds one residual declaration name to a caller-supplied
# callback that receives a PhysicalResidualContext.
adapters = [
    PhysicalResidualAdapter(
        residual_name="mass_balance:n1",
        callback=lambda ctx: ctx.unknown_values["mdot:evap"] - ctx.unknown_values["mdot:cond"],
    ),
    PhysicalResidualAdapter(
        residual_name="mass_balance:n2",
        callback=lambda ctx: ctx.unknown_values["mdot:cond"] - ctx.unknown_values["mdot:evap"],
    ),
    PhysicalResidualAdapter(
        residual_name="pressure_drop:evap",
        callback=lambda ctx: ctx.unknown_values["P:n1"] - ctx.unknown_values["P:n2"] - 600.0,
    ),
    PhysicalResidualAdapter(
        residual_name="pressure_drop:cond",
        callback=lambda ctx: ctx.unknown_values["P:n2"] - ctx.unknown_values["P:n1"] + 1000.0,
    ),
]

# Optionally group adapters into a validated, ordered set.
adapter_set = PhysicalResidualAdapterSet(adapters=tuple(adapters))

# Convert to NetworkResidualEvaluator objects (Phase 13G-compatible).
# Names must match assembly residual declarations exactly.
evaluators = build_network_residual_evaluators(
    assembly,       # NetworkResidualAssembly from Phase 13F
    adapter_set,    # or a plain list of PhysicalResidualAdapter
    metadata={"run_id": "example"},  # optional caller metadata
)

# Pass the evaluators directly to Phase 13G or Phase 13H.
result = evaluate_network_residuals(assembly, unknown_values, evaluators, scales)
```

The constants in this snippet are toy algebraic values only. They are not
library defaults, physical correlations, or validation data.

`PhysicalResidualContext` carries the current unknown-value mapping and
optional caller metadata.  It is created per evaluation and passed to the
adapter callback:

```python
def my_adapter(ctx: PhysicalResidualContext) -> float:
    v = ctx.unknown_values   # MappingProxyType[str, float] — read-only
    meta = ctx.metadata      # MappingProxyType[str, object] | None
    return v["P:n1"] - v["P:n2"] - 600.0
```

**What this is:**
- An explicit adapter layer: caller-supplied callback functions are bound to
  residual declaration names and converted to `NetworkResidualEvaluator`
  objects compatible with Phase 13G and Phase 13H.
- Adapter names must match assembly residual declarations exactly (missing
  and extra adapters are rejected).
- Assembly residual order is preserved in the generated evaluator tuple.
- `PhysicalResidualContext` is immutable; unknown values and metadata are
  defensively copied.
- A preparation step toward Phase 14B component binding and Phase 14C
  minimal physical single-loop solve.

**What this is NOT:**
- Does NOT construct residuals automatically from graph component physics.
- Does NOT execute component instances or call component physics methods.
- Does NOT call the frozen `contribute(...)` component contribution method.
- Does NOT look up fluid properties — no CoolProp, no `PropertyBackend`.
- Does NOT call `CorrelationRegistry` or any correlation registry.
- Does NOT attach physical state (`FluidState`, mdot, pressure, enthalpy)
  to graph nodes.
- Does NOT infer residual form from `component_type`.
- Does NOT implement `solve(network)`.
- Is NOT a full MPL network simulator — physical residual logic must be
  supplied entirely by the caller through explicit adapter callbacks.
- Is NOT validation against experiment or literature data.

---

## Component Binding and State-Vector Mapping Foundation (Phase 14B)

`mpl_sim.network` exports an explicit binding and mapping declaration layer
that links `NetworkGraph` component instances to caller-supplied binding
labels, and maps residual/unknown names to component instances and graph nodes.
**This is a declaration-only layer — it does NOT constitute a physical network
simulator, does NOT execute components, and does NOT call property backends.**

```python
from mpl_sim.network import (
    ComponentBinding,
    ComponentBindingSet,
    ComponentInstanceId,
    ComponentStateMap,
    GraphNodeId,
    NetworkBindingContext,
    assemble_network_residuals,
    build_binding_context,
)

# Assume `graph` is an existing NetworkGraph containing component instances
# "evap" and "cond" connected through nodes "n1" and "n2".

# Declare one binding per component instance.
bindings = ComponentBindingSet(
    bindings=(
        ComponentBinding(
            instance_id=ComponentInstanceId("evap"),
            binding_name="toy_evaporator_binding",
        ),
        ComponentBinding(
            instance_id=ComponentInstanceId("cond"),
            binding_name="toy_condenser_binding",
        ),
    )
)

# Declare how unknown/residual names map to component instances and nodes.
state_map = ComponentStateMap(
    unknown_to_component={
        "mdot:evap": ComponentInstanceId("evap"),
        "mdot:cond": ComponentInstanceId("cond"),
    },
    unknown_to_node={
        "P:n1": GraphNodeId("n1"),
        "P:n2": GraphNodeId("n2"),
    },
    residual_to_node={
        "mass_balance:n1": GraphNodeId("n1"),
        "mass_balance:n2": GraphNodeId("n2"),
    },
    residual_to_component={
        "pressure_drop:evap": ComponentInstanceId("evap"),
        "pressure_drop:cond": ComponentInstanceId("cond"),
    },
)

# Build a validated, immutable binding context.
assembly = assemble_network_residuals(graph)
ctx = build_binding_context(graph, assembly, bindings, state_map)

print(ctx.graph)          # NetworkGraph topology
print(ctx.binding_set)    # ComponentBindingSet — binding declarations
print(ctx.state_map)      # ComponentStateMap — name-to-ID declarations
```

`build_binding_context` validates that:

- Every component instance in the graph has exactly one binding (missing or
  extra bindings are rejected).
- Every mapped unknown/residual name is declared by the supplied assembly.
- Every component ID in the state map exists in the graph.
- Every node ID in the state map exists in the graph.

`ComponentBinding` is frozen and carries no executable state:

```python
b = ComponentBinding(
    instance_id=ComponentInstanceId("evap"),
    binding_name="my_evaporator_label",
    metadata={"info": "optional opaque caller data"},
)
# b.metadata is a MappingProxyType — read-only, defensively copied.
```

`ComponentStateMap` stores only ID references, never numerical values:

```python
sm = ComponentStateMap(
    unknown_to_component={"mdot:evap": ComponentInstanceId("evap")},
    unknown_to_node={"P:n1": GraphNodeId("n1")},
)
# sm.unknown_to_component is a MappingProxyType — read-only.
```

**What this is:**
- An explicit declaration layer: component instances are bound to caller
  labels; unknown/residual names are mapped to component and node IDs.
- Bindings are declarations only — they carry no executable component logic.
- All objects are immutable; all mappings are defensively copied.
- A preparation step toward Phase 14C minimal physical single-loop residual
  construction.

**What this is NOT:**
- Does NOT execute component instances or call any component method.
- Does NOT call the frozen `contribute(...)` component contribution method.
- Does NOT look up fluid properties — no CoolProp, no `PropertyBackend`.
- Does NOT call `CorrelationRegistry` or any correlation registry.
- Does NOT construct physical residuals automatically from component physics.
- Does NOT attach physical state (`FluidState`, mdot, pressure, enthalpy) to
  graph nodes.
- Does NOT store numerical unknown values.
- Does NOT infer residual form from `component_type`.
- Does NOT implement `solve(network)`.
- Is NOT a full MPL network simulator — physical residual logic must still be
  supplied entirely by the caller through explicit adapter callbacks (Phase 14A).
- Is NOT validation against experiment or literature data.

---

## Minimal Component Contribution Adapter Foundation (Phase 14C)

`mpl_sim.network` exports an explicit adapter layer that allows caller-supplied
component contribution callbacks to be declared and converted into Phase 14A
`PhysicalResidualAdapter` objects.  **This is a contribution-adapter foundation
only — it does NOT execute real component classes, does NOT call
`Component.contribute(...)`, does NOT assemble `SystemState`, and does NOT build
physical residuals automatically from `component_type`.**

```python
from mpl_sim.network import (
    ComponentContribution,
    ComponentContributionAdapter,
    ComponentContributionAdapterSet,
    ComponentContributionContext,
    ComponentInstanceId,
    build_physical_adapters_from_contributions,
    build_network_residual_evaluators,
    evaluate_network_residuals,
    NetworkUnknownValues,
)

# Assume `binding_context` is a NetworkBindingContext built in Phase 14B.
# The graph has components "evap" and "cond"; the assembly declares:
#   unknowns: mdot:evap, mdot:cond, P:n1, P:n2
#   residuals: mass_balance:n1, mass_balance:n2,
#              pressure_drop:evap, pressure_drop:cond

# Supply explicit contribution callbacks (not real component classes).
def evap_cb(ctx: ComponentContributionContext) -> ComponentContribution:
    v = ctx.unknown_values
    return ComponentContribution(
        residual_values={
            "mass_balance:n1": v["mdot:evap"] - v["mdot:cond"],
            "pressure_drop:evap": v["P:n1"] - v["P:n2"] - 600.0,
        }
    )

def cond_cb(ctx: ComponentContributionContext) -> ComponentContribution:
    v = ctx.unknown_values
    return ComponentContribution(
        residual_values={
            "mass_balance:n2": v["mdot:cond"] - v["mdot:evap"],
            "pressure_drop:cond": v["P:n2"] - v["P:n1"] + 1000.0,
        }
    )

# Declare one contribution adapter per bound component.
adapters = [
    ComponentContributionAdapter(
        instance_id=ComponentInstanceId("evap"),
        callback=evap_cb,
    ),
    ComponentContributionAdapter(
        instance_id=ComponentInstanceId("cond"),
        callback=cond_cb,
    ),
]

# Build PhysicalResidualAdapterSet from contribution adapters (Phase 14C → 14A).
physical_set = build_physical_adapters_from_contributions(
    binding_context, adapters
)

# Convert to Phase 13G evaluators via Phase 14A builder.
assembly = binding_context.assembly
evaluators = build_network_residual_evaluators(assembly, physical_set)

# One-shot Phase 13G evaluation (toy constants only, not real physics).
uv = NetworkUnknownValues(
    values={"mdot:evap": 0.05, "mdot:cond": 0.05, "P:n1": 100_000.0, "P:n2": 99_000.0}
)
scales = {
    "mass_balance:n1": 0.01,
    "mass_balance:n2": 0.01,
    "pressure_drop:evap": 100.0,
    "pressure_drop:cond": 100.0,
}
result = evaluate_network_residuals(assembly, uv, evaluators, scales)
# → mass_balance:n1=0.0, mass_balance:n2=0.0,
#   pressure_drop:evap=400.0, pressure_drop:cond=0.0
```

`build_physical_adapters_from_contributions` validates that:

- Every component instance bound in the `NetworkBindingContext` has exactly one
  contribution adapter (missing adapters are rejected).
- No contribution adapter references a component not bound in the context
  (extra/unbound adapters are rejected).

At evaluation time the generated physical adapter callbacks validate:

- All residual names returned by contribution callbacks are declared in the
  assembly (undeclared names raise `ValueError`).
- The specific residual requested by each physical adapter is provided by at
  least one contribution callback (missing residual raises `ValueError`).
- Each contribution callback returns a `ComponentContribution` (wrong return
  type raises `TypeError`).

**What this is:**
- An explicit adapter layer: caller-supplied contribution callbacks are bound to
  component instance IDs and converted into Phase 14A `PhysicalResidualAdapter`
  objects.
- These callbacks are explicit and caller-supplied — they are NOT the existing
  component `contribute(...)` API.
- Generated physical adapters preserve assembly residual declaration order.
- All objects are immutable; metadata is defensively copied.
- A preparation step toward future controlled component contribution integration.

**What this is NOT:**
- Does NOT execute real component classes.
- Does NOT call the frozen `contribute(...)` component contribution method.
- Does NOT assemble `SystemState` or `FluidState`.
- Does NOT compute or look up thermodynamic properties — no CoolProp, no
  `PropertyBackend`.
- Does NOT call `CorrelationRegistry` or any registry.
- Does NOT construct physical residuals automatically from `component_type`.
- Does NOT attach physical state to graph nodes.
- Does NOT implement `solve(network)`.
- Is NOT a full MPL network simulator.
- Is NOT validated against experiment or literature data.

---

## Component Contribution Contract Adapter Prep (Phase 14D)

`mpl_sim.network` exports small, explicit, value-object style contracts for
contribution records and contribution-to-residual mapping.  **This is a
contract adapter preparation layer only — it does NOT execute real component
classes, does NOT call `Component.contribute(...)`, does NOT assemble
`SystemState`, does NOT perform property lookup, and does NOT infer physics
from `component_type`.**

```python
from mpl_sim.network import (
    ContributionRecord,
    ContributionRecordSet,
    ContributionResidualMap,
    map_contribution_records_to_component_contribution,
    ComponentInstanceId,
    ComponentContribution,
)

evap_id = ComponentInstanceId("evap")

# Explicit value objects — not real component output, not property lookup.
record_set = ContributionRecordSet(
    records=(
        ContributionRecord(component_id=evap_id, name="mass_balance", value=0.0),
        ContributionRecord(component_id=evap_id, name="pressure_drop", value=400.0),
    )
)

# Explicit name translation — no automatic physics from component_type.
residual_map = ContributionResidualMap(
    mapping={
        (evap_id, "mass_balance"): "mass_balance:n1",
        (evap_id, "pressure_drop"): "pressure_drop:evap",
    }
)

# Convert to Phase 14C ComponentContribution (explicit mapping only).
contribution = map_contribution_records_to_component_contribution(
    evap_id, record_set, residual_map
)
# → ComponentContribution(residual_values={"mass_balance:n1": 0.0,
#                                          "pressure_drop:evap": 400.0})
```

The conversion function:

- Selects records belonging to the requested `ComponentInstanceId`.
- Translates each contribution name to a residual name using the explicit map.
- Rejects records with no mapping entry (missing mapping).
- Optionally rejects mappings to undeclared residuals when an allowed-names
  set is supplied.
- Rejects duplicate output residual names after mapping.
- Returns a Phase 14C `ComponentContribution` with `residual_values` in
  record-set insertion order.

**What this is:**
- Frozen value-object contracts for contribution records and residual-name
  translation.
- An explicit preparation layer that describes how future real component
  contribution outputs can be adapted into the Phase 14C contribution-adapter
  stack.
- Compatible with Phase 14C `ComponentContributionAdapter` callbacks: a
  callback may call `map_contribution_records_to_component_contribution`
  with a pre-built `ContributionRecordSet` and `ContributionResidualMap`.
- A preparation step toward future controlled component contribution
  integration (Phase 14E+).

**What this is NOT:**
- Does NOT execute real component classes.
- Does NOT call `Component.contribute(...)`.
- Does NOT assemble `SystemState` or `FluidState`.
- Does NOT compute or look up thermodynamic properties — no CoolProp, no
  `PropertyBackend`.
- Does NOT call `CorrelationRegistry` or any registry.
- Does NOT construct physical residuals automatically from `component_type`.
- Does NOT attach physical state to graph nodes.
- Does NOT implement `solve(network)`.
- Is NOT a full MPL network simulator.
- Is NOT validated against experiment or literature data.

---

## What is NOT implemented

| Capability | Status |
|---|---|
| Minimal fixed-architecture energy closure | Implemented in Phase 13A (`mpl_sim.closed_loop`) |
| Minimal fixed-architecture pressure closure | Implemented in Phase 13B (`mpl_sim.closed_loop`) |
| Residual/unknown/scaling framework | Implemented in Phase 13C (`mpl_sim.closed_loop`) |
| Coupled energy+pressure closure | Implemented in Phase 13D (`mpl_sim.closed_loop`) |
| Network graph / topology representation | Implemented in Phase 13E (`mpl_sim.network`) |
| Network residual assembly foundation | Implemented in Phase 13F (`mpl_sim.network`) |
| Network residual evaluation foundation | Implemented in Phase 13G (`mpl_sim.network`) |
| Configurable network solver v1 | Implemented in Phase 13H (`mpl_sim.network`) |
| Physical residual adapter foundation | Implemented in Phase 14A (`mpl_sim.network`) |
| Component binding and state-vector mapping | Implemented in Phase 14B (`mpl_sim.network`) |
| Minimal component contribution adapter foundation | Implemented in Phase 14C (`mpl_sim.network`) |
| Component contribution contract adapter prep | Implemented in Phase 14D (`mpl_sim.network`) |
| Generic network solver (`solve(network)`) | Deferred (Phase 14E+) |
| Controlled toy component execution harness | Deferred (Phase 14E) |
| Parallel evaporators, valves, manifolds, recuperator | Deferred (Phase 14E+) |
| Property lookup (CoolProp/REFPROP) in HX/component layers | Not in scope for these layers |
| Moving-boundary model | Deferred |
| Automatic phase inference | Not planned for this layer |
| Validation against experimental data | Deferred (Phase 12+ validation harness) |
| Dynamic/transient simulation | Deferred |
| Remaining boiling/condensation HTC closures | Deferred |
| Homogeneous/Cicchitti, Kim-Mudawar 2013 DP | Deferred |
