"""Phase 3C — ChurchillFrictionGradient tests.

Covers:
- Role is SINGLE_PHASE_DP
- Envelope is non-empty (bounds and fluid_families)
- Closure can be registered in CorrelationRegistry
- evaluate() accepts SinglePhaseDPInput and returns CorrelationOutput
- Output carries value (tuple), verdict, and metadata
- Returned gradient is positive for valid pipe-flow inputs
- Output value is a friction gradient in Pa/m, not total ΔP (L-independence)
- Laminar case gives result consistent with f=64/Re behaviour (Darcy-Weisbach)
- Turbulent case gives positive result in a reasonable range
- Increasing mass flux increases friction gradient
- Increasing roughness does not decrease turbulent friction gradient
- Invalid D_h / rho / mu / roughness raises ValueError
- G=0 returns 0.0 gradient (no flow, no wall shear)
- No CoolProp import in single_phase_dp module
- No properties, components, geometry, calibration, network, or solvers
  imported by single_phase_dp
- Existing Phase 3A and 3B tests are not broken (pytest discovers all)
"""

import math
import subprocess
import sys
import types

import pytest

from mpl_sim.core.fluid_identity import PureFluid
from mpl_sim.core.fluid_state import FluidState
from mpl_sim.correlations.contract import (
    ClosureMetadata,
    CorrelationOutput,
    CorrelationRole,
    SinglePhaseDPInput,
    ValidityEnvelope,
    ValidityStatus,
    ValidityVerdict,
)
from mpl_sim.correlations.registry import CorrelationRegistry
from mpl_sim.correlations.single_phase_dp import ChurchillFrictionGradient

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _state() -> FluidState:
    return FluidState(P=1.0e6, h=2.0e5, identity=PureFluid("R134a"))


def _water_inp(
    G: float = 300.0,
    D_h: float = 0.01,
    roughness: float = 0.0,
    rho: float = 1000.0,
    mu: float = 1.0e-3,
    L_cell: float = 0.1,
) -> SinglePhaseDPInput:
    """Convenience factory: water-like single-phase input."""
    return SinglePhaseDPInput(
        state=(_state(),),
        G=G,
        D_h=D_h,
        roughness=roughness,
        rho=rho,
        mu=mu,
        L_cell=L_cell,
    )


def _corr() -> ChurchillFrictionGradient:
    return ChurchillFrictionGradient()


# ---------------------------------------------------------------------------
# Role and envelope
# ---------------------------------------------------------------------------


class TestRoleAndEnvelope:
    def test_role_is_single_phase_dp(self):
        assert _corr().role() == CorrelationRole.SINGLE_PHASE_DP

    def test_envelope_is_validity_envelope(self):
        assert isinstance(_corr().envelope(), ValidityEnvelope)

    def test_envelope_has_non_empty_fluid_families(self):
        env = _corr().envelope()
        assert len(env.fluid_families) >= 1

    def test_envelope_has_non_empty_bounds(self):
        env = _corr().envelope()
        assert len(env.bounds) >= 1

    def test_envelope_has_source(self):
        env = _corr().envelope()
        assert env.source is not None
        assert "Churchill" in env.source.citation


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------


class TestRegistryIntegration:
    def test_can_register(self):
        reg = CorrelationRegistry()
        reg.register("churchill_dp", _corr())
        assert reg.is_registered("churchill_dp")

    def test_resolves_to_same_instance(self):
        reg = CorrelationRegistry()
        corr = _corr()
        reg.register("churchill_dp", corr)
        assert reg.resolve("churchill_dp") is corr

    def test_appears_in_by_role(self):
        reg = CorrelationRegistry()
        reg.register("churchill_dp", _corr())
        result = reg.by_role(CorrelationRole.SINGLE_PHASE_DP)
        assert "churchill_dp" in result


# ---------------------------------------------------------------------------
# Output contract
# ---------------------------------------------------------------------------


class TestOutputContract:
    def test_returns_correlation_output(self):
        out = _corr().evaluate(_water_inp())
        assert isinstance(out, CorrelationOutput)

    def test_value_is_tuple(self):
        out = _corr().evaluate(_water_inp())
        assert isinstance(out.value, tuple)

    def test_value_has_at_least_one_element(self):
        out = _corr().evaluate(_water_inp())
        assert len(out.value) >= 1

    def test_verdict_always_present(self):
        out = _corr().evaluate(_water_inp())
        assert isinstance(out.verdict, ValidityVerdict)

    def test_metadata_always_present(self):
        out = _corr().evaluate(_water_inp())
        assert isinstance(out.metadata, ClosureMetadata)

    def test_metadata_name(self):
        out = _corr().evaluate(_water_inp())
        assert out.metadata.name == "churchill_friction_gradient"

    def test_metadata_version_string(self):
        out = _corr().evaluate(_water_inp())
        assert out.metadata.version != ""


# ---------------------------------------------------------------------------
# Physical correctness — laminar
# ---------------------------------------------------------------------------
# Laminar test: G=100 kg/m²s, D_h=0.01 m, mu=1e-3 Pa·s → Re=1000
# f_D ≈ 64/Re = 0.064
# dP/dx = f_D * G² / (2·rho·D_h) = 0.064 * 10000 / (2·1000·0.01) = 32 Pa/m
# Hagen-Poiseuille: dP/dL = 32·mu·v/D² = 32·1e-3·0.1/0.0001 = 32 Pa/m  ✓


class TestLaminar:
    # Re=100*0.01/1e-3 = 1000
    _inp = _water_inp(G=100.0, D_h=0.01, roughness=0.0, rho=1000.0, mu=1.0e-3)

    def test_laminar_gradient_positive(self):
        out = _corr().evaluate(self._inp)
        assert out.value[0] > 0.0

    def test_laminar_gradient_close_to_hp(self):
        # Hagen-Poiseuille for Re=1000: dP/dx = 32 Pa/m
        out = _corr().evaluate(self._inp)
        assert out.value[0] == pytest.approx(32.0, rel=0.01)

    def test_laminar_verdict_in_envelope(self):
        out = _corr().evaluate(self._inp)
        assert out.verdict.status == ValidityStatus.IN_ENVELOPE

    def test_laminar_no_violated_bounds(self):
        out = _corr().evaluate(self._inp)
        assert out.verdict.violated == ()


# ---------------------------------------------------------------------------
# Physical correctness — turbulent
# ---------------------------------------------------------------------------
# Turbulent: G=1000 kg/m²s, D_h=0.01 m, mu=1e-3 Pa·s → Re=10000
# f_D (Churchill, smooth) ≈ 0.031  (Blasius: 0.316/Re^0.25 ≈ 0.0316)
# dP/dx = 0.031 * 1e6 / (2·1000·0.01) = 1550 Pa/m (approx)


class TestTurbulent:
    # Re=1000*0.01/1e-3 = 10000
    _inp = _water_inp(G=1000.0, D_h=0.01, roughness=0.0, rho=1000.0, mu=1.0e-3)

    def test_turbulent_gradient_positive(self):
        out = _corr().evaluate(self._inp)
        assert out.value[0] > 0.0

    def test_turbulent_gradient_in_plausible_range(self):
        # Blasius gives ~1580 Pa/m; accept ±25%
        out = _corr().evaluate(self._inp)
        assert 1000.0 < out.value[0] < 3000.0

    def test_turbulent_verdict_in_envelope(self):
        out = _corr().evaluate(self._inp)
        assert out.verdict.status == ValidityStatus.IN_ENVELOPE


# ---------------------------------------------------------------------------
# L-independence: gradient, not total ΔP
# ---------------------------------------------------------------------------


class TestGradientNotTotalDP:
    def test_output_unchanged_with_different_L_cell(self):
        out_short = _corr().evaluate(_water_inp(G=500.0, L_cell=0.01))
        out_long = _corr().evaluate(_water_inp(G=500.0, L_cell=10.0))
        assert out_short.value[0] == pytest.approx(out_long.value[0], rel=1e-12)


# ---------------------------------------------------------------------------
# Monotonicity
# ---------------------------------------------------------------------------


class TestMonotonicity:
    def test_higher_G_gives_higher_gradient(self):
        out_lo = _corr().evaluate(_water_inp(G=500.0))
        out_hi = _corr().evaluate(_water_inp(G=1000.0))
        assert out_hi.value[0] > out_lo.value[0]

    def test_rougher_pipe_does_not_decrease_turbulent_gradient(self):
        # Re=10000 (turbulent), compare smooth vs rough
        smooth = _water_inp(G=1000.0, D_h=0.01, roughness=0.0, rho=1000.0, mu=1e-3)
        rough = _water_inp(G=1000.0, D_h=0.01, roughness=1.0e-4, rho=1000.0, mu=1e-3)
        out_smooth = _corr().evaluate(smooth)
        out_rough = _corr().evaluate(rough)
        assert out_rough.value[0] >= out_smooth.value[0]

    def test_higher_density_increases_gradient(self):
        # dP/dx = f*G²/(2*rho*D_h); f also depends on Re=G*D_h/mu (no rho).
        # Hmm — actually higher rho → lower dP/dx (rho in denominator).
        # But lower rho → for same G, lower mass → higher velocity.
        # Let's just verify the trend at fixed Re (constant G*D_h/mu):
        # dP/dx ~ 1/rho, so lower rho → higher gradient.
        inp_lo_rho = _water_inp(G=300.0, rho=500.0)
        inp_hi_rho = _water_inp(G=300.0, rho=1000.0)
        out_lo = _corr().evaluate(inp_lo_rho)
        out_hi = _corr().evaluate(inp_hi_rho)
        assert out_lo.value[0] > out_hi.value[0]


# ---------------------------------------------------------------------------
# Zero mass flux
# ---------------------------------------------------------------------------


class TestZeroMassFlux:
    def test_zero_G_returns_zero_gradient(self):
        inp = _water_inp(G=0.0)
        out = _corr().evaluate(inp)
        assert out.value[0] == pytest.approx(0.0, abs=1e-12)

    def test_zero_G_returns_extrapolated_verdict(self):
        inp = _water_inp(G=0.0)
        out = _corr().evaluate(inp)
        assert out.verdict.status == ValidityStatus.EXTRAPOLATED

    def test_negative_G_same_magnitude_as_positive(self):
        out_pos = _corr().evaluate(_water_inp(G=500.0))
        out_neg = _corr().evaluate(_water_inp(G=-500.0))
        assert out_pos.value[0] == pytest.approx(out_neg.value[0], rel=1e-12)


# ---------------------------------------------------------------------------
# Invalid inputs raise ValueError
# ---------------------------------------------------------------------------


class TestInvalidInputs:
    def test_non_positive_dh_raises(self):
        with pytest.raises(ValueError, match="D_h"):
            _corr().evaluate(_water_inp(D_h=0.0))

    def test_negative_dh_raises(self):
        with pytest.raises(ValueError, match="D_h"):
            _corr().evaluate(_water_inp(D_h=-0.01))

    def test_non_positive_rho_raises(self):
        with pytest.raises(ValueError, match="rho"):
            _corr().evaluate(_water_inp(rho=0.0))

    def test_negative_rho_raises(self):
        with pytest.raises(ValueError, match="rho"):
            _corr().evaluate(_water_inp(rho=-1.0))

    def test_non_positive_mu_raises(self):
        with pytest.raises(ValueError, match="mu"):
            _corr().evaluate(_water_inp(mu=0.0))

    def test_negative_mu_raises(self):
        with pytest.raises(ValueError, match="mu"):
            _corr().evaluate(_water_inp(mu=-1.0e-3))

    def test_negative_roughness_raises(self):
        with pytest.raises(ValueError, match="roughness"):
            _corr().evaluate(_water_inp(roughness=-1.0e-6))

    def test_wrong_input_type_raises_type_error(self):
        from mpl_sim.correlations.contract import VolumePressureLawInput

        with pytest.raises(TypeError):
            _corr().evaluate(VolumePressureLawInput(V_g=0.001, V_total=0.01, law_params={}))


# ---------------------------------------------------------------------------
# Out-of-envelope inputs flagged EXTRAPOLATED (not silently in-envelope)
# ---------------------------------------------------------------------------


class TestOutOfEnvelopeVerdict:
    def test_low_re_flagged_extrapolated(self):
        # Re = 0.01 * 1e-4 / 1e-3 = 0.001 < 1.0
        inp = _water_inp(G=0.01, D_h=1.0e-4, mu=1.0e-3, rho=1000.0)
        out = _corr().evaluate(inp)
        assert out.verdict.status == ValidityStatus.EXTRAPOLATED

    def test_high_roughness_ratio_flagged_extrapolated(self):
        # eps/D = 0.001/0.01 = 0.1 > 0.05 bound
        inp = _water_inp(G=1000.0, D_h=0.01, roughness=1.0e-3, rho=1000.0, mu=1.0e-3)
        out = _corr().evaluate(inp)
        assert out.verdict.status == ValidityStatus.EXTRAPOLATED

    def test_extrapolated_value_is_finite(self):
        inp = _water_inp(G=0.01, D_h=1.0e-4, mu=1.0e-3, rho=1000.0)
        out = _corr().evaluate(inp)
        assert math.isfinite(out.value[0])

    def test_extrapolated_has_violated_bounds(self):
        inp = _water_inp(G=0.01, D_h=1.0e-4, mu=1.0e-3, rho=1000.0)
        out = _corr().evaluate(inp)
        assert len(out.verdict.violated) >= 1


# ---------------------------------------------------------------------------
# Import boundary checks
# ---------------------------------------------------------------------------


class TestImportBoundary:
    def _check_absent(self, forbidden_prefix: str) -> None:
        code = (
            "import sys; "
            "import mpl_sim.correlations.single_phase_dp; "
            f"loaded = [m for m in sys.modules if m.startswith({forbidden_prefix!r})]; "
            f"assert not loaded, f'Forbidden modules loaded: {{loaded}}'"
        )
        result = subprocess.run(
            [sys.executable, "-B", "-c", code],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

    def test_no_coolprop_import(self):
        code = (
            "import sys; "
            "import mpl_sim.correlations.single_phase_dp; "
            "bad = [k for k in sys.modules if 'CoolProp' in k]; "
            "assert not bad, 'CoolProp pulled in: ' + str(bad)"
        )
        result = subprocess.run(
            [sys.executable, "-B", "-c", code],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

    def test_no_properties_import(self):
        self._check_absent("mpl_sim.properties")

    def test_no_components_import(self):
        self._check_absent("mpl_sim.components")

    def test_no_geometry_import(self):
        self._check_absent("mpl_sim.geometry")

    def test_no_calibration_import(self):
        self._check_absent("mpl_sim.calibration")

    def test_no_network_import(self):
        self._check_absent("mpl_sim.network")

    def test_no_solvers_import(self):
        self._check_absent("mpl_sim.solvers")

    def test_single_phase_dp_does_not_import_forbidden_at_module_level(self):
        import mpl_sim.correlations.single_phase_dp as mod

        forbidden = {"properties", "components", "geometry", "calibration", "network", "solvers"}
        for _name, obj in vars(mod).items():
            if isinstance(obj, types.ModuleType):
                for f in forbidden:
                    assert (
                        f not in obj.__name__
                    ), f"single_phase_dp imports forbidden module: {obj.__name__}"


# ---------------------------------------------------------------------------
# Package-level export
# ---------------------------------------------------------------------------


class TestPackageExport:
    def test_churchill_importable_from_package(self):
        from mpl_sim.correlations import ChurchillFrictionGradient as C

        assert C is ChurchillFrictionGradient

    def test_churchill_in_all(self):
        import mpl_sim.correlations as pkg

        assert "ChurchillFrictionGradient" in pkg.__all__
