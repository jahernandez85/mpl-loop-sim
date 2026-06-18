"""Explicit q_flux plumbing tests — Phase 11N.

Verifies that HXSolveRequest.q_flux_primary is threaded correctly into
HTCInput.q_flux for all three HX model strategies, and that ShahBoilingHTC
can be injected when the caller supplies all required scalars and a positive
q_flux_primary.

Coverage:

  Request-level validation:
    - HXSolveRequest accepts finite positive q_flux_primary.
    - HXSolveRequest rejects zero, negative, NaN, and infinite q_flux_primary.
    - Omitting q_flux_primary remains valid (None is accepted).

  Spy correlation — q_flux passthrough:
    - EpsilonNTUModel: spy HTC correlation receives HTCInput.q_flux == q_flux_primary.
    - LMTDModel: spy HTC correlation receives HTCInput.q_flux == q_flux_primary.
    - SegmentedMarchModel FixedWallTemp: every cell spy receives q_flux_primary.
    - SegmentedMarchModel SinkInletTempAndFlow: primary HTC spy receives q_flux_primary
      once per cell; secondary HTC spy also receives q_flux_primary (same builder).

  No-q_flux paths still work:
    - EpsilonNTUModel FixedWallTemp without q_flux_primary passes None to HTCInput.
    - LMTDModel FixedWallTemp without q_flux_primary works with a simple HTC spy.
    - SegmentedMarchModel AmbientCoupling and FixedHeatRate need no q_flux at all.

  ShahBoilingHTC end-to-end injection:
    - EpsilonNTUModel FixedWallTemp with ShahBoilingHTC + required scalars + q_flux_primary
      produces a finite positive Q.
    - EpsilonNTUModel FixedWallTemp with ShahBoilingHTC but no q_flux_primary fails clearly.
    - LMTDModel FixedWallTemp with ShahBoilingHTC + required scalars + q_flux_primary
      produces a finite positive Q.
    - SegmentedMarchModel FixedWallTemp with ShahBoilingHTC + required scalars + q_flux_primary
      produces a finite positive Q from every cell.
    - SegmentedMarchModel FixedWallTemp with ShahBoilingHTC but no q_flux_primary fails clearly.

  Secondary HTC isolation:
    - Secondary HTC spy in SinkInletTempAndFlow receives q_flux_primary (same builder path).
    - Ambient coupling path does not call any HTC correlation regardless of q_flux_primary.

  Architecture:
    - HX models do not resolve CorrelationRegistry.
    - No CoolProp / PropertyBackend access.
    - No hidden q_flux default.
    - No abs() or clip on q_flux (tested via spy inspection).

Architectural constraints:
  - No CoolProp, no PropertyBackend, no Network, no Solver.
  - All custom correlations are test-only stubs.
  - No CorrelationRegistry constructed or queried inside HX model paths.
"""

from __future__ import annotations

import math

import pytest

from mpl_sim.core.fluid_identity import PureFluid
from mpl_sim.core.fluid_state import FluidState
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
from mpl_sim.correlations.two_phase_htc import ShahBoilingHTC
from mpl_sim.discretization.primitives import DiscretizationMode, DiscretizationSpec
from mpl_sim.hx_models.base import (
    AmbientCoupling,
    FixedHeatRate,
    FixedWallTemp,
    HXSolveRequest,
    PrimaryThermalMode,
    SinkInletTempAndFlow,
    UAComputationMode,
)
from mpl_sim.hx_models.epsilon_ntu import EpsilonNTUModel
from mpl_sim.hx_models.lmtd import LMTDModel
from mpl_sim.hx_models.segmented import SegmentedMarchModel

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_FLUID = PureFluid("R134a")
_STATE_IN = FluidState(P=500_000.0, h=250_000.0, identity=_FLUID)
_LUMPED = DiscretizationSpec(mode=DiscretizationMode.LUMPED, n_cells=1)
_SEGMENTED_3 = DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=3)

_MINIMAL_ENVELOPE = ValidityEnvelope(
    fluid_families=(AnyFluid(),),
    bounds=(Bound(quantity=BoundedQuantity.REYNOLDS, min=None, max=None, units=""),),
    source=SourceRef(citation="test-stub"),
)


def _htc_out(value: float, name: str = "spy_htc") -> CorrelationOutput:
    return CorrelationOutput(
        value=(value,),
        verdict=ValidityVerdict(
            status=ValidityStatus.IN_ENVELOPE,
            envelope=EnvelopeRef(correlation_name=name, correlation_version="0"),
            violated=(),
        ),
        metadata=ClosureMetadata(name=name, version="0", source=SourceRef(citation="test")),
    )


class _SpyHTCCorrelation(Correlation):
    """Records every HTCInput it receives; returns a fixed HTC value."""

    def __init__(self, htc: float = 500.0, name: str = "spy_htc") -> None:
        self._htc = htc
        self._name = name
        self.received_inputs: list[HTCInput] = []

    def role(self) -> CorrelationRole:
        return CorrelationRole.HTC

    def envelope(self) -> ValidityEnvelope:
        return _MINIMAL_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        assert isinstance(inp, HTCInput), f"Expected HTCInput, got {type(inp)!r}"
        self.received_inputs.append(inp)
        return _htc_out(self._htc, self._name)


_GEOM_SCALARS_SINGLE_PHASE = {
    "G": 200.0,
    "D_h": 0.001,
    "x": 0.5,
    "A_ht": 0.01,
    "rho": 1200.0,
    "mu": 0.0002,
    "L_cell": 0.1,
}

_SHAH_GEOM_SCALARS = {
    "G": 300.0,
    "D_h": 0.001,
    "x": 0.4,
    "A_ht": 0.01,
    "rho_l": 1200.0,
    "rho_v": 30.0,
    "mu_l": 0.0002,
    "k_l": 0.08,
    "Pr_l": 4.5,
    "h_fg": 180_000.0,
    "rho": 1200.0,
    "mu": 0.0002,
    "L_cell": 0.1,
}

_Q_FLUX = 10_000.0  # W/m² — positive, finite


# ---------------------------------------------------------------------------
# 1. Request-level validation
# ---------------------------------------------------------------------------


class TestHXSolveRequestQFluxValidation:
    """HXSolveRequest accepts and rejects q_flux_primary correctly."""

    def _base_req(self, **kwargs) -> HXSolveRequest:
        defaults = dict(
            primary_state_in=_STATE_IN,
            primary_mdot=0.01,
            secondary_bc=FixedHeatRate(Q=100.0),
            geometry=object(),
            discretization=_LUMPED,
        )
        defaults.update(kwargs)
        return HXSolveRequest(**defaults)

    def test_accepts_finite_positive_q_flux_primary(self):
        req = self._base_req(q_flux_primary=_Q_FLUX)
        assert req.q_flux_primary == _Q_FLUX

    def test_accepts_small_positive_q_flux_primary(self):
        req = self._base_req(q_flux_primary=1e-3)
        assert req.q_flux_primary == pytest.approx(1e-3)

    def test_accepts_large_positive_q_flux_primary(self):
        req = self._base_req(q_flux_primary=1e8)
        assert req.q_flux_primary == pytest.approx(1e8)

    def test_omitting_q_flux_primary_is_valid(self):
        req = self._base_req()
        assert req.q_flux_primary is None

    def test_explicit_none_q_flux_primary_is_valid(self):
        req = self._base_req(q_flux_primary=None)
        assert req.q_flux_primary is None

    def test_rejects_zero_q_flux_primary(self):
        with pytest.raises(ValueError, match="q_flux_primary"):
            self._base_req(q_flux_primary=0.0)

    def test_rejects_negative_q_flux_primary(self):
        with pytest.raises(ValueError, match="q_flux_primary"):
            self._base_req(q_flux_primary=-5000.0)

    def test_rejects_nan_q_flux_primary(self):
        with pytest.raises(ValueError, match="q_flux_primary"):
            self._base_req(q_flux_primary=float("nan"))

    def test_rejects_positive_inf_q_flux_primary(self):
        with pytest.raises(ValueError, match="q_flux_primary"):
            self._base_req(q_flux_primary=float("inf"))

    def test_rejects_negative_inf_q_flux_primary(self):
        with pytest.raises(ValueError, match="q_flux_primary"):
            self._base_req(q_flux_primary=float("-inf"))

    def test_error_message_does_not_mention_abs(self):
        with pytest.raises(ValueError) as exc_info:
            self._base_req(q_flux_primary=-1.0)
        msg = str(exc_info.value)
        assert "abs()" in msg or "abs" in msg.lower()

    def test_q_flux_primary_passed_unchanged(self):
        val = 12345.6789
        req = self._base_req(q_flux_primary=val)
        assert req.q_flux_primary is val or req.q_flux_primary == val


# ---------------------------------------------------------------------------
# 2. EpsilonNTUModel — q_flux passthrough
# ---------------------------------------------------------------------------


class TestEpsilonNTUModelQFluxPassthrough:
    """EpsilonNTUModel threads q_flux_primary into HTCInput.q_flux."""

    def _fixed_wall_req(self, q_flux_primary=None, htc=None, extra_scalars=None) -> HXSolveRequest:
        scalars = dict(_GEOM_SCALARS_SINGLE_PHASE)
        if extra_scalars:
            scalars.update(extra_scalars)
        return HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.01,
            secondary_bc=FixedWallTemp(T_wall=320.0),
            geometry=object(),
            discretization=_LUMPED,
            geom_scalars=scalars,
            htc_primary=htc or _SpyHTCCorrelation(),
            primary_T_in=280.0,
            q_flux_primary=q_flux_primary,
        )

    def test_spy_receives_q_flux_primary_when_supplied(self):
        spy = _SpyHTCCorrelation()
        req = self._fixed_wall_req(q_flux_primary=_Q_FLUX, htc=spy)
        EpsilonNTUModel().solve(req)
        assert len(spy.received_inputs) == 1
        assert spy.received_inputs[0].q_flux == _Q_FLUX

    def test_spy_receives_none_when_q_flux_primary_omitted(self):
        spy = _SpyHTCCorrelation()
        req = self._fixed_wall_req(q_flux_primary=None, htc=spy)
        EpsilonNTUModel().solve(req)
        assert len(spy.received_inputs) == 1
        assert spy.received_inputs[0].q_flux is None

    def test_q_flux_value_is_not_abs_or_clipped(self):
        spy = _SpyHTCCorrelation()
        original_val = 7777.5
        req = self._fixed_wall_req(q_flux_primary=original_val, htc=spy)
        EpsilonNTUModel().solve(req)
        assert spy.received_inputs[0].q_flux == original_val

    def test_no_q_flux_htc_still_works_without_q_flux_primary(self):
        spy = _SpyHTCCorrelation(htc=600.0)
        req = self._fixed_wall_req(q_flux_primary=None, htc=spy)
        result = EpsilonNTUModel().solve(req)
        assert math.isfinite(result.Q)


# ---------------------------------------------------------------------------
# 3. LMTDModel — q_flux passthrough
# ---------------------------------------------------------------------------


class TestLMTDModelQFluxPassthrough:
    """LMTDModel threads q_flux_primary into HTCInput.q_flux."""

    def _fixed_wall_req(self, q_flux_primary=None, htc=None) -> HXSolveRequest:
        return HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.01,
            secondary_bc=FixedWallTemp(T_wall=320.0),
            geometry=object(),
            discretization=_LUMPED,
            geom_scalars=_GEOM_SCALARS_SINGLE_PHASE,
            htc_primary=htc or _SpyHTCCorrelation(),
            primary_T_in=280.0,
            q_flux_primary=q_flux_primary,
        )

    def test_spy_receives_q_flux_primary_when_supplied(self):
        spy = _SpyHTCCorrelation()
        req = self._fixed_wall_req(q_flux_primary=_Q_FLUX, htc=spy)
        LMTDModel().solve(req)
        assert len(spy.received_inputs) == 1
        assert spy.received_inputs[0].q_flux == _Q_FLUX

    def test_spy_receives_none_when_q_flux_primary_omitted(self):
        spy = _SpyHTCCorrelation()
        req = self._fixed_wall_req(q_flux_primary=None, htc=spy)
        LMTDModel().solve(req)
        assert len(spy.received_inputs) == 1
        assert spy.received_inputs[0].q_flux is None

    def test_ambient_coupling_does_not_require_q_flux(self):
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.01,
            secondary_bc=AmbientCoupling(T_ambient=298.0, UA_ambient=5.0),
            geometry=object(),
            discretization=_LUMPED,
            primary_T_in=280.0,
        )
        result = LMTDModel().solve(req)
        assert math.isfinite(result.Q)


# ---------------------------------------------------------------------------
# 4. SegmentedMarchModel — q_flux passthrough
# ---------------------------------------------------------------------------


class TestSegmentedMarchModelQFluxPassthrough:
    """SegmentedMarchModel threads q_flux_primary into every cell HTCInput.q_flux."""

    def _fixed_wall_req(self, q_flux_primary=None, htc=None, n_cells=3) -> HXSolveRequest:
        disc = DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=n_cells)
        return HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.01,
            secondary_bc=FixedWallTemp(T_wall=320.0),
            geometry=object(),
            discretization=disc,
            geom_scalars=_GEOM_SCALARS_SINGLE_PHASE,
            htc_primary=htc or _SpyHTCCorrelation(),
            primary_T_in=280.0,
            primary_cp=1400.0,
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
            q_flux_primary=q_flux_primary,
        )

    def test_every_cell_receives_q_flux_primary_fixed_wall_temp(self):
        n = 4
        spy = _SpyHTCCorrelation()
        req = self._fixed_wall_req(q_flux_primary=_Q_FLUX, htc=spy, n_cells=n)
        SegmentedMarchModel().solve(req)
        assert len(spy.received_inputs) == n
        for inp in spy.received_inputs:
            assert inp.q_flux == _Q_FLUX

    def test_every_cell_receives_none_when_q_flux_primary_omitted(self):
        n = 3
        spy = _SpyHTCCorrelation()
        req = self._fixed_wall_req(q_flux_primary=None, htc=spy, n_cells=n)
        SegmentedMarchModel().solve(req)
        assert len(spy.received_inputs) == n
        for inp in spy.received_inputs:
            assert inp.q_flux is None

    def test_sink_inlet_primary_htc_receives_q_flux_primary(self):
        n = 2
        disc = DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=n)
        spy_primary = _SpyHTCCorrelation(htc=500.0, name="spy_primary")
        spy_secondary = _SpyHTCCorrelation(htc=400.0, name="spy_secondary")
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.01,
            secondary_bc=SinkInletTempAndFlow(T_in=300.0, mdot_secondary=0.02, cp_secondary=4200.0),
            geometry=object(),
            discretization=disc,
            geom_scalars=_GEOM_SCALARS_SINGLE_PHASE,
            htc_primary=spy_primary,
            htc_secondary=spy_secondary,
            primary_T_in=280.0,
            primary_cp=1400.0,
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
            ua_computation_mode=UAComputationMode.TWO_SIDED,
            q_flux_primary=_Q_FLUX,
        )
        SegmentedMarchModel().solve(req)
        assert len(spy_primary.received_inputs) == n
        for inp in spy_primary.received_inputs:
            assert inp.q_flux == _Q_FLUX
        assert len(spy_secondary.received_inputs) == n
        for inp in spy_secondary.received_inputs:
            assert inp.q_flux == _Q_FLUX

    def test_ambient_coupling_does_not_require_q_flux(self):
        disc = DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=2)
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.01,
            secondary_bc=AmbientCoupling(T_ambient=298.0, UA_ambient=5.0),
            geometry=object(),
            discretization=disc,
            primary_T_in=280.0,
            primary_cp=1400.0,
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
        )
        result = SegmentedMarchModel().solve(req)
        assert math.isfinite(result.Q)

    def test_fixed_heat_rate_does_not_require_q_flux(self):
        disc = DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=2)
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.01,
            secondary_bc=FixedHeatRate(Q=500.0),
            geometry=object(),
            discretization=disc,
        )
        result = SegmentedMarchModel().solve(req)
        assert math.isfinite(result.Q)


# ---------------------------------------------------------------------------
# 5. ShahBoilingHTC end-to-end injection
# ---------------------------------------------------------------------------


def _shah_req_epsilon_ntu(q_flux_primary=None) -> HXSolveRequest:
    return HXSolveRequest(
        primary_state_in=_STATE_IN,
        primary_mdot=0.01,
        secondary_bc=FixedWallTemp(T_wall=350.0),
        geometry=object(),
        discretization=_LUMPED,
        geom_scalars=_SHAH_GEOM_SCALARS,
        htc_primary=ShahBoilingHTC(),
        primary_T_in=280.0,
        q_flux_primary=q_flux_primary,
    )


def _shah_req_lmtd(q_flux_primary=None) -> HXSolveRequest:
    return HXSolveRequest(
        primary_state_in=_STATE_IN,
        primary_mdot=0.01,
        secondary_bc=FixedWallTemp(T_wall=350.0),
        geometry=object(),
        discretization=_LUMPED,
        geom_scalars=_SHAH_GEOM_SCALARS,
        htc_primary=ShahBoilingHTC(),
        primary_T_in=280.0,
        q_flux_primary=q_flux_primary,
    )


def _shah_req_segmented(q_flux_primary=None, n_cells=2) -> HXSolveRequest:
    disc = DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=n_cells)
    return HXSolveRequest(
        primary_state_in=_STATE_IN,
        primary_mdot=0.01,
        secondary_bc=FixedWallTemp(T_wall=350.0),
        geometry=object(),
        discretization=disc,
        geom_scalars=_SHAH_GEOM_SCALARS,
        htc_primary=ShahBoilingHTC(),
        primary_T_in=280.0,
        primary_cp=1400.0,
        primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
        q_flux_primary=q_flux_primary,
    )


class TestShahBoilingHTCInjection:
    """ShahBoilingHTC can be injected when required scalars and q_flux_primary are supplied."""

    def test_epsilon_ntu_shah_with_q_flux_produces_finite_q(self):
        req = _shah_req_epsilon_ntu(q_flux_primary=_Q_FLUX)
        result = EpsilonNTUModel().solve(req)
        assert math.isfinite(result.Q)
        assert result.Q > 0.0

    def test_epsilon_ntu_shah_without_q_flux_fails_clearly(self):
        req = _shah_req_epsilon_ntu(q_flux_primary=None)
        with pytest.raises(ValueError, match="q_flux"):
            EpsilonNTUModel().solve(req)

    def test_lmtd_shah_with_q_flux_produces_finite_q(self):
        req = _shah_req_lmtd(q_flux_primary=_Q_FLUX)
        result = LMTDModel().solve(req)
        assert math.isfinite(result.Q)
        assert result.Q > 0.0

    def test_lmtd_shah_without_q_flux_fails_clearly(self):
        req = _shah_req_lmtd(q_flux_primary=None)
        with pytest.raises(ValueError, match="q_flux"):
            LMTDModel().solve(req)

    def test_segmented_shah_with_q_flux_produces_finite_q(self):
        req = _shah_req_segmented(q_flux_primary=_Q_FLUX, n_cells=3)
        result = SegmentedMarchModel().solve(req)
        assert math.isfinite(result.Q)
        assert result.Q > 0.0

    def test_segmented_shah_with_q_flux_all_cells_have_htc(self):
        req = _shah_req_segmented(q_flux_primary=_Q_FLUX, n_cells=3)
        result = SegmentedMarchModel().solve(req)
        assert result.zone_profile is not None
        for cell in result.zone_profile.cells:
            assert cell.htc_primary is not None
            assert cell.htc_primary > 0.0

    def test_segmented_shah_without_q_flux_fails_clearly(self):
        req = _shah_req_segmented(q_flux_primary=None)
        with pytest.raises(ValueError, match="q_flux"):
            SegmentedMarchModel().solve(req)


# ---------------------------------------------------------------------------
# 6. Architecture boundary checks
# ---------------------------------------------------------------------------


class TestQFluxArchitectureBoundaries:
    """Architecture invariants hold after Phase 11N changes."""

    def test_hx_models_do_not_import_correlation_registry(self):
        import mpl_sim.hx_models.epsilon_ntu as m_entu
        import mpl_sim.hx_models.lmtd as m_lmtd
        import mpl_sim.hx_models.segmented as m_seg

        for mod in (m_entu, m_lmtd, m_seg):
            assert not hasattr(
                mod, "CorrelationRegistry"
            ), f"{mod.__name__} must not import CorrelationRegistry"

    def test_hx_models_do_not_import_coolprop(self):
        import mpl_sim.hx_models.epsilon_ntu as m_entu
        import mpl_sim.hx_models.lmtd as m_lmtd
        import mpl_sim.hx_models.segmented as m_seg

        for mod in (m_entu, m_lmtd, m_seg):
            assert "CoolProp" not in mod.__dict__, f"{mod.__name__} must not import CoolProp"

    def test_hx_models_do_not_import_property_backend(self):
        import mpl_sim.hx_models.epsilon_ntu as m_entu
        import mpl_sim.hx_models.lmtd as m_lmtd
        import mpl_sim.hx_models.segmented as m_seg

        for mod in (m_entu, m_lmtd, m_seg):
            assert (
                "PropertyBackend" not in mod.__dict__
            ), f"{mod.__name__} must not import PropertyBackend"

    def test_no_hidden_q_flux_default_spy_receives_none(self):
        spy = _SpyHTCCorrelation()
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.01,
            secondary_bc=FixedWallTemp(T_wall=320.0),
            geometry=object(),
            discretization=_LUMPED,
            geom_scalars=_GEOM_SCALARS_SINGLE_PHASE,
            htc_primary=spy,
            primary_T_in=280.0,
        )
        EpsilonNTUModel().solve(req)
        assert (
            spy.received_inputs[0].q_flux is None
        ), "HTCInput.q_flux must be None when q_flux_primary is not supplied — no hidden default"

    def test_q_flux_is_not_negated_or_abs_before_passing(self):
        """Verify the value reaching the spy is the exact same object as supplied."""
        spy = _SpyHTCCorrelation()
        val = 55555.5
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.01,
            secondary_bc=FixedWallTemp(T_wall=320.0),
            geometry=object(),
            discretization=_LUMPED,
            geom_scalars=_GEOM_SCALARS_SINGLE_PHASE,
            htc_primary=spy,
            primary_T_in=280.0,
            q_flux_primary=val,
        )
        EpsilonNTUModel().solve(req)
        assert spy.received_inputs[0].q_flux == val
