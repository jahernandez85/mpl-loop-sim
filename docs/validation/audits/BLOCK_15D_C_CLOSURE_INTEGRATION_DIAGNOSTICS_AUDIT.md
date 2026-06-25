# Block 15D-C Closure Integration and Diagnostics Audit

## Verdict

**APPROVED WITH MINOR FIXES.**

Block 15D-C correctly integrates the existing hydraulic and thermal closure
primitives as an evaluation, category-diagnostics, and plain-reporting layer.
It does not add a solver, combined physical residual assembly, property-backed
thermodynamics, HX-model execution, production component execution, or
arbitrary-topology simulation.

## Branch and commits

- Branch: `phase-15d-c-closure-integration-diagnostics`
- Base commit: `a9329d8`
- HEAD before audit: `a9329d8`
- Audit commit: `fce4fd0` (initial audit commit; amended only to record this hash)

The implementation was uncommitted at audit start. Changed files were limited
to the expected 15D-C runtime, export, tests, and roadmap status files. This
audit document was added during finalization. No frozen architecture document
was modified.

## Scope audited

- `src/mpl_sim/network/closure_integration.py`
- `src/mpl_sim/network/__init__.py`
- `tests/network/test_closure_integration.py`
- `tests/network/test_closure_integration_parallel_context.py`
- `docs/roadmap/PROJECT_STATUS.md`
- Existing 15D-A, 15D-B, and 15C-B runtime and test dependencies

## Public API added

- `ClosureDomain`
- `CombinedClosureResidualSet`
- `CombinedClosureEvaluationResult`
- `CombinedClosureDiagnosticResult`
- `build_combined_closure_residuals`
- `evaluate_combined_closure_residuals`
- `evaluate_combined_closure_sufficiency`
- `build_combined_closure_report`

## Checkpoint review

### 15D-C.1 — combined residual set and evaluation

Approved. The combined set wraps the existing hydraulic and thermal residual
sets, preserves hydraulic-first deterministic ordering, supports explicitly
documented single-domain sets, rejects an empty set, rejects cross-domain
duplicate residual names, delegates unknown validation and residual evaluation
to the underlying domain sets, ignores extra unknowns consistently with those
sets, and returns read-only mappings.

One audit defect was corrected: direct construction of the exported frozen
dataclass previously bypassed the factory invariants and could silently
overwrite a hydraulic residual with a same-named thermal residual. A
`__post_init__` now enforces non-empty domains, domain types, and cross-domain
name uniqueness for every construction path. Four focused regression tests
were added.

`CombinedClosureEvaluationResult` is frozen and is produced with defensively
copied `MappingProxyType` residual maps and metadata. It contains per-domain and
combined residuals, max-absolute and L2 norms, and domain counts.

### 15D-C.2 — diagnostics and reporting

Approved. Combined diagnostics call the existing 15D-A and 15D-B
category-presence evaluators and aggregate their provided categories, missing
categories, deterministic missing messages, and sufficiency flags.

The diagnostic limitation is explicit: sufficiency means only that every
required category in each checked diagnostic has a matching closure. It does
not establish equation count, algebraic rank, DAE solvability, uniqueness, or
physical predictiveness. Domains without a supplied diagnostic are explicitly
skipped and do not fail the verdict.

The report builder returns a plain JSON-serializable dictionary. It includes
hydraulic, thermal, and combined residuals; max-absolute and L2 norms; domain
counts; optional diagnostic details; `status: "evaluation_only"`; and
`no_solve: true`. Its limitations state that the layer is not property-backed,
correlation-backed, HX-model-backed, or production-component-backed and does
not assemble `SystemState` or construct `FluidState`.

### 15D-C.3 — parallel context integration

Approved. The integration tests prove that the 15C-A scenario still builds,
15C-B topology residuals still evaluate at a known consistent point, 15D-A
hydraulic closures and 15D-B thermal closures evaluate at that point, and the
combined closure set evaluates to zero there. Hydraulic and thermal
perturbations affect the expected domain residuals. Topology residuals and
closure residuals remain separate subsystems; no combined physical solve is
performed or claimed.

## Validation results

All pytest commands used fresh repository-local base-temp directories and
disabled the pytest cache provider.

| Validation | Result |
|---|---:|
| 15D-C focused closure integration | 69 passed |
| 15D-C parallel context | 35 passed |
| 15D-B thermal regression | 203 passed |
| 15D-A hydraulic regression | 205 passed |
| 15C-B parallel topology regression | 152 passed |
| Network suite | 2559 passed |
| Full suite | 6420 passed |
| Production contract inspection | 60 passed |
| Skipped / xfailed / deselected | 0 / 0 / 0 |

All six requested examples completed successfully:

- `minimal_evaporator_condenser_loop.py`
- `fixed_heat_rate_hx.py`
- `segmented_counterflow_hx.py`
- `minimal_closed_mpl_solver.py`
- `minimal_pressure_closure.py`
- `minimal_coupled_closure.py`

Tooling:

- `ruff check src tests examples`: passed
- `black --check --no-cache --verbose src tests examples`: passed after
  formatting the two audit-touched files
- `git diff --check`: passed

## Permission-error classification

The previously reported Windows permission errors did not recur. Both the
network and full suites passed with fresh repository-local base-temp
directories and `-p no:cacheprovider`. They are therefore classified as stale
temporary-directory/cache artifacts rather than product test errors. No
unresolved test error remains.

## Boundary audit

Required searches covered CoolProp, `PropertyBackend`, `CorrelationRegistry`,
`SystemState`, `FluidState`, `component_type`, production components,
`contribute`, generic solve APIs, property/component/correlation/HX imports,
file-writing APIs, phase/property/HX terminology, and numerical root/least-
squares/optimization functions.

Findings:

- New runtime executable imports are limited to standard-library utilities and
  existing hydraulic/thermal closure and diagnostic modules.
- Sensitive words in the new runtime are documentation negative statements.
- Sensitive test hits are negative assertions or source-inspection helpers.
- Test-file `open()` calls only read source files for boundary assertions.
- Existing generic residual solvers and test-only fake `contribute` methods are
  pre-existing, outside the 15D-C surface, and unchanged.
- No prohibited executable hit was found.

## Production contract regression

The Phase 14G inspection regression passed. `Component`, `Pipe`,
`PumpComponent`, `AccumulatorComponent`, `EvaporatorComponent`, and
`CondenserComponent` all remain `NO_CONTRIBUTE_METHOD`.

## Documentation alignment

`PROJECT_STATUS.md` now records the independently verified test counts,
permission-artifact classification, evaluation/reporting-only boundary,
diagnostic limitations, constructor-invariant fix, audit reference, and
post-15D-C deferred work.

## Findings

### Critical

None.

### Major

None remaining.

### Minor fixed

1. Direct `CombinedClosureResidualSet` construction bypassed factory
   validation and permitted empty sets, wrong domain types, and duplicate
   cross-domain residual names with silent overwrite.
2. Roadmap status contained stale 15D-C test counts and stale active-phase
   text.
3. The two audit-touched Python files required Black formatting.

### Minor remaining

None.

## Deferred items

- Configurable scenario construction
- Production component adapters and execution
- Property-backed and correlation-backed closures
- Real HX-model-backed closures
- Combined physical residual assembly
- Equation-count, symbolic-rank, and DAE-solvability analysis
- Physically predictive solves
- Arbitrary-topology simulation
- Generic `solve(network)` and `NetworkGraph.solve()`

## Readiness

Block 15D-C is ready within its explicit closure integration,
category-diagnostics, and reporting MVP scope.

Merge readiness: **YES**, subject to committing this audit finalization and
successfully pushing the audited branch to the expected repository remote.
