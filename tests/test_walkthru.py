"""Smoke tests for walkthru."""


def test_import():
    """The package imports without error."""
    import walkthru  # noqa: F401


def test_has_version():
    """The package exposes a version string."""
    import walkthru

    assert isinstance(walkthru.__version__, str)
