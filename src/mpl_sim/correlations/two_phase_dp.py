"""Two-phase pressure-drop correlations — Phase 11O.

Implements one two-phase frictional pressure-gradient closure under the
TWO_PHASE_DP role:

  - MSHTwoPhaseFrictionGradient  (Müller-Steinhagen & Heck 1986)

Returns dP/dx_friction in Pa/m (positive = pressure decreasing in flow
direction), matching the convention of ChurchillFrictionGradient.

Output convention (vector-first, CORRELATION_CONTRACT §5.1):
    value[0] = dP/dx_friction [Pa/m]

This is a GRADIENT, not a total pressure drop.  Integration over the cell
length is the caller's (Component's) responsibility ([F14]).

Migration source
---------------
Formula migrated from:
  legacy/PyP2PL/pyp2pl/correlations/dp_twophase.py  — msh_frictional_gradient
  legacy/MPL_Simulator/mpl/correlations.py           — MullerSteinhagenHeckDP

Numerical coefficients and interpolation form are taken directly from the
PyP2PL source (Churchill friction factor, Darcy-Weisbach form).
Architectural anti-patterns in the MPL source are removed:
  - FluidState coupling replaced by explicit property_scalars mapping
    (rho_l, rho_v, mu_l, mu_v in TwoPhaseDPInput.property_scalars)
  - Quality clamping (max/min) replaced by explicit ValueError
  - No CoolProp, PropertyBackend, or hidden fluid-specific defaults

Required scalars
----------------
From TwoPhaseDPInput fields and property_scalars (Decision 011):
  G       : mass flux [kg/m²s]  — must be finite and > 0
  x[0]    : local vapor quality [-] — must be finite and in [0, 1]
  D_h     : hydraulic diameter [m] — must be finite and > 0

From TwoPhaseDPInput.property_scalars:
  rho_l   : liquid density [kg/m³] — must be finite and > 0
  rho_v   : vapor density [kg/m³]  — must be finite and > 0
  mu_l    : liquid dynamic viscosity [Pa·s] — must be finite and > 0
  mu_v    : vapor dynamic viscosity [Pa·s]  — must be finite and > 0

Domain notes
------------
Smooth wall: MSH (1986) uses smooth-wall Churchill (1977) friction factor.
  Roughness is NOT a formula parameter; the caller cannot provide roughness.
  eps/D = 0 is a documented formula assumption, not a hidden default.
Reynolds numbers: Re_lo = G*D_h/mu_l and Re_vo = G*D_h/mu_v.
  Re_lo < 1 or Re_vo < 1 returns EXTRAPOLATED (Churchill gives correct
  Stokes-limit values, but MSH was not validated in that regime).  Full
  PyP2PL equivalence is only claimed for Re ≥ 1.
Fluid scope: validated for refrigerants (Ould Didi et al. 2002, Kokate 2024).
  AnyFluid() is NOT used; envelope declares FluidClassSpec(REFRIGERANT).
L_cell: present in TwoPhaseDPInput (frozen contract) but NOT used by this
  correlation.  Output is a Pa/m gradient; multiplication by L_cell to
  obtain a pressure drop [Pa] is the caller's responsibility.

Output semantics
----------------
  value[0] : dP/dx_friction [Pa/m], positive for pressure decreasing in
             flow direction.  Gravity and acceleration gradients are NOT
             included (they are Component terms, CORRELATION_CONTRACT §3.2).

Sign convention: same as ChurchillFrictionGradient — returns an unsigned
positive gradient for positive mass flux G.

HX injection status
-------------------
Direct HX injection is implemented by Phase 11P.  The caller explicitly sets
HXSolveRequest.dp_primary_is_two_phase=True; HX models then build
TwoPhaseDPInput with rho_l, rho_v, mu_l, and mu_v in property_scalars and
multiply value[0] by L_cell exactly once to obtain pressure drop [Pa].
Correlation selection remains injected and explicit; this module performs no
registry resolution or HX-specific conversion.

Architectural rules:
- No import of CoolProp, properties/, geometry/, components/, network/,
  calibration/, or solvers/.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

from mpl_sim.correlations.contract import (
    Bound,
    BoundedQuantity,
    ClosureMetadata,
    Correlation,
    CorrelationInput,
    CorrelationOutput,
    CorrelationRole,
    EnvelopeRef,
    FluidClass,
    FluidClassSpec,
    SourceRef,
    TwoPhaseDPInput,
    ValidityEnvelope,
    ValidityStatus,
    ValidityVerdict,
)

# ---------------------------------------------------------------------------
# Private scalar-extraction helper
# ---------------------------------------------------------------------------


def _require_scalar(ps: Mapping[str, float], key: str, context: str) -> float:
    """Return ps[key], raising ValueError clearly on absence or invalid value."""
    if key not in ps:
        raise ValueError(
            f"{context}: property_scalars must contain '{key}'; " f"keys present: {sorted(ps)}"
        )
    v = ps[key]
    if not math.isfinite(v) or v <= 0.0:
        raise ValueError(f"{context}: property_scalars['{key}'] must be finite and > 0; got {v!r}")
    return v


# ---------------------------------------------------------------------------
# Canonical metadata
# ---------------------------------------------------------------------------

_SOURCE = SourceRef(
    citation=(
        "Müller-Steinhagen, H., Heck, K. (1986). A simple friction pressure "
        "drop correlation for two-phase flow in pipes. "
        "Chemical Engineering and Processing, 20(6), 297–308. "
        "Evaluated by Ould Didi, M.B. et al. (2002) and used by "
        "Kokate, R. (PhD 2024) Appendix B for MPL evaporator/condenser DP."
    ),
    doi=None,
    notes=(
        "Interpolation between all-liquid and all-vapor Darcy-Weisbach "
        "gradients using Churchill (1977) friction factor.  "
        "Acceleration and gravity gradients are NOT included — those are "
        "Component terms (CORRELATION_CONTRACT §3.2)."
    ),
)

_NAME = "msh_two_phase_friction_gradient"
_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Validity-envelope bounds
# ---------------------------------------------------------------------------

_BOUND_QUALITY = Bound(
    quantity=BoundedQuantity.QUALITY_X,
    min=0.0,
    max=1.0,
    units="-",
)

_BOUND_DH = Bound(
    quantity=BoundedQuantity.HYDRAULIC_DIAMETER,
    min=1.0e-6,
    max=None,
    units="m",
)

_BOUND_RE_LO = Bound(
    quantity=BoundedQuantity.REYNOLDS,
    min=1.0,
    max=None,
    units="Re_lo [-]",
)

_BOUND_RE_VO = Bound(
    quantity=BoundedQuantity.REYNOLDS,
    min=1.0,
    max=None,
    units="Re_vo [-]",
)

_ENVELOPE = ValidityEnvelope(
    fluid_families=(FluidClassSpec(FluidClass.REFRIGERANT),),
    bounds=(_BOUND_QUALITY, _BOUND_DH, _BOUND_RE_LO, _BOUND_RE_VO),
    source=_SOURCE,
    notes=(
        "Quality x ∈ [0, 1]; D_h ≥ 1 μm; Re_lo ≥ 1; Re_vo ≥ 1.  "
        "Formula uses smooth-wall Churchill (1977) friction factor; "
        "roughness is not a free parameter (MSH smooth-wall assumption).  "
        "Validated for refrigerants (Ould Didi et al. 2002, Kokate 2024); "
        "AnyFluid overclaims — scope is refrigerant-class fluids.  "
        "At x = 0 returns all-liquid gradient; at x = 1 returns all-vapor gradient.  "
        "Re < 1 is outside the MSH validation domain; Churchill (1977) returns "
        "correct Stokes-limit values but MSH was not validated for that regime — "
        "verdict is EXTRAPOLATED, not an error."
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
# Private helpers
# ---------------------------------------------------------------------------


def _churchill_darcy(Re: float) -> float:
    """Churchill (1977) Darcy friction factor, smooth-wall (eps/D = 0).

    MSH (1986) assumes smooth-wall tubes; roughness is not a free parameter
    of the two-phase DP formula.  The eps_D = 0 simplification is the same
    as ChurchillFrictionGradient._churchill_darcy(Re, eps_D=0.0).
    """
    term_lam = (8.0 / Re) ** 12
    inner = (7.0 / Re) ** 0.9  # eps_D = 0: smooth wall, MSH formula assumption
    A = (2.457 * math.log(1.0 / inner)) ** 16
    B = (37530.0 / Re) ** 16
    return 8.0 * (term_lam + (A + B) ** (-1.5)) ** (1.0 / 12.0)


def _build_verdict(x: float, D_h: float, Re_lo: float, Re_vo: float) -> ValidityVerdict:
    violated: list[Bound] = []

    if x < _BOUND_QUALITY.min or x > _BOUND_QUALITY.max:  # type: ignore[operator]
        violated.append(_BOUND_QUALITY)
    if D_h < _BOUND_DH.min:  # type: ignore[operator]
        violated.append(_BOUND_DH)
    if Re_lo < _BOUND_RE_LO.min:  # type: ignore[operator]
        violated.append(_BOUND_RE_LO)
    if Re_vo < _BOUND_RE_VO.min:  # type: ignore[operator]
        violated.append(_BOUND_RE_VO)

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
# MSHTwoPhaseFrictionGradient — public closure
# ---------------------------------------------------------------------------


class MSHTwoPhaseFrictionGradient(Correlation):
    """Two-phase frictional pressure gradient via Müller-Steinhagen & Heck (1986).

    Returns dP/dx_friction in Pa/m (positive = pressure decreasing in
    flow direction).  Gravity and acceleration gradients are excluded.

    Formula
    -------
    A  = dPdz_lo = f_lo * G² / (2 * rho_l * D_h)   [all-liquid gradient]
    B  = dPdz_vo = f_vo * G² / (2 * rho_v * D_h)   [all-vapor gradient]

    dP/dx = [A + 2*(B - A)*x] * (1 - x)^(1/3) + B * x³

    f_lo, f_vo : Churchill (1977) Darcy friction factors at Re_lo = G*D_h/mu_l
                 and Re_vo = G*D_h/mu_v, smooth-wall (eps/D = 0).

    Migration source
    ----------------
    PyP2PL dp_twophase.py `msh_frictional_gradient`; MPL correlations.py
    `MullerSteinhagenHeckDP`.  Churchill friction factor from PyP2PL version.

    Traceability
    ------------
    Müller-Steinhagen & Heck (1986) Chem. Eng. Process. 20(6):297–308.
    Evaluation: Ould Didi et al. (2002).  MPL usage: Kokate PhD (2024) App. B.
    """

    def role(self) -> CorrelationRole:
        return CorrelationRole.TWO_PHASE_DP

    def envelope(self) -> ValidityEnvelope:
        return _ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        if not isinstance(inp, TwoPhaseDPInput):
            raise TypeError(
                f"MSHTwoPhaseFrictionGradient expects TwoPhaseDPInput, " f"got {type(inp)!r}"
            )

        # --- Required field validation ---

        if not inp.x:
            raise ValueError("MSHTwoPhaseFrictionGradient: x tuple must not be empty")

        x = inp.x[0]

        if not math.isfinite(x):
            raise ValueError(f"MSHTwoPhaseFrictionGradient: x must be finite; got {x!r}")
        if x < 0.0 or x > 1.0:
            raise ValueError(
                f"MSHTwoPhaseFrictionGradient: quality x must be in [0, 1]; " f"got {x!r}"
            )

        G = inp.G
        if not math.isfinite(G) or G <= 0.0:
            raise ValueError(f"MSHTwoPhaseFrictionGradient: G must be finite and > 0; got {G!r}")

        D_h = inp.D_h
        if not math.isfinite(D_h) or D_h <= 0.0:
            raise ValueError(
                f"MSHTwoPhaseFrictionGradient: D_h must be finite and > 0; " f"got {D_h!r}"
            )

        # Explicit property scalars from property_scalars mapping (Decision 011).
        _CTX = "MSHTwoPhaseFrictionGradient"
        rho_l = _require_scalar(inp.property_scalars, "rho_l", _CTX)
        rho_v = _require_scalar(inp.property_scalars, "rho_v", _CTX)
        mu_l = _require_scalar(inp.property_scalars, "mu_l", _CTX)
        mu_v = _require_scalar(inp.property_scalars, "mu_v", _CTX)

        # --- Derived Reynolds numbers (needed for verdict and friction factors) ---
        Re_lo = G * D_h / mu_l
        Re_vo = G * D_h / mu_v

        # --- Validity verdict ---
        verdict = _build_verdict(x, D_h, Re_lo, Re_vo)

        # --- All-liquid frictional gradient (smooth-wall Churchill ff) ---
        f_lo = _churchill_darcy(Re_lo)
        dPdz_lo = f_lo * G**2 / (2.0 * rho_l * D_h)

        # --- All-vapor frictional gradient (smooth-wall Churchill ff) ---
        f_vo = _churchill_darcy(Re_vo)
        dPdz_vo = f_vo * G**2 / (2.0 * rho_v * D_h)

        # --- MSH interpolation ---
        # dP/dz = [A + 2*(B-A)*x] * (1-x)^(1/3) + B * x^3
        A = dPdz_lo
        B = dPdz_vo
        Gx = A + 2.0 * (B - A) * x
        dPdz = Gx * (1.0 - x) ** (1.0 / 3.0) + B * x**3

        return CorrelationOutput(value=(dPdz,), verdict=verdict, metadata=_METADATA)
