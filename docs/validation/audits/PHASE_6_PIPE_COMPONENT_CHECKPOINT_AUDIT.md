# Phase 6 Pipe Component Checkpoint Audit

## Verdict

**APPROVED AS PHASE 6 CHECKPOINT - CONTINUE PHASE 6**

## Summary

Phase 6A introduces the first component-layer primitives: immutable component identity, component kind vocabulary, component port declarations, and an abstract local `Component` base.

Phase 6B adds the `Pipe` skeleton and a single-phase friction-only evaluation helper. The helper accepts scalar density and viscosity, uses a handed-in `SINGLE_PHASE_DP` correlation, preserves validity verdict and metadata, and returns both friction gradient and length-integrated friction pressure drop.

Phase 6C adds a gravity pressure contribution helper. It uses density, gravitational acceleration, and the pipe trajectory elevation change, with an explicit sign convention and no correlation or property-backend access.

This is a safe checkpoint, not a full Phase 6 closeout. `IMPLEMENTATION_PLAN.md` still requires the complete Pipe contribution contract, the internal 1D gradient kernel, acceleration contribution, momentum residual, frozen-zero derivatives, and calibration placement before Phase 6 can be considered complete.

## Scope Audited

Source and configuration inspected:

- `src/mpl_sim/components/base.py`
- `src/mpl_sim/components/pipe.py`
- `src/mpl_sim/components/__init__.py`
- `src/mpl_sim/core/`
- `src/mpl_sim/properties/`
- `src/mpl_sim/correlations/`
- `src/mpl_sim/geometry/`
- `src/mpl_sim/discretization/`
- `src/mpl_sim/calibration/`
- `pyproject.toml`

Tests inspected:

- `tests/components/test_component_contract.py`
- `tests/components/test_pipe_skeleton.py`
- `tests/components/test_pipe_single_phase_friction.py`
- `tests/components/test_pipe_gravity.py`

Authoritative documents inspected:

- `docs/roadmap/PROJECT_STATUS.md`
- `docs/roadmap/IMPLEMENTATION_PLAN.md`
- `docs/roadmap/ROADMAP.md`
- `docs/architecture/ARCHITECTURE_MASTER.md`
- `docs/architecture/INTERFACE_SPEC.md`
- `docs/architecture/CORRELATION_CONTRACT.md`
- `docs/architecture/SCHEMA_SPEC.md`
- `docs/validation/TEST_PLAN_V1.md`
- `docs/decisions/DECISION_LOG.md`
- `docs/validation/audits/PHASE_3_CORRELATION_LAYER_AUDIT.md`
- `docs/validation/audits/PHASE_4_GEOMETRY_DISCRETIZATION_AUDIT.md`
- `docs/validation/audits/PHASE_5A_CALIBRATION_PRIMITIVES_AUDIT.md`

## Audit Checklist

### Component Contract

`ComponentId`, `ComponentKind`, and `ComponentPort` are immutable or enum-based primitives. `ComponentKind` includes `PIPE` plus the planned future component kinds: `PUMP`, `ACCUMULATOR`, `EVAPORATOR`, `CONDENSER`, and `HEAT_EXCHANGER`.

`ComponentPort` uses existing core port concepts through `PortId` and `PortRole`. It declares component-local connectivity only and stores no thermodynamic state, derived property, residual, solver vector, or network topology.

The abstract `Component` base owns only structural declarations: `kind()`, `ports()`, and `internal_state_names()`. It does not own solver logic, network topology, `SystemState`, `FluidState`, geometry mutation, or physics.

### Pipe Skeleton

`Pipe` is a local component, not a network. It has a stable `ComponentId`, returns `ComponentKind.PIPE`, and declares exactly two V1 ports: inlet and outlet.

`Pipe` stores `PipeGeometry` and `DiscretizationSpec` by reference and does not mutate them. The class is a frozen dataclass and does not persist pressure, enthalpy, mass flow, density, viscosity, Reynolds number, friction factor, HTC, Nusselt number, quality, phase, residuals, solver vectors, mesh cells, or network references.

`Pipe` does not implement pump, accumulator, evaporator, condenser, or heat-exchanger behavior.

### Single-Phase Friction Kernel

`Pipe.evaluate_single_phase_friction()` accepts a `PipeSinglePhaseFrictionInput` containing scalar `G`, `rho`, and `mu`, plus a handed-in `Correlation`.

The method validates that the correlation role is `CorrelationRole.SINGLE_PHASE_DP`, builds a `SinglePhaseDPInput`, and calls the correlation contract. It does not call CoolProp, `PropertyBackend`, `CorrelationRegistry`, network, solvers, heat-transfer logic, phase-change logic, or two-phase pressure-drop logic.

The result exposes `dp_dx_friction` in Pa/m and `delta_p_friction = dp_dx_friction * pipe.geometry.L`. It preserves the correlation validity verdict and metadata. Gravity, acceleration, heat transfer, energy balance, and phase change are absent from the friction result.

The method does not mutate the `Pipe`, geometry, discretization, correlation registry, or inputs.

### Gravity Contribution

`Pipe.evaluate_gravity_pressure()` accepts scalar density and gravitational acceleration, reads `delta_z` from `pipe.geometry.trajectory.delta_z`, and returns `delta_p_gravity = rho * g * delta_z`.

The sign convention is explicit and tested: horizontal pipes return zero, upward pipes return a positive pressure contribution, and downward pipes return a negative contribution.

Gravity evaluation does not call correlations, `PropertyBackend`, CoolProp, friction computation, acceleration computation, heat transfer, network, or solvers. It does not mutate the `Pipe`, geometry, discretization, or inputs.

### Separation of Physical Terms

Friction and gravity remain separately inspectable through separate input/result types and separate evaluation methods.

No total mechanical balance or residual has been implemented prematurely. Acceleration, energy balance, two-phase behavior, network integration, and solver integration remain deferred.

### Calibration Boundary

Calibration primitives remain separate in `calibration/`. `Pipe` does not import `calibration/`, does not resolve or apply calibration factors, and does not scale gravity or balances.

This is acceptable for the current checkpoint, but full Phase 6 still needs the implementation-plan requirement that calibration placement be proven: `R*` scales only the friction gradient, while gravity and acceleration remain unscaled.

### Import Boundaries

`components/base.py` imports only standard library modules and `mpl_sim.core.port`.

`components/pipe.py` imports core, correlations contract types, geometry, and discretization, which is justified by local Pipe behavior. It does not import CoolProp, `properties/`, `network/`, `solvers/`, `CorrelationRegistry`, calibration, or unrelated components.

Reverse boundaries remain clean: properties, correlations, geometry, discretization, and calibration do not import components.

Import-boundary enforcement remains mostly test/static-review based rather than import-linter based.

### Tests

The component tests meaningfully cover:

- component identity construction, equality, hashability, validation, and immutability;
- component kind vocabulary;
- component port declaration construction, immutability, and absence of thermodynamic fields;
- Pipe construction, dataclass immutability, kind, inlet/outlet ports, port ordering, and forbidden persistent attributes;
- friction result units, length scaling, zero flow, monotonicity with mass flux, role validation, invalid density/viscosity behavior, verdict and metadata preservation, and no extra physical terms;
- gravity sign convention, horizontal-zero behavior, density and `g` linearity, no property/correlation calls, and no extra physical terms;
- import-boundary purity for component modules.

Important remaining tests before full Phase 6 closeout are tied to not-yet-implemented Phase 6 requirements: contribution-contract residuals, frozen-zero derivative reporting, acceleration contribution, mechanical summary/integrated kernel behavior, and calibration application to friction only.

### Architecture Consistency

The current implementation is consistent with the frozen architecture at this checkpoint:

- Core primitives remain independent.
- Properties remain independent, and CoolProp remains confined to `properties/`.
- Correlations remain independent from components.
- Geometry remains dimensional and state-free.
- Discretization remains numerical partitioning only.
- Calibration remains a separate seam/layer.
- Components are local and do not know network or solver objects.
- Pipe is the first component.
- Pump, accumulator, evaporator, condenser, and heat-exchanger components remain deferred.
- Heat transfer, phase change, two-phase pressure drop, network, and solvers remain deferred.

One implementation-plan gap is intentional at this checkpoint: full Phase 6 requires acceleration and contribution-contract residual behavior, neither of which has been implemented yet.

## Findings

### Critical Findings

None.

### Major Findings

None.

### Minor Findings

- The current gravity helper uses `geometry.trajectory.delta_z` directly rather than the more general `PipePath.derived().dz_dx_profile` integration path named in the architecture. This is acceptable for the current V1 straight-segment checkpoint, but the full Phase 6 kernel should use the derived path/cell metric route when the integrated 1D kernel is implemented.
- Import-direction rules remain enforced by targeted tests, static inspection, and review rather than import-linter or equivalent tooling. This is not a Phase 6 checkpoint blocker, but it should remain tracked as cross-layer imports increase.

## Phase 6 Status

Phase 6 is **partially complete** and should remain the current active phase.

Completed:

- Phase 6A - component contract primitives and Pipe skeleton.
- Phase 6B - Pipe single-phase friction-only helper using the existing correlation contract.
- Phase 6C - Pipe gravity pressure contribution helper.

Still required before full Phase 6 closeout according to `IMPLEMENTATION_PLAN.md`:

- complete Pipe contribution contract behavior;
- internal 1D gradient kernel in lumped mode;
- acceleration pressure contribution;
- integrated mechanical pressure summary or momentum residual;
- frozen-zero derivative reporting for named internal states, if required by the final Phase 6 contract slice;
- calibration placement proving `R*` scales only friction, not gravity, acceleration, or balances.

Deferred to later phases:

- network and `SystemState` assembly;
- solvers;
- pump and accumulator components;
- evaporator, condenser, heat-exchanger models, heat transfer, phase change, and two-phase behavior.

Implementation should continue in Phase 6 rather than advance to Phase 7.

## Recommended Next Step

Recommended next implementation slice:

**Phase 6D - pipe acceleration pressure contribution and mechanical summary scaffold.**

This slice should preserve the current separation of terms, add acceleration as its own inspectable contribution, and avoid network/solver integration. If the mechanical summary is added, it should combine friction, gravity, and acceleration contributions without becoming a global residual assembler. Calibration should either remain explicitly deferred or be applied only to friction in a narrowly tested seam.

## Verification

Verified on 2026-06-15.

Commands run:

```text
pytest
ruff check .
black --check src tests
```

Results:

- `pytest`: passed; 870 tests passed, with one pytest cache warning because Windows denied access to `.pytest_cache`.
- `ruff check .`: passed.
- `black --check src tests`: passed; 54 files would be left unchanged.

If `black --check .` fails due to `.pytest_cache` Windows permissions, `black --check src tests` is the meaningful formatting check for source and test files.

## Files Inspected

Documents:

- `docs/roadmap/PROJECT_STATUS.md`
- `docs/roadmap/IMPLEMENTATION_PLAN.md`
- `docs/roadmap/ROADMAP.md`
- `docs/architecture/ARCHITECTURE_MASTER.md`
- `docs/architecture/INTERFACE_SPEC.md`
- `docs/architecture/CORRELATION_CONTRACT.md`
- `docs/architecture/SCHEMA_SPEC.md`
- `docs/validation/TEST_PLAN_V1.md`
- `docs/decisions/DECISION_LOG.md`
- `docs/validation/audits/PHASE_3_CORRELATION_LAYER_AUDIT.md`
- `docs/validation/audits/PHASE_4_GEOMETRY_DISCRETIZATION_AUDIT.md`
- `docs/validation/audits/PHASE_5A_CALIBRATION_PRIMITIVES_AUDIT.md`

Source and configuration:

- `src/mpl_sim/components/base.py`
- `src/mpl_sim/components/pipe.py`
- `src/mpl_sim/components/__init__.py`
- `src/mpl_sim/core/`
- `src/mpl_sim/properties/`
- `src/mpl_sim/correlations/`
- `src/mpl_sim/geometry/`
- `src/mpl_sim/discretization/`
- `src/mpl_sim/calibration/`
- `pyproject.toml`

Tests:

- `tests/components/test_component_contract.py`
- `tests/components/test_pipe_skeleton.py`
- `tests/components/test_pipe_single_phase_friction.py`
- `tests/components/test_pipe_gravity.py`
