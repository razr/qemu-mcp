# tests/test_loader.py
import inspect
import pytest

from qemu_mcp.runtimes.loader import get_runtime_class
from qemu_mcp.runtimes.vxworks.runtime import VxWorksRuntime


def test_dynamic_os_parameter_loading(os_name):
    """
    Loads any target OS class by its parameter token name and dumps its 
    underlying methods to prove it successfully resolved the true runtime asset.
    Fails hard with an execution error if the requested OS is not found.
    """
    # 1. Resolve the runtime class dynamically from the real discovered plugins
    runtime_cls = get_runtime_class(os_name)
    
    # 2. Hard validation guard: If the plugin is missing, fail the test immediately
    if runtime_cls is None:
        pytest.fail(f"Execution Error: No registered runtime found matching OS token: '{os_name}'")

    # 3. Extract all functions explicitly implemented or overridden in this subclass
    runtime_methods = [
        name for name, func in inspect.getmembers(runtime_cls, predicate=inspect.isfunction)
        if not name.startswith("_")  # Ignore private/protected base implementation mechanics
    ]

    # 4. Print structured debug blocks down stdout to prove class authenticity
    print(f"\n\n==================================================")
    print(f" DYNAMIC RUNTIME PROOF FOR OS TOKEN: '{os_name}'")
    print(f"==================================================")
    print(f" Resolved Class Type : {runtime_cls.__name__}")
    print(f" Bound Registration Key: {getattr(runtime_cls, 'os_name', 'None')}")
    print(f" Implemented Functions : {sorted(runtime_methods)}")
    print(f"==================================================\n")

    # 5. Enforce baseline polymorphic structural constraints
    assert getattr(runtime_cls, "os_name", "").lower() == os_name.lower()
    assert "exec" in runtime_methods
    assert "status" in runtime_methods


def test_default_vxworks_resolution_baseline():
    """
    Sanity check to guarantee that 'vxworks' matches the real VxWorksRuntime class
    and that the dynamic string attribute link is correctly established.
    """
    runtime_cls = get_runtime_class("vxworks")
    assert runtime_cls is not None
    assert runtime_cls == VxWorksRuntime

