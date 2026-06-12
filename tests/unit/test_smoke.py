"""Phase 0 smoke test — verifies the package is importable."""


def test_import_mpl_sim():
    import mpl_sim  # noqa: F401


def test_version_attribute():
    import mpl_sim

    assert isinstance(mpl_sim.__version__, str)
    assert mpl_sim.__version__  # non-empty
