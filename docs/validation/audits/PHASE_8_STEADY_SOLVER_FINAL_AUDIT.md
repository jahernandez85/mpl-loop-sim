# Phase 8 Steady Solver Final Audit

## Verdict

**APPROVED FOR MERGE AND NEXT PHASE**

## Summary

Phase 8A added solver contract primitives: `SolverId`, `SolverStatus`,
`SolverOptions`, `SolverReport`, and `SolverResult`.

Phase 8B added the generic residual evaluation interface:
`ResidualVector`, `ResidualEvaluation`, and `ResidualEvaluator`.

Phase 8C added the first minimal `SteadySolver` convergence-gate path.

Phase 8D added the generic assembled steady problem wrapper, explicit
convergence strategy metadata, and the state update interface.

Phase 8E added the fixed-point steady solver loop through
`StateUpdateProvider`, while preserving the no-update residual-gate behavior.

The completed Phase 8 solver remains generic and physics-free. It does not own
physical residuals, does not solve pressure or flow directly, and does not
implement Newton, Jacobians, schema serialization, transient solving, or new
components.

## Scope Audited

Source files inspected:

- `src/mpl_sim/solvers/base.py`
- `src/mpl_sim/solvers/residuals.py`
- `src/mpl_sim/solvers/problem.py`
- `src/mpl_sim/solvers/steady.py`
- `src/mpl_sim/solvers/updates.py`
- `src/mpl_sim/solvers/__init__.py`
- `src/mpl_sim/core/state.py`
- `src/mpl_sim/core/port.py`
- `src/mpl_sim/network/`
- `src/mpl_sim/components/`
- `src/mpl_sim/properties/`
- `src/mpl_sim/correlations/`
- `src/mpl_sim/geometry/`
- `src/mpl_sim/discretization/`
- `src/mpl_sim/calibration/`
- `pyproject.toml`

Test files inspected:

- `tests/solvers/test_solver_contract.py`
- `tests/solvers/test_residual_interface.py`
- `tests/solvers/test_assembled_problem.py`
- `tests/solvers/test_update_interface.py`
- `tests/solvers/test_steady_solver.py`
- `tests/solvers/test_fixed_point_solver.py`

Documentation files inspected:

- `docs/roadmap/PROJECT_STATUS.md`
- `docs/roadmap/IMPLEMENTATION_PLAN.md`
- `docs/roadmap/ROADMAP.md`
- `docs/architecture/ARCHITECTURE_MASTER.md`
- `docs/architecture/INTERFACE_SPEC.md`
- `docs/architecture/SCHEMA_SPEC.md`
- `docs/validation/TEST_PLAN_V1.md`
- `docs/decisions/DECISION_LOG.md`
- `docs/validation/audits/PHASE_6_PIPE_COMPONENT_FINAL_AUDIT.md`
- `docs/validation/audits/PHASE_7_NETWORK_ASSEMBLY_AUDIT.md`
- `docs/validation/audits/PHASE_8_STEADY_SOLVER_AUDIT.md`

## Audit Checklist

Solver contract primitives:

- Approved. `SolverId`, `SolverStatus`, `SolverOptions`, `SolverReport`, and
  `SolverResult` exist.
- `SolverId` rejects empty names.
- `SolverOptions` validates positive tolerance, positive maximum iterations,
  and positive relaxation when present.
- `SolverReport` and `SolverResult` are frozen, data-only records.
- `SolverReport` rejects non-finite residual norms.
- Solver contracts import only standard library modules and `SystemState` from
  core. They do not import physics layers.

Residual evaluation interface:

- Approved. `ResidualVector` stores values as an immutable tuple.
- Residual values reject NaN and positive or negative infinity.
- `inf_norm()` and `l2_norm()` are deterministic.
- `ResidualEvaluation` is immutable and rejects non-finite norms.
- `ResidualEvaluator` is generic over `SystemState`.
- Residual evaluation does not require components, network, `PropertyBackend`,
  correlations, calibration, or CoolProp.
- Residual logic is not placed inside Network or Pipe.

Assembled steady problem wrapper:

- Approved. `AssembledSteadyProblem` is a frozen, data-only wrapper.
- It contains a non-empty name, initial `SystemState`, residual evaluator, and
  optional description.
- It does not contain components, Pipe, Network, `NetworkTopology`,
  `PropertyBackend`, `CorrelationRegistry`, or `CalibrationRegistry`.
- It does not evaluate residuals on construction.
- Residual evaluation delegates only to the provided evaluator.

Convergence metadata:

- Approved. `ConvergenceStrategy` explicitly represents `RESIDUAL_GATE` and
  `FIXED_POINT`, plus declared future/custom vocabulary.
- `ConvergenceMetadata` records strategy, tolerance, maximum iterations,
  iterations, convergence flag, final residual norm, and optional message.
- Metadata rejects invalid tolerance, maximum iterations, iteration count, and
  non-finite or negative final residual norms.
- Metadata is immutable and data-only.
- `solve_problem()` reports `RESIDUAL_GATE`; the fixed-point path reports
  `FIXED_POINT`.

Update interface:

- Approved. `StateUpdate` and `StateUpdateProvider` exist.
- The update interface is generic and physics-free.
- Providers operate on `SystemState` and `ResidualEvaluation` only.
- Providers do not require components, network, `PropertyBackend`,
  correlations, calibration, or CoolProp.
- `StateUpdate.step_norm` rejects NaN, infinity, and negative values when
  present.
- Tests verify dummy providers return new candidate states without mutating the
  input `SystemState`.

Fixed-point steady solver:

- Approved. The no-update `solve()` path preserves Phase 8C residual-gate
  behavior and no convergence metadata.
- The `solve_problem()` no-update path preserves residual-gate behavior with
  explicit `RESIDUAL_GATE` metadata.
- The fixed-point path evaluates residuals, checks convergence, and then calls
  the update provider only when another candidate is needed.
- Already-converged initial states do not call the update provider.
- Non-converging fixed-point problems reach `MAX_ITERATIONS`.
- Converging dummy update providers reach `CONVERGED`.
- Final state and final residual norm are consistent with the same evaluation
  point.
- Iteration count semantics are documented and tested: with
  `max_iterations=N` and non-convergence, there are N residual evaluations,
  N-1 update-provider calls, final state equals the candidate from the N-1-th
  update, and final norm comes from the N-th evaluation.
- The solver copies the initial `SystemState` and does not mutate it.
- The solver does not accept components or Pipe directly.
- The solver does not call component physical helpers.
- The solver does not implement Newton, Jacobians, physical residuals, pressure
  solving, or flow solving.

Layer boundaries:

- Approved. Solvers do not import CoolProp, properties, correlations,
  calibration, components, network, geometry, or discretization.
- Approved. Network does not import solvers.
- Approved. Components do not import solvers.
- Approved. Properties, correlations, geometry, discretization, and calibration
  do not import solvers.
- Approved. Ports remain value-free.
- Approved. `SystemState` remains the only owner of stored values.
- Note. Import-boundary enforcement is still primarily test/review based rather
  than import-linter based.

Tests:

- Approved. Tests cover solver id construction and validation, solver options,
  solver status vocabulary, solver reports, solver results, residual vectors,
  residual evaluation, dummy evaluators, assembled problem wrapper behavior,
  convergence metadata, update interface behavior, residual-gate behavior,
  fixed-point convergence, fixed-point max-iteration behavior, update-provider
  call counts, deterministic iteration semantics, initial-state non-mutation,
  solver result contents, and import-boundary purity.
- The full suite passed.

Phase 8 completeness:

- Approved for current Phase 8 closeout. The completed implementation satisfies
  the planned first generic steady solver foundation now represented by Phase
  8A through Phase 8E: contract primitives, residual interface, assembled
  problem wrapper, convergence metadata with strategy reporting, update
  interface, and fixed-point steady iteration.
- Newton, finite-difference Jacobians, physical residual assembly,
  pressure/flow solving, validation invariants, and Result/schema
  serialization remain deferred. They are not blockers before merging this
  branch because this closeout explicitly preserves solver genericity and does
  not start Phase 9.
- Schema serialization is the next planned phase and is out of scope for this
  audit.
- Transient solving, optimization, fitting, advanced component models, and new
  components remain out of scope.

Branch merge readiness:

- `phase-8-solver` is safe to merge into `main`.
- No minor fixes are required before merge.
- The project is ready to advance to **Phase 9 - Result and schema
  serialization** after the merge.

## Findings

### Critical Findings

None.

### Major Findings

None.

### Minor Findings

- Import-direction enforcement remains test/review based. Add import-linter or
  equivalent if cross-layer growth increases the risk of accidental DAG
  violations.
- The no-update direct `solve()` path intentionally has no convergence metadata,
  while `solve_problem()` carries `RESIDUAL_GATE` metadata. This is preserved by
  tests and is acceptable, but future public API cleanup may choose one
  metadata policy for all no-update entry points.

## Phase 8 Status

Phase 8 is complete for the first steady solver foundation now implemented on
`phase-8-solver`.

Completed:

- Phase 8A - solver contract primitives.
- Phase 8B - residual evaluation interface.
- Phase 8C - minimal convergence-gate steady solver.
- Phase 8D - assembled steady problem wrapper, convergence metadata, and update
  interface.
- Phase 8E - fixed-point steady iteration through the update interface.

Deferred:

- Newton and finite-difference Jacobians.
- Physical residual assembly from components and network closure conditions.
- Direct pressure solving and flow solving.
- Validation invariants.
- Result and schema serialization.
- Transient solving.
- Optimization, fitting, and advanced component models.
- Pump, accumulator, evaporator, condenser, and heat-exchanger components.

These deferred items are acceptable planned work, not blockers before merge.

## Merge Readiness

`phase-8-solver` can be merged into `main`.

The branch contains a generic, physics-free solver foundation with fixed-point
iteration semantics documented and tested. No source or test code was changed
during this audit closeout.

## Next Phase Readiness

The project is ready to advance to **Phase 9 - Result and schema
serialization**, as named in `IMPLEMENTATION_PLAN.md`, after this branch is
merged.

Phase 9 should focus on schema/result serialization and validation invariants
without extending solver physics or component models.

## Recommended Follow-ups

- Keep solver core generic and physics-free.
- Introduce Newton and Jacobians only when explicitly planned.
- Keep physical residual adapters separate from solver core.
- Keep Network solver-free.
- Keep components solver-free.
- Add import-linter or equivalent if import-boundary risks grow.
- Keep schema serialization in Phase 9, not in Phase 8 closeout.

## Verification

Commands run on 2026-06-16:

- `pytest` - passed: 1519 passed, 1 warning. Warning: pytest could not create
  `.pytest_cache\v\cache\nodeids` on Windows due to access denied.
- `ruff check .` - passed: all checks passed.
- `black --check src tests` - passed: 76 files would be left unchanged.

`black --check src tests` was used as the formatting gate and avoids the known
`.pytest_cache` Windows permission issue that can affect broader checks on this
machine.

## Files Inspected

- `docs/roadmap/PROJECT_STATUS.md`
- `docs/roadmap/IMPLEMENTATION_PLAN.md`
- `docs/roadmap/ROADMAP.md`
- `docs/architecture/ARCHITECTURE_MASTER.md`
- `docs/architecture/INTERFACE_SPEC.md`
- `docs/architecture/SCHEMA_SPEC.md`
- `docs/validation/TEST_PLAN_V1.md`
- `docs/decisions/DECISION_LOG.md`
- `docs/validation/audits/PHASE_6_PIPE_COMPONENT_FINAL_AUDIT.md`
- `docs/validation/audits/PHASE_7_NETWORK_ASSEMBLY_AUDIT.md`
- `docs/validation/audits/PHASE_8_STEADY_SOLVER_AUDIT.md`
- `src/mpl_sim/solvers/base.py`
- `src/mpl_sim/solvers/residuals.py`
- `src/mpl_sim/solvers/problem.py`
- `src/mpl_sim/solvers/steady.py`
- `src/mpl_sim/solvers/updates.py`
- `src/mpl_sim/solvers/__init__.py`
- `src/mpl_sim/core/state.py`
- `src/mpl_sim/core/port.py`
- `src/mpl_sim/network/`
- `src/mpl_sim/components/`
- `src/mpl_sim/properties/`
- `src/mpl_sim/correlations/`
- `src/mpl_sim/geometry/`
- `src/mpl_sim/discretization/`
- `src/mpl_sim/calibration/`
- `tests/solvers/test_solver_contract.py`
- `tests/solvers/test_residual_interface.py`
- `tests/solvers/test_assembled_problem.py`
- `tests/solvers/test_update_interface.py`
- `tests/solvers/test_steady_solver.py`
- `tests/solvers/test_fixed_point_solver.py`
- `pyproject.toml`
