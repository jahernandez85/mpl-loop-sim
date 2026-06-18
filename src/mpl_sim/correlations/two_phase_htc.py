"""Two-phase heat-transfer-coefficient correlations — Phase 11M.

Implements two flow-regime HTC closures under the HTC role:

  - ShahBoilingHTC     (Shah 1982, saturated flow boiling)
  - YanCondensationHTC (Yan, Lio & Lin 1999, plate condenser condensation)

Both return h [W/m²/K] in CorrelationOutput.value[0].

Migration source
----------------
Formulas migrated from:
  legacy/MPL_Simulator/mpl/correlations.py — ShahBoilingHTC and
  YanCondensationHTC classes.

Numerical coefficients are taken directly from the legacy source.
Architectural anti-patterns present in legacy code are removed:
  - FluidState coupling replaced by explicit scalar inputs
  - Quality clamping (max/min) replaced by explicit ValueError
  - No CoolProp, PropertyBackend, or hidden fluid-specific defaults

Required scalars — ShahBoilingHTC
----------------------------------
From HTCInput:
  G       : mass flux [kg/m²/s]  — must be finite and > 0
  x[0]    : vapor quality [-]    — must be strictly in (0, 1); singular at endpoints
  D_h     : hydraulic diameter [m] — must be finite and > 0
  q_flux  : wall heat flux [W/m²]  — must be finite and > 0

From HTCInput.geom_scalars:
  rho_l   : liquid density [kg/m³]
  rho_v   : vapor density [kg/m³]
  mu_l    : liquid dynamic viscosity [Pa·s]
  k_l     : liquid thermal conductivity [W/m/K]
  Pr_l    : liquid Prandtl number [-]
  h_fg    : latent heat of vaporization [J/kg]

Required scalars — YanCondensationHTC
--------------------------------------
From HTCInput:
  G       : mass flux [kg/m²/s]  — must be finite and > 0
  x[0]    : vapor quality [-]    — must be finite and in [0, 1]
  D_h     : hydraulic diameter [m] — must be finite and > 0

From HTCInput.geom_scalars:
  rho_l   : liquid density [kg/m³]
  rho_v   : vapor density [kg/m³]
  mu_l    : liquid dynamic viscosity [Pa·s]
  k_l     : liquid thermal conductivity [W/m/K]
  Pr_l    : liquid Prandtl number [-]

Architectural rules
-------------------
- No import of CoolProp, properties/, geometry/, components/, network/,
  calibration/, or solvers/.
- Correlations are stateless and pure.
- All physical inputs are validated; ValueError is raised for non-finite or
  out-of-range required scalars (hard failure per CORRELATION_CONTRACT §6.4).
- Quality clamping is forbidden; instead x at the singular endpoints of Shah
  raises ValueError, and Yan returns EXTRAPOLATED at x=0 or x=1.
- Out-of-envelope but evaluable inputs return an honest extrapolated value
  flagged EXTRAPOLATED; no clamping or fabricated substitute.
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
# Physical constant
# ---------------------------------------------------------------------------

_G_EARTH: float = 9.806  # standard gravity [m/s²]

# ---------------------------------------------------------------------------
# Shared helper — extract a required finite positive scalar from geom_scalars
# ---------------------------------------------------------------------------


def _require_positive(scalars: object, key: str, corr_name: str) -> float:
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
# ShahBoilingHTC
# ===========================================================================

_SB_SOURCE = SourceRef(
    citation=(
        "Shah, M. M. (1982). Chart correlation for saturated boiling heat transfer: "
        "equations and further study. ASHRAE Transactions, 88(1), 185–196. "
        "Implementation reference: Kokate, R., & Park, C. (2023). "
        "Pumped two-phase loop thermal control system. "
        "Applied Thermal Engineering, 229, 120630 (Appendix A). "
        "Kokate, R. PhD Thesis (2024), Appendix A."
    ),
    doi=None,
    notes=(
        "Saturated flow boiling in mini/micro-channels. "
        "alpha = max(alpha_cb, alpha_nb); "
        "alpha_cb = 1.8 * alpha_l / N^0.8; "
        "alpha_nb depends on N and Bo (four regime branches). "
        "alpha_l = Dittus-Boelter liquid-only baseline at total mass flux G. "
        "Valid for 0 < x < 1 (formula singular at endpoints). "
        "Migration source: legacy/MPL_Simulator/mpl/correlations.py ShahBoilingHTC."
    ),
)

_SB_NAME = "shah_boiling_htc"
_SB_VERSION = "1.0"

_SB_BOUND_X = Bound(
    quantity=BoundedQuantity.QUALITY_X,
    min=0.0,
    max=1.0,
    units="-",
)

_SB_ENVELOPE = ValidityEnvelope(
    fluid_families=(AnyFluid(),),
    bounds=(_SB_BOUND_X,),
    source=_SB_SOURCE,
    notes=(
        "Saturated two-phase flow boiling: x strictly in (0, 1). "
        "Formula is singular at x=0 and x=1; these raise ValueError. "
        "No declared G or q_flux envelope bounds; all positive values accepted."
    ),
)

_SB_ENVELOPE_REF = EnvelopeRef(correlation_name=_SB_NAME, correlation_version=_SB_VERSION)
_SB_METADATA = ClosureMetadata(name=_SB_NAME, version=_SB_VERSION, source=_SB_SOURCE)


def _sb_verdict() -> ValidityVerdict:
    # All valid Shah inputs (x strictly in (0,1), positive scalars) are IN_ENVELOPE.
    # Envelope excursions at x≤0 or x≥1 are enforced via ValueError before this point.
    return ValidityVerdict(
        status=ValidityStatus.IN_ENVELOPE,
        envelope=_SB_ENVELOPE_REF,
        violated=(),
    )


class ShahBoilingHTC(Correlation):
    """Saturated flow boiling HTC via Shah (1982).

    Formula
    -------
    alpha_l = 0.023 * Re_l^0.8 * Pr_l^0.4 * k_l / D_h
      Re_l  = G * D_h / mu_l   (liquid-only Re at total mass flux)

    C0      = ((1-x)/x)^0.8 * (rho_v/rho_l)^0.5   (convection number)
    Bo      = q_flux / (G * h_fg)                   (boiling number)
    Fr_l    = G^2 / (rho_l^2 * g * D_h)            (Froude number, liquid)

    N = C0                          if Fr_l > 0.04
    N = 0.38 * Fr_l^(-0.3) * C0    otherwise

    alpha_cb = alpha_l * 1.8 / N^0.8

    alpha_nb (four branches based on N and Bo):
      N > 1, Bo > 3e-4  : alpha_l * 230 * Bo^0.5
      N > 1, Bo ≤ 3e-4  : alpha_l * (1 + 46 * Bo^0.5)
      0.1 < N ≤ 1       : Fs * alpha_l * Bo^0.5 * exp(2.74*N - 0.1)
      N ≤ 0.1           : Fs * alpha_l * Bo^0.5 * exp(2.74*N - 0.15)
      Fs = 14.7 if Bo > 0.0011 else 15.43

    h = max(alpha_cb, alpha_nb)

    Required inputs
    ---------------
    inp.G, inp.x[0], inp.D_h, inp.q_flux (all from HTCInput fields).
    geom_scalars: rho_l, rho_v, mu_l, k_l, Pr_l, h_fg.

    Quality domain
    --------------
    x must be strictly in (0, 1).  x ≤ 0 or x ≥ 1 raises ValueError
    because the formula is singular at those points (division by zero in C0).

    Output
    ------
    value[0] = h [W/m²/K]
    """

    def role(self) -> CorrelationRole:
        return CorrelationRole.HTC

    def envelope(self) -> ValidityEnvelope:
        return _SB_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        if not isinstance(inp, HTCInput):
            raise TypeError(f"ShahBoilingHTC expects HTCInput, got {type(inp)!r}")

        # ── Validate HTCInput fields ──────────────────────────────────────
        G = inp.G
        if not math.isfinite(G) or G <= 0.0:
            raise ValueError(f"ShahBoilingHTC: G must be finite and > 0; got {G!r}")

        D_h = inp.D_h
        if not math.isfinite(D_h) or D_h <= 0.0:
            raise ValueError(f"ShahBoilingHTC: D_h must be finite and > 0; got {D_h!r}")

        if not inp.x:
            raise ValueError("ShahBoilingHTC: HTCInput.x is empty; x[0] is required")
        x = inp.x[0]
        if not math.isfinite(x):
            raise ValueError(f"ShahBoilingHTC: x must be finite; got {x!r}")
        if not (0.0 < x < 1.0):
            raise ValueError(
                f"ShahBoilingHTC: x must be strictly in (0, 1); got {x!r}. "
                "The formula is singular at x=0 and x=1. "
                "Do not clamp quality — supply a valid two-phase quality."
            )

        q_flux = inp.q_flux
        if q_flux is None:
            raise ValueError("ShahBoilingHTC: q_flux is required but None")
        if not math.isfinite(q_flux) or q_flux <= 0.0:
            raise ValueError(f"ShahBoilingHTC: q_flux must be finite and > 0; got {q_flux!r}")

        # ── Validate geom_scalars ─────────────────────────────────────────
        gs = inp.geom_scalars
        rho_l = _require_positive(gs, "rho_l", "ShahBoilingHTC")
        rho_v = _require_positive(gs, "rho_v", "ShahBoilingHTC")
        mu_l = _require_positive(gs, "mu_l", "ShahBoilingHTC")
        k_l = _require_positive(gs, "k_l", "ShahBoilingHTC")
        Pr_l = _require_positive(gs, "Pr_l", "ShahBoilingHTC")
        h_fg = _require_positive(gs, "h_fg", "ShahBoilingHTC")

        # ── Liquid-only Dittus-Boelter baseline ───────────────────────────
        Re_l = G * D_h / mu_l
        alpha_l = 0.023 * (Re_l**0.8) * (Pr_l**0.4) * k_l / D_h

        # ── Dimensionless groups ──────────────────────────────────────────
        C0 = ((1.0 - x) / x) ** 0.8 * (rho_v / rho_l) ** 0.5
        Bo = q_flux / (G * h_fg)
        Fr_l = G**2 / (rho_l**2 * _G_EARTH * D_h)

        # ── Convection number N ───────────────────────────────────────────
        if Fr_l > 0.04:
            N = C0
        else:
            N = 0.38 * Fr_l ** (-0.3) * C0

        # ── Convective boiling component ──────────────────────────────────
        alpha_cb = alpha_l * 1.8 / (N**0.8)

        # ── Nucleate boiling component (four regime branches) ─────────────
        Fs = 14.7 if Bo > 0.0011 else 15.43

        if N > 1.0:
            if Bo > 0.0003:
                alpha_nb = alpha_l * 230.0 * (Bo**0.5)
            else:
                alpha_nb = alpha_l * (1.0 + 46.0 * (Bo**0.5))
        elif N > 0.1:
            alpha_nb = alpha_l * Fs * (Bo**0.5) * math.exp(2.74 * N - 0.1)
        else:
            alpha_nb = alpha_l * Fs * (Bo**0.5) * math.exp(2.74 * N - 0.15)

        h = max(alpha_cb, alpha_nb)

        return CorrelationOutput(value=(h,), verdict=_sb_verdict(), metadata=_SB_METADATA)


# ===========================================================================
# YanCondensationHTC
# ===========================================================================

_YC_SOURCE = SourceRef(
    citation=(
        "Yan, Y.-Y., Lio, H.-C., & Lin, T.-F. (1999). Condensation heat transfer "
        "and pressure drop of refrigerant R-134a in a plate heat exchanger. "
        "International Journal of Heat and Mass Transfer, 42(6), 993–1006. "
        "Implementation reference: Kokate, R., & Park, C. (2023). "
        "Applied Thermal Engineering, 229, 120630. "
        "Kokate, R. PhD Thesis (2024)."
    ),
    doi="10.1016/S0017-9310(98)00127-6",
    notes=(
        "Condensation in plate heat exchangers (chevron angle β = 30°, R-134a). "
        "alpha = 4.118 * Re_eq^0.4 * Pr_l^(1/3) * k_l / D_h; "
        "G_eq  = G * (1 - x + x * sqrt(rho_l/rho_v))  [Akers equivalent mass flux]; "
        "Re_eq = G_eq * D_h / mu_l. "
        "Formula evaluable at x=0 and x=1; endpoints flagged EXTRAPOLATED. "
        "Migration source: legacy/MPL_Simulator/mpl/correlations.py YanCondensationHTC."
    ),
)

_YC_NAME = "yan_condensation_htc"
_YC_VERSION = "1.0"

_YC_BOUND_X = Bound(
    quantity=BoundedQuantity.QUALITY_X,
    min=0.0,
    max=1.0,
    units="-",
)

_YC_ENVELOPE = ValidityEnvelope(
    fluid_families=(AnyFluid(),),
    bounds=(_YC_BOUND_X,),
    source=_YC_SOURCE,
    notes=(
        "Condensation in two-phase region: x strictly in (0, 1). "
        "Formula is evaluable at x=0 and x=1; those return EXTRAPOLATED. "
        "Originally developed for R-134a, plate HX, chevron angle β = 30°; "
        "applied to broader conditions in Kokate 2023."
    ),
)

_YC_ENVELOPE_REF = EnvelopeRef(correlation_name=_YC_NAME, correlation_version=_YC_VERSION)
_YC_METADATA = ClosureMetadata(name=_YC_NAME, version=_YC_VERSION, source=_YC_SOURCE)


def _yc_verdict(x: float) -> ValidityVerdict:
    # x in (0, 1) strictly → IN_ENVELOPE.
    # x = 0 or x = 1 → EXTRAPOLATED (formula evaluable, outside two-phase regime).
    # x < 0 or x > 1 → already raised ValueError before this point.
    if not (0.0 < x < 1.0):
        return ValidityVerdict(
            status=ValidityStatus.EXTRAPOLATED,
            envelope=_YC_ENVELOPE_REF,
            violated=(_YC_BOUND_X,),
            detail=f"x={x!r} is at the boundary of the two-phase condensation domain (0, 1).",
        )
    return ValidityVerdict(
        status=ValidityStatus.IN_ENVELOPE,
        envelope=_YC_ENVELOPE_REF,
        violated=(),
    )


class YanCondensationHTC(Correlation):
    """In-tube condensation HTC via Yan, Lio & Lin (1999).

    Formula
    -------
    G_eq  = G * (1 - x + x * sqrt(rho_l / rho_v))   [Akers equivalent mass flux]
    Re_eq = G_eq * D_h / mu_l
    h     = 4.118 * Re_eq^0.4 * Pr_l^(1/3) * k_l / D_h

    Required inputs
    ---------------
    inp.G, inp.x[0], inp.D_h (all from HTCInput fields).
    geom_scalars: rho_l, rho_v, mu_l, k_l, Pr_l.

    Quality domain
    --------------
    x must be in [0, 1].  x < 0 or x > 1 raises ValueError.
    x = 0 or x = 1 are evaluable and return EXTRAPOLATED verdict.

    Output
    ------
    value[0] = h [W/m²/K]
    """

    def role(self) -> CorrelationRole:
        return CorrelationRole.HTC

    def envelope(self) -> ValidityEnvelope:
        return _YC_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        if not isinstance(inp, HTCInput):
            raise TypeError(f"YanCondensationHTC expects HTCInput, got {type(inp)!r}")

        # ── Validate HTCInput fields ──────────────────────────────────────
        G = inp.G
        if not math.isfinite(G) or G <= 0.0:
            raise ValueError(f"YanCondensationHTC: G must be finite and > 0; got {G!r}")

        D_h = inp.D_h
        if not math.isfinite(D_h) or D_h <= 0.0:
            raise ValueError(f"YanCondensationHTC: D_h must be finite and > 0; got {D_h!r}")

        if not inp.x:
            raise ValueError("YanCondensationHTC: HTCInput.x is empty; x[0] is required")
        x = inp.x[0]
        if not math.isfinite(x):
            raise ValueError(f"YanCondensationHTC: x must be finite; got {x!r}")
        if x < 0.0 or x > 1.0:
            raise ValueError(
                f"YanCondensationHTC: x must be in [0, 1]; got {x!r}. "
                "Do not clamp quality — supply a physically valid quality."
            )

        # ── Validate geom_scalars ─────────────────────────────────────────
        gs = inp.geom_scalars
        rho_l = _require_positive(gs, "rho_l", "YanCondensationHTC")
        rho_v = _require_positive(gs, "rho_v", "YanCondensationHTC")
        mu_l = _require_positive(gs, "mu_l", "YanCondensationHTC")
        k_l = _require_positive(gs, "k_l", "YanCondensationHTC")
        Pr_l = _require_positive(gs, "Pr_l", "YanCondensationHTC")

        # ── Yan (1999) condensation formula ───────────────────────────────
        G_eq = G * (1.0 - x + x * math.sqrt(rho_l / rho_v))
        Re_eq = G_eq * D_h / mu_l
        h = 4.118 * (Re_eq**0.4) * (Pr_l ** (1.0 / 3.0)) * k_l / D_h

        return CorrelationOutput(value=(h,), verdict=_yc_verdict(x), metadata=_YC_METADATA)
