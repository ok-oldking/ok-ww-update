# pyappify/__init__.py
import os
import signal
import hashlib
import json
import logging
import shutil
import subprocess
import urllib.request
import zipfile
import threading
import time
import tempfile
import uuid
import sys
from pathlib import Path

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

app_version = os.environ.get("PYAPPIFY_APP_VERSION")
app_starting_version = os.environ.get("PYAPPIFY_APP_STARTING_VERSION") or app_version
update_note = os.environ.get("PYAPPIFY_UPDATE_NOTE")
app_profile = os.environ.get("PYAPPIFY_APP_PROFILE")
app_locale = os.environ.get("PYAPPIFY_LOCALE") or "en"
pyappify_version = os.environ.get("PYAPPIFY_VERSION")
app_json_path = configure_app_json(os.environ.get("PYAPPIFY_APP_JSON_PATH"))

pyappify_upgradeable = os.environ.get("PYAPPIFY_UPGRADEABLE") == '1'
logger = None
_console_logger = None
_DOWNLOAD_IO_TIMEOUT_SECONDS = 2

try:
    pid = int(os.environ.get("PYAPPIFY_PID"))
except (ValueError, TypeError):
    pid = None

try:
    import ctypes
except ImportError:
    ctypes = None


def find_pyappify_executable(start_dir=None, environ=None):
    """Find the configured launcher or an app launcher above ``working``."""
    environ = os.environ if environ is None else environ
    configured = environ.get("PYAPPIFY_EXECUTABLE")
    if configured:
        configured_path = Path(configured).expanduser()
        if configured_path.is_file():
            return str(configured_path.resolve())
        return None

    current = Path(start_dir or os.getcwd()).expanduser()
    if current.is_file():
        current = current.parent
    try:
        current = current.resolve()
    except OSError:
        current = current.absolute()

    working_directory = next(
        (
            directory
            for directory in (current,) + tuple(current.parents)
            if directory.name.casefold() == "working" and directory.parent.name
        ),
        None,
    )
    if working_directory is None:
        return None

    app_name = working_directory.parent.name
    apps_directory = working_directory.parent.parent
    data_directory = apps_directory.parent
    if apps_directory.name.casefold() != "apps" or data_directory.name.casefold() != "data":
        return None

    app_root = data_directory.parent
    executable_name = "{}.exe".format(app_name)
    search_directories = []
    directory = working_directory
    while True:
        search_directories.append(directory)
        if directory == app_root:
            break
        directory = directory.parent

    for directory in search_directories:
        candidate = directory / executable_name
        if candidate.is_file():
            return str(candidate.resolve())
    return None


pyappify_executable = find_pyappify_executable()


def _get_logger():
    global _console_logger

    if logger is not None:
        return logger
    if _console_logger is None:
        _console_logger = logging.getLogger("pyappify")
        if not _console_logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
            _console_logger.addHandler(handler)
        _console_logger.setLevel(logging.INFO)
        _console_logger.propagate = False
    return _console_logger


def _find_visible_window_by_pid(process_pid):
    if not ctypes or sys.platform != "win32":
        return None

    found_hwnd = []
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def enum_windows_callback(hwnd, lParam):
        owner_pid = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_pid))
        if owner_pid.value == process_pid and ctypes.windll.user32.IsWindowVisible(hwnd):
            found_hwnd.append(hwnd)
            return False
        return True

    ctypes.windll.user32.EnumWindows(EnumWindowsProc(enum_windows_callback), 0)

    return found_hwnd[0] if found_hwnd else None


def minimize_window_by_pid(pid):
    hwnd = _find_visible_window_by_pid(pid)
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, 6)
        return True

    return False


def bring_window_to_front_by_pid(pid):
    hwnd = _find_visible_window_by_pid(pid)
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, 9)
        return bool(ctypes.windll.user32.SetForegroundWindow(hwnd))

    return False


def kill_pyappify(timeout=30, exit_event=None):
    if pid:
        log = _get_logger()
        log.info(f"Attempting to terminate process with PID: {pid}")
        try:
            os.kill(pid, signal.SIGTERM)
            if not _wait_for_process_exit(pid, timeout, exit_event=exit_event):
                log.warning(f"Timed out waiting for process with PID {pid} to exit.")
                return False
            log.info(f'_wait_for_process_exit success {pid}')
            return True
        except Exception as e:
            log.error(f"Failed to terminate process with PID {pid}: {e}")
            return False
    return False


def kill_pyappify_exe(timeout=30, exit_event=None):
    return kill_pyappify(timeout, exit_event=exit_event)


def _wait_for_process_exit(process_pid, timeout=30, exit_event=None):
    if sys.platform == "win32" and ctypes:
        synchronize = 0x00100000
        wait_timeout = 0x00000102
        wait_failed = 0xFFFFFFFF
        ctypes.windll.kernel32.OpenProcess.argtypes = (
            ctypes.c_uint,
            ctypes.c_bool,
            ctypes.c_ulong,
        )
        ctypes.windll.kernel32.OpenProcess.restype = ctypes.c_void_p
        ctypes.windll.kernel32.WaitForSingleObject.argtypes = (
            ctypes.c_void_p,
            ctypes.c_uint,
        )
        ctypes.windll.kernel32.WaitForSingleObject.restype = ctypes.c_uint
        ctypes.windll.kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        ctypes.windll.kernel32.CloseHandle.restype = ctypes.c_bool
        handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, process_pid)
        if handle:
            try:
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    if _exit_requested(exit_event):
                        return False
                    remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
                    result = ctypes.windll.kernel32.WaitForSingleObject(
                        handle, min(100, remaining_ms)
                    )
                    if result == wait_failed:
                        return False
                    if result != wait_timeout:
                        return True
                return False
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _exit_requested(exit_event):
            return False
        try:
            os.kill(process_pid, 0)
        except OSError:
            return True
        if _wait_for_exit(exit_event, 0.1):
            return False
    return False


def _is_process_running(process_pid):
    if not process_pid:
        return False

    if sys.platform == "win32" and ctypes:
        synchronize = 0x00100000
        wait_timeout = 0x00000102
        ctypes.windll.kernel32.OpenProcess.argtypes = (
            ctypes.c_uint,
            ctypes.c_bool,
            ctypes.c_ulong,
        )
        ctypes.windll.kernel32.OpenProcess.restype = ctypes.c_void_p
        ctypes.windll.kernel32.WaitForSingleObject.argtypes = (
            ctypes.c_void_p,
            ctypes.c_uint,
        )
        ctypes.windll.kernel32.WaitForSingleObject.restype = ctypes.c_uint
        ctypes.windll.kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        ctypes.windll.kernel32.CloseHandle.restype = ctypes.c_bool
        handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, process_pid)
        if not handle:
            return False
        try:
            return ctypes.windll.kernel32.WaitForSingleObject(handle, 0) == wait_timeout
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)

    try:
        os.kill(process_pid, 0)
    except OSError:
        return False
    return True


def show_pyappify(args=None, cwd=None, env=None):
    global pid

    log = _get_logger()
    already_running = _is_process_running(pid)
    if already_running and not args:
        log.info(f"PyAppify is already running with PID: {pid}")
        bring_window_to_front_by_pid(pid)
        return pid

    executable = pyappify_executable or find_pyappify_executable()
    if not executable:
        log.error("PyAppify executable was not found.")
        return None

    command = [executable]
    if args:
        if isinstance(args, str):
            command.append(args)
        else:
            command.extend(args)

    try:
        process = subprocess.Popen(
            command,
            cwd=cwd or os.path.dirname(executable) or None,
            env=env,
        )
        if not already_running:
            pid = process.pid
        return pid
    except Exception as e:
        log.error(f"Failed to start PyAppify executable {executable}: {e}")
        return None


def _require_pyappify_executable():
    global pyappify_executable

    if pyappify_executable and os.path.isfile(pyappify_executable):
        return os.path.abspath(pyappify_executable)
    pyappify_executable = find_pyappify_executable()
    if not pyappify_executable:
        raise FileNotFoundError(
            "PyAppify executable was not found. Set PYAPPIFY_EXECUTABLE to an "
            "existing executable or place <app_name>.exe between the working directory "
            "and the app root."
        )
    return pyappify_executable


def _exit_requested(*events):
    return any(event is not None and event.is_set() for event in events)


def _wait_for_exit(exit_event, timeout):
    if exit_event is not None:
        return exit_event.wait(timeout)
    time.sleep(timeout)
    return False


def _raise_if_exit_requested(exit_event):
    if _exit_requested(exit_event):
        raise InterruptedError("PyAppify operation cancelled because exit_event was set")


def _terminate_process(process):
    try:
        if process.poll() is None:
            process.terminate()
    except (AttributeError, OSError):
        pass


def _run_launcher_api(arguments, timeout=300, exit_event=None):
    _raise_if_exit_requested(exit_event)
    executable = _require_pyappify_executable()
    response_path = os.path.join(
        tempfile.gettempdir(),
        "pyappify-response-{}-{}.json".format(os.getpid(), uuid.uuid4().hex),
    )
    command = list(arguments) + ["--response-file", response_path]
    try:
        process = subprocess.Popen(
            [executable] + command,
            cwd=os.path.dirname(executable) or None,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as error:
        raise RuntimeError(
            "Failed to execute PyAppify at '{}': {}".format(executable, error)
        )

    deadline = time.monotonic() + timeout
    cancelled = False
    try:
        while time.monotonic() < deadline:
            if _exit_requested(exit_event):
                cancelled = True
                _terminate_process(process)
                break
            try:
                with open(response_path, "r", encoding="utf-8") as response_file:
                    response = json.load(response_file)
                if isinstance(response, dict) and response.get("error"):
                    raise RuntimeError(response["error"])
                return response
            except FileNotFoundError:
                pass
            except json.JSONDecodeError:
                # The running launcher may still be completing the response write.
                pass
            if _wait_for_exit(exit_event, 0.05):
                cancelled = True
                _terminate_process(process)
                break
    finally:
        try:
            os.remove(response_path)
        except FileNotFoundError:
            pass

    if cancelled:
        raise InterruptedError("PyAppify operation cancelled because exit_event was set")
    raise TimeoutError("Timed out waiting for a response from PyAppify")


def get_version_list(
    number_versions=10, release_only=True, timeout=120, exit_event=None
):
    """Return version details, cancelling with InterruptedError on exit_event."""
    if isinstance(number_versions, bool) or not isinstance(number_versions, int):
        raise TypeError("number_versions must be an integer")
    if number_versions <= 0:
        raise ValueError("number_versions must be greater than zero")
    if not isinstance(release_only, bool):
        raise TypeError("release_only must be a boolean")

    if not _is_supported_pyappify_version(pyappify_version):
        raise RuntimeError(
            "PyAppify does not support checking for updates for "
            f"pyappify_version: {pyappify_version}"
        )

    if "PYAPPIFY_PYTHON_TEST" in os.environ:
        if _wait_for_exit(exit_event, 5):
            _raise_if_exit_requested(exit_event)
        return _get_mock_version_list(number_versions)

    response = _run_launcher_api(
        [
            "--get-version-list",
            "--number-versions",
            str(number_versions),
            "--release-only",
            str(release_only).lower(),
        ],
        timeout=timeout,
        exit_event=exit_event,
    )
    if not isinstance(response, list):
        raise RuntimeError("PyAppify returned an invalid version-list response")
    return response


def _is_supported_pyappify_version(version):
    """Return whether a PyAppify version is valid and supports version checks."""
    if not isinstance(version, str) or not version:
        return False

    normalized = version[1:] if version.startswith("v") else version
    parts = normalized.split(".")
    if not parts or any(not part.isdigit() for part in parts):
        return False

    return tuple(int(part) for part in parts) >= (1, 2, 2)


def get_versions(number_versions=10, release_only=True, timeout=120, exit_event=None):
    """Alias for get_version_list."""
    return get_version_list(number_versions, release_only, timeout, exit_event)


def calculate_update_notes(update_notes, current_version, target_version):
    """Return descending notes without including versions newer than the target."""
    if not isinstance(update_notes, list):
        raise TypeError("update_notes must be a list")

    versions = [
        item for item in update_notes
        if isinstance(item, dict) and item.get("version")
    ]

    def normalize(version):
        return str(version or "").lstrip("v")

    def find_index(version):
        normalized = normalize(version)
        return next(
            (index for index, item in enumerate(versions)
             if normalize(item["version"]) == normalized),
            None,
        )

    target_index = find_index(target_version)
    if target_index is None:
        return []

    current_index = find_index(current_version)
    if current_index is None:
        selected_versions = versions[target_index:]
    else:
        first = min(current_index, target_index)
        last = max(current_index, target_index)
        selected_versions = versions[first:last + 1]

    notes = []
    for item in selected_versions:
        raw_notes = item.get("update_note") or []
        notes.extend(raw_notes if isinstance(raw_notes, list) else [raw_notes])
    return [str(note) for note in notes]


def update_to_version(version, timeout=300, exit_event=None):
    """Update the app, cancelling with InterruptedError on exit_event."""
    if not isinstance(version, str) or not version.strip():
        raise ValueError("version must be a non-empty string")
    if "PYAPPIFY_PYTHON_TEST" in os.environ:
        _raise_if_exit_requested(exit_event)
        return {"updated": True, "version": version, "mocked": True}
    response = _run_launcher_api(
        ["--update-to-version", version],
        timeout=timeout,
        exit_event=exit_event,
    )
    if not isinstance(response, dict) or not response.get("updated"):
        raise RuntimeError("PyAppify returned an invalid update response")
    return response


def _get_mock_version_list(number_versions):
    """Return deterministic launcher data for UI and integration tests."""
    current = app_version or "v1.0.0"
    prefix = "v" if current.startswith("v") else ""
    try:
        parts = [int(part) for part in current.lstrip("v").split(".")]
    except (TypeError, ValueError):
        parts = [1, 0, 0]
        prefix = "v"
    parts = (parts + [0, 0, 0])[:3]

    def previous_parts(version_parts):
        major, minor, patch = version_parts
        if patch > 0:
            return [major, minor, patch - 1]
        if minor > 0:
            return [major, minor - 1, 9]
        if major > 0:
            return [major - 1, 9, 9]
        return None

    version_parts = [[100, 1, 1], parts[:2] + [parts[2] + 2], parts[:2] + [parts[2] + 1], parts]
    previous = previous_parts(parts)
    while len(version_parts) < number_versions:
        if previous is not None:
            version_parts.append(previous)
            previous = previous_parts(previous)
        else:
            break

    versions = []
    for item_parts in version_parts:
        item_prefix = "v" if item_parts == [100, 1, 1] else prefix
        version = item_prefix + ".".join(str(part) for part in item_parts)
        previous_item = previous_parts(item_parts)
        previous = item_prefix + ".".join(str(part) for part in previous_item) if previous_item else version
        versions.append({
            "version": version,
            "previous_version": previous,
            "update_note": [
                f"Mock update note for {version}",
                f"Changes since {previous}",
            ],
        })
    return versions[:number_versions]


def _replace_executable(source_path, target_path, timeout=30, exit_event=None):
    deadline = time.monotonic() + timeout
    last_error = None
    while True:
        _raise_if_exit_requested(exit_event)
        try:
            shutil.move(source_path, target_path)
            return
        except PermissionError as e:
            last_error = e
            if time.monotonic() >= deadline:
                raise last_error
            if _wait_for_exit(exit_event, 0.25):
                _raise_if_exit_requested(exit_event)


def hide_pyappify():
    if pid:
        log = _get_logger()
        log.info(f"Attempting to minimize window for process with PID: {pid}")
        try:
            minimize_window_by_pid(pid)
        except Exception as e:
            log.error(f"Failed to minimize window for process with PID {pid}: {e}")
            pass

def upgrade(
    to_version,
    executable_sha256,
    executable_zip_urls,
    stop_event=None,
    exit_event=None,
):
    log = _get_logger()
    if not pyappify_upgradeable or not is_greater_version(to_version, pyappify_version):
        log.info(f"pyappify no need to upgrade {pyappify_upgradeable} {to_version} {executable_sha256} {executable_zip_urls}")
        return
    log.info(
        f"pyappify start to upgrade {pyappify_upgradeable} {to_version} {executable_sha256} {executable_zip_urls}")
    def _do_upgrade():
        tmp_dir = os.path.join(os.getcwd(), "pyappify_tmp")
        try:
            if _exit_requested(stop_event, exit_event):
                return
            os.makedirs(tmp_dir, exist_ok=True)
            downloaded_zip_path = None
            for url in executable_zip_urls:
                if _exit_requested(stop_event, exit_event):
                    return
                try:
                    log.info(
                        f"pyappify start to download {url}")
                    local_zip_path = os.path.join(tmp_dir, os.path.basename(url))
                    with urllib.request.urlopen(
                        url, timeout=_DOWNLOAD_IO_TIMEOUT_SECONDS
                    ) as response, open(local_zip_path, 'wb') as out_file:
                        while True:
                            if _exit_requested(stop_event, exit_event):
                                log.info("pyappify Upgrade download cancelled.")
                                return
                            chunk = response.read(8192)
                            if not chunk:
                                break
                            out_file.write(chunk)
                    downloaded_zip_path = local_zip_path
                    log.info(
                        f"pyappify download success {url}")
                    break
                except Exception as e:
                    log.warning(f"pyappify Failed to download from {url}: {e}")
                    continue

            if not downloaded_zip_path:
                log.error("pyappify Failed to download upgrade.")
                return

            with zipfile.ZipFile(downloaded_zip_path, 'r') as zip_ref:
                for member in zip_ref.infolist():
                    if _exit_requested(stop_event, exit_event):
                        return
                    zip_ref.extract(member, tmp_dir)

            new_executable_name = os.path.basename(pyappify_executable)
            found_executable_path = None
            for root, _, files in os.walk(tmp_dir):
                if _exit_requested(stop_event, exit_event):
                    return
                if new_executable_name in files:
                    found_executable_path = os.path.join(root, new_executable_name)
                    break

            if not found_executable_path:
                log.error("pyappify Executable not found in zip.")
                return

            sha256_hash = hashlib.sha256()
            with open(found_executable_path, "rb") as f:
                while True:
                    if _exit_requested(stop_event, exit_event):
                        return
                    byte_block = f.read(4096)
                    if not byte_block:
                        break
                    sha256_hash.update(byte_block)

            if executable_sha256 and sha256_hash.hexdigest() != executable_sha256:
                log.error("pyappify SHA256 checksum mismatch.")
                return

            if _exit_requested(stop_event, exit_event):
                return
            kill_pyappify(exit_event=exit_event or stop_event)
            _replace_executable(
                found_executable_path,
                pyappify_executable,
                exit_event=exit_event or stop_event,
            )
            log.info(f"pyappify Upgrade success")
        except Exception as e:
            log.error(f"pyappify Upgrade failed: {e}")
        finally:
            if os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir)

    thread = threading.Thread(target=_do_upgrade)
    thread.daemon = True
    thread.start()
    return thread


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


def is_greater_version(version1, version2):
    """
    Compares two semantic version strings.

    Args:
        version1 (str): The first version string.
        version2 (str): The second version string.

    Returns:
        bool: True if version1 is strictly greater than version2,
              False otherwise or if parsing fails.
    """
    try:
        version1 = version1.lstrip('v')
        version2 = version2.lstrip('v')
        v1_parts = [int(p) for p in version1.split('.')]
        v2_parts = [int(p) for p in version2.split('.')]
        return v1_parts > v2_parts
    except (ValueError, AttributeError):
        return False
