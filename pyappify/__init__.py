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
pyappify_executable = os.environ.get("PYAPPIFY_EXECUTABLE")
app_json_path = configure_app_json(os.environ.get("PYAPPIFY_APP_JSON_PATH"))

pyappify_upgradeable = os.environ.get("PYAPPIFY_UPGRADEABLE") == '1'
logger = None
_console_logger = None

try:
    pid = int(os.environ.get("PYAPPIFY_PID"))
except (ValueError, TypeError):
    pid = None

import sys

try:
    import ctypes
except ImportError:
    ctypes = None


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


def kill_pyappify(timeout=30):
    if pid:
        log = _get_logger()
        log.info(f"Attempting to terminate process with PID: {pid}")
        try:
            os.kill(pid, signal.SIGTERM)
            if not _wait_for_process_exit(pid, timeout):
                log.warning(f"Timed out waiting for process with PID {pid} to exit.")
                return False
            log.info(f'_wait_for_process_exit success {pid}')
            return True
        except Exception as e:
            log.error(f"Failed to terminate process with PID {pid}: {e}")
            return False
    return False


def kill_pyappify_exe(timeout=30):
    return kill_pyappify(timeout)


def _wait_for_process_exit(process_pid, timeout=30):
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
                result = ctypes.windll.kernel32.WaitForSingleObject(
                    handle, int(timeout * 1000)
                )
                if result == wait_failed:
                    return False
                return result != wait_timeout
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(process_pid, 0)
        except OSError:
            return True
        time.sleep(0.1)
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
    if _is_process_running(pid):
        log.info(f"PyAppify is already running with PID: {pid}")
        bring_window_to_front_by_pid(pid)
        return pid

    if not pyappify_executable:
        log.error("PYAPPIFY_EXECUTABLE is not configured.")
        return None

    command = [pyappify_executable]
    if args:
        if isinstance(args, str):
            command.append(args)
        else:
            command.extend(args)

    try:
        process = subprocess.Popen(
            command,
            cwd=cwd or os.path.dirname(pyappify_executable) or None,
            env=env,
        )
        pid = process.pid
        return pid
    except Exception as e:
        log.error(f"Failed to start PyAppify executable {pyappify_executable}: {e}")
        return None


def _replace_executable(source_path, target_path, timeout=30):
    deadline = time.monotonic() + timeout
    last_error = None
    while True:
        try:
            shutil.move(source_path, target_path)
            return
        except PermissionError as e:
            last_error = e
            if time.monotonic() >= deadline:
                raise last_error
            time.sleep(0.25)


def hide_pyappify():
    if pid:
        log = _get_logger()
        log.info(f"Attempting to minimize window for process with PID: {pid}")
        try:
            minimize_window_by_pid(pid)
        except Exception as e:
            log.error(f"Failed to minimize window for process with PID {pid}: {e}")
            pass

def upgrade(to_version, executable_sha256, executable_zip_urls, stop_event=None):
    log = _get_logger()
    if not pyappify_upgradeable or not is_greater_version(to_version, pyappify_version):
        log.info(f"pyappify no need to upgrade {pyappify_upgradeable} {to_version} {executable_sha256} {executable_zip_urls}")
        return
    log.info(
        f"pyappify start to upgrade {pyappify_upgradeable} {to_version} {executable_sha256} {executable_zip_urls}")
    def _do_upgrade():
        tmp_dir = os.path.join(os.getcwd(), "pyappify_tmp")
        try:
            os.makedirs(tmp_dir, exist_ok=True)
            downloaded_zip_path = None
            for url in executable_zip_urls:
                try:
                    log.info(
                        f"pyappify start to download {url}")
                    local_zip_path = os.path.join(tmp_dir, os.path.basename(url))
                    with urllib.request.urlopen(url) as response, open(local_zip_path, 'wb') as out_file:
                        while True:
                            if stop_event and stop_event.is_set():
                                log.info("pyappify Upgrade download cancelled by stop event.")
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
                zip_ref.extractall(tmp_dir)

            new_executable_name = os.path.basename(pyappify_executable)
            found_executable_path = None
            for root, _, files in os.walk(tmp_dir):
                if new_executable_name in files:
                    found_executable_path = os.path.join(root, new_executable_name)
                    break

            if not found_executable_path:
                log.error("pyappify Executable not found in zip.")
                return

            sha256_hash = hashlib.sha256()
            with open(found_executable_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)

            if executable_sha256 and sha256_hash.hexdigest() != executable_sha256:
                log.error("pyappify SHA256 checksum mismatch.")
                return

            kill_pyappify()
            _replace_executable(found_executable_path, pyappify_executable)
            log.info(f"pyappify Upgrade success")
        except Exception as e:
            log.error(f"pyappify Upgrade failed: {e}")
        finally:
            if os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir)

    thread = threading.Thread(target=_do_upgrade)
    thread.daemon = True
    thread.start()


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
