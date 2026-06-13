# Phase 4 Geometry and Discretization Audit

## Verdict

**APPROVED FOR PHASE 5**

## Summary

Phase 4A implements immutable geometry primitives as inert value objects. The geometry layer contains physical dimensions, trajectory/containment descriptors, and scalar heat-exchanger geometry descriptors only. It does not store operating state, discretization state, or physics outputs, and it does not call properties or correlations.

Phase 4B implements immutable discretization primitives as numerical partitioning objects. The discretization layer is separate from geometry, includes lumped, uniform, and moving-boundary declarations, and provides a deterministic `UniformGrid` without component integration or physics.

## Scope Audited

Source and configuration inspected:

- `src/mpl_sim/geometry/primitives.py`
- `src/mpl_sim/geometry/__init__.py`
- `src/mpl_sim/discretization/primitives.py`
- `src/mpl_sim/discretization/__init__.py`
- `pyproject.toml`

Tests inspected:

- `tests/geometry/test_geometry_primitives.py`
- `tests/geometry/__init__.py`
- `tests/discretization/test_discretization_primitives.py`
- `tests/discretization/__init__.py`

Authoritative documents inspected:

- `docs/roadmap/PROJECT_STATUS.md`
- `docs/roadmap/IMPLEMENTATION_PLAN.md`
- `docs/roadmap/ROADMAP.md`
- `docs/architecture/ARCHITECTURE_MASTER.md`
- `docs/architecture/INTERFACE_SPEC.md`
- `docs/architecture/SCHEMA_SPEC.md`
- `docs/validation/TEST_PLAN_V1.md`
- `docs/decisions/DECISION_LOG.md`
- `docs/validation/audits/PHASE_3_CORRELATION_LAYER_AUDIT.md`

## Audit Checklist

### Geometry Primitives

`PipePathDerived`, `StraightSegment`, `PipeGeometry`, `ContainmentSpec`, `ThermalSpec`, `AccumulatorGeometry`, `PlateGeometry`, `PortDimensions`, `FinGeometry`, and `MicrochannelGeometry` are frozen dataclasses. They are immutable value objects and validate basic invalid physical dimensions.

The geometry primitives store physical dimensions or scalar physical descriptors only. They do not store thermodynamic state, pressure, enthalpy, mass flow, quality, phase, density, viscosity, Reynolds number, friction factor, HTC, Nusselt number, pressure drop, heat-transfer results, mesh, cell count, or discretization state. They do not compute physics, call `PropertyBackend`, call correlations, or import CoolProp, properties, correlations, components, calibration, network, or solvers.

The only derived accessors found are dimensional path accessors: total length, `delta_z / length`, and V1 minor-loss coefficient sum.

### Pipe Geometry and Path

`StraightSegment` is immutable and requires positive length. Its `derived()` output is dimensionally consistent for V1: `L_total = length`, `dz_dx_profile = delta_z / length`, and `sum_minor_K = 0.0` because fittings are not implemented in V1.

`PipeGeometry` is immutable and stores only `L`, `D_h`, `A`, `roughness`, and `trajectory`. It validates positive length, positive hydraulic diameter, positive area, and non-negative roughness. It does not contain discretization count, mesh, state, or physics variables, and it is not a Pipe component.

### Accumulator Geometry

`AccumulatorGeometry` is containment-only. It validates positive total volume and composes containment and optional thermal descriptors. It does not include accumulator-law parameters such as gas-charge pressure, gas volume, spring rate, bellows area, polytropic index, pressure setpoint, or system state. Accumulator law behavior and accumulator component behavior remain deferred to later phases.

### Optional Heat-Exchanger Geometry Primitives

`PlateGeometry`, `PortDimensions`, `FinGeometry`, and `MicrochannelGeometry` are scalar-only immutable descriptors. They validate basic dimensions and do not implement heat-exchanger models, compute heat transfer, contain HTC correlations, call properties, or store state/discretization choices.

### Discretization Primitives

`DiscretizationMode`, `DiscretizationSpec`, `CellIndex`, `CellSpan`, and `UniformGrid` are separate from geometry. The dataclass primitives are immutable and store numerical partitioning choices only. They do not store thermodynamic state or physics outputs, compute physics, call `PropertyBackend`, call correlations, or import CoolProp, properties, correlations, components, calibration, network, solvers, or geometry.

### UniformGrid

`UniformGrid` is immutable. It requires positive total length and a positive number of cells. Its `cell_length` is `length / n_cells`, and its generated `CellSpan` sequence is deterministic, contiguous, sequentially indexed from zero, and covers the full length.

### Import Boundaries

Static inspection and tests show `geometry` imports only dataclass support and its own primitives. `discretization` imports only `enum`, dataclass support, and its own primitives. No Phase 4 module imports CoolProp, properties, correlations, components, calibration, network, solvers, or solver-side state.

### Tests

The Phase 4 tests meaningfully cover:

- geometry construction, immutability, and validation;
- forbidden geometry fields;
- accumulator law-parameter exclusion;
- optional heat-exchanger geometry construction and validation;
- geometry import boundaries;
- discretization mode declarations;
- discretization construction, immutability, and validation;
- `UniformGrid` coverage, determinism, contiguity, equal cell length, and sequential indices;
- forbidden discretization fields;
- discretization import boundaries;
- full test suite passing.

No additional test is required before Phase 5. Import-boundary tooling remains a tracked follow-up as layers expand.

### Architecture Consistency

Phase 4 is consistent with the frozen architecture:

- Geometry stores physical dimensions only.
- Discretization stores numerical partitioning only.
- Components have not started.
- Pipe component remains V1 Build Phase 6.
- Pump and Accumulator components remain V1 Build Phase 10.
- Evaporator and Condenser remain V1 Build Phase 11.
- Heat-exchanger models remain separate from raw geometry.
- Correlations remain separate from geometry and discretization.
- Properties remain separate from geometry and discretization.
- Solvers and network remain absent from Phase 4 implementation.

Deferred seams are acceptable and not blockers:

- `MultiSegmentPath`, `BendSegment`, and `FittingSegment`.
- `LumpedDiscretization`, `SegmentedDiscretization`, and `MovingBoundaryDiscretization` integration objects with `declared_state_count(geometry)` and `cell_metrics(geometry)`.
- Pipe component.
- Accumulator laws and accumulator components.
- Import-linter or equivalent import-direction tooling.

## Findings

### Critical Findings

None.

### Major Findings

None.

### Minor Findings

- Import-direction rules are still enforced by targeted tests, static inspection, and review rather than import-linter or equivalent tooling. This is not a Phase 5 blocker, but should remain a follow-up before higher-layer cross-package imports expand.

## Phase 5 Readiness

The project is ready to begin **Phase 5 - Calibration**, the next planned V1 Build Phase in `docs/roadmap/IMPLEMENTATION_PLAN.md`.

Phase 5 is calibration, not Pipe. The Pipe component remains deferred to V1 Build Phase 6. Component-coupled discretization integration objects also remain deferred until component integration requires them.

## Recommended Follow-ups

- Keep import-boundary checks under control as layers expand.
- Do not implement the Pipe component until V1 Build Phase 6.
- Keep geometry and discretization separated from physics and state.
- Introduce richer path and fitting objects only when components require them.
- Keep component-coupled discretization integration objects deferred until their planned component phases.

## Verification

Commands run:

```text
pytest
ruff check .
black --check .
black --check src tests
```

Results:

- `pytest`: 588 passed, with one pytest cache warning because Windows denied access to `.pytest_cache`.
- `ruff check .`: passed.
- `black --check .`: blocked by `PermissionError: [WinError 5] Access is denied: '.pytest_cache'`.
- `black --check src tests`: passed; 42 files would be left unchanged.

## Files Inspected

Documents:

- `docs/roadmap/PROJECT_STATUS.md`
- `docs/roadmap/IMPLEMENTATION_PLAN.md`
- `docs/roadmap/ROADMAP.md`
- `docs/architecture/ARCHITECTURE_MASTER.md`
- `docs/architecture/INTERFACE_SPEC.md`
- `docs/architecture/SCHEMA_SPEC.md`
- `docs/validation/TEST_PLAN_V1.md`
- `docs/decisions/DECISION_LOG.md`
- `docs/validation/audits/PHASE_3_CORRELATION_LAYER_AUDIT.md`

Source and configuration:

- `src/mpl_sim/geometry/primitives.py`
- `src/mpl_sim/geometry/__init__.py`
- `src/mpl_sim/discretization/primitives.py`
- `src/mpl_sim/discretization/__init__.py`
- `pyproject.toml`

Tests:

- `tests/geometry/test_geometry_primitives.py`
- `tests/geometry/__init__.py`
- `tests/discretization/test_discretization_primitives.py`
- `tests/discretization/__init__.py`
