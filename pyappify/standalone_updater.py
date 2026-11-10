"""Console process that applies a standalone update after the app exits.

Started by :func:`pyappify.standalone.update_to_version` as::

    python -m pyappify.standalone_updater <state dir>/update-job.json

in its own console window, so the user can watch the update log; the same log
is appended to ``update.log`` next to the job. The state dir is
``.git/pyappify`` for a plain clone and ``<app>/pyappify-update`` for the
launcher's layout, whose older installs are converted to the shared-checkout
layout first (see :mod:`pyappify.standalone`). Steps:

1. wait for the app to exit, stopping it after a grace period (as the launcher
   stops the app before updating);
2. check out the version tag (detached HEAD) and update submodules;
3. ``pip install`` the profile's requirements if they changed;
4. on failure, check out the previous commit again;
5. restart the app, with ``PYAPPIFY_APP_VERSION``, ``PYAPPIFY_APP_STARTING_VERSION``
   and ``PYAPPIFY_UPDATE_NOTE`` set after a successful update;
6. on Windows, refresh the Start Menu shortcut (and the Desktop one if it
   exists), as the launcher does.

On success the window closes after a few seconds; on failure it stays open
until the user presses Enter.
"""
import json
import logging
import os
import signal
import subprocess
import sys
import time

from . import _process, shortcut, standalone

SUCCESS_CLOSE_DELAY_SECONDS = 3
APP_STOP_TIMEOUT_SECONDS = 15


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: python -m pyappify.standalone_updater <update-job.json>")
        return 2
    job_path = os.path.abspath(argv[0])
    with open(job_path, "r", encoding="utf-8") as job_file:
        job = json.load(job_file)

    log = _setup_logging(os.path.join(os.path.dirname(job_path), standalone.LOG_FILE_NAME))
    _set_console_title("Updating to {}".format(job.get("version")))
    try:
        succeeded = run_job(job, log)
    except Exception:
        log.exception("Update failed unexpectedly.")
        succeeded = False
    finally:
        _remove(job_path)

    if succeeded:
        log.info("Done. This window closes in %s seconds.", SUCCESS_CLOSE_DELAY_SECONDS)
        time.sleep(SUCCESS_CLOSE_DELAY_SECONDS)
        return 0
    _pause("Update failed. Press Enter to close this window.")
    return 1


def run_job(job, log):
    """Apply the update described by ``job``; return whether it succeeded."""
    repo_path = job["repo_path"]
    version = job["version"]
    previous_commit = job["previous_commit"]
    log.info("Updating %s", repo_path)
    log.info("From %s to %s", job.get("previous_version") or previous_commit[:12], version)

    if not stop_app(job.get("pid"), job.get("exit_timeout", standalone.APP_EXIT_TIMEOUT_SECONDS), log):
        return False

    if standalone.is_launcher_layout(repo_path) and not standalone.is_bare_repo(repo_path):
        try:
            standalone.migrate_to_bare_layout(repo_path, log)
        except Exception as error:
            log.error("Could not convert %s to the shared-checkout layout: %s", repo_path, error)
            return False

    try:
        apply_version(repo_path, version, job.get("profile"), log)
    except Exception as error:
        log.error("Update to %s failed: %s", version, error)
        if rollback(repo_path, previous_commit, log):
            relaunch(job, {}, log)
        return False

    update_note = job.get("update_note") or []
    relaunch(job, {
        "PYAPPIFY_APP_VERSION": version,
        "PYAPPIFY_APP_STARTING_VERSION": job.get("previous_version") or version,
        "PYAPPIFY_UPDATE_NOTE": json.dumps(update_note, ensure_ascii=False) if update_note else "",
    }, log)
    refresh_shortcuts(job, log)
    log.info("Updated to %s.", version)
    return True


def refresh_shortcuts(job, log):
    """Refresh the app's shortcuts as the launcher does; failures are only logged."""
    relaunch_info = job.get("relaunch") or {}
    argv = relaunch_info.get("argv")
    if os.name != "nt" or not argv or not job.get("refresh_shortcuts"):
        return []
    try:
        paths = shortcut.refresh_shortcuts(
            target=argv[0],
            arguments=argv[1:],
            working_dir=relaunch_info.get("cwd") or standalone.app_files_dir(job["repo_path"]),
            profile=job.get("profile") or "",
        )
    except Exception as error:
        log.warning("Could not refresh the app's shortcuts: %s", error)
        return []
    for path in paths:
        log.info("Refreshed shortcut %s", path)
    if not paths:
        log.info("Shortcuts are up to date.")
    return paths


def stop_app(pid, grace_seconds, log):
    """Wait for the app to exit, then stop it; return whether it is gone."""
    if not pid or not _process._is_process_running(pid):
        return True
    log.info("Waiting up to %s seconds for the app (PID %s) to exit...", grace_seconds, pid)
    if _process._wait_for_process_exit(pid, grace_seconds):
        return True
    log.info("The app is still running. Stopping it.")
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as error:
        log.warning("Could not stop PID %s: %s", pid, error)
    if _process._wait_for_process_exit(pid, APP_STOP_TIMEOUT_SECONDS):
        return True
    log.error("The app (PID %s) did not exit. Close it and update again.", pid)
    return False


def apply_version(repo_path, version, profile, log):
    """Check out ``version``, update submodules and sync requirements if needed.

    In the launcher's layout tracked files are forced to the new version, as
    the launcher does; a plain clone with local changes is not touched.
    """
    managed = standalone.is_launcher_layout(repo_path)
    with standalone.open_repo(repo_path) as repo:
        if not managed and standalone.has_local_changes(repo):
            raise standalone.StandaloneUpdateError(
                "tracked files have local changes; commit or stash them first"
            )
        old_commit = repo.head()
        target_commit = standalone.tag_commit(repo, version)
        old_spec, _old_args, old_content = standalone.requirements_at(repo, old_commit, profile)

        log.info("Checking out %s (%s)...", version, target_commit.decode("ascii")[:12])
        _checkout(repo, target_commit, log, force=managed)

        new_spec, new_args, new_content = standalone.requirements_at(repo, target_commit, profile)

    files_dir = standalone.app_files_dir(repo_path)
    if not new_spec:
        log.info("No requirements configured. Skipping dependency sync.")
    elif old_spec != new_spec:
        log.info("Requirements changed from '%s' to '%s'. Syncing dependencies.", old_spec, new_spec)
        pip_install(files_dir, new_spec, new_args, log)
    elif old_content != new_content:
        changed_file = new_spec if new_spec.endswith(".txt") else "pyproject.toml"
        log.info("%s changed. Syncing dependencies.", changed_file)
        pip_install(files_dir, new_spec, new_args, log)
    else:
        log.info("Requirements are up to date. Skipping dependency sync.")


def rollback(repo_path, previous_commit, log):
    log.info("Rolling back to %s...", previous_commit[:12])
    try:
        with standalone.open_repo(repo_path) as repo:
            _checkout(
                repo,
                previous_commit.encode("ascii"),
                log,
                force=standalone.is_launcher_layout(repo_path),
            )
    except Exception as error:
        log.error("Rollback failed: %s", error)
        return False
    log.info("Rolled back. The app stays on its previous version.")
    return True


def _checkout(repo, commit_id, log, force=False):
    porcelain = standalone._dulwich().porcelain
    porcelain.checkout(repo, repo[commit_id], force=force)
    if os.path.isfile(os.path.join(repo.path, ".gitmodules")):
        log.info("Updating submodules...")
        standalone.link_submodule_work_trees(repo, log)
        porcelain.submodule_update(repo, init=True, recursive=True)


def pip_install(repo_path, spec, pip_args, log):
    command = [sys.executable, "-m", "pip", "install", "--no-warn-script-location"]
    command.extend(pip_args.split())
    if spec.endswith(".txt"):
        requirements_path = os.path.join(repo_path, spec)
        if not os.path.isfile(requirements_path):
            raise standalone.StandaloneUpdateError(
                "Requirements file not found at {}".format(requirements_path)
            )
        command.extend(["-r", requirements_path])
    else:
        command.extend(spec.split())

    log.info("Running: %s", subprocess.list2cmdline(command))
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    process = subprocess.Popen(
        command,
        cwd=repo_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
    )
    for line in process.stdout:
        log.info("  %s", line.rstrip())
    if process.wait() != 0:
        raise standalone.StandaloneUpdateError(
            "pip install exited with code {}".format(process.returncode)
        )


def relaunch(job, env_updates, log):
    relaunch_info = job.get("relaunch") or {}
    argv = relaunch_info.get("argv")
    if not argv:
        log.info("No restart command was recorded; start the app yourself.")
        return None

    env = os.environ.copy()
    pythonpath = relaunch_info.get("pythonpath")
    if pythonpath is None:
        env.pop("PYTHONPATH", None)
    else:
        env["PYTHONPATH"] = pythonpath
    env.update(env_updates)

    kwargs = {"cwd": relaunch_info.get("cwd") or None, "env": env, "close_fds": True}
    if os.name == "nt":
        gui = os.path.basename(argv[0]).lower() == "pythonw.exe"
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | (
            subprocess.DETACHED_PROCESS if gui else subprocess.CREATE_NEW_CONSOLE
        )
    else:
        kwargs["start_new_session"] = True
    try:
        process = subprocess.Popen(argv, **kwargs)
    except OSError as error:
        log.error("Could not restart the app (%s): %s", subprocess.list2cmdline(argv), error)
        return None
    log.info("Restarted the app (PID %s).", process.pid)
    return process


def _setup_logging(log_path):
    log = logging.getLogger("pyappify.standalone_updater")
    log.setLevel(logging.INFO)
    log.propagate = False
    log.handlers.clear()

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", "%H:%M:%S"))
    log.addHandler(console)
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        log_file = logging.FileHandler(log_path, encoding="utf-8")
        log_file.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(log_file)
    except OSError as error:
        log.warning("Cannot write the update log to %s: %s", log_path, error)
    return log


def _set_console_title(title):
    if os.name == "nt" and _process.ctypes:
        try:
            _process.ctypes.windll.kernel32.SetConsoleTitleW(title)
        except Exception:
            pass


def _pause(message):
    if not sys.stdin or not sys.stdin.isatty():
        return
    try:
        input(message)
    except (EOFError, KeyboardInterrupt):
        pass


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


if __name__ == "__main__":
    sys.exit(main())
