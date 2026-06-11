# ARCHITECTURE_FINAL_AUDIT.md

**Final pre-implementation coherence audit of the MPL simulation framework documentation.**

Status: **audit only.** No existing file was modified, no architecture was redesigned, no frozen decision was reopened, and no implementation code was produced. This document records findings; it does not act on them.

Scope audited (the eight binding documents):
`ARCHITECTURE_MASTER.md`, `INTERFACE_SPEC.md`, `CORRELATION_CONTRACT.md`, `SCHEMA_SPEC.md`, `TEST_PLAN_V1.md`, `IMPLEMENTATION_PLAN.md`, `DECISION_LOG.md`, `ARCHITECTURE_REVIEW_LEGACY.md`.

Method: each document was read in full. Concept ownership, interface signatures, schema fields, the correlation contract, the test mapping, the phase sequence, and the legacy verdicts were cross-checked pairwise for contradiction, terminology drift, over-/under-specification, and implementation risk. External references (`VALIDATION_PLAN.md`, the `ARCHITECTURE_LEVEL_1/2/3.md` trail, `OPEN_ARCHITECTURE_QUESTIONS.md`) were confirmed to exist and, where they carry load-bearing values (the <1 % invariant tolerances), to agree.

Posture: **conservative.** The default recommendation is *no change* wherever the documentation is already coherent. Findings are documentation-consistency items; none is an architectural defect.

---

# 1. Executive Verdict

**APPROVED WITH MINOR FIXES.**

The architecture is coherent end-to-end. The frozen decisions `[F1]`–`[F18]` and Decisions 001–009 are expressed consistently across the master, the three interface documents, the test plan, and the roadmap. The stored-vs-derived boundary, the dependency DAG, the correlation purity contract, the calibration firewall, the accumulator geometry↔law separation, the `HeatExchangerModel` separation, and the five-part Scenario are stated the same way wherever they appear. The legacy harvest order is identical across `ARCHITECTURE_REVIEW_LEGACY.md`, `ARCHITECTURE_MASTER.md` §17, and `IMPLEMENTATION_PLAN.md` §20.

There are **no CRITICAL findings** — nothing forces a wrong implementation or contradicts a frozen contract at the level of a signature, a stored quantity, or an ownership rule.

There are **two MAJOR findings**, both **documentation-consistency / governance**, not architecture:
1. A phase-numbering collision between `IMPLEMENTATION_PLAN.md` (fine 0–14) and the other documents (coarse "Phases 1–4", "Phase 5 = DOE", "Phase 6 = dynamics"). The same token "Phase 5"/"Phase 6" denotes different work in different documents, and `TEST_PLAN_V1.md` §18 keys its acceptance gates on the coarse numbers.
2. `DECISION_LOG.md` stops at Decision 009 and does not record the four interface-era refinements (the `HeatExchangerModel` concept and its departure from the master's original enumerated role, `PipePath`, the accumulator geometry↔law split, the five-part Scenario) or the two new tuple selection fields — even though the documents' own governance rules require frozen-surface changes to be logged.

Neither MAJOR blocks Phase 0 (tooling). Both should be resolved before substantive coding begins (Phase 1), because both are navigation/governance hazards for implementation agents that cross-reference documents. The remaining findings are MINOR (wording, enumeration alignment, stale "to-be-applied" notes) or NOTE (already-tracked data tasks).

**Phase 0 may begin now. The MAJOR fixes are paperwork, not redesign.**

---

# 2. Critical Findings

**None.**

No contradiction was found in any of the items the brief enumerated as critical risk areas:

- **FluidState ownership** — pure `(P, h, identity)`, three fields, no stored derived property, no backend reference, no `mdot`: stated identically in MASTER §5, INTERFACE_SPEC §3.2, SCHEMA §14.1, TEST_PLAN §5.1, DECISION_LOG 006, IMPL Phase 1.
- **PropertyBackend separation** — Layer-1 citizen, own registry, vector-first, capability-flagged, no extrapolation by stealth, never in the correlation registry: MASTER §6, INTERFACE_SPEC §3.3–§3.4, CORRELATION_CONTRACT §1.3/§11.7, SCHEMA §5, TEST_PLAN §5, DECISION_LOG 006.
- **Port vs SystemState** — Port connectivity-only (id, owner, role, peer); all unknowns in solver-owned `SystemState`; `PortState`/`FlowState` retired: MASTER §7, INTERFACE_SPEC §4, SCHEMA §8/§14.1, TEST_PLAN §10.2, DECISION_LOG 004 (closing 002).
- **Geometry vs Discretization** — immutable flat typed family supplying scalars; mesh derived-from-never-stored-in geometry; fidelity switch touches no geometry field: MASTER §8/§9, INTERFACE_SPEC §5/§6, SCHEMA §6/§7, TEST_PLAN §6, DECISION_LOG 007.
- **Correlation vs HeatExchangerModel** — correlation returns one local closure value; HX model orchestrates a whole exchanger and *consumes* correlations; separate registries: MASTER §2/§10, INTERFACE_SPEC §7/§8, CORRELATION_CONTRACT §1.2/§1.3/§3, SCHEMA §11, TEST_PLAN §9.9.
- **Correlation vs PropertyBackend** — distinct contracts, distinct registries, DAG-cycle guard: consistent (above).
- **Calibration seam** — value object applied by the component at the output seam; targets `FRICTION_GRADIENT | HTC | UA` only; conservation firewall; resolution slot→component→global→neutral: MASTER §11, INTERFACE_SPEC §9, CORRELATION_CONTRACT §7, SCHEMA §12, TEST_PLAN §8, DECISION_LOG 005/008.
- **Accumulator geometry vs pressure law** — `AccumulatorGeometry` containment-only; law parameters in `law_params`/`thermal`; stores `V_g`, derives `P`; never stores `P_sys`: MASTER §8/§12, INTERFACE_SPEC §5.4/§11.6, CORRELATION_CONTRACT §9, SCHEMA §6.4/§11, TEST_PLAN §9.5, DECISION_LOG 008.
- **Scenario five-part decomposition** — boundary conditions / commands / disturbances / environment / operating point: MASTER §15, INTERFACE_SPEC §10, SCHEMA §10. Consistent.
- **Result minimal storage** — only converged `(P,h,ṁ)` + named internal states + `tuple_ref` stored; profiles derived: MASTER §15, INTERFACE_SPEC §14, SCHEMA §2.3/§14, TEST_PLAN §12.
- **ReproducibilityTuple fields** — every swappable model is a named binding (see MINOR M2 for a field-decomposition wording difference, which is reconcilable, not contradictory).
- **Solver responsibilities** — owns `SystemState`; assembles contributions + Network conditions; FD-primary Jacobian; nothing depends on it: MASTER §14, INTERFACE_SPEC §13, TEST_PLAN §11.
- **Network/Component/Solver split** — where/what/how; one reference; single inventory accountant; branch closure a Network condition: MASTER §13, INTERFACE_SPEC §11/§12, SCHEMA §9, TEST_PLAN §10.
- **Legacy migration decisions** — four verdicts and harvest order identical across REVIEW_LEGACY, MASTER §17, IMPL §20, and TEST_PLAN §7.10/§14.
- **Implementation phase ordering** — the *dependency order* (data → properties → correlations → calibration → component → network → solver → result) is identical everywhere; only the *numbering scheme* collides (MAJOR-1, §3).

---

# 3. Major Findings

## MAJOR-1 — Phase-numbering collision across documents

**Severity: MAJOR (documentation/navigation; should fix before Phase 1).**

Two incompatible phase-numbering schemes are in use:

- **`IMPLEMENTATION_PLAN.md`** uses a fine **Phase 0–14** scheme: Phase 1 = core data, Phase 2 = PropertyBackend, Phase 3 = Correlation, Phase 4 = Geometry/Discretization, Phase 5 = **Calibration**, Phase 6 = **Pipe**, Phase 7 = Network, Phase 8 = Solver, Phase 9 = Result/schema, Phase 10 = Pump/Accumulator, Phase 11 = HX/Evaporator/Condenser, Phase 12 = validation, Phase 13 = **DOE/surrogate**, Phase 14 = release.
- **`ARCHITECTURE_MASTER.md`, `CORRELATION_CONTRACT.md`, `SCHEMA_SPEC.md`, `TEST_PLAN_V1.md`** use a coarse scheme: "Phases 1–4 = steady-state", **"Phase 5 = DOE/surrogate"** (MASTER §11/§16, SCHEMA §17, CORRELATION_CONTRACT §7.2), **"Phase 6 = dynamics / MovingBoundary"** (MASTER §9/§16, INTERFACE_SPEC §13.5, SCHEMA §13).

The collision is direct and load-bearing:

- "**Phase 5**" = *Calibration* in IMPL, but = *DOE/surrogate generation* everywhere else.
- "**Phase 6**" = *Pipe component* in IMPL, but = *the dynamic solver / moving-boundary* everywhere else.
- `TEST_PLAN_V1.md` §18 names its acceptance gates "(Phase 1)…(Phase 4)" with coarse content (Gate 3 = Pipe+Pump+Accumulator; Gate 4 = Evaporator+Condenser+Solver), which maps to IMPL Phases 3/5/6/8/10/11 — not to IMPL Phases 1–4.

`IMPLEMENTATION_PLAN.md` §4 asserts "the phase order **is** the harvest order … and the test order of `TEST_PLAN_V1.md` §2.2" — true for the *order*, false for the *numbers*. An implementation agent that reads "complete Phase 5 before Phase 6" in one document and "Phase 5 is DOE, deferred" in another, or that gate-checks IMPL Phase 6 (Pipe) against TEST_PLAN "Gate … Phase 6" (dynamic seams §18.6), will mis-sequence or mis-gate.

*Why it is not CRITICAL:* `IMPLEMENTATION_PLAN.md` is internally self-consistent and is the named authority for build sequencing; the architecture and contracts are unaffected. The hazard is cross-document navigation, not a wrong build.

*Recommended fix (§7):* add a one-table phase Rosetta (or renumber TEST_PLAN's gate labels to the IMPL 0–14 scheme), and have the coarse documents say "Phase 5/6 here refers to the *post-V1* surrogate/dynamic milestones of `ARCHITECTURE_MASTER.md`, distinct from the V1 build phases of `IMPLEMENTATION_PLAN.md`."

## MAJOR-2 — DECISION_LOG does not record the interface-era refinements

**Severity: MAJOR (governance/traceability; should fix before Phase 1).**

`DECISION_LOG.md` ends at Decision 009 (2026-06-10). Four substantive refinements were introduced *after* that, during interface specification, and are now embedded as frozen contract across MASTER/INTERFACE/CORRELATION/SCHEMA:

1. **`HeatExchangerModel` as a distinct concept** with its own registry, *removing* `HeatExchangeMethodInput` from the correlation role set (INTERFACE_SPEC §17-A3 calls this "a deliberate departure from MASTER §10's enumerated `HeatExchangeMethodInput`").
2. **`PipePath` trajectory** generalizing `PipeGeometry`'s elevation descriptor.
3. **Accumulator geometry↔law strict separation.**
4. **Five-part Scenario decomposition**, plus the two new tuple fields `hx_model_selections` and `accumulator_law_selections`.

The documents' own governance rules require this to be logged: INTERFACE_SPEC §1.2 ("A change to any signature marked **FROZEN** … must go through `DECISION_LOG.md`"); IMPL §2.2/§21.2 ("a change to one is a redesign requiring a `DECISION_LOG.md` entry"). Item 1 in particular alters a previously-enumerated frozen element of MASTER §10. An implementer who treats `DECISION_LOG.md` as the authoritative ledger of frozen-surface changes will find the ledger incomplete, with no dated rationale for the role-set change, the new concept, or the two tuple fields.

*Why it is not CRITICAL:* the refinements are consistently applied and mutually coherent across the four specs; the gap is the missing paper trail, not a contradiction.

*Recommended fix (§7):* add Decision 010 (and/or 011–013) recording the four refinements, their rationale, and their "supersedes/refines" relationship to `[F4]`/`[F8]`/`[F9]`/§10/§15 — even if only by reference to INTERFACE_SPEC §17. This also resolves the stale "to-be-applied" framing flagged in MINOR M1.

---

# 4. Minor Findings

## M1 — INTERFACE_SPEC §17 "Required Master Amendments" is stale (already applied)

INTERFACE_SPEC §17 lists amendments **A1–A6** as required-but-not-yet-applied to the master ("this task does not edit the master … listed for later application"). Inspection of `ARCHITECTURE_MASTER.md` shows they **have been applied**: §8 carries `PipePath` and containment-only `AccumulatorGeometry`; §10 states "ε-NTU and LMTD are *not* correlation roles"; §2 lists `HeatExchangerModel` under "Not concepts"; §15 carries the five-part Scenario and both `hx_model_selections`/`accumulator_law_selections`; §18 notes the refinements. `CORRELATION_CONTRACT.md` (§3, §9.3) and `SCHEMA_SPEC.md` (§6.4) likewise refer to "the §17-A2/A3 amendment to the master" as if pending.

Effect: a reader following INTERFACE_SPEC §17 may attempt to re-apply amendments that already exist, or conclude the master is out of date when it is not. *Fix:* mark INTERFACE_SPEC §17 "APPLIED — reconciled into MASTER vX" (or fold it into the new DECISION_LOG entry of MAJOR-2) and soften the "§17 amendment" cross-references in CORRELATION/SCHEMA to "reconciled in MASTER."

## M2 — ReproducibilityTuple field decomposition differs across the three authorities

- **INTERFACE_SPEC §15:** one combined `fluid: { FluidIdentity -> backend_name }`; **no** separate `discretizations` field (discretization implicitly inside topology/components).
- **SCHEMA §4:** split into `fluid_identities: { FluidRef -> FluidIdentity }` **and** `property_backend_selections: { FluidRef -> BackendSelection }`; **plus** a distinct top-level `discretizations: { ComponentId -> Discretization }`.
- **MASTER §15 prose:** lists "fluid identity" and neither a separate backend-selection nor a separate discretizations field.

These are reconcilable (the schema legitimately refines the in-memory shape, and keys by a serializable `FluidRef` rather than a value object), but the canonical top-level field list of the tuple should be stated once and identically. Also note INTERFACE_SPEC §15 keys the `fluid` map by `FluidIdentity` (a value object), which is awkward as a literal serialization key — SCHEMA's `FluidRef` keying is the correct realization. *Fix:* align INTERFACE_SPEC §15's field list to SCHEMA §4 (separate identity/backend, explicit discretizations) or add a one-line note that SCHEMA §4 is the authoritative decomposition.

## M3 — Correlation role enumeration is narrower in INTERFACE_SPEC than in CORRELATION_CONTRACT

`CORRELATION_CONTRACT.md` §3/§4.1 enumerates eight roles: `SINGLE_PHASE_DP`, `TWO_PHASE_DP`, `HTC`, `VOID_FRACTION`, **`FLOW_REGIME`** (a full frozen role with `FlowRegimeInput` and `FlowRegimeVerdict`), `CRITICAL_HEAT_FLUX` (seam), `VOLUME_PRESSURE_LAW`, `CUSTOM_CLOSURE` (seam). `INTERFACE_SPEC.md` §7.2 lists five "+ …", and its §7.5 role-catalogue table lists only five (omitting `FLOW_REGIME`, `CRITICAL_HEAT_FLUX`, `CUSTOM_CLOSURE`). Since CORRELATION_CONTRACT explicitly *owns* the role detail (per its scope statement and INTERFACE_SPEC §7.2's deferral), this is abbreviation rather than contradiction — but a reader of INTERFACE_SPEC §7.5 alone would not know `FLOW_REGIME` is a frozen role. *Fix:* add `FLOW_REGIME` (and the two seams, marked `<<SEAM>>`) to the INTERFACE_SPEC §7.5 catalogue, or cross-reference CORRELATION_CONTRACT §3 as the complete enumeration.

## M4 — "Malformed Result" mandatory-field set enumerated inconsistently

- **INTERFACE_SPEC §14:** malformed if missing {energy-imbalance, mass-imbalance, pressure-closure, quality-bounds, **calibration-report**} — omits `validity_warnings`, `convergence_metadata`, `tuple_ref` from the explicit list.
- **SCHEMA §14.5** and **TEST_PLAN §12.10:** malformed if missing {`validation_invariants`, `calibration_report`, `validity_warnings`, `convergence_metadata`, `tuple_ref`}.

SCHEMA and TEST_PLAN agree and are the more complete pair; INTERFACE_SPEC's enumeration is a subset (its prose elsewhere does require `tuple_ref` and `convergence`, so the intent matches). *Fix:* align INTERFACE_SPEC §14's malformed-Result enumeration to the SCHEMA/TEST_PLAN set so the "malformed" guard is defined identically in all three.

## M5 — DECISION_LOG 002 and 003 not flagged superseded in their own blocks

Decision 002 ("Port carries mdot") and Decision 003 (status "Accepted for architecture review") retain their original text and status. They are correctly closed/superseded by Decisions 004 and 006 respectively, but only the *superseding* decisions announce it; a reader scanning 002/003 in isolation sees statements that now contradict `[F10]`/`[F6]` with no inline marker. *Fix:* add a "Status: Superseded by Decision 004 / 006" line to the 002 and 003 blocks. (Cosmetic; the supersession itself is unambiguous.)

## M6 — SCHEMA §11 "four registries" wording

SCHEMA §11 says "The four registries are distinct: `PropertyBackendRegistry`, `CorrelationRegistry`, `HeatExchangerModelRegistry`, and — within the correlation registry … — the `VOLUME_PRESSURE_LAW` role." Calling it "four registries" and then stating the fourth lives *inside* the correlation registry is mildly self-contradictory; there are three registries and four selection families. *Fix:* reword to "three registries, four selection families" (the body already makes the substance correct).

---

# 5. Notes for Future Phases

These are non-blocking; all are already tracked consistently across the documents. Listed for continuity, not action.

- **N1 — VALIDATION_PLAN.md is the home of the invariant tolerances.** The <1 % energy-imbalance and <1 % pressure-closure targets that `TEST_PLAN_V1.md` (§4.3, §12.4, §12.6) attributes to `VALIDATION_PLAN.md` are present there (confirmed) and consistent. `VALIDATION_PLAN.md` is outside the audit set but is a load-bearing reference; keep it in sync if a tolerance ever changes.
- **N2 — The 29 property CSVs are missing.** `TabulatedPropertyBackend` (the only source of `σ_e`/`ε_r`) is structurally portable but functionally empty until the data is located/regenerated, schema-verified, versioned, and content-hash pinned. Tracked identically in MASTER §17, REVIEW_LEGACY §6.3, SCHEMA §5.4/§21.2, TEST_PLAN §5.7/§17.3, IMPL §20. A parallel data task; blocks nothing in the CoolProp-based V1.
- **N3 — Per-correlation `ValidityEnvelope` bounds are a per-closure literature task.** The envelope *format* is frozen; the *bounds per closure* must be sourced from each citation. Gates catalogue completeness, not the contract. (CORRELATION_CONTRACT §14.2-1, TEST_PLAN §18.2.)
- **N4 — Content-hash canonicalization rule is deferred to first serializer authoring.** Recommended canonical-JSON with sorted keys, recorded in artifact `metadata`. Tests assert determinism + recording, not a specific algorithm. (SCHEMA §21.2-3, TEST_PLAN §13.4.)
- **N5 — Secondary-side HTC (`htc_secondary`) optionality** for heat exchangers is an open HX-model-level decision, not a contract gap. (CORRELATION_CONTRACT §14.2-5, INTERFACE_SPEC §8.1.)
- **N6 — Dynamic / MovingBoundary / linearisation / surrogate seams** are declared and shaped now, built later. Their seam-existence is asserted in TEST_PLAN §18.6 and IMPL Phase deliverables. Activation is "fill a declared field / unfreeze a named state," not a redesign — confirmed consistent.

---

# 6. Cross-Document Consistency Matrix

Legend: **OK** = consistent across all documents that address it · **WARNING** = reconcilable difference in wording/decomposition/enumeration (a MINOR) · **ISSUE** = a contradiction or collision needing a fix before coding (a MAJOR) · **N/A** = not applicable.

| Concept | Status | Where checked / note |
|---|---|---|
| **FluidState** | OK | MASTER §5, INTERFACE §3.2, SCHEMA §14.1, TEST §5.1, DLOG 006 — identical (pure `(P,h,identity)`, nothing stored). |
| **PropertyBackend** | OK | MASTER §6, INTERFACE §3.3–§3.4, CORR §1.3/§11.7, SCHEMA §5, TEST §5, DLOG 006 — identical separation + contract. |
| **Port / SystemState** | OK | MASTER §7, INTERFACE §4, SCHEMA §8/§14.1, TEST §10.2, DLOG 004 — connectivity-only Port; solver-owned state. |
| **Geometry** | OK | MASTER §8, INTERFACE §5, SCHEMA §6, TEST §6, DLOG 007 — immutable flat family, scalars only. |
| **Discretization** | WARNING | Concept consistent (MASTER §9, INTERFACE §6, SCHEMA §7, DLOG 007). Tuple field placement differs: separate `discretizations` map in SCHEMA §4, folded in INTERFACE §15 (MINOR M2). |
| **Correlation** | WARNING | Contract identical (INTERFACE §7, CORR §1–§8). Role enumeration narrower in INTERFACE §7.5 than CORR §3 (MINOR M3). |
| **HeatExchangerModel** | OK | MASTER §2, INTERFACE §8, CORR §1.3/§3, SCHEMA §11, TEST §9.9 — consistently a separate concept/registry. (Decision record missing → MAJOR-2, tracked under Decisions, not a concept inconsistency.) |
| **Calibration** | OK | MASTER §11, INTERFACE §9, CORR §7, SCHEMA §12, TEST §8, DLOG 005/008 — targets, firewall, resolution identical. |
| **Accumulator** | OK | MASTER §8/§12, INTERFACE §5.4/§11.6, CORR §9, SCHEMA §6.4/§11, TEST §9.5, DLOG 008 — geometry↔law split, `V_g` stored. |
| **Scenario** | OK | MASTER §15, INTERFACE §10, SCHEMA §10 — five-part, gravity in Environment, `P_set` a BC. |
| **Result** | WARNING | Stored/derived partition identical. Malformed-field enumeration differs: INTERFACE §14 subset vs SCHEMA §14.5 / TEST §12.10 (MINOR M4). |
| **Schema** | WARNING | Versioning, minimal-state, explicit-selection all consistent. Tuple field decomposition (M2) and "four registries" wording (M6) are MINORs. |
| **Solver** | OK | MASTER §14, INTERFACE §13, TEST §11 — owns SystemState, FD-primary, nothing depends on it. |
| **Network** | OK | MASTER §13, INTERFACE §11/§12, SCHEMA §9, TEST §10 — where/what/how, one reference, single accountant. |
| **Legacy migration** | OK | REVIEW_LEGACY §2/§8, MASTER §17, IMPL §20, TEST §7.10/§14 — verdicts and harvest order identical. |
| **Implementation phases** | ISSUE | Dependency *order* identical everywhere; *numbering* collides — "Phase 5/6" mean different work in IMPL vs MASTER/TEST/CORR/SCHEMA (MAJOR-1). |

---

# 7. Required Fixes Before Coding

No fix is strictly required to begin **Phase 0** (repository/tooling scaffolding) — it is physics-free and unaffected by every finding. The two MAJOR items below should be resolved **before Phase 1** (the first substantive code), because both are hazards for any agent that cross-references documents while building:

1. **Resolve the phase-numbering collision (MAJOR-1).** Add a single canonical phase-mapping table (Rosetta) — or renumber `TEST_PLAN_V1.md` §18 gate labels to the `IMPLEMENTATION_PLAN.md` 0–14 scheme — and add one clarifying sentence to the coarse documents distinguishing the *V1 build phases* (IMPL 0–14) from the *post-V1 milestones* ("Phase 5 = surrogate/DOE", "Phase 6 = dynamics") used in MASTER/CORRELATION/SCHEMA/TEST_PLAN. Pick one scheme as primary and cross-reference the other.

2. **Close the decision-log gap (MAJOR-2).** Add `DECISION_LOG.md` entries (Decision 010+, dated) for the four interface-era refinements — `HeatExchangerModel` concept + role-set change, `PipePath`, accumulator geometry↔law split, five-part Scenario + the two tuple fields — recording rationale and their "refines `[F4]`/`[F8]`/`[F9]`/§10/§15" relationship. This satisfies the documents' own rule that frozen-surface changes pass through the log, and it lets MINOR M1 be closed at the same time.

These are edits to `IMPLEMENTATION_PLAN.md` / `TEST_PLAN_V1.md` / `DECISION_LOG.md` (and optionally a stale-note touch in `INTERFACE_SPEC.md` §17). They do not alter any frozen contract, signature, schema field, or ownership rule.

---

# 8. Recommended Fixes Before Coding

Useful but non-blocking; batch them with the MAJOR fixes or fold into the first documentation pass of Phase 0/9:

- **M1 — Mark INTERFACE_SPEC §17 "APPLIED"** and soften the "§17 amendment" references in CORRELATION_CONTRACT (§3, §9.3) and SCHEMA (§6.4) to "reconciled in MASTER."
- **M2 — State the canonical ReproducibilityTuple field list once.** Align INTERFACE_SPEC §15 to SCHEMA §4 (separate `fluid_identities` / `property_backend_selections`; explicit `discretizations`; `FluidRef` keys), or add a note that SCHEMA §4 is authoritative for the serialized decomposition.
- **M3 — Complete the role catalogue in INTERFACE_SPEC §7.5** (add `FLOW_REGIME` as frozen, `CRITICAL_HEAT_FLUX`/`CUSTOM_CLOSURE` as `<<SEAM>>`), or cross-reference CORRELATION_CONTRACT §3 as the complete enumeration.
- **M4 — Unify the malformed-Result field set** in INTERFACE_SPEC §14 to match SCHEMA §14.5 / TEST_PLAN §12.10.
- **M5 — Add inline "Superseded by …" status** lines to DECISION_LOG 002 and 003.
- **M6 — Reword SCHEMA §11** from "four registries" to "three registries, four selection families."

---

# 9. Final Recommendation

**Phase 0 can begin immediately.** Repository scaffolding, the `src/mpl_sim/` package tree, the test tree, the import-direction guard encoding the DAG, and CI are all physics-free and unblocked by every finding in this audit.

The architecture itself is **sound, internally coherent, and ready to build against.** All frozen decisions are expressed consistently across the documents; the five frozen interfaces of MASTER §18 are fully specified and mutually agreeing; the test plan maps cleanly to implementable checks; the legacy harvest is consistently classified; and the brief's enumerated risk areas (FluidState ownership, PropertyBackend separation, Port/SystemState, Geometry/Discretization, Correlation vs HX-model, calibration seam, accumulator geometry/law, Scenario, Result, tuple, solver, network split) show **no contradictions**.

The two MAJOR findings are **documentation-consistency and governance items**, not architectural defects: a phase-number Rosetta and a handful of catch-up decision-log entries. They should be cleared **before Phase 1** so that implementation agents reading any two documents together are never misdirected, but they require **no redesign, no scope change, and no reopening of a frozen decision.** The MINOR items are wording/enumeration alignments best done in the same pass; the NOTES are pre-existing, well-tracked data and catalogue tasks that proceed in parallel and block nothing in the steady-state V1.

**Recommendation: APPROVED WITH MINOR FIXES.** Clear MAJOR-1 and MAJOR-2 (documentation only) before Phase 1; begin Phase 0 now.

---

*End of ARCHITECTURE_FINAL_AUDIT.md — a read-only coherence audit. No existing file was modified, no architecture was redesigned, no frozen decision was reopened, and no implementation code was written. Findings are documentation-consistency and governance items; the architecture is approved for implementation subject to the two MAJOR paperwork fixes of §7.*
