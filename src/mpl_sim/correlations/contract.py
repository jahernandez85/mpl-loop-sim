"""Correlation contract primitives — Phase 3A.

Defines the closed role set, role-typed input value objects, validity-envelope
declarations, ValidityVerdict, ClosureMetadata, CorrelationOutput, and the
Correlation abstract base.

Architectural rules enforced here:
- No import of properties/, CoolProp, or geometry.
- FluidState is imported from core/ (Layer 1); that direction is allowed.
- No actual correlation formulas — contract only.
- CorrelationOutput never returns a bare number ([F11], CORRELATION_CONTRACT §5).
- ValidityVerdict is always present on every output (§5.3, Rule 5).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum, auto
from types import MappingProxyType

from mpl_sim.core.fluid_state import FluidState

# ---------------------------------------------------------------------------
# CorrelationRole — frozen set of closure categories (INTERFACE_SPEC §7.2,
# CORRELATION_CONTRACT §3).
# ---------------------------------------------------------------------------


class CorrelationRole(Enum):
    """Frozen role set.  One entry per closure category the framework admits.

    CRITICAL_HEAT_FLUX and CUSTOM_CLOSURE are declared seams (<<SEAM>>):
    the roles exist so future closures are additive, not redesigns.
    """

    SINGLE_PHASE_DP = auto()
    TWO_PHASE_DP = auto()
    HTC = auto()
    VOID_FRACTION = auto()
    FLOW_REGIME = auto()
    CRITICAL_HEAT_FLUX = auto()  # <<SEAM>>: future role; no component slot yet
    VOLUME_PRESSURE_LAW = auto()
    CUSTOM_CLOSURE = auto()  # <<SEAM>>: ML / surrogate / ROM


# ---------------------------------------------------------------------------
# FlowRegimeLabel — the regime label vocabulary for FlowRegimeVerdict.
# ---------------------------------------------------------------------------


class FlowRegimeLabel(Enum):
    """Discriminated labels produced by FLOW_REGIME closures."""

    BUBBLY = auto()
    SLUG = auto()
    CHURN = auto()
    ANNULAR = auto()
    MIST = auto()
    STRATIFIED = auto()
    INTERMITTENT = auto()
    SINGLE_PHASE = auto()


# ---------------------------------------------------------------------------
# BoundedQuantity — the closed (extensible-by-name) set of quantities that
# ValidityEnvelope bounds can reference (CORRELATION_CONTRACT §6.2).
# ---------------------------------------------------------------------------


class BoundedQuantity(Enum):
    """Dimensionless groups and scalar quantities for validity bounds.

    The core set is frozen; a closure needing a quantity not listed here
    should declare a NAMED_SCALAR bound and document its name in the
    Bound.units field.
    """

    REYNOLDS = auto()
    MASS_FLUX_G = auto()
    QUALITY_X = auto()
    BOND = auto()
    WEBER = auto()
    FROUDE = auto()
    REDUCED_PRESSURE = auto()
    PRANDTL = auto()
    HYDRAULIC_DIAMETER = auto()
    ASPECT_RATIO = auto()
    CHEVRON_ANGLE = auto()
    HEAT_FLUX = auto()
    SATURATION_TEMP = auto()
    NAMED_SCALAR = auto()  # extension point; use Bound.units to name it


# ---------------------------------------------------------------------------
# FluidFamilySpec — declares which fluids a closure is validated for.
# ---------------------------------------------------------------------------


class FluidClass(Enum):
    """Broad fluid-class labels for FluidClassSpec."""

    REFRIGERANT = auto()
    WATER = auto()
    HYDROCARBON = auto()
    DIELECTRIC = auto()
    CRYOGEN = auto()
    OTHER = auto()


@dataclass(frozen=True)
class AnyFluid:
    """Envelope restriction: the closure claims validity for any fluid."""


@dataclass(frozen=True)
class NamedFluids:
    """Envelope restriction: valid only for the named fluids."""

    names: tuple[str, ...]


@dataclass(frozen=True)
class FluidClassSpec:
    """Envelope restriction: valid for a broad fluid class."""

    fluid_class: FluidClass


# Union over the three variants.
FluidFamilySpec = AnyFluid | NamedFluids | FluidClassSpec


# ---------------------------------------------------------------------------
# Bound — one scalar limit within a ValidityEnvelope.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Bound:
    """One scalar or dimensionless-group bound in a ValidityEnvelope.

    quantity : the physical quantity being bounded
    min      : lower bound (None = unbounded below)
    max      : upper bound (None = unbounded above)
    units    : SI unit string; for NAMED_SCALAR also carries the quantity name
    """

    quantity: BoundedQuantity
    min: float | None
    max: float | None
    units: str


# ---------------------------------------------------------------------------
# ValidityEnvelope — static per-correlation declaration of applicability
# (CORRELATION_CONTRACT §6.2).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceRef:
    """Bibliographic or dataset reference for a closure or its envelope."""

    citation: str
    doi: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class ValidityEnvelope:
    """Static declaration of the physical domain a correlation is valid for.

    Every concrete Correlation declares one of these.  It is checked on each
    evaluate() call to produce a ValidityVerdict.
    """

    fluid_families: tuple[FluidFamilySpec, ...]
    bounds: tuple[Bound, ...]
    source: SourceRef
    regime_restriction: tuple[FlowRegimeLabel, ...] | None = None
    notes: str | None = None


# ---------------------------------------------------------------------------
# ValidityVerdict — per-call result of checking inputs against the envelope
# (CORRELATION_CONTRACT §6.4, INTERFACE_SPEC §7.4).
# ---------------------------------------------------------------------------


class ValidityStatus(Enum):
    """Three-level severity for a single evaluate() call."""

    IN_ENVELOPE = auto()
    EXTRAPOLATED = auto()
    OUT_OF_RANGE = auto()


@dataclass(frozen=True)
class EnvelopeRef:
    """Lightweight reference back to the envelope that was checked."""

    correlation_name: str
    correlation_version: str


@dataclass(frozen=True)
class ValidityVerdict:
    """Per-call validity report.  Always present on every CorrelationOutput.

    status   : IN_ENVELOPE / EXTRAPOLATED / OUT_OF_RANGE
    envelope : which envelope was checked
    violated : which specific Bound(s) were exceeded (empty when IN_ENVELOPE)
    detail   : human-readable note; None when status is IN_ENVELOPE
    """

    status: ValidityStatus
    envelope: EnvelopeRef
    violated: tuple[Bound, ...]
    detail: str | None = None


# ---------------------------------------------------------------------------
# ClosureMetadata — provenance for every CorrelationOutput (§5.5, §12).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClosureMetadata:
    """Reproducibility anchor attached to every CorrelationOutput.

    name    : canonical registered name
    version : correlation version string
    source  : citation / DOI establishing this closure and its envelope
    """

    name: str
    version: str
    source: SourceRef


# ---------------------------------------------------------------------------
# CorrelationOutput — the only valid return type from evaluate() (§5.1).
# A bare number is forbidden.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CorrelationOutput:
    """Return type for every evaluate() call.

    value    : raw, un-calibrated closure quantity in SI units, vector-first
    verdict  : validity status for this call (always present)
    metadata : provenance (always present)
    """

    value: tuple[float, ...]
    verdict: ValidityVerdict
    metadata: ClosureMetadata


# ---------------------------------------------------------------------------
# FlowRegimeVerdict — output of FLOW_REGIME closures; also consumed as an
# optional input by TwoPhaseDPInput and HTCInput (§3.6).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FlowRegimeVerdict:
    """Regime classification produced by a FLOW_REGIME closure.

    regime            : discrete label from FlowRegimeLabel
    transition_coords : continuous blending coordinates keyed by name;
                        None if the regime map does not provide them
    verdict           : validity status of the regime evaluation itself
    """

    regime: FlowRegimeLabel
    verdict: ValidityVerdict
    transition_coords: Mapping[str, float] | None = None

    def __post_init__(self) -> None:
        if self.transition_coords is not None:
            object.__setattr__(
                self, "transition_coords", MappingProxyType(dict(self.transition_coords))
            )


# ---------------------------------------------------------------------------
# ThermalSpec — sub-object for HCA-type VolumePressureLawInput (§4.4, §9).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ThermalSpec:
    """Heater / saturation reference for thermally-controlled accumulator laws.

    heater_duty_W     : heater power [W]; None when not driven
    saturation_ref_Pa : saturation-reference pressure [Pa]; None when absent
    """

    heater_duty_W: float | None = None
    saturation_ref_Pa: float | None = None


# ---------------------------------------------------------------------------
# Role-typed CorrelationInput value objects (CORRELATION_CONTRACT §4.4).
# One type per role, shared by every formula in that role.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SinglePhaseDPInput:
    """Input manifest for SINGLE_PHASE_DP closures.

    state     : cell state(s); length >= 1  (vector-first)
    G         : mass flux [kg/m²s]
    D_h       : hydraulic diameter [m]
    roughness : absolute wall roughness [m]
    L_cell    : cell length [m] (caller's integration length; closure returns gradient)
    rho       : fluid density [kg/m³]  — must be positive
    mu        : dynamic viscosity [Pa·s] — must be positive
    """

    state: tuple[FluidState, ...]
    G: float
    D_h: float
    roughness: float
    L_cell: float
    rho: float
    mu: float


@dataclass(frozen=True)
class TwoPhaseDPInput:
    """Input manifest for TWO_PHASE_DP closures.  Amended by Decision 011.

    Required by every two-phase DP correlation:
        state            : cell state(s); length >= 1  (vector-first)
        G                : mass flux [kg/m²s]
        x                : local quality profile across the cell; must be finite in [0, 1]
        D_h              : hydraulic diameter [m]
        L_cell           : cell length [m] (caller's integration length; closure returns gradient)

    Optional regime hint:
        regime           : FlowRegimeVerdict; for regime-aware closures

    Formula-specific scalars (Decision 011):
        property_scalars : caller-supplied Mapping[str, float]; default empty.
                           Example keys: rho_l, rho_v, mu_l, mu_v (for MSH 1986).
                           No CoolProp, no PropertyBackend, no hidden defaults.
                           Each closure validates required keys; missing key raises ValueError.
    """

    state: tuple[FluidState, ...]
    G: float
    x: tuple[float, ...]
    D_h: float
    L_cell: float
    regime: FlowRegimeVerdict | None = None
    property_scalars: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "property_scalars", MappingProxyType(dict(self.property_scalars)))


@dataclass(frozen=True)
class HTCInput:
    """Input manifest for HTC closures (single- and two-phase).

    geom_scalars : flat scalar bag forwarded from Geometry (name -> float);
                   e.g. chevron_angle, fin descriptors.  Never a Geometry object.
    """

    state: tuple[FluidState, ...]
    G: float
    x: tuple[float, ...]
    D_h: float
    geom_scalars: Mapping[str, float]
    q_flux: float | None = None
    T_wall: float | None = None
    regime: FlowRegimeVerdict | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "geom_scalars", MappingProxyType(dict(self.geom_scalars)))


@dataclass(frozen=True)
class VoidFractionInput:
    """Input manifest for VOID_FRACTION closures."""

    state: tuple[FluidState, ...]
    x: tuple[float, ...]
    G: float | None = None
    D_h: float | None = None


@dataclass(frozen=True)
class FlowRegimeInput:
    """Input manifest for FLOW_REGIME closures."""

    state: tuple[FluidState, ...]
    G: float
    x: tuple[float, ...]
    D_h: float
    orientation: float | None = None


@dataclass(frozen=True)
class CriticalHeatFluxInput:
    """Input manifest for CRITICAL_HEAT_FLUX closures.  <<SEAM>>

    Declared now so the role is additive when implemented.
    No component declares a CHF slot in v1.
    """

    state: tuple[FluidState, ...]
    G: float
    x: tuple[float, ...]
    D_h: float
    L_heated: float | None = None


@dataclass(frozen=True)
class VolumePressureLawInput:
    """Input manifest for VOLUME_PRESSURE_LAW closures (§9).

    V_g        : stored gas/displaced volume [m³]
    V_total    : containment volume [m³] (geometry scalar)
    state      : working-fluid state at the accumulator port, when the law needs it
    law_params : PCA charge volume & polytropic index, spring rate & preload, etc.
    thermal    : heater duty / saturation reference for HCA-type laws
    P_set      : reference setpoint from Scenario [Pa]
    """

    V_g: float
    V_total: float
    law_params: Mapping[str, float]
    state: FluidState | None = None
    thermal: ThermalSpec | None = None
    P_set: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "law_params", MappingProxyType(dict(self.law_params)))


# Union over all role-typed inputs.
CorrelationInput = (
    SinglePhaseDPInput
    | TwoPhaseDPInput
    | HTCInput
    | VoidFractionInput
    | FlowRegimeInput
    | CriticalHeatFluxInput
    | VolumePressureLawInput
)


# ---------------------------------------------------------------------------
# Correlation — abstract base (CORRELATION_CONTRACT §1, INTERFACE_SPEC §7.2).
# ---------------------------------------------------------------------------


class Correlation(ABC):
    """Abstract base for every closure in the framework.

    Concrete subclasses must be stateless and pure: two calls with equal
    inputs must return equal outputs regardless of call order or history.

    Subclasses must not import from properties/, geometry/, components/,
    network/, or solvers/.
    """

    @abstractmethod
    def role(self) -> CorrelationRole:
        """Return the role this closure satisfies."""

    @abstractmethod
    def envelope(self) -> ValidityEnvelope:
        """Return the static validity envelope declared by this closure."""

    @abstractmethod
    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        """Evaluate the closure.  Must never return a bare number.

        A bare-float return is forbidden ([F11], CORRELATION_CONTRACT §5.1).
        The returned CorrelationOutput always carries a ValidityVerdict and
        ClosureMetadata.

        Out-of-envelope inputs: return honest extrapolated value flagged
        EXTRAPOLATED, or NaN flagged OUT_OF_RANGE for hard failures.
        Never clamp, never fabricate an in-range substitute (§6.4).
        """
