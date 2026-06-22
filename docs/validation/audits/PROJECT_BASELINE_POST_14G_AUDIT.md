# Project Baseline Post-14G Audit

## Verdict

**APPROVED BASELINE FOR BLOCK 15A**

## Summary

The repository baseline after Phase 14G is clean and ready to begin Block 15A.
The audit found no runtime, public-API, solver-path, physics, or architecture
boundary regression. The only findings were stale operational and user-facing
documentation that stopped at Phase 14E, described the completed Phase 14F as
future work, or still named the Phase 14G implementation branch.

Those documentation findings were corrected. No source/runtime code or tests
were changed or added.

The current production component classes still do not implement
`Component.contribute(...)`. There is no production component bridge, no
production component execution through the network, no automatic physics from
`component_type`, no physical arbitrary-topology solve, and no `solve(network)`
or `NetworkGraph.solve()` API.

## Scope Audited

- Git branch, worktree, history, diffs, and relationship to `main`.
- Full and focused test suites, six runnable examples, Ruff, Black, and
  whitespace validation.
- Public exports from `mpl_sim.core`, `geometry`, `discretization`,
  `correlations`, `components`, `hx_models`, `network`, `closed_loop`,
  `results`, and `schema`.
- README, examples documentation, user guides, and operational project status.
- Frozen architecture, interface, correlation, schema, and decision references.
- Phase 13E through Phase 14G audit documents.
- Network, closed-loop, examples, tests, and user-documentation architecture
  boundary searches.

Frozen architecture documents and the decision log were inspected but not
modified.

## Commands Executed

### Git inspection

- `git branch --show-current`
- `git status --short --branch`
- `git log --oneline --decorate -20`
- `git diff --stat`
- `git diff --cached --stat`
- `git diff --check`
- `git log main --oneline --decorate -12`
- `git merge-base main HEAD`
- `git rev-parse main`
- `git rev-parse HEAD`

### Validation

- `pytest`
- `pytest tests/correlations`
- `pytest tests/hx_models tests/components`
- `pytest tests/loops -v`
- `pytest tests/examples -v`
- `pytest tests/closed_loop -v`
- `pytest tests/network -v`
- all six required example scripts
- `ruff check src tests examples`
- `black --check --no-cache --verbose src tests examples`
- `git diff --check`

Pytest used repository-local temporary directories. The environment emitted
the known non-blocking warning that `.pytest_cache` could not be written; test
temporary files were created successfully and no test was skipped, xfailed,
deselected, or excluded.

### Inventory and boundary checks

- imported every required public package and enumerated `__all__`;
- checked `mpl_sim.network` and `NetworkGraph` for accidental `solve` APIs;
- checked all known production component classes for `contribute`;
- searched for accidental `init.py` files;
- ran the requested CoolProp, property-backend, correlation-registry, solver,
  state, contribution, component-type, production-component import, deferred
  component, and validation-claim searches with `rg`.

## Repository State

- Branch: `audit/project-baseline-post-14g`.
- Initial `HEAD`: `c9273df`, the Phase 14G merge.
- Initial `main`: `c9273df`.
- Initial merge base with `main`: `c9273df`.
- Initial working tree: clean.
- No staged changes or unrelated uncommitted changes were present.
- No tracked or staged temporary/cache files were found.
- `src/mpl_sim/network/init.py` does not exist.
- The correct package initializer is
  `src/mpl_sim/network/__init__.py`.

## Validation Results

| Gate | Result |
|---|---:|
| Full suite | **5050 passed** |
| Correlations | **512 passed** |
| HX models + components | **1896 passed** |
| Loops | **33 passed** |
| Examples tests | **60 passed** |
| Closed-loop | **393 passed** |
| Network | **1189 passed** |
| Required example scripts | **6 passed** |
| Ruff | **clean** |
| Black | **181 files unchanged** |
| `git diff --check` | **clean** |

Validation date: **2026-06-22**.

## Public API Inventory

The required packages imported successfully and exposed the following public
surface sizes:

| Package | Public exports |
|---|---:|
| `mpl_sim.core` | 14 |
| `mpl_sim.geometry` | 11 |
| `mpl_sim.discretization` | 5 |
| `mpl_sim.correlations` | 36 |
| `mpl_sim.components` | 34 |
| `mpl_sim.hx_models` | 21 |
| `mpl_sim.network` | 63 |
| `mpl_sim.closed_loop` | 17 |
| `mpl_sim.results` | 4 |
| `mpl_sim.schema` | 13 |

Verified public capability groups include:

- core fluid identity/state, port, state-layout, and `SystemState` primitives;
- geometry and discretization value objects;
- correlation contracts, registry, active HTC/DP closures, and PCA law;
- Pipe, Pump, Accumulator, Evaporator, and Condenser APIs;
- all three HX model strategies and current secondary boundary conditions;
- fixed-architecture energy, pressure, and coupled closure APIs;
- network graph, declaration assembly, residual evaluation, and configurable
  callback-only algebraic solving;
- Phase 14A physical residual adapters;
- Phase 14B binding/state-name maps;
- Phase 14C contribution adapters;
- Phase 14D contribution records and explicit residual mapping;
- Phase 14E toy execution;
- Phase 14F component-like provider execution;
- Phase 14G production contract inspection.

Negative API checks passed:

- no public `solve(network)`;
- no `NetworkGraph.solve()`;
- no production-component bridge export;
- no production `Component.contribute(...)`;
- all six known production classes report no `contribute` attribute.

## Documentation Alignment

After correction, the operational/user documentation distinguishes the
implemented baseline from deferred physical execution.

Implemented:

- explicit `FluidState` and identity primitives;
- active correlation contract and closures;
- geometry/discretization primitives;
- current HX model family and supported boundary conditions;
- evaporator/condenser scenario helper paths;
- examples and fixed-architecture closure solvers;
- network graph, residual declaration assembly, residual evaluation, and
  configurable callback-only algebraic solver;
- physical residual adapters, component binding, contribution adapters, and
  contribution records;
- toy executor and component-like provider adapter;
- static production component contract inspection.

Not implemented or deferred:

- production `Component.contribute(...)`;
- production component adapter/bridge;
- production component execution through the network;
- physical `SystemState`/`FluidState` assembly for production network
  execution;
- property-backed network component execution;
- automatic residual construction from `component_type`;
- arbitrary-topology physical simulation;
- `solve(network)` and `NetworkGraph.solve()`;
- parallel evaporator physical solving;
- valves, manifolds, recuperator, and pre/post-heaters as physical components;
- moving-boundary modeling;
- literature/experimental validation harness;
- mature DOE/surrogate generation workflow.

No document claims a complete MPL simulator, experimental validation, or
physical arbitrary-topology solving.

## PROJECT_STATUS Operational Memory

`docs/roadmap/PROJECT_STATUS.md` is sufficient as the operational memory
document after correction. It now records:

- the post-14G audit branch and status;
- the Phase 14G completion and `NO_CONTRIBUTE_METHOD` finding;
- the exact current validation counts and date;
- Block 15A as the next planned work;
- planning-only Blocks 15A through 15D;
- the full-validation and architecture-boundary rule for internal checkpoints;
- no claim that any Block 15 work is implemented.

The stale instruction to merge the already-completed Phase 14F branch was
removed. No separate roadmap file was created.

## Architecture Boundary Searches

Search matches were classified as:

- permitted negative statements and deferred-capability documentation;
- tests asserting prohibited behavior is absent;
- local fake/toy/provider classes in tests;
- the Phase 14G static inspection method-name checks;
- established fixed-architecture closed-loop helpers;
- established Phase 7 topology/state-layout assembly that creates a
  zero-initialized `SystemState` but does not execute production graph physics;
- historical implementation-plan and frozen architecture text.

No prohibited live path was found:

- no CoolProp call outside the properties boundary;
- no property lookup in network adapters;
- no correlation-registry resolution in network adapters;
- no provider call to `contribute`;
- no production component execution;
- no physical values attached to `NetworkGraph`;
- no physics generated from `component_type`;
- no hidden scipy/root/fsolve/least-squares solver path;
- no generic physical network solve API.

## Findings

### Critical Findings

None.

### Major Findings

None remaining.

### Minor Findings

Resolved during audit:

1. README and Quickstart stopped at Phase 14E, used an outdated `4000+` test
   count, and omitted the Phase 14F/14G capabilities and boundaries.
2. README still labeled Phase 14E as the current project status.
3. Quickstart recommended the already-completed Phase 14F as the next step and
   said there were four examples although six are required and present.
4. Example documentation used the superseded `Phase 14F+` deferral instead of
   the Block 15A/15B/15C plan.
5. `PROJECT_STATUS.md` named the Phase 14G implementation branch and contained
   a stale instruction to merge Phase 14F.

## Corrective Changes Made

- Updated `README.md`.
- Updated `examples/README.md`.
- Updated `docs/user_guide/QUICKSTART.md`.
- Updated `docs/user_guide/CONCEPTS.md`.
- Updated `docs/user_guide/EXAMPLES.md`.
- Updated `docs/roadmap/PROJECT_STATUS.md`.
- Added this audit document.

No source/runtime code, frozen architecture document, decision log, API, test,
physics, solver path, or component implementation was changed.

## Deferred Items

- Block 15A — Production Component Bridge MVP.
- Block 15B — Minimal Physical Single-Loop Network MVP.
- Block 15C — Topology Extensions MVP.
- Block 15D — Configurable MPL Scenario v1.
- Moving-boundary modeling.
- Literature/experimental validation.
- Mature DOE/surrogate generation.

These items are planning only and are not implemented by this audit.

## Block 15A Readiness

The repository is ready to begin Block 15A.

The baseline is green, the public surface is known, the missing production
contribution contract is explicit, documentation no longer overclaims current
capabilities, and the architecture boundaries required for a controlled bridge
remain clean.

Block 15A must preserve the full-validation gate and must not silently broaden
into arbitrary-topology physical solving, property-backed graph execution, or
an unreviewed `solve(network)` API.

## Recommended Files to Provide as Context in Future Chats

Minimum:

```text
docs/roadmap/PROJECT_STATUS.md
docs/user_guide/CONCEPTS.md
docs/validation/audits/PROJECT_BASELINE_POST_14G_AUDIT.md
```

Optional for user-facing documentation work:

```text
README.md
docs/user_guide/QUICKSTART.md
docs/user_guide/EXAMPLES.md
```
