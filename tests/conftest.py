# tests/conftest.py
import pytest

def pytest_addoption(parser):
    """Registers the custom --kernel-path argument with pytest CLI."""
    parser.addoption(
        "--kernel-path",
        action="store",
        default=None,
        help="Absolute path to a real compiled 64-bit kernel image file"
    )
    parser.addoption(
        "--os-name",
        action="store",
        default="vxworks",  # Hard default baseline matching your specification
        help="Target operating system name string (defaults to 'vxworks')"
    )

@pytest.fixture
def kernel_path(request):
    """Fixture to pass the runtime CLI argument value directly into test cases."""
    return request.config.getoption("--kernel-path")

@pytest.fixture
def os_name(request):
    """Fixture to inject the user or default OS name string parameter."""
    return request.config.getoption("--os-name")
