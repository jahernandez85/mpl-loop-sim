"""Phase 4B — immutable discretization primitive tests.

Validates:
- DiscretizationMode membership (lumped, uniform, moving-boundary).
- DiscretizationSpec construction, validation, and immutability.
- CellIndex construction, validation, and immutability.
- CellSpan construction, validation, and immutability.
- UniformGrid construction, cell geometry, coverage, and immutability.
- Import purity: discretization must not pull in CoolProp or higher-layer packages.
"""

from __future__ import annotations

import dataclasses
import math

import pytest

from mpl_sim.discretization import (
    CellIndex,
    CellSpan,
    DiscretizationMode,
    DiscretizationSpec,
    UniformGrid,
)

# ---------------------------------------------------------------------------
# DiscretizationMode
# ---------------------------------------------------------------------------


class TestDiscretizationMode:
    def test_lumped_member_exists(self) -> None:
        assert DiscretizationMode.LUMPED is not None

    def test_uniform_member_exists(self) -> None:
        assert DiscretizationMode.UNIFORM is not None

    def test_moving_boundary_member_exists(self) -> None:
        assert DiscretizationMode.MOVING_BOUNDARY is not None

    def test_exactly_three_modes(self) -> None:
        assert len(list(DiscretizationMode)) == 3


# ---------------------------------------------------------------------------
# DiscretizationSpec
# ---------------------------------------------------------------------------


class TestDiscretizationSpec:
    def test_lumped_construction(self) -> None:
        spec = DiscretizationSpec(mode=DiscretizationMode.LUMPED)
        assert spec.mode is DiscretizationMode.LUMPED
        assert spec.n_cells is None

    def test_lumped_with_explicit_one_cell(self) -> None:
        spec = DiscretizationSpec(mode=DiscretizationMode.LUMPED, n_cells=1)
        assert spec.n_cells == 1

    def test_uniform_construction(self) -> None:
        spec = DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=10)
        assert spec.mode is DiscretizationMode.UNIFORM
        assert spec.n_cells == 10

    def test_moving_boundary_construction(self) -> None:
        spec = DiscretizationSpec(mode=DiscretizationMode.MOVING_BOUNDARY)
        assert spec.mode is DiscretizationMode.MOVING_BOUNDARY

    def test_label_optional(self) -> None:
        spec = DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=5, label="pipe-a")
        assert spec.label == "pipe-a"

    def test_label_defaults_to_none(self) -> None:
        spec = DiscretizationSpec(mode=DiscretizationMode.LUMPED)
        assert spec.label is None

    def test_uniform_rejects_missing_n_cells(self) -> None:
        with pytest.raises(ValueError, match="n_cells"):
            DiscretizationSpec(mode=DiscretizationMode.UNIFORM)

    def test_uniform_rejects_zero_n_cells(self) -> None:
        with pytest.raises(ValueError, match="n_cells"):
            DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=0)

    def test_uniform_rejects_negative_n_cells(self) -> None:
        with pytest.raises(ValueError, match="n_cells"):
            DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=-1)

    def test_lumped_rejects_n_cells_greater_than_one(self) -> None:
        with pytest.raises(ValueError):
            DiscretizationSpec(mode=DiscretizationMode.LUMPED, n_cells=5)

    def test_immutable(self) -> None:
        spec = DiscretizationSpec(mode=DiscretizationMode.LUMPED)
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            spec.mode = DiscretizationMode.UNIFORM  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CellIndex
# ---------------------------------------------------------------------------


class TestCellIndex:
    def test_construction_zero(self) -> None:
        ci = CellIndex(index=0)
        assert ci.index == 0

    def test_construction_positive(self) -> None:
        ci = CellIndex(index=7)
        assert ci.index == 7

    def test_rejects_negative_index(self) -> None:
        with pytest.raises(ValueError, match="index"):
            CellIndex(index=-1)

    def test_immutable(self) -> None:
        ci = CellIndex(index=3)
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            ci.index = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CellSpan
# ---------------------------------------------------------------------------


class TestCellSpan:
    def test_construction(self) -> None:
        cs = CellSpan(index=0, x0=0.0, x1=1.0)
        assert cs.index == 0
        assert cs.x0 == pytest.approx(0.0)
        assert cs.x1 == pytest.approx(1.0)

    def test_x0_zero_is_allowed(self) -> None:
        cs = CellSpan(index=0, x0=0.0, x1=0.5)
        assert cs.x0 == 0.0

    def test_rejects_x1_equal_to_x0(self) -> None:
        with pytest.raises(ValueError, match="x1"):
            CellSpan(index=0, x0=1.0, x1=1.0)

    def test_rejects_x1_less_than_x0(self) -> None:
        with pytest.raises(ValueError, match="x1"):
            CellSpan(index=0, x0=2.0, x1=0.5)

    def test_rejects_negative_x0(self) -> None:
        with pytest.raises(ValueError, match="x0"):
            CellSpan(index=0, x0=-0.1, x1=1.0)

    def test_immutable(self) -> None:
        cs = CellSpan(index=0, x0=0.0, x1=1.0)
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            cs.x0 = 99.0  # type: ignore[misc]

    def test_does_not_store_physical_state(self) -> None:
        cs = CellSpan(index=0, x0=0.0, x1=1.0)
        forbidden = [
            "pressure",
            "enthalpy",
            "mdot",
            "quality",
            "phase",
            "rho",
            "mu",
            "Re",
            "f",
            "dP",
            "HTC",
            "Nu",
        ]
        for attr in forbidden:
            assert not hasattr(cs, attr), f"CellSpan must not expose '{attr}'"


# ---------------------------------------------------------------------------
# UniformGrid
# ---------------------------------------------------------------------------


class TestUniformGrid:
    def test_construction(self) -> None:
        grid = UniformGrid(length=1.0, n_cells=4)
        assert grid.length == pytest.approx(1.0)
        assert grid.n_cells == 4

    def test_from_length_factory(self) -> None:
        grid = UniformGrid.from_length(2.0, 8)
        assert grid.length == pytest.approx(2.0)
        assert grid.n_cells == 8

    def test_cell_length_equals_length_over_n(self) -> None:
        grid = UniformGrid(length=1.0, n_cells=4)
        assert grid.cell_length == pytest.approx(0.25)

    def test_cell_length_formula_non_trivial(self) -> None:
        grid = UniformGrid(length=3.0, n_cells=7)
        assert grid.cell_length == pytest.approx(3.0 / 7)

    def test_rejects_zero_length(self) -> None:
        with pytest.raises(ValueError, match="length"):
            UniformGrid(length=0.0, n_cells=4)

    def test_rejects_negative_length(self) -> None:
        with pytest.raises(ValueError, match="length"):
            UniformGrid(length=-1.0, n_cells=4)

    def test_rejects_zero_n_cells(self) -> None:
        with pytest.raises(ValueError, match="n_cells"):
            UniformGrid(length=1.0, n_cells=0)

    def test_rejects_negative_n_cells(self) -> None:
        with pytest.raises(ValueError, match="n_cells"):
            UniformGrid(length=1.0, n_cells=-3)

    def test_immutable(self) -> None:
        grid = UniformGrid(length=1.0, n_cells=4)
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            grid.length = 99.0  # type: ignore[misc]

    def test_cells_is_tuple(self) -> None:
        grid = UniformGrid(length=1.0, n_cells=4)
        assert isinstance(grid.cells, tuple)

    def test_cells_contain_cell_span_instances(self) -> None:
        grid = UniformGrid(length=1.0, n_cells=4)
        for cell in grid.cells:
            assert isinstance(cell, CellSpan)

    def test_cells_count_equals_n_cells(self) -> None:
        grid = UniformGrid(length=1.0, n_cells=5)
        assert len(grid.cells) == 5

    def test_cells_are_deterministic(self) -> None:
        grid = UniformGrid(length=1.0, n_cells=4)
        assert grid.cells == grid.cells

    def test_cells_start_at_zero(self) -> None:
        grid = UniformGrid(length=1.0, n_cells=3)
        assert grid.cells[0].x0 == pytest.approx(0.0)

    def test_cells_end_at_total_length(self) -> None:
        grid = UniformGrid(length=3.0, n_cells=7)
        assert grid.cells[-1].x1 == pytest.approx(3.0, rel=1e-12)

    def test_cells_are_contiguous(self) -> None:
        grid = UniformGrid(length=2.0, n_cells=5)
        cells = grid.cells
        for i in range(len(cells) - 1):
            assert cells[i].x1 == pytest.approx(cells[i + 1].x0)

    def test_cells_are_equal_length(self) -> None:
        grid = UniformGrid(length=1.0, n_cells=4)
        dx = grid.cell_length
        for cell in grid.cells:
            assert (cell.x1 - cell.x0) == pytest.approx(dx)

    def test_cell_indices_are_sequential_from_zero(self) -> None:
        grid = UniformGrid(length=1.0, n_cells=5)
        for i, cell in enumerate(grid.cells):
            assert cell.index == i

    def test_single_cell_grid(self) -> None:
        grid = UniformGrid(length=5.0, n_cells=1)
        cells = grid.cells
        assert len(cells) == 1
        assert cells[0].x0 == pytest.approx(0.0)
        assert cells[0].x1 == pytest.approx(5.0)

    def test_total_coverage_equals_length(self) -> None:
        grid = UniformGrid(length=7.3, n_cells=13)
        total = sum(c.x1 - c.x0 for c in grid.cells)
        assert math.isclose(total, grid.length, rel_tol=1e-12)

    def test_does_not_expose_physical_state(self) -> None:
        grid = UniformGrid(length=1.0, n_cells=4)
        forbidden = [
            "pressure",
            "enthalpy",
            "mdot",
            "quality",
            "phase",
            "rho",
            "mu",
            "Re",
            "f",
            "dP",
            "HTC",
            "Nu",
        ]
        for attr in forbidden:
            assert not hasattr(grid, attr), f"UniformGrid must not expose '{attr}'"


# ---------------------------------------------------------------------------
# Import purity
# ---------------------------------------------------------------------------


class TestImportPurity:
    def test_primitives_does_not_import_coolprop(self) -> None:
        import mpl_sim.discretization.primitives as prim_mod

        assert prim_mod.__file__ is not None
        with open(prim_mod.__file__) as fh:
            lines = fh.readlines()
        import_lines = [ln for ln in lines if ln.strip().startswith(("import ", "from "))]
        for ln in import_lines:
            assert (
                "CoolProp" not in ln and "coolprop" not in ln.lower()
            ), f"discretization/primitives.py must not import CoolProp: {ln.rstrip()!r}"

    def test_primitives_does_not_import_forbidden_packages(self) -> None:
        import mpl_sim.discretization.primitives as prim_mod

        assert prim_mod.__file__ is not None
        with open(prim_mod.__file__) as fh:
            lines = fh.readlines()
        import_lines = [ln for ln in lines if ln.strip().startswith(("import ", "from "))]

        forbidden = [
            "mpl_sim.properties",
            "mpl_sim.correlations",
            "mpl_sim.components",
            "mpl_sim.calibration",
            "mpl_sim.network",
            "mpl_sim.solvers",
            "mpl_sim.geometry",
        ]
        for ln in import_lines:
            for pkg in forbidden:
                assert (
                    pkg not in ln
                ), f"discretization/primitives.py must not import '{pkg}': {ln.rstrip()!r}"
