# Roadmap

This file is a short roadmap pointer.

The previous coarse roadmap has been superseded. The authoritative implementation sequence is `docs/roadmap/IMPLEMENTATION_PLAN.md`. The current project state is tracked in `docs/roadmap/PROJECT_STATUS.md`.

## Authoritative Roadmap

For coding work, always follow `docs/roadmap/IMPLEMENTATION_PLAN.md`.

`IMPLEMENTATION_PLAN.md` defines the V1 Build Phases 0-14 and is the source of truth for implementation order. Do not use this file to decide what to build next.

## Current Status

- Phase 0 is complete.
- Phase 1 is complete and audited.
- Phase 2 property layer is complete and audited.
- Phase 3 correlation layer foundation is complete and audited.
- Phase 4 geometry/discretization foundation is complete and audited.
- Phase 5A calibration primitives and registry are complete and audited.
- Phase 6 Pipe component is complete and finally audited.
- Phase 7 - Network and Assembly is complete and audited.
- Phase 8 - First Steady Solver is complete and finally audited.
- Phase 9 - Result and schema serialization is complete and finally audited.
- Phase 10 - Pump and Accumulator is complete. The final closeout on `phase-10b-pump-map-accumulator-law` is safe to merge into `main`.
- Phase 11 - HeatExchangerModel, Evaporator and Condenser is the next active phase after the Phase 10 merge.

## Component Implementation Timing

- Pipe component: V1 Build Phase 6.
- Pump and Accumulator: V1 Build Phase 10.
- `HeatExchangerModel`, Evaporator, and Condenser: V1 Build Phase 11.

Therefore, the absence of components in `src/mpl_sim/components/` at the end of Phase 2 is expected and correct.
The current presence of the Pipe skeleton plus single-phase friction, gravity, acceleration, mechanical pressure summary, and friction-only calibration placement helpers in `src/mpl_sim/components/` is expected and correct for the Phase 6 closeout.
The current presence of Network topology primitives, validation/graph checks, and `SystemState` assembly in `src/mpl_sim/network/` is expected and correct for the Phase 7 closeout.
The current presence of generic solver contract primitives, residual interface, assembled steady problem wrapper, convergence metadata, update interface, and fixed-point steady iteration in `src/mpl_sim/solvers/` is expected and correct for the Phase 8 closeout.
The current presence of result primitives, schema primitives, canonical serialization, validation invariant primitives, and safe serialization adapters is expected and correct for the Phase 9 closeout.
The current presence of Pump and Accumulator component foundations, prescribed pressure-rise and pressure-reference seams, pump map/command behavior, pump power/efficiency seam, shaft-speed/inertia named seam, accumulator `VolumePressureLaw` integration, PCA closure, `V_g` seam, network pressure-reference wiring, pump-driven accumulator-referenced loop acceptance shape, and component exports is expected and correct for the Phase 10 final closeout.

## Legacy Coarse Roadmap

Older references to coarse phases such as "Phase 2 - Steady-State Components" are historical and superseded.

They should not be used by AI agents or contributors for implementation sequencing. If phase-numbering ambiguity appears, use the Rosetta table in `docs/roadmap/IMPLEMENTATION_PLAN.md`.

## Instructions for AI Agents

- Read `docs/roadmap/PROJECT_STATUS.md` first.
- Read `docs/roadmap/IMPLEMENTATION_PLAN.md` second.
- Work only on the current active phase.
- Do not infer missing implementation tasks from this file.
- Do not implement components until the V1 Build Phase that schedules them.
- After merging the Phase 10 final closeout, start Phase 11 with `HeatExchangerModel`, Evaporator, and Condenser according to `IMPLEMENTATION_PLAN.md`.
- Keep dynamic simulation, controls, fitting, optimization, DOE generation, literature validation, and unplanned solver behavior changes deferred unless explicitly requested.
- Do not modify architecture or decision documents unless explicitly requested.
