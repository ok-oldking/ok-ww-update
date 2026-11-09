"""Replacing the PyAppify launcher executable with a newer release."""
import hashlib
import os
import shutil
import threading
import time
import urllib.request
import zipfile

from . import _process, launcher
from ._state import get_logger, pkg
from .versions import is_greater_version

_DOWNLOAD_IO_TIMEOUT_SECONDS = 2
_TMP_DIR_NAME = "pyappify_tmp"


class _Cancelled(Exception):
    """Raised inside the upgrade worker when stop_event or exit_event is set."""


def upgrade(
    to_version,
    executable_sha256,
    executable_zip_urls,
    stop_event=None,
    exit_event=None,
):
    state = pkg()
    log = get_logger()
    if not state.pyappify_upgradeable or not is_greater_version(to_version, state.pyappify_version):
        log.info(f"pyappify no need to upgrade {state.pyappify_upgradeable} {to_version} {executable_sha256} {executable_zip_urls}")
        return
    log.info(
        f"pyappify start to upgrade {state.pyappify_upgradeable} {to_version} {executable_sha256} {executable_zip_urls}")

    thread = threading.Thread(
        target=_run_upgrade,
        args=(executable_sha256, executable_zip_urls, stop_event, exit_event),
    )
    thread.daemon = True
    thread.start()
    return thread


def _run_upgrade(executable_sha256, executable_zip_urls, stop_event, exit_event):
    log = get_logger()
    tmp_dir = os.path.join(os.getcwd(), _TMP_DIR_NAME)

    def check_cancelled():
        if _process._exit_requested(stop_event, exit_event):
            raise _Cancelled()

    try:
        check_cancelled()
        os.makedirs(tmp_dir, exist_ok=True)

        zip_path = _download_first(executable_zip_urls, tmp_dir, check_cancelled)
        if not zip_path:
            log.error("pyappify Failed to download upgrade.")
            return

        _extract_zip(zip_path, tmp_dir, check_cancelled)

        target_executable = pkg().pyappify_executable
        new_executable = _find_file(tmp_dir, os.path.basename(target_executable), check_cancelled)
        if not new_executable:
            log.error("pyappify Executable not found in zip.")
            return

        if executable_sha256 and _sha256_file(new_executable, check_cancelled) != executable_sha256:
            log.error("pyappify SHA256 checksum mismatch.")
            return

        check_cancelled()
        cancel_event = exit_event or stop_event
        launcher.kill_pyappify(exit_event=cancel_event)
        _replace_executable(new_executable, target_executable, exit_event=cancel_event)
        log.info("pyappify Upgrade success")
    except _Cancelled:
        pass
    except Exception as e:
        log.error(f"pyappify Upgrade failed: {e}")
    finally:
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir)


def _download_first(urls, directory, check_cancelled):
    """Download the first URL that succeeds into ``directory`` and return its path."""
    log = get_logger()
    for url in urls:
        check_cancelled()
        try:
            log.info(f"pyappify start to download {url}")
            local_path = os.path.join(directory, os.path.basename(url))
            with urllib.request.urlopen(
                url, timeout=_DOWNLOAD_IO_TIMEOUT_SECONDS
            ) as response, open(local_path, 'wb') as out_file:
                while True:
                    check_cancelled()
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    out_file.write(chunk)
            log.info(f"pyappify download success {url}")
            return local_path
        except _Cancelled:
            log.info("pyappify Upgrade download cancelled.")
            raise
        except Exception as e:
            log.warning(f"pyappify Failed to download from {url}: {e}")
    return None


def _extract_zip(zip_path, directory, check_cancelled):
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        for member in zip_ref.infolist():
            check_cancelled()
            zip_ref.extract(member, directory)


def _find_file(directory, file_name, check_cancelled):
    for root, _, files in os.walk(directory):
        check_cancelled()
        if file_name in files:
            return os.path.join(root, file_name)
    return None


def _sha256_file(path, check_cancelled):
    sha256_hash = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            check_cancelled()
            byte_block = f.read(4096)
            if not byte_block:
                break
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def _replace_executable(source_path, target_path, timeout=30, exit_event=None):
    deadline = time.monotonic() + timeout
    while True:
        _process._raise_if_exit_requested(exit_event)
        try:
            shutil.move(source_path, target_path)
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            if _process._wait_for_exit(exit_event, 0.25):
                _process._raise_if_exit_requested(exit_event)
