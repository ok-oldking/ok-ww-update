# import importlib
# import os
#
#
# def _import_submodules(package_name, package_path, blacklist=None, debug=False):
#     """Imports all Python modules within subdirectories of a package.
#
#     Args:
#         package_name: The name of the package (e.g., "ok").
#         package_path: The absolute path to the package directory.
#         blacklist: A list of subdirectory names to skip.
#         debug: Whether to print debug messages.
#     """
#
#     if blacklist is None:
#         blacklist = []
#
#     for item in os.listdir(package_path):
#         if item in blacklist:
#             if debug:
#                 print(f"Skipping blacklisted directory: {item}")
#             continue
#
#         item_path = os.path.join(package_path, item)
#         if os.path.isdir(item_path) and not item.startswith("_"):  # Skip private dirs
#             init_file = os.path.join(item_path, "__init__.py")
#             if os.path.exists(init_file):  # Only consider subdirs with __init__.py
#                 submodule_name = f"{package_name}.{item}"
#                 try:
#                     # submodule = importlib.import_module(submodule_name)
#                     # if debug:
#                     #     print(f"Imported submodule: {submodule_name}")
#                     # # Import all non-private names from __init__.py
#                     # for name, obj in submodule.__dict__.items():
#                     #     if not name.startswith("_"):
#                     #         globals()[name] = obj
#
#                     # Import all non-private names from .py files in the submodule
#                     for python_file in os.listdir(item_path):
#                         if python_file.endswith(
#                                 (".py", ".pyd")) and python_file != "__init__.py":  # Avoid reimporting __init__.py
#                             module_file_name = os.path.splitext(python_file)[0]
#                             if python_file.endswith(".pyd"):
#                                 module_file_name = os.path.splitext(module_file_name)[0]
#                             module_name_with_file = f"{submodule_name}.{module_file_name}"
#                             try:
#                                 submodule_file = importlib.import_module(module_name_with_file)
#                                 if debug:
#                                     print(f"Imported python file: {module_name_with_file}")
#                                 for name, obj in submodule_file.__dict__.items():
#                                     if not name.startswith("_"):
#                                         globals()[name] = obj
#                             except ImportError as e:
#                                 print(f"Error importing python file {module_name_with_file}: {e}")
#                             except Exception as e:
#                                 print(f"Unexpected error importing {module_name_with_file}: {e}")
#
#                 except ImportError as e:
#                     print(f"Error importing submodule {submodule_name}: {e}")
#                 except Exception as e:  # Catch other potential import errors
#                     print(f"Unexpected error importing {submodule_name}: {e}")
#             elif debug:
#                 print(f"Skipping directory without __init__.py: {item_path}")
#
#
# # Example usage within ok/__init__.py:
# __INIT_FILE_PATH = os.path.abspath(__file__)
# _ok_package_path = os.path.dirname(__INIT_FILE_PATH)
# _ok_package_name = __name__  # ok
#
# _blacklist = ["rotypes", "ocr", 'analytics', 'alas']  # Example blacklist
#
# _import_submodules(_ok_package_name, _ok_package_path, blacklist=_blacklist, debug=False)
#
# del _import_submodules
# del __INIT_FILE_PATH
# del _ok_package_path
# del _ok_package_name
# del _blacklist


import importlib

submodule = importlib.import_module('ok.ok')
# Import all non-private names from __init__.py
for name, obj in submodule.__dict__.items():
    if not name.startswith("_"):
        globals()[name] = obj
        # print(f"{name} loaded")
