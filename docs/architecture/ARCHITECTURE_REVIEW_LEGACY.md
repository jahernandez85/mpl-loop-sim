# ARCHITECTURE_REVIEW_LEGACY.md

**Audit of the legacy implementations against the approved architecture (Levels 1–3)**

Status: review only — no code written, no files refactored, no repository state changed.
Inputs: `ARCHITECTURE_LEVEL_1.md`, `ARCHITECTURE_LEVEL_2.md`, `ARCHITECTURE_LEVEL_3.md` (treated as binding), and `legacy/` (`A0_SS_v3_Stable/`, `PyP2PL/`, `MPL_Simulator/`).
Author: architecture review pass, 2026-06-10.

---

## 0. How to read this document

The approved architecture is fixed. Legacy code is judged **only** by what it can contribute to that architecture, using four verdicts:

| Verdict | Meaning |
|---|---|
| **Reuse** | Can be lifted into `src/` with cosmetic change only (rename, import path). Rare — almost nothing legacy is dependency-clean enough. |
| **Adapt** | The *physics/algorithm* is sound and worth porting, but it must be re-housed behind an approved interface (Correlation, PropertyBackend, Component contract) before it touches `src/`. This is where most legacy value lives. |
| **Rewrite** | The *idea* is needed by the roadmap but the implementation violates the DAG/ownership rules so deeply that re-typing from the architecture is cheaper and safer than porting. |
| **Discard** | No architectural value, or actively dangerous to copy (global state, import-time execution, hidden fudge factors). |

The decisive test throughout is the Level 2 dependency DAG:
`Geometry/PropertyBackend → FluidState → Port → Correlation → Component → Network → Solver`, with **nothing depending on the Solver** and **only P, h, ṁ stored**.

---

## 1. Executive summary

Three legacy attempts exist, at three different maturity levels, and they are **complementary, not redundant**:

- **`A0_SS_v3_Stable`** — a monolithic 1-D axial-marching steady-state solver. **Architecturally unusable** (module-level globals, executes on import, hard-wired everything), but it is the **richest source of validated physics and numerics**: HEM closures, the friction-factor mixture model, the nucleate+convective boiling ΔT fixed-point, the `R*` per-region pressure-drop calibration, axial marching with a two-pass momentum corrector, and embedded Fujii (2004) validation data. **Verdict: Discard the structure; Adapt the equations and the calibration concept; preserve the validation cases.**

- **`PyP2PL`** — the most complete *component-based* attempt and the **best validation asset** (Kokate 2024 R-134a digitised data + MAE machinery + four worked example sweeps). Its component/port vocabulary is close to the target, but its FluidState is T-anchored (not P–h), its correlations are organism-specific function families, and its "solver" is an explicit Kokate control-law march with **no real loop closure**. **Verdict: Adapt the correlations and validation; Rewrite the solver and FluidState; keep the component decomposition as a reference, not as code.**

- **`MPL_Simulator`** — by far the **most architecturally aligned** layer. Its `FluidState` is already **(P, h)-anchored** (matches Decision 001), it already has a **CoolProp + tabulated-table + empirical fallback chain** behind one state object (matches Decision 003), its `correlations.py` already uses a **Protocol-based strategy pattern with name registries** (matches the Correlation Registry of L3 §7), its accumulator already exposes **HCA and PCA behind one `set_pressure()`/volume↔pressure interface** (matches L1 §6), and its loop already does a **simultaneous Newton solve (scipy `fsolve`) on (ṁ, P_sys)** (matches L1 §7 / L2 §9-C). **Verdict: this is the primary harvest target — Adapt aggressively, Rewrite the ownership leaks.**

**The single most strategically reusable asset** is the fluid-property fallback chain in `MPL_Simulator/mpl/fluid_properties.py` together with the `A1_TwoPhProp` tabulated-table mechanism — specifically because it supplies **electrical conductivity and relative permittivity, which CoolProp does not expose at all**. If MPL ever needs dielectric/EHD-relevant properties, this table path is the *only* legacy source for them and should be preserved as a `PropertyBackend` implementation.

> **⚠ Critical data-availability finding.** The CSV property tables the table loader expects (`R134A.csv`, `AMMONIA.csv`, … 29 files) **are not present anywhere in `legacy/`.** Only the *loader code* survives. The sole CSVs in the tree are `PyP2PL/examples/*.csv`, which are simulation **outputs (sweep results)**, not property tables. The tabulated-property capability is therefore **latent**: the extraction logic is reusable, but the actual tables must be located/regenerated before that backend can do anything. See §6.

---

## 2. Project-level classification map

| Legacy element | Verdict | One-line reason |
|---|---|---|
| **A0_SS_v3_Stable** | | |
| `A0_SS_v3_Stable.py` — module structure / globals / run-on-import | **Discard** | Module-level mutable arrays + executes a full sim + plots on import. Cannot enter `src/`. |
| `governing_mass/momentum/energy` | **Adapt** | Correct HEM balances; re-house as Component residual contributions. |
| HEM closures (`void_fraction`, `rho_mixture`, `actual_quality`, `homogeneous_velocity`, mixture `friction_factor`) | **Adapt** | Sound, swap-in physics; become Correlation/FluidState internals. |
| `alpha_boiling` (nucleate+convective ΔT fixed-point) | **Adapt** | Valuable wall-superheat closure; re-house as a boiling-HTC Correlation. |
| `alpha_condensation` (Chen / Shah-1979) | **Adapt** | Becomes condensation-HTC Correlations (registry entries). |
| `solve_R_for_region` / `calibrate_R_stars` (R* bisection) | **Adapt → Rewrite** | The R\* concept = the architecture's calibration seam; the *bisection-on-globals* implementation is rewritten. |
| Two-pass momentum corrector in `function_conservation` | **Adapt** | Good numerical pattern for the segmented passage; re-house in the Solver. |
| `EOS_liq_properties`/`EOS_vap_properties` (try-CoolProp-then-table) | **Discard** (superseded) | MPL's `FluidState` does this better and cleaner. |
| Fujii (2004) embedded validation data (annex comments) | **Reuse** (as data) | Lift the numbers into a validation fixture; do not lift the code. |
| Inline `plot_profile`, matplotlib calls | **Discard** | Presentation; belongs to a results/plotting utility, not physics. |
| **PyP2PL** | | |
| `components/base.py` (`PortState`, `ComponentResult`, `BaseComponent`) | **Rewrite** | Right idea (P,h,ṁ port + compute contract + `time_derivatives` stub) but no internal-state names, derived props recomputed ad hoc, fluid backend per-component. |
| `system/node.py` (derived props on demand) | **Adapt** | Correctly *derives* T/x/ρ from (P,h) — matches ownership rule; becomes a thin view over FluidState. |
| `system/solver.py` (Kokate explicit control law) | **Discard** (as a solver) / **Reuse** (as a scenario closure) | Not a loop solver — it hard-codes Kokate's `m_dot=χ·q/h_fg` and never closes pressure. Keep the *formula* as a documented special case only. |
| `system/loop.py` (march + sweep) | **Rewrite** | Topology = an ordered Python list; closure = "last node P ≈ P_sys". No Network concept. |
| `correlations/htc_boiling.py` (Shah/Chen/Bennett-Chen/Gungor-Winterton/Kandlikar) | **Adapt** | Five real boiling correlations; port each as a registry Correlation. Remove the `_fluid_name` global hack and `hasattr` self-introspection. |
| `correlations/dp_twophase.py` (MSH + acceleration, Churchill) | **Adapt** | Clean MSH + homogeneous-acceleration; near-ready as Correlations. |
| `correlations/dp_plate.py`, `dp_singlephase.py` | **Adapt** | Plate and single-phase ΔP; registry Correlations. |
| `components/*` (pump, preheater, evaporator, condenser, reservoir, accumulator, pipe) | **Rewrite** (keep as reference) | Good physical decomposition and per-channel/segment integration logic; but each holds its own `FluidProperties`, embeds correlation choice, mixes calibration-free physics. Re-derive against the Component contract. |
| `utils/validation.py` (Kokate digitised data + MAE Eq.17) | **Reuse** (data) / **Adapt** (MAE) | Embedded Kokate 2024 tables + MAE are gold for the validation harness. |
| `examples/01–04` + `examples/*.csv/*.png` | **Reuse** (as scenarios/reference outputs) | Worked DOE sweeps map directly to Phase-5 Scenario examples. |
| `utils/parametric.py`, `utils/plotting.py` | **Adapt** | Sweep/plot helpers; rehome under results tooling, not physics. |
| **MPL_Simulator** | | |
| `mpl/fluid_properties.py` (`FluidState` (P,h) + fallback chain + electrical/dielectric) | **Adapt** | Closest thing to the target FluidState + PropertyBackend; split the two layers, make it lazy, strip eager electrical computation from hot path. |
| `mpl/A1_TwoPhProp.py` (CSV table loader, sat interpolation) | **Adapt** | Becomes a `TabulatedPropertyBackend`; **the only source of σ_e and ε_r**. (Tables themselves missing — see §6.) |
| `mpl/correlations.py` (Protocol HTC/DP + `get_htc_correlation`/`get_dp_correlation` registries; Shah, Kim-Mudawar 2012/2013, Yan, MSH, Churchill, Homogeneous, accel/gravity gradients) | **Adapt** | The richest, most architecture-aligned correlation library. Port wholesale into the Correlation Registry; adjust the call signature to `(FluidState, declared scalars) → (value, validity verdict)`. |
| `mpl/accumulator.py` (`AccumulatorHCA` + `AccumulatorPCA`, `set_pressure`, volume↔pressure, `dP_dT`, `effective_compressibility`, `fluid_inventory`) | **Adapt** | Already realises the generic volume↔pressure law and names the frozen dynamic states (V_g, V_l). Re-house as the Accumulator's volume↔pressure Correlation slot + Component. |
| `mpl/condenser.py` (ε-NTU node march, desuperheat/condensation/subcooling zones, counter-flow two-pass) | **Adapt** | Strong condenser physics and a near-moving-boundary zone structure; re-house behind the Component contract with a selectable heat-exchange-method slot. |
| `mpl/base.py` (`Port` holds a `FluidState`; `Component` ABC; `Orientation`) | **Rewrite** | Port stores a *state object that caches derived T/ρ/x* → two-sources-of-truth risk. Contract lacks internal-state names / Discretization / residual form. |
| `mpl/loop.py` (`LoopSolver` Newton on (ṁ, P_sys) via `fsolve`; `LoopResult`; `build_standard_loop`) | **Adapt → Rewrite** | The *numerical strategy* (simultaneous Newton, two residuals) is exactly what L1 §7 / L2 §9-C want; but it imports components flatly, hard-codes single-loop topology, and the accumulator is a side protocol, not a Network reference node. |
| `mpl/pipe.py`, `mpl/pump.py`, `mpl/evaporator.py` | **Rewrite** (keep as reference) | Same pattern as PyP2PL components; physics is fine, housing violates the contract. |
| `mpl/Simple_test_v1.py`, `.spyproject/`, `docs/*.docx` | **Discard** | Scratch/IDE/binary artefacts. |
| `tests/*` (both projects) | **Reuse** (as test oracles) | Component/correlation/property test values are reusable as regression fixtures against the new code. |

---

## 3. `A0_SS_v3_Stable` — detailed audit

### 3.1 Architectural concepts it already supports
- **Separation of governing vs. constitutive equations** (file sections 1 and 2): mass/momentum/energy balances are written separately from closures (friction, HTC, void). This is exactly the L1 §1.3 physics-vs-numerics split *in spirit*, even though it is implemented with globals.
- **(P, h)-style axial state propagation**: it marches enthalpy by energy balance and pressure by momentum balance, with density/quality derived locally — the same advect-h / close-on-P asymmetry the architecture formalises (L2 §4).
- **Pressure-drop decomposition** `ΔP = friction + hydrostatic + acceleration`, with only the friction term scaled by `R*` — this is **precisely** the calibration firewall of L1 §9 / L2 §7 (`ΔP_total = R*·ΔP_friction + ΔP_gravity + ΔP_acceleration`), discovered independently.
- **Segmented passage with per-region geometry** (variable `Ac`/`Pw` along the heater inlet/outlet tapers) — a concrete instance of the shared 1-D segmented-passage mechanism (L1 §3).

### 3.2 What violates the approved architecture
- **Module-level mutable global arrays** (`G_vec, h_vec, P_vec, T_vec, x_vec, …`) that every function reads and writes. This is the antithesis of single-source-of-truth and reproducibility (L1 §1.7, L2 §2). Functions like `alpha_boiling(i)` reach into globals by index.
- **Executes a full simulation, calibration and eight plots at import time.** The file *is* the run. There is no separation of library from script.
- **Solver/physics fully entangled**: `function_conservation` simultaneously computes properties, closures, momentum corrector, and writes results — Component, Correlation, and Solver responsibilities fused into one function (violates L2 §1, anti-pattern L3 §11.5/6).
- **Hard-wired everything**: fluid (`'R123'`), geometry, heat loads, region targets are module constants.
- **`R*` calibration by stateful bisection over globals** (`solve_R_for_region`): correct concept, but mutates `R_vec` and re-runs region functions that mutate globals — un-reproducible and un-testable.

### 3.3 Equations / correlations / validation worth preserving
- HEM relations: `void_fraction` (α homogeneous), `rho_mixture`, `actual_quality` with [0,1] clamping, `homogeneous_velocity`.
- **Mixture friction factor** `f_i = (1-ψ)(ρ_l/ρ)f_l + ψ(ρ_v/ρ)f_v` with Blasius single-phase `f = 0.079 Re^-0.25` — a documented two-phase friction model.
- **`alpha_boiling`**: convective (void-weighted Dittus-Boelter on liquid+vapor) **plus** a nucleate-boiling ΔT closure solved by damped fixed-point against the segment energy balance, with Tcrit-aware ΔT capping and a microconvective shape factor `S(x)`. This wall-superheat iteration is genuinely useful and not present in the other projects.
- **`alpha_condensation`**: Chen-style (enhancement E + suppression S) and Shah-1979/2021 (Froude-based enhancement) condensation HTCs.
- **Two-pass momentum corrector** (provisional → refresh) in `function_conservation` — a robust per-segment pressure update worth keeping as a numerical pattern.
- **Fujii et al. (2004) validation data** embedded as annex comments (High/Medium/Low cases: node pressures, temperatures, qualities, wall temperatures, and per-region ΔP targets). **This is a complete, citable validation case** and should be lifted into the validation harness.

### 3.4 Property-backend / tabulated data to extract
- `EOS_liq_properties`/`EOS_vap_properties` implement a try-CoolProp-then-`A1_TwoPhProp`-table fallback. The *fallback idea* is kept, but the **MPL_Simulator version supersedes it** (cleaner, (P,h)-based, with empirical correlations as a third tier). Extract nothing from A0's EOS layer except the confirmation that the table fallback is the intended design.

### 3.5 What should never be copied into `src/`
- Any module-level array, the run-on-import body (sections 6–9), the inline plotting, the hard-coded BCs, and `calibrate_R_stars`/`solve_R_for_region` as written (they depend on the global region-runner machinery).

### 3.6 Recommended migration path
1. Lift the **equations** (§3.3) into pure functions/closures with explicit arguments — no globals — as candidate Correlations and FluidState helpers.
2. Re-express `governing_*` as a Component **residual contribution** for the shared segmented passage; let the Solver own the marching/corrector.
3. Re-express `R*` as the architecture's **per-slot calibration factor on ΔP_friction** (L2 §7) — the concept is already correct; only the mechanism changes.
4. Move Fujii data into `tests/validation/` fixtures.
5. Discard the file as a runtime artefact.

---

## 4. `PyP2PL` — detailed audit

### 4.1 Architectural concepts it already supports
- **Physical-component vocabulary** (Pump, Preheater, MicrochannelEvaporator, FlatPlateCondenser, Reservoir, Accumulator, Pipe) — directly matches L1 §3 / L3 §4.
- **(P, h, ṁ) port** (`PortState`) passed between components — matches the Port interface (L1 §5).
- **Derived-on-demand properties** (`Node.T/x/rho/phase` computed from (P,h) via CoolProp, never stored) — matches the single-source-of-truth ownership rule (L2 §2.1). `node.py` is the cleanest expression of this rule in all of legacy.
- **A `compute(inlet) → ComponentResult` contract** plus a reserved `time_derivatives()` stub — anticipates the residual/derivative contract and the dynamic seam (L1 §10).
- **Correlations as standalone functions with a name dispatcher** (`compute_htc_boiling(correlation=...)`, `AVAILABLE_CORRELATIONS`) — a primitive Correlation Registry.
- **Segmented integration inside the evaporator** (`_integrate_htc`, `two_phase_pressure_drop` over `n_cv`) — the shared 1-D passage used by composition (L1 §3).

### 4.2 What violates the approved architecture
- **FluidState is T-anchored, not P–h.** `FluidProperties.state_TP` is primary; `state_PH` converts to T first; quality uses a `-1` sentinel for single-phase. This contradicts Decision 001 and L1 §4 (continuity across the dome, no region switching).
- **Each component constructs its own `FluidProperties(fluid)`** in `BaseComponent.__init__` and calls CoolProp directly — no shared PropertyBackend, defeating the swappability and Phase-5 surrogate path (L3 §2 PropertyBackend, L2 §10 perf bottleneck).
- **No Network.** Topology is an ordered Python list (`Loop(components=[...])`); "closure" is `abs(nodes[-1].P - P_sys)` measured, not enforced. Branches, one-reference invariant, and mass inventory are absent (violates L1 §7, L2 §8).
- **The "solver" is not a solver.** `solve_steady_state` computes `m_dot = chi_d · q_total / h_fg` and `P_sys = P_sat(T_coolant + ΔT_approach)` in closed form, then marches **once**. It is a *Kokate-specific scenario closure*, declared "always converges". It cannot represent pressure-driven flow, Ledinegg behaviour, or any loop whose flow is not set by the control law (violates L1 §7).
- **Reservoir sets the reference pressure** (`set_reference_pressure`) — the architecture assigns the single pressure reference to the **Accumulator**, with the Reservoir holding inventory and setting *no* reference (L2 §8, L3 §4). Ownership is misassigned.
- **Correlation impurity / hacks**: `htc_boiling.chen` uses a module-level mutable `_fluid_name` list and `hasattr(chen, '_mu_v_store')` self-introspection; `gungor_winterton` hard-codes `M = 102.0` (R-134a) with a comment that the component "will override" it — leakage that breaks fluid-agnosticism.
- **Calibration absent.** There is no `R*`/HTC multiplier seam at all; physics is raw. (Predictive baseline only — acceptable as `none`, but the seam must be added.)

### 4.3 Equations / correlations / validation worth preserving
- **Five boiling HTC correlations** (Shah-1982, Chen-1966, Bennett-Chen-1980, Gungor-Winterton-1986, Kandlikar-Balasubramanian-2004), all referenced to Kokate (2024) Table 3 / Eqs. 18–24. These are high-value, directly portable as registry Correlations.
- **Müller-Steinhagen-Heck** two-phase frictional gradient + **homogeneous acceleration** gradient + **Churchill** single-phase friction (`dp_twophase.py`) — clean, well-documented, and Kokate-aligned.
- **Plate and single-phase ΔP** (`dp_plate.py`, `dp_singlephase.py`).
- **The MicrochannelEvaporator integration recipe**: per-channel mass flux, linear-quality segmentation, local HTC → `T_wall = T_sat + q''/α`, average/max wall temperature — a reusable algorithm for the segmented evaporator Component.
- **Validation gold (`utils/validation.py`)**: digitised Kokate (2024) HTC-vs-q″, ΔP-vs-q″, HTC-vs-G tables; Kokate (2023) Table 5 system baseline; and **MAE per Eq. 17** — exactly the Phase-1 literature target named in L3 §12.4.
- **Four worked example sweeps** (`examples/01–04` + their `.csv`/`.png`) — ready-made Phase-5 Scenario examples and reference outputs (charge ratio, coolant temp, heat flux, 2-D q×T_cool, fluid comparison).

### 4.4 Property-backend / tabulated data to extract
- Nothing reusable as a *backend* (it is a thin CoolProp wrapper, T-anchored). The `SatState` field list (the full set of saturation anchors a correlation needs: ρ_l/v, h_l/v, cp, μ, k, Pr, h_fg, σ) is a useful **checklist** for what the new FluidState must expose to correlations — keep it as a reference, not as code.
- The `examples/*.csv` are **outputs**, not property tables — do not mistake them for tabulated properties.

### 4.5 What should never be copied into `src/`
- `solve_steady_state`/`march_loop` as the solver; the T-anchored `FluidProperties`/`FluidState`; the `_fluid_name`/`hasattr` correlation hacks; the hard-coded `M=102.0`; the Reservoir-as-reference logic; per-component CoolProp construction.

### 4.6 Recommended migration path
1. **Port the correlations first** (§4.3) into the Correlation Registry with the `(FluidState, declared scalars) → (value, verdict)` signature; strip globals/hacks; add validity envelopes.
2. **Lift the validation data and MAE** into the Phase-1 test harness as the Kokate R-134a literature target.
3. Keep the **component decomposition and the evaporator integration recipe as design references**; re-implement each component against the real Component contract (internal-state names, Discretization, calibration slots).
4. Treat the examples as the first Scenario/Result fixtures.
5. Discard the solver and FluidState entirely (MPL provides better).

---

## 5. `MPL_Simulator` — detailed audit (primary harvest target)

### 5.1 Architectural concepts it already supports
This project independently converged on much of the approved architecture:

- **(P, h)-anchored FluidState** (`from_Ph` is the canonical constructor; T/x/ρ/phase all derived; `from_PT`/`from_Px`/`from_Tsat` convert *to* (P,h) on entry) — matches L1 §4 and **Decision 001** exactly.
- **PropertyBackend-style fallback chain behind FluidState**: CoolProp `AbstractState` primary → empirical correlations (Letsou-Stiel μ, Latini k, Brock-Bird σ) → `A1_TwoPhProp` CSV tables, with **per-property source tracking** (`_prop_sources`) — matches L1 §8 (property model as a swappable family) and **Decision 003** (FluidState must not depend directly on CoolProp; queries a backend).
- **Correlation strategy pattern + name registries**: `HTCCorrelation`/`DPCorrelation` `Protocol`s and `get_htc_correlation(name)`/`get_dp_correlation(name)` — a direct realisation of the Correlation Registry (L3 §7) and the "select by name" seam (L1 §8).
- **Components accept correlations as injected callables** (strategy pattern in `base.py` docstring) rather than hard-coding them — matches the slot model (L1 §8, anti-pattern L3 §11.6 avoided).
- **Accumulator HCA and PCA behind one interface** (`set_pressure()`), each implementing a volume↔pressure law, with `dP_dT`, `effective_compressibility`, `fluid_inventory`, and named gas/liquid volumes — matches the "generic volume↔pressure law slot, PCA/HCA interchangeable" of L1 §6 and the **frozen dynamic states** of L1 §10 / L2 §9.
- **Simultaneous Newton loop solve**: `LoopSolver` iterates `(ṁ, P_sys)` with `scipy.optimize.fsolve` on two residuals — `R1 = ΔP_pump − ΣΔP`, `R2 = P_sys − P_acc`. This is the simultaneous-Newton strategy L1 §7 offers and L2 §9-C asks to keep first-class.
- **ε-NTU condenser with moving-zone classification** (desuperheat / condensation / subcooling per node, counter-flow water, two-pass corrector) — close to the MovingBoundary seam (L2 §9-A) and uses ε-NTU as a selectable heat-exchange method (L3 §4 condenser).
- **Pressure-drop decomposition** with separate friction/acceleration/gravity gradients (`acceleration_pressure_gradient`, `gravity_pressure_gradient`) — supports the calibration firewall (scale friction only).

### 5.2 What violates the approved architecture
- **Two-sources-of-truth risk at the Port.** `base.py` `Port` holds a `FluidState` *object* that has T, ρ, x, and a large pile of transport/electrical fields computed and **stored** at construction. The architecture stores only P, h, ṁ and derives the rest *on demand* (L2 §2.1, anti-pattern L3 §11.4/11.11). The MPL FluidState is a cached bag of derived numbers — convenient, but it can drift and it is expensive.
- **Eager, expensive FluidState construction.** `__post_init__` → `_compute()` always builds two `AbstractState` objects, computes transport, *and* queries electrical/dielectric tables — on **every** state creation, including inside solver inner loops. This is the Phase-5 performance wall L2 §10 warns about, made worse by doing dielectric lookups nobody asked for.
- **FluidState mixes Layer-1 and Layer-3 concerns.** It reaches for empirical correlations (Letsou-Stiel/Latini/Brock-Bird) *inside* the state object. Per L2 §6/§10-#1 the **PropertyBackend is Layer 1** and must be cleanly separated from closure Correlations; here property *correlations* live inside FluidState. Acceptable as a backend internal, but must be re-housed as a `PropertyBackend` implementation, not as FluidState methods.
- **Flat imports and `sys.path` hacks.** `loop.py` does `from base import Component`, `from fluid_properties import FluidState`; `pyproject.toml` sets `pythonpath=["mpl"]`. No package namespacing — will not survive moving into `src/`.
- **Accumulator is not a Component** and exposes `set_pressure()` as a side `Protocol` the solver calls directly. The architecture makes the Accumulator a **first-class Component** whose pressure-setting law is a slot, with the *reference-node wiring* owned by the Network (L2 §8, L3 §4). MPL's solver reaches into the accumulator out-of-band.
- **Topology hard-coded to single loop.** `LoopSolver` assumes one pump, one ordered chain, one accumulator; `build_standard_loop` bakes the P&ID. No Network object, no branch/junction support, no one-reference *validation* (L1 §7, L2 §8, anti-pattern L3 §11.2).
- **Correlations receive the whole `state` object** (`__call__(self, state, G, D_h, …)`) rather than declared scalars + FluidState. Close to compliant, but L2 §6 wants declared scalars to avoid coupling to a state *type*; the signature should be tightened.
- **Component statelessness vs. cached `_last_dP/_last_Q`.** `base.py` caches last-solve results on the instance and offers `dP`/`Q` properties — a mild stateful wrinkle that the residual/derivative contract removes.

### 5.3 Equations / correlations / validation worth preserving
- **The entire `correlations.py` library**: `ShahBoilingHTC`, `KimMudawar2012HTC`, `YanCondensationHTC`, `DittusBoelterHTC`, `GnielinskiHTC`, `ShahLondonLaminarHTC`; `BlassiusDP`, `ChurchillDP`, `HomogeneousDP`, `KimMudawar2013DP`, `MullerSteinhagenHeckDP`; and the standalone `acceleration_pressure_gradient`/`gravity_pressure_gradient`. This is the broadest, best-structured correlation set in legacy and the closest to drop-in.
- **The fluid-property fallback chain** (CoolProp → empirical → tables) and its **source-tracking** — see §6; this is the strategic asset.
- **HCA/PCA accumulator laws** including polytropic gas (`gas_volume`, `effective_compressibility`) and saturation-thermal control (`set_pressure`, `dP_dT`), plus inventory accounting.
- **The ε-NTU condenser node march with zone classification and counter-flow two-pass corrector** — reusable as the condenser Component's segmented/ε-NTU mode.
- **The Newton residual formulation** `(R1 = ΔP_pump − ΣΔP, R2 = P_sys − P_acc)` — the correct steady-state residual shape; keep as the basis of the simultaneous Solver.
- **Li et al. (2021) Acetone validation** (`validation_li2021.py`): Mode A (evaporator component, fixed experimental ṁ, energy-balance check) and Mode B (loop, accumulator BC → T_sat) plus the embedded experimental dataset — a **second, non-Kokate, non-R134a validation case** (Acetone, the project's own candidate fluid). High value.
- **Test suites** (`tests/test_correlations.py`, `test_fluid_properties.py`, etc.) — reusable as regression oracles for the ported correlations/properties.

### 5.4 Property-backend / tabulated data to extract — see §6 (dedicated)

### 5.5 What should never be copied into `src/`
- The eager `FluidState._compute()` as the inner-loop property path; the Port-holds-stored-derived-state pattern; `from base import …` flat imports and `sys.path.insert` hacks; `build_standard_loop` hard-wired topology; the out-of-band `accumulator.set_pressure()` solver coupling; `.spyproject/`, `.docx`, `Simple_test_v1.py`.

### 5.6 Recommended migration path
1. **Split `fluid_properties.py` into two layers** (§6): a lazy `FluidState` value object (stores only fluid + P + h; derives on demand) and one or more `PropertyBackend` implementations (`CoolPropBackend`, `EmpiricalCorrelationBackend`, `TabulatedPropertyBackend`). This realises Decision 003 and removes the eager-compute / two-truths problems in one move.
2. **Port `correlations.py` into the Correlation Registry**, tightening the signature to `(FluidState, declared scalars) → (value, validity verdict)` and adding validity envelopes. This is the single highest-yield port in the whole legacy tree.
3. **Adopt the Newton residual formulation** as the simultaneous Solver, but read topology/closure from a real **Network** and make the Accumulator a Component whose reference role the Network wires.
4. **Re-house HCA/PCA** as the accumulator's volume↔pressure slot + Component; the frozen V_g/V_l states carry into Phase 6 unchanged.
5. **Re-house the condenser** behind the Component contract with `Segmented`/(declared) `MovingBoundary` Discretization and an ε-NTU heat-exchange-method slot.
6. Lift Li-2021 and the test values into the validation harness.

---

## 6. Fluid-property modules & tabulated data — strategic assessment

This is called out separately per the audit brief: property/backend logic and tabulated files may be **reusable even if the surrounding architecture is discarded.**

### 6.1 Inventory of fluid-property assets

| Asset | Location | Nature |
|---|---|---|
| `A1_TwoPhProp.py` (CSV loader + sat interpolation) | `A0_SS_v3_Stable/` **and** `MPL_Simulator/mpl/` (byte-identical) | Loads 29 fluid CSVs into `{fluid: {prop: array}}`; `np.interp` over saturation T/P; quality-weighted liquid↔vapour blending. |
| `MPL_Simulator/mpl/fluid_properties.py` | `MPL_Simulator/mpl/` | (P,h) `FluidState` + CoolProp→empirical→table fallback chain + electrical/dielectric + source tracking. |
| `PyP2PL/pyp2pl/fluid/fluid.py` | `PyP2PL/` | Thin T-anchored CoolProp wrapper (`FluidProperties`, `SatState`, `FluidState`). |
| The 29 CSV property tables themselves | **MISSING** | Referenced by name in `A1_TwoPhProp.py`; **not present anywhere in `legacy/`.** |

### 6.2 Why the tabulated path is strategically valuable
- **It supplies properties CoolProp does not have at all**: `EleConduc_liq/vap` (electrical conductivity) and `RelPermittivity_liq/vap` (relative permittivity). `fluid_properties.py` explicitly marks these as `_TABLE_ONLY_PROPS`. If MPL research ever touches dielectric heating, EHD effects, sensing, or any electrically-aware modelling, **this table mechanism is the only legacy source** for those numbers.
- **It covers 29 fluids**, far more than the 6 "supported" CoolProp fluids in the registry — useful as a breadth fallback and for fluids/mixtures CoolProp models poorly (the exact rationale in Decision 003).
- **It is already integrated as a fallback tier** with sensible behaviour (no extrapolation beyond table range; returns `None`/NaN rather than guessing; warns on table use).

### 6.3 The data-availability gap (must resolve before this backend is real)
- The loader expects 29 CSVs (`R134A.csv`, `AMMONIA.csv`, `WATER.csv`, … `NOVEC649.csv`, `R1336MZZZ.csv`) in `cwd`/`data/`/`tables/`. **None are in the repository.**
- The only CSVs present (`PyP2PL/examples/*.csv`) are **sweep outputs**, not property tables — they must not be confused with property data.
- **Action (data, not code):** locate the original 29 CSVs (author's machine / prior project), confirm their column schema matches the loader (`Temperature_sat`, `Pressure_sat`, `Density_liq/vap`, `Enthalpy_liq/vap`, `ViscosityDyn_*`, `ThConduc_*`, `Surface_tension`, `EleConduc_*`, `RelPermittivity_*`, …), version them, and store them under a `data/`/`tables/` directory inside the new package. Until then the `TabulatedPropertyBackend` is structurally portable but functionally empty.

### 6.4 Classification of the property assets

| Asset | Verdict | Migration |
|---|---|---|
| `MPL_Simulator/mpl/fluid_properties.py` — the `FluidState` (P,h) + fallback design | **Adapt** | Split into lazy `FluidState` (P,h only, derive on demand) + `PropertyBackend` implementations. Keep the fallback *priority logic* and the *source-tracking* idea verbatim. |
| Empirical correlations inside it (Letsou-Stiel, Latini, Brock-Bird) + `_FLUID_CONSTANTS` | **Adapt** | Move into an `EmpiricalCorrelationBackend` (Layer 1), not FluidState methods. |
| `A1_TwoPhProp.py` table loader + `interpolate_property`/`get_*` | **Adapt** | Becomes `TabulatedPropertyBackend`; keep lazy load, no-extrapolation, quality blend. Drop the print-based error handling for proper warnings/returns. |
| The CoolProp↔table name map (`_coolprop_to_table_key`, `SUPPORTED_FLUIDS`) | **Reuse** | Useful fluid-name normalisation table; lift as-is. |
| The 29 tabulated CSVs | **Reuse — once located** | Version and ship under the package; they are the only source of σ_e and ε_r. |
| `PyP2PL/.../fluid.py` (T-anchored wrapper) | **Discard** | Superseded; violates Decision 001. Keep `SatState`'s field list as a "what correlations need" checklist only. |
| `A0`'s `EOS_liq/vap_properties` | **Discard** | Superseded by the MPL fallback chain. |

---

## 7. Cross-cutting findings

### 7.1 Where legacy already agrees with the architecture (independent convergence — high confidence to adopt)
- **(P, h) state** — MPL FluidState and A0 marching both use it; ratifies Decision 001.
- **Property backend with table/empirical fallback** — MPL implements it; ratifies Decision 003.
- **Correlation-by-name registry + strategy injection** — MPL `correlations.py`; ratifies L1 §8 / L3 §7.
- **Friction-only ΔP calibration (`R*`)** — A0; ratifies the L1 §9 / L2 §7 calibration firewall.
- **HCA/PCA behind one pressure-setting interface** — MPL accumulator; ratifies L1 §6.
- **Simultaneous Newton on (ṁ, P_sys)** — MPL `LoopSolver`; ratifies L1 §7 / L2 §9-C.
- **Derived-on-demand port properties** — PyP2PL `node.py`; ratifies L2 §2.1.

These agreements are the strongest evidence the approved architecture is buildable; the corresponding legacy code should be the **first ported**, since it is closest to compliant.

### 7.2 Recurring violations to guard against during the port (legacy → `src/`)
1. **Stored derived state on Port/State objects** (MPL FluidState, PyP2PL FluidState fields) — the #1 silent-divergence trap (L3 §11.4/11.11). Enforce P,h,ṁ-only storage in code review.
2. **Per-component property-engine construction / direct CoolProp calls** (PyP2PL, A0) — defeats the single PropertyBackend and Phase-5 surrogate (L3 §11.9). Route all properties through one backend.
3. **Topology baked into the solver** (all three) — no Network, single-loop assumed (L3 §11.2). The new code must introduce the Network *before* the first multi-branch case.
4. **Solver reaching into components out-of-band** (MPL `accumulator.set_pressure()` from the solver) — the reference is a Network wiring fact (L2 §8).
5. **Correlations receiving whole component/state objects, or carrying globals/hacks** (PyP2PL `_fluid_name`, hard-coded `M`) — tighten to `(FluidState, declared scalars)` and purge globals (L3 §11.6).
6. **Run-on-import / module-level state** (A0) — never in `src/`.

### 7.3 Validation assets consolidated (lift all into the Phase-1 test harness)
- **Kokate (2024) R-134a**: HTC-vs-q″, ΔP-vs-q″, HTC-vs-G digitised tables + Table-5 system baseline + MAE Eq.17 (PyP2PL `validation.py`). → the L3 §12.4 named first end-to-end target.
- **Li et al. (2021) Acetone**: evaporator-component and loop-level cases + dataset (MPL `validation_li2021.py`). → a second fluid/source.
- **Fujii et al. (2004)**: High/Medium/Low node profiles + per-region ΔP (A0 annex). → a third, geometry-resolved case.
- **PyP2PL example sweeps** (charge ratio, coolant temp, heat flux, 2-D q×T_cool, fluid comparison) + their reference CSV/PNG outputs. → first Phase-5 Scenario/Result fixtures.

---

## 8. Consolidated recommendation & suggested harvest order

Build `src/` from the architecture, not from legacy — but **harvest in this order**, because each step lands on an approved seam and reuses the most-aligned legacy code first:

1. **FluidState + PropertyBackend split** (Adapt MPL `fluid_properties.py` + `A1_TwoPhProp.py`). Resolves Decisions 001/003; unblocks everything else. Locate the 29 CSVs in parallel (§6.3).
2. **Correlation Registry** (Adapt MPL `correlations.py`; then fold in PyP2PL's five boiling correlations and A0's `alpha_boiling`/`alpha_condensation` and mixture friction). Tighten signatures, add validity envelopes.
3. **Calibration seam** (Adapt A0's `R*` concept as the per-slot friction/HTC multiplier).
4. **Component contract + first components** (Rewrite from PyP2PL/MPL references: Pipe → Pump → Accumulator(HCA/PCA from MPL) → Evaporator(PyP2PL recipe) → Condenser(MPL ε-NTU)). Name internal states; attach Discretization.
5. **Network + simultaneous Solver** (Adapt MPL's Newton residual shape behind a real Network; Accumulator as reference node).
6. **Validation harness** (Reuse Kokate / Li-2021 / Fujii data + MAE) — wired in from commit one, per L1 §1.4.

Everything else in `legacy/` is **Discard** or reference-only.

---

## 9. Appendix — file-by-file verdict index

```
A0_SS_v3_Stable/
  A0_SS_v3_Stable.py ............. Discard (structure) / Adapt (eqs §3.3) / Reuse (Fujii data)
  A1_TwoPhProp.py ................ Adapt → TabulatedPropertyBackend (identical to MPL copy)

PyP2PL/
  pyp2pl/components/base.py ...... Rewrite (port+contract idea good; no states/backend)
  pyp2pl/components/{pump,preheater,evaporator,condenser,reservoir,accumulator,pipe}.py
                                   Rewrite (reference); evaporator integration recipe = Adapt
  pyp2pl/correlations/htc_boiling.py ...... Adapt (5 correlations; purge globals/hacks)
  pyp2pl/correlations/dp_twophase.py ...... Adapt (MSH + accel + Churchill)
  pyp2pl/correlations/dp_plate.py ......... Adapt
  pyp2pl/correlations/dp_singlephase.py ... Adapt
  pyp2pl/fluid/fluid.py .......... Discard (T-anchored; violates Decision 001)
  pyp2pl/system/node.py .......... Adapt (derived-on-demand = correct ownership)
  pyp2pl/system/solver.py ........ Discard as solver / Reuse Kokate formula as documented closure
  pyp2pl/system/loop.py .......... Rewrite (list ≠ Network)
  pyp2pl/system/results.py ....... Adapt (reference for Result object)
  pyp2pl/utils/validation.py ..... Reuse (Kokate data) / Adapt (MAE)
  pyp2pl/utils/{parametric,plotting}.py ... Adapt (results tooling)
  pyp2pl/tests/* ................. Reuse (regression oracles)
  examples/01-04 + *.csv/*.png ... Reuse (Scenario/Result fixtures; CSVs are OUTPUTS)

MPL_Simulator/
  mpl/fluid_properties.py ........ Adapt (split FluidState | PropertyBackend; make lazy)  ★ primary asset
  mpl/A1_TwoPhProp.py ............ Adapt → TabulatedPropertyBackend (σ_e, ε_r — table-only)  ★ strategic
  mpl/correlations.py ............ Adapt (Protocol+registry; richest set)                    ★ highest-yield port
  mpl/accumulator.py ............. Adapt (HCA+PCA volume↔pressure law; frozen V_g/V_l)
  mpl/condenser.py ............... Adapt (ε-NTU zones; near moving-boundary)
  mpl/base.py .................... Rewrite (Port stores derived state; contract lacks states/Discretization)
  mpl/loop.py .................... Adapt (Newton residual shape) → Rewrite (topology/imports/accumulator coupling)
  mpl/{pipe,pump,evaporator}.py .. Rewrite (reference)
  validation/validation_li2021.py  Reuse (Acetone case) / Adapt (harness)
  tests/* ........................ Reuse (regression oracles)
  mpl/Simple_test_v1.py, .spyproject/, docs/*.docx ... Discard

MISSING (must locate): the 29 fluid property CSVs referenced by A1_TwoPhProp.py.
```

---

*End of ARCHITECTURE_REVIEW_LEGACY.md — review only; no code was written, no files refactored, and the repository was not modified beyond creating this document.*
