"""Single-phase heat-transfer-coefficient correlations — Phase 11L.

Implements two turbulent internal-flow HTC closures under the HTC role:
  - DittusBoelterHTC  (Dittus & Boelter 1930, turbulent pipe flow)
  - GnielinskiHTC     (Gnielinski 1976, turbulent pipe flow)

Both return h [W/m²/K] in CorrelationOutput.value[0].

Required scalars in HTCInput.geom_scalars
------------------------------------------
  Re  : Reynolds number [-] (must be finite and > 0)
  Pr  : Prandtl number  [-] (must be finite and > 0)
  k   : fluid thermal conductivity [W/m/K] (must be finite and > 0)

D_h is read directly from HTCInput.D_h (must be > 0).

For DittusBoelterHTC an additional scalar is required:
  n   : exponent on Pr [-]; 0.4 for heating, 0.3 for cooling (must be finite and > 0)

No CoolProp, no PropertyBackend, no hidden defaults.  All property scalars must
be supplied explicitly by the caller; the correlation never infers them from
FluidState.identity or from module-level fluid constants.

Architectural rules:
- No import of CoolProp, properties/, geometry/, components/, network/,
  calibration/, or solvers/.
- Correlations are stateless and pure.
- All physical inputs are validated; ValueError is raised for non-finite or
  non-positive required scalars (hard failure per CORRELATION_CONTRACT §6.4).
- Out-of-envelope but mathematically evaluable inputs return an honest
  extrapolated value flagged EXTRAPOLATED; no clamping or fabricated substitute.
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
    HTCInput,
    SourceRef,
    ValidityEnvelope,
    ValidityStatus,
    ValidityVerdict,
)

# ---------------------------------------------------------------------------
# Shared helper — extract a required finite positive scalar from geom_scalars
# ---------------------------------------------------------------------------


def _require_positive(scalars: object, key: str, corr_name: str) -> float:
    """Extract a required finite positive scalar from a geom_scalars mapping.

    Raises ValueError (not KeyError) so callers see a clear contract message.
    """
    try:
        val: float = scalars[key]  # type: ignore[index]
    except (KeyError, TypeError):
        raise ValueError(f"{corr_name}: geom_scalars[{key!r}] is required but absent")
    if not math.isfinite(val):
        raise ValueError(f"{corr_name}: geom_scalars[{key!r}] must be finite; got {val!r}")
    if val <= 0.0:
        raise ValueError(f"{corr_name}: geom_scalars[{key!r}] must be > 0; got {val!r}")
    return val


# ===========================================================================
# DittusBoelterHTC
# ===========================================================================

_DB_SOURCE = SourceRef(
    citation=(
        "Dittus, F. W., & Boelter, L. M. K. (1930). Heat transfer in automobile "
        "radiators of the tubular type. Publications in Engineering, University of "
        "California, Berkeley, 2, 443–461. "
        "Re-stated in: Incropera, F. P., et al. (2007). Fundamentals of Heat and "
        "Mass Transfer, 6th ed., Wiley, Eq. 8.60."
    ),
    doi=None,
    notes=(
        "Nu = 0.023 * Re^0.8 * Pr^n  (n = 0.4 heating, n = 0.3 cooling). "
        "Validated for 0.6 ≤ Pr ≤ 160, Re ≥ 10 000, L/D ≥ 10, "
        "moderate property variation (properties evaluated at bulk T). "
        "Envelope bounds are conservative; formula extrapolates smoothly outside them."
    ),
)

_DB_NAME = "dittus_boelter_htc"
_DB_VERSION = "1.0"

_DB_BOUND_RE = Bound(quantity=BoundedQuantity.REYNOLDS, min=1.0e4, max=None, units="-")
_DB_BOUND_PR = Bound(quantity=BoundedQuantity.PRANDTL, min=0.6, max=160.0, units="-")
_DB_BOUND_DH = Bound(quantity=BoundedQuantity.HYDRAULIC_DIAMETER, min=1.0e-6, max=None, units="m")

_DB_ENVELOPE = ValidityEnvelope(
    fluid_families=(AnyFluid(),),
    bounds=(_DB_BOUND_RE, _DB_BOUND_PR, _DB_BOUND_DH),
    source=_DB_SOURCE,
    notes=(
        "Turbulent pipe flow: Re ≥ 10 000, Pr ∈ [0.6, 160], D_h ≥ 1 μm, L/D ≥ 10. "
        "Extrapolates outside these limits with degraded accuracy."
    ),
)

_DB_ENVELOPE_REF = EnvelopeRef(correlation_name=_DB_NAME, correlation_version=_DB_VERSION)
_DB_METADATA = ClosureMetadata(name=_DB_NAME, version=_DB_VERSION, source=_DB_SOURCE)


def _db_verdict(Re: float, Pr: float, D_h: float) -> ValidityVerdict:
    violated: list[Bound] = []
    if Re < _DB_BOUND_RE.min:  # type: ignore[operator]
        violated.append(_DB_BOUND_RE)
    if Pr < _DB_BOUND_PR.min or Pr > _DB_BOUND_PR.max:  # type: ignore[operator]
        violated.append(_DB_BOUND_PR)
    if D_h < _DB_BOUND_DH.min:  # type: ignore[operator]
        violated.append(_DB_BOUND_DH)
    if violated:
        detail = "Extrapolating outside validated envelope: " + ", ".join(b.units for b in violated)
        return ValidityVerdict(
            status=ValidityStatus.EXTRAPOLATED,
            envelope=_DB_ENVELOPE_REF,
            violated=tuple(violated),
            detail=detail,
        )
    return ValidityVerdict(
        status=ValidityStatus.IN_ENVELOPE,
        envelope=_DB_ENVELOPE_REF,
        violated=(),
    )


class DittusBoelterHTC(Correlation):
    """Single-phase convective HTC via Dittus & Boelter (1930).

    Formula
    -------
    Nu = 0.023 * Re^0.8 * Pr^n
    h  = Nu * k / D_h

    Required scalars (via HTCInput.geom_scalars)
    ---------------------------------------------
    Re  : Reynolds number [-]
    Pr  : Prandtl number  [-]
    k   : fluid thermal conductivity [W/m/K]
    n   : Prandtl exponent [-]; 0.4 for heating, 0.3 for cooling

    D_h is read directly from HTCInput.D_h.

    Output (vector-first, one element)
    -----------------------------------
    value[0] = h [W/m²/K]

    Validity
    --------
    Full envelope: Re ≥ 10 000, Pr ∈ [0.6, 160], D_h ≥ 1 μm.
    Inputs outside the envelope return an honest extrapolated value flagged
    EXTRAPOLATED.  Non-finite or non-positive required inputs raise ValueError.
    """

    def role(self) -> CorrelationRole:
        return CorrelationRole.HTC

    def envelope(self) -> ValidityEnvelope:
        return _DB_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        if not isinstance(inp, HTCInput):
            raise TypeError(f"DittusBoelterHTC expects HTCInput, got {type(inp)!r}")

        D_h = inp.D_h
        if not math.isfinite(D_h) or D_h <= 0.0:
            raise ValueError(f"DittusBoelterHTC: D_h must be finite and > 0; got {D_h!r}")

        gs = inp.geom_scalars
        Re = _require_positive(gs, "Re", "DittusBoelterHTC")
        Pr = _require_positive(gs, "Pr", "DittusBoelterHTC")
        k = _require_positive(gs, "k", "DittusBoelterHTC")
        n = _require_positive(gs, "n", "DittusBoelterHTC")

        verdict = _db_verdict(Re, Pr, D_h)

        Nu = 0.023 * (Re**0.8) * (Pr**n)
        h = Nu * k / D_h

        return CorrelationOutput(value=(h,), verdict=verdict, metadata=_DB_METADATA)


# ===========================================================================
# GnielinskiHTC
# ===========================================================================

_GN_SOURCE = SourceRef(
    citation=(
        "Gnielinski, V. (1976). New equations for heat and mass transfer in "
        "turbulent pipe and channel flow. International Chemical Engineering, "
        "16(2), 359–368."
    ),
    doi=None,
    notes=(
        "Nu = ((f/8)(Re - 1000)Pr) / (1 + 12.7√(f/8)(Pr^(2/3) - 1)); "
        "f = (0.79 ln Re - 1.64)^(-2) (Petukhov friction factor). "
        "Validated for 0.5 ≤ Pr ≤ 2000, 3000 ≤ Re ≤ 5×10^6. "
        "Improves on Dittus-Boelter in the transitional regime (Re ~ 3000–10000). "
        "Envelope bounds are conservative; formula extrapolates smoothly outside them."
    ),
)

_GN_NAME = "gnielinski_htc"
_GN_VERSION = "1.0"

_GN_BOUND_RE = Bound(quantity=BoundedQuantity.REYNOLDS, min=3.0e3, max=5.0e6, units="-")
_GN_BOUND_PR = Bound(quantity=BoundedQuantity.PRANDTL, min=0.5, max=2000.0, units="-")
_GN_BOUND_DH = Bound(quantity=BoundedQuantity.HYDRAULIC_DIAMETER, min=1.0e-6, max=None, units="m")

_GN_ENVELOPE = ValidityEnvelope(
    fluid_families=(AnyFluid(),),
    bounds=(_GN_BOUND_RE, _GN_BOUND_PR, _GN_BOUND_DH),
    source=_GN_SOURCE,
    notes=(
        "Turbulent/transitional pipe flow: Re ∈ [3 000, 5×10⁶], "
        "Pr ∈ [0.5, 2 000], D_h ≥ 1 μm. "
        "Extrapolates outside these limits with degraded accuracy."
    ),
)

_GN_ENVELOPE_REF = EnvelopeRef(correlation_name=_GN_NAME, correlation_version=_GN_VERSION)
_GN_METADATA = ClosureMetadata(name=_GN_NAME, version=_GN_VERSION, source=_GN_SOURCE)


def _gn_verdict(Re: float, Pr: float, D_h: float) -> ValidityVerdict:
    violated: list[Bound] = []
    if Re < _GN_BOUND_RE.min or Re > _GN_BOUND_RE.max:  # type: ignore[operator]
        violated.append(_GN_BOUND_RE)
    if Pr < _GN_BOUND_PR.min or Pr > _GN_BOUND_PR.max:  # type: ignore[operator]
        violated.append(_GN_BOUND_PR)
    if D_h < _GN_BOUND_DH.min:  # type: ignore[operator]
        violated.append(_GN_BOUND_DH)
    if violated:
        detail = "Extrapolating outside validated envelope: " + ", ".join(b.units for b in violated)
        return ValidityVerdict(
            status=ValidityStatus.EXTRAPOLATED,
            envelope=_GN_ENVELOPE_REF,
            violated=tuple(violated),
            detail=detail,
        )
    return ValidityVerdict(
        status=ValidityStatus.IN_ENVELOPE,
        envelope=_GN_ENVELOPE_REF,
        violated=(),
    )


class GnielinskiHTC(Correlation):
    """Single-phase convective HTC via Gnielinski (1976).

    Formula
    -------
    f  = (0.79 * ln(Re) - 1.64)^(-2)          [Petukhov friction factor]
    Nu = ((f/8) * (Re - 1000) * Pr) /
         (1 + 12.7 * sqrt(f/8) * (Pr^(2/3) - 1))
    h  = Nu * k / D_h

    Required scalars (via HTCInput.geom_scalars)
    ---------------------------------------------
    Re  : Reynolds number [-]
    Pr  : Prandtl number  [-]
    k   : fluid thermal conductivity [W/m/K]

    D_h is read directly from HTCInput.D_h.

    Output (vector-first, one element)
    -----------------------------------
    value[0] = h [W/m²/K]

    Validity
    --------
    Full envelope: Re ∈ [3 000, 5×10⁶], Pr ∈ [0.5, 2 000], D_h ≥ 1 μm.
    Inputs outside the envelope return an honest extrapolated value flagged
    EXTRAPOLATED.  Non-finite or non-positive required inputs raise ValueError.
    The Petukhov friction factor requires Re > 0 to evaluate ln(Re); this is
    enforced by the positive-scalar check on Re.
    """

    def role(self) -> CorrelationRole:
        return CorrelationRole.HTC

    def envelope(self) -> ValidityEnvelope:
        return _GN_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        if not isinstance(inp, HTCInput):
            raise TypeError(f"GnielinskiHTC expects HTCInput, got {type(inp)!r}")

        D_h = inp.D_h
        if not math.isfinite(D_h) or D_h <= 0.0:
            raise ValueError(f"GnielinskiHTC: D_h must be finite and > 0; got {D_h!r}")

        gs = inp.geom_scalars
        Re = _require_positive(gs, "Re", "GnielinskiHTC")
        Pr = _require_positive(gs, "Pr", "GnielinskiHTC")
        k = _require_positive(gs, "k", "GnielinskiHTC")

        verdict = _gn_verdict(Re, Pr, D_h)

        # Petukhov (1970) friction factor; evaluable for all Re > 0.
        f = (0.79 * math.log(Re) - 1.64) ** (-2)

        f_over_8 = f / 8.0
        numerator = f_over_8 * (Re - 1000.0) * Pr
        denominator = 1.0 + 12.7 * math.sqrt(f_over_8) * (Pr ** (2.0 / 3.0) - 1.0)

        Nu = numerator / denominator
        h = Nu * k / D_h

        return CorrelationOutput(value=(h,), verdict=verdict, metadata=_GN_METADATA)
