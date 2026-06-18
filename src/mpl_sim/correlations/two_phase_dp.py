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
  - FluidState coupling replaced by explicit scalar inputs (rho_l, rho_v,
    mu_l, mu_v on TwoPhaseDPInput)
  - Quality clamping (max/min) replaced by explicit ValueError
  - No CoolProp, PropertyBackend, or hidden fluid-specific defaults

Required scalars
----------------
From TwoPhaseDPInput fields:
  G       : mass flux [kg/m²s]  — must be finite and > 0
  x[0]    : local vapor quality [-] — must be finite and in [0, 1]
  D_h     : hydraulic diameter [m] — must be finite and > 0
  rho_l   : liquid density [kg/m³] — must be finite and > 0
  rho_v   : vapor density [kg/m³]  — must be finite and > 0
  mu_l    : liquid dynamic viscosity [Pa·s] — must be finite and > 0
  mu_v    : vapor dynamic viscosity [Pa·s]  — must be finite and > 0

Output semantics
----------------
  value[0] : dP/dx_friction [Pa/m], positive for pressure decreasing in
             flow direction.  Gravity and acceleration gradients are NOT
             included (they are Component terms, CORRELATION_CONTRACT §3.2).

Sign convention: same as ChurchillFrictionGradient — returns an unsigned
positive gradient for positive mass flux G.

HX injection status
-------------------
Direct HX injection is DEFERRED.  Current HX models (_build_dp_input) build
SinglePhaseDPInput, not TwoPhaseDPInput, and treat value[0] as a pressure
drop (Pa) rather than a gradient (Pa/m).  Injection requires:
  1. HX models to build TwoPhaseDPInput with explicit two-phase scalars.
  2. Explicit gradient-to-drop multiplication by L_cell inside the HX model.
  3. Two-phase property scalars (rho_l, rho_v, mu_l, mu_v) forwarded through
     geom_scalars or a dedicated two-phase input builder.
Until these are in place, two-phase DP must be evaluated standalone.

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
    SourceRef,
    TwoPhaseDPInput,
    ValidityEnvelope,
    ValidityStatus,
    ValidityVerdict,
)

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

_ENVELOPE = ValidityEnvelope(
    fluid_families=(AnyFluid(),),
    bounds=(_BOUND_QUALITY, _BOUND_DH),
    source=_SOURCE,
    notes=(
        "Quality x ∈ [0, 1]; D_h ≥ 1 μm.  "
        "At x = 0 the formula returns the all-liquid gradient; "
        "at x = 1 it returns the all-vapor gradient.  "
        "Validated for refrigerants in conventional and mini-channels "
        "(Ould Didi et al. 2002, Kokate 2024).  "
        "Mass-flux and Reynolds-number bounds are not explicitly declared "
        "by the source; the formula uses Darcy-Weisbach which is valid for "
        "any positive Re."
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


def _churchill_darcy(Re: float, eps_D: float) -> float:
    """Churchill (1977) Darcy friction factor.

    Same formula as ChurchillFrictionGradient._churchill_darcy.
    Reproduced here to keep two_phase_dp.py self-contained.
    """
    term_lam = (8.0 / Re) ** 12
    inner = (7.0 / Re) ** 0.9 + 0.27 * eps_D
    A = (2.457 * math.log(1.0 / inner)) ** 16
    B = (37530.0 / Re) ** 16
    return 8.0 * (term_lam + (A + B) ** (-1.5)) ** (1.0 / 12.0)


def _build_verdict(x: float, D_h: float) -> ValidityVerdict:
    violated: list[Bound] = []

    if x < _BOUND_QUALITY.min or x > _BOUND_QUALITY.max:  # type: ignore[operator]
        violated.append(_BOUND_QUALITY)
    if D_h < _BOUND_DH.min:  # type: ignore[operator]
        violated.append(_BOUND_DH)

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

        # Explicit property scalars — None means the caller did not supply them.
        rho_l = inp.rho_l
        if rho_l is None:
            raise ValueError(
                "MSHTwoPhaseFrictionGradient: rho_l is required but was not "
                "supplied (TwoPhaseDPInput.rho_l is None)"
            )
        if not math.isfinite(rho_l) or rho_l <= 0.0:
            raise ValueError(
                f"MSHTwoPhaseFrictionGradient: rho_l must be finite and > 0; " f"got {rho_l!r}"
            )

        rho_v = inp.rho_v
        if rho_v is None:
            raise ValueError(
                "MSHTwoPhaseFrictionGradient: rho_v is required but was not "
                "supplied (TwoPhaseDPInput.rho_v is None)"
            )
        if not math.isfinite(rho_v) or rho_v <= 0.0:
            raise ValueError(
                f"MSHTwoPhaseFrictionGradient: rho_v must be finite and > 0; " f"got {rho_v!r}"
            )

        mu_l = inp.mu_l
        if mu_l is None:
            raise ValueError(
                "MSHTwoPhaseFrictionGradient: mu_l is required but was not "
                "supplied (TwoPhaseDPInput.mu_l is None)"
            )
        if not math.isfinite(mu_l) or mu_l <= 0.0:
            raise ValueError(
                f"MSHTwoPhaseFrictionGradient: mu_l must be finite and > 0; " f"got {mu_l!r}"
            )

        mu_v = inp.mu_v
        if mu_v is None:
            raise ValueError(
                "MSHTwoPhaseFrictionGradient: mu_v is required but was not "
                "supplied (TwoPhaseDPInput.mu_v is None)"
            )
        if not math.isfinite(mu_v) or mu_v <= 0.0:
            raise ValueError(
                f"MSHTwoPhaseFrictionGradient: mu_v must be finite and > 0; " f"got {mu_v!r}"
            )

        # --- Validity verdict ---
        verdict = _build_verdict(x, D_h)

        # --- All-liquid frictional gradient ---
        Re_lo = G * D_h / mu_l
        f_lo = _churchill_darcy(Re_lo, 0.0)
        dPdz_lo = f_lo * G**2 / (2.0 * rho_l * D_h)

        # --- All-vapor frictional gradient ---
        Re_vo = G * D_h / mu_v
        f_vo = _churchill_darcy(Re_vo, 0.0)
        dPdz_vo = f_vo * G**2 / (2.0 * rho_v * D_h)

        # --- MSH interpolation ---
        # dP/dz = [A + 2*(B-A)*x] * (1-x)^(1/3) + B * x^3
        A = dPdz_lo
        B = dPdz_vo
        Gx = A + 2.0 * (B - A) * x
        dPdz = Gx * (1.0 - x) ** (1.0 / 3.0) + B * x**3

        return CorrelationOutput(value=(dPdz,), verdict=verdict, metadata=_METADATA)
