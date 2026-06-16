"""VolumePressureLawInput contract tests -- Phase 10G.

Verifies that VolumePressureLawInput satisfies the correlation contract:
  - scalar/data-only inputs (no Component, no Geometry objects)
  - law_params is immutable (MappingProxyType)
  - positive volumes accepted; law_params key-value structure
  - VOLUME_PRESSURE_LAW role is present in CorrelationRole
  - PcaVolumePressureLaw is registered-ready (envelope present, role correct)
  - CorrelationOutput shape respected (value tuple, verdict, metadata always present)
  - No import of Component, Geometry, Network, Solver, CoolProp, or properties
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

# ---------------------------------------------------------------------------
# VOLUME_PRESSURE_LAW role exists
# ---------------------------------------------------------------------------


class TestVolumePressureLawRole:
    def test_role_exists_in_enum(self) -> None:
        assert hasattr(CorrelationRole, "VOLUME_PRESSURE_LAW")

    def test_role_is_enumeration_member(self) -> None:
        assert isinstance(CorrelationRole.VOLUME_PRESSURE_LAW, CorrelationRole)

    def test_pca_reports_correct_role(self) -> None:
        pca = PcaVolumePressureLaw()
        assert pca.role() is CorrelationRole.VOLUME_PRESSURE_LAW


# ---------------------------------------------------------------------------
# VolumePressureLawInput construction and contract
# ---------------------------------------------------------------------------


def _make_pca_params() -> dict:
    return {
        "charge_volume": 0.005,
        "charge_pressure": 1_000_000.0,
        "polytropic_index": 1.4,
    }


class TestVolumePressureLawInputConstruction:
    def test_basic_construction(self) -> None:
        inp = VolumePressureLawInput(
            V_g=0.005,
            V_total=0.010,
            law_params=_make_pca_params(),
        )
        assert inp.V_g == pytest.approx(0.005)
        assert inp.V_total == pytest.approx(0.010)

    def test_is_immutable_dataclass(self) -> None:
        inp = VolumePressureLawInput(V_g=0.005, V_total=0.01, law_params=_make_pca_params())
        with pytest.raises((AttributeError, TypeError)):
            inp.V_g = 0.006  # type: ignore[misc]

    def test_law_params_is_immutable_mapping(self) -> None:
        params = _make_pca_params()
        inp = VolumePressureLawInput(V_g=0.005, V_total=0.01, law_params=params)
        with pytest.raises((TypeError, AttributeError)):
            inp.law_params["new_key"] = 1.0  # type: ignore[index]

    def test_law_params_mutation_of_source_dict_does_not_affect_input(self) -> None:
        params = _make_pca_params()
        inp = VolumePressureLawInput(V_g=0.005, V_total=0.01, law_params=params)
        params["charge_volume"] = 999.0
        assert inp.law_params["charge_volume"] == pytest.approx(0.005)

    def test_state_optional_defaults_to_none(self) -> None:
        inp = VolumePressureLawInput(V_g=0.005, V_total=0.01, law_params=_make_pca_params())
        assert inp.state is None

    def test_thermal_optional_defaults_to_none(self) -> None:
        inp = VolumePressureLawInput(V_g=0.005, V_total=0.01, law_params=_make_pca_params())
        assert inp.thermal is None

    def test_p_set_optional_defaults_to_none(self) -> None:
        inp = VolumePressureLawInput(V_g=0.005, V_total=0.01, law_params=_make_pca_params())
        assert inp.P_set is None

    def test_input_carries_no_component_objects(self) -> None:
        inp = VolumePressureLawInput(V_g=0.005, V_total=0.01, law_params=_make_pca_params())
        forbidden = ("component", "Component", "pump", "accumulator", "pipe")
        for attr in forbidden:
            assert not hasattr(inp, attr), f"Input must not carry a {attr!r} attribute"

    def test_input_carries_no_geometry_objects(self) -> None:
        inp = VolumePressureLawInput(V_g=0.005, V_total=0.01, law_params=_make_pca_params())
        forbidden = ("geometry", "Geometry", "AccumulatorGeometry")
        for attr in forbidden:
            assert not hasattr(inp, attr), f"Input must not carry a {attr!r} attribute"

    def test_law_params_not_in_geometry(self) -> None:
        # Law parameters must live in law_params, not in any geometry object.
        params = _make_pca_params()
        inp = VolumePressureLawInput(V_g=0.005, V_total=0.01, law_params=params)
        # Verify the geometry-forbidden keys do not appear on inp itself.
        geom_forbidden = (
            "V_gas_charge",
            "spring_rate",
            "bellows_area",
            "gas_constant",
            "P_sys",
        )
        for attr in geom_forbidden:
            assert not hasattr(inp, attr), f"Law param {attr!r} must not be on inp directly"


# ---------------------------------------------------------------------------
# PcaVolumePressureLaw envelope contract
# ---------------------------------------------------------------------------


class TestPcaEnvelopeContract:
    def test_envelope_is_not_none(self) -> None:
        pca = PcaVolumePressureLaw()
        assert pca.envelope() is not None

    def test_envelope_has_fluid_families(self) -> None:
        pca = PcaVolumePressureLaw()
        assert len(pca.envelope().fluid_families) >= 1

    def test_envelope_has_bounds(self) -> None:
        pca = PcaVolumePressureLaw()
        assert len(pca.envelope().bounds) >= 1

    def test_envelope_has_source(self) -> None:
        pca = PcaVolumePressureLaw()
        assert pca.envelope().source is not None
        assert pca.envelope().source.citation


# ---------------------------------------------------------------------------
# CorrelationOutput contract compliance
# ---------------------------------------------------------------------------


class TestCorrelationOutputContract:
    def _make_inp(self, V_g: float = 0.005) -> VolumePressureLawInput:
        return VolumePressureLawInput(
            V_g=V_g,
            V_total=0.010,
            law_params=_make_pca_params(),
        )

    def test_output_always_has_value(self) -> None:
        pca = PcaVolumePressureLaw()
        out = pca.evaluate(self._make_inp())
        assert out.value is not None

    def test_output_value_is_tuple(self) -> None:
        pca = PcaVolumePressureLaw()
        out = pca.evaluate(self._make_inp())
        assert isinstance(out.value, tuple)

    def test_output_always_has_verdict(self) -> None:
        pca = PcaVolumePressureLaw()
        out = pca.evaluate(self._make_inp())
        assert out.verdict is not None

    def test_output_always_has_metadata(self) -> None:
        pca = PcaVolumePressureLaw()
        out = pca.evaluate(self._make_inp())
        assert out.metadata is not None

    def test_output_metadata_has_name(self) -> None:
        pca = PcaVolumePressureLaw()
        out = pca.evaluate(self._make_inp())
        assert out.metadata.name

    def test_output_metadata_has_version(self) -> None:
        pca = PcaVolumePressureLaw()
        out = pca.evaluate(self._make_inp())
        assert out.metadata.version

    def test_output_is_not_bare_float(self) -> None:
        pca = PcaVolumePressureLaw()
        out = pca.evaluate(self._make_inp())
        assert not isinstance(out, float)

    def test_out_of_range_verdict_on_invalid_V_g(self) -> None:
        pca = PcaVolumePressureLaw()
        out = pca.evaluate(self._make_inp(V_g=-0.001))
        assert out.verdict.status is ValidityStatus.OUT_OF_RANGE

    def test_out_of_range_value_is_nan(self) -> None:
        pca = PcaVolumePressureLaw()
        out = pca.evaluate(self._make_inp(V_g=-0.001))
        assert math.isnan(out.value[0])

    def test_in_envelope_verdict_for_valid_input(self) -> None:
        pca = PcaVolumePressureLaw()
        out = pca.evaluate(self._make_inp(V_g=0.005))
        assert out.verdict.status is ValidityStatus.IN_ENVELOPE

    def test_extrapolated_verdict_when_V_g_exceeds_V_total(self) -> None:
        pca = PcaVolumePressureLaw()
        inp = VolumePressureLawInput(
            V_g=0.015,  # > V_total=0.010
            V_total=0.010,
            law_params=_make_pca_params(),
        )
        out = pca.evaluate(inp)
        assert out.verdict.status is ValidityStatus.EXTRAPOLATED


# ---------------------------------------------------------------------------
# Import boundary: volume_pressure_law.py must not import forbidden packages
# ---------------------------------------------------------------------------


def _import_lines_vpl(module_file: str) -> list[str]:
    with open(module_file, encoding="utf-8") as f:
        lines = f.readlines()
    return [line.strip() for line in lines if line.strip().startswith(("import ", "from "))]


class TestVolumePressureLawImportBoundaries:
    def test_does_not_import_components(self) -> None:
        import mpl_sim.correlations.volume_pressure_law as mod

        assert mod.__file__ is not None
        for line in _import_lines_vpl(mod.__file__):
            assert "mpl_sim.components" not in line, f"Forbidden: {line!r}"

    def test_does_not_import_geometry(self) -> None:
        import mpl_sim.correlations.volume_pressure_law as mod

        assert mod.__file__ is not None
        for line in _import_lines_vpl(mod.__file__):
            assert "mpl_sim.geometry" not in line, f"Forbidden: {line!r}"

    def test_does_not_import_network(self) -> None:
        import mpl_sim.correlations.volume_pressure_law as mod

        assert mod.__file__ is not None
        for line in _import_lines_vpl(mod.__file__):
            assert "mpl_sim.network" not in line, f"Forbidden: {line!r}"

    def test_does_not_import_solvers(self) -> None:
        import mpl_sim.correlations.volume_pressure_law as mod

        assert mod.__file__ is not None
        for line in _import_lines_vpl(mod.__file__):
            assert "mpl_sim.solvers" not in line, f"Forbidden: {line!r}"

    def test_does_not_import_properties(self) -> None:
        import mpl_sim.correlations.volume_pressure_law as mod

        assert mod.__file__ is not None
        for line in _import_lines_vpl(mod.__file__):
            assert "mpl_sim.properties" not in line, f"Forbidden: {line!r}"

    def test_does_not_import_coolprop(self) -> None:
        import mpl_sim.correlations.volume_pressure_law as mod

        assert mod.__file__ is not None
        for line in _import_lines_vpl(mod.__file__):
            assert "coolprop" not in line.lower(), f"Forbidden: {line!r}"
