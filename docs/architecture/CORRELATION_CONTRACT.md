# CORRELATION_CONTRACT.md

**The scientific closure-model specification for the MPL simulation framework.**

Status: **interface specification (pre-implementation).** This is the authoritative reference for every *closure relation* in the framework — heat-transfer, pressure-drop, void-fraction, flow-regime, accumulator pressure-law, and future ML/PINN closures. It is downstream of, and subordinate to, `ARCHITECTURE_MASTER.md` and `INTERFACE_SPEC.md`; where it refines those documents it does so by **specifying a scientific contract**, never by reopening a frozen decision (`[F1]`–`[F18]`, Decisions 001–009).

Scope of authority (per MASTER §18 and INTERFACE_SPEC §7.2/§7.4): this document **owns**
- the per-role `CorrelationInput` field manifests (INTERFACE_SPEC froze the *roles*; this document freezes their *fields*);
- the **validity-envelope declaration format** and the semantics of the `ValidityVerdict` return shape;
- the scientific responsibilities, ownership boundaries, and anti-patterns of every closure category;
- the contract a machine-learning / surrogate / PINN closure must satisfy to be admissible.

Horizon: this document is written to remain valid for 5–10 years **even as every individual correlation in the catalogue is replaced.** It specifies *what a closure is and must guarantee*, not *which closures exist*. The catalogue is deliberately unfrozen (MASTER §20).

How to use this document:
- A researcher adding a new correlation should be able to do so from this document alone, without touching any component, solver, or network.
- A reviewer should be able to reject a non-conforming closure by citing a section here.
- It contains **no executable code, no class bodies, no algorithms** — only contracts, in the language-neutral pseudo-signature notation of `INTERFACE_SPEC.md` §1.2 (`<<FROZEN>>` = may not change without a `DECISION_LOG` entry; `<<SEAM>>` = declared now, built in a later phase).

---

## 1. Scope

### 1.1 What a correlation is

A **Correlation is one stateless, pure, named closure relation** that maps a role-typed bundle of physical inputs to a single closure quantity plus a validity verdict (`[F4] [F11]`, MASTER §10, INTERFACE_SPEC §7):

```
evaluate(CorrelationInput) -> CorrelationOutput            # CorrelationOutput { value[], verdict }   <<FROZEN>>
```

A correlation is the smallest replaceable unit of physics in the framework — the **primary research seam** (Principle 2). It answers exactly one local question (“what is the heat-transfer coefficient here?”, “what is the friction gradient in this cell?”, “what void fraction corresponds to this quality?”) for **one control volume / one local state**, and nothing more.

A correlation is a *constitutive* relation. It closes a governing balance by supplying a quantity the conservation laws (mass, momentum, energy) do not themselves determine. The governing balances are owned by Components and assembled by the Solver; the correlation only supplies the missing constitutive number.

### 1.2 What a correlation is NOT

A correlation is **not** any of the following, and conflating them is the most common architectural failure (§13):

- **It is not a property lookup.** `T`, `ρ`, `μ`, `k`, `σ`, `c_p`, `T_sat`, `h_f/h_g/h_fg`, `σ_e`, `ε_r` are thermodynamic/transport *properties of the fluid*, served by the **PropertyBackend** (Layer 1), not closures of a balance. A correlation *consumes* properties via `FluidState`; it never *is* one. The PropertyBackend lives in a separate registry for exactly this reason (`[F6]`, MASTER §6, §3.4 of INTERFACE_SPEC). See §1.3.
- **It is not a solution strategy.** ε-NTU, LMTD, segmented marching, and moving-boundary zone tracking solve a *whole heat exchanger*; they orchestrate many correlation calls and apply a secondary-fluid boundary condition. They are `HeatExchangerModel` strategies (INTERFACE_SPEC §8), a distinct concept with its own registry — **not** correlations. A correlation returns one local value; a model returns a whole-exchanger heat rate and outlet state.
- **It is not a governing balance.** Continuity, momentum, and energy conservation are owned by Components and assembled by the Solver. A correlation supplies a *term* (a gradient, a coefficient) that a balance consumes; it never enforces a balance and is never scaled as if it were one (the conservation firewall, §7, §11 MASTER).
- **It is not stateful.** It owns no state between calls, no cache (`_last_dP`, `_last_Q` forbidden), no module-level globals, no `hasattr` self-introspection, no hard-coded fluid constants (`M = 102.0`). These are catalogued legacy violations (§13, ARCHITECTURE_REVIEW_LEGACY §4.2, §5.2).
- **It is not topology-aware or solver-aware.** It does not know which component called it, what component *type* it serves, what the network looks like, whether it is being finite-differenced, or what timestep is in use (`[F4]`, forbidden DAG directions, MASTER §3).
- **It is not the calibrator.** Calibration multipliers are applied *outside* the correlation, by the Component, at the documented output seam (`[F5]`, §7 here). A correlation returns pure physics.

### 1.3 The five distinguished concepts

The framework deliberately separates five things that immature codebases fuse. This separation is the reason the architecture survives a correlation swap without disturbing anything else.

| Concept | DAG layer | Answers | Owns state? | Knows geometry *type*? | Knows topology / solver? | Registry |
|---|---|---|---|---|---|---|
| **Correlation** | 3 (closure) | one local closure value | no | no (sees declared scalars only) | no | `CorrelationRegistry`, by role |
| **PropertyBackend** | 1 (property engine) | a fluid property at `(P,h,identity)` | internal cache only (pure fn) | no | no | `PropertyBackendRegistry`, separate |
| **HeatExchangerModel** | 5-internal (strategy) | whole-exchanger `Q`, outlet state | no | scalars only | no (component-internal) | `HeatExchangerModelRegistry`, separate |
| **Solver** | 7 (numerics) | the converged `SystemState` | owns `SystemState` | no | yes (it *is* the numerics) | — |
| **Component** | 5 (physics) | a local residual / derivative | named internal states | yes (it owns its Geometry) | no (only its own ports) | — (held by Network) |

Read the table as a chain of responsibility: the **Component** builds a role-typed input from its **Geometry** scalars and `FluidState`(s) (whose properties come from the **PropertyBackend**), hands it to a **Correlation** (or, for an exchanger, to a **HeatExchangerModel** that itself calls correlations), applies **Calibration** to the raw output, and folds the result into the residual the **Solver** assembles. Each arrow crosses exactly one seam.

---

## 2. Correlation Philosophy

### 2.1 The role of correlations in the framework

Correlations are the framework's **engine of scientific extensibility.** The governing physics (conservation laws, the `(P,h)` state representation, the DAG) is fixed; the *constitutive knowledge* — which boiling correlation, which two-phase friction model, which void-fraction relation best matches a given fluid and geometry — is the thing the research is *about*. The entire architecture exists to make that knowledge swappable at one seam, by configuration, without code change (Rule 4, INTERFACE_SPEC §2).

Therefore a correlation is held to five non-negotiable invariants. Each is a consequence of the dependency DAG (MASTER §3) and is enforced in review.

### 2.2 Correlations are replaceable closures

A correlation is selected **by name, bound to a component slot in the Reproducibility Tuple** (§8). Replacing Shah with Kim-Mudawar in an evaporator is a tuple edit — it touches the evaporator's `correlation_selections` binding and nothing else: not the component, not the solver, not the network, not the neighbours. *If swapping a correlation requires touching anything but the tuple, the architecture has been violated.*

This is why **one input type per role, not per formula** (`[F11]`): Shah, Gungor-Winterton, Chen, and Kim-Mudawar all consume the identical `HTCInput`, so the slot accepts any of them interchangeably. The role set is bounded by design and does not grow with the catalogue.

### 2.3 Correlations never own state

A correlation is a mathematical function. Two calls with equal inputs return equal outputs, always, regardless of call order or history. It holds no fields between calls, caches no result, and reads no mutable global. Any apparent need for state is a design error: the missing data must arrive *through the input object*, never via a side channel. (Legacy `_fluid_name` lists and `_mu_v_store` introspection are the canonical violations — ARCHITECTURE_REVIEW_LEGACY §4.2.)

### 2.4 Correlations never know topology

A correlation cannot ask “am I in an evaporator?”, “what is the flow in the parallel branch?”, or “how many components are downstream?”. It receives a self-contained role-typed input and returns a value. Branch coupling, loop closure, and inventory are **Network** conditions (MASTER §13); a correlation that reaches for them breaks swappability and is forbidden by the DAG (Correlation → Component and Correlation → Network are forbidden directions, MASTER §3).

### 2.5 Correlations never know solver details

A correlation does not know whether it is being evaluated for a residual, a finite-difference Jacobian column, a fixed-point sweep, or a future implicit dynamic step. It must be **differentiable in practice** — no hidden non-smooth branches at phase transitions (the `(P,h)` representation buys continuity across the saturation dome; the correlation must not reintroduce discontinuities). It must never select a timestep, assume an iteration scheme, or store a Jacobian assumption (`[F18]`, MASTER §16, anti-pattern §13.5 MASTER).

### 2.6 Correlations never own calibration

A correlation returns **raw, predictive physics.** The reconciliation of model to experiment — the `R*` friction multiplier, the HTC/UA multiplier — is applied *afterward*, by the Component, at the documented output seam (§7). A reader of a correlation formula must never encounter a fudge factor. This is the conservation firewall (MASTER §11): because calibration scales *closures* and never *balances*, a wrong calibration shows up as a worse data match, never as a falsely-passing invariant.

---

## 3. Correlation Categories

The framework supports a **closed set of correlation roles** (the slot vocabulary, INTERFACE_SPEC §7.2/§7.5). Roles are frozen; the formulas filling them are not. Each role below states its **purpose**, **expected output(s)**, and **ownership boundaries** (what it may and may not see).

The roles, as a single enumeration:

```
CorrelationRole = SINGLE_PHASE_DP                                       <<FROZEN role set>>
                | TWO_PHASE_DP
                | HTC                       # single- and two-phase HTC share this role
                | VOID_FRACTION
                | FLOW_REGIME
                | CRITICAL_HEAT_FLUX        # <<SEAM>>: future
                | VOLUME_PRESSURE_LAW       # accumulator pressure laws (§9)
                | CUSTOM_CLOSURE            # <<SEAM>>: ML / PINN / ROM admissible under §10
```

> **ε-NTU / LMTD are not a role.** There is deliberately no `HEAT_EXCHANGE_METHOD` role; heat-exchanger solution strategies are `HeatExchangerModel` (INTERFACE_SPEC §8), resolved from a separate registry. This is the §17-A3 amendment to the master.

### 3.1 Single-phase pressure drop — `SINGLE_PHASE_DP`

- **Purpose:** supply the single-phase frictional pressure **gradient** for one control volume of a passage.
- **Output:** `(dP/dx)_friction` (Pa/m), vector-first. **Not** a total ΔP — total ΔP is the Component's integral over the discretization (`[F14]`, MASTER §12.3).
- **Ownership boundary:** consumes `SinglePhaseDPInput` (§4.4) — `FluidState`, mass flux `G`, hydraulic diameter `D_h`, roughness, cell length. Knows nothing of orientation, gravity, or acceleration: those terms are physics the Component adds (gravity from Scenario, acceleration from the flux profile) and are **never** part of the friction closure and **never** calibrated.
- **Representative formulas (catalogue, not frozen):** Churchill, Blasius, Gnielinski-region single-phase friction factors.

### 3.2 Two-phase pressure drop — `TWO_PHASE_DP`

- **Purpose:** supply the two-phase frictional pressure **gradient** for one control volume.
- **Output:** `(dP/dx)_friction` (Pa/m), two-phase, vector-first. The **acceleration gradient** `d(G²v)/dx` and the **gravity gradient** `ρ g dz/dx` are computed by the Component, not by this closure (MASTER §12.3); a two-phase-DP correlation that bundles acceleration into its return is malformed.
- **Ownership boundary:** consumes `TwoPhaseDPInput` (§4.4) — `FluidState`(s) spanning the cell, `G`, quality profile `x`, `D_h`, cell length. May internally require a void-fraction or multiplier sub-model; if so it consumes the *property anchors* it needs, never another component's output.
- **Representative formulas:** Friedel, Müller-Steinhagen-Heck (MSH), Kim-Mudawar (2013), homogeneous, mixture friction factor (legacy A0).

### 3.3 Single-phase heat-transfer coefficient — `HTC` (single-phase regime)

- **Purpose:** supply the local convective heat-transfer coefficient for single-phase flow.
- **Output:** `HTC` (W/m²·K), vector-first.
- **Ownership boundary:** consumes `HTCInput` (§4.4). Forwarded geometry scalars only (`D_h`, heated-area descriptors); no component identity.
- **Representative formulas:** Dittus-Boelter, Gnielinski, Shah-London laminar.

### 3.4 Two-phase heat-transfer coefficient — `HTC` (boiling / condensation regime)

- **Purpose:** supply the local boiling or condensation heat-transfer coefficient.
- **Output:** `HTC` (W/m²·K), vector-first. **Single- and two-phase HTC share one role** (`HTC`) and one input type (`HTCInput`) so a component's HTC slot is regime-agnostic; the *correlation* internally distinguishes nucleate/convective/condensing behaviour from its inputs.
- **Ownership boundary:** consumes `HTCInput` (§4.4), including the optional wall heat flux `q_flux` and the quality profile. A two-phase HTC must obtain wall-superheat and saturation anchors through `FluidState`/inputs, **never** by reaching into the component's wall-temperature state directly (that state is handed in *as input* when the formula needs it).
- **Representative formulas:** Shah, Chen, Bennett-Chen, Gungor-Winterton, Kandlikar-Balasubramanian, Kim-Mudawar (2012) for boiling; Shah-1979/2021, Chen-style, Yan for condensation; the legacy A0 nucleate+convective ΔT fixed-point.

### 3.5 Void fraction — `VOID_FRACTION`

- **Purpose:** supply the cross-sectional void fraction (vapor area fraction) given the local quality and phase properties.
- **Output:** `ε_void` / `α` (dimensionless, 0–1), vector-first.
- **Ownership boundary:** consumes `VoidFractionInput` (§4.4) — `FluidState`(s) and quality. Geometry-light: most void models need only properties and quality; any that need a Froude/Bond number receive the requisite scalars in the input. A void model is a **constitutive relation, not a balance** — it does not enforce inventory; the Network owns inventory.
- **Representative formulas:** homogeneous (HEM), Zivi, Rouhani-Axelsson, Steiner drift-flux.

### 3.6 Flow regime — `FLOW_REGIME`

- **Purpose:** classify the local two-phase flow pattern (e.g. bubbly, slug, annular, mist) and/or return a continuous regime indicator, for use as a *selector or weighting* by HTC/DP correlations that are regime-dependent.
- **Output:** a `FlowRegimeVerdict` — a discriminated regime label **plus**, where the underlying map provides it, continuous transition coordinates. Vector-first.
- **Ownership boundary:** consumes `FlowRegimeInput` (§4.4). **A flow-regime correlation classifies; it does not branch component code.** The anti-pattern `if regime == annular: shah()` welded into a component is forbidden (§13, MASTER §19.6). Regime selection, when used, is itself expressed as a regime-aware HTC/DP correlation that *consumes* the regime verdict as an input field — keeping the component free of physics branches.
- **Continuity caution:** a hard regime switch reintroduces the very non-smoothness `(P,h)` was chosen to avoid (§2.5). Regime maps used inside differentiable closures should expose smooth/blended transition coordinates, not only a hard label. This is a scientific requirement, not merely numerical hygiene.

```
FlowRegimeVerdict {                                                    <<FROZEN>>
  regime: (BUBBLY | SLUG | CHURN | ANNULAR | MIST | STRATIFIED | INTERMITTENT | SINGLE_PHASE | ...)
  transition_coords: { name -> float }?    # continuous indicators for blending, when available
  verdict: ValidityVerdict
}
```

### 3.7 Critical heat flux — `CRITICAL_HEAT_FLUX` `<<SEAM>>`

- **Purpose (future):** supply the critical/limiting heat flux for a given local state, enabling dryout/burnout detection.
- **Output:** `q''_crit` (W/m²) and/or a critical-quality indicator, vector-first.
- **Ownership boundary:** consumes a future `CriticalHeatFluxInput`. **Declared now, implemented later.** The role exists so a CHF closure is an additive catalogue entry, never a redesign. Until built, no component declares a CHF slot.

### 3.8 Accumulator pressure laws — `VOLUME_PRESSURE_LAW`

- **Purpose:** map the accumulator's stored gas/displaced volume to the system reference pressure (and, in dynamics, `dP/dt` from `dV_g/dt`).
- **Output:** `P` (Pa) derived from `V_g`, vector-first.
- **Ownership boundary:** see §9 — this is a correlation-like closure with its own role and input type, deliberately admitted to the same registry and contract so PCA/HCA/bellows/spring/gas-charged are interchangeable bindings.

### 3.9 Custom closure models — `CUSTOM_CLOSURE` `<<SEAM>>`

- **Purpose:** admit surrogate models, PINNs, neural closures, and reduced-order models under the identical contract (§10).
- **Output:** whatever role they stand in for — a custom closure declares the role it substitutes and obeys that role's input/output/verdict contract exactly.
- **Ownership boundary:** identical to the role it replaces, **plus** the traceability requirements of §10 and §12. A surrogate that does not declare its training-domain envelope is inadmissible.

---

## 4. Correlation Input Architecture

### 4.1 The role-typed input philosophy

A correlation receives **one immutable, role-typed `CorrelationInput` value object**, never a positional argument list and never a whole `Component`/`Geometry`/`SystemState` object (`[F11]`, Decision 005, INTERFACE_SPEC §7.2). There is **one input type per role**, shared by every formula in that role.

```
CorrelationInput = SinglePhaseDPInput
                 | TwoPhaseDPInput
                 | HTCInput
                 | VoidFractionInput
                 | FlowRegimeInput
                 | CriticalHeatFluxInput        # <<SEAM>>
                 | VolumePressureLawInput
                                                                       <<FROZEN role set>>
```

### 4.2 Why role-typed inputs over positional argument lists

This was settled in Decision 005; the reasons are restated because they are scientific, not merely stylistic:

- **A written manifest of visibility.** The input type is the exhaustive declaration of *what a correlation family is allowed to see.* A reviewer audits the data flow by reading one struct, not by tracing call sites. This is what makes a closure scientifically reviewable.
- **Order-independence and churn-resistance.** Positional scalars degrade past three arguments, are order-fragile, and force signature churn across the whole catalogue whenever one input is added. A named field is added once. (The legacy PyP2PL correlation layer broke on exactly this — ARCHITECTURE_REVIEW_LEGACY §4.2.)
- **Decoupling from component/geometry type.** Because the correlation sees scalars and `FluidState`, not a `MicrochannelGeometry` or an `Evaporator`, it cannot develop a hidden dependency on either. The forbidden direction Correlation → Component is made *unrepresentable*.
- **AD-traceability and ML-readiness.** An immutable, fully-named input struct is a feature vector. The same object serves a Shah formula, a finite-difference Jacobian column, and a PINN closure with no special-casing (§10).

### 4.3 Field taxonomy

Every input type draws its fields from four categories. The contract is: **the Component populates every required field; optional fields are explicitly absent (`?`), never silently defaulted.**

- **Fluid state data** — one or more `FluidState`(s), vector-first where a cell spans a quality range (e.g. inlet/outlet of a two-phase cell). Properties are *derived through the backend in context*, not stored on the input.
- **Flow data** — mass flux `G`, quality profile `x[]`, optional wall heat flux `q_flux`, and any dimensionless flow coordinates a family needs (`Re`, `Bond`, `We`, `Fr`) **only when the component already has them**; otherwise the correlation derives them from `G`, `D_h`, and properties.
- **Geometry data** — *declared scalars only* (`D_h`, `A`, `roughness`, `chevron_angle`, `plate_spacing`, per-cell `L_cell`, `dz/dx` where a closure legitimately needs it). **Never a Geometry object** (`[F8]`, MASTER §8).
- **Cell/discretization context** — `L_cell` (the integration length the gradient is multiplied by downstream), and, for variable-count modes, the cell index context. The correlation returns a *gradient/coefficient*, never an integrated total (`[F14]`).

### 4.4 Per-role input manifests (FROZEN field sets)

These manifests are what INTERFACE_SPEC §7.2 defers to this document. Field *types* and *required/optional status* are frozen; **units are SI** unless `SCHEMA_SPEC.md` names otherwise. `state: FluidState[]` is vector-first; a lumped cell is the length-1/2 case.

```
SinglePhaseDPInput {                                                   <<FROZEN>>
  state:      FluidState[]      # cell state(s); length ≥ 1
  G:          float            # mass flux [kg/m²s]
  D_h:        float            # hydraulic diameter [m]
  roughness:  float            # absolute wall roughness [m]
  L_cell:     float            # cell length [m] (for the caller's integration; closure returns a gradient)
}

TwoPhaseDPInput {                              <<FROZEN — amended by Decision 011>>
  state:              FluidState[]      # cell endpoint states spanning the quality range
  G:                  float
  x:                  float[]           # local quality profile across the cell (0..1, continuous through ends)
  D_h:                float
  L_cell:             float
  regime:             FlowRegimeVerdict?   # optional, for regime-aware two-phase ΔP closures
  property_scalars:   { name -> float }    # explicit formula-specific scalars (see Decision 011)
                                           # e.g. rho_l, rho_v, mu_l, mu_v for MSH (1986)
                                           # default: empty mapping
                                           # caller supplies formula-specific scalars; no property lookup
                                           # correlations validate required keys and values
                                           # missing or invalid keys fail clearly with ValueError
                                           # no CoolProp, no PropertyBackend, no hidden defaults allowed
                                           # does not imply automatic closure selection
                                           # HX use requires an explicit builder/plumbing path
}

HTCInput {                                                            <<FROZEN>>
  state:      FluidState[]
  G:          float
  x:          float[]           # quality profile; single-phase passes a degenerate profile
  D_h:        float
  q_flux:     float?            # wall heat flux [W/m²]; required by flux-dependent boiling closures, else absent
  T_wall:     float?            # wall temperature [K]; supplied as INPUT when a ΔT-driven closure needs it
  geom_scalars: { name -> float }   # e.g. chevron_angle, fin descriptors — declared scalars only
  regime:     FlowRegimeVerdict?
}

VoidFractionInput {                                                   <<FROZEN>>
  state:      FluidState[]
  x:          float[]
  G:          float?            # required only by drift-flux / flux-dependent void models
  D_h:        float?            # required only by models with a Bond/Froude dependence
}

FlowRegimeInput {                                                     <<FROZEN>>
  state:      FluidState[]
  G:          float
  x:          float[]
  D_h:        float
  orientation: float?           # inclination [rad from horizontal]; required by stratified-capable maps
}

CriticalHeatFluxInput {                                               <<SEAM>>
  state:      FluidState[]
  G:          float
  x:          float[]
  D_h:        float
  L_heated:   float?
}

VolumePressureLawInput {                                              <<FROZEN>>  # see §9
  V_g:        float             # stored gas/displaced volume [m³] (the accumulator internal state)
  V_total:    float             # containment volume [m³] (geometry scalar)
  state:      FluidState?       # working-fluid state at the accumulator port, when the law needs it
  law_params: { name -> float } # PCA charge volume & polytropic index, spring rate & preload, bellows area, ...
  thermal:    ThermalSpec?      # heater duty / saturation reference, for HCA-type laws only
  P_set:      float?            # the reference setpoint from Scenario (AccumulatorPressureSetpoint)
}
```

- **Required vs optional.** A field without `?` is mandatory; the Component must populate it. A `?` field is *legitimately absent* for formulas that do not need it — its absence is meaningful (e.g. a flux-independent HTC model receives no `q_flux`), and a formula that requires an absent optional field returns a hard failure verdict (§6.4), never a guessed value.
- **No geometry objects, ever.** `geom_scalars` is a flat scalar bag the Component forwards from its Geometry; the correlation can never recover the Geometry type from it.
- **Vector-first is structural.** Even scalar evaluations pass length-1 arrays so the Phase-5 batch and FD-Jacobian paths are not a later redesign (`[F13]`, Rule 6).

---

## 5. Correlation Output Architecture

### 5.1 The output shape (FROZEN)

```
CorrelationOutput {                                                    <<FROZEN>>
  value:    float[]             # vector-first; the single closure quantity for this role (see §3)
  verdict:  ValidityVerdict     # ALWAYS present (Rule 5: "a result without a residual is not a result")
  metadata: ClosureMetadata     # provenance for reproducibility (§12)
}
```

A correlation **may never return a bare number.** The verdict and metadata are first-class parts of the return, not optional decorations.

### 5.2 Predicted value

- `value` is the **raw, un-calibrated** closure quantity in SI units, in the role's defined meaning (a *gradient* for DP roles, a *coefficient* for HTC, a *fraction* for void, a *pressure* for the pressure law, a *label+coords* for flow regime via `FlowRegimeVerdict`).
- It is **vector-first**: one entry per state/cell passed in.
- It is **never integrated, never totalled, never scaled.** Integration belongs to the Component's discretization (`[F14]`); calibration belongs to the Component's seam (§7).

### 5.3 Validity envelope (carried by the verdict)

Every output carries, via its `ValidityVerdict`, a reference to the **declared envelope** the call was checked against and the **status** of that check (§6). The envelope itself is a static declaration of the correlation (§6.2); the verdict is the per-call result of testing the input against it.

### 5.4 Warnings

- A correlation surfaces concerns through the verdict's `status` and `detail`, and through `PropertyResult` warnings propagated from the backend — **never** through side-channel logging that the Result cannot see.
- Every non-`IN_ENVELOPE` verdict is propagated up through the Component and the HeatExchangerModel into the `Result.validity_warnings` list (INTERFACE_SPEC §14). *A warning that does not reach the Result does not exist.*

### 5.5 Metadata

```
ClosureMetadata {                                                     <<FROZEN>>
  name:     str                 # registered correlation name (the tuple binding)
  version:  str                 # correlation version (catalogue-managed; see §8)
  source:   SourceRef           # citation / DOI / dataset reference (§12)
}
```

Metadata is the reproducibility anchor (§12): it lets a Result name *exactly which closure, at which version, from which source* produced each number. The Component aggregates closure metadata into the Result; calibration and validity status are added at the component seam (§7) and solver level respectively.

### 5.6 Confidence, applicability, and out-of-range behaviour

- **Confidence** is expressed *categorically*, through the verdict status (`IN_ENVELOPE` / `EXTRAPOLATED` / `OUT_OF_RANGE`), not as an invented numeric probability — a correlation does not fabricate a confidence number it cannot defend. (A surrogate model under §10 *may* additionally return a genuine predictive-uncertainty estimate when its method provides one; that is an additive field, never a substitute for the categorical verdict.)
- **Applicability** is the envelope (§6.2): the documented region of fluids, geometries, flow conditions, and dimensionless groups the correlation was developed and validated for.
- **Out-of-range behaviour is transparent, never silent** (`[F4]`, MASTER §10): the framework **warns on extrapolation and never silently clamps or extrapolates.** The numeric value returned for an out-of-envelope call is the formula's honest extrapolated output (flagged `EXTRAPOLATED`) or `NaN` (flagged `OUT_OF_RANGE` for a hard failure, §6.4) — never a clamped or fabricated in-range substitute. The researcher decides acceptability; the framework guarantees they are never unaware.

---

## 6. Validity Philosophy

**This is the scientific heart of the document.** A closure outside its validated envelope is not “slightly less accurate” — it can be physically meaningless. The framework's contract is therefore: **a correlation always reports whether its inputs fell inside its declared envelope, and the framework never hides an excursion.**

### 6.1 What validity means here

Validity is **not** correctness against data (that is the validation harness, `TEST_PLAN_V1.md`). Validity is the **self-declared, per-call statement of whether the inputs lie within the region the correlation's authors validated it for.** It is a transparency mechanism, computed cheaply on every call, surfaced into the Result.

### 6.2 The validity-envelope declaration format (FROZEN)

Every correlation **declares a static `ValidityEnvelope`** as part of its registration. This is the format INTERFACE_SPEC §7.4 defers to this document.

```
ValidityEnvelope {                                                    <<FROZEN>>
  fluid_families:   FluidFamilySpec[]    # which fluids/families the closure is valid for
  bounds:           Bound[]              # the full set of scalar/dimensionless limits
  regime_restriction: FlowRegime[]?      # applicable two-phase regimes, if restricted
  source:           SourceRef            # the citation establishing this envelope
  notes:            str?
}

Bound {                                                               <<FROZEN>>
  quantity: BoundedQuantity              # what is bounded (closed enumeration below)
  min:      float?                       # absent = unbounded below
  max:      float?                       # absent = unbounded above
  units:    str                          # SI unless SCHEMA_SPEC names otherwise
}

BoundedQuantity = REYNOLDS | MASS_FLUX_G | QUALITY_X | BOND | WEBER | FROUDE
                | REDUCED_PRESSURE | PRANDTL | HYDRAULIC_DIAMETER | ASPECT_RATIO
                | CHEVRON_ANGLE | HEAT_FLUX | SATURATION_TEMP | <named scalar>
                                                                       <<FROZEN core; extensible by name>>

FluidFamilySpec = AnyFluid
                | NamedFluids   { names: str[] }            # e.g. ["R134a", "R1234yf"]
                | FluidClass    { class: (REFRIGERANT | WATER | HYDROCARBON | DIELECTRIC | ...) }
```

This declarative form is the longevity guarantee: a correlation's *applicability* is data, citable to its source, independent of the formula's code.

### 6.3 The dimensions an envelope must address

A complete envelope declares bounds across, at minimum, the dimensions relevant to its role:

- **Reynolds range** (`REYNOLDS`) — laminar/transitional/turbulent applicability; mandatory for every DP and single-phase-HTC closure.
- **Quality range** (`QUALITY_X`) — the `x` interval a two-phase closure was fitted over; mandatory for `TWO_PHASE_DP`, two-phase `HTC`, `VOID_FRACTION`.
- **Bond / Weber / Froude** (`BOND`, `WEBER`, `FROUDE`) — the surface-tension / inertial / gravitational regimes; mandatory for microchannel and gravity-sensitive closures (the MPL microchannel evaporator and any zero-/variable-g study live or die on the Bond-number bound).
- **Geometry limits** (`HYDRAULIC_DIAMETER`, `ASPECT_RATIO`, `CHEVRON_ANGLE`, …) — the passage dimensions the closure was developed for; a macrochannel correlation declared down to `D_h` it never saw is a misuse the envelope must catch.
- **Reduced pressure / saturation** (`REDUCED_PRESSURE`, `SATURATION_TEMP`) — proximity to the critical point, where two-phase closures degrade.
- **Fluid restrictions** (`fluid_families`) — the fluids or fluid classes validated; a closure fitted to R-134a is not silently valid for ammonia.
- **Heat flux** (`HEAT_FLUX`) — for flux-dependent boiling and the (future) CHF role.

A bound that the source does not establish is **declared absent**, not invented. An absent bound means “unbounded / unknown”, and the envelope's `notes`/`source` must make that explicit.

### 6.4 Warnings, soft failures, hard failures — the three-state contract

The frozen `ValidityVerdict.status` enum encodes a precise three-level severity. **The enum is frozen (INTERFACE_SPEC §7.4); this document fixes its semantics.**

```
ValidityVerdict {                                                     <<FROZEN>>
  status:   (IN_ENVELOPE | EXTRAPOLATED | OUT_OF_RANGE)
  envelope: EnvelopeRef        # reference to the ValidityEnvelope checked against
  violated: Bound[]            # which specific bounds were exceeded (empty when IN_ENVELOPE)
  detail:   str?
}
```

| Status | Severity | Meaning | Value returned | Framework action |
|---|---|---|---|---|
| `IN_ENVELOPE` | none (pass) | every input inside every declared bound | the physics value | none |
| `EXTRAPOLATED` | **soft failure (warning)** | one or more inputs outside a bound, but the formula remains evaluable and returns a defensible extrapolated number | the honest extrapolated value, **never clamped** | **warn**; surface into `Result.validity_warnings`; the run continues; the researcher decides acceptability |
| `OUT_OF_RANGE` | **hard failure** | inputs make the formula undefined / non-evaluable (e.g. required optional field absent, physically impossible input, a property the backend reports `UNAVAILABLE`/`OUT_OF_RANGE`) | `NaN` | **warn loudly**; surface into `Result.validity_warnings`; the invariant/bound checks (`Result.invariants`) will reflect the contaminated number — it is never masked |

Design rules behind the table:

- **The framework never silently clamps and never silently extrapolates** (`[F4]`). A `EXTRAPOLATED` value is the real extrapolation, flagged — not a value snapped back to the envelope edge.
- **A hard failure produces `NaN`, never a fabricated number** — consistent with the PropertyBackend's “no extrapolation by stealth” (`[F13]`-5). A `NaN` propagates honestly into the invariants rather than hiding behind a plausible-looking wrong value.
- **`violated` names the specific bounds**, so a researcher (or a future automated screen) sees *which* dimension was exceeded, not merely that something was.
- **The researcher, not the framework, decides whether an `EXTRAPOLATED` run is acceptable.** The framework's only obligation is that the excursion is impossible to miss: it is in the verdict, in the warnings list, and traceable to the named bound.

### 6.5 Validity and continuity

A subtle scientific obligation: a regime-restricted closure must not produce a *discontinuity* at its envelope edge that the solver then trips over. Envelope checking is a *reporting* mechanism, not a *branching* one — the correlation still returns a continuous value (extrapolated, flagged) past the edge. This preserves the differentiability promise (§2.5) while keeping the researcher informed (§6.4). Hard cut-offs that return `NaN` mid-domain (rather than at a genuine physical impossibility) are an anti-pattern (§13).

---

## 7. Calibration Interaction

### 7.1 The principle: calibration is external

Calibration (`[F5]`, MASTER §11, INTERFACE_SPEC §9) is the framework's mechanism for reconciling a predictive closure with experimental data **transparently.** Its single most important property, with respect to correlations, is:

> **Calibration applies *outside* the correlation. It never modifies the correlation definition, never enters the formula, and is never visible to the closure itself.**

A correlation returns raw physics (§2.6, §5.2). The Component then multiplies that raw output by a named factor *at the documented seam* (§7.3) before folding it into a balance. The correlation is, and remains, a pure predictive function.

### 7.2 The two modes

```
CalibrationMode = NONE | TARGET                                       <<FROZEN>>
```

- **`NONE`** — every factor = 1.0; pure predictive physics; the default and honest baseline. A correlation evaluated under `NONE` *is* its raw output.
- **`TARGET`** — factors chosen to meet a stated experimental target. A Result produced under `TARGET` is **flagged calibrated, not predictive**, and is never compared as-equal to a `NONE` run (§12, INTERFACE_SPEC §14).

There is no `DATASET_FIT` calibration mode. Least-squares identification over many points is **Phase-5 surrogate/identification territory**, and must route its results back as ordinary explicit `TARGET` factors at this same seam — never as a parallel hidden mechanism (MASTER §11, INTERFACE_SPEC §9.1).

### 7.3 Where calibration touches a correlation's output

Calibration scales **closure outputs only**, at three sanctioned targets (`[F14]`, INTERFACE_SPEC §9.2):

```
CalibrationTarget = FRICTION_GRADIENT | HTC | UA                      <<FROZEN>>
```

- **`FRICTION_GRADIENT`** — `R*` multiplies the friction gradient returned by a `SINGLE_PHASE_DP` or `TWO_PHASE_DP` closure. **Gravity and acceleration gradients are physics and are never scaled.**
- **`HTC`** — a multiplier on the heat-transfer coefficient returned by an `HTC` closure.
- **`UA`** — the analogous multiplier applied by a `HeatExchangerModel` to the conductance it assembles from HTC closures.

**Void-fraction, flow-regime, and volume-pressure-law closures are not calibrated** (§3.5, §3.6, §9; INTERFACE_SPEC §7.5). A calibration factor targeting them is malformed.

### 7.4 The conservation firewall (what calibration may never do)

Three invariants, each a hard requirement on how calibration interacts with closures:

1. **Correlations stay pure** — calibration scales the output *after* the correlation returns; the formula never sees a factor.
2. **Conservation is never scaled** — calibration multiplies *closures* (friction gradient, HTC, UA); it never multiplies a *balance* (mass/energy continuity). The friction term is scaled; the momentum balance that consumes it is not.
3. **Calibration cannot mask an invariant violation** — the Result's energy/mass imbalance and pressure-closure residuals are computed from *un-calibrated* conservation (INTERFACE_SPEC §13.4), so a wrong calibration shows up as a *worse data match*, never as a *false-passing balance*. Calibration can move the operating point; it can never make `Σṁ ≠ 0` look like zero.

### 7.5 Calibration reporting requirements

Calibration's interaction with correlations is only legitimate if it is **always reported** (§12). Every non-neutral factor must record, into the Result's `CalibrationReport`:

- the **target** (`FRICTION_GRADIENT` / `HTC` / `UA`);
- the **value** (1.0 = neutral);
- the **mode** (`NONE` / `TARGET`);
- the **seam location** — *which slot, on which component, scaling which correlation's output*.

*A factor that is not reported cannot exist.* A Result missing its calibration report is malformed (INTERFACE_SPEC §14). This requirement is what lets a reader of a Result reconstruct exactly which closure outputs were adjusted and by how much, years later.

---

## 8. Correlation Registry

The registry is the mechanism that makes a closure swappable by name. It is **lightweight by mandate** — “not a plugin framework, factory, or DI container” (Principle 6, INTERFACE_SPEC §7.6).

### 8.1 Registration

```
register(name: str, instance: Correlation) -> void     # startup only; name -> stateless instance
```

- Registration is **startup-time only.** The registry owns no per-run state and is never mutated mid-solve.
- A registered instance is **stateless**; one shared instance serves every call (§2.3).
- Registration records the instance's **role**, its **`ValidityEnvelope`** (§6.2), its **version**, and its **`SourceRef`** — the metadata a Result later cites (§12).

### 8.2 Lookup

```
resolve(name: str) -> Correlation
by_role(role: CorrelationRole) -> (name -> Correlation)
```

- A Component declares **slots by role** (“I need a boiling `HTC` and a `TWO_PHASE_DP`”); the Reproducibility Tuple **binds a registered name to each slot** (`correlation_selections`, INTERFACE_SPEC §15).
- Lookup is by name within a role; a name bound to the wrong role is a binding-time error, not a silent mismatch.
- **The PropertyBackend is never in this registry** — separate registry, no geometry, no slots, to avoid the latent DAG cycle (`[F6]`, §1.3). Likewise `HeatExchangerModel` and `VolumePressureLaw` selection: the HX model has its **own** registry; the volume-pressure law, being a true closure with role `VOLUME_PRESSURE_LAW`, lives in *this* registry but is bound via `accumulator_law_selections` (§9, INTERFACE_SPEC §15).

### 8.3 Versioning

- Every registered correlation carries a **version** string, captured in `ClosureMetadata` and surfaced into every Result (§12). A change to a formula that alters its numbers is a **new version** (and, where it changes inputs/role, a new name).
- Versioning is what lets a 5-year-old surrogate dataset remain interpretable: the Result names not just *Shah* but *which Shah implementation at which version*.

### 8.4 Aliases

- A registry **may** expose thin, readable aliases (e.g. `Splitter`/`Mixer` as aliases of `Junction` at the component level; a friendly correlation alias). Aliases resolve to a canonical name; the Result always records the **canonical** name and version, never the alias, so reproducibility is unambiguous.

### 8.5 Deprecation

- A correlation may be marked **deprecated** (still resolvable, flagged in `ClosureMetadata.notes` and in the Result warnings) before removal. Deprecation is a transparency state, not a silent disappearance — a tuple referencing a deprecated name still runs and still reports the deprecation, so old reproducibility tuples do not silently break.

### 8.6 Future support for user / research / experimental correlations

The registry is designed to admit, **under the identical contract**, three future classes:

- **User-defined correlations** — a researcher registers a new closure for their fluid/geometry; it is admissible the moment it implements `Correlation`, declares a role, and declares a `ValidityEnvelope`.
- **Research correlations** — closures under active development, registered with a clearly-bounded (possibly narrow) envelope and a `source` pointing to the working reference.
- **Experimental correlations** — closures not yet validated, admissible only if their envelope and metadata mark them experimental, so a Result that used one is unambiguously flagged.

No new mechanism is needed for any of these — that is the point of the contract. Admissibility is gated by *the contract*, not by a privileged registration path.

---

## 9. Accumulator Pressure Laws

### 9.1 Pressure laws are correlation-like closures

The accumulator's volume↔pressure relation is treated as a **closure with its own role, `VOLUME_PRESSURE_LAW`**, obeying the same `evaluate(input) → (value, verdict)` contract as any correlation (`[F9]`, INTERFACE_SPEC §11.6/§11.7). This is a deliberate unification: it makes a new accumulator technology a *new law binding*, not a redesigned component.

```
VolumePressureLaw : Correlation   with role = VOLUME_PRESSURE_LAW     <<FROZEN>>
   evaluate(VolumePressureLawInput) -> CorrelationOutput              # value = P derived from V_g
```

### 9.2 The supported laws

The interchangeable law bindings (the catalogue is unfrozen; the *interchangeability* is frozen):

- **Gas-charged** — a charged gas volume sets pressure via a polytropic gas relation.
- **PCA (Passively-Controlled Accumulator)** — charge volume + polytropic index as `law_params`.
- **HCA (Heater-Controlled Accumulator)** — a heater drives a saturation-temperature reference; needs the `thermal` sub-spec (heater duty, saturation reference).
- **Bellows** — an effective bellows area + rate map displacement to pressure.
- **Spring-loaded** — a spring constant + preload map displacement to pressure.

All five consume `VolumePressureLawInput` (§4.4) and return `P` from `V_g`. Swapping among them is a tuple edit (`accumulator_law_selections`, INTERFACE_SPEC §15); the component is unchanged.

### 9.3 Relationship with `AccumulatorGeometry`

**Geometry and law are strictly separated** (the §17-A2 amendment, INTERFACE_SPEC §5.4/§11.6):

- `AccumulatorGeometry` describes **containment only** — `V_total`, the vessel/port containment spec, and an optional `thermal` spec that *law-needing-it* reads.
- **No law parameters live in geometry.** PCA charge volume, polytropic index, bellows area, spring rate, gas-charge pressure, HCA heater duty — all are `law_params`/`thermal` inputs to the law, never geometry fields. A `V_gas_charge` stored in geometry is an anti-pattern (§13, MASTER §19.8).

The law receives `V_total` from geometry as a scalar (`VolumePressureLawInput.V_total`); it never receives the `AccumulatorGeometry` object.

### 9.4 Relationship with internal state

- The accumulator's **stored internal state is `V_g`** (gas/displaced volume); **`P` is derived** from the law, never stored (`[F15]`, Decision 008). The law's job is exactly this derivation.
- In dynamics the accumulator derives `dP/dt` from `dV_g/dt` via the law's slope (using the backend's optional property derivatives where the law needs compressibility, §3 of INTERFACE_SPEC, capability flag). The law's contract is unchanged between steady and dynamic — steady freezes `dV_g/dt = 0`.
- The accumulator does **not** own `P_sys` as a stored field; `P_sys` is a `SystemState` unknown constrained by the law (`[F15]`).

### 9.5 Relationship with Scenario

- The **reference setpoint `P_set`** is a Scenario boundary condition (`AccumulatorPressureSetpoint`, INTERFACE_SPEC §10.2), delivered to the law via `VolumePressureLawInput.P_set`. The law maps `(V_g, V_total, law_params, thermal?, P_set?) → P`.
- **Which node** is the pressure reference is a **Network** fact; the **law/value** is the Accumulator's; **global consistency** is the Solver's — the three-way split of `[F7]`. The law closure knows none of this; it only maps volume to pressure.

### 9.6 Validity for pressure laws

A volume-pressure law declares a `ValidityEnvelope` like any closure — typically bounding `V_g/V_total` (the law is undefined at full liquid or full gas), pressure range, and (for HCA) the saturation-temperature range of the working fluid. An accumulator driven outside its law's envelope reports `EXTRAPOLATED`/`OUT_OF_RANGE` exactly as a heat-transfer closure would (§6).

---

## 10. Machine Learning Closures

The framework is designed so that **surrogate models, PINNs, neural closures, and reduced-order models are admissible as ordinary closures**, under the identical contract — no special path, no parallel mechanism. This is a direct consequence of the role-typed input being a feature vector (§4.2) and the verdict being mandatory (§5).

### 10.1 How an ML closure integrates

An ML/PINN/ROM closure:

- **declares the role it substitutes** (it stands in for an `HTC`, a `TWO_PHASE_DP`, etc., or registers under `CUSTOM_CLOSURE` when it spans a novel role) and **obeys that role's frozen input/output contract exactly** — same `CorrelationInput` type in, same `CorrelationOutput` (`value[]`, `verdict`, `metadata`) out;
- is **registered by name** in the `CorrelationRegistry` (§8) and **bound to a slot in the tuple** like any correlation — swapping a physical correlation for a surrogate is a tuple edit;
- is **stateless at evaluation** (the trained weights are fixed parameters of the instance, not mutable per-call state) and **pure** (equal inputs → equal outputs);
- is **vector-first** — and benefits most from it, since batched inference is its natural mode.

The input object **doubles as the feature vector**: the role-typed manifest (§4.4) is precisely the named, immutable set of features the model consumes. No adapter layer is required.

### 10.2 Required contracts (what makes an ML closure admissible)

An ML closure is admissible **iff** it satisfies, in addition to the base correlation contract:

1. **A declared `ValidityEnvelope` equal to its training/validation domain** (§6.2). A surrogate's envelope is its training-data convex hull (or a defensible bounding box thereof). Querying outside it returns `EXTRAPOLATED`/`OUT_OF_RANGE` — surrogate extrapolation is *more* dangerous than physical-correlation extrapolation, so this is non-negotiable.
2. **Purity and statelessness** (§2.3) — no online learning during a solve, no per-call mutation.
3. **Differentiability in practice** (§2.5) — a closure used in a Newton/Jacobian path must not introduce non-smooth artefacts; this is a property a trained model must be checked for.
4. **No calibration absorption** — a surrogate must not bake an implicit fudge factor that bypasses the calibration seam (§7); if it was identified against data, that is `TARGET`-mode calibration territory and must be declared (§7.2).

### 10.3 Validation requirements

- An ML closure is **validated like any closure** against the literature/experimental targets of `TEST_PLAN_V1.md` — it earns no exemption for being learned.
- Its envelope claim must be **substantiated by its training domain**; a surrogate declaring a wider envelope than its data supports is inadmissible.
- A surrogate **may** additionally return a genuine **predictive-uncertainty** estimate when its method supports one (e.g. ensemble variance, Gaussian-process posterior). This is an *additive* metadata field, never a replacement for the categorical verdict (§5.6).

### 10.4 Traceability

An ML closure's `ClosureMetadata` (§5.5, §12) must name, beyond the usual `name`/`version`/`source`:

- the **training-dataset reference** (content-hash or citation) — the surrogate is only reproducible if its data is identifiable;
- the **model architecture/version** sufficient to reconstruct which trained artefact produced a number;
- the **envelope provenance** (how the training domain was bounded).

Without this, a Result that used the surrogate is not reproducible, and the closure is inadmissible (§12).

---

## 11. Legacy Correlation Migration

Using `ARCHITECTURE_REVIEW_LEGACY.md`, the legacy closure assets are classified under the four verdicts — **Reuse** (cosmetic change), **Adapt** (sound physics, re-housed behind this contract), **Rewrite** (idea needed, implementation violates the contract too deeply to port), **Discard**. Every **Adapt** below means: *port the equation into a stateless `Correlation` with a role-typed input, a declared `ValidityEnvelope`, and a `ValidityVerdict` return; strip globals/hacks; add the envelope; route any calibration to the external seam.*

### 11.1 Two-phase pressure-drop implementations

| Asset | Source | Verdict | Migration |
|---|---|---|---|
| **Müller-Steinhagen-Heck (MSH)** + homogeneous acceleration | PyP2PL `dp_twophase.py`; MPL `correlations.py` | **Adapt** | Clean, Kokate-aligned; near-ready as a `TWO_PHASE_DP` closure (acceleration term stays a *component* concern, not part of the friction closure). |
| **Kim-Mudawar 2013** two-phase ΔP | MPL `correlations.py` | **Adapt** | High-value microchannel two-phase friction; port with a microchannel-bounded envelope (Bond/Re). |
| **Mixture friction factor** `f = (1-ψ)(ρ_l/ρ)f_l + ψ(ρ_v/ρ)f_v` (Blasius base) | A0 `function_conservation` | **Adapt** | Documented HEM two-phase friction; lift the equation into a pure `TWO_PHASE_DP` closure, discard the global-array housing. |
| **Friedel** | *(not present in legacy; named in this contract as a target role member)* | **Rewrite (new)** | A standard `TWO_PHASE_DP` closure to be authored fresh against this contract; no legacy implementation to port. |

> Note: the user brief names **Friedel**; the legacy tree contains **MSH / Kim-Mudawar / mixture-factor**, not Friedel. Friedel is therefore a *new* catalogue entry to author under this contract, not a migration.

### 11.2 Single-phase pressure-drop implementations

| Asset | Source | Verdict | Migration |
|---|---|---|---|
| **Churchill** single-phase friction | PyP2PL `dp_twophase.py`; MPL `correlations.py` | **Adapt** | Clean; port as `SINGLE_PHASE_DP`. |
| **Blasius** | MPL `correlations.py`; A0 | **Adapt** | Port as `SINGLE_PHASE_DP` with a turbulent-Re envelope. |
| **Plate ΔP** | PyP2PL `dp_plate.py` | **Adapt** | Port as a plate-geometry `SINGLE_PHASE_DP`/`TWO_PHASE_DP` (chevron-angle scalar in input). |
| Acceleration / gravity gradient helpers | MPL `correlations.py` (`acceleration_pressure_gradient`, `gravity_pressure_gradient`) | **Adapt → Component** | These are **not correlations** — they are the Component's gravity/acceleration gradient terms (§3.1, MASTER §12.3). Re-house in the 1D-passage kernel, not the registry. |

### 11.3 Heat-transfer-coefficient implementations

| Asset | Source | Verdict | Migration |
|---|---|---|---|
| **Shah** (boiling) | MPL `correlations.py`; PyP2PL `htc_boiling.py` | **Adapt** | Port as an `HTC` closure; declare its quality/Re/reduced-pressure envelope. |
| **Chen, Bennett-Chen, Gungor-Winterton, Kandlikar-Balasubramanian** (boiling) | PyP2PL `htc_boiling.py` | **Adapt** | Five Kokate-referenced boiling closures; **purge the `_fluid_name` global, the `hasattr` introspection, and the hard-coded `M = 102.0`** (ARCHITECTURE_REVIEW_LEGACY §4.2) — the fluid constant must come through `FluidState`/inputs. |
| **Kim-Mudawar 2012** (boiling HTC) | MPL `correlations.py` | **Adapt** | Microchannel boiling HTC; microchannel envelope. |
| **Nucleate+convective ΔT fixed-point** | A0 `alpha_boiling` | **Adapt** | Valuable wall-superheat closure not present elsewhere; re-house as an `HTC` closure consuming `q_flux`/`T_wall` as inputs (never reaching into component state). |
| **Condensation HTC** — Shah-1979/2021, Chen-style (E/S), Yan | A0 `alpha_condensation`; MPL `correlations.py` | **Adapt** | Port as `HTC` (condensation regime) closures. |
| **Dittus-Boelter, Gnielinski, Shah-London laminar** (single-phase HTC) | MPL `correlations.py` | **Adapt** | Port as single-phase `HTC` closures. |

### 11.4 Void-fraction implementations

| Asset | Source | Verdict | Migration |
|---|---|---|---|
| **Homogeneous void fraction** (`void_fraction`, `rho_mixture`, `actual_quality` with [0,1] clamp, `homogeneous_velocity`) | A0 HEM closures | **Adapt** | Port the homogeneous `VOID_FRACTION` closure; the `[0,1]` clamp on *quality* is a physical-bound check, not a silent value clamp (§6.4 distinction). |
| Drift-flux / Zivi / Rouhani-Axelsson | *(not in legacy)* | **Rewrite (new)** | Author fresh as `VOID_FRACTION` members when needed; no legacy port. |

### 11.5 Flow-regime maps

- **No flow-regime map exists in legacy.** The `FLOW_REGIME` role is **new** (§3.6); any map is authored fresh under this contract, with the continuity caution of §6.5. A0's implicit regime weighting inside `alpha_boiling` (the microconvective shape factor `S(x)`) is **Adapt-as-part-of-the-HTC-closure**, not a standalone regime map.

### 11.6 Accumulator pressure laws

| Asset | Source | Verdict | Migration |
|---|---|---|---|
| **HCA + PCA** behind one `set_pressure()` / volume↔pressure interface (`dP_dT`, `effective_compressibility`, `fluid_inventory`, named `V_g`/`V_l`) | MPL `accumulator.py` | **Adapt** | Re-house as two `VOLUME_PRESSURE_LAW` closures (§9); **move charge volume / heater duty out of geometry into `law_params`/`thermal`**; the frozen `V_g` state carries into Phase 6 unchanged. |
| Bellows / spring-loaded / gas-charged | *(not in legacy)* | **Rewrite (new)** | Author fresh as `VOLUME_PRESSURE_LAW` members; interchangeable by binding. |

### 11.7 Property-derived helpers (NOT correlations)

The single most important migration boundary: **property helpers are PropertyBackend material, never correlations** (§1.2, `[F6]`).

| Asset | Source | Verdict | Migration |
|---|---|---|---|
| `FluidState` (P,h) + CoolProp→empirical→table fallback chain + source tracking | MPL `fluid_properties.py` | **Adapt → PropertyBackend** | Split into a lazy `FluidState` value object + `PropertyBackend` implementations. **Not** a correlation; not in the correlation registry. |
| Empirical property correlations — **Letsou-Stiel** (μ), **Latini** (k), **Brock-Bird** (σ) | MPL `fluid_properties.py` | **Adapt → `EmpiricalCorrelationBackend`** | These are *property* correlations (Layer 1), housed in a PropertyBackend, **never** in the Layer-3 correlation registry — the explicit guard against the DAG cycle (§1.3, anti-pattern §13). |
| `A1_TwoPhProp` tabulated loader (σ_e, ε_r — table-only) | A0 + MPL (identical) | **Adapt → `TabulatedPropertyBackend`** | The only source of electrical conductivity / relative permittivity; PropertyBackend, not correlation. (29 CSVs missing — a data task, ARCHITECTURE_REVIEW_LEGACY §6.3.) |
| A0 `EOS_liq/vap_properties` | A0 | **Discard** | Superseded by the MPL fallback chain. |
| PyP2PL T-anchored `FluidProperties`/`SatState` | PyP2PL `fluid/fluid.py` | **Discard** (keep `SatState` field list as a “what a closure needs” checklist) | Violates Decision 001; the field list is a useful manifest for designing `HTCInput`/`TwoPhaseDPInput`. |

### 11.8 Migration summary

The closure harvest order (within the broader §8 harvest of ARCHITECTURE_REVIEW_LEGACY): **MPL `correlations.py` first** (richest, most contract-aligned — Adapt wholesale, add envelopes, tighten to role-typed inputs), then **PyP2PL's five boiling correlations** (Adapt, purge globals/hacks), then **A0's `alpha_boiling`/`alpha_condensation`/mixture-friction** (Adapt the equations out of the global-array housing). Friedel, drift-flux void models, flow-regime maps, and bellows/spring laws are **new** entries authored against this contract.

---

## 12. Scientific Reproducibility

A closure result is only scientifically meaningful if it is reproducible. The framework therefore **records, for every closure call that contributes to a Result, the information needed to reproduce that number exactly.** This is the closure-level expression of the Reproducibility Tuple principle (`[F1]` Principle 7).

### 12.1 What must always be recorded

For every closure bound to a slot, the following are recorded — in the tuple (as the binding) and surfaced into the Result (as provenance):

- **Model name** — the canonical registered name (not an alias, §8.4).
- **Version** — the correlation/model version string (§8.3); for ML closures, the model+architecture version (§10.4).
- **Source** — the citation / DOI / reference establishing the closure and its envelope (`SourceRef`); for ML closures, additionally the training-dataset reference (§10.4).
- **Calibration** — the calibration factor applied at this closure's seam (target, value, mode, seam location), via the Result's `CalibrationReport` (§7.5). A `NONE`/neutral seam is recorded as such.
- **Validity status** — the per-call `ValidityVerdict` (status + violated bounds + envelope reference) for any non-`IN_ENVELOPE` call, via `Result.validity_warnings` (§5.4, §6.4).

### 12.2 The reproducibility guarantee

Given a Result and its tuple, a reader — years later — can determine **exactly which closure, at which version, from which source, under which calibration, evaluated within or outside which envelope** produced every constitutive number in the solution. This is the longevity property: the closures change, the *record format* does not.

- A Result that omits closure metadata, the calibration report, or out-of-envelope verdicts is **malformed** (INTERFACE_SPEC §14, Rule 5).
- A `TARGET`-calibrated Result is flagged `CALIBRATED` and never compared as-equal to a `PREDICTIVE` (`NONE`) Result (§7.2).
- An ML-closure Result without a training-dataset reference is non-reproducible and therefore inadmissible (§10.4).

---

## 13. Correlation Anti-Patterns

Each anti-pattern is tied to the guard that forbids it. These are the code-review checklist for closures, specializing MASTER §19 and INTERFACE_SPEC §16.

1. **Hidden calibration** — a fudge factor baked into a formula (`× 1.15` inside the equation). *Guard:* correlations are pure; calibration is an external value object at the documented seam, friction-gradient/HTC/UA only, always reported (§7).
2. **Geometry-specific / type-aware closures** — a correlation that receives a `MicrochannelGeometry`, asks `isinstance(geom, ...)`, or hard-codes a passage assumption. *Guard:* role-typed input carries *declared scalars only*; never a Geometry object (§4).
3. **Solver-aware correlations** — a closure that knows it is being finite-differenced, picks a step, assumes a scheme, or stores a Jacobian assumption. *Guard:* nothing depends on the Solver; differentiable-in-practice, scheme-agnostic (§2.5).
4. **Stateful correlations** — instance caching (`_last_dP`, `_mu_v_store`), module-level globals (`_fluid_name`), `hasattr` self-introspection, run-on-import. *Guard:* stateless, pure, equal-inputs-equal-outputs (§2.3, §8.1).
5. **Topology-aware correlations** — “am I in an evaporator?”, reading a neighbouring branch's flow. *Guard:* self-contained input; branch/loop/inventory are Network conditions (§2.4).
6. **Hard-coded fluid constants** — `M = 102.0` for R-134a with “the component will override it”. *Guard:* fluid data arrives through `FluidState`/inputs; fluid restriction is declared in the envelope (§4, §6.2). (Legacy PyP2PL violation.)
7. **Property lookup masquerading as a correlation** — putting CoolProp, or an empirical μ/k/σ correlation, into the correlation registry. *Guard:* properties are Layer-1 PropertyBackend material in a separate registry; the DAG-cycle guard (§1.3, §11.7).
8. **ε-NTU / LMTD as a correlation** — a heat-exchanger solution strategy in the correlation role set. *Guard:* `HeatExchangerModel` is a separate concept with its own registry (§3, INTERFACE_SPEC §8).
9. **Returning a bare number** — a closure that returns a value without a `ValidityVerdict`. *Guard:* the output always carries a verdict and metadata (§5, Rule 5).
10. **Silent clamping / stealth extrapolation** — snapping an out-of-range input back to the envelope edge, or returning a fabricated in-range value. *Guard:* warn-on-extrapolation, never clamp; honest extrapolated value flagged `EXTRAPOLATED`, hard failure → `NaN` flagged `OUT_OF_RANGE` (§5.6, §6.4).
11. **Returning a total instead of a gradient** — a DP closure that integrates over the cell and returns total ΔP. *Guard:* DP closures return per-cell *gradients*; integration is the Component's (`[F14]`, §3.1–§3.2, §5.2).
12. **Bundling gravity/acceleration into the friction closure** — a `TWO_PHASE_DP` return that includes the hydrostatic or acceleration term. *Guard:* friction only; gravity/acceleration are Component terms and are never calibrated (§3.2, §7.3).
13. **Calibrating the wrong target** — an `R*` on gravity, or a multiplier on void fraction / flow regime / pressure law. *Guard:* calibration targets are exactly `FRICTION_GRADIENT`/`HTC`/`UA` (§7.3).
14. **Mid-domain hard cut-off** — a closure returning `NaN` at an envelope edge where the physics is still defined, breaking solver continuity. *Guard:* envelope checking *reports*, it does not *branch*; continuous value past the edge, flagged (§6.5).
15. **Accumulator law parameters in geometry** — `V_gas_charge`/spring rate/bellows area stored in `AccumulatorGeometry`. *Guard:* geometry is containment only; law parameters are `law_params`/`thermal` inputs (§9.3).
16. **ML closure without a declared training-domain envelope** — a surrogate that extrapolates silently. *Guard:* envelope = training domain; traceability mandatory; inadmissible otherwise (§10.2, §10.4).
17. **Regime branch welded into a component** — `if regime == annular: shah()` inside component code. *Guard:* regime is a closure verdict consumed *by a regime-aware correlation*, never a component branch (§3.6).

---

## 14. Readiness for Implementation

### 14.1 Verdict

**The correlation/closure architecture is mature enough to implement the Phase-1–4 closure layer.** The contract is fully specified:

- the `evaluate(CorrelationInput) → CorrelationOutput` signature is frozen (`[F11]`, §1, §5);
- the role set, the per-role input manifests, the output shape, the validity-envelope format, and the `ValidityVerdict` semantics are specified here (§3–§6);
- calibration interaction, registry behaviour, accumulator-law treatment, and the ML-closure contract are specified (§7–§10);
- the legacy migration is classified per closure (§11);
- the reproducibility record is defined (§12).

A researcher can author a conforming correlation, and a reviewer can reject a non-conforming one, from this document plus `INTERFACE_SPEC.md` §7–§9.

### 14.2 Remaining blockers (all data/specification tasks, none architectural)

1. **Per-correlation envelope data must be sourced.** Each ported/authored closure needs its `ValidityEnvelope` bounds populated from its citation (§6.2). This is a literature task per correlation, not an architecture task — but a closure registered without an envelope is inadmissible (§6), so this gates *catalogue completeness*, not the *contract*.
2. **The 29 tabulated property CSVs are missing** (ARCHITECTURE_REVIEW_LEGACY §6.3). This blocks the `TabulatedPropertyBackend` (σ_e, ε_r), not the correlation layer — but any closure that someday consumes σ_e/ε_r cannot be validated until the data is recovered. A data task, flagged here for traceability.
3. **`CRITICAL_HEAT_FLUX` and `CUSTOM_CLOSURE` are declared seams, not built** (§3.7, §3.9). No v1 component declares a CHF slot; the role exists so its later addition is additive. No blocker for v1.
4. **`FLOW_REGIME` continuity convention** (§6.5) needs a concrete blending specification *per regime map* when the first regime-aware closure is authored. The *contract* (continuous transition coords, no hard branch) is fixed; the per-map blending is a closure-authoring detail, deferred to first use.
5. **Secondary-side HTC for heat exchangers** (`htc_secondary` in `HXSolveRequest`, INTERFACE_SPEC §8.1) is an optional slot; whether v1 condenser modelling needs it is a `HeatExchangerModel`-level decision, not a correlation-contract gap.

None of these reopen a frozen decision; none change a signature marked `<<FROZEN>>`. They are catalogue-population and data-recovery tasks that proceed in parallel with implementation.

### 14.3 Expected longevity

This specification is written to outlive its catalogue. The frozen surface — the `evaluate` contract, the role set, the input manifests, the output/verdict shape, the envelope format, the calibration seam, the reproducibility record — is independent of *which* Shah, Friedel, or surrogate is in the registry on any given day. Individual correlations will come and go; the contract they satisfy is designed to remain valid across the full 5–10-year horizon (MASTER §1, intro).

---

*End of CORRELATION_CONTRACT.md — the scientific closure-model specification for the MPL simulation framework. Subordinate to ARCHITECTURE_MASTER.md and INTERFACE_SPEC.md; frozen contracts are tagged `<<FROZEN>>`, future seams `<<SEAM>>`. This document owns the per-role CorrelationInput field manifests, the validity-envelope declaration format, and the ValidityVerdict semantics that INTERFACE_SPEC §7 defers to it. Companion documents: SCHEMA_SPEC.md, TEST_PLAN_V1.md.*
