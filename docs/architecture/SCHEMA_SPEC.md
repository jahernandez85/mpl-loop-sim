# SCHEMA_SPEC.md

**The serialization and reproducibility-schema specification for the MPL simulation framework.**

Status: **schema specification (pre-implementation).** This document specifies *how the framework's data is serialized, versioned, and archived* — the on-disk/over-the-wire shape of every artifact a run consumes or produces. It is downstream of, and subordinate to, `ARCHITECTURE_MASTER.md`, `INTERFACE_SPEC.md`, and `CORRELATION_CONTRACT.md`; where it refines those documents it does so by **specifying a serialization contract**, never by reopening a frozen decision (`[F1]`–`[F18]`, Decisions 001–009).

Companion documents (per MASTER §18): `INTERFACE_SPEC.md` (in-memory contracts + signatures), `CORRELATION_CONTRACT.md` (validity-envelope format + `ValidityVerdict` semantics), `TEST_PLAN_V1.md` (validation-level mapping). This document owns the **serialized bytes and the version fields** that `INTERFACE_SPEC.md` §14/§15 defer to it.

Horizon: 5–10 years. A `Result` and the dataset it belongs to must remain interpretable after the in-memory framework, the correlation catalogue, and the property backends have all turned over. The schema is therefore written to outlive every concrete model it references.

How to use this document:
- An implementer writing a YAML/JSON serializer should be able to produce a conforming file from the relevant section alone.
- A reviewer should be able to reject a non-conforming artifact by citing a section here.
- It specifies **no executable code, no class bodies, no language bindings.** Examples are pseudo-YAML / pseudo-JSON, language-neutral by design, and illustrative of *shape*, not authoritative over the frozen interface types (which live in `INTERFACE_SPEC.md`).

---

# 1. Scope and Status

This document specifies **serialization and reproducibility schemas, not implementation.**

- It defines the **persisted shape** (fields, nesting, references, versioning, units) of every serialized artifact the framework reads or writes.
- It does **not** define in-memory classes, method signatures, or algorithms — those are `INTERFACE_SPEC.md`'s. A serialized `Geometry` here mirrors the frozen `Geometry` value object there; this document fixes only how it is written to a file.
- It is **format-neutral.** The examples are pseudo-YAML/pseudo-JSON, but the schema is equally expressible as JSON, YAML, or any structured format with maps, lists, scalars, and references. No example here mandates a specific library, encoding, or file extension.
- Where a degree of freedom is deliberately left open (e.g. whether a tuple is embedded by value or referenced by content-hash, which serialization library is used), the document says so and names the rule that governs the choice.

A reviewer must be able to reject a non-conforming serialized artifact by citing a schema in this document. An implementer must be able to write a conforming serializer/deserializer from the relevant section alone.

## 1.1 Relationship to the frozen architecture and interfaces

Every schema here is traceable to a master/interface section and a frozen tag. The two **frozen interfaces** of MASTER §18 this document is responsible for serializing are:

| Frozen interface | In-memory contract | Serialized here in |
|---|---|---|
| Reproducibility Tuple schema (versioned) | `INTERFACE_SPEC.md` §15 | §4 |
| Result schema (versioned, minimal) | `INTERFACE_SPEC.md` §14 | §14 |

All other sections serialize the value objects and reports those two artifacts compose (Geometry §6, Scenario §10, Calibration §12, closure metadata §16, …).

A change to any field marked **`<<FROZEN>>`** in this document, or any change that breaks the ability to deserialize a previously valid artifact without a migration, is a **schema redesign** and must go through `DECISION_LOG.md` and a `schema_version` increment (§2.1).

## 1.2 Notation

This document reuses the pseudo-signature notation of `INTERFACE_SPEC.md` §1.2 for type references, and adds serialization conventions:

```
key: <Type>                  a serialized field of the given conceptual type
key: <Type>?                 optional field; absent (not null) when not applicable — never silently defaulted
key: [ <Type> ]              an ordered list
key: { K -> V }              a map / association from key K to value V
$ref: <pointer>              a reference to another artifact or in-file anchor (§3.4)
#kind: <Name>                a discriminator tag selecting one variant of a sum type
<<FROZEN>>                    field/shape may not change without a DECISION_LOG entry + schema_version bump
<<SEAM>>                      declared now, populated in a later phase; shape is fixed, may be empty in v1
@hash                        a content-hash reference (§3.4)
```

- All numeric quantities are **SI** unless a `units:` field or §3.3 names otherwise.
- All examples are illustrative. The **authoritative field types** are the `<<FROZEN>>` interface types in `INTERFACE_SPEC.md`/`CORRELATION_CONTRACT.md`; this document fixes their *serialized form*.

---

# 2. Schema Design Principles

These principles bind every schema in this document. They are the serialization-layer expression of MASTER §1 (principles), §4 (ownership), §15 (configuration/result), and the interface rules of `INTERFACE_SPEC.md` §2.

### 2.1 Versioning

- **Every top-level artifact carries a `schema_version`** (a string, e.g. `"1.0.0"`). No artifact is valid without it (anti-pattern §20). The field is the first line of defense for long-term archival: a reader 5 years on consults `schema_version` before interpreting a single other field.
- `schema_version` is a property of the **format**, distinct from `project_version` (the framework code version that produced the artifact, §4) and from any model `version` (a property of a correlation/backend, §11, §16).
- Versioning is **semantic**: a change that only *adds* optional fields is a minor bump and is backward-compatible (old readers ignore unknown fields per §2.6); a change that renames, removes, or re-types a field, or changes a default meaning, is a major bump and **requires a migration path** (§19, a `DECISION_LOG` entry).
- The same `schema_version` namespace governs all artifact types in this document, so a single version string identifies a coherent generation of tuple + result + dataset schemas.

### 2.2 Immutability

- Serialized inputs (the Reproducibility Tuple and every value object it composes — Geometry, Scenario, calibration factors, model selections) represent **immutable** in-memory value objects (`[F8]`, `INTERFACE_SPEC.md` §2 Rule 7). A serialized tuple is a frozen record; "varying a parameter" means writing a *new* tuple, never mutating an existing file in place.
- A serialized `Result` is likewise write-once: it is the immutable output paired with its immutable input. Re-running may produce a new `Result`; it never edits an existing one.
- This is what makes a tuple file the atomic unit a DOE iterates over (§17) and a content-hash a stable identity (§3.4).

### 2.3 Minimal stored state

- **Only irreducible values are serialized in a `Result`** (`[F3]`, MASTER §4.1, §15): the converged port unknowns `(P, h, mdot)` per port-node and the named component internal states. Nothing else is a stored number.
- **Derived properties are never serialized in a `Result`** (§2.4). A serialized result is reconstructable into full profiles on load, through `FluidState`, from the stored `(P, h)` and the tuple's fluid identity — but those profiles are *not in the file*.
- Minimal storage is what keeps a multi-thousand-point surrogate dataset (§17) compact and what guarantees a 5-year-old result cannot silently disagree with itself.

### 2.4 No derived properties (the serialization firewall)

> **`T`, `x`, `ρ`, `μ`, `k`, `σ`, `c_p`, `void`, `phase`, `T_sat`, `h_f`, `h_g`, `h_fg`, and all closure outputs (HTC, ΔP, ε) are NEVER serialized as primary stored data in a Result or tuple.** They are derived on load from `(P, h, identity)` through the PropertyBackend.

The moment a serialized `T` or `ρ` sits beside `(P, h)`, the file can drift from its own canonical state and the drift is invisible until a balance silently violates (MASTER §4.1, anti-pattern §20). The single exception is an **explicitly-marked, clearly-separated post-processing cache** (§14.4) — never co-mingled with stored state, never read back as canonical, and regenerable by discarding it and recomputing from `(P, h)`.

### 2.5 Explicit model selections

- **Every swappable model is a named binding in the serialized tuple** (`[F1]` Principle 7, Rule 4): the property backend per fluid, the correlation per slot, the heat-exchanger model per exchanger, the accumulator pressure law per accumulator, the discretization mode per component, the solver. Selecting one is a field in the file, resolved against a registry on load.
- No serialized artifact may rely on a model chosen by a constructor default, an import-time global, or call order. *If a model influenced a number, its selection is in the tuple* (§4, §11).

### 2.6 No hidden defaults

- **A field that matters is written explicitly.** Absence (`?`) is meaningful and bounded: it denotes "not applicable to this variant" (e.g. a `thermal` spec absent for a non-HCA accumulator law), never "use whatever the code defaults to."
- **Where a default value is legitimate** (e.g. gravity = 1 g terrestrial, calibration = neutral), the serializer **writes the resolved value explicitly** so the file is self-contained and reproducible without consulting the code that produced it. A reader never needs the framework source to know what value was used.
- Unknown fields encountered on read are **ignored, not errored**, when `schema_version` indicates a compatible-or-newer minor revision (§2.1) — this is the forward-compatibility mechanism, distinct from "hidden defaults," which concerns *writing*.

### 2.7 Reproducibility

- **A `Result` is fully reproducible from its tuple** (`[F1]` Principle 7, `CORRELATION_CONTRACT.md` §12). The serialized result carries a `tuple_ref` (§14, §3.4); re-instantiating the tuple and re-running reproduces the stored converged state to solver tolerance.
- **A `Result` records the provenance needed to interpret it:** the validation invariants, the calibration report, the validity warnings, the convergence metadata, the closure metadata of every model that contributed, and the predictive-vs-calibrated flag (§14, §16, `CORRELATION_CONTRACT.md` §12). A result missing any of these is **malformed**.
- Reproducibility is the union of §2.3 (the tuple + minimal state regenerate everything) and §2.5 (every model that touched a number is named).

### 2.8 Forward compatibility

- The schema is shaped so future additions are **additive**: new correlation roles, new geometry families (`PipePath` extension), new accumulator laws, new backends, the dynamic-state and DOE seams, and surrogate metadata all enter as **new optional fields or new discriminated-union variants**, never as a re-typing of an existing field.
- `<<SEAM>>` fields (dynamic disturbances §10, moving-boundary state counts §7, DOE/surrogate datasets §17, ML-closure traceability §16) are **declared in the schema now**, may be empty/absent in v1, and have their shape fixed so populating them later is not a redesign.

---

# 3. Top-Level File Types

The framework serializes a small, closed set of artifact types. Each is a standalone file (or document) carrying its own `schema_version`.

| Artifact | Mandatory? | Purpose | Schema § |
|---|---|---|---|
| **network/spec file** | optional (may be embedded in the tuple) | the topology + components + geometries — the reusable "loop definition" a DOE holds fixed | §8, §9 |
| **scenario file** | optional (may be embedded in the tuple) | one operating point (five-part Scenario) — the DOE axis | §10 |
| **run tuple file** (Reproducibility Tuple) | **mandatory** | the complete, versioned, self-contained run definition | §4 |
| **result file** | **mandatory** (one per completed run) | the converged irreducible state + invariants + reports, paired with its tuple | §14 |
| **DOE dataset file** | optional (Phase 5) | a collection of tuple/result references over a fixed network and varied scenarios | §17 |
| **validation case file** | optional | a literature/experimental case: inputs, measured quantities, uncertainty, expected outputs, comparison metrics | §18 |
| **property-table file(s)** | optional (data asset) | tabulated property data backing a `TabulatedPropertyBackend` | §5, §19 |

Rules:

- **The run tuple file is the only mandatory *input* artifact** and the result file the only mandatory *output*. A run cannot exist without a tuple; a completed run cannot be archived without a result (§14).
- **The network/spec and scenario files are optional decompositions.** A tuple may either *embed* its topology and scenario inline (§4) or *reference* a standalone network file and scenario file by `$ref` (§3.4). Both forms deserialize to the identical in-memory tuple. The decomposition exists so a DOE can hold one network file fixed and vary thousands of scenario files (§17).
- **The DOE dataset and validation case files are higher-order collections**, referencing many tuples/results rather than containing primary state.
- **Property-table files are a data asset**, not a run artifact; they are versioned and referenced by a `TabulatedPropertyBackend` selection (§5.4).

## 3.4 References, content-hashing, and embedding

Artifacts reference each other two ways; both are first-class and a single field may use either:

```
$ref: "examples/two_component_loop/tuple.yaml"     # a path/URI reference to another artifact
$ref: "@hash:9f2c4e..."                            # a content-hash reference (intrinsic identity)
embed: <inline object>                             # the referenced object copied inline (self-contained)
```

- **Path/URI `$ref`** points at another file by location — convenient for a working tree, but fragile across archival (the target may move). Used for the network/scenario decomposition (§3) and DOE point references (§17) within a managed dataset.
- **Content-hash `@hash`** is an intrinsic, location-independent, tamper-evident identity: the hash of the referenced artifact's *canonical serialization*. It is the **recommended identity for archival** — a `tuple_ref` or `result_id` that is a content-hash cannot silently point at mutated data (§2.2). The canonicalization rule (which normalized serialization is hashed, and with which algorithm) is an implementation decision fixed at first serializer authoring (§21.2) and **recorded in the artifact's `metadata`** so a reader can reproduce the hash.
- **`embed`** copies the referenced object inline, producing a **self-contained** artifact. A `Result` archived for the long term **should embed its tuple** (§14) so the reproducible pair is one file with no external dependency; a `Result` in a working DOE may reference its tuple by `@hash` to avoid duplication. Both forms deserialize identically.

A reference that cannot be resolved on load is a **deserialization error**, never a silent null — except `<<SEAM>>` references explicitly marked optional/unbuilt (§2.8).

---

# 4. ReproducibilityTuple Schema

The top-level serialized **input** object. **A run is fully determined by it; no result depends on anything outside it** (`[F1]` Principle 7, MASTER §15, `INTERFACE_SPEC.md` §15). Serializable, versioned, immutable.

```yaml
#kind: ReproducibilityTuple                              # <<FROZEN structure>>
schema_version: "1.0.0"                                  # <<FROZEN>> §2.1 — first field read
project_version: "mpl-sim 0.4.0"                         # framework code version that produced/validated this tuple

topology:                <TopologySpec>                  # §9 — components + connections + junctions + branch structure
component_parameters:    { ComponentId -> <ParamSet> }   # §8 — fixed per-component parameters (η, Cv, channel count, ...)
geometries:              { ComponentId -> <Geometry> }   # §6 — immutable typed geometry value objects
discretizations:         { ComponentId -> <Discretization> }  # §7 — fidelity axis per component
fluid_identities:        { FluidRef -> <FluidIdentity> } # §5 — the fluids present in the run
property_backend_selections: { FluidRef -> <BackendSelection> }  # §5 — backend + version + options per fluid
correlation_selections:  { (ComponentId, role) -> <ModelSelection> }    # §11 — closure per slot
hx_model_selections:     { ComponentId -> <ModelSelection> }            # §11 — heat-exchanger strategy per exchanger
accumulator_law_selections: { ComponentId -> <ModelSelection> }        # §11 — volume↔pressure law per accumulator
calibration:             <CalibrationReport>            # §12 — factors: target, value, mode, seam
scenario:                <Scenario>                     # §10 — the five-part operating point
solver_settings:         <SolverSettings>               # §13 — solver type, tolerances, limits, FD step
metadata:                <TupleMetadata>                # §4.2 — provenance, author, timestamps, free notes
```

### 4.1 How the tuple fully determines a run

Each field closes one degree of freedom; together they leave nothing to hidden state (the §2.5/§2.7 guarantee):

- **`topology` + `component_parameters` + `geometries` + `discretizations`** fix *what physical loop exists and at what fidelity* — the Network and its Components (MASTER §13, §12; "If changing this changes the P&ID/a part, it is Network/Component," `INTERFACE_SPEC.md` §10.4).
- **`fluid_identities` + `property_backend_selections`** fix *which fluid and which property engine* serve every `FluidState` (`[F6]`, §5).
- **`correlation_selections` + `hx_model_selections` + `accumulator_law_selections`** fix *every swappable model* — the closures, the exchanger strategies, the pressure laws. Swapping any of them is a single-field edit here (Rule 4, §2.5).
- **`calibration`** fixes *every named correction*, neutral by default, always present (`[F5]`, §12).
- **`scenario`** fixes *the operating point* — the primary DOE axis (`[F17]`, §10).
- **`solver_settings`** fixes *the numerics* — type, tolerances, FD step (§13).
- **`schema_version` + `project_version` + `metadata`** fix *how to interpret the file and where it came from*.

A `Result` carrying a `tuple_ref` to this object (§14) plus the framework at `project_version` regenerates the converged state to tolerance. *That round-trip is the definition of reproducibility* (§2.7).

### 4.2 TupleMetadata

```yaml
metadata:                                                # <<FROZEN core fields>>
  tuple_id:      <str | @hash>      # stable identity; content-hash recommended (§3.4)
  created:       <timestamp>        # ISO-8601, UTC
  author:        <str>?
  description:   <str>?             # free-text human label
  parent_tuple:  $ref?              # if derived from another tuple (e.g. one DOE point off a base), the base
  tags:          [ <str> ]?         # free classification (e.g. "kokate-validation", "doe-2026-06")
```

- `tuple_id` is the handle a `Result` and a DOE dataset reference. A **content-hash** over the canonical serialization (§3.4) is the recommended `tuple_id`, because it makes identity intrinsic and tamper-evident.
- `parent_tuple` records DOE lineage: a swept point names the base tuple it varied from, so a dataset is reconstructable as "base + the one field each point changed" (§17).

---

# 5. FluidIdentity and PropertyBackend Schema

Serializes the Layer-0/1 fluid selection (`[F6] [F12] [F13]`, MASTER §5/§6, `INTERFACE_SPEC.md` §3, `CORRELATION_CONTRACT.md` §1.2). **Identity names *which fluid*; backend selection names *which engine* serves its properties** — two separate fields, deliberately (the DAG-cycle guard, §2.5).

## 5.1 FluidIdentity — the discriminated union

```yaml
# A mixture-capable value object; a bare string is insufficient. <<FROZEN>>
fluid_identities:
  primary:                                  # FluidRef — an in-tuple key referenced elsewhere
    #kind: PureFluid
    name: "R134a"

  secondary_sink:
    #kind: PureFluid
    name: "Water"
```

The three variants (`INTERFACE_SPEC.md` §3.1):

```yaml
# Pure fluid
{ #kind: PureFluid, name: <str> }                        # e.g. "R134a", "Acetone"

# Mixture (future-ready; v1 may carry none)              <<FROZEN shape>>
{ #kind: Mixture,
  components: [ { fluid: <str>, mole_fraction: <float> } ],   # ordered; fractions sum to 1
  model: <str>? }                                        # mixture model name, when the backend needs one

# Custom fluid — opaque handle into a CustomFluidBackend
{ #kind: CustomFluid, handle: <str> }
```

- **`FluidRef`** (the map key, e.g. `primary`, `secondary_sink`) is an in-tuple alias used by `property_backend_selections`, by `Scenario` fields that carry a fluid (e.g. `CondenserSink.fluid`, §10), and by component port states. It is **not** a property — it is a reference label resolved within the file.
- **Mixtures and custom fluids serialize without changing the schema** of anything that *references* a fluid: a `FluidRef` is a `FluidRef` whether it points at a pure fluid, a mixture, or a custom handle. This is the seam that lets a future `MixtureBackend`/`CustomFluidBackend` be selected by a backend-selection edit alone (§2.8).
- **Identity carries no properties and no capability flags** (`INTERFACE_SPEC.md` §3.1) — capabilities belong to the *backend* selected for it (§5.3).

## 5.2 BackendSelection — engine, version, options

```yaml
property_backend_selections:                             # { FluidRef -> BackendSelection }  <<FROZEN core fields>>
  primary:
    backend:  "CoolProp"                # registered backend name (default = CoolProp, MASTER §6)
    version:  "6.6.0"                   # backend library/implementation version — provenance for archival
    options:  { }                       # backend-specific options (e.g. equation-of-state choice), explicit
  secondary_sink:
    backend:  "CoolProp"
    version:  "6.6.0"
    options:  { }
```

- **Selection is a `(FluidRef -> backend name)` binding** (`[F13]`, `INTERFACE_SPEC.md` §3.4). Replacing CoolProp with REFPROP or a tabulated surrogate is editing `backend` here — config, not code (§2.5).
- **`version` is mandatory for archival.** A property number is only reproducible if the engine version that produced it is named (`CORRELATION_CONTRACT.md` §12). Two CoolProp releases can differ; the file records which.
- **`options` are written explicitly** even when empty (§2.6) — no hidden backend defaults.

## 5.3 Backend capability declaration (informational, on the backend, not the tuple)

Capability flags (`provides(SIGMA_E)`, `provides(DERIVATIVES)`, `valid_range(identity)`, `INTERFACE_SPEC.md` §3.3) are a **runtime property of the resolved backend**, not serialized into the tuple. They are *queried on load*, not stored — storing them would be a hidden derived value (§2.4). A `Result` that consumed a table-only property (`σ_e`, `ε_r`) records that fact through the *closure/validity provenance* (§16), not through a copied capability flag.

## 5.4 Backend-specific serialized references

Some backends reference an external data asset:

```yaml
# TabulatedPropertyBackend — references versioned property-table files (§19)
property_backend_selections:
  primary:
    backend: "Tabulated"
    version: "tables-2026.1"
    options:
      table_set: $ref: "data/property_tables/r134a/@hash"   # content-hash pin for reproducibility
```

- A `TabulatedPropertyBackend` (the only source of `σ_e`/`ε_r`, MASTER §17) **pins its table set by content-hash** so a result remains reproducible only against the exact tables it used. The 29-CSV recovery (MASTER §17, a data task) populates these; until then the reference is declarable but unresolvable (§19).
- **Future backends** — `RefpropBackend`, `EmpiricalCorrelationBackend` (Letsou-Stiel/Latini/Brock-Bird), `MixtureBackend`, `CustomFluidBackend` — add nothing to this schema: each is a `backend` name with its own `version`/`options`, exactly the §2.8 additive pattern.

---

# 6. Geometry Schema

Serializes the **immutable, flat, typed family** of geometry value objects (`[F8]`, MASTER §8, `INTERFACE_SPEC.md` §5). **No base type, no inheritance** — each variant is discriminated by `#kind` and carries only its own fields (the hierarchy-creep guard, §20).

General serialization rules (mirroring `INTERFACE_SPEC.md` §5):

- **Geometry is immutable.** A serialized geometry is a frozen record; varying a dimension writes a new geometry → a new tuple (§2.2). This is the DOE unit for a geometric sweep.
- **Geometry stores no mesh and no operating state** (`[F16] [F17]`). Discretization is serialized separately (§7); gravity/flow/time-varying quantities are Scenario (§10) — never geometry fields.
- **Geometry stores primitives; derived dimensional accessors are not serialized** (`D_h` from primitives is recomputed on load, not stored — §2.4 applied to dimensional algebra). When a single primitive *is* the canonical input (e.g. round-pipe `D` serving as `D_h`), it is stored as the primitive.

## 6.1 PipeGeometry and PipePath (trajectory)

```yaml
#kind: PipeGeometry                                      # <<FROZEN core fields>>
L:         <float>          # flow length [m]
D_h:       <float>          # hydraulic diameter [m]
A:         <float>          # flow area [m²]
roughness: <float>          # absolute wall roughness [m]
trajectory:                 # <PipePath> — replaces a bare Δz
  #kind: StraightSegment    # v1 default — reproduces "single straight run characterized by Δz"
  length:      <float>      # [m]
  delta_z:     <float>      # elevation change over the segment [m]
  inclination: <float>      # angle from horizontal [rad]; 0 = horizontal, ±π/2 = vertical
```

- **The `trajectory` field is typed as `PipePath` from v1**, with `StraightSegment` the only v1 variant. This is the seam (`INTERFACE_SPEC.md` §5.1) that makes richer trajectories additive (§2.8), never a re-typing.
- **Future variants serialize as additional `#kind`s** under `trajectory` (declared, `<<SEAM>>`, unbuilt in v1):

```yaml
trajectory:
  #kind: MultiSegmentPath                                # <<SEAM>>
  segments:
    - { #kind: StraightSegment, length: ..., delta_z: ..., inclination: ... }
    - { #kind: BendSegment,    radius: ..., angle: ... }     # <<SEAM>>
    - { #kind: FittingSegment, fitting_kind: ..., K_L: ... } # <<SEAM>>
```

- **The correlation-facing scalars (`D_h`, `A`, `roughness`, per-cell `dz/dx`, `Σ K_L`) are derived from the geometry+trajectory on load** (`INTERFACE_SPEC.md` §5.1 `PipePath.derived()`), never serialized — §2.4.
- **Collectors and manifolds are NOT a geometry variant** — they are a Network topology of pipe segments joined at Junctions (§9, `INTERFACE_SPEC.md` §5.1). A geometry file describes one passage; multiplicity is the topology's job.

## 6.2 PlateGeometry

```yaml
#kind: PlateGeometry                                     # <<FROZEN core fields>>
N_plates:       <int>
chevron_angle:  <float>      # [rad]
plate_spacing:  <float>      # [m]
port_dims:      [ <float>, <float> ]   # [m, m]
A_per_plate:    <float>      # [m²]
sink_side:      <SinkSideGeometry>?    # secondary-fluid passage description, when modelled
```

No single `D`; correlations consume `chevron_angle`, `plate_spacing`, `A_per_plate`. Used by the plate condenser (§8, §11 of `INTERFACE_SPEC.md`).

## 6.3 MicrochannelGeometry

```yaml
#kind: MicrochannelGeometry                              # <<FROZEN core fields>>
N_channels:    <int>
D_h_channel:   <float>       # [m]
fin_geometry:  <FinGeometry>
A_heated:      <float>       # [m²]
wall_mass:     <float>       # [kg] — exposed for the dynamic wall-capacitance internal state [F15]
wall_material: <MaterialRef> # material handle (for c_p, conductivity of the wall solid)
```

`wall_mass`/`wall_material` are serialized because the frozen dynamic wall-capacitance internal state needs them (`[F15]`, §8 internal states). They are *geometry* (immutable structure), not state.

## 6.4 AccumulatorGeometry (containment only)

```yaml
#kind: AccumulatorGeometry                               # <<FROZEN core fields>>
V_total:     <float>         # [m³] total containment volume
containment: <ContainmentSpec>     # vessel/port geometry; law-agnostic
thermal:     <ThermalSpec>?        # heater/wall data, read ONLY by laws that need it (e.g. HCA)
```

- **Containment only.** `AccumulatorGeometry` serializes **no** `V_gas_charge`, **no** spring constant, **no** bellows area, **no** polytropic index (the geometry-carrying-the-law anti-pattern, §20; `INTERFACE_SPEC.md` §5.4). Those are **law parameters** and serialize with the accumulator-law selection (§11.3), never here.
- Swapping PCA→HCA→bellows→spring→gas-charged changes the *law selection* (§11.3) and at most the optional `thermal`/`containment` sub-specs the law reads — never the geometry `#kind` (§2.5).

---

# 7. Discretization Schema

Serializes the **fidelity axis** (`[F16]`, MASTER §9, `INTERFACE_SPEC.md` §6) — a small declared object per component, owned by the component's numeric configuration, **derived-from but never stored-in geometry** (§6 rule).

```yaml
discretizations:                                         # { ComponentId -> Discretization }  <<FROZEN enumeration>>
  pipe_1:
    #kind: Lumped                        # 0D: one control volume — v1 default
  evaporator_1:
    #kind: Segmented                     # 1D finite-volume
    N: 20                                # resolution: number of control volumes
  condenser_1:
    #kind: MovingBoundary                # <<SEAM>>: zones appear/disappear, Phase 6
    max_zones: 3                         # an upper bound for allocation; live count is per-step (below)
```

- **Resolution is represented by the variant's own field:** `Lumped` carries none (one cell); `Segmented` carries `N`; `MovingBoundary` carries `max_zones` (an allocation hint, not a fixed count).
- **State count is a property of the discretization, derived against geometry on load** (`INTERFACE_SPEC.md` §6) — it is **not serialized in the tuple**. The serializer writes the *mode and resolution*; the solver computes the resulting unknown count (§2.4 applied to derived counts).
- **MovingBoundary state count is per-step, not frozen at assembly** (`[F16]`). A `MovingBoundary` *tuple* serializes only `max_zones`; a `MovingBoundary` *result* (§14) serializes the converged states with whatever zone count the converged solution had, recorded as a variable-length internal-state list (§14.2). The dynamic, per-step zone evolution is not a tuple concern.
- **The same geometry serves a lumped and a segmented run** — switching `#kind: Lumped` ↔ `#kind: Segmented` here is a fidelity edit that touches no geometry field (the mesh-in-geometry anti-pattern guard, §20).

---

# 8. Component Schema

Serializes one physical element (MASTER §12, `INTERFACE_SPEC.md` §11). A component is **not** a monolithic blob: its geometry, discretization, and model selections are serialized in their own tuple maps (§6, §7, §11) and **referenced by `ComponentId`**, so a DOE can vary one facet without rewriting the component. The component's own record carries identity, type, ports, parameters, and slot declarations.

```yaml
# Within topology.components (§9):                       # <<FROZEN core fields>>
- id:    "evaporator_1"                  # ComponentId — the key all tuple maps reference
  type:  "Evaporator"                    # one of the closed component vocabulary (below)
  ports:
    - { id: "evaporator_1.in",  role: INLET }
    - { id: "evaporator_1.out", role: OUTLET }
  geometry_ref:        "evaporator_1"    # -> geometries[evaporator_1]               (§6)
  discretization_ref:  "evaporator_1"    # -> discretizations[evaporator_1]          (§7)
  parameters_ref:      "evaporator_1"    # -> component_parameters[evaporator_1]     (below)
  correlation_slots:                     # roles I declare; bound in correlation_selections (§11)
    - { role: HTC,          slot: "boiling_htc" }
    - { role: TWO_PHASE_DP, slot: "tp_friction" }
  hx_model_slot:       "hx"              # present only for heat-exchanger components (§11)
  accumulator_law_slot: null             # present only for the Accumulator (§11.3)
  calibration_slots:                     # which seams accept a factor; values in calibration (§12)
    - { target: HTC,             slot: "boiling_htc" }
    - { target: FRICTION_GRADIENT, slot: "tp_friction" }
  scenario_bindings:                     # which Scenario inputs I accept (declarations, §10.5)
    - { accepts: EvaporatorHeatLoad }
  internal_state_names: [ "wall_T", "fluid_inventory" ]   # named even when frozen [F15]
```

- **`ports`** serialize connectivity-only records (id + role annotation) — **never values** (`[F10]`, the state-on-port anti-pattern, §20). The `(P, h, mdot)` at a port live in the `Result`'s converged-port-values map (§14), keyed by `PortId`, never on the port record here.
- **`*_ref` fields point into the tuple's sibling maps**, keeping the swappable facets (geometry, discretization, parameters, model selections, calibration) editable independently — the §2.5 explicit-selection principle realized as referenced sub-objects.
- **`internal_state_names` are serialized even when frozen** (`[F15]`): the names are part of the component's declared structure, so a tuple records *which states exist* and a result records *their converged values* (§14.2) under those names.
- **`ParamSet`** (`component_parameters[id]`) holds the fixed, non-swept scalars of the component (e.g. pump efficiency η, valve `Cv`, channel count when not in geometry). These are *component* facts ("changing this changes one part without re-wiring," `INTERFACE_SPEC.md` §10.4), distinct from Scenario.

The closed component vocabulary (`type`), per `INTERFACE_SPEC.md` §11.4 — each row names what is serialized:

| `type` | Geometry | Internal states (named) | Correlation slots | HX model slot | Accum. law slot | Scenario bindings |
|---|---|---|---|---|---|---|
| **Pump** | minimal (perf-map ref) | shaft speed / loop inertia `I` | pump map | — | — | `PumpSpeedCommand` / `PumpFlowTarget` |
| **Pipe** | `PipeGeometry` | per-seg mass/momentum, wall T if heated | single-phase ΔP; two-phase ΔP; void | — | — | optional wall heat (BC) |
| **Evaporator** | `MicrochannelGeometry` | flow regime; wall capacitance/seg; inventory | boiling HTC; two-phase ΔP | **yes** | — | `EvaporatorHeatLoad` |
| **Condenser** | `PlateGeometry` | effective areas/zone; moving-boundary positions | condensation HTC; ΔP | **yes** | — | `CondenserSink` |
| **Accumulator** | `AccumulatorGeometry` | `V_g` (P derived) | — | — | **yes** (one law) | `AccumulatorPressureSetpoint` |
| **Valve** | minimal (`Cv`) | position | loss coefficient `K_L` | — | — | `ValveOpeningCommand` |
| **Junction** | minimal | none | none | — | — | — |
| **Reservoir** | containment volume | inventory; liquid level | none | — | — | — |

- **`Junction`** serializes the n-in/m-out node; `Splitter`/`Mixer` are configurations of it, optionally written as thin aliases that deserialize to a `Junction` (`INTERFACE_SPEC.md` §11.4). The canonical serialized `type` is `Junction`.
- **`Reservoir`** serializes inventory/level state but **no pressure-reference** field — the Accumulator sets the reference (§9), the Network is the single inventory accountant.

---

# 9. Network Topology Schema

Serializes the **topology** — what components exist, how their ports connect, the branch structure, the pressure reference, and inventory accounting (`[F7]`, MASTER §13, `INTERFACE_SPEC.md` §12). The Network states *what must hold*; the schema records that statement, never the solver's method of satisfying it.

```yaml
topology:                                                # <<FROZEN structure>>
  components:        [ <Component> ]          # §8 — the component records
  connections:                                # non-directional port pairings (§4.1 INTERFACE_SPEC)
    - { a: "pump_1.out", b: "evaporator_1.in" }
    - { a: "evaporator_1.out", b: "condenser_1.in" }
    - ...
  junctions:                                  # n-in/m-out conservation nodes
    - { id: "split_1", trunk: "...", branches: [ "...", "..." ] }
  branch_groups:                              # splitter↔mixer pairings; equal-ΔP branch sets
    - { splitter: "split_1", mixer: "mix_1", branches: [ "branch_a", "branch_b" ] }
  pressure_reference: "accumulator_1"         # EXACTLY ONE — the reference component (the node only)
  inventory:                                  # the single global mass-inventory account
    total_charge: <float>?                    # [kg] — first-class Network quantity from v1
    accountant:   "Network"                   # the single accountant; never a component
  topology_validation: <TopologyValidationRecord>?   # §9.1 — the cached verdict, if persisted
```

- **`connections` are non-directional** (`[F10]`): a pair `{a, b}` asserts equal pressure, equal enthalpy (for the passing fluid), and a mass-flow balance at the node — direction is not serialized (role annotations on ports are hints only, §8).
- **`pressure_reference` names exactly one component** (`[F7]`): the *which node* fact the Network owns. The pressure *law and value* live with the Accumulator's law selection (§11.3) and Scenario `P_set` (§10) — the three-way split serialized across three places, never duplicated. A second reference is a validation failure (§9.1).
- **`inventory` is first-class from v1** (MASTER §13): the single accountant is the Network; no component serializes a competing total.
- **Collectors/manifolds are realized here** as pipe-segment components joined at `junctions` (§6.1), not as a geometry field.

## 9.1 Topology validation record

Topology validation is computed (`Network.validate()`, `INTERFACE_SPEC.md` §12); its **verdict may be persisted** for archival traceability, but is always **re-derivable** from the topology (so it is not primary state, §2.4):

```yaml
topology_validation:                                     # <<FROZEN core fields>>
  valid: <bool>
  checks:
    - { check: "no_dangling_ports",        passed: <bool>, detail: <str>? }
    - { check: "exactly_one_reference",    passed: <bool>, detail: <str>? }
    - { check: "well_formed_branch_sets",  passed: <bool>, detail: <str>? }
    - { check: "no_double_counted_inventory", passed: <bool>, detail: <str>? }
```

- This record represents the `TopologyVerdict` (`INTERFACE_SPEC.md` §12): no dangling ports, exactly one pressure reference, well-formed splitter↔mixer sets, no double-counted inventory.
- It is **informational/cached**: a reader trusts the live `validate()` on load over a stale persisted verdict; persisting it serves archival auditing, not runtime decisions.

---

# 10. Scenario Schema

Serializes the **five-part Scenario** — the operating point and the **primary DOE axis** (`[F17]`, MASTER §15, `INTERFACE_SPEC.md` §10). All five parts are immutable; sweeping any field without rebuilding the loop is the membership test for a Scenario input.

```yaml
scenario:                                                # <<FROZEN structure>>
  boundary_conditions: [ <BoundaryCondition> ]
  commands:            [ <Command> ]
  disturbances:        [ <Disturbance> ]      # <<SEAM>>: time-varying; v1 empty/constant
  environment:         <Environment>
  operating_point:     <OperatingPoint>
```

## 10.1 Boundary conditions

```yaml
boundary_conditions:
  - { #kind: EvaporatorHeatLoad, target: "evaporator_1", Q: 1500.0 }        # [W]  (or wall_flux)
  - { #kind: CondenserSink, target: "condenser_1",
      T_in: 293.15, mdot: 0.25, fluid: "secondary_sink" }                   # sink inlet T [K], flow [kg/s], FluidRef
  - { #kind: AccumulatorPressureSetpoint, target: "accumulator_1", P_set: 8.0e5 }   # the reference VALUE [Pa]
  - { #kind: FixedInletState, target: "pump_1.in", P: 8.0e5, h: 250.0e3 }?  # optional fixed port state
```

- `EvaporatorHeatLoad` carries `Q` **or** `wall_flux` (one of, never both silently — §2.6).
- `CondenserSink.fluid` is a **`FluidRef`** (§5) into `fluid_identities`, not an inline fluid — the secondary fluid is a first-class identity with its own backend selection.
- `AccumulatorPressureSetpoint.P_set` is the reference **value**; the **law** is Component (§11.3), the **node** is Network (§9) — the three-way split.

## 10.2 Commands

```yaml
commands:
  - { #kind: PumpSpeedCommand,    target: "pump_1",  omega: 314.0 }     # [rad/s]
  # or: { #kind: PumpFlowTarget,  target: "pump_1",  mdot: 0.05 }       # [kg/s]
  - { #kind: ValveOpeningCommand, target: "valve_1", fraction: 0.75 }   # [0..1]
```

## 10.3 Disturbances (`<<SEAM>>`)

```yaml
disturbances: [ ]            # v1: empty or constant. Dynamics activates; future MPC consumes.
# Future shape (declared, unbuilt):
#   - { #kind: TimeVarying, signal: <Signal>, applies_to: <BoundaryCondition | Command> }
```

The field is **present in the schema from v1** (§2.8) so dynamics populates it without a re-typing. A v1 serializer writes `[]`.

## 10.4 Environment

```yaml
environment:                                             # <<FROZEN core fields>>
  gravity:   [ 0.0, 0.0, -9.80665 ]      # Vector3 [m/s²]; default 1 g terrestrial, WRITTEN EXPLICITLY (§2.6)
  T_ambient: 298.15?                     # [K]
  ambient_loss: { UA_amb: <float> }?     # heat-loss condition for exposed components
```

- **Gravity is Scenario, not Geometry** (`[F17]`): a zero-g / variable-g study is a `gravity` edit here, not a geometry rebuild. The default 1 g is **written explicitly**, not left implicit (§2.6) — so a spacecraft sweep is visibly a sweep.

## 10.5 Operating point and binding

```yaml
operating_point:                                         # the DOE coordinate label
  label:       "design-load-nominal-charge"?
  coordinates: { "heat_load": 1500.0, "subcooling": 5.0 }   # named coordinates of this DOE point
```

- **`OperatingPoint` is the DOE coordinate label** — the human/sweep-axis name for *where in the design space* this run sits (`INTERFACE_SPEC.md` §10.2). It is metadata-for-the-sweep, distinct from the boundary conditions that physically set the point.
- **Binding** (`bind(scenario, network)`, `INTERFACE_SPEC.md` §10.5) resolves each part's `target` to a component/port on load. A target naming a non-existent component is a **deserialization/binding error**, not a silent no-op. The binding itself is *not* serialized — it is derived from the Scenario + topology on load (§2.4).

---

# 11. Model Selection Schema

Serializes **every swappable model as a named binding** (Rule 4, §2.5). Four selection families share one `ModelSelection` shape, differing only in which tuple map they live in and which registry resolves them.

```yaml
# The shared shape:                                      # <<FROZEN core fields>>
<ModelSelection>:
  name:    <str>            # canonical registered name (never an alias — CORRELATION_CONTRACT §8.4)
  version: <str>            # model version captured for archival/provenance (CORRELATION_CONTRACT §8.3)
  role:    <Role>?          # the role/slot this fills (for correlations); informational, validated on load
  options: { }?             # model-specific options, written explicitly; absent ⇒ none
  source:  <SourceRef>?     # citation/DOI/provenance, when the catalogue records it (§16, §18)
```

The four families:

```yaml
# 1. Correlation per slot — resolved by CorrelationRegistry, keyed (ComponentId, role/slot)
correlation_selections:
  [ "evaporator_1", "boiling_htc" ]: { name: "Shah",            version: "1982-rev2", role: HTC }
  [ "evaporator_1", "tp_friction" ]: { name: "Kim-Mudawar2013", version: "1.0", role: TWO_PHASE_DP }
  [ "pipe_1",       "sp_friction" ]: { name: "Churchill",       version: "1.0", role: SINGLE_PHASE_DP }

# 2. Heat-exchanger model per exchanger — resolved by HeatExchangerModelRegistry (separate)
hx_model_selections:
  "condenser_1":  { name: "EpsilonNTU",     version: "1.0" }    # kind ∈ EPSILON_NTU|LMTD|SEGMENTED_MARCH|MOVING_BOUNDARY
  "evaporator_1": { name: "SegmentedMarch", version: "1.0" }

# 3. Accumulator pressure law per accumulator — role VOLUME_PRESSURE_LAW, lives in the CorrelationRegistry
#    but is bound via its own tuple field; law parameters travel HERE, never in geometry (§6.4)
accumulator_law_selections:
  "accumulator_1":
    name: "PCA"
    version: "1.0"
    role: VOLUME_PRESSURE_LAW
    options:                              # the law parameters — NOT geometry (§6.4, §20)
      charge_volume:    1.2e-4            # [m³]
      polytropic_index: 1.2

# 4. Property backend per fluid — resolved by PropertyBackendRegistry (separate); serialized in §5.2
#    (property_backend_selections is its own tuple field, shown in §5)
```

- **`name` is always canonical, never an alias** (`CORRELATION_CONTRACT.md` §8.4) — so reproducibility is unambiguous. A deprecated name still resolves and is recorded with its deprecation flag in the Result (`CORRELATION_CONTRACT.md` §8.5).
- **`version` is mandatory** for archival: a Result names not just *Shah* but *which Shah at which version* (`CORRELATION_CONTRACT.md` §8.3, §12).
- **The four registries are distinct** (`CORRELATION_CONTRACT.md` §1.3, §8.2): `PropertyBackendRegistry`, `CorrelationRegistry`, `HeatExchangerModelRegistry`, and — within the correlation registry but bound by its own tuple field — the `VOLUME_PRESSURE_LAW` role. The serialized *fields* keep them separate so a property engine is never miscategorised as a slot correlation, and a heat-exchanger strategy is never miscategorised as a correlation (the §20 anti-patterns).
- **`role` on a correlation selection is validated on load**: a name bound to the wrong role is a binding-time error (`CORRELATION_CONTRACT.md` §8.2), not a silent mismatch.

---

# 12. Calibration Schema

Serializes the calibration report — **every correction named, neutral by default, always present** (`[F5]`, MASTER §11, `INTERFACE_SPEC.md` §9, `CORRELATION_CONTRACT.md` §7). Calibration appears **twice in the same shape**: as an *input* in the tuple (§4) and as a *report* in every Result (§14). *A factor that is not reported cannot exist.*

```yaml
calibration:                                             # <CalibrationReport>  <<FROZEN>>
  mode: NONE                               # NONE | TARGET — the run's overall mode
  factors:                                 # every NON-NEUTRAL factor; empty list under pure NONE
    - target: HTC                          # FRICTION_GRADIENT | HTC | UA  (the only legal targets)
      value:  1.15                         # 1.0 == neutral
      mode:   TARGET
      scope:  SLOT                         # SLOT | COMPONENT | GLOBAL  (resolution order)
      seam:                                # the documented point of application
        component: "evaporator_1"
        slot:      "boiling_htc"
        scales:    "Shah HTC output"       # human-readable seam description
```

- **`mode`** is `NONE` (pure predictive, all factors neutral, the honest baseline) or `TARGET` (factors chosen to meet an experimental target). A `TARGET` run's Result is flagged `CALIBRATED` and never compared as-equal to a `PREDICTIVE` run (§14, `CORRELATION_CONTRACT.md` §7.2).
- **`target` is one of `FRICTION_GRADIENT | HTC | UA`** (`[F14]`). A factor targeting gravity, acceleration, a balance, void fraction, flow regime, or a pressure law is **malformed** (`CORRELATION_CONTRACT.md` §7.3, §13). `R*` scales the *friction gradient only*.
- **`scope`** records the resolution level (slot → component → global, falling back to neutral, `INTERFACE_SPEC.md` §9.3). The *resolved, applied* factor is what serializes — no reader needs the resolution algorithm to know what value was used (§2.6).
- **`value` and `seam` are mandatory per factor** — the seam names *which slot, on which component, scaling which output* (`CORRELATION_CONTRACT.md` §7.5). This is what lets a reader reconstruct, years later, exactly which closure outputs were adjusted and by how much.
- **There is no `DATASET_FIT` mode.** Least-squares identification is Phase-5 surrogate territory and routes its results back as ordinary explicit `TARGET` factors at this same seam (`CORRELATION_CONTRACT.md` §7.2) — never a parallel serialized mechanism.
- **The conservation firewall is preserved by construction** (§2.4, `CORRELATION_CONTRACT.md` §7.4): because the Result's invariants (§15) are computed from *un-calibrated* conservation, a serialized calibration can never make a serialized imbalance falsely pass.

---

# 13. Solver Settings Schema

Serializes the numerics selection — *how* the system is driven to satisfaction, with **no physics** (MASTER §14, `INTERFACE_SPEC.md` §13). "If changing this changes only the numerics, not the physics, it is Solver settings" (`INTERFACE_SPEC.md` §10.4).

```yaml
solver_settings:                                         # <<FROZEN core fields>>
  solver_type: "SimultaneousNewton"        # "FixedPointPressure" | "SimultaneousNewton" (steady strategies)
  tolerances:
    residual_norm: 1.0e-8                  # convergence threshold on the assembled residual
    step_norm:     1.0e-10?                # optional secondary criterion
  max_iterations: 100
  finite_difference:                       # the FD-primary Jacobian/sensitivity settings ([F18])
    step:          1.0e-6                  # structured-FD perturbation
    scheme:        "forward"               # "forward" | "central"
  convergence_criteria:
    require_invariants_within: { energy: 1.0e-3, mass: 1.0e-6 }?   # optional gating on invariants
  dynamic:                                 # <<SEAM>>: dynamic-solver settings, Phase 6
    integrator:    null
    time_step:     null
    event_detection: null
```

- **`solver_type` selects between the two frozen steady strategies** (fixed-point pressure iteration; simultaneous Newton–Raphson) — both behind the identical component contract (`INTERFACE_SPEC.md` §13.1). Swapping is a settings edit (§2.5).
- **`finite_difference` settings are first-class** because structured FD is the primary Jacobian/sensitivity mechanism (`[F18]`). Analytic/AD overrides are *runtime capabilities of a component/backend*, not serialized settings — **AD is not promised and is not a serialized field** (anti-pattern §20).
- **The `dynamic` block is a declared `<<SEAM>>`** (§2.8): present in the schema, null/empty in v1, populated when the dynamic solver lands. Its presence now means Phase 6 *fills a field* rather than re-typing the settings object.
- **Solver settings carry no model choice and no physics** — a solver name is a numerics fact; a correlation name is a tuple model selection (§11). Conflating them is forbidden (§2.5, `INTERFACE_SPEC.md` §13: "must never access any physics").

---

# 14. Result Schema

Serializes the atomic **output** unit, paired with its tuple, under the single-source-of-truth rule (MASTER §15, `INTERFACE_SPEC.md` §14). **Stored = irreducible only; reported invariants/reports = always present; derived profiles = never stored** (§2.3, §2.4).

```yaml
#kind: Result                                            # <<FROZEN>>
schema_version: "1.0.0"                                  # <<FROZEN>>
project_version: "mpl-sim 0.4.0"

# --- 1. tuple reference (the reproducibility anchor) ---
tuple_ref:                                               # §3.4 — by value or content-hash
  tuple_id: "@hash:9f2c..."                # content-hash of the ReproducibilityTuple (§4)
  embed:    $ref?                          # optional inline copy of the full tuple, for self-contained archival

# --- 2. STORED, irreducible converged state (the ONLY stored numbers) ---
converged_port_values:                     # { PortId -> (P, h, mdot) }   [Pa, J/kg, kg/s]
  "pump_1.out":      { P: 8.10e5, h: 251.3e3, mdot: 0.050 }
  "evaporator_1.out": { P: 7.95e5, h: 410.0e3, mdot: 0.050 }
  ...
converged_internal_states:                 # { (ComponentId, state_name) -> float[] }
  [ "evaporator_1", "wall_T" ]:          [ 305.1, 306.4, ... ]    # per-segment; length = discretization
  [ "accumulator_1", "V_g" ]:            [ 1.05e-4 ]              # V_g stored; P is DERIVED, never stored
  ...

# --- 3. REPORTED, first-class, ALWAYS present ---
validation_invariants: <ValidationInvariants>     # §15 — energy/mass imbalance, pressure closure, bound checks
calibration_report:    <CalibrationReport>        # §12 — must be present even under NONE (empty factors list)
validity_warnings:     [ <ValidityVerdict> ]      # §16 — every non-IN_ENVELOPE closure/HX call
closure_metadata:      [ <ClosureMetadata> ]      # §16 — name/version/source of every model that contributed
convergence_metadata:  <ConvergenceMetadata>      # §14.3
predictive_or_calibrated: PREDICTIVE              # PREDICTIVE | CALIBRATED — derived from CalibrationMode

# --- 4. DERIVED post-processing cache (OPTIONAL, explicitly marked, never canonical) ---
cached_profiles: <CachedProfiles>?                # §14.4 — regenerable; discardable; not stored state
result_metadata: <ResultMetadata>                 # §14.5
```

## 14.1 Stored irreducible state

- **`converged_port_values`** holds `(P, h, mdot)` per `PortId` — keyed by port, but the values are the SystemState unknowns, not stored "on" any port (`[F3] [F10]`). These three numbers per node + the internal states are *the entire stored numeric content* of a result.
- **Derived profiles (`T`, `x`, `ρ`, …) are NOT here** (§2.4). They are recomputed on load from `(P, h)` + the tuple's fluid identity through `FluidState`.

## 14.2 Converged internal states

- **`converged_internal_states`** holds each component's named internal states as **vectors** (length = the discretization's state count, §7): per-segment wall T, per-cell inventory, the accumulator `V_g`, condenser moving-boundary positions.
- **`V_g` is stored; `P_sys` is derived** from the accumulator law (`[F15]`, `CORRELATION_CONTRACT.md` §9.4) — a result never stores `P_sys` as an accumulator field.
- **MovingBoundary results store the converged variable-count states** (§7): the list length reflects the converged zone count, recorded under the named state, with the live count implicit in the vector length.

## 14.3 Convergence metadata

```yaml
convergence_metadata:                                    # <<FROZEN core fields>>
  iterations:          <int>
  final_residual_norm: <float>
  converged:           <bool>
  strategy:            <str>            # the solver_type actually used (§13)
```

A non-converged result (`converged: false`) is still a valid serialized record — it carries its (non-converged) state and its invariants honestly, so a DOE can record and analyze failed points (§17), never hide them.

## 14.4 The post-processing cache (the one sanctioned derived store)

```yaml
cached_profiles:                                         # OPTIONAL — §2.4 exception, explicitly marked
  marked_as: "post_processing_cache"     # the mandatory marker — never read back as canonical
  regenerable_from: "converged_port_values"   # the provenance: recompute from (P,h) to discard/refresh
  P_profile:   [ ... ]                   # convenience copies for plotting/analysis ONLY
  T_profile:   [ ... ]
  x_profile:   [ ... ]
```

- This is the **single exception** to §2.4, and it is hedged: it is **explicitly marked**, **physically separated** from stored state, **never read back as canonical**, and **regenerable** by discarding it and recomputing from `(P, h)`. A reader treats a discrepancy between `cached_profiles` and the recomputed profile as *the cache is stale*, never as *the state is wrong*.
- Omitting `cached_profiles` entirely is the **default and preferred** form (§2.3). It exists only to make plotting a large archived dataset cheap without re-running property queries — a convenience, never a source of truth.

## 14.5 Result metadata

```yaml
result_metadata:                                         # <<FROZEN core fields>>
  result_id:  <str | @hash>
  produced:   <timestamp>
  duration_s: <float>?           # wall-clock solve time (informational)
  tags:       [ <str> ]?
```

A `Result` **without** `validation_invariants`, `calibration_report`, `validity_warnings`, `convergence_metadata`, and `tuple_ref` is **malformed** (§2.7, `INTERFACE_SPEC.md` §14, `CORRELATION_CONTRACT.md` §12.2).

---

# 15. Validation Invariants Schema

Serializes the first-class validation outputs — **computed from un-calibrated conservation** (MASTER §14, `INTERFACE_SPEC.md` §13.4). *A result without a residual is not a result.*

```yaml
validation_invariants:                                   # <<FROZEN core fields>>
  energy_imbalance:           <float>      # [W]  global energy balance residual
  mass_imbalance:             <float>      # [kg/s]  Σṁ at nodes / global continuity residual
  pressure_closure_residual:  <float>      # [Pa]  Σ ΔP around closed loops (loop closure, MASTER §13)
  bound_checks:                            # physical-validity checks
    - { quantity: "quality_x", bound: "0 <= x <= 1", passed: <bool>, worst_value: <float>?, location: <PortId>? }
    - { quantity: "T_subcritical", bound: "T < T_crit", passed: <bool>, worst_value: <float>?, location: <PortId>? }
```

- **Energy imbalance, mass imbalance, pressure-closure residual** are the three global conservation residuals; all three are mandatory.
- **`bound_checks`** are the physical-validity checks (`0 ≤ x ≤ 1`, `T < T_crit`), each recording pass/fail and (when failed) the worst value and where it occurred.
- **All computed from un-calibrated conservation** (§2.4, `CORRELATION_CONTRACT.md` §7.4): the conservation firewall guarantees a wrong calibration shows as a worse data match, never as a falsely-passing balance. A serialized calibration (§12) and a serialized invariant are independent records by construction.

---

# 16. Closure Metadata and Validity Warning Schema

Serializes the per-closure provenance and validity outputs (`CORRELATION_CONTRACT.md` §5.5, §6, §12). This is the schema that makes a result interpretable *at the level of every constitutive number*: a reader can name **which closure, at which version, from which source, within or outside which envelope** produced each value.

## 16.1 ClosureMetadata

```yaml
closure_metadata:                                        # [ ClosureMetadata ]  <<FROZEN core fields>>
  - name:    "Shah"                      # canonical registered name (never an alias)
    version: "1982-rev2"
    role:    HTC
    seam:    { component: "evaporator_1", slot: "boiling_htc" }
    source:                              # SourceRef — citation/DOI/dataset (§18)
      citation: "Shah, M.M. (1982)"
      doi:      "10.xxxx/xxxxx"?
    # ML/surrogate closures additionally carry (CORRELATION_CONTRACT §10.4):
    training_dataset:  $ref?             # content-hash/citation of the training data
    model_architecture: <str>?           # architecture+version to reconstruct the artefact
    envelope_provenance: <str>?          # how the training domain was bounded
```

- **Every model that contributed a number is recorded** — correlations, the heat-exchanger model, the accumulator law. The set of `closure_metadata` entries plus the tuple's model selections (§11) is the complete provenance.
- **ML/surrogate closures are inadmissible without `training_dataset`** (`CORRELATION_CONTRACT.md` §10.4): a surrogate result that omits its training-data reference is non-reproducible and therefore malformed.

## 16.2 ValidityWarning (the per-call verdict)

```yaml
validity_warnings:                                       # [ ValidityVerdict ]  <<FROZEN>>
  - status:   EXTRAPOLATED               # IN_ENVELOPE | EXTRAPOLATED | OUT_OF_RANGE
    closure:  { name: "Shah", version: "1982-rev2", seam: { component: "evaporator_1", slot: "boiling_htc" } }
    envelope: $ref                       # reference to the ValidityEnvelope checked against (§16.3)
    violated:                            # which specific bounds were exceeded (empty when IN_ENVELOPE)
      - { quantity: QUALITY_X, min: 0.0, max: 0.8, actual: 0.92, units: "-" }
    detail:   "quality above fitted range"?
```

- **Only non-`IN_ENVELOPE` verdicts are persisted** into `validity_warnings` (`CORRELATION_CONTRACT.md` §5.4, §6.4): every extrapolation or out-of-range call is surfaced; in-envelope calls need no warning. *A warning that does not reach the Result does not exist.*
- **`status` is the three-state contract** (`CORRELATION_CONTRACT.md` §6.4): `EXTRAPOLATED` = soft failure (honest extrapolated value, never clamped, run continues); `OUT_OF_RANGE` = hard failure (`NaN`, the contaminated number propagates honestly into the invariants, never masked).
- **`violated` names the specific bounds** so a reader sees *which* dimension was exceeded, not merely that something was.

## 16.3 ValidityEnvelope (the static declaration, referenced not duplicated)

A correlation's envelope is a **static property of the registered model**, not per-run data. It is serialized **once** (in a catalogue/registry-export artifact or the validation-case file, §18) and **referenced by `$ref`** from a `validity_warnings` entry (§16.2) — never duplicated into every result (§2.3).

```yaml
# Serialized in a catalogue/registry export, referenced from results:   <<FROZEN>>
validity_envelope:
  closure: { name: "Shah", version: "1982-rev2" }
  fluid_families:
    - { #kind: NamedFluids, names: [ "R134a", "R1234yf" ] }
  bounds:
    - { quantity: REYNOLDS,   min: 3000.0,  max: 1.0e5, units: "-" }
    - { quantity: QUALITY_X,  min: 0.0,     max: 0.8,   units: "-" }
    - { quantity: BOND,       min: 0.1,     max: 100.0, units: "-" }
  regime_restriction: [ ANNULAR, SLUG ]?
  source: { citation: "Shah, M.M. (1982)", doi: "..."? }
  notes: "Bond-number bound governs microchannel applicability"?
```

- This is the **validity-envelope declaration format** of `CORRELATION_CONTRACT.md` §6.2, serialized. `BoundedQuantity` is the frozen-core/extensible-by-name enumeration there. An **absent bound means unbounded/unknown** (§2.6) — never invented.
- A result names the envelope by reference; the envelope's full declaration lives once, with the catalogue, citable to its source — the longevity guarantee (`CORRELATION_CONTRACT.md` §6.2).

---

# 17. DOE and Surrogate Dataset Schema

Serializes a **collection of runs** — many tuples and their results over a *fixed network* and *varied scenarios* — the Phase-5 surrogate-generation substrate (MASTER §15, `INTERFACE_SPEC.md` §10.3, §14). This is the schema that makes "sweep thousands of operating points against a fixed loop, every result attributable to an exact tuple" a serialized reality.

```yaml
#kind: DOEDataset                                        # <<SEAM>>: Phase 5; shape fixed now
schema_version: "1.0.0"
dataset_id:        "@hash:..." | <str>
description:       <str>?

fixed_network:     $ref                   # the ONE network/spec file held constant (§3, §8, §9)
fixed_fluids:      { FluidRef -> $ref }?   # fluids+backends held constant, if not swept

varied_axes:                              # which Scenario fields this dataset sweeps (the DOE coordinates)
  - { axis: "boundary_conditions[EvaporatorHeatLoad].Q", range: [500.0, 2000.0], samples: 16 }
  - { axis: "commands[PumpSpeedCommand].omega",          range: [200.0, 400.0],  samples: 8 }

sampling:
  method: "grid"                          # "grid" | "latin_hypercube" | "sobol" | "explicit"
  seed:   <int>?                          # for reproducible stochastic sampling

points:                                   # the sampled runs
  - point_id:    "p0001"
    tuple_ref:   $ref                      # the exact tuple for this point (base + varied fields, §4.2 parent_tuple)
    result_ref:  $ref                      # the result, if the run completed
    coordinates: { "Q": 500.0, "omega": 200.0 }   # this point's location on the varied axes
    status:      CONVERGED                 # CONVERGED | FAILED | OUT_OF_ENVELOPE | NOT_RUN
    validity_flag: IN_ENVELOPE             # rolled up from the result's validity_warnings
  - point_id:    "p0002"
    tuple_ref:   $ref
    result_ref:  null
    coordinates: { "Q": 600.0, "omega": 200.0 }
    status:      FAILED                     # non-converged points are RECORDED, never hidden (§14.3)
    failure:     { reason: "non_convergence", residual_norm: 3.2e-2 }

surrogate_training: <SurrogateTrainingMetadata>?   # §17.1 — when this dataset trains a surrogate
```

- **`fixed_network` is referenced once**; the dataset's bulk is the `points` list of (tuple_ref, result_ref) pairs. Because a tuple records its `parent_tuple` (§4.2), each point is reconstructable as "the base tuple + the fields this point varied" — a dataset need not duplicate the full network in every point.
- **`varied_axes`** name the swept Scenario fields — exactly the `(Scenario → Result)` training-pair inputs (`INTERFACE_SPEC.md` §10.3). The fixed network/components are *not* axes; only Scenario is the primary DOE axis (`[F17]`).
- **Failed runs are first-class** (`status: FAILED`, §14.3): a DOE records non-convergence and out-of-envelope points with their failure reason, never silently drops them — a surrogate must learn the feasible region's boundary, which requires the failures.
- **`validity_flag` rolls up** each point's worst validity status (§16.2), so a surrogate-training step can filter on in-envelope points without opening every result.

## 17.1 Surrogate training metadata

```yaml
surrogate_training:                                      # <<SEAM>>: how this dataset feeds a surrogate
  input_vector:   [ <axis_name> ]         # the Scenario-derived feature columns (CORRELATION_CONTRACT §4.2/§10)
  output_vector:  [ <result_quantity> ]   # the Result-derived target columns (invariants + outputs, §14)
  filter:         { status: CONVERGED, validity_flag: IN_ENVELOPE }   # which points are admissible for training
  envelope:       <ValidityEnvelope>?     # the surrogate's training-domain envelope (= its admissible region)
  notes:          <str>?
```

- This makes the **`(Scenario in tuple) → (invariants + outputs in Result)` mapping** (`INTERFACE_SPEC.md` §14, §15) an explicit serialized training pair: `input_vector` from the swept Scenario axes, `output_vector` from the Result quantities.
- **The surrogate's envelope is its training domain** (`CORRELATION_CONTRACT.md` §10.2): a surrogate trained on this dataset declares (§16.3) an envelope no wider than the dataset's sampled region — and is then admissible as an ordinary closure (§11) under the identical contract. This is the seam from §2.8 made concrete: a learned closure enters the catalogue with no new mechanism.

---

# 18. Validation Case Schema

Serializes a **literature or experimental validation case** — the measured reference a run is compared against (MASTER §17 harvest, `TEST_PLAN_V1.md` is the consumer). This is the schema for the Kokate / Li et al. / Fujii datasets named in the migration plan.

```yaml
#kind: ValidationCase                                    # <<FROZEN core fields>>
schema_version: "1.0.0"
case_id:    "kokate-2024-r134a-sweep-3"

source:                                   # provenance of the reference data
  citation:  "Kokate et al. (2024)"
  doi:       "10.xxxx/xxxx"?
  dataset:   $ref?                         # digitised data file, content-hash pinned
  notes:     "R-134a microchannel loop; MAE per Eq. 17"?

input_conditions:                         # the operating point to reproduce — maps to a Scenario (§10)
  fluid:        "R134a"
  scenario_ref: $ref                       # the tuple/scenario that recreates these conditions
  raw_inputs:   { heat_load_W: 1500.0, sink_T_K: 293.15, mdot_kg_s: 0.05 }   # as reported by the source

measured_quantities:                      # what the experiment/literature reports
  - { quantity: "outlet_quality",   value: 0.78,    uncertainty: 0.03, units: "-" }
  - { quantity: "pressure_drop",    value: 5.0e4,   uncertainty: 2.0e3, units: "Pa" }
  - { quantity: "wall_T",           value: 305.0,   uncertainty: 1.5,  units: "K" }

expected_outputs:                         # what a conforming run should produce (derived from measured)
  - { quantity: "outlet_quality", expected: 0.78, tolerance: 0.05 }
  - { quantity: "pressure_drop",  expected: 5.0e4, tolerance: 0.10 }   # relative tolerance

comparison_metrics:                       # how agreement is scored
  - { metric: "MAE",  definition: "Kokate Eq. 17", applies_to: [ "outlet_quality", "wall_T" ] }
  - { metric: "relative_error", applies_to: [ "pressure_drop" ] }
```

- **`measured_quantities` carry uncertainty** — a validation case without reported uncertainty is incomplete; the comparison is meaningful only against the experimental error band.
- **`input_conditions` map to a Scenario** (`scenario_ref`): a validation case is run by instantiating the tuple that recreates its conditions, producing a Result, and scoring the Result against `expected_outputs` via `comparison_metrics`.
- **Named future cases** (MASTER §17, harvest order item 6): **Kokate (2024)** R-134a (the first end-to-end target, with digitised data + MAE Eq. 17 + four worked sweeps), **Li et al. (2021)** Acetone, **Fujii et al. (2004)** (the A0 embedded validation data). Each serializes under this schema; the digitised data is pinned by `$ref`/content-hash for reproducibility.
- **This schema feeds `TEST_PLAN_V1.md`'s literature level**: the case is the reference; the test plan defines the pass/fail gating on `comparison_metrics`.

---

# 19. File Organization Recommendation

Where serialized artifacts and data assets should live in the repository, and what is and is not committed to git.

```
mpl-loop-sim/
├── examples/                       # worked, committed tuple+result fixtures (small, illustrative)
│   ├── two_component_loop/         #   the §18-MASTER first vertical slice as a fixture
│   └── kokate_r134a/               #   a validation-case tuple + expected result
├── data/
│   ├── validation/                 # validation case files (§18) + digitised reference data
│   │   ├── kokate_2024/            #   Kokate R-134a: case file + digitised CSVs
│   │   ├── li_2021/                #   Li et al. Acetone
│   │   └── fujii_2004/             #   Fujii (from A0)
│   ├── surrogates/                 # DOE dataset files (§17) + trained surrogate artefacts
│   │   └── doe_2026_06/            #   dataset manifest + (large) result collections
│   └── property_tables/            # tabulated property data backing TabulatedPropertyBackend (§5.4)
│       └── r134a/                  #   the 29-CSV recovery target (MASTER §17 — currently MISSING)
└── docs/architecture/             # this document and its companions
```

Commit / do-not-commit rules:

- **Commit (small, canonical, reference):** validation case files (§18) and their *digitised* reference data; small example tuples/results (`examples/`); the schema itself; a DOE dataset's *manifest* (the `points` list with refs).
- **Commit with care (data assets, version-pinned):** property-table files (§5.4) — they are a reproducibility dependency (a result is only reproducible against the exact tables it used), so they are committed and content-hash pinned **when recovered**. The 29 CSVs are **currently missing** (MASTER §17) — the `property_tables/` tree is structurally present but functionally empty until the data task completes (§5.4).
- **Do NOT commit (large, regenerable, derived):** bulk DOE *result collections* (potentially thousands of result files — store in `data/surrogates/` but git-ignore the heavy payloads, keeping only the manifest); the `cached_profiles` post-processing payload (§14.4, regenerable from `(P, h)`); trained surrogate weight blobs beyond a size threshold (reference by content-hash, store in an artifact store, not git).
- **Never commit** anything that re-derives from a committed tuple — that is the §2.3 minimal-state principle applied to the repository: store the irreducible input, regenerate the rest.

---

# 20. Schema Anti-Patterns

Each is tied to the principle (§2) or frozen decision it violates. These are the serialization-layer code-review checklist, specializing MASTER §19 and `INTERFACE_SPEC.md` §16.

1. **Storing derived properties redundantly** — serializing `T`/`x`/`ρ` beside `(P, h)` in a tuple or result. *Guard:* §2.4 — derived properties are recomputed on load through `FluidState`; the only sanctioned derived store is the explicitly-marked, separated, regenerable `cached_profiles` (§14.4).
2. **Missing schema version** — any artifact without `schema_version`. *Guard:* §2.1 — it is the first field read; an unversioned artifact is uninterpretable for archival.
3. **Hidden default model selections** — a result whose number depended on a backend/correlation/law chosen by a constructor default, not named in the tuple. *Guard:* §2.5 — every model selection is an explicit serialized binding (§5, §11).
4. **Result without a tuple reference** — a result that cannot name the input that produced it. *Guard:* §2.7, §14 — `tuple_ref` is mandatory; a result without it is unreproducible and malformed.
5. **Calibration not reported** — a `TARGET` run whose result omits the factors, or a result with no `calibration_report` at all. *Guard:* §12, §14 — the report is mandatory even under `NONE` (empty factors); *a factor that is not reported cannot exist*.
6. **Validity warnings not persisted** — an extrapolated/out-of-range closure call that never reaches `validity_warnings`. *Guard:* §16.2 — *a warning that does not reach the Result does not exist*; non-`IN_ENVELOPE` verdicts are always persisted.
7. **Accumulator law parameters in geometry** — serializing `V_gas_charge`/spring rate/bellows area/polytropic index inside `AccumulatorGeometry`. *Guard:* §6.4, §11.3 — geometry is containment only; law parameters travel with the law selection.
8. **Mesh in geometry** — serializing segment/zone count inside a geometry record. *Guard:* §6, §7 — discretization is a separate per-component field; state count is derived on load, never serialized in geometry.
9. **Geometry hierarchy creep** — a serialized base-`Geometry` object growing shared fields/optionals, or a single `Δz` hard-wired so a trajectory cannot extend. *Guard:* §6 — flat `#kind`-discriminated family; `trajectory` is typed `PipePath` for additive extension.
10. **Storing `P_sys` on the accumulator** — serializing the system pressure as an accumulator internal state. *Guard:* §14.2, `[F15]` — `V_g` is stored, `P` is derived from the law; `P_sys` is a SystemState unknown, never an accumulator field.
11. **Miscategorising a model registry in serialization** — putting a property backend in `correlation_selections`, or a heat-exchanger strategy among the correlation roles. *Guard:* §11 — four distinct selection fields/registries; a backend is `property_backend_selections`, an HX strategy is `hx_model_selections`.
12. **Values on serialized ports** — a port record carrying `(P, h, mdot)` or a derived property. *Guard:* §8 — ports serialize connectivity only; converged values live in the result's `converged_port_values` map.
13. **Mutating a tuple/result file in place** — editing a "varied" parameter on an existing input file rather than writing a new one. *Guard:* §2.2 — serialized inputs and outputs are immutable; variation writes a new tuple (the DOE unit).
14. **Hiding failed DOE points** — a dataset that drops non-converged or out-of-envelope runs. *Guard:* §17 — failed runs are first-class records with a `status`/`failure`; the surrogate needs the feasible-region boundary.
15. **Surrogate without a serialized training-domain envelope** — an admitted ML closure whose result omits `training_dataset` / `envelope`. *Guard:* §16.1, §17.1, `CORRELATION_CONTRACT.md` §10.4 — non-reproducible and inadmissible.
16. **Comparing calibrated and predictive results as equal** — a dataset/analysis ignoring the `predictive_or_calibrated` flag. *Guard:* §14, §12 — a `CALIBRATED` result is never compared as-equal to a `PREDICTIVE` one.
17. **Inventing absent bounds/defaults** — writing a fabricated envelope bound or a guessed property where the source establishes none. *Guard:* §2.6, §16.3 — an absent bound means unbounded/unknown and is declared absent, never invented.

---

# 21. Readiness for Implementation

## 21.1 Verdict

**The serialization schema is mature enough to implement YAML/JSON serialization for the Phase-1–4 steady-state framework.** The two mandatory artifacts — the Reproducibility Tuple (§4) and the Result (§14) — are fully specified, versioned, and traceable to their frozen in-memory contracts (`INTERFACE_SPEC.md` §15, §14). Every value object they compose has a serialized form (§5–§13, §15, §16). An implementer can write a conforming serializer/deserializer, and a reviewer can reject a non-conforming artifact, from this document plus its two upstream contracts.

The schema satisfies every required principle:

- **Versioned** (§2.1) — `schema_version` on every artifact.
- **Result reproducible from its tuple** (§2.7, §14) — `tuple_ref` + minimal state.
- **Only irreducible values stored** (§2.3, §14) — `(P, h, mdot)` + named internal states.
- **No redundant derived properties** (§2.4) — recomputed through `FluidState`; one hedged cache.
- **DOE/surrogate-ready** (§17) — dataset schema with failed-point recording and training-pair metadata.
- **Multi-fluid and mixture-ready** (§5) — discriminated `FluidIdentity`; additive backend selection.
- **Calibrated and predictive runs** (§12, §14) — mode flag and always-present report.
- **Long-term archival** (§2, §16, §19) — version pinning, closure provenance, commit discipline.

## 21.2 Remaining blockers and decisions (all data/specification, none architectural)

1. **The 29 tabulated property CSVs are missing** (MASTER §17, §5.4, §19). The `TabulatedPropertyBackend` selection schema is complete, but the data it pins is unrecovered. This blocks `σ_e`/`ε_r`-dependent runs, not the schema. A data-recovery task, flagged for traceability.
2. **Validation-case digitised data must be sourced and pinned** (§18). The case schema is complete; the Kokate / Li / Fujii datasets must be digitised and content-hash pinned before the literature-validation level (`TEST_PLAN_V1.md`) can run. A data task, parallel to implementation.
3. **The content-hash canonicalization rule must be fixed** (§3.4 referenced; §4.2, §14 use it). Whether `tuple_id`/`result_id` hash over a canonical-JSON normalization or another stable serialization is an *implementation* decision to settle at first serializer authoring — the schema only requires that the chosen canonicalization be deterministic and documented. Recommend canonical-JSON (sorted keys, normalized number formatting) and recording the hash algorithm in `metadata`.
4. **`<<SEAM>>` fields are declared, not populated** (§2.8): `disturbances` (§10.3), the `dynamic` solver block (§13), `MovingBoundary` variable-count result states (§7, §14.2), the DOE dataset (§17), and surrogate training metadata (§17.1). Their shapes are fixed; v1 writes them empty/absent. Populating them is a phase activation, not a schema redesign.
5. **Per-correlation `ValidityEnvelope` data must be populated** (§16.3, `CORRELATION_CONTRACT.md` §6.2/§14.2). The envelope *format* is frozen here; the *bounds per closure* are a literature task per correlation. A closure registered without an envelope is inadmissible — this gates catalogue completeness, not the schema.

None of these reopen a frozen decision; none change a field marked `<<FROZEN>>`. They are data-recovery and catalogue-population tasks that proceed in parallel with implementing the serializer.

## 21.3 Expected longevity

This schema is written to outlive its contents. The frozen surface — the tuple structure, the result's stored/reported/derived partition, the model-selection bindings, the closure-provenance record, the validity-warning format, the `schema_version` discipline — is independent of *which* correlation, backend, fluid, or solver is named on any given day. The catalogue turns over; the record format does not. A `Result` written under `schema_version: 1.0.0` against a fixed tuple remains interpretable across the full 5–10-year horizon, because everything beyond `(P, h, mdot)` + named internal states is regenerated from the named, versioned models the tuple records — not frozen into the bytes.

---

*End of SCHEMA_SPEC.md — the serialization and reproducibility-schema specification for the MPL simulation framework. Subordinate to ARCHITECTURE_MASTER.md, INTERFACE_SPEC.md, and CORRELATION_CONTRACT.md; frozen schemas are tagged `<<FROZEN>>`, future seams `<<SEAM>>`. This document owns the serialized bytes and version fields that INTERFACE_SPEC.md §14/§15 defer to it. Companion remaining: TEST_PLAN_V1.md.*
