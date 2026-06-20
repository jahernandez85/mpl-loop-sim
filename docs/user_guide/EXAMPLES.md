# Examples

Annotated walkthrough of the four runnable examples in [`examples/`](../../examples/).

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
- Pressure closure (Phase 13B): solving for pump head such that the loop ΔP balances.
- Generic network solver (Phase 13D): arbitrary topology, multiple parallel components.
- Validation against published HX data (Phase 12+ validation harness, deferred).
