"""Creating Windows shortcuts that start the app, as the launcher does.

The launcher writes ``<app>.lnk`` to the Start Menu (and refreshes an existing
Desktop one) after the app starts. :func:`create_shortcut` does the same from
Python, mainly for apps run without the launcher. Shortcuts are written with
Windows' own ``WScript.Shell`` COM object through PowerShell, so no extra
package is needed.
"""
import os
import subprocess

from . import _process, standalone
from ._state import get_logger, pkg

_CSIDL_PROGRAMS = 0x0002  # %APPDATA%\Microsoft\Windows\Start Menu\Programs
_CSIDL_DESKTOPDIRECTORY = 0x0010
_LINK_FLAGS_OFFSET = 0x14  # MS-SHLLINK ShellLinkHeader.LinkFlags
_RUN_AS_ADMIN_FLAG = 0x00002000  # RunAsUser: "Run as administrator"
_INVALID_FILE_NAME_CHARS = '<>:"/\\|?*'
_POWERSHELL_TIMEOUT_SECONDS = 30

# Values arrive through environment variables, so nothing needs quoting. An
# existing shortcut that already matches is left untouched; the script prints
# WRITTEN when it saved the file and UNCHANGED otherwise.
_CREATE_SHORTCUT_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$path = $env:PYAPPIFY_SHORTCUT_PATH
$icon = $env:PYAPPIFY_SHORTCUT_ICON
$expectedIcon = if ($icon) { "$icon,0" } else { ",0" }
$exists = Test-Path -LiteralPath $path
$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($path)
if ($exists -and
    $shortcut.TargetPath -eq $env:PYAPPIFY_SHORTCUT_TARGET -and
    $shortcut.Arguments -ceq [string]$env:PYAPPIFY_SHORTCUT_ARGUMENTS -and
    $shortcut.WorkingDirectory -eq $env:PYAPPIFY_SHORTCUT_WORKING_DIR -and
    $shortcut.Description -ceq $env:PYAPPIFY_SHORTCUT_NAME -and
    $shortcut.IconLocation -eq $expectedIcon) {
    'UNCHANGED'
    exit 0
}
$shortcut.TargetPath = $env:PYAPPIFY_SHORTCUT_TARGET
$shortcut.Arguments = $env:PYAPPIFY_SHORTCUT_ARGUMENTS
$shortcut.WorkingDirectory = $env:PYAPPIFY_SHORTCUT_WORKING_DIR
$shortcut.Description = $env:PYAPPIFY_SHORTCUT_NAME
$shortcut.IconLocation = $expectedIcon
$shortcut.Save()
'WRITTEN'
"""


def create_shortcut(
    name=None,
    target=None,
    arguments=None,
    working_dir=None,
    icon=None,
    run_as_admin=None,
    start_menu=True,
    desktop=True,
    directories=None,
    profile=None,
    command=None,
):
    """Create or update Windows shortcuts that start the app.

    Every argument defaults to the running app, using ``pyappify.yml`` in
    ``working_dir`` (and its ``profile``, by default the app's current one)
    when it exists, also in a development checkout:

    - ``name``: the shortcut's file and display name; the yml ``name``, else
      the working directory's folder name.
    - ``target`` and ``arguments``: built like the launcher's shortcut from
      the profile's ``main_script``: a ``.py`` script runs with the app's
      Python (``pythonw.exe`` when ``use_pythonw`` is true, else
      ``python.exe``) and anything else runs directly. Without a
      ``main_script`` the running command line is used, with ``python.exe``
      replaced by the ``pythonw.exe`` next to it so no console window opens.
      ``command`` (an argv list, the running command line by default) gives
      that fallback and the Python that runs the script. ``arguments`` may be
      a string or a list. An explicit ``target`` is used as given.
    - ``working_dir``: the current directory.
    - ``icon``: an .ico path; defaults to the yml ``icon`` (or the same path
      with an .ico extension), else the target's own icon.
    - ``run_as_admin``: the current profile's ``admin`` (or ``uac``) setting.

    Shortcuts go to the Start Menu (``start_menu``) and/or Desktop
    (``desktop``), or to ``directories`` when given; a location set to False
    is neither created nor updated. A shortcut that already matches is left
    untouched. Returns the paths of the shortcuts that were created or
    changed, so an empty list means nothing needed writing.
    """
    if os.name != "nt":
        raise OSError("Shortcuts can only be created on Windows")
    settings = _shortcut_settings(
        name, target, arguments, working_dir, icon, run_as_admin, profile, command
    )
    if directories is None:
        directories = _default_directories(start_menu, desktop)
    return _write_all(directories, settings)


def refresh_shortcuts(target=None, arguments=None, working_dir=None, profile=None, command=None):
    """Refresh the app's shortcuts the way the launcher does after starting it.

    The Start Menu shortcut is always written; the Desktop one is only updated
    when it already exists, so a shortcut the user deleted is not recreated.
    Arguments default as in :func:`create_shortcut`. Returns the paths of the
    shortcuts that were created or changed.
    """
    if os.name != "nt":
        return []
    settings = _shortcut_settings(
        None, target, arguments, working_dir, None, None, profile, command
    )
    directories = [_known_folder(_CSIDL_PROGRAMS)]
    desktop = _known_folder(_CSIDL_DESKTOPDIRECTORY)
    if os.path.isfile(os.path.join(desktop, settings["name"] + ".lnk")):
        directories.append(desktop)
    return _write_all(directories, settings)


def _shortcut_settings(name, target, arguments, working_dir, icon, run_as_admin, profile, command=None):
    working_dir = os.path.abspath(working_dir or os.getcwd())
    config = _read_app_config(working_dir)
    profile = standalone.select_profile(
        config.get("profiles"), profile if profile is not None else pkg().app_profile
    )

    if target is None:
        target, default_arguments = _app_command(
            working_dir, profile, list(command or standalone._relaunch_argv())
        )
        if arguments is None:
            arguments = default_arguments
    if not isinstance(arguments, str):
        arguments = subprocess.list2cmdline(list(arguments or []))
    name = _safe_file_name(
        name or str(config.get("name") or "") or os.path.basename(working_dir)
    )
    if icon is None:
        icon = _resolve_icon(working_dir, str(config.get("icon") or ""))
    if run_as_admin is None:
        run_as_admin = _is_truthy(profile.get("admin", profile.get("uac")))
    return {
        "name": name,
        "target": os.path.abspath(target),
        "arguments": arguments,
        "working_dir": working_dir,
        "icon": os.path.abspath(icon) if icon else "",
        "run_as_admin": bool(run_as_admin),
    }


def _write_all(directories, settings):
    written = []
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        shortcut_path = os.path.join(directory, settings["name"] + ".lnk")
        changed = _write_shortcut(
            shortcut_path,
            settings["target"],
            settings["arguments"],
            settings["working_dir"],
            settings["name"],
            settings["icon"],
            settings["run_as_admin"],
        )
        if changed:
            written.append(shortcut_path)
    return written


def windowless_python(executable):
    """``pythonw.exe`` next to a ``python.exe``, so a shortcut opens no console window.

    Other executables (and a python.exe without a pythonw.exe beside it) are
    returned unchanged.
    """
    directory, name = os.path.split(executable)
    if name.lower() == "python.exe":
        candidate = os.path.join(directory, "pythonw.exe")
        if os.path.isfile(candidate):
            return candidate
    return executable


def _app_command(working_dir, profile, command):
    """Return ``(target, arguments)`` that start the app, as the launcher's shortcut does."""
    main_script = str(profile.get("main_script") or "").strip()
    if not main_script:
        return windowless_python(command[0]), command[1:]
    python_dir = os.path.dirname(os.path.abspath(command[0]))
    script = _find_script(main_script, working_dir, python_dir)
    if not main_script.lower().endswith(".py"):
        return script, []
    python_name = "pythonw.exe" if _is_truthy(profile.get("use_pythonw")) else "python.exe"
    python = os.path.join(python_dir, python_name)
    if not os.path.isfile(python):
        python = command[0]
    return python, [script]


def _find_script(main_script, working_dir, python_dir):
    """Find ``main_script`` in the working dir, else next to Python (like the launcher)."""
    for directory in (working_dir, python_dir, os.path.join(python_dir, "Scripts")):
        candidate = os.path.join(directory, main_script)
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)
    return os.path.abspath(os.path.join(working_dir, main_script))


def _read_app_config(working_dir):
    path = os.path.join(working_dir, standalone.PYAPPIFY_YML)
    try:
        with open(path, "r", encoding="utf-8") as config_file:
            return standalone.parse_app_config(config_file.read())
    except OSError:
        return {}


def _resolve_icon(working_dir, configured):
    """Return the configured icon as an .ico inside ``working_dir``, or None.

    Like the launcher: absolute paths and paths escaping the working directory
    are ignored, and a non-.ico icon is replaced by the same path ending in .ico.
    """
    configured = configured.strip()
    if not configured or os.path.isabs(configured):
        return None
    root = os.path.realpath(working_dir)
    icon_path = os.path.realpath(os.path.join(root, configured))
    if os.path.commonpath([root, icon_path]) != root:
        return None
    if not icon_path.lower().endswith(".ico"):
        icon_path = os.path.splitext(icon_path)[0] + ".ico"
    return icon_path if os.path.isfile(icon_path) else None


def _is_truthy(value):
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "on", "1")
    return bool(value)


def _safe_file_name(name):
    cleaned = "".join("_" if char in _INVALID_FILE_NAME_CHARS else char for char in name)
    cleaned = cleaned.strip().rstrip(".")
    if not cleaned:
        raise ValueError("The shortcut name is empty")
    return cleaned


def _default_directories(start_menu, desktop):
    directories = []
    if start_menu:
        directories.append(_known_folder(_CSIDL_PROGRAMS))
    if desktop:
        directories.append(_known_folder(_CSIDL_DESKTOPDIRECTORY))
    return directories


def _known_folder(csidl):
    ctypes = _process.ctypes
    buffer = ctypes.create_unicode_buffer(32768)
    result = ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buffer)
    if result != 0:
        raise OSError("Could not resolve Windows folder {} (HRESULT {})".format(csidl, result))
    return buffer.value


def _powershell():
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    path = os.path.join(system_root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    return path if os.path.isfile(path) else "powershell"


def _write_shortcut(path, target, arguments, working_dir, name, icon, run_as_admin):
    """Create or update one shortcut; return whether the file was created or changed."""
    env = os.environ.copy()
    env.update({
        "PYAPPIFY_SHORTCUT_PATH": path,
        "PYAPPIFY_SHORTCUT_TARGET": target,
        "PYAPPIFY_SHORTCUT_ARGUMENTS": arguments,
        "PYAPPIFY_SHORTCUT_WORKING_DIR": working_dir,
        "PYAPPIFY_SHORTCUT_NAME": name,
        "PYAPPIFY_SHORTCUT_ICON": icon,
    })
    completed = subprocess.run(
        [_powershell(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-Command", _CREATE_SHORTCUT_SCRIPT],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=_POWERSHELL_TIMEOUT_SECONDS,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if completed.returncode != 0 or not os.path.isfile(path):
        raise OSError("Failed to write shortcut {}: {}".format(
            path, (completed.stderr or completed.stdout).strip()
        ))
    saved = "WRITTEN" in completed.stdout
    admin_changed = _set_run_as_admin(path, run_as_admin)
    changed = saved or admin_changed
    log = get_logger()
    if changed:
        log.info(
            "pyappify wrote shortcut %s -> %s %s (working directory: %s, icon: %s, run as admin: %s)",
            path, target, arguments, working_dir, icon or None, run_as_admin,
        )
    else:
        log.debug("pyappify shortcut %s is up to date", path)
    return changed


def _set_run_as_admin(path, run_as_admin):
    """Set or clear "Run as administrator", which WScript.Shell cannot do.

    Returns whether the flag had to change.
    """
    with open(path, "r+b") as link_file:
        link_file.seek(_LINK_FLAGS_OFFSET)
        flags = int.from_bytes(link_file.read(4), "little")
        updated = flags | _RUN_AS_ADMIN_FLAG if run_as_admin else flags & ~_RUN_AS_ADMIN_FLAG
        if updated == flags:
            return False
        link_file.seek(_LINK_FLAGS_OFFSET)
        link_file.write(updated.to_bytes(4, "little"))
        return True
