# Block 15D-B Thermal Closure Primitives Audit

## Verdict

**APPROVED WITH MINOR FIXES.**

Block 15D-B correctly implements explicit, algebraic, property-free thermal
closure primitives and deterministic category-presence diagnostics. It adds no
property evaluation, thermodynamic conversion, real heat-exchanger prediction,
production component execution, state assembly, topology inference, or network
solve API.

## Git and scope

- Branch: `phase-15d-b-thermal-closure-primitives`
- Base commit: `77ac47ee6c5e328f8751dc816d4b7a54976e673d`
- HEAD before audit: `77ac47ee6c5e328f8751dc816d4b7a54976e673d`
- Base description: merged Block 15D-A
- Frozen architecture documents modified: none

Audited implementation files:

- `src/mpl_sim/network/thermal_closures.py`
- `src/mpl_sim/network/thermal_closure_diagnostics.py`
- `src/mpl_sim/network/__init__.py`
- `tests/network/test_thermal_closures.py`
- `tests/network/test_thermal_closure_diagnostics.py`
- `tests/network/test_thermal_closure_integration.py`
- `docs/roadmap/PROJECT_STATUS.md`

Audit-added file:

- `docs/validation/audits/BLOCK_15D_B_THERMAL_CLOSURE_PRIMITIVES_AUDIT.md`

## Public API added

- `ThermalClosureKind`
- `ThermalClosureDeclaration`
- `FixedHeatRateClosure`
- `ImposedEnthalpyClosure`
- `ImposedTemperatureLikeClosure`
- `SensibleHeatRateClosure`
- `EnthalpyFlowHeatRateClosure`
- `EffectivenessHeatRateClosure`
- `RecuperatorEnergyBalanceClosure`
- `ThermalClosureResidualSet`
- `build_thermal_closure_residuals`
- `ThermalClosureCategory`
- `ThermalClosureDiagnostic`
- `ThermalClosureDiagnosticResult`
- `evaluate_thermal_closure_sufficiency`
- `make_basic_thermal_loop_diagnostic`
- `make_recuperator_thermal_diagnostic`

## Checkpoint review

### 15D-B.1 — closure primitives

Approved. All seven closure declarations are frozen dataclasses with explicit
unknown and residual names. Structural scalar parameters reject bool,
non-numeric, NaN, and infinity values. Required unknown values receive the same
validation during evaluation.

`ThermalClosureResidualSet` preserves declaration order, rejects duplicate
residual names through its factory, evaluates every closure, ignores unrelated
extra unknowns as documented, returns a read-only residual map, and
defensively copies optional metadata.

### 15D-B.2 — diagnostics

Approved. The seven categories map narrowly to the seven closure kinds.
Evaluation is deterministic and reports required categories as provided or
missing with ordered human-readable messages.

`is_sufficient=True` means only that all categories required by the selected
targeted diagnostic are represented. It does not establish equation count,
symbolic rank, DAE solvability, arbitrary-network closure, or physical
predictiveness.

### 15D-B.3 — integration

Approved. Integration tests prove independent evaluation at known consistent
points, coexistence with Block 15D-A hydraulic closures, a preheater-like
fixed-duty/enthalpy-flow example, and a recuperator-like two-stream energy
balance. Perturbations produce nonzero residuals. No solve, property conversion,
HX model, or production component execution is performed or claimed.

## Closure equations and sign conventions

- Fixed heat rate: `r = q - q_fixed`. Positive fixed duty means heat added to
  the stream; negative values represent rejection.
- Imposed enthalpy: `r = h - h_imposed`. Both values are scalar algebraic data;
  no fluid identity, pressure, state object, or property backend is involved.
- Imposed temperature-like scalar:
  `r = theta - theta_imposed`. This is explicitly symbolic and user imposed,
  not a calculated thermodynamic temperature.
- Sensible heat rate:
  `r = q - mdot * cp * (theta_out - theta_in)`. `cp` is an explicit,
  caller-supplied positive finite scalar. Positive flow and positive
  temperature-like rise yield positive heat rate.
- Enthalpy-flow heat rate:
  `r = q - mdot * (h_out - h_in)`. Positive flow and enthalpy rise yield
  positive heat rate; enthalpy loss yields negative heat rate.
- Effectiveness:
  `r = q - effectiveness * q_max`, with explicit
  `0 <= effectiveness <= 1`. Both heat-rate values are caller-provided
  unknowns.
- Recuperator energy balance: `r = q_hot + q_cold`. The tested convention is
  `q_hot < 0` for heat given up and `q_cold > 0` for heat received.

## Scalar-only and property-free review

- Enthalpy closures use scalar unknowns only. They construct no `FluidState`,
  use no fluid identity, and perform no pressure/enthalpy lookup, phase,
  saturation, or quality operation.
- Temperature-like closures do not calculate temperature from enthalpy or
  enthalpy from temperature. The name and documentation consistently identify
  a symbolic scalar.
- Sensible heat uses only explicit caller-supplied `cp`; there is no automatic
  heat-capacity, density, viscosity, fluid, or phase lookup.
- Effectiveness does not calculate `C_min`, UA, NTU, or LMTD. The recuperator
  closure enforces energy consistency only and does not predict heat-transfer
  magnitude. Neither imports or calls an HX model.

## Diagnostics review

The diagnostic category set includes heat rate, enthalpy reference,
temperature-like reference, sensible heat relation, enthalpy-flow relation,
effectiveness relation, and recuperator energy balance.

The basic helper requires heat-rate and enthalpy-flow categories. The
recuperator helper requires recuperator energy balance and at least one
enthalpy-flow category, while explicitly warning that a fully closed
two-stream system normally needs more equations. Missing categories are clear
and deterministic.

## Validation results

The stale `.pytest_tmp` directory remained inaccessible to cleanup because of
an external Windows ACL artifact. Validation therefore used fresh,
repository-local `.pytest_audit_*` base-temp directories and disabled the
pytest cache provider. No product test failed or errored.

| Validation | Result |
|---|---:|
| `test_thermal_closures.py` | 128 passed |
| `test_thermal_closure_diagnostics.py` | 39 passed |
| `test_thermal_closure_integration.py` | 36 passed |
| New 15D-B tests total | 203 passed |
| 15D-A closure primitives | 122 passed |
| 15D-A diagnostics | 41 passed |
| 15D-A integration | 42 passed |
| 15D-A regression total | 205 passed |
| 15C-B residuals | 90 passed |
| 15C-B closeout | 62 passed |
| 15C-B regression total | 152 passed |
| Production contract inspection | 60 passed |
| Network suite | 2455 passed |
| Full suite | 6316 passed |
| Failed/errors | 0 |
| Skipped/xfailed/deselected | 0/0/0 |
| Six required examples | 6 passed |
| Ruff | clean |
| Black | clean; 212 files unchanged |
| `git diff --check` | clean |

Required examples passed:

- `minimal_evaporator_condenser_loop.py`
- `fixed_heat_rate_hx.py`
- `segmented_counterflow_hx.py`
- `minimal_closed_mpl_solver.py`
- `minimal_pressure_closure.py`
- `minimal_coupled_closure.py`

## Test-count discrepancy

The three new test files contain exactly 203 tests:

- 128 thermal closure primitive tests
- 39 thermal diagnostic tests
- 36 thermal integration tests

The reported full-suite increase from 6106 to 6316 appeared to be 210 because
6106 was a stale Block 15D-A total. The prior status was already internally
inconsistent: its own figures were a 5908 baseline plus 205 new 15D-A tests,
which equals 6113. The corrected arithmetic is:

`6113 + 203 = 6316`

No additional regression test files were modified or accidentally generated.
The network-suite arithmetic independently agrees:

`2252 + 203 = 2455`

## Boundary-search results

Searches covered CoolProp/property/registry names, `SystemState`, `FluidState`,
production components, `component_type`, `contribute`, solve APIs,
property/component/correlation/HX imports, file I/O, saturation/phase/quality,
LMTD/NTU/UA/HTC and correlation terms, and numerical root/least-squares
solvers.

Classification:

- Executable allowed: explicit scalar validation and arithmetic, immutable
  containers, deterministic category inspection, and test-only evaluation.
- Executable suspicious: none.
- Documentation negative statements: present and accurate.
- Test negative assertions: present and consistent with the architecture.
- Prohibited executable hits: none.

The new runtime modules import only standard-library facilities plus the
thermal closure declarations needed by diagnostics. They do not construct
state objects, infer physics from topology or component type, execute
components, call properties/correlations/HX models, solve equations, or write
files.

Repository-wide solve and component hits belong to pre-existing, explicitly
scoped callback/fixed-loop infrastructure or negative documentation/tests.
They were not introduced or called by Block 15D-B.

## Production-contract regression

The Phase 14G inspection test file passed all 60 tests. Direct inspection
reports `NO_CONTRIBUTE_METHOD` for:

- `Component`
- `Pipe`
- `PumpComponent`
- `AccumulatorComponent`
- `EvaporatorComponent`
- `CondenserComponent`

## Documentation alignment

`PROJECT_STATUS.md` now records the explicit algebraic scope, scalar-only
enthalpy and temperature-like constraints, caller-supplied `cp`, simplified
effectiveness and recuperator equations, architecture exclusions, deferred
physical models, corrected test baseline, final validation counts, and this
audit reference.

## Findings

### Critical

None.

### Major

None.

### Minor fixed

1. Corrected the stale full-suite baseline from 6106 to 6113 and documented
   why the apparent +210 increase is actually the expected +203.
2. Removed an unenforced claim that metadata keys must be strings; metadata is
   defensively copied but intentionally uninterpreted.
3. Updated project status to identify the checkpoint as independently audited
   and reference this audit document.

### Minor remaining

None.

## Deferred items

- Property-backed thermal closures and CoolProp integration
- Enthalpy-temperature conversion
- Saturation, phase, and quality logic
- Real LMTD, NTU, UA, effectiveness-NTU, HTC, and area-based HX prediction
- Correlation- and HX-model-backed closures
- Production component adapters and execution
- `SystemState` assembly and `FluidState` construction in network execution
- Configurable scenario building
- Combined hydraulic/thermal/physical residual assembly
- Symbolic rank and DAE solvability analysis
- Physically predictive thermal-network solves
- Arbitrary-topology physical simulation
- Generic `solve(network)` and `NetworkGraph.solve()`

## Readiness

Block 15D-B is complete within its explicit thermal-closure-primitives MVP
scope. No critical or major findings remain. The branch is ready to merge after
the audit commit is pushed. It must not be interpreted as providing
property-backed thermodynamics, a real heat-exchanger model, production
component execution, or a thermal network solver.
