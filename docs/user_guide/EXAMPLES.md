# Examples

Annotated walkthrough of the six runnable examples in [`examples/`](../../examples/).

---

## 1. Minimal Evaporator-Condenser Loop

**File:** [`examples/minimal_evaporator_condenser_loop.py`](../../examples/minimal_evaporator_condenser_loop.py)

**Run:**
```bash
python examples/minimal_evaporator_condenser_loop.py
```

**What it demonstrates:**

- Wire two components (`EvaporatorComponent`, `CondenserComponent`) end-to-end.
- Feed the evaporator primary outlet directly into the condenser inlet.
- Report the energy imbalance (`net_Q`, `net_dh`) explicitly — the loop is not closed.
- Collect non-`IN_ENVELOPE` correlation verdicts into a `warnings` tuple.

**Key function:**

```python
from examples.minimal_evaporator_condenser_loop import (
    MinimalLoopResult,
    evaluate_minimal_evaporator_condenser_loop,
)

result = evaluate_minimal_evaporator_condenser_loop(
    inlet_state=...,
    primary_mdot=0.05,
    evap_component=..., evap_scenario=...,
    cond_component=..., cond_scenario=...,
)
# result.Q_evap  > 0  (primary gains heat)
# result.Q_cond  < 0  (primary rejects heat)
# result.net_Q   != 0 (loop not closed)
# result.net_dh  != 0 (loop not closed)
```

**What it is NOT:**

- Not a converged loop solution.
- Not a network solver.
- `net_Q` and `net_dh` are energy-imbalance diagnostics, not physical residuals driving convergence.

---

## 2. Fixed-Heat-Rate HX

**File:** [`examples/fixed_heat_rate_hx.py`](../../examples/fixed_heat_rate_hx.py)

**Run:**
```bash
python examples/fixed_heat_rate_hx.py
```

**What it demonstrates:**

- Create a `FluidState` with explicit P and h.
- Configure an `EvaporatorComponent` with a `FixedHeatRate` BC.
- Evaluate outlet enthalpy and pressure drop.
- The result is deterministic: `h_out = h_in + Q / mdot`.

**Representative output:**

```
Q (result):         +750.0 W
h_out:              238.750 kJ/kg
dh (Q/mdot):        +18750.000 J/kg
dP_primary:         0.00 Pa
```

**When to use `FixedHeatRate`:**

When you want to prescribe the total heat exchange and observe its effect on the primary stream, without specifying a secondary fluid temperature or HTC correlation. Useful for:
- Checking the enthalpy arithmetic.
- Establishing a baseline before adding correlations.
- Testing the component assembly path.

---

## 3. Segmented Counterflow HX

**File:** [`examples/segmented_counterflow_hx.py`](../../examples/segmented_counterflow_hx.py)

**Run:**
```bash
python examples/segmented_counterflow_hx.py
```

**What it demonstrates:**

- Use `SegmentedMarchModel` with `SinkInletTempAndFlow`.
- Set `FlowArrangement.COUNTERFLOW` with `CounterflowIterationConfig(enabled=True)`.
- Inject `DittusBoelterHTC` (primary and secondary) and `ChurchillFrictionGradient` (DP) explicitly.
- Print heat rate, outlet enthalpy, `dP_primary`, `converged`, `residual`, and `iteration_count`.

**Representative output:**

```
Q (result):         +2688.01 W
h_out:              253.7603 kJ/kg
dP_primary:         16000.0000 Pa
Converged:          True
Iterations:         6
Final residual:     4.68e-06
All correlation verdicts: IN_ENVELOPE
```

**Key ingredients:**

| Ingredient | Supplied as |
|---|---|
| Primary inlet T | `primary_T_in=280.0` [K] in `HXSolveRequest` |
| Primary cp | `primary_cp=1500.0` [J/kg/K] |
| Primary thermal mode | `PrimaryThermalMode.FINITE_CAPACITY` |
| UA computation mode | `UAComputationMode.TWO_SIDED` |
| Flow arrangement | `FlowArrangement.COUNTERFLOW` |
| Iteration config | `CounterflowIterationConfig(enabled=True, max_iter=30, tolerance=1e-5)` |
| HTC scalars | `Re`, `Pr`, `k`, `n`, `D_h`, `G`, `x` in `geom_scalars` |
| DP scalars | `rho`, `mu`, `roughness`, `A_cs`, `L_cell` in `geom_scalars` |

**What it is NOT:**

- Not a full-loop convergence.
- Not a network solver.
- All scalars are explicit caller-supplied inputs, not looked up from property tables.
- The `converged` flag refers only to the secondary-temperature-profile fixed-point iteration within this single HX component — not to a loop-level energy balance.

---

## 4. Minimal Closed MPL Solver

**File:** [`examples/minimal_closed_mpl_solver.py`](../../examples/minimal_closed_mpl_solver.py)

**Run:**
```bash
python examples/minimal_closed_mpl_solver.py
```

**What it demonstrates:**

- The first actual closed-loop energy closure in the library.
- Solve for condenser heat rate `Q_cond` such that `h_return = h_reference` using bounded bisection.
- Fixed architecture: `reference_state -> evaporator -> condenser -> return`.
- Explicit bracket `(q_cond_lo, q_cond_hi)` must enclose the root (sign change validated at startup).
- Convergence reported via `converged`, `iterations`, and `energy_residual` fields.
- Pressure-drop accumulation is diagnostic only (`dP_total`); no pressure closure.

**Key API:**

```python
from mpl_sim.closed_loop import (
    ClosedLoopSolveConfig,
    MinimalClosedMPLCase,
    solve_minimal_closed_mpl,
)

case = MinimalClosedMPLCase(
    reference_state=...,
    primary_mdot=0.05,
    evap_component=..., evap_scenario=...,
    cond_component=..., cond_scenario=...,  # cond secondary_bc MUST be FixedHeatRate
    q_cond_bounds=(-5000.0, 0.0),           # explicit bracket; must enclose root
)
result = solve_minimal_closed_mpl(case, ClosedLoopSolveConfig(max_iter=60, tolerance=1e-3))
# result.converged          True when abs(energy_residual) <= tolerance
# result.solved_q_cond      Q_cond [W] that closes the energy balance
# result.energy_residual    h_return - h_reference [J/kg]
# result.dP_total           diagnostic only; no pressure closure
```

**Representative output:**

```
=== Minimal Closed MPL Solver (Phase 13A) ===

  Architecture: reference -> evaporator -> condenser -> return
  Solved unknown: Q_cond [W] via FixedHeatRate BC
  Solve condition: h_return = h_reference (energy closure)

  Solved Q_cond:      -1000.000015 W
  Energy residual:    -2.98e-04 J/kg
  Converged:          True
  Iterations:         26

NOTE: Phase 13A - fixed architecture; not a generic network solver.
      Pressure closure is NOT implemented; dP_total is diagnostic only.
```

**What it is NOT:**

- Not a generic network solver (fixed one-evaporator + one-condenser architecture only).
- Not a pressure-closed loop (dP_total is diagnostic).
- Not a validated physical model (no experimental data).
- Not a moving-boundary or quality-marching model.
- Not a multi-component loop (no parallel evaporators, valves, manifolds, or recuperator).

---

## 5. Minimal Pressure Closure Solver

**File:** [`examples/minimal_pressure_closure.py`](../../examples/minimal_pressure_closure.py)

**Run:**
```bash
python examples/minimal_pressure_closure.py
```

**What it demonstrates:**

- Phase 13B minimal fixed-architecture pressure closure.
- Solve for primary mass flow rate `primary_mdot` such that `pump_head(mdot) = dP_total(mdot)`.
- Explicit `PumpHeadCurve` value object (constant or linear pump curve; no hidden pump model).
- Explicit evaporator and condenser flow areas; trial mass flux is
  `G = primary_mdot / flow_area` for each component evaluation.
- Explicit primary-side pressure-drop closures for both heat exchangers.
- Fixed architecture: `reference_state -> evaporator -> condenser`.
- Explicit `mdot_bounds` bracket; sign change validated at startup.
- Pressure residual, pump head, and loop ΔP are all reported.
- Energy residual `h_return - h_reference` is reported as a diagnostic (Option A; not solved).

**Key API:**

```python
from mpl_sim.closed_loop import (
    MinimalPressureClosureCase,
    PressureClosureConfig,
    PumpHeadCurve,
    solve_minimal_pressure_closure,
)

pump = PumpHeadCurve(head_Pa=5625.0, slope_Pa_s_kg=100_000.0)

case = MinimalPressureClosureCase(
    reference_state=...,
    pump_head_curve=pump,
    evap_component=..., evap_scenario=..., evap_flow_area=0.01,
    cond_component=..., cond_scenario=..., cond_flow_area=0.02,
    mdot_bounds=(0.01, 0.50),  # explicit bracket; must enclose root
)
result = solve_minimal_pressure_closure(case, PressureClosureConfig(max_iter=60, tolerance=0.01))
# result.converged            True when abs(pressure_residual) <= tolerance
# result.evaluations          complete evaporator+condenser evaluations
# result.solved_primary_mdot  primary_mdot [kg/s] at pressure balance
# result.pressure_residual    pump_head - dP_total [Pa]
# result.pump_head            pump head at solution [Pa]
# result.dP_total             dP_evap + dP_cond [Pa]
# result.energy_residual      h_return - h_reference [J/kg] — diagnostic only
```

**Representative output:**

```
=== Minimal Pressure Closure Solver (Phase 13B) ===

  Solved primary_mdot:  0.050000 kg/s
  Pump head at solution:+625.0019 Pa
  dP_total (evap+cond): 624.9998 Pa
  Pressure residual:    +2.1e-03 Pa  [near zero when converged]
  Converged:            True
  Iterations:           19
  Evaluations:          21

  Energy residual (diagnostic only, NOT solved):
    h_return - h_reference = +4000.00 J/kg

NOTE: Phase 13B — fixed architecture; not a generic network solver.
      Pressure closure solves mdot, not Q_cond.  Energy balance is
      diagnostic only (Option A).
```

**What it is NOT:**

- Not a generic network solver (fixed one-evaporator + one-condenser architecture only).
- Not a combined pressure + energy solver (use `solve_minimal_coupled_closure` for that — Phase 13D).
- Not a validated physical model (no experimental data).
- Not a moving-boundary or quality-marching model.
- Not a multi-component loop (no parallel evaporators, valves, manifolds, or recuperator).
- Does not support arbitrary topology changes.

---

## 6. Minimal Coupled Fixed-Architecture Closure

**File:** [`examples/minimal_coupled_closure.py`](../../examples/minimal_coupled_closure.py)

**Run:**
```bash
python examples/minimal_coupled_closure.py
```

**What it demonstrates:**

- Phase 13D coupled fixed-architecture energy+pressure closure.
- Solve for **both** `Q_cond` and `primary_mdot` simultaneously:
  - `energy_residual   = h_return - h_reference = 0`
  - `pressure_residual = pump_head(mdot) - dP_total(mdot) = 0`
- Solver strategy: nested scalar bisection (Option A):
  - Outer: bisect `primary_mdot` for pressure closure.
  - Inner: at each outer trial, bisect `Q_cond` for energy closure.
- Explicit `PumpHeadCurve`; explicit `q_cond_bounds` and `mdot_bounds` brackets.
- Explicit evaporator and condenser flow areas; mass flux is `G = mdot / flow_area`.
- `ResidualVector` provides scaled convergence diagnostics (`max_abs_scaled`, `l2_scaled`, `is_converged`).
- All diagnostics explicit: both residuals, pump head, dP breakdown, HX results, state history.

**Key API:**

```python
from mpl_sim.closed_loop import (
    CoupledClosureConfig,
    MinimalCoupledClosureCase,
    PumpHeadCurve,
    solve_minimal_coupled_closure,
)

case = MinimalCoupledClosureCase(
    reference_state=...,
    pump_head_curve=PumpHeadCurve(head_Pa=5625.0, slope_Pa_s_kg=100_000.0),
    evap_component=..., evap_scenario=..., evap_flow_area=0.01,
    cond_component=..., cond_scenario=..., cond_flow_area=0.02,
    q_cond_bounds=(-500.0, 0.0),   # inner bracket for Q_cond [W]
    mdot_bounds=(0.01, 0.50),      # outer bracket for primary_mdot [kg/s]
)
config = CoupledClosureConfig(
    energy_tolerance=1e-6, pressure_tolerance=0.01,
    energy_scale=1000.0, pressure_scale=100.0,
    inner_max_iter=60, outer_max_iter=60,
)
result = solve_minimal_coupled_closure(case, config)
# result.converged              True if BOTH residuals below tolerance
# result.solved_q_cond          condenser heat rate [W] at solution
# result.solved_primary_mdot    primary mass flow [kg/s] at solution
# result.energy_residual        h_return - h_reference [J/kg]
# result.pressure_residual      pump_head - dP_total [Pa]
# result.residual_vector        ResidualVector with both evaluations and scales
# result.max_abs_scaled         L∞ norm of (energy/scale, pressure/scale)
# result.pump_head              [Pa] at solved_primary_mdot
# result.dP_total               dP_evap + dP_cond [Pa]
```

**What it is NOT:**

- Not a generic network solver — architecture is fixed at one evaporator + one condenser.
- Not arbitrary topology — no `Network`, `Node`, `Branch`, or `Junction` classes.
- Not validated against experimental data.
- Not a moving-boundary or quality-marching model.
- Does not support parallel evaporators, valves, manifolds, recuperators, or pre/post-heaters.
- Does not support arbitrary topology changes.

---

## Common Patterns

### Changing the HX model strategy

Swap `EpsilonNTUModel()` for `SegmentedMarchModel()` in the scenario binding:

```python
scenario = EvaporatorScenarioBinding(
    secondary_bc=FixedHeatRate(Q=1000.0),
    model=SegmentedMarchModel(),          # was EpsilonNTUModel()
    discretization=DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=8),
)
```

### Injecting a different HTC correlation

```python
from mpl_sim.correlations import GnielinskiHTC

scenario = EvaporatorScenarioBinding(
    secondary_bc=FixedHeatRate(Q=1000.0),
    model=EpsilonNTUModel(),
    discretization=DiscretizationSpec(mode=DiscretizationMode.LUMPED),
    htc_primary=GnielinskiHTC(),          # inject Gnielinski instead of Dittus-Boelter
    geom_scalars={"Re": 12_000.0, "Pr": 4.0, "k": 0.08, "D_h": 0.001},
)
```

### Checking correlation validity

```python
result = component.evaluate_scenario(inlet, mdot, scenario)
for v in result.verdicts:
    if v.verdict.status.name != "IN_ENVELOPE":
        print(f"  {v.metadata.name}: {v.verdict.status.name} — {v.verdict.detail}")
```

---

## What remains deferred

- Plotting (no matplotlib dependency yet).
- Phase-change examples with `ShahBoilingHTC` or `YanCondensationHTC` (require explicit quality scalars; `evaluate_scenario` path ready, dedicated example deferred).
- Automatic component execution and physical network residual construction
  (Phase 14D+). Phase 14A's callback adapters, Phase 14B's declarative
  component binding/state-name mappings, and Phase 14C's explicit
  component-contribution callback adapters have no dedicated runnable example
  in this guide.
- Parallel evaporators, valves, manifolds, recuperators, pre/post-heaters (Phase 14D+).
- Validation against published HX data (Phase 12+ validation harness, deferred).
