"""Tests for project infrastructure."""

def test_project_imports():
    """Verify the arena_buddy package can be imported."""
    import arena_buddy
    assert arena_buddy.__version__ == "0.1.0"


def test_package_has_init():
    """Verify __init__.py exists and is importable."""
    from arena_buddy import __version__
    assert isinstance(__version__, str)
