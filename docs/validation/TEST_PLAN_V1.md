# TEST_PLAN_V1.md

**The concrete validation and testing strategy for the first (steady-state) implementation phase of the MPL simulation framework.**

Status: **test plan (pre-implementation).** This is the fourth and final interface document of `ARCHITECTURE_MASTER.md` §18. It is downstream of, and subordinate to, `ARCHITECTURE_MASTER.md`, `INTERFACE_SPEC.md`, `CORRELATION_CONTRACT.md`, and `SCHEMA_SPEC.md`; it translates their frozen contracts into testable requirements. It **does not reopen any frozen decision** (`[F1]`–`[F18]`, Decisions 001–009) and it **defines no new architecture** — where a test would imply an architectural change, the test is wrong, not the architecture.

What this document is:
- a mapping from the validation levels of `VALIDATION_PLAN.md` to **concrete checks, expected results, and pass/fail criteria**;
- a **development order** (test-driven) for Phases 1–4, with acceptance gates;
- the **anti-pattern compliance checklist** turned into review/test obligations.

What this document is **not**: it contains **no executable code, no test files, no test implementations, no fixtures.** Test *cases* are described as contracts ("given X, assert Y to tolerance Z"), in prose and pseudo-assertions, exactly as the upstream specs describe interfaces in pseudo-signatures. An implementer writes the tests from this document; a reviewer rejects a non-conforming test suite by citing a section here.

How to read a test entry: each test names its **purpose**, its **inputs**, the **expected check** (the assertion), and its **pass/fail criterion**. Where a test depends on data that is not yet present (the 29 property CSVs, digitised literature data), it is marked **`PENDING-DATA`** and is *declared now, skipped until the data lands* — never silently omitted.

---

# 1. Scope and Status

## 1.1 What this plan covers

This is the **V1 test plan for the steady-state implementation** — the validation strategy for Phases 1–4 of `ARCHITECTURE_MASTER.md` §17/§18:

1. FluidState + PropertyBackend split (core data + property + schema);
2. Correlation Registry + Calibration seam;
3. first Components (Pipe, Pump, Accumulator);
4. Evaporator, Condenser, Network, and the steady Solver, validated against literature.

It covers every DAG layer end-to-end at steady state, plus the serialization layer and the literature-validation harness. The **recommended first vertical slice** (`ARCHITECTURE_MASTER.md` §18) is the spine: `FluidState + PropertyBackend(CoolProp) → Port → one friction Correlation + registry → Pipe(Lumped) → trivial Network → fixed-point/Newton steady Solver → Result with invariants`.

## 1.2 Included

- Unit tests of equations and value objects (FluidState, Geometry, CorrelationInput).
- PropertyBackend tests (CoolProp default; capability flags; out-of-range behaviour).
- Correlation-contract tests (statelessness, role-typed input, ValidityVerdict, envelope, gradient-not-total, friction-only calibration).
- Geometry / Discretization tests (immutability, PipePath, mesh-not-in-geometry).
- Calibration tests (NONE/TARGET, slot→component→global resolution, conservation firewall).
- Component tests (Pump, Pipe, Evaporator, Condenser, Accumulator, Valve, Junction, Reservoir) at the V1 fidelity.
- Network / topology tests (one reference, no dangling ports, branch sets, inventory accountant).
- Solver tests (SystemState ownership, residual assembly, fixed-point and Newton, convergence metadata, non-converged persistence).
- Result / invariant tests (minimal stored state, mandatory invariants, predictive/calibrated flag).
- Schema / serialization tests (versioning, round-trip, explicit selections, no hidden defaults).
- Literature-validation tests (Kokate 2024, Li 2021, Fujii 2004, PyP2PL sweeps) — readiness-gated.
- Regression-test strategy (golden Results, tolerance policy, baseline governance).
- Architecture-compliance tests (the anti-pattern checklist as automated/review gates).

## 1.3 Excluded (declared, not tested in V1)

These are **seams declared now and built later**; their tests are shaped here but not required to pass in V1:

- **Dynamic solver, time integration, `MovingBoundary` zone evolution** (Phase 6). Tested only that the *seams* exist: internal states are named-but-frozen; `MovingBoundaryDiscretization` is declarable; the `dynamic` solver block serializes as null.
- **Sensitivity/Linearisation `(A,B,C,D)` extraction** (`[F18]`, Category B) — only the precondition (ordered introspectable `SystemState`) is tested in V1.
- **DOE/surrogate dataset generation and surrogate closures** (Phase 5) — only the dataset *schema* and the `CUSTOM_CLOSURE` admissibility *contract* are tested, not a real surrogate.
- **`TabulatedPropertyBackend` numerical correctness** — `PENDING-DATA` until the 29 CSVs are recovered (`ARCHITECTURE_MASTER.md` §17, `SCHEMA_SPEC.md` §21.2-1). Its *interface conformance* (capability flags, no-extrapolation contract) is tested with whatever partial data exists or with a stub.
- **REFPROP, Mixture, CustomFluid backends; bellows/spring/gas-charged accumulator laws; Friedel, drift-flux void, flow-regime maps, CHF** — new catalogue entries, tested when authored, against the same contract these tests already fix.

## 1.4 Status

The four upstream contracts are frozen and mature (each ends with a "ready for implementation" verdict). **This plan is therefore ready to drive test-first implementation of Phases 1–4.** The only blockers are *data* (property CSVs, digitised literature) — they gate the literature level and the tabulated backend, not the framework or this plan (§20).

---

# 2. Testing Philosophy

The seven design principles (`ARCHITECTURE_MASTER.md` §1) dictate how this framework is tested, not just how it is built.

## 2.1 Validation-first design (Principle 4)

*A result without a residual is not a result.* Energy/mass balance, pressure closure, and physical-bound checks are **first-class test subjects from commit one**, not added after features work. The very first end-to-end test (the vertical slice) asserts the **invariants**, not just that a number came out. A Result missing `energy_imbalance`, `mass_imbalance`, `pressure_closure_residual`, `bound_checks`, or `calibration_report` is **malformed** and its mere production is a test failure (`INTERFACE_SPEC.md` §14, `SCHEMA_SPEC.md` §14.5).

## 2.2 Test before full features (test-driven)

Each layer of the DAG is tested **before** the layer above it is built. The harvest order (`ARCHITECTURE_MASTER.md` §17) is also the test order: FluidState/PropertyBackend tests pass before any Correlation is written; Correlation-contract tests pass before any Component consumes a correlation; the Component contribution-contract test passes before the Network assembles components; the Network/topology tests pass before the Solver drives them. **No layer is implemented against an untested layer below it.**

## 2.3 Conservation invariants as the spine

The three global residuals — **energy imbalance, mass imbalance, pressure-closure residual** — and the bound checks (`0 ≤ x ≤ 1`, `T < T_crit`) are computed from **un-calibrated conservation** (`INTERFACE_SPEC.md` §13.4, §9.5). Every loop-level test asserts them to tolerance. This is the test-level expression of the **conservation firewall**: a test can never let calibration mask a balance violation, because the test reads the same un-calibrated invariants the architecture does.

## 2.4 The minimal vertical slice (Principle 6)

The first integration target is the **smallest loop that exercises every DAG layer** (§4). It is built and made green before any expensive component (Evaporator, Condenser). This surfaces interface friction (handle mapping, context-supplied backend, residual assembly) on a two-component loop where the physics is trivial and the failure is unambiguous, exactly as `ARCHITECTURE_MASTER.md` §18 prescribes.

## 2.5 Reproducibility (Principle 7)

Every Result is tested to be **fully determined by its Reproducibility Tuple**: serialize the tuple, re-instantiate, re-solve, and assert the converged `(P, h, ṁ)` and internal states reproduce to solver tolerance (the round-trip of `SCHEMA_SPEC.md` §2.7). No test may depend on call order, import-time state, or an un-versioned default — a test that passes only on the first run in a process is itself a detected anti-pattern (§16).

## 2.6 Architecture anti-pattern detection

The anti-pattern checklists (`ARCHITECTURE_MASTER.md` §19, `INTERFACE_SPEC.md` §16, `CORRELATION_CONTRACT.md` §13, `SCHEMA_SPEC.md` §20) are converted into **explicit compliance tests and review gates** (§16). Where a violation can be detected programmatically (a Port carrying a value; a Result serializing `T` beside `(P,h)`; a correlation returning a bare number), there is an automated test. Where it cannot, there is a named review checklist item that gates the phase (§18). The legacy port (`ARCHITECTURE_REVIEW_LEGACY.md` §7.2) is the catalogue of violations these gates exist to catch.

---

# 3. Test Levels

Eleven levels, bottom-up along the DAG. Each level states its **purpose**, representative **examples**, and **acceptance criteria** (the bar the level must clear before the level above it is built).

## 3.1 Unit tests

- **Purpose:** verify individual equations, value objects, and utility functions in isolation — the smallest checkable units (`VALIDATION_PLAN.md` Level 1).
- **Examples:** quality `x = (h − h_f)/h_fg` continuous through 0 and 1; homogeneous void fraction; a friction-factor formula against a hand-computed value; FluidIdentity structural equality; a Geometry derived accessor (`D_h` from primitives).
- **Acceptance criteria:** every unit test deterministic and backend-pinned where properties are involved; numeric assertions to a stated absolute/relative tolerance; no unit test touches a Component, Network, or Solver.

## 3.2 PropertyBackend tests

- **Purpose:** verify the `PropertyBackend` contract (`INTERFACE_SPEC.md` §3.3): vector-first query, full derived set, capability flags, no extrapolation by stealth.
- **Examples:** `query(rho, P[], h[], identity)` returns a length-matched `PropertyResult`; an unsupported property returns `UNAVAILABLE`, not a guess; an out-of-range `(P,h)` returns `OUT_OF_RANGE` + `NaN` + warning; `provides(SIGMA_E)` is `false` for CoolProp and (when data exists) `true` for the tabulated backend.
- **Acceptance criteria:** scalar and vector calls return identical values for the length-1 case; no call ever fabricates an in-range value for an out-of-range input; the backend is a pure function of `(P, h, identity)` (two calls, equal output).

## 3.3 Correlation tests

- **Purpose:** verify the `evaluate(CorrelationInput) → CorrelationOutput` contract (`CORRELATION_CONTRACT.md` §1, §5) and the five non-negotiable invariants (statelessness, no topology, no solver-awareness, no calibration, role-typed input).
- **Examples:** a friction closure returns a **gradient** `(dP/dx)`, never a total ΔP; output always carries a `ValidityVerdict`; equal inputs → equal outputs across calls; an out-of-envelope input yields `EXTRAPOLATED` (value, flagged) or `OUT_OF_RANGE` (`NaN`).
- **Acceptance criteria:** no correlation holds state between calls; none receives a Geometry/Component object; none returns a bare number; the verdict's `violated` names the specific bound.

## 3.4 Geometry tests

- **Purpose:** verify Geometry is an immutable, flat, typed family that supplies scalars and computes no physics (`INTERFACE_SPEC.md` §5, `[F8]`).
- **Examples:** mutating a `PipeGeometry` field is impossible (a new object results); `PipePath.derived()` returns `{L_total, dz_dx_profile, sum_minor_K}`; the v1 `StraightSegment` reproduces a single-`Δz` run; a geometry exposes no `Nu`/`ΔP` accessor; `AccumulatorGeometry` carries no `V_gas_charge`.
- **Acceptance criteria:** every geometry type is immutable; none stores a mesh or operating state; none computes a correlation output.

## 3.5 Component tests

- **Purpose:** verify each component satisfies the **contribution contract** (`INTERFACE_SPEC.md` §11.1) — declares ports/internal-state names/slots, consumes only handed-in trial state, returns residuals (+ frozen-zero derivatives), reaches outside itself for nothing.
- **Examples:** a Pipe in `Lumped` mode returns a single momentum residual; its internal states are named with zero derivative; it never calls the backend except through FluidState in `ctx`; it never names a neighbour.
- **Acceptance criteria:** the contribution signature is identical across `Lumped`/`Segmented`; the component passes no test by reading the Network or Solver; calibration factors actually applied are reported.

## 3.6 Network/topology tests

- **Purpose:** verify the Network states *what must hold* and validates topology (`INTERFACE_SPEC.md` §12, `[F7]`).
- **Examples:** `validate()` rejects a dangling port; rejects a second pressure reference; accepts exactly one; a branch group is well-formed (splitter↔mixer paired); inventory has a single accountant.
- **Acceptance criteria:** the four `TopologyVerdict` checks (no dangling ports, exactly one reference, well-formed branch sets, no double-counted inventory) each have a passing and a failing test.

## 3.7 Solver tests

- **Purpose:** verify the Solver owns `SystemState`, assembles contributions, converges, and emits invariants + metadata, depending on nothing below it (`INTERFACE_SPEC.md` §13).
- **Examples:** fixed-point pressure iteration converges a single loop; simultaneous Newton converges the same loop to the same state; a non-converging problem yields `converged: false` with honest invariants; the Jacobian is obtained by FD copy-and-bump over the contract.
- **Acceptance criteria:** both steady strategies reach the same converged state to tolerance; the Solver never calls a correlation/geometry/property formula directly; `SystemState` is mutated only by the Solver.

## 3.8 Schema/serialization tests

- **Purpose:** verify the serialized tuple and Result conform to `SCHEMA_SPEC.md` (versioning, round-trip, minimal state, explicit selections, no hidden defaults).
- **Examples:** every artifact carries `schema_version`; a Result stores only `(P,h,ṁ)` + internal states (no `T`/`ρ`); deserialize→serialize is byte-stable under the canonicalization rule; an unresolvable `$ref` is a hard error.
- **Acceptance criteria:** round-trip fidelity for tuple and Result; no derived property serialized as primary state; every model selection present and canonical.

## 3.9 Result/invariant tests

- **Purpose:** verify the Result is minimal-stored, invariant-bearing, and correctly flagged (`INTERFACE_SPEC.md` §14, `SCHEMA_SPEC.md` §14–§15).
- **Examples:** a Result without `invariants`/`calibration_report`/`tuple_ref` is rejected as malformed; profiles are derived on demand, not stored; a `TARGET` run is flagged `CALIBRATED`.
- **Acceptance criteria:** the malformed-Result guard fires for each missing mandatory field; derived profiles recompute from stored `(P,h)`.

## 3.10 Literature validation tests

- **Purpose:** verify the framework reproduces published data within experimental error (`VALIDATION_PLAN.md` Level 4).
- **Examples:** Kokate 2024 R-134a HTC-vs-q″ / ΔP-vs-q″ within MAE (Eq. 17); Li 2021 Acetone evaporator energy balance; Fujii 2004 node profiles.
- **Acceptance criteria:** `PENDING-DATA` until each case's digitised data is sourced and pinned (`SCHEMA_SPEC.md` §18); once present, agreement within the case's `comparison_metrics` tolerance against the reported uncertainty band.

## 3.11 Regression tests

- **Purpose:** protect against accidental model/number drift across changes (§15).
- **Examples:** the vertical-slice Result is a golden file; the Kokate case Result is a golden file; a code change that shifts a converged `(P,h)` beyond tolerance fails until the baseline is deliberately updated.
- **Acceptance criteria:** golden Results stored for every committed example; a documented baseline-update procedure; predictive and calibrated baselines never cross-compared.

---

# 4. Phase-1 Minimal Vertical Slice Tests

The recommended first slice (`ARCHITECTURE_MASTER.md` §18) is the **first integration test of the whole DAG**:

```
FluidState + PropertyBackend(CoolProp)
  → Port
  → one friction Correlation + CorrelationRegistry
  → Pipe(Lumped)
  → trivial two-component Network (e.g. fixed-inlet source → Pipe → fixed-outlet/reference)
  → fixed-point (or Newton) steady Solver
  → Result with invariants
```

## 4.1 Required tests (in build order)

1. **FluidState/PropertyBackend** (§5): construct `FluidState(P, h, PureFluid("R134a"))`; query `T, ρ, x, h_f, h_g, h_fg` via CoolProp; assert against CoolProp reference values; assert no property stored on the state.
2. **Port/handle** (§7-of-this-plan / `INTERFACE_SPEC.md` §4): assemble two ports, connect them, build `PortHandle`s; assert the handle maps to `SystemState` slots and the Port itself carries no value.
3. **Friction correlation + registry** (§7): register one `SINGLE_PHASE_DP` closure (e.g. Churchill); `resolve("Churchill")`; `evaluate(SinglePhaseDPInput)` returns `(dP/dx)[]` + `IN_ENVELOPE` verdict for an in-range input.
4. **Pipe(Lumped)** (§9): the Pipe's `contribute` integrates the one-cell gradient kernel — friction (from the slot) + gravity (`ρ g dz/dx`, g from Scenario) + acceleration — into a momentum residual; internal states named with zero derivative.
5. **Trivial Network** (§10): two components, one connection, exactly one pressure reference; `validate()` passes.
6. **Steady Solver** (§11): assemble; drive the residual to `< residual_norm` tolerance; obtain Jacobian by FD; emit `ConvergenceMetadata`.
7. **Result with invariants** (§12): produce a Result; assert energy imbalance, mass imbalance, pressure-closure residual within tolerance and bound checks pass; assert `calibration_report` present (empty under `NONE`); flag `PREDICTIVE`.

## 4.2 Expected outputs

- A converged `SystemState`: `(P, h, ṁ)` at each port-node; the Pipe's frozen internal states present at their named slots.
- A well-formed Result: stored `(P,h,ṁ)` only; derived `T/ρ/x` recomputable; all invariants present and within tolerance; `validity_warnings` empty (in-envelope); `convergence.converged = true`.
- A serialized tuple + Result that round-trips and reproduces the solve (§2.5).

## 4.3 Pass/fail criteria

- **Pass:** all seven layer tests green; loop invariants within the §1.4 acceptance targets (energy imbalance < 1%, pressure-closure residual < 1%, `0 ≤ x ≤ 1`); the Result is well-formed; the reproducibility round-trip is exact to solver tolerance.
- **Fail (any of):** a property stored on a state/port; a correlation returning a total instead of a gradient; the Solver reaching into a component out-of-band; a missing mandatory Result field; an invariant out of tolerance with no honest report.

## 4.4 What this slice proves

It proves the **frozen interfaces compose end-to-end** before any expensive physics is written: the stored-vs-derived boundary holds; the context-supplied backend pattern works in the solver inner loop; `PortHandle`/`SystemState` assembly is correct; the gradient kernel integrates in `Lumped` mode; the Solver depends on nothing below it; and the Result carries first-class invariants. Every later component (Pump, Accumulator, Evaporator, Condenser, Junction) is then added **against now-proven contracts**, so a failure in a later phase localizes to that component, not to the plumbing.

---

# 5. FluidState and PropertyBackend Tests

Tests for the Layer-0/1 core (`INTERFACE_SPEC.md` §3, `[F2] [F6] [F12] [F13]`, Decision 006).

## 5.1 FluidState — P,h canonical state

- **P,h canonical:** construct from `(P, h, identity)`; assert `T, T_sat, x, ρ, μ, k, σ, c_p, phase, h_f, h_g, h_fg` are all derivable; assert `x = (h − h_f)/h_fg` is continuous across subcooled→saturated→superheated (sweep h across the dome at fixed P; no discontinuity, no region-variable switch).
- **No stored derived properties:** assert `FluidState` holds exactly three fields (`P`, `h`, `identity`); assert no derived attribute is cached on it; re-querying a property recomputes (a backend-call counter, or equal results after a hypothetical backend swap, demonstrates non-caching).
- **ṁ is not on FluidState:** assert there is no mass-flow field on the state.
- **Ephemeral lifecycle:** assert a `FluidState` is never required to be stored on a Port or Component to be usable (it is constructed transiently in `ctx`).

## 5.2 CoolPropBackend (default)

- **Reference agreement:** for a grid of `(P, h)` for R-134a and Acetone, assert backend `query` matches CoolProp reference values to a tight tolerance.
- **Identity selection:** `PureFluid("R134a")` and `PureFluid("Acetone")` resolve to distinct backend instances per identity, shared by reference within a run (`INTERFACE_SPEC.md` §3.4).
- **No import-time construction / no global mutable state:** assert constructing a backend has no module-level side effect; two runs are independent.

## 5.3 Vector-first query behaviour

- **Length-matching:** `query(prop, P[], h[], identity)` returns a `value[]` and `status[]` of the same length as the inputs.
- **Scalar = length-1:** the scalar case equals the length-1 vector case exactly (Rule 6, `[F13]`).
- **Batch consistency:** a vector query equals element-wise scalar queries (the precondition for Phase-5 batch and FD-Jacobian columns).

## 5.4 Unsupported property handling

- **Capability gate:** `provides(SIGMA_E)` is `false` for CoolProp; a `query(sigma_e, …)` on a backend that lacks it returns `UNAVAILABLE` with a warning, never a fabricated number (`σ_e`/`ε_r` are table-only, `ARCHITECTURE_MASTER.md` §17).
- **No silent guess:** asking for any unsupported `PropertyName` returns an explicit `UNAVAILABLE` status.

## 5.5 Out-of-range behaviour

- **No extrapolation by stealth (`[F13]`-5):** an out-of-range `(P,h)` (e.g. below triple point, above critical envelope) returns `OUT_OF_RANGE` + `NaN` + warning; assert the value is never a clamped edge value.
- **`valid_range(identity)`:** returns a `RangeEnvelope` that the out-of-range test points fall outside and the in-range points fall inside.

## 5.6 Capability flags

- `provides(DERIVATIVES)` reflects whether `query_derivative` is implemented; if `true`, `∂ρ/∂P|h` and `∂ρ/∂h|P` are queryable and finite in-range; if `false`, the analytic-Jacobian path is correctly not exercised (FD is primary regardless, `[F18]`).
- A capability flag is **queried, never serialized** into the tuple (`SCHEMA_SPEC.md` §5.3) — assert no capability flag appears in a serialized tuple/Result.

## 5.7 TabulatedPropertyBackend — `PENDING-DATA`

> **The 29 property CSV files are missing** (`ARCHITECTURE_MASTER.md` §17, `ARCHITECTURE_REVIEW_LEGACY.md` §6.3, `SCHEMA_SPEC.md` §21.2-1). All numerical tests for `TabulatedPropertyBackend` are **skipped/marked pending until the data is recovered, located, schema-verified, versioned, and content-hash pinned** (`SCHEMA_SPEC.md` §5.4).

- **Interface conformance (testable now, with a stub or partial table):** the backend satisfies the same `PropertyBackend` contract — vector-first, capability flags (`provides(SIGMA_E) = true`), no extrapolation beyond table range (returns `OUT_OF_RANGE`/`NaN`, never a guessed value).
- **`PENDING-DATA` numerical tests (declared, skipped):** saturation interpolation against known table points; quality-weighted liquid↔vapour blend; `σ_e`/`ε_r` retrieval for a covered fluid. Each test is written with a skip marker citing the missing-data blocker, so recovery flips it from skipped to active without authoring new tests.

## 5.8 Future backends (mixture / custom-fluid)

- **Additive-by-contract:** a `MixtureBackend`/`CustomFluidBackend` is admissible the moment it satisfies the `PropertyBackend` interface; assert a `Mixture` or `CustomFluid` identity selects it via a backend-selection edit alone, with **no change to FluidState or to anything that references a fluid by `FluidRef`** (`SCHEMA_SPEC.md` §5.1, §2.8). V1 ships no such backend; the test asserts the *seam* (identity discriminated union round-trips; a stub mixture backend is selectable).

---

# 6. Geometry and Discretization Tests

Tests for Layer-0 Geometry and Layer-5 Discretization (`INTERFACE_SPEC.md` §5–§6, `[F8] [F16] [F17]`, Decision 007).

## 6.1 Immutable geometry

- Assert every geometry type (`PipeGeometry`, `PlateGeometry`, `MicrochannelGeometry`, `AccumulatorGeometry`) is immutable: a "variation" produces a new object → a new tuple (the DOE unit, §2.2 of `SCHEMA_SPEC.md`).
- Assert a geometry is safely shareable by reference (the same object serves two components without aliasing hazard).

## 6.2 PipeGeometry + PipePath

- Assert `PipeGeometry` exposes `{L, D_h, A, roughness, trajectory}`; the correlation-facing scalars (`D_h`, `A`, `roughness`, per-cell `dz/dx`, `Σ K_L`) come from `PipePath.derived()`, never the trajectory's internal structure (`INTERFACE_SPEC.md` §5.1).

## 6.3 Straight segment (v1 default)

- Assert `trajectory = StraightSegment{length, delta_z, inclination}` reproduces a single straight `Δz` run exactly — `dz/dx` constant over the cell, `Σ K_L = 0` with no fittings.
- Assert no v1 path requires `MultiSegmentPath`/`BendSegment`/`FittingSegment` (declared `<<SEAM>>`, unbuilt) — over-generalizing the trajectory in V1 is itself an anti-pattern (`INTERFACE_SPEC.md` §16-18).

## 6.4 Trajectory-derived dz/dx

- Assert `PipePath.derived().dz_dx_profile` integrated over `L` equals `delta_z`; assert the gravity gradient kernel consumes this `dz/dx` (not a stored `Δz`) and the **gravity magnitude from Scenario** (`[F17]`).

## 6.5 No mesh in geometry

- Assert no geometry type carries a segment/zone count or any mesh field (`[F16]`). Switching a component `Lumped ↔ Segmented` touches **no geometry field** (the mesh-in-geometry guard, `INTERFACE_SPEC.md` §16-9).

## 6.6 Lumped and Segmented discretizations

- `LumpedDiscretization`: `declared_state_count` corresponds to one control volume; `cell_metrics` returns one cell derived from geometry.
- `SegmentedDiscretization{N}`: `declared_state_count` scales with `N`; `cell_metrics` returns `N` cells with `L_cell = L/N` derived from `PipeGeometry.L` (never stored in geometry).
- Assert the **same geometry object** serves both a lumped and a segmented run.

## 6.7 MovingBoundary seam — `<<SEAM>>`

- Assert `MovingBoundaryDiscretization{max_zones}` is *declarable* and serializes (`SCHEMA_SPEC.md` §7); its `current_state_count`/`events` per-step contract is shaped but **not exercised in V1** (Phase 6).
- Assert that in V1, a component declaring `MovingBoundary` is either rejected as not-yet-implemented with a clear message, or treated as its `Lumped`/`Segmented` fallback — never silently mis-sized by the Solver.

---

# 7. Correlation Contract Tests

Tests grounded in `CORRELATION_CONTRACT.md`. The correlation is the core research seam; these tests guard its purity.

## 7.1 Statelessness

- **Equal inputs → equal outputs:** call `evaluate` twice with equal inputs; assert identical outputs regardless of call order or history (`CORRELATION_CONTRACT.md` §2.3).
- **No hidden state:** assert no instance field changes across calls; no module-level global (`_fluid_name`), no `hasattr` self-introspection, no `_last_dP`/`_mu_v_store` cache (the legacy violations, `CORRELATION_CONTRACT.md` §13-4).

## 7.2 Role-typed inputs

- Assert a correlation receives exactly its role's `CorrelationInput` (one type per role, not per formula): Shah, Gungor-Winterton, Kim-Mudawar all accept the identical `HTCInput`; Friedel/MSH share `TwoPhaseDPInput` (`[F11]`).
- Assert a correlation **never** receives a `Geometry` or `Component` object — only declared scalars + `FluidState` (the forbidden `Correlation → Component` direction made unrepresentable, `CORRELATION_CONTRACT.md` §13-2).
- Assert required input fields are populated by the component; an absent optional field (`q_flux?`, `T_wall?`) is *meaningfully absent*, and a formula that needs an absent optional returns a hard-failure verdict, never a guess (`CORRELATION_CONTRACT.md` §4.4).

## 7.3 Output shape

- Assert `CorrelationOutput {value[], verdict, metadata}` always — a correlation **may never return a bare number** (`CORRELATION_CONTRACT.md` §13-9, Rule 5).
- Assert `value` is vector-first (length-1 for a lumped cell) and is the role's defined meaning (a *gradient* for DP, a *coefficient* for HTC, a *fraction* for void, a *pressure* for the pressure law).

## 7.4 ValidityVerdict

- Assert every output carries a `ValidityVerdict {status, envelope, violated, detail}`.
- Assert `status ∈ {IN_ENVELOPE, EXTRAPOLATED, OUT_OF_RANGE}`; `violated` is empty when `IN_ENVELOPE` and names the specific exceeded bounds otherwise (`CORRELATION_CONTRACT.md` §6.4).

## 7.5 Validity envelope checks

- Register a closure with a declared `ValidityEnvelope` (fluid families + bounds + regime restriction + source); assert an in-bounds input → `IN_ENVELOPE`, an above-`QUALITY_X` input → `EXTRAPOLATED` with `violated = [QUALITY_X]`, a non-evaluable input → `OUT_OF_RANGE`.
- Assert a closure registered **without** an envelope is **inadmissible** (`CORRELATION_CONTRACT.md` §6, §14.2) — the registry rejects it.

## 7.6 EXTRAPOLATED vs OUT_OF_RANGE

- **EXTRAPOLATED (soft):** the formula is still evaluable; assert the returned value is the **honest extrapolated number, never clamped to the envelope edge** (`CORRELATION_CONTRACT.md` §6.4); the run continues; the verdict is surfaced into `Result.validity_warnings`.
- **OUT_OF_RANGE (hard):** the input is non-evaluable (impossible input, or a backend `UNAVAILABLE`/`OUT_OF_RANGE`); assert the value is `NaN`, surfaced loudly, and that the `NaN` **propagates honestly into the invariants** rather than being masked.
- **Continuity caution (`CORRELATION_CONTRACT.md` §6.5):** assert a regime-restricted closure does **not** return `NaN` mid-domain where the physics is still defined (a mid-domain hard cut-off is the anti-pattern §13-14); envelope checking *reports*, it does not *branch*.

## 7.7 No hidden calibration

- Assert a correlation's output under `NONE` equals its raw physics — there is no `× factor` inside the formula (`CORRELATION_CONTRACT.md` §13-1). A reader of the formula encounters no fudge factor.

## 7.8 No total ΔP from DP correlations

- Assert a `SINGLE_PHASE_DP`/`TWO_PHASE_DP` closure returns a **per-cell gradient** `(dP/dx)`, never an integrated total (`[F14]`, anti-pattern §13-11). Integration over the discretization is the Component's job (§9 here).

## 7.9 No gravity/acceleration inside the friction closure

- Assert a two-phase-DP return contains **only** the friction gradient — never the hydrostatic `ρ g dz/dx` or the acceleration `d(G²v)/dx` term (anti-pattern §13-12). Those are Component terms added outside the closure and **never calibrated**.

## 7.10 Legacy correlation migration tests

For each **Adapt** closure (`CORRELATION_CONTRACT.md` §11), a migration test asserts the ported equation reproduces the legacy numeric result **after** the globals/hacks are stripped and the role-typed input + envelope are added:

- MPL `correlations.py`: Shah, Kim-Mudawar 2012/2013, Yan, Dittus-Boelter, Gnielinski, Shah-London, Blasius, Churchill, MSH, Homogeneous — assert each matches its legacy output for a reference input (using the legacy `tests/*` as oracles, `ARCHITECTURE_REVIEW_LEGACY.md` §7.3).
- PyP2PL boiling: Shah, Chen, Bennett-Chen, Gungor-Winterton, Kandlikar-Balasubramanian — assert each matches **with the `_fluid_name` global, `hasattr` introspection, and hard-coded `M = 102.0` removed**, the fluid constant now arriving through `FluidState`/inputs (`CORRELATION_CONTRACT.md` §11.3).
- A0: `alpha_boiling` (nucleate+convective ΔT fixed-point), `alpha_condensation`, mixture friction factor — assert each matches the legacy equation lifted out of the global-array housing (`CORRELATION_CONTRACT.md` §11.1, §11.3).
- **New (not migrations):** Friedel, drift-flux/Zivi/Rouhani void, flow-regime maps, bellows/spring/gas-charged laws are authored fresh against the contract and tested as new closures, not as ports (`CORRELATION_CONTRACT.md` §11.4–§11.6).
- The acceleration/gravity gradient helpers (MPL `acceleration_pressure_gradient`/`gravity_pressure_gradient`) are tested as **Component kernel terms, not registry correlations** (`CORRELATION_CONTRACT.md` §11.2) — a test asserts they are *not* registered in the `CorrelationRegistry`.

---

# 8. Calibration Tests

Tests for the calibration seam (`INTERFACE_SPEC.md` §9, `CORRELATION_CONTRACT.md` §7, `[F5] [F14]`, Decision 005/008).

## 8.1 NONE mode

- Assert under `CalibrationMode.NONE` every factor = 1.0; a calibrated output equals the raw correlation output; the Result is flagged `PREDICTIVE`; the `calibration_report` is present with an **empty factors list** (`SCHEMA_SPEC.md` §12).

## 8.2 TARGET mode

- Assert under `TARGET` a non-neutral factor scales the closure output at the seam; the Result is flagged `CALIBRATED`; the factor (target, value, mode, seam) appears in the `calibration_report`.
- Assert a `CALIBRATED` Result is **never compared as-equal** to a `PREDICTIVE` Result (`INTERFACE_SPEC.md` §14, anti-pattern `SCHEMA_SPEC.md` §20-16).

## 8.3 Slot / component / global resolution

- Assert resolution order **slot → component → global → neutral** (`INTERFACE_SPEC.md` §9.3): a per-slot factor overrides a per-component factor overrides a global factor overrides neutral; the **resolved, applied** factor is what is reported and serialized (no reader needs the resolution algorithm).

## 8.4 R* applied only to friction gradient

- Assert `R*` (target `FRICTION_GRADIENT`) multiplies the **friction gradient only**, per `ΔP_total = R*·ΔP_friction + ΔP_gravity + ΔP_acceleration` (`[F14]`); assert gravity and acceleration gradients are **unchanged** by any calibration.
- Assert a calibration factor targeting gravity, acceleration, a balance, void fraction, flow regime, or a pressure law is **malformed/rejected** (`CORRELATION_CONTRACT.md` §7.3, anti-pattern §13-13).

## 8.5 HTC/UA multipliers

- Assert an `HTC` multiplier scales the heat-transfer coefficient at the component seam; a `UA` multiplier scales the conductance a `HeatExchangerModel` assembles from HTC closures (`CORRELATION_CONTRACT.md` §7.3) — never a balance.

## 8.6 Calibration reporting

- Assert **every** non-neutral factor records target, value, mode, scope, and **seam location** (which slot, which component, scaling which output) into the Result's `CalibrationReport` (`CORRELATION_CONTRACT.md` §7.5). *A factor that is not reported cannot exist* — a `TARGET` run whose Result omits the factor is malformed (anti-pattern `SCHEMA_SPEC.md` §20-5).

## 8.7 Calibrated vs predictive Result flags

- Assert `predictive_or_calibrated` is derived from the run's `CalibrationMode` and is mandatory; a missing flag is a malformed Result.

## 8.8 Conservation firewall

- **The central calibration test.** Construct a run with a deliberately *wrong* `TARGET` calibration; assert the energy/mass imbalance and pressure-closure residuals (computed from **un-calibrated** conservation) get **worse** (a worse data match), and **never** falsely pass (`CORRELATION_CONTRACT.md` §7.4, `INTERFACE_SPEC.md` §9.5). Assert calibration can move the operating point but can never make `Σṁ ≠ 0` look like zero.

---

# 9. Component Tests

Per-component tests against the contribution contract (`INTERFACE_SPEC.md` §11.4). Each component is tested for: **minimum V1 behaviour**, **physical checks**, **residual checks**, **internal-state checks**, and **scenario-binding checks**. All components share the contract test (§3.5): named ports + internal-state names, consume only handed-in trial state, never reach outside themselves, report applied calibration.

## 9.1 Pump

- **Min V1:** two ports `[in]`,`[out]`; performance/efficiency-map slot; loop inertia `I` and shaft speed named-but-frozen.
- **Physical:** `ΔP_pump` follows the performance map at the commanded `ω` or target `ṁ`; pump power derivable.
- **Residual:** the pump contributes its `ΔP` to the loop momentum balance.
- **Internal-state:** shaft speed / inertia `I = L/A` named with zero derivative (`[F15]`, Decision 007).
- **Scenario:** binds `PumpSpeedCommand` (ω) or `PumpFlowTarget` (ṁ); a command targeting a non-existent pump is a binding error (`INTERFACE_SPEC.md` §10.5).

## 9.2 Pipe

- **Min V1:** `PipeGeometry` (+ `PipePath`); `Lumped` default; slots for single-phase ΔP, two-phase ΔP, void fraction.
- **Physical:** total ΔP = integral of the per-cell gradient kernel (friction + gravity + acceleration); a horizontal pipe has zero gravity term; raising `delta_z` raises only the gravity term.
- **Residual:** momentum residual from the integrated gradients; `R*` scales only the friction part (§8.4).
- **Internal-state:** per-segment mass/momentum (and wall T if heated) named, count = Discretization, frozen derivative.
- **Scenario:** optional wall heat (a BC).

## 9.3 Evaporator

- **Min V1:** `MicrochannelGeometry`; `Segmented` meaningful mode; `HeatExchangerModel` slot (`SEGMENTED_MARCH` default, §9.9); boiling-HTC + two-phase-ΔP slots; HTC × and `R*` calibration.
- **Physical:** applied heat load raises outlet enthalpy/quality consistently with energy balance; wall T = `T_sat + q″/α` per segment; outlet quality within `[0,1]`.
- **Residual:** energy + momentum residuals per segment; `HXSolveResult.Q` consistent with the `EvaporatorHeatLoad` BC.
- **Internal-state:** flow regime (algebraic); wall capacitance/seg and fluid inventory named-but-frozen.
- **Scenario:** binds `EvaporatorHeatLoad` (Q or wall flux).

## 9.4 Condenser

- **Min V1:** `PlateGeometry`; `HeatExchangerModel` slot (`EPSILON_NTU` default; LMTD/segmented/MB selectable, §9.9); condensation-HTC + ΔP slots; HTC/UA × and `R*` calibration.
- **Physical:** heat rejected to the sink consistent with the `CondenserSink` BC (sink inlet T + flow); inlet two-phase → outlet subcooled; energy balance closes.
- **Residual:** energy + momentum residuals; `Q` matches the ε-NTU/LMTD solution.
- **Internal-state:** effective areas/zone named; moving-boundary positions named-but-frozen (Phase 6 unfreezes).
- **Scenario:** binds `CondenserSink {T_in, mdot, fluid}`; `fluid` is a `FluidRef` to a secondary identity with its own backend.

## 9.5 Accumulator (pressure-reference component)

- **Min V1:** `AccumulatorGeometry` (**containment only**); one `VolumePressureLaw` slot; stores `V_g`, derives `P`.
- **Physical / pressure-reference law (`[F9]`, `CORRELATION_CONTRACT.md` §9):**
  - **PCA:** given `V_g`, `V_total`, `charge_volume`, `polytropic_index`, the law returns `P` via the polytropic gas relation; assert monotonic `P(V_g)` and agreement with the MPL legacy PCA values (Adapt, `CORRELATION_CONTRACT.md` §11.6).
  - **HCA:** a heater-driven saturation-temperature reference returns `P` using the `thermal` sub-spec; assert agreement with the MPL legacy HCA values.
  - **Gas-charged / spring / bellows (`<<SEAM>>`):** declared interchangeable laws; V1 tests assert only that the slot **accepts** them by binding and that **no law parameter lives in geometry** (§9.6); numerical tests are authored when each law is built.
- **Residual / reference:** the accumulator sets the pressure reference at its node; `P_set` arrives from Scenario (`AccumulatorPressureSetpoint`); the law maps `(V_g, V_total, law_params, thermal?, P_set?) → P`.
- **Internal-state:** stores **`V_g`**; asserts **`P_sys` is NOT stored** on the accumulator (it is a `SystemState` unknown constrained by the law, `[F15]`, anti-pattern `SCHEMA_SPEC.md` §20-10).
- **Geometry↔law separation:** assert `AccumulatorGeometry` carries **no** `V_gas_charge`, spring rate, bellows area, or polytropic index; all law parameters travel in `law_params`/`thermal` with the law selection (`SCHEMA_SPEC.md` §6.4, anti-pattern §20-7).

## 9.6 Valve

- **Min V1:** minimal (`Cv`) geometry; loss-coefficient `K_L` vs opening slot; position frozen.
- **Physical:** ΔP rises as opening fraction falls; optional × on loss reported when used.
- **Scenario:** binds `ValveOpeningCommand` (fraction).

## 9.7 Junction

- **Min V1:** `[trunk]` + N `[branch_i]`; no internal state; supplies mass + energy conservation and equal node pressure only.
- **Physical / topology:** assert a Junction **never knows another branch exists** (`ARCHITECTURE_MASTER.md` §12, anti-pattern §19-2); `Splitter`/`Mixer` are configurations of it (optional thin aliases deserializing to `Junction`).
- **Residual:** algebraic `Σṁ = 0` at the node and equal pressure across connected ports.

## 9.8 Reservoir

- **Min V1:** containment-volume geometry; inventory + liquid level named-but-frozen.
- **Physical:** holds inventory and guarantees NPSH but **sets no pressure reference** (the Accumulator does); assert a Reservoir never serializes a pressure-reference field (`INTERFACE_SPEC.md` §11.4).

## 9.9 HeatExchangerModel tests (Condenser / Evaporator)

Tests for the distinct `HeatExchangerModel` strategy concept (`INTERFACE_SPEC.md` §8), **not** a correlation:

- **Separate concept:** assert ε-NTU/LMTD/segmented/moving-boundary are resolved from the `HeatExchangerModelRegistry`, **not** the `CorrelationRegistry`; a heat-exchange method in the correlation role set is the anti-pattern `INTERFACE_SPEC.md` §16-6 / `CORRELATION_CONTRACT.md` §13-8.
- **Consumes correlations:** assert the model **builds `UA` from injected HTC correlations** + geometry area and calls HTC/ΔP correlations per cell for `SEGMENTED_MARCH`; the model never resolves a registry itself and never knows which formula it got (`INTERFACE_SPEC.md` §8.2).
- **Secondary BC:** assert the `SecondaryFluidBC` (sink T+flow / fixed wall T / fixed heat rate / ambient) is **bound from Scenario**, not stored as a component attribute (`INTERFACE_SPEC.md` §8.3).
- **Calibration through the model:** assert HTC/UA and friction multipliers apply at the model's documented seams and never scale a balance.
- **`HXSolveResult`:** assert it returns a derived `primary_state_out` (P,h), total `Q`, integrated `dP_primary` (derived, not primary), and the `verdicts[]` of every correlation it called.
- **`MOVING_BOUNDARY` (`<<SEAM>>`):** declared, not exercised in V1.

---

# 10. Network and Topology Tests

Tests for Layer-6 (`INTERFACE_SPEC.md` §12, `SCHEMA_SPEC.md` §9, `[F7]`).

## 10.1 Port connection

- Assert `connect(a, b)` records a non-directional peer relationship asserting equal pressure, equal enthalpy (for the passing fluid), and a node mass-flow balance; assert direction is *not* stored (role annotations are hints only).

## 10.2 No values on ports

- Assert a Port carries connectivity only (id, owner, role, peer) and **no** `P`/`h`/`ṁ`/`FluidState`/derived property (`[F10]`, anti-pattern §19-13 / `SCHEMA_SPEC.md` §20-12). Converged values live in the Result's `converged_port_values` map keyed by `PortId`, never on the port.

## 10.3 Exactly one pressure reference

- Assert `validate()` **passes** with exactly one reference (the Accumulator) and **fails** with zero or two (a second accumulator is caught by topology validation, not as a numerical pathology, `INTERFACE_SPEC.md` §12).
- Assert the three-way split: the Accumulator owns the law/value, the Network owns *which node*, the Solver owns global consistency.

## 10.4 Dangling ports

- Assert `validate()` fails on any unconnected (dangling) port with a clear message naming the port.

## 10.5 Branch groups

- Assert a well-formed splitter↔mixer branch group validates; assert parallel branches between a common splitter and mixer **share the same ΔP** with branch flows summing to the trunk (the Network states it, the Solver enforces it).
- Assert **adding a branch is a topology edit only** — no Component or Solver change (`INTERFACE_SPEC.md` §12).

## 10.6 Splitter/mixer as Junction configurations

- Assert `Splitter` (1-in/N-out) and `Mixer` (N-in/1-out) deserialize to a canonical `Junction` `type`; assert no separate Splitter/Mixer class carries physics beyond the Junction's conservation.

## 10.7 Global inventory accountant

- Assert the Network is the **single** mass-inventory accountant; assert `total_charge` is a first-class Network quantity from V1; assert no component serializes a competing inventory total (the double-counting check of the `TopologyVerdict`).

## 10.8 Loop closure conditions

- Assert "Σ pressure changes around any closed path = 0" is a **Network condition the Solver satisfies**, not a single component's job; assert the steady solve drives the `pressure_closure_residual` to within tolerance for a closed loop (the pressure-global / enthalpy-local asymmetry, `ARCHITECTURE_MASTER.md` §13).

---

# 11. Solver Tests

Tests for Layer-7 (`INTERFACE_SPEC.md` §13, `[F1] [F7]`).

## 11.1 SystemState ownership

- Assert `SystemState` is created at assembly, **owned and mutated only by the Solver**; nothing below the Solver holds a mutable reference (`[F1]`: nothing depends on the Solver).
- Assert `SystemState` stores exactly every port-node `(P, h, ṁ)` and every named internal state — and nothing else (`[F3]`).
- Assert `StateLayout.names()` is ordered and introspectable (the precondition for the future linearisation seam, `[F18]`).

## 11.2 Residual assembly

- Assert the Solver scatters trial values to each component via `PortHandle`/`InternalStateHandle` (`ComponentTrialState`) and gathers `ComponentContribution` back — **no component fetches from the network** (`INTERFACE_SPEC.md` §13.2).
- Assert the assembled residual = all component contributions + all Network continuity/closure conditions, over `SystemState`.

## 11.3 Fixed-point pressure iteration

- Assert fixed-point iteration (iterate global pressure/flow, march local enthalpy) converges a single loop to within `residual_norm` tolerance; assert it is the robust default for the vertical slice.

## 11.4 Simultaneous Newton option

- Assert simultaneous Newton–Raphson on the full residual converges the **same** loop to the **same** converged state to tolerance (the two strategies agree); assert the legacy `(R1 = ΔP_pump − ΣΔP, R2 = P_sys − P_acc)` residual shape is reproducible behind a real Network (`ARCHITECTURE_REVIEW_LEGACY.md` §5.3).

## 11.5 Finite-difference Jacobian seam

- Assert the Solver obtains the Jacobian itself by **structured FD** — a copy-the-array-and-bump-one-entry over the component contract (`[F18]`); assert a component is **not required** to provide derivatives, only to be differentiable (no hidden non-smooth branch at the saturation line — sweep a quality transition and assert residual continuity).
- Assert an optional analytic/AD Jacobian override (when a component provides one) yields the same converged state as FD. **AD through the property layer is not promised** and is not assumed by any test (anti-pattern §16-17).

## 11.6 Convergence metadata

- Assert `ConvergenceMetadata {iterations, final_residual_norm, converged, strategy}` is emitted on every solve, converged or not.

## 11.7 Failure reporting

- Assert a non-converging problem reports `converged: false` with the honest final residual and strategy; assert the Solver does not raise-and-discard the partial state.

## 11.8 Non-converged Result persistence

- Assert a non-converged solve still produces a **valid serialized Result** carrying its (non-converged) state and its invariants honestly (`SCHEMA_SPEC.md` §14.3) — so a DOE can record and analyze failed points, never hide them (anti-pattern `SCHEMA_SPEC.md` §20-14).

## 11.9 Solver isolation

- Assert the Solver **never** calls a correlation, geometry, or property formula directly; assert it works for *any* valid Network (swap the two-component slice for a three-component loop with no solver change).

---

# 12. Result and Invariant Tests

Tests for the output unit (`INTERFACE_SPEC.md` §14, `SCHEMA_SPEC.md` §14–§16).

## 12.1 Minimal stored state

- Assert a Result stores **only** `converged_port_values {PortId → (P,h,ṁ)}`, `converged_internal_states {(ComponentId, name) → float[]}`, and a `tuple_ref` — nothing else is a stored number (`[F3]`, `SCHEMA_SPEC.md` §2.3).

## 12.2 No stored derived properties

- Assert `T`, `x`, `ρ`, `μ`, `k`, profiles, heat-rejected, subcooling, pump power are **derived on demand** (recomputed from stored `(P,h)` through FluidState), **never** serialized as primary state (`SCHEMA_SPEC.md` §2.4, anti-pattern §20-1).
- Assert the one sanctioned exception — `cached_profiles` — is explicitly marked `post_processing_cache`, physically separated, regenerable, and never read back as canonical (`SCHEMA_SPEC.md` §14.4).

## 12.3 tuple_ref required

- Assert a Result **without** a `tuple_ref` is malformed (unreproducible, `SCHEMA_SPEC.md` §20-4); assert `tuple_ref` may be by-value or content-hash and that a long-term archival Result embeds its tuple.

## 12.4 Energy imbalance

- Assert `energy_imbalance` [W] is present, computed from un-calibrated conservation, and within the acceptance target (< 1% of throughput, `VALIDATION_PLAN.md`).

## 12.5 Mass imbalance

- Assert `mass_imbalance` [kg/s] (`Σṁ` at nodes / global continuity) is present and within tolerance.

## 12.6 Pressure closure residual

- Assert `pressure_closure_residual` [Pa] (Σ ΔP around closed loops) is present and within the acceptance target (< 1%).

## 12.7 Bound checks

- Assert `bound_checks` record `0 ≤ x ≤ 1` and `T < T_crit` with pass/fail, worst value, and location; assert a violated bound is reported, not silently clamped.

## 12.8 Validity warnings

- Assert every non-`IN_ENVELOPE` correlation/HX call is surfaced into `validity_warnings` with status, closure identity, envelope reference, and `violated` bounds (`SCHEMA_SPEC.md` §16.2); assert an in-envelope run has an empty list. *A warning that does not reach the Result does not exist.*

## 12.9 Calibration report

- Assert `calibration_report` is present **even under `NONE`** (empty factors list); a Result missing it is malformed (§8.6).

## 12.10 Predictive/calibrated flag

- Assert `predictive_or_calibrated ∈ {PREDICTIVE, CALIBRATED}` is present and consistent with the run's mode; assert the malformed-Result guard fires when any of `invariants`, `calibration_report`, `validity_warnings`, `convergence_metadata`, `tuple_ref` is absent (`SCHEMA_SPEC.md` §14.5).

---

# 13. Schema and Serialization Tests

Tests for the persisted artifacts (`SCHEMA_SPEC.md`).

## 13.1 schema_version required

- Assert every top-level artifact (tuple, Result, DOE dataset, validation case, property-table file) carries a `schema_version`; an unversioned artifact is rejected (anti-pattern §20-2). Assert `schema_version` is distinct from `project_version` and from any model `version`.

## 13.2 Tuple serialization/deserialization

- Assert a `ReproducibilityTuple` round-trips: deserialize→serialize is stable under the canonicalization rule; all fields (topology, parameters, geometries, discretizations, fluid identities, backend/correlation/hx-model/accumulator-law selections, calibration, scenario, solver settings, metadata) survive (`SCHEMA_SPEC.md` §4).

## 13.3 Result serialization/deserialization

- Assert a `Result` round-trips: stored state, invariants, reports, closure metadata, convergence metadata, and the predictive/calibrated flag survive; the optional `cached_profiles` is omittable and regenerable.

## 13.4 References and content-hash placeholder

- Assert `$ref` (path) and `@hash` (content-hash) both resolve; an unresolvable non-seam reference is a deserialization error (`SCHEMA_SPEC.md` §3.4). Assert the **canonicalization rule is documented and recorded in `metadata`** so a reader can reproduce the hash (the rule itself is an implementation decision settled at first serializer authoring, `SCHEMA_SPEC.md` §21.2-3 — the test asserts *presence and determinism*, not a specific algorithm).

## 13.5 Model selections explicit

- Assert every swappable model is a named, **canonical** (never alias) binding in the tuple — backend per fluid, correlation per slot, hx-model per exchanger, accumulator-law per accumulator (`SCHEMA_SPEC.md` §11). Assert the four selection families live in their four distinct fields/registries (a backend in `correlation_selections` is anti-pattern §20-11).

## 13.6 No hidden defaults

- Assert a legitimate default (gravity = 1 g; calibration = neutral; empty `options`) is **written explicitly** so the file is self-contained (`SCHEMA_SPEC.md` §2.6). Assert no number in a Result depended on a constructor default, import-time global, or call order not named in the tuple (anti-pattern §20-3).

## 13.7 Calibration persisted

- Assert calibration appears in the **same shape** as input (tuple §12) and report (Result §12); assert a `TARGET` factor is fully persisted (target, value, mode, scope, seam) and a `NONE` run persists an empty factors list.

## 13.8 Validity warnings persisted

- Assert non-`IN_ENVELOPE` verdicts persist into `validity_warnings`; assert the static `ValidityEnvelope` is serialized **once** (catalogue/registry export) and referenced by `$ref`, never duplicated into every Result (`SCHEMA_SPEC.md` §16.3).

## 13.9 DOE dataset schema basic checks (`<<SEAM>>`)

- Assert a `DOEDataset` serializes with `fixed_network`, `varied_axes`, `sampling`, and a `points` list of (tuple_ref, result_ref) pairs; assert **failed points are first-class** (`status: FAILED` with a `failure` record), never dropped (anti-pattern §20-14). V1 tests the *schema shape*, not a real sweep (Phase 5).

---

# 14. Literature Validation Tests

The Level-4 cases (`VALIDATION_PLAN.md`, `ARCHITECTURE_REVIEW_LEGACY.md` §7.3, `SCHEMA_SPEC.md` §18). Each case is wired from commit one (`ARCHITECTURE_MASTER.md` §17 harvest item 6) but **gated on data readiness**. Each is serialized as a `ValidationCase` (`SCHEMA_SPEC.md` §18): inputs → Scenario, measured quantities + uncertainty, expected outputs + tolerance, comparison metrics.

## 14.1 Kokate 2024 — R-134a microchannel (first end-to-end target)

- **Data needed:** Kokate digitised HTC-vs-q″, ΔP-vs-q″, HTC-vs-G tables + Kokate (2023) Table-5 system baseline + MAE Eq. 17 (from PyP2PL `utils/validation.py`, **Reuse** — `ARCHITECTURE_REVIEW_LEGACY.md` §4.3). The digitised data must be **sourced, content-hash pinned** (`SCHEMA_SPEC.md` §18).
- **Expected quantities:** boiling HTC vs heat flux and mass flux; two-phase ΔP vs heat flux; outlet quality.
- **Comparison metric:** MAE per Kokate Eq. 17 on HTC; relative error on ΔP.
- **Acceptance:** MAE within the case-declared tolerance against the reported uncertainty band; the run uses the five ported boiling correlations + MSH/Churchill ΔP under the contract.
- **Readiness:** the legacy digitised tables exist in PyP2PL and are **Reuse-classified**; once lifted into `data/validation/kokate_2024/` and pinned, this case is **active**. Until lifted, **`PENDING-DATA`** (skipped).

## 14.2 Li et al. 2021 — Acetone

- **Data needed:** the MPL `validation_li2021.py` embedded experimental dataset (**Reuse** — `ARCHITECTURE_REVIEW_LEGACY.md` §5.3): Mode A (evaporator component, fixed experimental ṁ, energy-balance check) and Mode B (loop, accumulator BC → `T_sat`).
- **Expected quantities:** evaporator energy balance (Mode A); loop operating point under the accumulator pressure BC (Mode B).
- **Comparison metric:** energy-balance closure (Mode A); operating-point agreement (Mode B).
- **Acceptance:** energy imbalance within target; loop quantities within case tolerance. Acetone is the project's own candidate fluid — a second, non-Kokate, non-R134a case.
- **Readiness:** dataset is embedded in legacy MPL; lift into `data/validation/li_2021/` and pin → **active**; until then **`PENDING-DATA`**.

## 14.3 Fujii 2004 — A0 embedded validation data

- **Data needed:** the High/Medium/Low cases embedded as annex comments in `A0_SS_v3_Stable` (**Reuse as data** — `ARCHITECTURE_REVIEW_LEGACY.md` §3.3): node pressures, temperatures, qualities, wall temperatures, per-region ΔP targets.
- **Expected quantities:** node profiles (P, T, x, T_wall) and per-region ΔP — a geometry-resolved case.
- **Comparison metric:** per-node and per-region relative error.
- **Acceptance:** profiles within case tolerance; per-region ΔP within tolerance (the `R*` calibration concept may be exercised here, reported as `TARGET`).
- **Readiness:** the numbers exist in A0 annex comments; transcribe into `data/validation/fujii_2004/` and pin → **active**; until then **`PENDING-DATA`**.

## 14.4 PyP2PL example sweeps as initial fixtures

- **Data needed:** PyP2PL `examples/01–04` + their `.csv`/`.png` **outputs** (**Reuse as Scenario/Result fixtures** — `ARCHITECTURE_REVIEW_LEGACY.md` §4.3; note the CSVs are sweep *outputs*, not property tables).
- **Expected quantities:** charge ratio, coolant temp, heat flux, 2-D q×T_cool, fluid comparison sweeps.
- **Comparison metric:** these are the **first Phase-5 Scenario/Result fixtures** — used as smoke/regression fixtures for the Scenario→Result mapping, not as independent literature truth.
- **Acceptance:** the framework reproduces the qualitative sweep trends; quantitative agreement is secondary (these are the project's own prior outputs, not measured data).
- **Readiness:** the example files exist in legacy; lift into `examples/` → **active** as fixtures.

## 14.5 Readiness summary

All four cases are **declared and wired now**; their pass/fail gating is defined; **each is `PENDING-DATA` until its digitised/transcribed data is lifted from legacy into `data/validation/` and content-hash pinned** (`SCHEMA_SPEC.md` §18, §21.2-2). The data is a transcription/digitisation task on assets that **exist in `legacy/`** (unlike the 29 property CSVs, which are missing) — so the literature level is *low-risk to activate*, gated only on the lift, not on locating lost data.

---

# 15. Regression Test Strategy

## 15.1 Golden results

- For every committed example (the vertical slice; each active literature case; the PyP2PL fixtures), store the converged `Result` as a **golden file** (`examples/*/`, `SCHEMA_SPEC.md` §19). A golden file stores the minimal state + invariants + reports — never derived profiles (it is itself subject to §12).

## 15.2 Tolerance policy

- Numeric regression compares stored `(P, h, ṁ)` and internal states to the golden, plus the invariants, to a **stated tolerance** (tighter than physical-validity tolerance — regression catches *drift*, not just *error*). Property-dependent values are compared against a **pinned backend version** so a CoolProp upgrade does not masquerade as a code regression.

## 15.3 When to update baselines

- A baseline is updated **only** by a deliberate, reviewed action that documents *why* the numbers changed (a corrected equation, a chosen correlation swap, a new backend version). An accidental drift fails the regression and **blocks the change** until either the bug is fixed or the baseline is consciously updated with justification. Silent baseline updates are forbidden.

## 15.4 Protecting against accidental model changes

- A model-selection or calibration change that alters numbers must change the corresponding **tuple binding**, which changes the tuple's content-hash, which makes the regression diff *explainable* by a named selection edit. A number that changed with **no** tuple edit is an accidental model change and is the regression's primary target (it implies a hidden default — anti-pattern §20-3).

## 15.5 Calibrated vs predictive baselines

- Predictive (`NONE`) and calibrated (`TARGET`) Results have **separate baselines** and are **never cross-compared** (`INTERFACE_SPEC.md` §14, anti-pattern §20-16). A regression suite asserts the `predictive_or_calibrated` flag matches the baseline's flag before comparing any number.

---

# 16. Architecture Compliance Tests

The anti-pattern checklists (`ARCHITECTURE_MASTER.md` §19, `INTERFACE_SPEC.md` §16, `CORRELATION_CONTRACT.md` §13, `SCHEMA_SPEC.md` §20) as **tests or review gates**. Where detectable programmatically, an automated test; otherwise a named review-gate item (§18).

## 16.1 No direct CoolProp calls in components

- **Test:** a component obtains properties only through `FluidState` derivation in `ctx`; assert no component imports or calls a property engine directly (the per-component property-engine construction is the legacy violation `ARCHITECTURE_REVIEW_LEGACY.md` §7.2-2; anti-pattern §16-12).

## 16.2 No state on ports

- **Test:** a Port has no `P`/`h`/`ṁ`/`FluidState`/derived field; a serialized port record carries connectivity only (`[F10]`, anti-pattern §19-13 / §20-12).

## 16.3 No derived properties stored

- **Test:** neither a `SystemState`, a Result, nor a tuple stores `T`/`x`/`ρ`/`μ`/`k`/closure outputs as primary data; only `(P,h,ṁ)` + named internal states (`[F3]`, anti-pattern §20-1). The sole exception (`cached_profiles`) is explicitly marked and regenerable.

## 16.4 No correlations receiving components/geometries

- **Test:** a correlation's input is a role-typed `CorrelationInput` of declared scalars + `FluidState`; assert it never receives a `Geometry` or `Component` (`CORRELATION_CONTRACT.md` §13-2). The forbidden `Correlation → Component` direction is made unrepresentable by the input types.

## 16.5 No hidden calibration

- **Test:** under `NONE` a correlation output equals raw physics; calibration is an external value object applied at the seam, friction-gradient/HTC/UA only, always reported (`CORRELATION_CONTRACT.md` §13-1, anti-pattern §19-3).

## 16.6 No solver-aware components

- **Test:** a component's `contribute` consumes only handed-in trial state + its own slots; assert it never names the Network, a neighbour, another branch's flow, the Solver, a timestep, or an iteration scheme (`INTERFACE_SPEC.md` §16-14/15, anti-pattern §19-2/§19-5). **Nothing depends on the Solver** (a dependency-direction test).

## 16.7 No mesh in geometry

- **Test:** no geometry type carries a segment/zone count; switching `Lumped ↔ Segmented` touches no geometry field (`[F16]`, anti-pattern §19-7 / §20-8).

## 16.8 No accumulator law parameters in geometry

- **Test:** `AccumulatorGeometry` carries no `V_gas_charge`/spring rate/bellows area/polytropic index; all law parameters travel in `law_params`/`thermal` with the law selection; the accumulator stores `V_g`, not `P_sys` (`[F9] [F15]`, anti-pattern §19-8 / §20-7/§20-10).

## 16.9 Additional programmatic guards

- **ε-NTU/LMTD not a correlation:** assert no heat-exchange method is registered in the `CorrelationRegistry` (anti-pattern §16-6).
- **PropertyBackend not in correlation registry:** assert the backend lives in its own registry (anti-pattern §19-9).
- **No run-on-import / module-level mutable state:** assert importing any module triggers no solve, no plot, no global mutation (the A0 violation, `ARCHITECTURE_REVIEW_LEGACY.md` §3.2; anti-pattern Rule 2).
- **No `_last_dP`/`_last_Q` caches:** assert no correlation or component caches a closure output between calls (anti-pattern §16-3).
- **Speculative generality:** review-gate — no plugin system, DI container, event bus, abstract-primitive component, or over-generalized pipe trajectory/accumulator law beyond the two concrete v1 cases (anti-pattern §16-18).

---

# 17. Test Data and Repository Organization

Recommended layout (aligned with `SCHEMA_SPEC.md` §19):

```
mpl-loop-sim/
├── tests/                          # the test suites (unit → integration → compliance)
│   ├── unit/                       #   equation + value-object tests (§3.1)
│   ├── property/                   #   PropertyBackend contract tests (§5)
│   ├── correlations/              #   correlation-contract + migration tests (§7)
│   ├── components/                #   per-component contract tests (§9)
│   ├── network/                   #   topology validation tests (§10)
│   ├── solver/                    #   solver + invariant tests (§11)
│   ├── schema/                    #   serialization round-trip tests (§13)
│   ├── compliance/                #   anti-pattern guard tests (§16)
│   └── validation/                #   literature-case harness (§14)
├── examples/                       # committed tuple+result fixtures + goldens (§15.1)
│   ├── two_component_loop/         #   the vertical-slice fixture (§4)
│   └── kokate_r134a/               #   validation-case tuple + expected result
├── data/
│   ├── validation/                 # validation case files + digitised reference data (§14)
│   │   ├── kokate_2024/  li_2021/  fujii_2004/
│   ├── surrogates/                 # DOE dataset manifests (Phase 5; heavy payloads git-ignored)
│   └── property_tables/            # TabulatedPropertyBackend CSVs — the 29-CSV recovery target
│       └── r134a/                  #   currently MISSING (PENDING-DATA)
└── docs/                           # this plan + the three upstream specs
```

## 17.1 What to commit

- **Commit:** all test suites; the schema; validation **case files** + their **digitised** reference data; small example tuples/results and their goldens; a DOE dataset **manifest** (the `points` list with refs). These are small, canonical, and reproducibility-bearing (`SCHEMA_SPEC.md` §19).

## 17.2 What to git-ignore

- **Do not commit:** bulk DOE **result collections** (potentially thousands of files — keep only the manifest); the `cached_profiles` post-processing payload (regenerable from `(P,h)`); trained surrogate weight blobs beyond a size threshold (reference by content-hash, store in an artifact store). **Never commit** anything that re-derives from a committed tuple (the §2.3 minimal-state principle applied to the repo).

## 17.3 Handling missing property tables

- `data/property_tables/` is **structurally present but functionally empty** until the 29 CSVs are recovered, schema-verified, versioned, and content-hash pinned (`ARCHITECTURE_MASTER.md` §17, `SCHEMA_SPEC.md` §5.4/§21.2-1). Until then:
  - `TabulatedPropertyBackend` numerical tests are **`PENDING-DATA`/skipped** (§5.7);
  - a tuple selecting `backend: "Tabulated"` is **declarable but unresolvable** — the test asserts a clear unresolved-data error, never a silent fallback to a wrong value;
  - committed CSVs, when recovered, are pinned by content-hash so a Result is reproducible only against the exact tables it used.

---

# 18. Acceptance Gates Before Implementation Phases

Each gate lists **required tests**, **pass criteria**, and **blockers**. A phase does not begin until the prior gate is green. Phases map to the harvest order (`ARCHITECTURE_MASTER.md` §17).

## 18.1 Gate 1 — Core data + property + schema (Phase 1)

- **Required tests:** FluidState (§5.1), CoolPropBackend (§5.2–§5.6), Geometry immutability + PipePath (§6.1–§6.5), tuple/Result round-trip + versioning + no-hidden-defaults (§13.1–§13.6), the compliance guards on stored-vs-derived and ports (§16.2–§16.3, §16.9 import-time).
- **Pass criteria:** P,h state derives the full property set against CoolProp reference; out-of-range returns `OUT_OF_RANGE`/`NaN`; geometry is immutable and mesh-free; tuple+Result serialize and round-trip; every artifact versioned.
- **Blockers:** none architectural. `TabulatedPropertyBackend` numerics are `PENDING-DATA` but do not block the gate (CoolProp is the default).

## 18.2 Gate 2 — Correlations + calibration (Phase 2)

- **Required tests:** correlation contract (§7.1–§7.9), legacy migration (§7.10), calibration NONE/TARGET + resolution + R*-friction-only + conservation firewall (§8), the correlation anti-pattern guards (§16.4–§16.5, §16.9 ε-NTU/registry).
- **Pass criteria:** closures are stateless, role-typed, gradient-returning, verdict-bearing, envelope-checked; calibration scales friction-gradient/HTC/UA only and **cannot mask** an imbalance; every Adapt closure reproduces its legacy number with hacks stripped.
- **Blockers:** per-correlation `ValidityEnvelope` bounds are a **literature task per closure** (`CORRELATION_CONTRACT.md` §14.2-1) — a closure registered without an envelope is inadmissible, so envelope population gates *catalogue completeness*, not the contract. The migration tests need the legacy `tests/*` oracles (present in `legacy/`).

## 18.3 Gate 3 — Pipe + Pump + Accumulator (Phase 3)

- **Required tests:** the component contribution-contract test (§3.5); Pipe (§9.2) including the gradient kernel and R* placement; Pump (§9.1); Accumulator (§9.5) including PCA/HCA law numerics, geometry↔law separation, and `V_g`-stored/`P`-derived; the compliance guards on solver-awareness and accumulator-geometry (§16.6, §16.8).
- **Pass criteria:** each component returns correct residuals with frozen-zero derivatives, consumes only handed-in trial state, reaches outside itself for nothing; the Pipe integrates the one-cell kernel; PCA/HCA reproduce MPL legacy law values; no `P_sys` stored on the accumulator.
- **Blockers:** none. Bellows/spring/gas-charged law numerics are `<<SEAM>>` (V1 asserts only slot-acceptance and geometry↔law separation).

## 18.4 Gate 4 — Evaporator + Condenser + loop solver (Phase 4)

- **Required tests:** Evaporator (§9.3), Condenser (§9.4), HeatExchangerModel (§9.9); Network/topology (§10); Solver fixed-point + Newton agreement + FD Jacobian + non-converged persistence (§11); the full **vertical-slice integration test** (§4) extended to a complete loop; Result/invariant tests (§12); the **first literature case** (§14.1 Kokate) when data is lifted.
- **Pass criteria:** a complete loop converges by both strategies to the same state; all invariants within the acceptance targets (energy < 1%, pressure-closure < 1%, `0 ≤ x ≤ 1`); the Result is well-formed; topology validation enforces one reference / no dangling ports / well-formed branches / single inventory accountant; Kokate MAE within tolerance **once data is pinned**.
- **Blockers:** the literature pass/fail is **`PENDING-DATA`** until Kokate/Li/Fujii data is lifted from `legacy/` and pinned (§14.5) — a low-risk transcription task, since the data exists in `legacy/`.

## 18.5 Gate 5 — DOE / surrogate readiness (Phase 5, schema only in V1)

- **Required tests:** DOE dataset schema shape + failed-point-first-class (§13.9); the Scenario→Result mapping reproducibility (§2.5); the `CUSTOM_CLOSURE` admissibility contract (a stub surrogate obeys the role contract + declares a training-domain envelope, `CORRELATION_CONTRACT.md` §10).
- **Pass criteria:** a DOE dataset serializes, references one fixed network, records varied Scenario axes, and records failed points; a stub surrogate is admissible only with a declared envelope + training-dataset reference.
- **Blockers:** real surrogate generation is Phase 5 work; V1 gates only the **schema + admissibility contract**, not a trained model.

## 18.6 Gate 6 — Dynamic seams (Phase 6 readiness, declared only in V1)

- **Required tests:** internal states are named-but-frozen across all components (§9); `MovingBoundaryDiscretization` is declarable and serializes (§6.7); the `dynamic` solver block serializes as null (`SCHEMA_SPEC.md` §13); `disturbances` serializes as empty (`SCHEMA_SPEC.md` §10.3); `SystemState` is ordered and introspectable (§11.1).
- **Pass criteria:** every dynamic seam is **present and shaped** but unbuilt; activating Phase 6 fills a declared field/unfreezes a named state rather than restructuring (`ARCHITECTURE_MASTER.md` §16).
- **Blockers:** none for V1 — these are seam-existence assertions, not dynamic-physics tests.

---

# 19. Risks and Failure Modes

Each risk names its **detection** (the test/invariant that catches it) and its **mitigation**.

1. **CoolProp instability near saturation.** Property slopes have kinks at `x = 0`/`x = 1`; near-critical and near-zero-quality states are the normal regime. *Detection:* §5.5 out-of-range tests; §11.5 residual-continuity sweep across the dome. *Mitigation:* `(P,h)` buys continuity (not smoothness); the backend returns `OUT_OF_RANGE`/`NaN` honestly near the envelope edge; smoothed/regularised derivatives are the recommended technique for the future gradient path (`[F18]`), not assumed in V1.

2. **Invalid correlations outside their envelope.** A closure used past its validated region can be physically meaningless. *Detection:* §7.5–§7.6 envelope tests; `validity_warnings` in every Result (§12.8). *Mitigation:* `EXTRAPOLATED`/`OUT_OF_RANGE` verdicts surfaced into the Result; the researcher decides acceptability but is never unaware; a closure without an envelope is inadmissible.

3. **Pressure loop not closing.** The global pressure-closure condition may fail to converge (Ledinegg behaviour, ill-conditioning). *Detection:* §12.6 `pressure_closure_residual`; §11.7–§11.8 non-converged reporting. *Mitigation:* both fixed-point and Newton strategies available; non-convergence is reported honestly with the partial state, never hidden.

4. **Hidden derived state (drift).** A cached `T`/`ρ` beside `(P,h)` drifts invisibly until a balance violates. *Detection:* §16.3 stored-vs-derived guard; §13.6 no-hidden-defaults; the conservation invariants (§12.4–§12.6). *Mitigation:* only `(P,h,ṁ)` + named internal states stored anywhere; FluidState derives the rest; the #1 legacy silent-divergence trap (`ARCHITECTURE_REVIEW_LEGACY.md` §7.2-1) is a first-class compliance test.

5. **Calibration masking errors.** A wrong calibration could appear to "fix" a result. *Detection:* §8.8 conservation-firewall test (invariants computed from un-calibrated conservation get *worse*, never falsely pass). *Mitigation:* calibration scales closures never balances; `TARGET` results flagged `CALIBRATED` and never compared as-equal to predictive.

6. **Legacy equations ported incorrectly.** A migration may subtly alter a formula. *Detection:* §7.10 migration tests against legacy oracles; §15 regression goldens. *Mitigation:* each Adapt closure must reproduce its legacy number with hacks stripped before it is admissible; the legacy `tests/*` serve as oracles.

7. **Missing property tables.** The 29 CSVs are absent; `σ_e`/`ε_r` and 29-fluid breadth are unavailable. *Detection:* §5.7 `PENDING-DATA` skips; §17.3 unresolved-data error on a `Tabulated` selection. *Mitigation:* CoolProp is the default and unblocks all V1 work; the tabulated backend's *interface* is tested with a stub; the data recovery is a tracked parallel task, never a silent fallback.

8. **Insufficient validation data.** Literature cases cannot pass without digitised data. *Detection:* §14 `PENDING-DATA` gating. *Mitigation:* the data **exists in `legacy/`** (Kokate in PyP2PL, Li in MPL, Fujii in A0) — a transcription/lift task, not lost-data recovery; the harness is wired now so activation is a data lift, not new code.

---

# 20. Readiness for Implementation

## 20.1 Verdict

**The testing strategy is mature enough to drive test-first implementation of Phases 1–4 (steady-state).** Every frozen contract in the four upstream specs maps to concrete tests with pass/fail criteria; the development order and acceptance gates are defined; the anti-pattern checklists are converted into automated guards and review gates; the vertical slice gives an unambiguous first integration target. Nothing in this plan requires reopening a frozen decision.

## 20.2 Remaining blockers (all data/catalogue, none architectural)

1. **The 29 tabulated property CSVs are missing** (`ARCHITECTURE_MASTER.md` §17, `SCHEMA_SPEC.md` §21.2-1). Blocks `TabulatedPropertyBackend` numerics and `σ_e`/`ε_r` runs — **not** the framework, the schema, or the CoolProp-based V1. Its tests are `PENDING-DATA` (§5.7).
2. **Literature digitised data must be lifted and pinned** (§14, `SCHEMA_SPEC.md` §21.2-2). Blocks the literature *pass/fail*, not the harness. **Low risk** — the data exists in `legacy/` and needs transcription into `data/validation/`, not recovery.
3. **Per-correlation `ValidityEnvelope` bounds must be sourced** (`CORRELATION_CONTRACT.md` §14.2-1). A literature task per closure; gates *catalogue completeness*, not the contract — an envelope-less closure is simply inadmissible until its bounds are populated.
4. **The content-hash canonicalization rule must be fixed at first serializer authoring** (`SCHEMA_SPEC.md` §21.2-3). An implementation decision (recommend canonical-JSON, sorted keys); the schema tests assert *determinism and recording*, not a specific algorithm.

## 20.3 Conclusion

The four interface documents of `ARCHITECTURE_MASTER.md` §18 are complete: `INTERFACE_SPEC.md`, `SCHEMA_SPEC.md`, `CORRELATION_CONTRACT.md`, and this `TEST_PLAN_V1.md`. With this plan, **implementation of Phases 1–4 may begin test-first**, starting from the minimal vertical slice (§4) and proceeding gate by gate (§18). The blockers above are data-recovery and catalogue-population tasks that proceed in parallel with implementation; none of them, and nothing in this plan, reopens a frozen architecture decision.

---

*End of TEST_PLAN_V1.md — the V1 steady-state validation and testing strategy for the MPL simulation framework. Subordinate to ARCHITECTURE_MASTER.md, INTERFACE_SPEC.md, CORRELATION_CONTRACT.md, and SCHEMA_SPEC.md. It defines test levels, cases, checks, acceptance criteria, and development order; it writes no code, creates no test files, and implements no tests. This completes the four interface documents of the §18 implementation gate.*
