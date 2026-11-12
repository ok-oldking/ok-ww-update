# pyappify/__init__.py
"""Python API for apps run by the PyAppify launcher.

Runtime state below is read from the environment the launcher sets. It stays
on the package so apps can override it (``pyappify.logger = my_logger``);
the submodules read it from here at call time.
"""
import json
import os

from .app_config import (
    UPDATE_METHOD_AUTO,
    UPDATE_METHOD_AUTO_PRE_RELEASE,
    UPDATE_METHOD_MANUAL,
    add_app_config_listener,
    configure_app_json,
    get_app_config,
    get_app_json_path,
    get_auto_start,
    get_update_method,
    remove_app_config_listener,
    set_auto_start,
    set_update_method,
    start_app_config_watcher,
    stop_app_config_watcher,
    update_app_config,
)
from ._process import bring_window_to_front_by_pid, minimize_window_by_pid
from .launcher import (
    find_pyappify_executable,
    hide_pyappify,
    kill_pyappify,
    kill_pyappify_exe,
    show_pyappify,
)
from .self_upgrade import upgrade
from .shortcut import create_shortcut, refresh_shortcuts
from .updates import PIP_INDEX_URLS, get_pip_index_config, set_pip_index_url
from .updates import get_version_list, get_versions, is_local_checkout, update_to_version
from .updater_ui import can_show_window as can_show_updater, open_updater
from .versions import calculate_update_notes, entry_notes, is_greater_version

app_ref = None
app_version = os.environ.get("PYAPPIFY_APP_VERSION")
app_starting_version = os.environ.get("PYAPPIFY_APP_STARTING_VERSION") or app_version
update_note = os.environ.get("PYAPPIFY_UPDATE_NOTE")
app_profile = os.environ.get("PYAPPIFY_APP_PROFILE")
app_locale = os.environ.get("PYAPPIFY_LOCALE") or "en"
pyappify_version = os.environ.get("PYAPPIFY_VERSION")
app_json_path = configure_app_json(os.environ.get("PYAPPIFY_APP_JSON_PATH"))

pyappify_upgradeable = os.environ.get("PYAPPIFY_UPGRADEABLE") == '1'
logger = None

try:
    pid = int(os.environ.get("PYAPPIFY_PID"))
except (ValueError, TypeError):
    pid = None

pyappify_executable = find_pyappify_executable()

if app_version is None and not pyappify_version and not pyappify_executable:
    # Running from a git clone without the launcher: use the version tag at HEAD.
    from .standalone import detect_app_checkout

    app_version, app_ref = detect_app_checkout()
    app_starting_version = app_starting_version or app_version


def is_app_updated():
    return is_greater_version(app_version, app_starting_version)


def is_app_downgraded():
    return is_greater_version(app_starting_version, app_version)


def is_updated():
    return is_app_updated()


def is_downgrade():
    return is_app_downgraded()


def get_update_notes():
    if not update_note:
        return []
    try:
        notes = json.loads(update_note)
    except (TypeError, ValueError):
        return []
    if isinstance(notes, list):
        return [str(note) for note in notes]
    return []


def get_update_note():
    return get_update_notes()


def get_locale():
    return app_locale
