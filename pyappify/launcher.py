"""Talking to and controlling the PyAppify launcher executable."""
import json
import os
import signal
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from . import _process
from ._state import get_logger, pkg


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


def _require_pyappify_executable():
    state = pkg()
    if state.pyappify_executable and os.path.isfile(state.pyappify_executable):
        return os.path.abspath(state.pyappify_executable)
    state.pyappify_executable = find_pyappify_executable()
    if not state.pyappify_executable:
        raise FileNotFoundError(
            "PyAppify executable was not found. Set PYAPPIFY_EXECUTABLE to an "
            "existing executable or place <app_name>.exe between the working directory "
            "and the app root."
        )
    return state.pyappify_executable


def kill_pyappify(timeout=30, exit_event=None):
    pid = pkg().pid
    if pid:
        log = get_logger()
        log.info(f"Attempting to terminate process with PID: {pid}")
        try:
            os.kill(pid, signal.SIGTERM)
            if not _process._wait_for_process_exit(pid, timeout, exit_event=exit_event):
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


def show_pyappify(args=None, cwd=None, env=None):
    state = pkg()
    log = get_logger()
    already_running = _process._is_process_running(state.pid)
    if already_running and not args:
        log.info(f"PyAppify is already running with PID: {state.pid}")
        _process.bring_window_to_front_by_pid(state.pid)
        return state.pid

    executable = state.pyappify_executable or find_pyappify_executable()
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
            state.pid = process.pid
        return state.pid
    except Exception as e:
        log.error(f"Failed to start PyAppify executable {executable}: {e}")
        return None


def hide_pyappify():
    pid = pkg().pid
    if pid:
        log = get_logger()
        log.info(f"Attempting to minimize window for process with PID: {pid}")
        try:
            _process.minimize_window_by_pid(pid)
        except Exception as e:
            log.error(f"Failed to minimize window for process with PID {pid}: {e}")


def _run_launcher_api(arguments, timeout=300, exit_event=None):
    """Run a launcher API command and return its JSON response."""
    _process._raise_if_exit_requested(exit_event)
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
            if _process._exit_requested(exit_event):
                cancelled = True
                _process._terminate_process(process)
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
            if _process._wait_for_exit(exit_event, 0.05):
                cancelled = True
                _process._terminate_process(process)
                break
    finally:
        try:
            os.remove(response_path)
        except FileNotFoundError:
            pass

    if cancelled:
        raise InterruptedError("PyAppify operation cancelled because exit_event was set")
    raise TimeoutError("Timed out waiting for a response from PyAppify")
