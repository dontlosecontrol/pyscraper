import pkgutil
import importlib

# Iterate over all modules in the current package directory
for loader, module_name, is_pkg in pkgutil.walk_packages(__path__):
    if not is_pkg: # Ensure it's a module, not subpackage
        # Dynamically import the module
        # The module_name is relative to the current package
        importlib.import_module(f".{module_name}", __package__)
