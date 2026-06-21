# MPL Loop Simulation Library

A modular, explicit-input thermo-hydraulic simulation library for mechanically pumped two-phase loops (MPLs) and related systems.

**Current state:** HX/component/correlation architecture is implementation-complete, with minimal fixed-architecture energy-closure, pressure-closure, and coupled energy+pressure-closure solvers, a physics-free network graph foundation, and 4000+ deterministic tests. Generic network solving, arbitrary-topology simulation, property lookup at the HX layer, moving-boundary modeling, and experimental validation remain deferred.

---

## What it can do now

- Represent primary-fluid states as explicit `(P, h, identity)` triples — no property lookup in the HX layer.
- Evaluate heat exchangers with three model strategies:
  - `EpsilonNTUModel` — lumped ε-NTU, all four secondary BCs.
  - `LMTDModel` — `FixedWallTemp` and `AmbientCoupling` only.
  - `SegmentedMarchModel` — cell-by-cell march, all four secondary BCs, including iterated counterflow.
- Inject HTC correlations: `DittusBoelterHTC`, `GnielinskiHTC`, `ShahBoilingHTC`, `YanCondensationHTC`.
- Inject DP correlations: `ChurchillFrictionGradient`, `MSHTwoPhaseFrictionGradient`.
- Evaluate `EvaporatorComponent` and `CondenserComponent` through immutable scenario bindings.
- Assemble and run a minimal evaporator-to-condenser forward pass.
- Solve the fixed `reference -> evaporator -> condenser -> return` architecture
  for condenser heat rate so that `h_return = h_reference` (energy closure).
- Solve the fixed `reference -> evaporator -> condenser` architecture for
  primary mass flow so that `pump_head(mdot) = dP_total(mdot)` (pressure closure).
  Energy residual is diagnostic in Phase 13B.
- Solve the fixed architecture for **both** `Q_cond` and `primary_mdot` simultaneously
  (coupled energy+pressure closure, Phase 13D) using nested scalar bisection.
  `ResidualVector` provides scaled convergence diagnostics.
- Represent unknowns and residuals with explicit names, units, scales, scaled
  vectors, and convergence norms through the Phase 13C residual framework.
- Represent configurable loop topology with the physics-free Phase 13E
  `NetworkGraph`, without solving or residual assembly.
- Run 4000+ deterministic, property-lookup-free tests.

## What it cannot do yet

- Generic full-loop convergence beyond the fixed one-evaporator + one-condenser
  architecture (residual assembly and configurable solving remain deferred).
- Parallel evaporators, valves, manifolds, recuperator, pre/post-heaters (deferred to Phase 14+).
- Network flow-pressure solving or arbitrary-topology simulation.
- Property lookup at the HX/component/correlation layer (CoolProp is only in `mpl_sim.properties`).
- Moving-boundary two-phase zone modeling.
- Automatic phase inference or quality marching.
- Experimental validation (no literature data pinned yet).

---

## Quick start

```bash
# Run all tests
pytest

# Run examples
python examples/minimal_evaporator_condenser_loop.py
python examples/fixed_heat_rate_hx.py
python examples/segmented_counterflow_hx.py
python examples/minimal_closed_mpl_solver.py
python examples/minimal_pressure_closure.py
python examples/minimal_coupled_closure.py

# Lint and format checks
ruff check src tests examples
black --check --no-cache src tests examples
```

See [`docs/user_guide/QUICKSTART.md`](docs/user_guide/QUICKSTART.md) for the full entry-point guide.

---

## Simplest example

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
print(f"Q = {result.Q:.1f} W,  h_out = {result.primary_state_out.h:.1f} J/kg")
# Q = 750.0 W,  h_out = 238750.0 J/kg
```

---

## Documentation

| Document | Purpose |
|---|---|
| [`docs/user_guide/QUICKSTART.md`](docs/user_guide/QUICKSTART.md) | Ten entry-point questions answered |
| [`docs/user_guide/CONCEPTS.md`](docs/user_guide/CONCEPTS.md) | Core abstractions: FluidState, BC, HX models, correlations |
| [`docs/user_guide/EXAMPLES.md`](docs/user_guide/EXAMPLES.md) | Annotated example walkthroughs |
| [`examples/README.md`](examples/README.md) | Example script index |
| [`docs/roadmap/PROJECT_STATUS.md`](docs/roadmap/PROJECT_STATUS.md) | Current phase, test counts, deferred items |
| [`docs/roadmap/IMPLEMENTATION_PLAN.md`](docs/roadmap/IMPLEMENTATION_PLAN.md) | Authoritative phase order |
| [`docs/architecture/ARCHITECTURE_MASTER.md`](docs/architecture/ARCHITECTURE_MASTER.md) | Frozen architectural decisions |

---

## Architecture philosophy

The library is built around five principles:

1. **Explicit inputs only.** No hidden defaults, no automatic property lookup in HX/component/correlation layers.
2. **Injected correlations.** HX models accept correlation objects as arguments; no registry resolution at evaluation time.
3. **Immutable value objects.** `FluidState`, `HXSolveRequest`, `HXSolveResult`, scenario bindings, and geometry are all frozen dataclasses.
4. **Honest diagnostics.** Energy imbalance, out-of-envelope verdicts, and non-convergence are always reported — never suppressed.
5. **Clean layer boundaries.** CoolProp stays in `properties/`; the generic
   network solver stays in `solvers/`; Phase 13A's `closed_loop` helper is a
   fixed case-specific orchestrator, not a generic Solver or Network; components
   do not know their neighbours.

---

## Target systems

- Mechanically Pumped Loops (MPL)
- Pumped Two-Phase Loops (P2PL)
- Electronics cooling loops
- Space thermal-control systems
- Experimental two-phase test benches

---

## Project status

Phase 13E — Network Graph Foundation.
The HX component family (Phases 11A–11U), fixed-architecture closure work
(Phases 13A–13D), and the Phase 13E physics-free topology representation are
complete checkpoints. Network residual assembly, configurable network solving,
validation harness work, and moving-boundary modeling remain deferred.

*Developed at Université de Liège — Andrés Hernández, 2026.*
