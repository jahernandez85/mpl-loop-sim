# Examples

Runnable example scripts for the `mpl-loop-sim` library.

All examples:
- are standalone scripts (run with `python examples/<name>.py`);
- are importable as modules with no side effects (logic guarded by `if __name__ == "__main__"`, or exposed as an `evaluate_example()` function);
- use only public `mpl_sim.*` package APIs;
- make no CoolProp or property-lookup calls;
- write no files;
- have corresponding smoke tests in `tests/examples/test_examples.py`.

---

## Examples

### `minimal_evaporator_condenser_loop.py` (Phase 12A)

Demonstrates a minimal evaporator-condenser forward pass.

- Wires `EvaporatorComponent` and `CondenserComponent` end-to-end.
- Reports energy imbalance (`net_Q`, `net_dh`) explicitly — loop is not closed.
- Uses `EpsilonNTUModel` + `FixedHeatRate` BC.
- Provides `MinimalLoopResult` frozen dataclass and
  `evaluate_minimal_evaporator_condenser_loop(...)` for use in tests and downstream scripts.

**Not:** a converged loop solution, a network solver, or a validated model.

---

### `fixed_heat_rate_hx.py` (Phase 12B)

Demonstrates a single-component ε-NTU evaluation with a `FixedHeatRate` BC.

- Creates a `FluidState`, configures an `EvaporatorComponent`, and evaluates outlet enthalpy
  and pressure drop in one call.
- Shows the deterministic arithmetic: `h_out = h_in + Q / mdot`.

**Not:** a validated physical design, a full-loop solve, or property-lookup-backed.

---

### `segmented_counterflow_hx.py` (Phase 12B)

Demonstrates `SegmentedMarchModel` with iterated counterflow.

- Uses `SinkInletTempAndFlow` + `FlowArrangement.COUNTERFLOW` +
  `CounterflowIterationConfig(enabled=True)`.
- Injects `DittusBoelterHTC` (primary and secondary) and `ChurchillFrictionGradient` (DP) explicitly.
- Prints `Q`, `h_out`, `dP_primary`, `converged`, `residual`, and `iteration_count`.
- All geom_scalars are explicit caller-supplied constants.

**Not:** a validated physical design, a full-loop solve, or property-lookup-backed.

---

### `minimal_closed_mpl_solver.py` (Phase 13A)

Demonstrates the first minimal closed-loop MPL energy closure.

- Solves for condenser heat rate `Q_cond` such that `h_return = h_reference` (energy closure).
- Fixed architecture: `reference_state -> evaporator -> condenser -> return`.
- Uses bounded bisection with an explicit bracket; bracket sign change validated at startup.
- Reports `converged`, `iterations`, `energy_residual`, `solved_q_cond`, and `dP_total` (diagnostic).
- All inputs explicit; no hidden defaults; no property lookup.

**Not:** a generic network solver, a pressure-closed loop, a validated physical model.

---

### `minimal_pressure_closure.py` (Phase 13B)

Demonstrates the minimal fixed-architecture pressure closure.

- Solves for primary mass flow rate `primary_mdot` such that `pump_head(mdot) = dP_total(mdot)` (pressure closure).
- Fixed architecture: `reference_state -> evaporator -> condenser`.
- Explicit `PumpHeadCurve` (linear curve); no hidden pump model.
- Explicit primary flow areas and pressure-drop closures; trial mass flux is
  recomputed from `primary_mdot` for each heat exchanger evaluation.
- Uses bounded bisection with an explicit `mdot_bounds` bracket.
- Reports `converged`, `iterations`, `evaluations`, `pressure_residual`, `solved_primary_mdot`, `pump_head`, `dP_total`.
- Energy residual `h_return - h_reference` is reported as a diagnostic only (Option A; not solved).
- All inputs explicit; no hidden defaults; no property lookup.

**Not:** a generic network solver, a combined pressure+energy solver (Phase 13C), a validated physical model.

---

## Running examples

```bash
python examples/minimal_evaporator_condenser_loop.py
python examples/fixed_heat_rate_hx.py
python examples/segmented_counterflow_hx.py
python examples/minimal_closed_mpl_solver.py
python examples/minimal_pressure_closure.py
```

## Running example tests

```bash
pytest tests/examples -v
```

## Further reading

- [`docs/user_guide/QUICKSTART.md`](../docs/user_guide/QUICKSTART.md) — entry-point guide
- [`docs/user_guide/CONCEPTS.md`](../docs/user_guide/CONCEPTS.md) — core concepts
- [`docs/user_guide/EXAMPLES.md`](../docs/user_guide/EXAMPLES.md) — annotated example walkthroughs
