# Quickstart

This guide answers the ten most common entry-point questions for `mpl-loop-sim`.

---

## 1. What is `mpl-loop-sim`?

`mpl-loop-sim` is a modular, explicit-input thermo-hydraulic simulation library for mechanically pumped two-phase loops (MPLs) and related systems (pumped two-phase loops, electronics-cooling loops, space thermal-control systems).

It is a **research and engineering development library**, not an end-user simulation tool.
Its current strength is a clean, explicit, well-tested HX/component/correlation architecture with no hidden defaults and no automatic property lookup.

---

## 2. What can it currently do?

- Represent primary-fluid states as explicit `(P, h, identity)` triples — no property lookup required.
- Evaluate heat exchangers using three model strategies:
  - `EpsilonNTUModel` — lumped ε-NTU, supports all four secondary BCs.
  - `LMTDModel` — limited foundation, supports `FixedWallTemp` and `AmbientCoupling`.
  - `SegmentedMarchModel` — cell-by-cell march, supports all four secondary BCs including iterated counterflow.
- Inject heat transfer (`DittusBoelterHTC`, `GnielinskiHTC`, `ShahBoilingHTC`, `YanCondensationHTC`) and pressure-drop (`ChurchillFrictionGradient`, `MSHTwoPhaseFrictionGradient`) correlations explicitly.
- Evaluate `EvaporatorComponent` and `CondenserComponent` through scenario bindings.
- Assemble a minimal forward evaporator-to-condenser path and report energy imbalance explicitly.
- Solve a minimal closed loop for energy closure: find the condenser heat rate `Q_cond` such that `h_return = h_reference` using bounded bisection (`solve_minimal_closed_mpl`).
- Solve a minimal closed loop for pressure closure: find the primary mass flow `primary_mdot` such that `pump_head(mdot) = dP_total(mdot)` using bounded bisection (`solve_minimal_pressure_closure`). Energy residual is reported as a diagnostic (Phase 13B, Option A).
- Run 3700+ deterministic, property-lookup-free tests.

---

## 3. What can it NOT yet do?

- **Fixed-architecture closures only.** Both `solve_minimal_closed_mpl` (energy) and `solve_minimal_pressure_closure` (pressure) operate on a fixed one-evaporator + one-condenser architecture. Generic network topology, combined pressure+energy closure (Phase 13C), and multi-component loops remain deferred.
- **No network solver.** Components cannot be connected through an arbitrary flow-pressure network.
- **No property lookup.** `FluidState` carries only `(P, h, identity)`; no CoolProp or REFPROP call occurs in the HX/component/correlation layers.
- **No moving-boundary model.** Two-phase zone tracking is not implemented.
- **No automatic phase inference or quality marching.**
- **Not validated against experiments.** All test values are deterministic arithmetic results, not physical measurements.

These limitations are by design. The architecture is built so that these capabilities can be added cleanly in future phases.

---

## 4. How do I run the tests?

```bash
pytest
```

To run focused suites:

```bash
pytest tests/correlations       # correlation arithmetic and contract tests
pytest tests/hx_models          # HX model strategy tests
pytest tests/components         # component wrapper tests
pytest tests/loops -v           # Phase 12A minimal loop acceptance tests
pytest tests/examples -v        # Phase 12B example smoke tests
```

Lint and format checks:

```bash
ruff check src tests examples
black --check --no-cache src tests examples
```

---

## 5. How do I run the examples?

```bash
python examples/minimal_evaporator_condenser_loop.py
python examples/fixed_heat_rate_hx.py
python examples/segmented_counterflow_hx.py
python examples/minimal_closed_mpl_solver.py
python examples/minimal_pressure_closure.py
```

All five examples are standalone scripts. They print diagnostics to stdout, write no files, and make no network or property-lookup calls.

---

## 6. What is the simplest example?

The simplest example is [`examples/fixed_heat_rate_hx.py`](../../examples/fixed_heat_rate_hx.py).

It creates a `FluidState`, configures an `EvaporatorComponent` with a `FixedHeatRate` BC, and evaluates the outlet enthalpy and pressure drop in one call.

```python
from mpl_sim.components import ComponentId, EvaporatorComponent, EvaporatorScenarioBinding
from mpl_sim.core import FluidState, PureFluid
from mpl_sim.discretization import DiscretizationMode, DiscretizationSpec
from mpl_sim.geometry import FinGeometry, MicrochannelGeometry
from mpl_sim.hx_models import EpsilonNTUModel, FixedHeatRate

fluid = PureFluid(name="R134a")
inlet = FluidState(P=600_000.0, h=220_000.0, identity=fluid)

component = EvaporatorComponent(
    component_id=ComponentId(name="evap"),
    geometry=MicrochannelGeometry(
        N_channels=16, D_h_channel=0.0008,
        fin_geometry=FinGeometry(fin_pitch=400.0, fin_height=0.008, fin_thickness=0.00015),
        A_heated=0.04, wall_mass=0.15, wall_material="aluminium",
    ),
)
scenario = EvaporatorScenarioBinding(
    secondary_bc=FixedHeatRate(Q=750.0),
    model=EpsilonNTUModel(),
    discretization=DiscretizationSpec(mode=DiscretizationMode.LUMPED),
)
result = component.evaluate_scenario(inlet, primary_mdot=0.04, scenario=scenario)
print(f"Q = {result.Q:.1f} W, h_out = {result.primary_state_out.h:.1f} J/kg")
```

---

## 7. What are the core concepts?

See [`CONCEPTS.md`](CONCEPTS.md) for the full explanation. Summary:

| Concept | Role |
|---|---|
| `FluidState(P, h, identity)` | Primary-fluid state. Carries only pressure, enthalpy, and identity; no derived properties. |
| `SecondaryFluidBC` | What the secondary side does to the primary: `FixedHeatRate`, `SinkInletTempAndFlow`, `FixedWallTemp`, `AmbientCoupling`. |
| `HeatExchangerModel` | Strategy for computing Q and ΔP: `EpsilonNTUModel`, `LMTDModel`, `SegmentedMarchModel`. |
| `Correlation` | A closure computing HTC or ΔP/ΔP/m from explicit scalar inputs. No component or geometry object enters a correlation. |
| `EvaporatorComponent` / `CondenserComponent` | Wrappers that hold geometry and delegate to injected HX models. |
| `EvaporatorScenarioBinding` | Immutable scenario config binding a secondary BC, model, discretization, and optional correlations. |
| `HXSolveRequest` / `HXSolveResult` | The contract between a component wrapper and an HX model. |
| `geom_scalars` | Flat `dict[str, float]` carrying explicit physical scalars (Re, Pr, k, D_h, G, x, …) for correlation input. |

---

## 8. How do HX models, components, correlations, and explicit inputs relate?

```
  Caller
    │
    ├── FluidState (P, h, identity)           ← primary inlet
    ├── primary_mdot [kg/s]                   ← explicit
    ├── EvaporatorScenarioBinding             ← immutable config
    │       ├── secondary_bc                  ← what the secondary side does
    │       ├── model (EpsilonNTUModel etc.)  ← HX strategy
    │       ├── geom_scalars                  ← explicit physical scalars
    │       └── htc_primary / dp_primary      ← injected correlations (optional)
    │
    ▼
  EvaporatorComponent.evaluate_scenario(...)
    │
    ├── builds HXSolveRequest
    └── calls model.solve(request)
            │
            ├── builds HTCInput / DPInput from geom_scalars
            ├── calls injected correlation.evaluate(input)
            └── returns HXSolveResult (Q, h_out, dP, verdicts, zone_profile)
```

No property lookup, no registry resolution, no hidden defaults occur in this path.

---

## 9. What are the architecture boundaries?

| Boundary | Rule |
|---|---|
| CoolProp / REFPROP | Only in `mpl_sim.properties`. Not in HX models, components, or correlations. |
| `FluidState` | Carries only `(P, h, identity)`. No derived property fields. |
| Correlations | Receive only `CorrelationInput` objects and explicit scalars. Never receive a Component or Geometry. |
| Calibration | Never inside a correlation. Applied as a multiplier after the correlation call. |
| Network topology | Only in `mpl_sim.network`. Components do not know their neighbours or the network. |
| Generic Solver | Only in `mpl_sim.solvers`. Network never knows the solver; solver never knows physics. Phase 13A's `mpl_sim.closed_loop` API is a fixed case-specific orchestration helper, not the generic Network/Solver path. |
| `SystemState` | The only owner of numerical state values. Not the ports or components. |

---

## 10. What is the recommended next step for users / developers?

**For users exploring the library:**

1. Run `pytest` to verify the baseline.
2. Run the four examples in [`examples/`](../../examples/).
3. Read [`CONCEPTS.md`](CONCEPTS.md) for the mental model.
4. Read [`EXAMPLES.md`](EXAMPLES.md) for annotated walkthroughs.

**For developers continuing the library:**

1. Check `docs/roadmap/PROJECT_STATUS.md` for the current phase and deferred items.
2. Check `docs/roadmap/IMPLEMENTATION_PLAN.md` for the authoritative phase order.
3. The next recommended directions are:
   - Combined pressure + energy closure (Phase 13C): solve mdot and Q_cond simultaneously.
   - Remaining two-phase DP closures: Homogeneous/Cicchitti, Kim-Mudawar 2013.
   - Validation harness: pin literature data as acceptance tests.
4. Preserve the architecture boundaries in `docs/architecture/ARCHITECTURE_MASTER.md`.
5. Do not commit without running `pytest` + `ruff` + `black --check`.
