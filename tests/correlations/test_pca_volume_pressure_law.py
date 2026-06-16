"""PCA volume-pressure law numerical tests -- Phase 10G.

Verifies:
  - PCA returns positive pressure for valid inputs
  - PCA is monotonically decreasing in V_g
  - PCA agrees with hand-calculated reference cases
  - Missing/invalid law_params raise ValueError
  - Wrong input type raises TypeError
"""

from __future__ import annotations

import math

import pytest

from mpl_sim.correlations.contract import (
    CorrelationRole,
    ValidityStatus,
    VolumePressureLawInput,
)
from mpl_sim.correlations.volume_pressure_law import PcaVolumePressureLaw


def _pca_inp(V_g: float, V_total: float = 0.010, **overrides) -> VolumePressureLawInput:
    params = {
        "charge_volume": 0.005,
        "charge_pressure": 1_000_000.0,
        "polytropic_index": 1.4,
    }
    params.update(overrides)
    return VolumePressureLawInput(V_g=V_g, V_total=V_total, law_params=params)


PCA = PcaVolumePressureLaw()

# ---------------------------------------------------------------------------
# Pressure positivity
# ---------------------------------------------------------------------------


class TestPcaPressurePositivity:
    def test_pressure_positive_at_charge_point(self) -> None:
        out = PCA.evaluate(_pca_inp(V_g=0.005))
        assert out.value[0] > 0.0

    def test_pressure_positive_for_V_g_less_than_charge(self) -> None:
        out = PCA.evaluate(_pca_inp(V_g=0.003))
        assert out.value[0] > 0.0

    def test_pressure_positive_for_V_g_greater_than_charge(self) -> None:
        out = PCA.evaluate(_pca_inp(V_g=0.008))
        assert out.value[0] > 0.0

    def test_pressure_positive_for_very_small_V_g(self) -> None:
        out = PCA.evaluate(_pca_inp(V_g=1e-9))
        assert out.value[0] > 0.0

    def test_pressure_finite_for_normal_inputs(self) -> None:
        out = PCA.evaluate(_pca_inp(V_g=0.005))
        assert math.isfinite(out.value[0])


# ---------------------------------------------------------------------------
# Monotonicity in V_g
# ---------------------------------------------------------------------------


class TestPcaMonotonicity:
    def test_pressure_decreases_as_V_g_increases(self) -> None:
        V_g_vals = [0.001, 0.002, 0.004, 0.006, 0.008, 0.010]
        pressures = [PCA.evaluate(_pca_inp(V_g=v)).value[0] for v in V_g_vals]
        for i in range(len(pressures) - 1):
            assert pressures[i] > pressures[i + 1], (
                f"Pressure not monotonically decreasing at V_g[{i}]={V_g_vals[i]!r}: "
                f"P={pressures[i]!r} <= P_next={pressures[i + 1]!r}"
            )

    def test_pressure_equals_charge_pressure_at_charge_volume(self) -> None:
        V_charge = 0.005
        P_charge = 1_000_000.0
        out = PCA.evaluate(
            VolumePressureLawInput(
                V_g=V_charge,
                V_total=0.010,
                law_params={
                    "charge_volume": V_charge,
                    "charge_pressure": P_charge,
                    "polytropic_index": 1.4,
                },
            )
        )
        assert out.value[0] == pytest.approx(P_charge, rel=1e-9)

    def test_pressure_greater_than_charge_when_V_g_less_than_V_charge(self) -> None:
        V_charge = 0.005
        P_charge = 1_000_000.0
        out = PCA.evaluate(
            VolumePressureLawInput(
                V_g=0.003,  # compressed more than charge
                V_total=0.010,
                law_params={
                    "charge_volume": V_charge,
                    "charge_pressure": P_charge,
                    "polytropic_index": 1.4,
                },
            )
        )
        assert out.value[0] > P_charge

    def test_pressure_less_than_charge_when_V_g_greater_than_V_charge(self) -> None:
        V_charge = 0.005
        P_charge = 1_000_000.0
        out = PCA.evaluate(
            VolumePressureLawInput(
                V_g=0.008,  # expanded past charge
                V_total=0.010,
                law_params={
                    "charge_volume": V_charge,
                    "charge_pressure": P_charge,
                    "polytropic_index": 1.4,
                },
            )
        )
        assert out.value[0] < P_charge


# ---------------------------------------------------------------------------
# Hand-calculated reference cases
# ---------------------------------------------------------------------------
#
# PCA law: P = P_charge * (V_charge / V_g) ^ n
#
# Reference case 1 (isothermal, n=1):
#   V_charge=0.005, P_charge=1e6, n=1.0, V_g=0.010
#   P = 1e6 * (0.005 / 0.010) ^ 1.0 = 1e6 * 0.5 = 500_000 Pa
#
# Reference case 2 (polytropic, n=1.4):
#   V_charge=0.005, P_charge=2e6, n=1.4, V_g=0.010
#   P = 2e6 * (0.005/0.010)^1.4 = 2e6 * 0.5^1.4
#   0.5^1.4 = exp(1.4 * ln(0.5)) = exp(1.4 * (-0.693147...)) = exp(-0.970406...) = 0.379366...
#   P = 2e6 * 0.379366 = 758_731 Pa  (rounded to integer precision)
#
# Reference case 3 (charge volume larger than V_g, n=1.0):
#   V_charge=0.010, P_charge=5e5, n=1.0, V_g=0.005
#   P = 5e5 * (0.010 / 0.005) ^ 1.0 = 5e5 * 2 = 1_000_000 Pa
#
# Reference case 4 (charge volume == V_g, any n):
#   P = P_charge * 1^n = P_charge
#   Tested with V_charge=V_g=0.007, P_charge=1.5e6, n=1.3
#   P = 1_500_000 Pa
#
# Reference case 5 (large V_g, EXTRAPOLATED verdict):
#   V_charge=0.005, P_charge=1e6, n=1.4, V_total=0.010, V_g=0.015
#   P = 1e6 * (0.005/0.015)^1.4 = 1e6 * (1/3)^1.4
#   (1/3)^1.4 = exp(1.4 * ln(1/3)) = exp(1.4 * (-1.098612...)) = exp(-1.538057...) = 0.214765...
#   P ~ 214_765 Pa


class TestPcaReferenceValues:
    def test_reference_1_isothermal_half_volume(self) -> None:
        out = PCA.evaluate(
            VolumePressureLawInput(
                V_g=0.010,
                V_total=0.020,
                law_params={
                    "charge_volume": 0.005,
                    "charge_pressure": 1_000_000.0,
                    "polytropic_index": 1.0,
                },
            )
        )
        expected = 500_000.0
        assert out.value[0] == pytest.approx(expected, rel=1e-9)

    def test_reference_2_polytropic_n14(self) -> None:
        out = PCA.evaluate(
            VolumePressureLawInput(
                V_g=0.010,
                V_total=0.020,
                law_params={
                    "charge_volume": 0.005,
                    "charge_pressure": 2_000_000.0,
                    "polytropic_index": 1.4,
                },
            )
        )
        expected = 2_000_000.0 * (0.005 / 0.010) ** 1.4
        assert out.value[0] == pytest.approx(expected, rel=1e-9)

    def test_reference_3_compressed_isothermal(self) -> None:
        out = PCA.evaluate(
            VolumePressureLawInput(
                V_g=0.005,
                V_total=0.020,
                law_params={
                    "charge_volume": 0.010,
                    "charge_pressure": 500_000.0,
                    "polytropic_index": 1.0,
                },
            )
        )
        expected = 1_000_000.0
        assert out.value[0] == pytest.approx(expected, rel=1e-9)

    def test_reference_4_charge_point_identity(self) -> None:
        P_charge = 1_500_000.0
        out = PCA.evaluate(
            VolumePressureLawInput(
                V_g=0.007,
                V_total=0.020,
                law_params={
                    "charge_volume": 0.007,
                    "charge_pressure": P_charge,
                    "polytropic_index": 1.3,
                },
            )
        )
        assert out.value[0] == pytest.approx(P_charge, rel=1e-9)

    def test_reference_5_extrapolated_large_V_g(self) -> None:
        out = PCA.evaluate(
            VolumePressureLawInput(
                V_g=0.015,
                V_total=0.010,
                law_params={
                    "charge_volume": 0.005,
                    "charge_pressure": 1_000_000.0,
                    "polytropic_index": 1.4,
                },
            )
        )
        expected = 1_000_000.0 * (0.005 / 0.015) ** 1.4
        assert out.value[0] == pytest.approx(expected, rel=1e-9)
        assert out.verdict.status is ValidityStatus.EXTRAPOLATED


# ---------------------------------------------------------------------------
# Validity verdict details
# ---------------------------------------------------------------------------


class TestPcaValidityVerdicts:
    def test_in_envelope_when_V_g_at_V_total(self) -> None:
        out = PCA.evaluate(_pca_inp(V_g=0.010, V_total=0.010))
        assert out.verdict.status is ValidityStatus.IN_ENVELOPE

    def test_in_envelope_when_V_g_well_below_V_total(self) -> None:
        out = PCA.evaluate(_pca_inp(V_g=0.003, V_total=0.010))
        assert out.verdict.status is ValidityStatus.IN_ENVELOPE

    def test_extrapolated_when_V_g_just_above_V_total(self) -> None:
        out = PCA.evaluate(_pca_inp(V_g=0.0101, V_total=0.010))
        assert out.verdict.status is ValidityStatus.EXTRAPOLATED

    def test_out_of_range_when_V_g_is_zero(self) -> None:
        out = PCA.evaluate(_pca_inp(V_g=0.0))
        assert out.verdict.status is ValidityStatus.OUT_OF_RANGE

    def test_out_of_range_when_V_g_is_negative(self) -> None:
        out = PCA.evaluate(_pca_inp(V_g=-0.005))
        assert out.verdict.status is ValidityStatus.OUT_OF_RANGE

    def test_out_of_range_when_V_g_is_nan(self) -> None:
        out = PCA.evaluate(_pca_inp(V_g=math.nan))
        assert out.verdict.status is ValidityStatus.OUT_OF_RANGE

    def test_out_of_range_returns_nan_value(self) -> None:
        out = PCA.evaluate(_pca_inp(V_g=0.0))
        assert math.isnan(out.value[0])

    def test_role_is_volume_pressure_law(self) -> None:
        assert PCA.role() is CorrelationRole.VOLUME_PRESSURE_LAW


# ---------------------------------------------------------------------------
# Missing / invalid law_params
# ---------------------------------------------------------------------------


class TestPcaLawParamValidation:
    def test_missing_charge_volume_raises(self) -> None:
        inp = VolumePressureLawInput(
            V_g=0.005,
            V_total=0.010,
            law_params={
                "charge_pressure": 1_000_000.0,
                "polytropic_index": 1.4,
            },
        )
        with pytest.raises(ValueError, match="charge_volume"):
            PCA.evaluate(inp)

    def test_missing_charge_pressure_raises(self) -> None:
        inp = VolumePressureLawInput(
            V_g=0.005,
            V_total=0.010,
            law_params={
                "charge_volume": 0.005,
                "polytropic_index": 1.4,
            },
        )
        with pytest.raises(ValueError, match="charge_pressure"):
            PCA.evaluate(inp)

    def test_missing_polytropic_index_raises(self) -> None:
        inp = VolumePressureLawInput(
            V_g=0.005,
            V_total=0.010,
            law_params={
                "charge_volume": 0.005,
                "charge_pressure": 1_000_000.0,
            },
        )
        with pytest.raises(ValueError, match="polytropic_index"):
            PCA.evaluate(inp)

    def test_zero_charge_volume_raises(self) -> None:
        inp = VolumePressureLawInput(
            V_g=0.005,
            V_total=0.010,
            law_params={
                "charge_volume": 0.0,
                "charge_pressure": 1_000_000.0,
                "polytropic_index": 1.4,
            },
        )
        with pytest.raises(ValueError, match="charge_volume"):
            PCA.evaluate(inp)

    def test_negative_charge_pressure_raises(self) -> None:
        inp = VolumePressureLawInput(
            V_g=0.005,
            V_total=0.010,
            law_params={
                "charge_volume": 0.005,
                "charge_pressure": -1.0,
                "polytropic_index": 1.4,
            },
        )
        with pytest.raises(ValueError, match="charge_pressure"):
            PCA.evaluate(inp)

    def test_zero_polytropic_index_raises(self) -> None:
        inp = VolumePressureLawInput(
            V_g=0.005,
            V_total=0.010,
            law_params={
                "charge_volume": 0.005,
                "charge_pressure": 1_000_000.0,
                "polytropic_index": 0.0,
            },
        )
        with pytest.raises(ValueError, match="polytropic_index"):
            PCA.evaluate(inp)


# ---------------------------------------------------------------------------
# Wrong input type
# ---------------------------------------------------------------------------


class TestPcaWrongInputType:
    def test_non_vpl_input_raises_type_error(self) -> None:
        with pytest.raises(TypeError):
            PCA.evaluate(object())  # type: ignore[arg-type]

    def test_dict_input_raises_type_error(self) -> None:
        with pytest.raises(TypeError):
            PCA.evaluate(  # type: ignore[arg-type]
                {"V_g": 0.005, "V_total": 0.010, "law_params": {}}
            )
