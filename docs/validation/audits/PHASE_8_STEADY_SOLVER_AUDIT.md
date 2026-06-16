# Phase 8 Steady Solver Audit

## Verdict

**APPROVED FOR MERGE AS PHASE 8 CHECKPOINT — CONTINUE PHASE 8**

## Summary

Phase 8A added solver contract primitives: `SolverId`, `SolverStatus`,
`SolverOptions`, `SolverReport`, and `SolverResult`.

Phase 8B added a generic residual evaluation interface:
`ResidualVector`, `ResidualEvaluation`, and `ResidualEvaluator`.

Phase 8C added the first minimal `SteadySolver` foundation. It is intentionally
a convergence gate only: it evaluates the residual at the initial `SystemState`
once, returns `CONVERGED` if the norm is within tolerance, and otherwise returns
`FAILED` with the copied initial state. It does not update the state, assemble
physical residuals, perform fixed-point iteration, compute Jacobians, or run
Newton.

## Scope Audited

Source files inspected:

- `src/mpl_sim/solvers/base.py`
- `src/mpl_sim/solvers/residuals.py`
- `src/mpl_sim/solvers/steady.py`
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
- `tests/solvers/test_steady_solver.py`
- relevant cross-layer import-boundary tests in `tests/unit/`, `tests/network/`,
  `tests/components/`, `tests/property/`, `tests/correlation/`,
  `tests/geometry/`, `tests/discretization/`, and `tests/calibration/`

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

## Audit Checklist

Solver contract primitives:

- Approved for checkpoint. `SolverId`, `SolverStatus`, `SolverOptions`,
  `SolverReport`, and `SolverResult` exist.
- `SolverId` rejects empty names.
- `SolverOptions` validates positive tolerance, positive maximum iterations,
  and positive relaxation when present.
- `SolverReport` and `SolverResult` are frozen dataclasses and data-only.
- `SolverReport` rejects non-finite residual norms.
- Solver contract primitives import only standard library and `SystemState`
  from core. They do not import physics, properties, correlations, calibration,
  components, network, geometry, or CoolProp.

Residual evaluation interface:

- Approved for checkpoint. `ResidualVector` stores residual values as an
  immutable tuple and exposes no mutable backing collection.
- Residual values reject NaN and positive or negative infinity.
- `inf_norm()` and `l2_norm()` are deterministic.
- `ResidualEvaluation` is immutable and rejects non-finite norms.
- `ResidualEvaluator` is a generic abstract interface over `SystemState`.
- Residual evaluation does not require components, network, `PropertyBackend`,
  correlations, calibration, or CoolProp.
- Residual logic has not been placed inside Network or Pipe.

First minimal steady solver:

- Approved for checkpoint. `SteadySolver.solve()` consumes an initial
  `SystemState`, a `ResidualEvaluator`, and `SolverOptions`.
- The solver does not accept components or Pipe directly.
- The solver does not mutate the initial `SystemState`; it returns a copied
  final state.
- The solver returns `SolverResult`.
- Zero residual at the initial state converges immediately.
- Nonzero residual above tolerance fails clearly because Phase 8C has no update
  rule.
- Tolerance is respected, including equality at the threshold.
- `SolverReport` records iteration count and final residual norm.
- The solver does not implement Newton, Jacobians, physical residuals, pressure
  solving, flow solving, or component physical helper calls.

Phase 8 completeness check:

- Not complete. `IMPLEMENTATION_PLAN.md` Phase 8 requires fixed-point pressure
  iteration, simultaneous Newton as a first-class option, residual assembly from
  components and Network conditions, a finite-difference Jacobian seam,
  convergence metadata with strategy, non-convergence reporting, and a vertical
  slice green end-to-end.
- `INTERFACE_SPEC.md` section 13 requires `SteadyStateSolver.assemble()`,
  `AssembledProblem`, fixed-point pressure iteration, simultaneous
  Newton-Raphson, shared residual assembly, structured finite differences, and
  `ConvergenceMetadata {iterations, final_residual_norm, converged, strategy}`.
- The current convergence gate is architecturally safe but does not satisfy the
  full Phase 8 acceptance criteria.
- Missing fixed-point pressure iteration, assembled steady problem wrapper,
  physical residual assembly, finite-difference Jacobian, Newton option, and
  strategy-bearing convergence metadata are blockers before Phase 8 closeout.
  They are not blockers before merging this checkpoint.
- Validation invariants such as mass imbalance, energy imbalance, pressure
  closure, and physical bound checks remain deferred to Phase 9/result work per
  the current staged implementation, but the Phase 8 vertical-slice target still
  needs enough convergence metadata and residual reporting to support that next
  layer.
- Schema serialization, transient solving, optimization, fitting, advanced
  component models, and new components are out of scope for this audit.

Layer boundaries:

- Approved. Solvers do not import CoolProp, properties, correlations,
  calibration, components, network, geometry, or discretization.
- Approved. Network does not import solvers.
- Approved. Components do not import solvers.
- Approved. Properties, correlations, geometry, discretization, and calibration
  do not import solvers.
- Approved. Ports remain value-free.
- Approved. `SystemState` remains the owner of stored values.
- Note. Import-direction enforcement is still mostly test/review based rather
  than import-linter based.

Tests:

- Approved for checkpoint. Tests cover solver id construction, validation,
  equality, hashability, and immutability.
- Tests cover solver option construction, validation, equality, and
  immutability.
- Tests cover the solver status vocabulary.
- Tests cover solver report construction, finite residual norm validation, and
  immutability.
- Tests cover solver result construction and immutability.
- Tests cover residual vector construction, immutability-by-tuple, finite value
  validation, equality, hashability, and norm calculations.
- Tests cover residual evaluation construction, finite norm validation, and
  immutability.
- Tests cover dummy residual evaluator behavior and determinism.
- Tests cover steady solver immediate convergence for zero residual.
- Tests cover steady solver non-convergence behavior for nonzero residual.
- Tests cover no mutation of the initial `SystemState`.
- Tests cover solver result contents, report fields, tolerance semantics, and
  copied final state.
- Tests cover solver import-boundary purity and lower-layer non-dependence on
  solvers.
- The full suite passed.

Architecture consistency:

- Approved for checkpoint. The implementation preserves the frozen DAG: lower
  layers do not depend on numerics, and the solver layer does not embed physics.
- The convergence-gate solver is a safe scaffold because it exercises the
  solver-result and residual-evaluator contracts without prematurely coupling
  to components, Network, properties, correlations, or calibration.
- The checkpoint does not contradict the architecture, but it also does not
  fulfill the full solver interface described in `INTERFACE_SPEC.md` section 13.

Branch merge readiness:

- `phase-8-solver` is safe to merge into `main` as a Phase 8 checkpoint.
- The branch should not be described as a complete Phase 8 closeout.
- Phase 8 should remain active after merge.

## Findings

### Critical Findings

None.

### Major Findings

None.

### Minor Findings

- Phase 8 is incomplete relative to the authoritative Phase 8 scope. The
  current implementation lacks fixed-point iteration, assembled steady problem
  wrapping, physical residual assembly, finite-difference Jacobian support,
  Newton, and strategy-bearing convergence metadata. This is acceptable for a
  mergeable checkpoint but blocks Phase 8 closeout.
- Import-direction enforcement remains primarily test/review based rather than
  enforced by import-linter or equivalent tooling.
- `SolverReport` records status, iterations, residual norm, and message, but it
  is not the full `ConvergenceMetadata` shape because it lacks an explicit
  strategy field.

## Phase 8 Status

Phase 8 is partially complete but safe to merge.

Completed:

- Phase 8A - solver contract primitives.
- Phase 8B - residual evaluation interface.
- Phase 8C - minimal convergence-gate steady solver foundation.

Remaining Phase 8 items before closeout:

- Phase 8D - fixed-point pressure iteration / update interface.
- Phase 8D - assembled steady problem wrapper, including `AssembledProblem` and
  `SteadyStateSolver.assemble()` or an implementation-equivalent shape.
- Phase 8D - residual assembly from component contributions and Network
  continuity/closure conditions over `SystemState`.
- Phase 8D - convergence metadata with an explicit strategy field.
- Later Phase 8 slice - finite-difference Jacobian seam.
- Later Phase 8 slice - simultaneous Newton option, if kept in the current
  Phase 8 closeout scope as written.

## Merge Readiness

`phase-8-solver` can be merged into `main` as a Phase 8 checkpoint.

It should be merged with the understanding that Phase 8 remains active and the
next implementation work must continue solver assembly and iteration rather
than start Phase 9.

## Next Step

Continue Phase 8 with:

**Phase 8D - assembled steady problem wrapper, fixed-point pressure iteration /
update interface, and convergence metadata with strategy reporting.**

This slice should preserve the current solver purity: no direct CoolProp,
properties, correlations, calibration, component physical helpers, or Pipe
special cases inside solver numerics.

## Recommended Follow-ups

- Add an `AssembledProblem` or equivalent wrapper before physical residual
  assembly grows.
- Add an explicit strategy field to convergence reporting.
- Add the fixed-point/update interface before Newton.
- Keep Newton and finite-difference Jacobian work in Phase 8, but after the
  assembled residual path is stable.
- Add import-linter or equivalent enforcement before solver-layer growth makes
  manual import checks too easy to miss.
- Keep validation invariants, Result/schema serialization, transient solving,
  optimization, fitting, and new components deferred to their planned phases.

## Verification

Commands run on 2026-06-16:

- `pytest` - passed: 1361 passed, 1 warning. Warning: pytest could not create
  `.pytest_cache\v\cache\nodeids` on Windows due to access denied.
- `ruff check .` - passed: all checks passed.
- `black --check src tests` - passed: 71 files would be left unchanged.

`black --check .` was not used because the requested source/test formatting
gate is `black --check src tests`, which also avoids the known `.pytest_cache`
Windows permission issue.

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
- `src/mpl_sim/solvers/base.py`
- `src/mpl_sim/solvers/residuals.py`
- `src/mpl_sim/solvers/steady.py`
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
- `tests/solvers/test_steady_solver.py`
- `pyproject.toml`
