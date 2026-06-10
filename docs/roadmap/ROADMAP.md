# Roadmap

## Current Stage

Architecture definition and literature consolidation.

## Phase 0 — Project Setup

- Create repository structure.
- Add literature-derived Markdown documents.
- Add legacy simulation references.
- Define modelling decisions.
- Define validation strategy.

## Phase 1 — Core Architecture

- Define `FluidState`.
- Define `Port`.
- Define base `Component` interface.
- Define geometry and mesh objects.
- Define correlation strategy interfaces.

## Phase 2 — Steady-State Components

- Implement `Pipe1D`.
- Implement `Pump`.
- Implement `AccumulatorSS`.
- Implement `Evaporator1D`.
- Implement `PlateCondenser1D`.
- Implement `Splitter` and `Mixer`.

## Phase 3 — Steady-State Loop Solver

- Assemble single-loop architecture.
- Solve pressure and mass-flow closure.
- Add pressure-drop calibration mode: `none` / `target`.
- Generate profiles for pressure, enthalpy, quality and temperature.

## Phase 4 — Validation

- Validate pipe pressure drop.
- Validate evaporator energy balance and outlet quality.
- Validate condenser heat rejection.
- Validate full loop against literature or experimental data.

## Phase 5 — Surrogate Model Generation

- Define input parameters.
- Generate DOE datasets.
- Run batch simulations.
- Train and test surrogate models.

## Phase 6 — Dynamic Extension

- Add dynamic accumulator.
- Add wall thermal capacitance.
- Add moving-boundary evaporator/condenser models.
- Add dynamic solver.

## Phase 7 — Control-Oriented Models

- Add linearization tools.
- Add reduced-order models.
- Prepare MPC-compatible state-space models.