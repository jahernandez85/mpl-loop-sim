"""Phase 5A — calibration primitive tests.

Validates:
- CalibrationTargetKind enum values.
- CalibrationTargetId construction, validation, immutability.
- CalibrationModifierKind enum values.
- CalibrationModifier construction (multiplier, offset, affine).
- CalibrationModifier rejects NaN/infinity.
- CalibrationModifier is immutable.
- CalibrationModifier.apply_to_scalar works correctly.
- CalibrationSet construction (empty and non-empty).
- CalibrationSet is immutable.
- CalibrationSet deterministic ordering.
- CalibrationSet.modifiers_for returns expected modifiers.
- Mutation of original iterable does not affect CalibrationSet.
- CalibrationMode, CalibrationTarget, CalibrationScope enum values.
- CalibrationFactor construction and validation.
- CalibrationReport construction and is_empty.
- Import purity: calibration must not pull in CoolProp or forbidden packages.
"""

from __future__ import annotations

import dataclasses

import pytest

from mpl_sim.calibration import (
    CalibrationFactor,
    CalibrationMode,
    CalibrationModifier,
    CalibrationModifierKind,
    CalibrationReport,
    CalibrationScope,
    CalibrationSet,
    CalibrationTarget,
    CalibrationTargetId,
    CalibrationTargetKind,
    SeamLocation,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def correlation_target() -> CalibrationTargetId:
    return CalibrationTargetId(
        kind=CalibrationTargetKind.CORRELATION,
        name="churchill",
    )


@pytest.fixture()
def component_target() -> CalibrationTargetId:
    return CalibrationTargetId(
        kind=CalibrationTargetKind.COMPONENT,
        name="evaporator_1",
        field_name="htc_slot",
    )


@pytest.fixture()
def mult_modifier(correlation_target: CalibrationTargetId) -> CalibrationModifier:
    return CalibrationModifier.multiplier(correlation_target, factor=1.2)


@pytest.fixture()
def offset_modifier(correlation_target: CalibrationTargetId) -> CalibrationModifier:
    return CalibrationModifier.offset(correlation_target, offset_value=0.5)


@pytest.fixture()
def affine_modifier(correlation_target: CalibrationTargetId) -> CalibrationModifier:
    return CalibrationModifier.affine(correlation_target, scale=1.1, offset_value=-0.05)


@pytest.fixture()
def seam_location() -> SeamLocation:
    return SeamLocation(
        component_id="pipe_1",
        slot_name="friction_dp",
        scope=CalibrationScope.SLOT,
    )


# ---------------------------------------------------------------------------
# CalibrationTargetKind
# ---------------------------------------------------------------------------


class TestCalibrationTargetKind:
    def test_correlation_member_exists(self) -> None:
        assert CalibrationTargetKind.CORRELATION is not None

    def test_component_member_exists(self) -> None:
        assert CalibrationTargetKind.COMPONENT is not None

    def test_property_backend_member_exists(self) -> None:
        assert CalibrationTargetKind.PROPERTY_BACKEND is not None

    def test_geometry_member_exists(self) -> None:
        assert CalibrationTargetKind.GEOMETRY is not None

    def test_exactly_four_kinds(self) -> None:
        assert len(list(CalibrationTargetKind)) == 4


# ---------------------------------------------------------------------------
# CalibrationTargetId
# ---------------------------------------------------------------------------


class TestCalibrationTargetId:
    def test_basic_construction(self) -> None:
        tid = CalibrationTargetId(
            kind=CalibrationTargetKind.CORRELATION,
            name="churchill",
        )
        assert tid.kind is CalibrationTargetKind.CORRELATION
        assert tid.name == "churchill"
        assert tid.field_name is None

    def test_construction_with_field_name(self) -> None:
        tid = CalibrationTargetId(
            kind=CalibrationTargetKind.COMPONENT,
            name="evaporator_1",
            field_name="htc_slot",
        )
        assert tid.field_name == "htc_slot"

    def test_rejects_empty_name(self) -> None:
        with pytest.raises(ValueError, match="name must be non-empty"):
            CalibrationTargetId(kind=CalibrationTargetKind.CORRELATION, name="")

    def test_rejects_empty_field_name(self) -> None:
        with pytest.raises(ValueError, match="field_name.*non-empty"):
            CalibrationTargetId(
                kind=CalibrationTargetKind.CORRELATION,
                name="churchill",
                field_name="",
            )

    def test_none_field_name_is_valid(self) -> None:
        tid = CalibrationTargetId(
            kind=CalibrationTargetKind.GEOMETRY,
            name="pipe_geom",
            field_name=None,
        )
        assert tid.field_name is None

    def test_is_immutable(self) -> None:
        tid = CalibrationTargetId(
            kind=CalibrationTargetKind.CORRELATION,
            name="churchill",
        )
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            tid.name = "other"  # type: ignore[misc]

    def test_structural_equality(self) -> None:
        a = CalibrationTargetId(kind=CalibrationTargetKind.CORRELATION, name="x")
        b = CalibrationTargetId(kind=CalibrationTargetKind.CORRELATION, name="x")
        assert a == b

    def test_inequality_different_name(self) -> None:
        a = CalibrationTargetId(kind=CalibrationTargetKind.CORRELATION, name="x")
        b = CalibrationTargetId(kind=CalibrationTargetKind.CORRELATION, name="y")
        assert a != b

    def test_inequality_different_kind(self) -> None:
        a = CalibrationTargetId(kind=CalibrationTargetKind.CORRELATION, name="x")
        b = CalibrationTargetId(kind=CalibrationTargetKind.COMPONENT, name="x")
        assert a != b

    def test_inequality_different_field_name(self) -> None:
        a = CalibrationTargetId(kind=CalibrationTargetKind.COMPONENT, name="x", field_name="f1")
        b = CalibrationTargetId(kind=CalibrationTargetKind.COMPONENT, name="x", field_name="f2")
        assert a != b

    def test_hashable(self) -> None:
        tid = CalibrationTargetId(kind=CalibrationTargetKind.CORRELATION, name="x")
        assert isinstance(hash(tid), int)


# ---------------------------------------------------------------------------
# CalibrationModifierKind
# ---------------------------------------------------------------------------


class TestCalibrationModifierKind:
    def test_multiplier_member_exists(self) -> None:
        assert CalibrationModifierKind.MULTIPLIER is not None

    def test_offset_member_exists(self) -> None:
        assert CalibrationModifierKind.OFFSET is not None

    def test_affine_member_exists(self) -> None:
        assert CalibrationModifierKind.AFFINE is not None

    def test_exactly_three_kinds(self) -> None:
        assert len(list(CalibrationModifierKind)) == 3


# ---------------------------------------------------------------------------
# CalibrationModifier — construction
# ---------------------------------------------------------------------------


class TestCalibrationModifierConstruction:
    def test_multiplier_construction(self, correlation_target: CalibrationTargetId) -> None:
        m = CalibrationModifier.multiplier(correlation_target, factor=1.5)
        assert m.kind is CalibrationModifierKind.MULTIPLIER
        assert m.scale == pytest.approx(1.5)
        assert m.offset == pytest.approx(0.0)
        assert m.target == correlation_target
        assert m.note is None

    def test_offset_construction(self, correlation_target: CalibrationTargetId) -> None:
        m = CalibrationModifier.offset(correlation_target, offset_value=3.0)
        assert m.kind is CalibrationModifierKind.OFFSET
        assert m.scale == pytest.approx(1.0)
        assert m.offset == pytest.approx(3.0)
        assert m.target == correlation_target

    def test_affine_construction(self, correlation_target: CalibrationTargetId) -> None:
        m = CalibrationModifier.affine(correlation_target, scale=2.0, offset_value=-1.0)
        assert m.kind is CalibrationModifierKind.AFFINE
        assert m.scale == pytest.approx(2.0)
        assert m.offset == pytest.approx(-1.0)

    def test_note_is_stored(self, correlation_target: CalibrationTargetId) -> None:
        m = CalibrationModifier.multiplier(correlation_target, factor=1.0, note="from Kokate 2024")
        assert m.note == "from Kokate 2024"

    def test_direct_construction(self, correlation_target: CalibrationTargetId) -> None:
        m = CalibrationModifier(
            kind=CalibrationModifierKind.AFFINE,
            target=correlation_target,
            scale=1.5,
            offset=0.3,
        )
        assert m.kind is CalibrationModifierKind.AFFINE
        assert m.scale == pytest.approx(1.5)
        assert m.offset == pytest.approx(0.3)


# ---------------------------------------------------------------------------
# CalibrationModifier — NaN / infinity rejection
# ---------------------------------------------------------------------------


class TestCalibrationModifierValidation:
    def test_multiplier_rejects_nan_factor(self, correlation_target: CalibrationTargetId) -> None:
        with pytest.raises(ValueError, match="finite"):
            CalibrationModifier.multiplier(correlation_target, factor=float("nan"))

    def test_multiplier_rejects_pos_inf(self, correlation_target: CalibrationTargetId) -> None:
        with pytest.raises(ValueError, match="finite"):
            CalibrationModifier.multiplier(correlation_target, factor=float("inf"))

    def test_multiplier_rejects_neg_inf(self, correlation_target: CalibrationTargetId) -> None:
        with pytest.raises(ValueError, match="finite"):
            CalibrationModifier.multiplier(correlation_target, factor=float("-inf"))

    def test_offset_rejects_nan(self, correlation_target: CalibrationTargetId) -> None:
        with pytest.raises(ValueError, match="finite"):
            CalibrationModifier.offset(correlation_target, offset_value=float("nan"))

    def test_offset_rejects_inf(self, correlation_target: CalibrationTargetId) -> None:
        with pytest.raises(ValueError, match="finite"):
            CalibrationModifier.offset(correlation_target, offset_value=float("inf"))

    def test_affine_rejects_nan_scale(self, correlation_target: CalibrationTargetId) -> None:
        with pytest.raises(ValueError, match="finite"):
            CalibrationModifier.affine(correlation_target, scale=float("nan"), offset_value=0.0)

    def test_affine_rejects_inf_offset(self, correlation_target: CalibrationTargetId) -> None:
        with pytest.raises(ValueError, match="finite"):
            CalibrationModifier.affine(correlation_target, scale=1.0, offset_value=float("inf"))

    def test_direct_construction_rejects_nan_scale(
        self, correlation_target: CalibrationTargetId
    ) -> None:
        with pytest.raises(ValueError, match="finite"):
            CalibrationModifier(
                kind=CalibrationModifierKind.AFFINE,
                target=correlation_target,
                scale=float("nan"),
                offset=0.0,
            )

    def test_direct_construction_rejects_nan_offset(
        self, correlation_target: CalibrationTargetId
    ) -> None:
        with pytest.raises(ValueError, match="finite"):
            CalibrationModifier(
                kind=CalibrationModifierKind.OFFSET,
                target=correlation_target,
                scale=1.0,
                offset=float("nan"),
            )


# ---------------------------------------------------------------------------
# CalibrationModifier — immutability
# ---------------------------------------------------------------------------


class TestCalibrationModifierImmutability:
    def test_is_immutable_scale(self, mult_modifier: CalibrationModifier) -> None:
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            mult_modifier.scale = 9.9  # type: ignore[misc]

    def test_is_immutable_offset(self, offset_modifier: CalibrationModifier) -> None:
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            offset_modifier.offset = 99.0  # type: ignore[misc]

    def test_is_frozen_dataclass(self) -> None:
        assert dataclasses.is_dataclass(CalibrationModifier)


# ---------------------------------------------------------------------------
# CalibrationModifier — apply_to_scalar
# ---------------------------------------------------------------------------


class TestCalibrationModifierApplyToScalar:
    def test_multiplier_apply(self, mult_modifier: CalibrationModifier) -> None:
        # scale = 1.2
        assert mult_modifier.apply_to_scalar(10.0) == pytest.approx(12.0)

    def test_offset_apply(self, offset_modifier: CalibrationModifier) -> None:
        # offset = 0.5
        assert offset_modifier.apply_to_scalar(10.0) == pytest.approx(10.5)

    def test_affine_apply(self, affine_modifier: CalibrationModifier) -> None:
        # scale = 1.1, offset = -0.05
        expected = 1.1 * 10.0 + (-0.05)
        assert affine_modifier.apply_to_scalar(10.0) == pytest.approx(expected)

    def test_neutral_multiplier_is_identity(self, correlation_target: CalibrationTargetId) -> None:
        m = CalibrationModifier.multiplier(correlation_target, factor=1.0)
        assert m.apply_to_scalar(42.0) == pytest.approx(42.0)

    def test_zero_offset_is_identity(self, correlation_target: CalibrationTargetId) -> None:
        m = CalibrationModifier.offset(correlation_target, offset_value=0.0)
        assert m.apply_to_scalar(42.0) == pytest.approx(42.0)

    def test_neutral_affine_is_identity(self, correlation_target: CalibrationTargetId) -> None:
        m = CalibrationModifier.affine(correlation_target, scale=1.0, offset_value=0.0)
        assert m.apply_to_scalar(42.0) == pytest.approx(42.0)

    def test_multiplier_zero_factor(self, correlation_target: CalibrationTargetId) -> None:
        m = CalibrationModifier.multiplier(correlation_target, factor=0.0)
        assert m.apply_to_scalar(100.0) == pytest.approx(0.0)

    def test_negative_scale(self, correlation_target: CalibrationTargetId) -> None:
        m = CalibrationModifier.multiplier(correlation_target, factor=-2.0)
        assert m.apply_to_scalar(5.0) == pytest.approx(-10.0)


# ---------------------------------------------------------------------------
# CalibrationSet
# ---------------------------------------------------------------------------


class TestCalibrationSet:
    def test_empty_construction(self) -> None:
        cs = CalibrationSet()
        assert cs.is_empty
        assert len(cs) == 0

    def test_empty_factory(self) -> None:
        cs = CalibrationSet.empty()
        assert cs.is_empty

    def test_construction_with_single_modifier(self, mult_modifier: CalibrationModifier) -> None:
        cs = CalibrationSet([mult_modifier])
        assert not cs.is_empty
        assert len(cs) == 1

    def test_construction_with_multiple_modifiers(
        self,
        mult_modifier: CalibrationModifier,
        offset_modifier: CalibrationModifier,
    ) -> None:
        cs = CalibrationSet([mult_modifier, offset_modifier])
        assert len(cs) == 2

    def test_deterministic_ordering(
        self,
        mult_modifier: CalibrationModifier,
        offset_modifier: CalibrationModifier,
    ) -> None:
        cs = CalibrationSet([mult_modifier, offset_modifier])
        items = list(cs)
        assert items[0] is mult_modifier
        assert items[1] is offset_modifier

    def test_modifiers_for_returns_matching(
        self,
        correlation_target: CalibrationTargetId,
        component_target: CalibrationTargetId,
        mult_modifier: CalibrationModifier,
    ) -> None:
        comp_mod = CalibrationModifier.multiplier(component_target, factor=0.9)
        cs = CalibrationSet([mult_modifier, comp_mod])
        result = cs.modifiers_for(correlation_target)
        assert len(result) == 1
        assert result[0] is mult_modifier

    def test_modifiers_for_returns_multiple_matches(
        self,
        correlation_target: CalibrationTargetId,
        mult_modifier: CalibrationModifier,
        offset_modifier: CalibrationModifier,
    ) -> None:
        cs = CalibrationSet([mult_modifier, offset_modifier])
        result = cs.modifiers_for(correlation_target)
        assert len(result) == 2

    def test_modifiers_for_empty_when_no_match(
        self,
        component_target: CalibrationTargetId,
        mult_modifier: CalibrationModifier,
    ) -> None:
        cs = CalibrationSet([mult_modifier])
        result = cs.modifiers_for(component_target)
        assert result == ()

    def test_modifiers_for_empty_set(self, correlation_target: CalibrationTargetId) -> None:
        cs = CalibrationSet.empty()
        result = cs.modifiers_for(correlation_target)
        assert result == ()

    def test_is_immutable_via_setattr(self, mult_modifier: CalibrationModifier) -> None:
        cs = CalibrationSet([mult_modifier])
        with pytest.raises(AttributeError):
            cs._modifiers = ()  # type: ignore[misc]

    def test_is_immutable_new_attribute(self, mult_modifier: CalibrationModifier) -> None:
        cs = CalibrationSet([mult_modifier])
        with pytest.raises(AttributeError):
            cs.new_field = "bad"  # type: ignore[attr-defined]

    def test_mutation_of_original_list_does_not_affect_set(
        self,
        mult_modifier: CalibrationModifier,
        offset_modifier: CalibrationModifier,
    ) -> None:
        source = [mult_modifier]
        cs = CalibrationSet(source)
        source.append(offset_modifier)
        assert len(cs) == 1

    def test_equality_same_contents(self, mult_modifier: CalibrationModifier) -> None:
        a = CalibrationSet([mult_modifier])
        b = CalibrationSet([mult_modifier])
        assert a == b

    def test_inequality_different_modifiers(
        self,
        mult_modifier: CalibrationModifier,
        offset_modifier: CalibrationModifier,
    ) -> None:
        a = CalibrationSet([mult_modifier])
        b = CalibrationSet([offset_modifier])
        assert a != b

    def test_empty_sets_are_equal(self) -> None:
        assert CalibrationSet() == CalibrationSet()

    def test_iter_returns_modifiers_in_order(
        self,
        mult_modifier: CalibrationModifier,
        offset_modifier: CalibrationModifier,
    ) -> None:
        cs = CalibrationSet([mult_modifier, offset_modifier])
        assert list(cs) == [mult_modifier, offset_modifier]

    def test_hashable(self, mult_modifier: CalibrationModifier) -> None:
        cs = CalibrationSet([mult_modifier])
        assert isinstance(hash(cs), int)

    def test_rejects_non_modifier_element(self, mult_modifier: CalibrationModifier) -> None:
        with pytest.raises(TypeError):
            CalibrationSet([mult_modifier, "not_a_modifier"])  # type: ignore[list-item]

    def test_construction_from_generator(
        self,
        mult_modifier: CalibrationModifier,
        offset_modifier: CalibrationModifier,
    ) -> None:
        gen = (m for m in [mult_modifier, offset_modifier])
        cs = CalibrationSet(gen)
        assert len(cs) == 2


# ---------------------------------------------------------------------------
# CalibrationMode
# ---------------------------------------------------------------------------


class TestCalibrationMode:
    def test_none_member_exists(self) -> None:
        assert CalibrationMode.NONE is not None

    def test_target_member_exists(self) -> None:
        assert CalibrationMode.TARGET is not None

    def test_exactly_two_modes(self) -> None:
        assert len(list(CalibrationMode)) == 2


# ---------------------------------------------------------------------------
# CalibrationTarget
# ---------------------------------------------------------------------------


class TestCalibrationTarget:
    def test_friction_gradient_member_exists(self) -> None:
        assert CalibrationTarget.FRICTION_GRADIENT is not None

    def test_htc_member_exists(self) -> None:
        assert CalibrationTarget.HTC is not None

    def test_ua_member_exists(self) -> None:
        assert CalibrationTarget.UA is not None

    def test_exactly_three_targets(self) -> None:
        assert len(list(CalibrationTarget)) == 3


# ---------------------------------------------------------------------------
# CalibrationScope
# ---------------------------------------------------------------------------


class TestCalibrationScope:
    def test_slot_member_exists(self) -> None:
        assert CalibrationScope.SLOT is not None

    def test_component_member_exists(self) -> None:
        assert CalibrationScope.COMPONENT is not None

    def test_global_member_exists(self) -> None:
        assert CalibrationScope.GLOBAL is not None

    def test_exactly_three_scopes(self) -> None:
        assert len(list(CalibrationScope)) == 3


# ---------------------------------------------------------------------------
# SeamLocation
# ---------------------------------------------------------------------------


class TestSeamLocation:
    def test_construction(self) -> None:
        s = SeamLocation(
            component_id="pipe_1",
            slot_name="friction_dp",
            scope=CalibrationScope.SLOT,
        )
        assert s.component_id == "pipe_1"
        assert s.slot_name == "friction_dp"
        assert s.scope is CalibrationScope.SLOT

    def test_none_slot_name(self) -> None:
        s = SeamLocation(
            component_id="pipe_1",
            slot_name=None,
            scope=CalibrationScope.COMPONENT,
        )
        assert s.slot_name is None

    def test_rejects_empty_component_id(self) -> None:
        with pytest.raises(ValueError, match="component_id"):
            SeamLocation(
                component_id="",
                slot_name=None,
                scope=CalibrationScope.GLOBAL,
            )

    def test_rejects_empty_slot_name(self) -> None:
        with pytest.raises(ValueError, match="slot_name"):
            SeamLocation(
                component_id="pipe_1",
                slot_name="",
                scope=CalibrationScope.SLOT,
            )

    def test_is_immutable(self, seam_location: SeamLocation) -> None:
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            seam_location.component_id = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CalibrationFactor
# ---------------------------------------------------------------------------


class TestCalibrationFactor:
    def test_construction(self, seam_location: SeamLocation) -> None:
        f = CalibrationFactor(
            target=CalibrationTarget.FRICTION_GRADIENT,
            value=1.1,
            mode=CalibrationMode.TARGET,
            seam=seam_location,
        )
        assert f.target is CalibrationTarget.FRICTION_GRADIENT
        assert f.value == pytest.approx(1.1)
        assert f.mode is CalibrationMode.TARGET
        assert f.seam is seam_location

    def test_neutral_value_is_one(self, seam_location: SeamLocation) -> None:
        f = CalibrationFactor(
            target=CalibrationTarget.HTC,
            value=1.0,
            mode=CalibrationMode.NONE,
            seam=seam_location,
        )
        assert f.value == pytest.approx(1.0)

    def test_rejects_nan(self, seam_location: SeamLocation) -> None:
        with pytest.raises(ValueError, match="finite"):
            CalibrationFactor(
                target=CalibrationTarget.FRICTION_GRADIENT,
                value=float("nan"),
                mode=CalibrationMode.TARGET,
                seam=seam_location,
            )

    def test_rejects_inf(self, seam_location: SeamLocation) -> None:
        with pytest.raises(ValueError, match="finite"):
            CalibrationFactor(
                target=CalibrationTarget.FRICTION_GRADIENT,
                value=float("inf"),
                mode=CalibrationMode.TARGET,
                seam=seam_location,
            )

    def test_is_immutable(self, seam_location: SeamLocation) -> None:
        f = CalibrationFactor(
            target=CalibrationTarget.UA,
            value=1.0,
            mode=CalibrationMode.NONE,
            seam=seam_location,
        )
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            f.value = 2.0  # type: ignore[misc]

    def test_all_targets_constructible(self, seam_location: SeamLocation) -> None:
        for target in CalibrationTarget:
            f = CalibrationFactor(
                target=target,
                value=1.0,
                mode=CalibrationMode.NONE,
                seam=seam_location,
            )
            assert f.target is target


# ---------------------------------------------------------------------------
# CalibrationReport
# ---------------------------------------------------------------------------


class TestCalibrationReport:
    def test_empty_factory_defaults(self) -> None:
        r = CalibrationReport.empty()
        assert r.is_empty
        assert r.mode is CalibrationMode.NONE
        assert r.factors == ()

    def test_empty_factory_with_target_mode(self) -> None:
        r = CalibrationReport.empty(CalibrationMode.TARGET)
        assert r.mode is CalibrationMode.TARGET
        assert r.is_empty

    def test_construction_with_factors(self, seam_location: SeamLocation) -> None:
        f = CalibrationFactor(
            target=CalibrationTarget.FRICTION_GRADIENT,
            value=1.2,
            mode=CalibrationMode.TARGET,
            seam=seam_location,
        )
        r = CalibrationReport(factors=(f,), mode=CalibrationMode.TARGET)
        assert not r.is_empty
        assert len(r.factors) == 1
        assert r.factors[0] is f

    def test_factors_coerced_to_tuple(self, seam_location: SeamLocation) -> None:
        f = CalibrationFactor(
            target=CalibrationTarget.HTC,
            value=1.0,
            mode=CalibrationMode.NONE,
            seam=seam_location,
        )
        r = CalibrationReport(factors=[f], mode=CalibrationMode.NONE)  # type: ignore[arg-type]
        assert isinstance(r.factors, tuple)

    def test_is_immutable(self) -> None:
        r = CalibrationReport.empty()
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            r.mode = CalibrationMode.TARGET  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Import purity
# ---------------------------------------------------------------------------


class TestImportPurity:
    def test_calibration_has_no_forbidden_imports(self) -> None:
        """Verify that importing mpl_sim.calibration does not pull in any
        forbidden packages in a fresh interpreter subprocess.

        Checked by spawning a clean Python process so the test is not
        contaminated by other modules already in sys.modules from the
        full test suite.
        """
        import subprocess
        import sys

        forbidden_prefixes = [
            "CoolProp",
            "mpl_sim.properties",
            "mpl_sim.correlations",
            "mpl_sim.geometry",
            "mpl_sim.discretization",
            "mpl_sim.components",
            "mpl_sim.network",
            "mpl_sim.solvers",
        ]
        check = (
            "import mpl_sim.calibration, sys; "
            f"forbidden = {forbidden_prefixes!r}; "
            "bad = [k for k in sys.modules "
            "if any(k == p or k.startswith(p + '.') for p in forbidden)]; "
            "assert not bad, f'calibration imported forbidden modules: {bad}'"
        )
        result = subprocess.run(
            [sys.executable, "-c", check],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Import purity check failed:\n{result.stderr}"
