"""Single-phase pressure-drop correlations — Phase 3C.

Implements the Churchill (1977) Darcy friction factor for internal flow,
returning the friction pressure gradient dP/dx_friction [Pa/m].

Does not include gravity, acceleration, or pipe-length integration.
Fluid properties (rho, mu) are received as explicit scalars via
SinglePhaseDPInput; CoolProp is never imported here.

Architectural rules:
- No import of CoolProp, properties/, geometry/, components/, network/,
  calibration/, or solvers/.
"""

from __future__ import annotations

import math

from mpl_sim.correlations.contract import (
    AnyFluid,
    Bound,
    BoundedQuantity,
    ClosureMetadata,
    Correlation,
    CorrelationInput,
    CorrelationOutput,
    CorrelationRole,
    EnvelopeRef,
    SinglePhaseDPInput,
    SourceRef,
    ValidityEnvelope,
    ValidityStatus,
    ValidityVerdict,
)

# ---------------------------------------------------------------------------
# Canonical metadata
# ---------------------------------------------------------------------------

_SOURCE = SourceRef(
    citation=(
        "Churchill, S. W. (1977). Friction-factor equation spans all fluid-flow "
        "regimes. Chemical Engineering, 84(24), 91–92."
    ),
    doi=None,
    notes=(
        "Darcy friction factor; continuous and explicit for all Re ≥ 0 and "
        "all relative roughness ≥ 0. "
        "Envelope bounds are conservative engineering limits; the formula "
        "extrapolates smoothly outside them."
    ),
)

_NAME = "churchill_friction_gradient"
_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Validity-envelope bounds (module-level constants, shared across calls)
# ---------------------------------------------------------------------------

_BOUND_RE = Bound(
    quantity=BoundedQuantity.REYNOLDS,
    min=1.0,
    max=1.0e8,
    units="-",
)

_BOUND_DH = Bound(
    quantity=BoundedQuantity.HYDRAULIC_DIAMETER,
    min=1.0e-6,
    max=None,
    units="m",
)

_BOUND_ROUGHNESS_RATIO = Bound(
    quantity=BoundedQuantity.NAMED_SCALAR,
    min=0.0,
    max=0.05,
    units="roughness_ratio [-]",
)

_ENVELOPE = ValidityEnvelope(
    fluid_families=(AnyFluid(),),
    bounds=(_BOUND_RE, _BOUND_DH, _BOUND_ROUGHNESS_RATIO),
    source=_SOURCE,
    notes=(
        "Conservative engineering envelope: Re ∈ [1, 1×10⁸], D_h ≥ 1 μm, "
        "eps/D ∈ [0, 0.05].  Colebrook-equivalent accuracy over most of this "
        "range.  Surface-effect corrections (microchannels, very-rough pipes) "
        "are not included."
    ),
)

_ENVELOPE_REF = EnvelopeRef(
    correlation_name=_NAME,
    correlation_version=_VERSION,
)

_METADATA = ClosureMetadata(
    name=_NAME,
    version=_VERSION,
    source=_SOURCE,
)


# ---------------------------------------------------------------------------
# Private formula helper
# ---------------------------------------------------------------------------


def _churchill_darcy(Re: float, eps_D: float) -> float:
    """Darcy friction factor via Churchill (1977).

    Parameters
    ----------
    Re    : Reynolds number, Re > 0
    eps_D : relative roughness = roughness / D_h, eps_D >= 0

    Returns
    -------
    f_D : Darcy friction factor (dimensionless, positive)

    Formula
    -------
    f_D = 8 · {(8/Re)¹² + [A + B]^(−3/2)}^(1/12)

    A = {2.457 · ln[1 / ((7/Re)^0.9 + 0.27·(eps/D))]}^16
    B = (37530 / Re)^16

    Recovers 64/Re exactly in the laminar limit (Re → 0 through term (8/Re)¹²)
    and Colebrook-equivalent values in turbulent flow.

    Reference: Churchill (1977) Chemical Engineering 84(24):91-92.
    """
    term_lam = (8.0 / Re) ** 12
    inner = (7.0 / Re) ** 0.9 + 0.27 * eps_D
    A = (2.457 * math.log(1.0 / inner)) ** 16
    B = (37530.0 / Re) ** 16
    return 8.0 * (term_lam + (A + B) ** (-1.5)) ** (1.0 / 12.0)


# ---------------------------------------------------------------------------
# Validity verdict helper
# ---------------------------------------------------------------------------


def _build_verdict(Re: float, D_h: float, eps_D: float) -> ValidityVerdict:
    violated: list[Bound] = []

    if Re < _BOUND_RE.min or Re > _BOUND_RE.max:  # type: ignore[operator]
        violated.append(_BOUND_RE)
    if D_h < _BOUND_DH.min:  # type: ignore[operator]
        violated.append(_BOUND_DH)
    if eps_D > _BOUND_ROUGHNESS_RATIO.max:  # type: ignore[operator]
        violated.append(_BOUND_ROUGHNESS_RATIO)

    if violated:
        detail = "Extrapolating outside validated envelope: " + ", ".join(b.units for b in violated)
        return ValidityVerdict(
            status=ValidityStatus.EXTRAPOLATED,
            envelope=_ENVELOPE_REF,
            violated=tuple(violated),
            detail=detail,
        )
    return ValidityVerdict(
        status=ValidityStatus.IN_ENVELOPE,
        envelope=_ENVELOPE_REF,
        violated=(),
    )


# ---------------------------------------------------------------------------
# ChurchillFrictionGradient — public closure
# ---------------------------------------------------------------------------


class ChurchillFrictionGradient(Correlation):
    """Single-phase friction pressure gradient via Churchill (1977).

    Returns dP/dx_friction in Pa/m (Darcy-Weisbach form, positive scalar).

    Output tuple convention (vector-first, §5.1):
        value[0] = dP/dx_friction [Pa/m]

    The closure is stateless and pure.  Fluid properties rho and mu must be
    supplied as scalars in SinglePhaseDPInput; they are never fetched from
    CoolProp or from properties/ in this module.
    """

    def role(self) -> CorrelationRole:
        return CorrelationRole.SINGLE_PHASE_DP

    def envelope(self) -> ValidityEnvelope:
        return _ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        if not isinstance(inp, SinglePhaseDPInput):
            raise TypeError(
                f"ChurchillFrictionGradient expects SinglePhaseDPInput, " f"got {type(inp)!r}"
            )

        # Guard: physically invalid scalars raise immediately; do not return
        # a fabricated result ([F11], CORRELATION_CONTRACT §6.4).
        if inp.D_h <= 0.0:
            raise ValueError(f"D_h must be positive; got {inp.D_h!r}")
        if inp.rho <= 0.0:
            raise ValueError(f"rho must be positive; got {inp.rho!r}")
        if inp.mu <= 0.0:
            raise ValueError(f"mu must be positive; got {inp.mu!r}")
        if inp.roughness < 0.0:
            raise ValueError(f"roughness must be non-negative; got {inp.roughness!r}")

        # Zero mass flux → zero friction gradient (no flow, no wall shear).
        G_abs = abs(inp.G)
        if G_abs == 0.0:
            verdict = ValidityVerdict(
                status=ValidityStatus.EXTRAPOLATED,
                envelope=_ENVELOPE_REF,
                violated=(_BOUND_RE,),
                detail="G=0: Re=0 is outside the Churchill validity domain; gradient is zero.",
            )
            return CorrelationOutput(value=(0.0,), verdict=verdict, metadata=_METADATA)

        # Intermediate scalars.
        Re = G_abs * inp.D_h / inp.mu
        eps_D = inp.roughness / inp.D_h

        # Validity verdict (built before the formula; does not affect result).
        verdict = _build_verdict(Re, inp.D_h, eps_D)

        # Churchill (1977) Darcy friction factor.
        f_D = _churchill_darcy(Re, eps_D)

        # Darcy-Weisbach friction gradient [Pa/m], gravity and acceleration excluded.
        # dP/dx = f_D * G² / (2 · rho · D_h)
        dp_dx = f_D * (G_abs**2) / (2.0 * inp.rho * inp.D_h)

        return CorrelationOutput(value=(dp_dx,), verdict=verdict, metadata=_METADATA)
