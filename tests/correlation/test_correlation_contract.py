"""Phase 3A — correlation contract primitive tests.

Covers:
- CorrelationRole enum: all roles present, frozen set
- FlowRegimeLabel enum
- BoundedQuantity enum
- FluidFamilySpec variants (AnyFluid, NamedFluids, FluidClassSpec)
- Bound construction and immutability
- SourceRef construction
- ValidityEnvelope construction and immutability
- ValidityStatus and ValidityVerdict
- ClosureMetadata
- CorrelationOutput: immutability, no bare-number return enforced by type
- FlowRegimeVerdict
- ThermalSpec
- All six role-typed input value objects
- Correlation abstract base: cannot instantiate, subclass contract
- Import boundary: no properties/, CoolProp in correlations/
"""

import math
import types

import pytest

from mpl_sim.core.fluid_identity import PureFluid
from mpl_sim.core.fluid_state import FluidState
from mpl_sim.correlations.contract import (
    AnyFluid,
    Bound,
    BoundedQuantity,
    ClosureMetadata,
    Correlation,
    CorrelationOutput,
    CorrelationRole,
    CriticalHeatFluxInput,
    EnvelopeRef,
    FlowRegimeInput,
    FlowRegimeLabel,
    FlowRegimeVerdict,
    FluidClass,
    FluidClassSpec,
    HTCInput,
    NamedFluids,
    SinglePhaseDPInput,
    SourceRef,
    ThermalSpec,
    TwoPhaseDPInput,
    ValidityEnvelope,
    ValidityStatus,
    ValidityVerdict,
    VoidFractionInput,
    VolumePressureLawInput,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _state(P: float = 1e6, h: float = 2e5) -> FluidState:
    return FluidState(P=P, h=h, identity=PureFluid("R134a"))


def _source() -> SourceRef:
    return SourceRef(citation="Test citation", doi=None)


def _envelope() -> ValidityEnvelope:
    return ValidityEnvelope(
        fluid_families=(AnyFluid(),),
        bounds=(Bound(BoundedQuantity.REYNOLDS, min=1e3, max=1e6, units="-"),),
        source=_source(),
    )


def _envelope_ref() -> EnvelopeRef:
    return EnvelopeRef(correlation_name="test_corr", correlation_version="1.0")


def _in_envelope_verdict() -> ValidityVerdict:
    return ValidityVerdict(
        status=ValidityStatus.IN_ENVELOPE,
        envelope=_envelope_ref(),
        violated=(),
    )


def _metadata() -> ClosureMetadata:
    return ClosureMetadata(name="test_corr", version="1.0", source=_source())


# ---------------------------------------------------------------------------
# CorrelationRole
# ---------------------------------------------------------------------------


class TestCorrelationRole:
    def test_all_required_roles_present(self):
        roles = {r.name for r in CorrelationRole}
        assert "SINGLE_PHASE_DP" in roles
        assert "TWO_PHASE_DP" in roles
        assert "HTC" in roles
        assert "VOID_FRACTION" in roles
        assert "FLOW_REGIME" in roles
        assert "CRITICAL_HEAT_FLUX" in roles
        assert "VOLUME_PRESSURE_LAW" in roles
        assert "CUSTOM_CLOSURE" in roles

    def test_role_count(self):
        assert len(CorrelationRole) == 8

    def test_roles_are_distinct(self):
        values = [r.value for r in CorrelationRole]
        assert len(values) == len(set(values))

    def test_role_comparison(self):
        assert CorrelationRole.HTC != CorrelationRole.TWO_PHASE_DP
        assert CorrelationRole.HTC == CorrelationRole.HTC


# ---------------------------------------------------------------------------
# FlowRegimeLabel
# ---------------------------------------------------------------------------


class TestFlowRegimeLabel:
    def test_standard_labels_present(self):
        labels = {lbl.name for lbl in FlowRegimeLabel}
        for name in (
            "BUBBLY",
            "SLUG",
            "CHURN",
            "ANNULAR",
            "MIST",
            "STRATIFIED",
            "INTERMITTENT",
            "SINGLE_PHASE",
        ):
            assert name in labels

    def test_labels_are_distinct(self):
        values = [lbl.value for lbl in FlowRegimeLabel]
        assert len(values) == len(set(values))


# ---------------------------------------------------------------------------
# BoundedQuantity
# ---------------------------------------------------------------------------


class TestBoundedQuantity:
    def test_core_quantities_present(self):
        names = {q.name for q in BoundedQuantity}
        for name in (
            "REYNOLDS",
            "MASS_FLUX_G",
            "QUALITY_X",
            "BOND",
            "WEBER",
            "FROUDE",
            "REDUCED_PRESSURE",
            "PRANDTL",
            "HYDRAULIC_DIAMETER",
            "ASPECT_RATIO",
            "CHEVRON_ANGLE",
            "HEAT_FLUX",
            "SATURATION_TEMP",
            "NAMED_SCALAR",
        ):
            assert name in names


# ---------------------------------------------------------------------------
# FluidFamilySpec variants
# ---------------------------------------------------------------------------


class TestFluidFamilySpec:
    def test_any_fluid_is_frozen(self):
        a = AnyFluid()
        with pytest.raises((AttributeError, TypeError)):
            a.extra = "nope"  # type: ignore[attr-defined]

    def test_named_fluids_stores_tuple(self):
        nf = NamedFluids(names=("R134a", "R1234yf"))
        assert nf.names == ("R134a", "R1234yf")

    def test_named_fluids_is_frozen(self):
        nf = NamedFluids(names=("R134a",))
        with pytest.raises((AttributeError, TypeError)):
            nf.names = ("Water",)  # type: ignore[misc]

    def test_fluid_class_spec(self):
        fcs = FluidClassSpec(fluid_class=FluidClass.REFRIGERANT)
        assert fcs.fluid_class == FluidClass.REFRIGERANT

    def test_fluid_class_spec_is_frozen(self):
        fcs = FluidClassSpec(fluid_class=FluidClass.WATER)
        with pytest.raises((AttributeError, TypeError)):
            fcs.fluid_class = FluidClass.HYDROCARBON  # type: ignore[misc]

    def test_any_fluid_equality(self):
        assert AnyFluid() == AnyFluid()

    def test_named_fluids_equality(self):
        assert NamedFluids(names=("R134a",)) == NamedFluids(names=("R134a",))
        assert NamedFluids(names=("R134a",)) != NamedFluids(names=("Water",))


# ---------------------------------------------------------------------------
# Bound
# ---------------------------------------------------------------------------


class TestBound:
    def test_basic_construction(self):
        b = Bound(BoundedQuantity.REYNOLDS, min=1e3, max=1e6, units="-")
        assert b.quantity == BoundedQuantity.REYNOLDS
        assert b.min == pytest.approx(1e3)
        assert b.max == pytest.approx(1e6)
        assert b.units == "-"

    def test_unbounded_below(self):
        b = Bound(BoundedQuantity.QUALITY_X, min=None, max=1.0, units="-")
        assert b.min is None

    def test_unbounded_above(self):
        b = Bound(BoundedQuantity.MASS_FLUX_G, min=100.0, max=None, units="kg/m2s")
        assert b.max is None

    def test_is_frozen(self):
        b = Bound(BoundedQuantity.PRANDTL, min=0.7, max=160.0, units="-")
        with pytest.raises((AttributeError, TypeError)):
            b.min = 0.0  # type: ignore[misc]

    def test_equality(self):
        b1 = Bound(BoundedQuantity.REYNOLDS, min=1e3, max=1e6, units="-")
        b2 = Bound(BoundedQuantity.REYNOLDS, min=1e3, max=1e6, units="-")
        assert b1 == b2

    def test_inequality(self):
        b1 = Bound(BoundedQuantity.REYNOLDS, min=1e3, max=1e6, units="-")
        b2 = Bound(BoundedQuantity.REYNOLDS, min=0.0, max=1e6, units="-")
        assert b1 != b2


# ---------------------------------------------------------------------------
# SourceRef
# ---------------------------------------------------------------------------


class TestSourceRef:
    def test_construction_citation_only(self):
        s = SourceRef(citation="Shah 1979")
        assert s.citation == "Shah 1979"
        assert s.doi is None
        assert s.notes is None

    def test_construction_full(self):
        s = SourceRef(citation="Churchill 1977", doi="10.1234/test", notes="friction factor")
        assert s.doi == "10.1234/test"

    def test_is_frozen(self):
        s = SourceRef(citation="Test")
        with pytest.raises((AttributeError, TypeError)):
            s.citation = "Changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ValidityEnvelope
# ---------------------------------------------------------------------------


class TestValidityEnvelope:
    def test_basic_construction(self):
        env = _envelope()
        assert isinstance(env.fluid_families, tuple)
        assert isinstance(env.bounds, tuple)
        assert env.regime_restriction is None
        assert env.notes is None

    def test_with_regime_restriction(self):
        env = ValidityEnvelope(
            fluid_families=(AnyFluid(),),
            bounds=(),
            source=_source(),
            regime_restriction=(FlowRegimeLabel.ANNULAR,),
        )
        assert FlowRegimeLabel.ANNULAR in env.regime_restriction

    def test_with_notes(self):
        env = ValidityEnvelope(
            fluid_families=(AnyFluid(),),
            bounds=(),
            source=_source(),
            notes="Validated for microchannels only",
        )
        assert "microchannel" in env.notes

    def test_is_frozen(self):
        env = _envelope()
        with pytest.raises((AttributeError, TypeError)):
            env.notes = "changed"  # type: ignore[misc]

    def test_multiple_fluid_families(self):
        env = ValidityEnvelope(
            fluid_families=(
                NamedFluids(names=("R134a",)),
                FluidClassSpec(fluid_class=FluidClass.REFRIGERANT),
            ),
            bounds=(),
            source=_source(),
        )
        assert len(env.fluid_families) == 2

    def test_multiple_bounds(self):
        env = ValidityEnvelope(
            fluid_families=(AnyFluid(),),
            bounds=(
                Bound(BoundedQuantity.REYNOLDS, min=1e3, max=1e6, units="-"),
                Bound(BoundedQuantity.QUALITY_X, min=0.0, max=1.0, units="-"),
            ),
            source=_source(),
        )
        assert len(env.bounds) == 2


# ---------------------------------------------------------------------------
# ValidityStatus / ValidityVerdict
# ---------------------------------------------------------------------------


class TestValidityStatus:
    def test_three_levels(self):
        statuses = {s.name for s in ValidityStatus}
        assert statuses == {"IN_ENVELOPE", "EXTRAPOLATED", "OUT_OF_RANGE"}


class TestValidityVerdict:
    def test_in_envelope(self):
        v = _in_envelope_verdict()
        assert v.status == ValidityStatus.IN_ENVELOPE
        assert v.violated == ()
        assert v.detail is None

    def test_extrapolated(self):
        b = Bound(BoundedQuantity.REYNOLDS, min=1e3, max=1e6, units="-")
        v = ValidityVerdict(
            status=ValidityStatus.EXTRAPOLATED,
            envelope=_envelope_ref(),
            violated=(b,),
            detail="Re=1.2e6 exceeds upper bound",
        )
        assert v.status == ValidityStatus.EXTRAPOLATED
        assert len(v.violated) == 1
        assert "Re" in v.detail

    def test_out_of_range(self):
        v = ValidityVerdict(
            status=ValidityStatus.OUT_OF_RANGE,
            envelope=_envelope_ref(),
            violated=(),
            detail="q_flux required but absent",
        )
        assert v.status == ValidityStatus.OUT_OF_RANGE

    def test_is_frozen(self):
        v = _in_envelope_verdict()
        with pytest.raises((AttributeError, TypeError)):
            v.status = ValidityStatus.EXTRAPOLATED  # type: ignore[misc]

    def test_equality(self):
        v1 = _in_envelope_verdict()
        v2 = _in_envelope_verdict()
        assert v1 == v2


# ---------------------------------------------------------------------------
# ClosureMetadata
# ---------------------------------------------------------------------------


class TestClosureMetadata:
    def test_construction(self):
        m = _metadata()
        assert m.name == "test_corr"
        assert m.version == "1.0"
        assert isinstance(m.source, SourceRef)

    def test_is_frozen(self):
        m = _metadata()
        with pytest.raises((AttributeError, TypeError)):
            m.name = "other"  # type: ignore[misc]

    def test_equality(self):
        m1 = _metadata()
        m2 = _metadata()
        assert m1 == m2


# ---------------------------------------------------------------------------
# CorrelationOutput
# ---------------------------------------------------------------------------


class TestCorrelationOutput:
    def test_basic_construction(self):
        out = CorrelationOutput(
            value=(42.5,),
            verdict=_in_envelope_verdict(),
            metadata=_metadata(),
        )
        assert out.value == (42.5,)

    def test_vector_value(self):
        out = CorrelationOutput(
            value=(1.0, 2.0, 3.0),
            verdict=_in_envelope_verdict(),
            metadata=_metadata(),
        )
        assert len(out.value) == 3

    def test_nan_for_out_of_range(self):
        v = ValidityVerdict(
            status=ValidityStatus.OUT_OF_RANGE,
            envelope=_envelope_ref(),
            violated=(),
            detail="hard failure",
        )
        out = CorrelationOutput(value=(float("nan"),), verdict=v, metadata=_metadata())
        assert math.isnan(out.value[0])

    def test_is_frozen(self):
        out = CorrelationOutput(
            value=(1.0,),
            verdict=_in_envelope_verdict(),
            metadata=_metadata(),
        )
        with pytest.raises((AttributeError, TypeError)):
            out.value = (2.0,)  # type: ignore[misc]

    def test_verdict_always_present(self):
        out = CorrelationOutput(
            value=(0.0,),
            verdict=_in_envelope_verdict(),
            metadata=_metadata(),
        )
        assert out.verdict is not None
        assert out.metadata is not None


# ---------------------------------------------------------------------------
# FlowRegimeVerdict
# ---------------------------------------------------------------------------


class TestFlowRegimeVerdict:
    def test_basic_construction(self):
        frv = FlowRegimeVerdict(
            regime=FlowRegimeLabel.ANNULAR,
            verdict=_in_envelope_verdict(),
        )
        assert frv.regime == FlowRegimeLabel.ANNULAR
        assert frv.transition_coords is None

    def test_with_transition_coords(self):
        frv = FlowRegimeVerdict(
            regime=FlowRegimeLabel.SLUG,
            verdict=_in_envelope_verdict(),
            transition_coords={"x_an": 0.8, "x_sl": 0.2},
        )
        assert frv.transition_coords["x_an"] == pytest.approx(0.8)

    def test_is_frozen(self):
        frv = FlowRegimeVerdict(
            regime=FlowRegimeLabel.BUBBLY,
            verdict=_in_envelope_verdict(),
        )
        with pytest.raises((AttributeError, TypeError)):
            frv.regime = FlowRegimeLabel.ANNULAR  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ThermalSpec
# ---------------------------------------------------------------------------


class TestThermalSpec:
    def test_empty_construction(self):
        ts = ThermalSpec()
        assert ts.heater_duty_W is None
        assert ts.saturation_ref_Pa is None

    def test_with_values(self):
        ts = ThermalSpec(heater_duty_W=500.0, saturation_ref_Pa=1.5e6)
        assert ts.heater_duty_W == pytest.approx(500.0)

    def test_is_frozen(self):
        ts = ThermalSpec(heater_duty_W=100.0)
        with pytest.raises((AttributeError, TypeError)):
            ts.heater_duty_W = 200.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Role-typed inputs
# ---------------------------------------------------------------------------


class TestSinglePhaseDPInput:
    def test_construction(self):
        inp = SinglePhaseDPInput(
            state=(_state(),),
            G=300.0,
            D_h=0.002,
            roughness=1e-6,
            L_cell=0.01,
            rho=1000.0,
            mu=1e-3,
        )
        assert inp.G == pytest.approx(300.0)
        assert inp.D_h == pytest.approx(0.002)
        assert inp.rho == pytest.approx(1000.0)
        assert inp.mu == pytest.approx(1e-3)
        assert len(inp.state) == 1

    def test_is_frozen(self):
        inp = SinglePhaseDPInput(
            state=(_state(),), G=300.0, D_h=0.002, roughness=1e-6, L_cell=0.01, rho=1000.0, mu=1e-3
        )
        with pytest.raises((AttributeError, TypeError)):
            inp.G = 400.0  # type: ignore[misc]

    def test_multiple_states(self):
        inp = SinglePhaseDPInput(
            state=(_state(P=1e6), _state(P=0.9e6)),
            G=500.0,
            D_h=0.003,
            roughness=5e-7,
            L_cell=0.05,
            rho=900.0,
            mu=5e-4,
        )
        assert len(inp.state) == 2


class TestTwoPhaseDPInput:
    def test_construction_no_regime(self):
        inp = TwoPhaseDPInput(
            state=(_state(),),
            G=300.0,
            x=(0.3,),
            D_h=0.002,
            L_cell=0.01,
        )
        assert inp.regime is None
        assert inp.x == (0.3,)

    def test_construction_with_regime(self):
        frv = FlowRegimeVerdict(regime=FlowRegimeLabel.ANNULAR, verdict=_in_envelope_verdict())
        inp = TwoPhaseDPInput(
            state=(_state(),),
            G=300.0,
            x=(0.5,),
            D_h=0.002,
            L_cell=0.01,
            regime=frv,
        )
        assert inp.regime.regime == FlowRegimeLabel.ANNULAR

    def test_is_frozen(self):
        inp = TwoPhaseDPInput(state=(_state(),), G=300.0, x=(0.5,), D_h=0.002, L_cell=0.01)
        with pytest.raises((AttributeError, TypeError)):
            inp.G = 400.0  # type: ignore[misc]


class TestHTCInput:
    def test_minimal_construction(self):
        inp = HTCInput(
            state=(_state(),),
            G=300.0,
            x=(0.5,),
            D_h=0.002,
            geom_scalars={},
        )
        assert inp.q_flux is None
        assert inp.T_wall is None
        assert inp.regime is None

    def test_with_optional_fields(self):
        inp = HTCInput(
            state=(_state(),),
            G=300.0,
            x=(0.5,),
            D_h=0.002,
            geom_scalars={"chevron_angle": 60.0},
            q_flux=1e4,
            T_wall=320.0,
        )
        assert inp.q_flux == pytest.approx(1e4)
        assert inp.T_wall == pytest.approx(320.0)
        assert inp.geom_scalars["chevron_angle"] == pytest.approx(60.0)

    def test_is_frozen(self):
        inp = HTCInput(state=(_state(),), G=300.0, x=(0.5,), D_h=0.002, geom_scalars={})
        with pytest.raises((AttributeError, TypeError)):
            inp.G = 400.0  # type: ignore[misc]


class TestVoidFractionInput:
    def test_minimal_construction(self):
        inp = VoidFractionInput(state=(_state(),), x=(0.3,))
        assert inp.G is None
        assert inp.D_h is None

    def test_with_optional_fields(self):
        inp = VoidFractionInput(state=(_state(),), x=(0.3,), G=200.0, D_h=0.001)
        assert inp.G == pytest.approx(200.0)

    def test_is_frozen(self):
        inp = VoidFractionInput(state=(_state(),), x=(0.5,))
        with pytest.raises((AttributeError, TypeError)):
            inp.x = (0.6,)  # type: ignore[misc]


class TestFlowRegimeInput:
    def test_construction_no_orientation(self):
        inp = FlowRegimeInput(state=(_state(),), G=300.0, x=(0.5,), D_h=0.002)
        assert inp.orientation is None

    def test_with_orientation(self):
        import math

        inp = FlowRegimeInput(
            state=(_state(),),
            G=300.0,
            x=(0.5,),
            D_h=0.002,
            orientation=math.pi / 4,
        )
        assert inp.orientation == pytest.approx(math.pi / 4)

    def test_is_frozen(self):
        inp = FlowRegimeInput(state=(_state(),), G=300.0, x=(0.5,), D_h=0.002)
        with pytest.raises((AttributeError, TypeError)):
            inp.D_h = 0.005  # type: ignore[misc]


class TestCriticalHeatFluxInput:
    def test_construction(self):
        inp = CriticalHeatFluxInput(state=(_state(),), G=300.0, x=(0.5,), D_h=0.002)
        assert inp.L_heated is None

    def test_with_l_heated(self):
        inp = CriticalHeatFluxInput(state=(_state(),), G=300.0, x=(0.5,), D_h=0.002, L_heated=0.5)
        assert inp.L_heated == pytest.approx(0.5)

    def test_is_frozen(self):
        inp = CriticalHeatFluxInput(state=(_state(),), G=300.0, x=(0.5,), D_h=0.002)
        with pytest.raises((AttributeError, TypeError)):
            inp.G = 400.0  # type: ignore[misc]


class TestVolumePressureLawInput:
    def test_minimal_construction(self):
        inp = VolumePressureLawInput(V_g=0.001, V_total=0.01, law_params={"k_poly": 1.4})
        assert inp.state is None
        assert inp.thermal is None
        assert inp.P_set is None
        assert inp.law_params["k_poly"] == pytest.approx(1.4)

    def test_full_construction(self):
        ts = ThermalSpec(heater_duty_W=200.0)
        inp = VolumePressureLawInput(
            V_g=0.002,
            V_total=0.01,
            law_params={"V_charge": 0.003, "k_poly": 1.4},
            state=_state(),
            thermal=ts,
            P_set=1.2e6,
        )
        assert inp.thermal.heater_duty_W == pytest.approx(200.0)
        assert inp.P_set == pytest.approx(1.2e6)

    def test_is_frozen(self):
        inp = VolumePressureLawInput(V_g=0.001, V_total=0.01, law_params={})
        with pytest.raises((AttributeError, TypeError)):
            inp.V_g = 0.002  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Nested-payload immutability — MappingProxyType wrapping
# ---------------------------------------------------------------------------


class TestNestedPayloadImmutability:
    """Verify that dict-like fields are immutable after construction."""

    # --- HTCInput.geom_scalars ---

    def test_htc_geom_scalars_cannot_be_mutated(self):
        inp = HTCInput(
            state=(_state(),),
            G=300.0,
            x=(0.5,),
            D_h=0.002,
            geom_scalars={"chevron_angle": 60.0},
        )
        with pytest.raises(TypeError):
            inp.geom_scalars["chevron_angle"] = 45.0  # type: ignore[index]

    def test_htc_geom_scalars_source_dict_mutation_does_not_propagate(self):
        source = {"chevron_angle": 60.0}
        inp = HTCInput(state=(_state(),), G=300.0, x=(0.5,), D_h=0.002, geom_scalars=source)
        source["new_key"] = 99.0
        assert "new_key" not in inp.geom_scalars

    def test_htc_geom_scalars_read_access_still_works(self):
        inp = HTCInput(
            state=(_state(),),
            G=300.0,
            x=(0.5,),
            D_h=0.002,
            geom_scalars={"angle": 45.0},
        )
        assert inp.geom_scalars["angle"] == pytest.approx(45.0)

    # --- VolumePressureLawInput.law_params ---

    def test_vpl_law_params_cannot_be_mutated(self):
        inp = VolumePressureLawInput(V_g=0.001, V_total=0.01, law_params={"k_poly": 1.4})
        with pytest.raises(TypeError):
            inp.law_params["k_poly"] = 1.6  # type: ignore[index]

    def test_vpl_law_params_source_dict_mutation_does_not_propagate(self):
        source = {"k_poly": 1.4}
        inp = VolumePressureLawInput(V_g=0.001, V_total=0.01, law_params=source)
        source["k_poly"] = 9.9
        assert inp.law_params["k_poly"] == pytest.approx(1.4)

    def test_vpl_law_params_read_access_still_works(self):
        inp = VolumePressureLawInput(
            V_g=0.001, V_total=0.01, law_params={"V_charge": 0.003, "k_poly": 1.4}
        )
        assert inp.law_params["V_charge"] == pytest.approx(0.003)

    def test_vpl_empty_law_params_accepted(self):
        inp = VolumePressureLawInput(V_g=0.001, V_total=0.01, law_params={})
        assert len(inp.law_params) == 0

    # --- FlowRegimeVerdict.transition_coords ---

    def test_flow_regime_verdict_transition_coords_cannot_be_mutated(self):
        frv = FlowRegimeVerdict(
            regime=FlowRegimeLabel.SLUG,
            verdict=_in_envelope_verdict(),
            transition_coords={"x_an": 0.8},
        )
        with pytest.raises(TypeError):
            frv.transition_coords["x_an"] = 0.5  # type: ignore[index]

    def test_flow_regime_verdict_transition_coords_source_dict_mutation_does_not_propagate(self):
        source = {"x_an": 0.8, "x_sl": 0.2}
        frv = FlowRegimeVerdict(
            regime=FlowRegimeLabel.SLUG,
            verdict=_in_envelope_verdict(),
            transition_coords=source,
        )
        source["x_an"] = 0.0
        assert frv.transition_coords["x_an"] == pytest.approx(0.8)

    def test_flow_regime_verdict_none_transition_coords_unchanged(self):
        frv = FlowRegimeVerdict(
            regime=FlowRegimeLabel.ANNULAR,
            verdict=_in_envelope_verdict(),
        )
        assert frv.transition_coords is None

    def test_flow_regime_verdict_transition_coords_read_access_still_works(self):
        frv = FlowRegimeVerdict(
            regime=FlowRegimeLabel.SLUG,
            verdict=_in_envelope_verdict(),
            transition_coords={"x_an": 0.8, "x_sl": 0.2},
        )
        assert frv.transition_coords["x_sl"] == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# Correlation ABC
# ---------------------------------------------------------------------------


class TestCorrelationABC:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            Correlation()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_role(self):
        class IncompleteCorrelation(Correlation):
            def evaluate(self, inp):
                return CorrelationOutput(
                    value=(1.0,),
                    verdict=_in_envelope_verdict(),
                    metadata=_metadata(),
                )

            def envelope(self):
                return _envelope()

            # role() is missing

        with pytest.raises(TypeError):
            IncompleteCorrelation()

    def test_concrete_subclass_must_implement_evaluate(self):
        class IncompleteCorrelation(Correlation):
            def role(self):
                return CorrelationRole.SINGLE_PHASE_DP

            def envelope(self):
                return _envelope()

            # evaluate() is missing

        with pytest.raises(TypeError):
            IncompleteCorrelation()

    def test_concrete_subclass_must_implement_envelope(self):
        class IncompleteCorrelation(Correlation):
            def role(self):
                return CorrelationRole.HTC

            def evaluate(self, inp):
                return CorrelationOutput(
                    value=(1.0,),
                    verdict=_in_envelope_verdict(),
                    metadata=_metadata(),
                )

            # envelope() is missing

        with pytest.raises(TypeError):
            IncompleteCorrelation()

    def test_minimal_concrete_subclass_works(self):
        class DummyDP(Correlation):
            def role(self):
                return CorrelationRole.SINGLE_PHASE_DP

            def envelope(self):
                return _envelope()

            def evaluate(self, inp):
                return CorrelationOutput(
                    value=(100.0,),
                    verdict=_in_envelope_verdict(),
                    metadata=_metadata(),
                )

        corr = DummyDP()
        assert corr.role() == CorrelationRole.SINGLE_PHASE_DP
        inp = SinglePhaseDPInput(
            state=(_state(),), G=300.0, D_h=0.002, roughness=1e-6, L_cell=0.01, rho=1000.0, mu=1e-3
        )
        out = corr.evaluate(inp)
        assert isinstance(out, CorrelationOutput)
        assert out.value == (100.0,)
        assert out.verdict.status == ValidityStatus.IN_ENVELOPE

    def test_correlation_subclass_with_all_roles(self):
        for target_role in CorrelationRole:

            class RoleCorrelation(Correlation):
                _role = target_role

                def role(self):
                    return self._role

                def envelope(self):
                    return _envelope()

                def evaluate(self, inp):
                    return CorrelationOutput(
                        value=(0.0,),
                        verdict=_in_envelope_verdict(),
                        metadata=_metadata(),
                    )

            corr = RoleCorrelation()
            assert corr.role() == target_role


# ---------------------------------------------------------------------------
# Import boundary — no properties/, CoolProp in correlations.contract
# ---------------------------------------------------------------------------


class TestImportBoundary:
    def test_contract_does_not_import_properties_module(self):
        import mpl_sim.correlations.contract as contract_mod

        for name, mod in vars(contract_mod).items():
            if isinstance(mod, types.ModuleType):
                assert (
                    "properties" not in mod.__name__
                ), f"correlations.contract imports from properties/: {mod.__name__}"

    def test_contract_does_not_import_coolprop(self):
        import subprocess
        import sys

        # Run in a fresh interpreter so prior test-session CoolProp imports
        # cannot pollute sys.modules.
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import mpl_sim.correlations.contract, sys; "
                    "bad = [k for k in sys.modules if 'CoolProp' in k]; "
                    "assert not bad, 'CoolProp pulled in: ' + str(bad)"
                ),
            ],
            capture_output=True,
            text=True,
        )
        assert (
            result.returncode == 0
        ), f"correlations.contract indirectly imports CoolProp:\n{result.stderr}"

    def test_contract_does_not_import_components(self):
        import mpl_sim.correlations.contract as contract_mod

        for name, mod in vars(contract_mod).items():
            if isinstance(mod, types.ModuleType):
                assert "components" not in mod.__name__

    def test_contract_does_not_import_geometry(self):
        import mpl_sim.correlations.contract as contract_mod

        for name, mod in vars(contract_mod).items():
            if isinstance(mod, types.ModuleType):
                assert "geometry" not in mod.__name__

    def test_contract_does_not_import_solvers(self):
        import mpl_sim.correlations.contract as contract_mod

        for name, mod in vars(contract_mod).items():
            if isinstance(mod, types.ModuleType):
                assert "solvers" not in mod.__name__


# ---------------------------------------------------------------------------
# Package-level __init__ re-exports
# ---------------------------------------------------------------------------


class TestPackageExports:
    def test_all_symbols_importable_from_package(self):
        from mpl_sim.correlations import (
            CorrelationRole,
        )

        assert CorrelationRole.HTC is not None

    def test_all_declared_in_all(self):
        import mpl_sim.correlations as pkg

        assert hasattr(pkg, "__all__")
        for name in pkg.__all__:
            assert hasattr(pkg, name), f"__all__ entry {name!r} not actually exported"
