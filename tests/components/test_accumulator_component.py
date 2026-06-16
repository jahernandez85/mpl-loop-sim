"""Accumulator component tests -- Phase 10C / 10D / 10H.

Verifies:
  AccumulatorComponent -- construction, id/name, kind, port, geometry storage,
    immutability.
  AccumulatorOperatingPoint -- construction, validation, immutability.
  AccumulatorPressureSummary -- structure, immutability.
  AccumulatorComponent.evaluate_pressure_reference -- prescribed pressure-reference
    law, validation, no mutation.
  VolumePressureLawBinding -- data-only, immutable, law_params isolation (10H).
  AccumulatorVolumePressureSummary -- result shape (10H).
  AccumulatorComponent.evaluate_volume_pressure_law -- delegation to correlation (10H).

Import-boundary assertions:
  components/accumulator.py may import mpl_sim.correlations.contract only;
  must not import coolprop, network, solvers, mpl_sim.properties,
  mpl_sim.correlations.registry, or any other correlations sub-module.
"""

from __future__ import annotations

import math

import pytest

from mpl_sim.components.accumulator import (
    AccumulatorComponent,
    AccumulatorOperatingPoint,
    AccumulatorPressureSummary,
    AccumulatorVolumePressureSummary,
    VolumePressureLawBinding,
)
from mpl_sim.components.base import ComponentId, ComponentKind
from mpl_sim.core.port import PortRole
from mpl_sim.geometry.primitives import AccumulatorGeometry, ContainmentSpec

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_containment() -> ContainmentSpec:
    return ContainmentSpec(inner_diameter=0.1, height=0.5)


def _make_geometry(v_total: float = 0.01) -> AccumulatorGeometry:
    return AccumulatorGeometry(V_total=v_total, containment=_make_containment())


def _make_accumulator(name: str = "acc_1") -> AccumulatorComponent:
    return AccumulatorComponent(
        component_id=ComponentId(name),
        geometry=_make_geometry(),
    )


def _import_lines(module_file: str) -> list[str]:
    with open(module_file, encoding="utf-8") as f:
        lines = f.readlines()
    return [line.strip() for line in lines if line.strip().startswith(("import ", "from "))]


# ---------------------------------------------------------------------------
# Phase 10C — skeleton: construction and identity
# ---------------------------------------------------------------------------


class TestAccumulatorConstruction:
    def test_basic_construction(self) -> None:
        acc = _make_accumulator()
        assert acc.component_id == ComponentId("acc_1")

    def test_kind_is_accumulator(self) -> None:
        assert _make_accumulator().kind() is ComponentKind.ACCUMULATOR

    def test_stores_geometry_by_reference(self) -> None:
        geom = _make_geometry()
        acc = AccumulatorComponent(component_id=ComponentId("a"), geometry=geom)
        assert acc.geometry is geom

    def test_is_immutable(self) -> None:
        acc = _make_accumulator()
        with pytest.raises((AttributeError, TypeError)):
            acc.component_id = ComponentId("other")  # type: ignore[misc]

    def test_geometry_not_mutated(self) -> None:
        geom = _make_geometry(v_total=0.02)
        acc = AccumulatorComponent(component_id=ComponentId("a"), geometry=geom)
        assert acc.geometry.V_total == pytest.approx(0.02)

    def test_rejects_empty_name(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            AccumulatorComponent(
                component_id=ComponentId(""),
                geometry=_make_geometry(),
            )

    def test_different_ids_not_equal(self) -> None:
        assert _make_accumulator("a1") != _make_accumulator("a2")

    def test_same_ids_and_geometry_are_equal(self) -> None:
        geom = _make_geometry()
        a1 = AccumulatorComponent(component_id=ComponentId("a"), geometry=geom)
        a2 = AccumulatorComponent(component_id=ComponentId("a"), geometry=geom)
        assert a1 == a2

    def test_repr_contains_name(self) -> None:
        acc = _make_accumulator("myacc")
        assert "myacc" in repr(acc)

    def test_internal_state_names_has_V_g(self) -> None:
        assert "V_g" in _make_accumulator().internal_state_names()

    def test_geometry_carries_no_law_parameters(self) -> None:
        geom = _make_geometry()
        forbidden = (
            "V_gas_charge",
            "charge_pressure",
            "polytropic_index",
            "spring_rate",
            "bellows_area",
            "gas_constant",
            "P_set",
            "V_g",
            "P_sys",
        )
        for attr in forbidden:
            assert not hasattr(
                geom, attr
            ), f"AccumulatorGeometry must not have law parameter {attr!r}"


# ---------------------------------------------------------------------------
# Phase 10C — port consistent with component contract
# ---------------------------------------------------------------------------


class TestAccumulatorPort:
    def test_ports_returns_one_port(self) -> None:
        assert len(_make_accumulator().ports()) == 1

    def test_fluid_port_role_is_bidirectional(self) -> None:
        acc = _make_accumulator()
        assert acc.fluid_port.role is PortRole.BIDIRECTIONAL

    def test_ports_tuple_first_entry_is_fluid_port(self) -> None:
        acc = _make_accumulator()
        assert acc.ports()[0].role is PortRole.BIDIRECTIONAL

    def test_fluid_port_name(self) -> None:
        acc = _make_accumulator("a")
        assert acc.fluid_port.id.port_name == "fluid"

    def test_fluid_port_owned_by_component(self) -> None:
        acc = _make_accumulator("myacc")
        assert acc.fluid_port.owner == "myacc"

    def test_fluid_port_id_references_component(self) -> None:
        acc = _make_accumulator("myacc")
        assert acc.fluid_port.id.component_id == "myacc"

    def test_fluid_port_has_no_peer_before_assembly(self) -> None:
        assert _make_accumulator().fluid_port.peer is None

    def test_ports_carry_no_thermodynamic_values(self) -> None:
        forbidden = ("P", "h", "mdot", "T", "x", "rho", "mu", "quality", "phase")
        for port in _make_accumulator().ports():
            for attr in forbidden:
                assert not hasattr(port, attr), f"Port must not have attribute {attr!r}"

    def test_accumulator_does_not_store_p_sys(self) -> None:
        acc = _make_accumulator()
        forbidden = ("P_sys", "p_sys", "pressure", "p_ref_stored")
        for attr in forbidden:
            assert not hasattr(
                acc, attr
            ), f"AccumulatorComponent must not store system pressure as {attr!r}"


# ---------------------------------------------------------------------------
# Phase 10C — import boundary
# ---------------------------------------------------------------------------


class TestAccumulatorImportBoundaries:
    def test_accumulator_module_does_not_import_coolprop(self) -> None:
        import mpl_sim.components.accumulator as mod

        assert mod.__file__ is not None
        for line in _import_lines(mod.__file__):
            assert "coolprop" not in line.lower(), f"Forbidden import: {line!r}"

    def test_accumulator_module_does_not_import_network(self) -> None:
        import mpl_sim.components.accumulator as mod

        assert mod.__file__ is not None
        for line in _import_lines(mod.__file__):
            assert "network" not in line, f"Forbidden import: {line!r}"

    def test_accumulator_module_does_not_import_solvers(self) -> None:
        import mpl_sim.components.accumulator as mod

        assert mod.__file__ is not None
        for line in _import_lines(mod.__file__):
            assert "solvers" not in line, f"Forbidden import: {line!r}"

    def test_accumulator_module_does_not_import_properties(self) -> None:
        import mpl_sim.components.accumulator as mod

        assert mod.__file__ is not None
        for line in _import_lines(mod.__file__):
            assert "mpl_sim.properties" not in line, f"Forbidden import: {line!r}"

    def test_accumulator_module_may_only_import_correlations_contract(self) -> None:
        import mpl_sim.components.accumulator as mod

        assert mod.__file__ is not None
        for line in _import_lines(mod.__file__):
            if "mpl_sim.correlations" in line:
                assert "mpl_sim.correlations.contract" in line, (
                    f"Only mpl_sim.correlations.contract is allowed; " f"forbidden import: {line!r}"
                )


# ---------------------------------------------------------------------------
# Phase 10D — AccumulatorOperatingPoint validation
# ---------------------------------------------------------------------------


class TestAccumulatorOperatingPoint:
    def test_basic_construction(self) -> None:
        op = AccumulatorOperatingPoint(p_setpoint=1_000_000.0)
        assert op.p_setpoint == 1_000_000.0

    def test_is_immutable(self) -> None:
        op = AccumulatorOperatingPoint(p_setpoint=1e6)
        with pytest.raises((AttributeError, TypeError)):
            op.p_setpoint = 2e6  # type: ignore[misc]

    def test_rejects_nan(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            AccumulatorOperatingPoint(p_setpoint=math.nan)

    def test_rejects_pos_inf(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            AccumulatorOperatingPoint(p_setpoint=math.inf)

    def test_rejects_neg_inf(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            AccumulatorOperatingPoint(p_setpoint=-math.inf)

    def test_rejects_zero(self) -> None:
        with pytest.raises(ValueError, match="> 0"):
            AccumulatorOperatingPoint(p_setpoint=0.0)

    def test_rejects_negative_pressure(self) -> None:
        with pytest.raises(ValueError, match="> 0"):
            AccumulatorOperatingPoint(p_setpoint=-1e5)

    def test_positive_pressure_accepted(self) -> None:
        op = AccumulatorOperatingPoint(p_setpoint=1.5e6)
        assert op.p_setpoint == 1.5e6

    def test_small_positive_pressure_accepted(self) -> None:
        op = AccumulatorOperatingPoint(p_setpoint=1.0)
        assert op.p_setpoint == 1.0


# ---------------------------------------------------------------------------
# Phase 10D — AccumulatorPressureSummary structure
# ---------------------------------------------------------------------------


class TestAccumulatorPressureSummary:
    def test_is_immutable(self) -> None:
        summary = AccumulatorPressureSummary(p_ref=1e6, p_setpoint=1e6)
        with pytest.raises((AttributeError, TypeError)):
            summary.p_ref = 2e6  # type: ignore[misc]

    def test_fields_accessible(self) -> None:
        summary = AccumulatorPressureSummary(p_ref=1.5e6, p_setpoint=1.5e6)
        assert summary.p_ref == 1.5e6
        assert summary.p_setpoint == 1.5e6


# ---------------------------------------------------------------------------
# Phase 10D — evaluate_pressure_reference behaviour
# ---------------------------------------------------------------------------


class TestAccumulatorEvaluatePressureReference:
    def test_returns_setpoint_as_p_ref(self) -> None:
        acc = _make_accumulator()
        op = AccumulatorOperatingPoint(p_setpoint=1_500_000.0)
        result = acc.evaluate_pressure_reference(op)
        assert result.p_ref == pytest.approx(1_500_000.0)

    def test_setpoint_echoed_in_result(self) -> None:
        acc = _make_accumulator()
        op = AccumulatorOperatingPoint(p_setpoint=2_000_000.0)
        result = acc.evaluate_pressure_reference(op)
        assert result.p_setpoint == pytest.approx(2_000_000.0)

    def test_p_ref_equals_p_setpoint(self) -> None:
        acc = _make_accumulator()
        op = AccumulatorOperatingPoint(p_setpoint=800_000.0)
        result = acc.evaluate_pressure_reference(op)
        assert result.p_ref == pytest.approx(result.p_setpoint)

    def test_result_is_immutable(self) -> None:
        acc = _make_accumulator()
        op = AccumulatorOperatingPoint(p_setpoint=1e6)
        result = acc.evaluate_pressure_reference(op)
        with pytest.raises((AttributeError, TypeError)):
            result.p_ref = 2e6  # type: ignore[misc]

    def test_accumulator_not_mutated_by_evaluation(self) -> None:
        acc = _make_accumulator("acc_x")
        acc.evaluate_pressure_reference(AccumulatorOperatingPoint(p_setpoint=1e6))
        assert acc.component_id == ComponentId("acc_x")

    def test_geometry_not_mutated_by_evaluation(self) -> None:
        geom = _make_geometry(v_total=0.02)
        acc = AccumulatorComponent(component_id=ComponentId("a"), geometry=geom)
        acc.evaluate_pressure_reference(AccumulatorOperatingPoint(p_setpoint=1e6))
        assert acc.geometry.V_total == pytest.approx(0.02)

    def test_different_setpoints_give_different_p_ref(self) -> None:
        acc = _make_accumulator()
        r1 = acc.evaluate_pressure_reference(AccumulatorOperatingPoint(p_setpoint=1e6))
        r2 = acc.evaluate_pressure_reference(AccumulatorOperatingPoint(p_setpoint=2e6))
        assert r1.p_ref != r2.p_ref

    def test_p_sys_not_stored_on_accumulator_after_evaluation(self) -> None:
        acc = _make_accumulator()
        acc.evaluate_pressure_reference(AccumulatorOperatingPoint(p_setpoint=1e6))
        assert not hasattr(acc, "P_sys")
        assert not hasattr(acc, "p_sys")


# ---------------------------------------------------------------------------
# Phase 10H -- VolumePressureLawBinding
# ---------------------------------------------------------------------------


def _pca_law_params() -> dict:
    return {
        "charge_volume": 0.005,
        "charge_pressure": 1_000_000.0,
        "polytropic_index": 1.4,
    }


class TestVolumePressureLawBinding:
    def test_basic_construction(self) -> None:
        b = VolumePressureLawBinding(law_params=_pca_law_params())
        assert b.law_params["charge_volume"] == pytest.approx(0.005)

    def test_is_immutable_dataclass(self) -> None:
        b = VolumePressureLawBinding(law_params=_pca_law_params())
        with pytest.raises((AttributeError, TypeError)):
            b.law_params = {}  # type: ignore[misc]

    def test_law_params_is_immutable_mapping(self) -> None:
        b = VolumePressureLawBinding(law_params=_pca_law_params())
        with pytest.raises((TypeError, AttributeError)):
            b.law_params["new_key"] = 1.0  # type: ignore[index]

    def test_mutation_of_source_dict_does_not_affect_binding(self) -> None:
        params = _pca_law_params()
        b = VolumePressureLawBinding(law_params=params)
        params["charge_volume"] = 999.0
        assert b.law_params["charge_volume"] == pytest.approx(0.005)

    def test_carries_no_geometry_object(self) -> None:
        b = VolumePressureLawBinding(law_params=_pca_law_params())
        forbidden = ("geometry", "Geometry", "AccumulatorGeometry", "V_total")
        for attr in forbidden:
            assert not hasattr(b, attr), f"Binding must not carry {attr!r}"

    def test_carries_no_correlation_object(self) -> None:
        b = VolumePressureLawBinding(law_params=_pca_law_params())
        forbidden = ("correlation", "Correlation", "role", "evaluate", "envelope")
        for attr in forbidden:
            assert not hasattr(b, attr), f"Binding must not carry {attr!r}"


# ---------------------------------------------------------------------------
# Phase 10H -- AccumulatorVolumePressureSummary
# ---------------------------------------------------------------------------


class TestAccumulatorVolumePressureSummary:
    def _make_summary(self) -> AccumulatorVolumePressureSummary:
        from mpl_sim.correlations.contract import VolumePressureLawInput
        from mpl_sim.correlations.volume_pressure_law import PcaVolumePressureLaw

        pca = PcaVolumePressureLaw()
        inp = VolumePressureLawInput(
            V_g=0.005,
            V_total=0.010,
            law_params={
                "charge_volume": 0.005,
                "charge_pressure": 1_000_000.0,
                "polytropic_index": 1.4,
            },
        )
        output = pca.evaluate(inp)
        return AccumulatorVolumePressureSummary(
            P_derived=output.value[0],
            V_g=0.005,
            output=output,
        )

    def test_p_derived_accessible(self) -> None:
        s = self._make_summary()
        assert s.P_derived == pytest.approx(1_000_000.0)

    def test_v_g_accessible(self) -> None:
        s = self._make_summary()
        assert s.V_g == pytest.approx(0.005)

    def test_output_accessible(self) -> None:
        s = self._make_summary()
        assert s.output is not None

    def test_is_immutable(self) -> None:
        s = self._make_summary()
        with pytest.raises((AttributeError, TypeError)):
            s.P_derived = 2e6  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Phase 10H -- AccumulatorComponent.evaluate_volume_pressure_law
# ---------------------------------------------------------------------------


class TestEvaluateVolumePressureLaw:
    def _make_pca(self):
        from mpl_sim.correlations.volume_pressure_law import PcaVolumePressureLaw

        return PcaVolumePressureLaw()

    def _make_binding(self) -> VolumePressureLawBinding:
        return VolumePressureLawBinding(law_params=_pca_law_params())

    def test_returns_summary(self) -> None:
        acc = _make_accumulator()
        result = acc.evaluate_volume_pressure_law(
            binding=self._make_binding(),
            V_g=0.005,
            correlation=self._make_pca(),
        )
        assert isinstance(result, AccumulatorVolumePressureSummary)

    def test_p_derived_is_positive(self) -> None:
        acc = _make_accumulator()
        result = acc.evaluate_volume_pressure_law(
            binding=self._make_binding(),
            V_g=0.005,
            correlation=self._make_pca(),
        )
        assert result.P_derived > 0.0

    def test_p_derived_matches_hand_calc(self) -> None:
        # P = 1e6 * (0.005 / 0.005)^1.4 = 1e6
        acc = _make_accumulator()
        result = acc.evaluate_volume_pressure_law(
            binding=self._make_binding(),
            V_g=0.005,
            correlation=self._make_pca(),
        )
        assert result.P_derived == pytest.approx(1_000_000.0, rel=1e-9)

    def test_v_g_echoed_in_result(self) -> None:
        acc = _make_accumulator()
        result = acc.evaluate_volume_pressure_law(
            binding=self._make_binding(),
            V_g=0.007,
            correlation=self._make_pca(),
        )
        assert result.V_g == pytest.approx(0.007)

    def test_uses_geometry_V_total_as_envelope_bound(self) -> None:
        from mpl_sim.correlations.contract import ValidityStatus

        acc = AccumulatorComponent(
            component_id=ComponentId("acc"),
            geometry=_make_geometry(v_total=0.010),
        )
        # V_g within V_total => IN_ENVELOPE
        result = acc.evaluate_volume_pressure_law(
            binding=self._make_binding(),
            V_g=0.008,
            correlation=self._make_pca(),
        )
        assert result.output.verdict.status is ValidityStatus.IN_ENVELOPE

    def test_extrapolated_when_V_g_exceeds_V_total(self) -> None:
        from mpl_sim.correlations.contract import ValidityStatus

        acc = AccumulatorComponent(
            component_id=ComponentId("acc"),
            geometry=_make_geometry(v_total=0.010),
        )
        result = acc.evaluate_volume_pressure_law(
            binding=self._make_binding(),
            V_g=0.015,  # > V_total=0.010
            correlation=self._make_pca(),
        )
        assert result.output.verdict.status is ValidityStatus.EXTRAPOLATED

    def test_accumulator_not_mutated_by_evaluation(self) -> None:
        acc = _make_accumulator("acc_vol")
        acc.evaluate_volume_pressure_law(
            binding=self._make_binding(),
            V_g=0.005,
            correlation=self._make_pca(),
        )
        assert acc.component_id == ComponentId("acc_vol")

    def test_geometry_not_mutated_by_evaluation(self) -> None:
        geom = _make_geometry(v_total=0.02)
        acc = AccumulatorComponent(component_id=ComponentId("a"), geometry=geom)
        acc.evaluate_volume_pressure_law(
            binding=self._make_binding(),
            V_g=0.005,
            correlation=self._make_pca(),
        )
        assert acc.geometry.V_total == pytest.approx(0.02)

    def test_p_derived_matches_output_value(self) -> None:
        acc = _make_accumulator()
        result = acc.evaluate_volume_pressure_law(
            binding=self._make_binding(),
            V_g=0.005,
            correlation=self._make_pca(),
        )
        assert result.P_derived == pytest.approx(result.output.value[0])

    def test_pressure_not_stored_on_accumulator(self) -> None:
        acc = _make_accumulator()
        acc.evaluate_volume_pressure_law(
            binding=self._make_binding(),
            V_g=0.005,
            correlation=self._make_pca(),
        )
        forbidden = ("P_sys", "p_sys", "P_derived", "V_g_stored")
        for attr in forbidden:
            assert not hasattr(acc, attr), f"Accumulator must not store {attr!r}"
