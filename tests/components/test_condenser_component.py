"""Tests for CondenserComponent — Phase 11D.

Verifies:
  - Condenser has exactly inlet and outlet ports
  - No values on ports
  - ComponentKind is CONDENSER
  - Component is local and imports no Network/Solver/CoolProp
  - Component holds a HX model slot separate from correlation slots (via input object)
  - evaluate_heat_exchanger calls the injected HX model
  - evaluate_heat_exchanger passes injected correlations to model via request
  - evaluate_heat_exchanger passes secondary BC
  - evaluate_heat_exchanger passes calibration multipliers
  - Result contains primary_state_out, Q, dP_primary, and verdicts
  - No derived state is stored on the component
"""

from __future__ import annotations

import math

import pytest

from mpl_sim.components.base import ComponentId, ComponentKind
from mpl_sim.components.condenser import CondenserComponent, CondenserHXInput
from mpl_sim.core.fluid_identity import PureFluid
from mpl_sim.core.fluid_state import FluidState
from mpl_sim.core.port import PortRole
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
    ValidityEnvelope,
    ValidityStatus,
    ValidityVerdict,
)
from mpl_sim.discretization.primitives import DiscretizationMode, DiscretizationSpec
from mpl_sim.geometry.primitives import PlateGeometry, PortDimensions
from mpl_sim.hx_models.base import (
    FixedHeatRate,
    HeatExchangerModel,
    HeatExchangerModelKind,
    HXSolveRequest,
    HXSolveResult,
)

# ---------------------------------------------------------------------------
# Minimal fake HX model
# ---------------------------------------------------------------------------


class _RecordingModel(HeatExchangerModel):
    def __init__(self) -> None:
        self.call_count = 0
        self.last_req: HXSolveRequest | None = None

    def kind(self) -> HeatExchangerModelKind:
        return HeatExchangerModelKind.EPSILON_NTU

    def solve(self, req: HXSolveRequest) -> HXSolveResult:
        self.call_count += 1
        self.last_req = req
        bc = req.secondary_bc
        if isinstance(bc, FixedHeatRate):
            h_out = req.primary_state_in.h + bc.Q / req.primary_mdot
            state_out = FluidState(
                P=req.primary_state_in.P, h=h_out, identity=req.primary_state_in.identity
            )
            return HXSolveResult(primary_state_out=state_out, Q=bc.Q, dP_primary=0.0, verdicts=())
        raise NotImplementedError("stub: only FixedHeatRate")


# ---------------------------------------------------------------------------
# Fake correlations
# ---------------------------------------------------------------------------

_MINIMAL_ENVELOPE = ValidityEnvelope(
    fluid_families=(AnyFluid(),),
    bounds=(Bound(quantity=BoundedQuantity.REYNOLDS, min=None, max=None, units=""),),
    source=SourceRef(citation="test"),
)


class _FakeHTCCorr(Correlation):
    def role(self) -> CorrelationRole:
        return CorrelationRole.HTC

    def envelope(self) -> ValidityEnvelope:
        return _MINIMAL_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        return CorrelationOutput(
            value=(200.0,),
            verdict=ValidityVerdict(
                status=ValidityStatus.IN_ENVELOPE,
                envelope=EnvelopeRef("fake_htc", "0"),
                violated=(),
            ),
            metadata=ClosureMetadata("fake_htc", "0", SourceRef("test")),
        )


class _FakeDPCorr(Correlation):
    def role(self) -> CorrelationRole:
        return CorrelationRole.SINGLE_PHASE_DP

    def envelope(self) -> ValidityEnvelope:
        return _MINIMAL_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        return CorrelationOutput(
            value=(300.0,),
            verdict=ValidityVerdict(
                status=ValidityStatus.IN_ENVELOPE,
                envelope=EnvelopeRef("fake_dp", "0"),
                violated=(),
            ),
            metadata=ClosureMetadata("fake_dp", "0", SourceRef("test")),
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_IDENTITY = PureFluid("R134a")
_STATE_IN = FluidState(P=1.2e6, h=430e3, identity=_IDENTITY)
_DISC = DiscretizationSpec(mode=DiscretizationMode.LUMPED)
_GEOM = PlateGeometry(
    N_plates=20,
    chevron_angle=60.0,
    plate_spacing=0.003,
    port_dims=PortDimensions(diameter=0.025),
    A_per_plate=0.04,
)
_COMP_ID = ComponentId("cond1")


def _make_condenser() -> CondenserComponent:
    return CondenserComponent(component_id=_COMP_ID, geometry=_GEOM)


def _make_input(
    Q: float = -1500.0,
    mdot: float = 0.06,
    model: HeatExchangerModel | None = None,
    htc_primary: Correlation | None = None,
    htc_secondary: Correlation | None = None,
    dp_primary: Correlation | None = None,
    htc_multiplier: float = 1.0,
    friction_multiplier: float = 1.0,
    bc=None,
) -> CondenserHXInput:
    return CondenserHXInput(
        primary_state_in=_STATE_IN,
        primary_mdot=mdot,
        secondary_bc=bc or FixedHeatRate(Q=Q),
        model=model or _RecordingModel(),
        discretization=_DISC,
        geom_scalars={"rho": 1100.0, "mu": 1e-4},
        htc_primary=htc_primary,
        htc_secondary=htc_secondary,
        dp_primary=dp_primary,
        htc_multiplier=htc_multiplier,
        friction_multiplier=friction_multiplier,
    )


# ---------------------------------------------------------------------------
# Port structure
# ---------------------------------------------------------------------------


class TestCondenserPorts:
    def test_has_exactly_two_ports(self) -> None:
        cond = _make_condenser()
        assert len(cond.ports()) == 2

    def test_inlet_role_is_inlet(self) -> None:
        cond = _make_condenser()
        assert cond.inlet.role is PortRole.INLET

    def test_outlet_role_is_outlet(self) -> None:
        cond = _make_condenser()
        assert cond.outlet.role is PortRole.OUTLET

    def test_inlet_peer_is_none(self) -> None:
        cond = _make_condenser()
        assert cond.inlet.peer is None

    def test_outlet_peer_is_none(self) -> None:
        cond = _make_condenser()
        assert cond.outlet.peer is None

    def test_ports_tuple_order(self) -> None:
        cond = _make_condenser()
        ports = cond.ports()
        assert ports[0].id == cond.inlet.id
        assert ports[1].id == cond.outlet.id


# ---------------------------------------------------------------------------
# ComponentKind
# ---------------------------------------------------------------------------


class TestCondenserKind:
    def test_kind_is_condenser(self) -> None:
        cond = _make_condenser()
        assert cond.kind() is ComponentKind.CONDENSER


# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------


class TestCondenserInternalState:
    def test_internal_state_names_is_tuple(self) -> None:
        cond = _make_condenser()
        assert isinstance(cond.internal_state_names(), tuple)

    def test_no_internal_states_in_v1(self) -> None:
        cond = _make_condenser()
        assert cond.internal_state_names() == ()


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


class TestCondenserImmutability:
    def test_component_is_frozen(self) -> None:
        cond = _make_condenser()
        with pytest.raises((AttributeError, TypeError)):
            cond.component_id = ComponentId("other")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# HX model slot separate from correlation slots
# ---------------------------------------------------------------------------


class TestCondenserHXModelSlot:
    def test_hx_input_has_model_field(self) -> None:
        inp = _make_input()
        assert hasattr(inp, "model")
        assert isinstance(inp.model, HeatExchangerModel)

    def test_hx_input_has_separate_htc_slot(self) -> None:
        inp = _make_input()
        assert hasattr(inp, "htc_primary")

    def test_hx_input_has_separate_dp_slot(self) -> None:
        inp = _make_input()
        assert hasattr(inp, "dp_primary")

    def test_model_and_htc_are_different_slots(self) -> None:
        htc = _FakeHTCCorr()
        model = _RecordingModel()
        inp = _make_input(model=model, htc_primary=htc)
        assert inp.model is not inp.htc_primary


# ---------------------------------------------------------------------------
# evaluate_heat_exchanger — model called
# ---------------------------------------------------------------------------


class TestEvaluateHXModelCalled:
    def test_model_is_called(self) -> None:
        cond = _make_condenser()
        rec = _RecordingModel()
        inp = _make_input(model=rec)
        cond.evaluate_heat_exchanger(inp)
        assert rec.call_count == 1

    def test_model_receives_geometry(self) -> None:
        cond = _make_condenser()
        rec = _RecordingModel()
        inp = _make_input(model=rec)
        cond.evaluate_heat_exchanger(inp)
        assert rec.last_req is not None
        assert rec.last_req.geometry is _GEOM

    def test_model_receives_secondary_bc(self) -> None:
        cond = _make_condenser()
        rec = _RecordingModel()
        bc = FixedHeatRate(Q=-500.0)
        inp = _make_input(model=rec, bc=bc)
        cond.evaluate_heat_exchanger(inp)
        assert rec.last_req is not None
        assert rec.last_req.secondary_bc is bc

    def test_model_receives_htc_correlation(self) -> None:
        cond = _make_condenser()
        rec = _RecordingModel()
        htc = _FakeHTCCorr()
        inp = _make_input(model=rec, htc_primary=htc)
        cond.evaluate_heat_exchanger(inp)
        assert rec.last_req is not None
        assert rec.last_req.htc_primary is htc

    def test_model_receives_secondary_htc(self) -> None:
        cond = _make_condenser()
        rec = _RecordingModel()
        htc_s = _FakeHTCCorr()
        inp = _make_input(model=rec, htc_secondary=htc_s)
        cond.evaluate_heat_exchanger(inp)
        assert rec.last_req is not None
        assert rec.last_req.htc_secondary is htc_s

    def test_model_receives_dp_correlation(self) -> None:
        cond = _make_condenser()
        rec = _RecordingModel()
        dp = _FakeDPCorr()
        inp = _make_input(model=rec, dp_primary=dp)
        cond.evaluate_heat_exchanger(inp)
        assert rec.last_req is not None
        assert rec.last_req.dp_primary is dp

    def test_model_receives_calibration_multipliers(self) -> None:
        cond = _make_condenser()
        rec = _RecordingModel()
        inp = _make_input(model=rec, htc_multiplier=1.3, friction_multiplier=0.7)
        cond.evaluate_heat_exchanger(inp)
        assert rec.last_req is not None
        assert math.isclose(rec.last_req.htc_multiplier, 1.3)
        assert math.isclose(rec.last_req.friction_multiplier, 0.7)


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------


class TestCondenserResultStructure:
    def test_result_is_hx_solve_result(self) -> None:
        cond = _make_condenser()
        result = cond.evaluate_heat_exchanger(_make_input())
        assert isinstance(result, HXSolveResult)

    def test_result_has_primary_state_out(self) -> None:
        cond = _make_condenser()
        result = cond.evaluate_heat_exchanger(_make_input())
        assert isinstance(result.primary_state_out, FluidState)

    def test_result_has_q(self) -> None:
        cond = _make_condenser()
        Q = -2000.0
        result = cond.evaluate_heat_exchanger(_make_input(Q=Q))
        assert result.Q == Q

    def test_result_has_dp_primary(self) -> None:
        cond = _make_condenser()
        result = cond.evaluate_heat_exchanger(_make_input())
        assert hasattr(result, "dP_primary")
        assert math.isfinite(result.dP_primary)

    def test_result_has_verdicts(self) -> None:
        cond = _make_condenser()
        result = cond.evaluate_heat_exchanger(_make_input())
        assert hasattr(result, "verdicts")
        assert isinstance(result.verdicts, tuple)

    def test_negative_q_decreases_enthalpy(self) -> None:
        from mpl_sim.hx_models.epsilon_ntu import EpsilonNTUModel

        cond = _make_condenser()
        Q, mdot = -3000.0, 0.06
        inp = CondenserHXInput(
            primary_state_in=_STATE_IN,
            primary_mdot=mdot,
            secondary_bc=FixedHeatRate(Q=Q),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars={"rho": 1100.0, "mu": 1e-4},
        )
        result = cond.evaluate_heat_exchanger(inp)
        expected_h = _STATE_IN.h + Q / mdot
        assert math.isclose(result.primary_state_out.h, expected_h, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# No derived state stored
# ---------------------------------------------------------------------------


class TestNoStoredDerivedState:
    def test_component_has_no_q_attribute(self) -> None:
        cond = _make_condenser()
        assert not hasattr(cond, "Q")

    def test_component_has_no_htc_attribute(self) -> None:
        cond = _make_condenser()
        assert not hasattr(cond, "htc")

    def test_evaluate_does_not_mutate_component(self) -> None:
        cond = _make_condenser()
        cid_before = cond.component_id
        geom_before = cond.geometry
        cond.evaluate_heat_exchanger(_make_input())
        assert cond.component_id is cid_before
        assert cond.geometry is geom_before


# ---------------------------------------------------------------------------
# Import boundary
# ---------------------------------------------------------------------------


def _import_lines(module_file: str) -> list[str]:
    with open(module_file) as f:
        return [ln.strip() for ln in f if ln.strip().startswith(("import ", "from "))]


class TestCondenserImportBoundary:
    def _imports(self) -> list[str]:
        import mpl_sim.components.condenser as m

        assert m.__file__ is not None
        return _import_lines(m.__file__)

    def test_does_not_import_network(self) -> None:
        for ln in self._imports():
            assert "network" not in ln

    def test_does_not_import_solvers(self) -> None:
        for ln in self._imports():
            assert "solvers" not in ln

    def test_does_not_import_coolprop(self) -> None:
        for ln in self._imports():
            assert "coolprop" not in ln.lower()

    def test_does_not_import_properties(self) -> None:
        for ln in self._imports():
            assert "properties" not in ln
