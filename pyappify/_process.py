"""Process, window and cancellation helpers shared by the other modules."""
import os
import sys
import time

try:
    import ctypes
except ImportError:
    ctypes = None

_SYNCHRONIZE = 0x00100000
_WAIT_TIMEOUT = 0x00000102
_WAIT_FAILED = 0xFFFFFFFF
_SW_MINIMIZE = 6
_SW_RESTORE = 9


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


def _kernel32():
    """Return kernel32 with the signatures used here, or None off Windows."""
    if sys.platform != "win32" or not ctypes:
        return None
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.argtypes = (ctypes.c_uint, ctypes.c_bool, ctypes.c_ulong)
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint)
    kernel32.WaitForSingleObject.restype = ctypes.c_uint
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    kernel32.CloseHandle.restype = ctypes.c_bool
    return kernel32


def _wait_for_process_exit(process_pid, timeout=30, exit_event=None):
    kernel32 = _kernel32()
    handle = kernel32.OpenProcess(_SYNCHRONIZE, False, process_pid) if kernel32 else None
    if handle:
        try:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if _exit_requested(exit_event):
                    return False
                remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
                result = kernel32.WaitForSingleObject(handle, min(100, remaining_ms))
                if result == _WAIT_FAILED:
                    return False
                if result != _WAIT_TIMEOUT:
                    return True
            return False
        finally:
            kernel32.CloseHandle(handle)

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

    kernel32 = _kernel32()
    if kernel32:
        handle = kernel32.OpenProcess(_SYNCHRONIZE, False, process_pid)
        if not handle:
            return False
        try:
            return kernel32.WaitForSingleObject(handle, 0) == _WAIT_TIMEOUT
        finally:
            kernel32.CloseHandle(handle)

    try:
        os.kill(process_pid, 0)
    except OSError:
        return False
    return True


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
        ctypes.windll.user32.ShowWindow(hwnd, _SW_MINIMIZE)
        return True

    return False


def bring_window_to_front_by_pid(pid):
    hwnd = _find_visible_window_by_pid(pid)
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, _SW_RESTORE)
        return bool(ctypes.windll.user32.SetForegroundWindow(hwnd))

    return False
