# src/qemu_mcp/runtimes/loader.py
import pkgutil
import importlib
import logging
from typing import List, Type, Optional
from .base import TargetRuntime
from qemu_mcp import runtimes as runtimes_pkg

logger = logging.getLogger("qemu_mcp.runtimes")

def _load_runtimes() -> List[Type[TargetRuntime]]:
    """Dynamically collects all classes implementing the TargetRuntime contract."""
    discovered_runtimes: List[Type[TargetRuntime]] = []

    for _, module_name, ispkg in pkgutil.iter_modules(runtimes_pkg.__path__):
        if not ispkg or module_name in ["__pycache__", "core"]:
            continue
        try:
            module = importlib.import_module(f"qemu_mcp.runtimes.{module_name}.runtime")
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type) 
                    and issubclass(attr, TargetRuntime) 
                    and attr is not TargetRuntime
                ):
                    discovered_runtimes.append(attr)
        except Exception as e:
            logger.error(f"Failed to dynamically load module [{module_name}]: {e}")

    return discovered_runtimes

RUNTIMES = _load_runtimes()

def get_runtime_class(os_name: str) -> Optional[Type[TargetRuntime]]:
    """
    Directly resolves the runtime engine class dynamically matching
    the class-level 'os_name' attribute to the configuration profile token.
    """
    target_os = os_name.lower()
    
    for runtime_cls in RUNTIMES:
        # Check the class attribute directly
        if getattr(runtime_cls, "os_name", "").lower() == target_os:
            return runtime_cls
            
    return None

