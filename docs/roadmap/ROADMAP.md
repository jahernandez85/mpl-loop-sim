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
- Phase 3 is next, starting with correlation contract primitives.
- Components are not skipped; they are scheduled later in the V1 build sequence.

## Component Implementation Timing

- Pipe component: V1 Build Phase 6.
- Pump and Accumulator: V1 Build Phase 10.
- `HeatExchangerModel`, Evaporator, and Condenser: V1 Build Phase 11.

Therefore, the absence of components in `src/mpl_sim/components/` at the end of Phase 2 is expected and correct.

## Legacy Coarse Roadmap

Older references to coarse phases such as "Phase 2 - Steady-State Components" are historical and superseded.

They should not be used by AI agents or contributors for implementation sequencing. If phase-numbering ambiguity appears, use the Rosetta table in `docs/roadmap/IMPLEMENTATION_PLAN.md`.

## Instructions for AI Agents

- Read `docs/roadmap/PROJECT_STATUS.md` first.
- Read `docs/roadmap/IMPLEMENTATION_PLAN.md` second.
- Work only on the current active phase.
- Do not infer missing implementation tasks from this file.
- Do not implement components until the V1 Build Phase that schedules them.
- Do not modify architecture or decision documents unless explicitly requested.
