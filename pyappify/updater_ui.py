"""A Tk window for standalone updates: versions, patch notes, pip mirror, progress.

Two modes, both run in their own process so Tk never meets the app's own UI
toolkit:

- ``python -m pyappify.updater_ui [--repo PATH] [--session FILE]`` opens the
  update manager: pick a version (releases, or with "All" also pre-releases,
  branches and pull requests), read its patch notes, choose the pip mirror
  used for dependency installs, then update with live progress and logs.
  :func:`open_updater` starts it from a running app, which it then closes and
  restarts on the chosen version.
- ``python -m pyappify.updater_ui --job FILE`` only shows the progress of an
  update job written by :func:`pyappify.update_to_version`; it replaces the
  console window of :mod:`pyappify.standalone_updater` when Tk is available.

Only the standard library is used. Pythons without Tk (the embeddable
Windows zip, some Linux packages) fall back to the console updater; set
``PYAPPIFY_UPDATER_UI=console`` to always use it.
"""
import argparse
import importlib.util
import json
import os
import subprocess
import sys

from . import standalone

SESSION_FILE_NAME = "updater-session.json"
PREFERENCES_FILE_NAME = "updater-ui.json"
UI_ENV = "PYAPPIFY_UPDATER_UI"
# Seconds the app gets to exit by itself after the user starts an update in
# the window, before the updater stops it.
APP_EXIT_TIMEOUT_SECONDS = 3


def can_show_window(environ=None):
    """Return whether this Python can open the Tk updater window."""
    environ = os.environ if environ is None else environ
    choice = (environ.get(UI_ENV) or "").strip().lower()
    if choice == "console":
        return False
    try:
        if importlib.util.find_spec("_tkinter") is None:
            return False
    except (ImportError, ValueError):
        return False
    if choice == "tk":
        return True
    if os.name == "nt" or sys.platform == "darwin":
        return True
    return bool(environ.get("DISPLAY") or environ.get("WAYLAND_DISPLAY"))


def open_updater(app_version=None, app_profile=None, exit_timeout=APP_EXIT_TIMEOUT_SECONDS):
    """Open the update manager window for this app; return its process.

    The window lists versions and applies the chosen one: it closes this app
    (after ``exit_timeout`` seconds), updates it and starts it again. Only for
    apps without the PyAppify launcher, which has its own update UI.
    """
    from ._state import pkg
    from .updates import uses_launcher

    if uses_launcher():
        raise RuntimeError("The PyAppify launcher has its own update window")
    if not can_show_window():
        raise RuntimeError("This Python has no Tk, so the update window cannot open")
    state = pkg()
    repo_path = standalone.find_repo_path()
    session = {
        "repo_path": repo_path,
        "app_version": app_version or state.app_version,
        "app_profile": app_profile or state.app_profile,
        "pid": os.getpid(),
        "exit_timeout": exit_timeout,
        "relaunch": standalone.relaunch_info(),
    }
    directory = standalone.state_dir(repo_path)
    os.makedirs(directory, exist_ok=True)
    session_path = os.path.join(directory, SESSION_FILE_NAME)
    with open(session_path, "w", encoding="utf-8") as session_file:
        json.dump(session, session_file, indent=2, ensure_ascii=False)
    return _spawn([
        standalone._gui_python(), "-m", "pyappify.updater_ui", "--session", session_path
    ], cwd=directory)


def _spawn(command, cwd):
    package_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        path for path in (package_parent, env.get("PYTHONPATH")) if path
    )
    env["PYTHONIOENCODING"] = "utf-8"
    kwargs = {"cwd": cwd, "env": env, "close_fds": True}
    if os.name == "nt":
        gui = os.path.basename(command[0]).lower() == "pythonw.exe"
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | (
            subprocess.DETACHED_PROCESS if gui else subprocess.CREATE_NO_WINDOW
        )
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(command, **kwargs)


# --- preferences --------------------------------------------------------------


def _preferences_path():
    base = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME") or os.path.join(
        os.path.expanduser("~"), ".config"
    )
    return os.path.join(base, "pyappify", PREFERENCES_FILE_NAME)


def load_preferences():
    try:
        with open(_preferences_path(), "r", encoding="utf-8") as source:
            document = json.load(source)
        return document if isinstance(document, dict) else {}
    except (OSError, ValueError):
        return {}


def save_preferences(preferences):
    path = _preferences_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as target:
            json.dump(preferences, target, indent=2)
    except OSError:
        pass


# --- command line -------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m pyappify.updater_ui")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--job", help="show the progress of this update-job.json")
    group.add_argument("--session", help="manage updates for the app described here")
    parser.add_argument("--repo", help="the app's repository (default: found from here)")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    if args.job:
        return _run_job_window(os.path.abspath(args.job))

    session = {}
    if args.session:
        with open(args.session, "r", encoding="utf-8") as source:
            session = json.load(source)
        _remove(args.session)
    if args.repo:
        session["repo_path"] = os.path.abspath(args.repo)
    from . import _tk_updater

    return _tk_updater.run_manager(session)


def _run_job_window(job_path):
    from . import standalone_updater

    try:
        from . import _tk_updater

        return _tk_updater.run_job_window(job_path)
    except _tk_unavailable_errors():
        # No usable display after all: apply the update without a window.
        return standalone_updater.main([job_path])


def _tk_unavailable_errors():
    try:
        import tkinter

        return (ImportError, tkinter.TclError)
    except ImportError:
        return (ImportError,)


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


if __name__ == "__main__":
    sys.exit(main())
