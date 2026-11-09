"""Updating a git checkout of the app without the PyAppify launcher.

Used when the app runs from a plain git clone: no launcher executable was found
and ``PYAPPIFY_VERSION`` is not set. Versions are the checkout's version tags,
the same ones the launcher uses. Git access goes through Dulwich, so git itself
does not need to be installed (``pip install "pyappify[standalone]"``).

``update_to_version`` only prepares the update while the app runs. The checkout
and the dependency sync happen in ``python -m pyappify.standalone_updater``,
which opens its own console window for the log, waits for the app to exit
(stopping it after a grace period, as the launcher does) and then restarts it.
"""
import functools
import json
import os
import subprocess
import sys
import threading
import time
import types
from contextlib import contextmanager

from . import _process
from ._state import get_logger
from .versions import is_release_version, sort_version_tags

REMOTE_NAME = b"origin"
TAG_PREFIX = b"refs/tags/"
PEELED_SUFFIX = b"^{}"
MAX_UPDATE_NOTE_LINES = 10
PYAPPIFY_YML = "pyappify.yml"
DEFAULT_REQUIREMENTS = "requirements.txt"
STATE_DIR_NAME = "pyappify"
JOB_FILE_NAME = "update-job.json"
LOG_FILE_NAME = "update.log"
APP_EXIT_TIMEOUT_SECONDS = 10


class StandaloneUpdateError(RuntimeError):
    """A standalone update cannot be listed, prepared or applied."""


@functools.lru_cache(maxsize=None)
def _dulwich():
    try:
        from dulwich import porcelain
        from dulwich.client import get_transport_and_path
        from dulwich.errors import NotGitRepository
        from dulwich.object_store import tree_lookup_path
        from dulwich.repo import Repo
        from dulwich.walk import ORDER_DATE
    except ImportError:
        raise StandaloneUpdateError(
            "Updating without the PyAppify launcher requires Dulwich (Python 3.10+). "
            'Install it with: pip install "pyappify[standalone]"'
        )

    return types.SimpleNamespace(
        porcelain=porcelain,
        get_transport_and_path=get_transport_and_path,
        NotGitRepository=NotGitRepository,
        tree_lookup_path=tree_lookup_path,
        Repo=Repo,
        ORDER_DATE=ORDER_DATE,
    )


# --- repository access ----------------------------------------------------


def find_repo_path(start_dir=None, environ=None):
    """Return the git checkout the app runs from.

    ``PYAPPIFY_REPO_PATH`` overrides the search upward from ``start_dir`` (the
    current directory by default).
    """
    environ = os.environ if environ is None else environ
    dulwich = _dulwich()
    configured = environ.get("PYAPPIFY_REPO_PATH")
    start = configured or start_dir or os.getcwd()
    try:
        if configured:
            repo = dulwich.Repo(configured)
        else:
            repo = dulwich.Repo.discover(start)
    except dulwich.NotGitRepository:
        raise StandaloneUpdateError(
            "Cannot update without the PyAppify launcher: {} is not inside a git "
            "checkout. Set PYAPPIFY_REPO_PATH to the app's repository.".format(start)
        )
    try:
        return os.path.abspath(repo.path)
    finally:
        repo.close()


@contextmanager
def open_repo(repo_path):
    repo = _dulwich().Repo(repo_path)
    try:
        yield repo
    finally:
        repo.close()


def state_dir(repo):
    """Directory inside .git for the update job and log, never tracked by git."""
    return os.path.join(repo.controldir(), STATE_DIR_NAME)


def local_version_tags(repo):
    """Return the checkout's version tags, newest first."""
    names = [name.decode("utf-8", "replace") for name in repo.refs.as_dict(TAG_PREFIX)]
    return sort_version_tags(names)


def tag_commit(repo, tag_name):
    """Return the commit id a tag points to, peeling annotated tags."""
    ref = TAG_PREFIX + tag_name.encode("utf-8")
    try:
        return repo.get_peeled(ref)
    except KeyError:
        raise StandaloneUpdateError("Version tag '{}' does not exist.".format(tag_name))


def head_version(repo):
    """Return the newest version tag at HEAD, or None."""
    try:
        head = repo.head()
    except KeyError:
        return None
    for tag in local_version_tags(repo):
        if tag_commit(repo, tag) == head:
            return tag
    return None


def has_local_changes(repo):
    """Return whether tracked files differ from HEAD (untracked files are ignored)."""
    status = _dulwich().porcelain.status(repo, untracked_files="no")
    return any(status.staged.values()) or bool(status.unstaged)


def read_file_at(repo, commit_id, path):
    """Return the bytes of ``path`` in ``commit_id``, or None if it does not exist."""
    dulwich = _dulwich()
    try:
        _mode, blob_id = dulwich.tree_lookup_path(
            repo.__getitem__, repo[commit_id].tree, path.encode("utf-8")
        )
        return repo[blob_id].data
    except KeyError:
        return None


# --- fetching ---------------------------------------------------------------


def fetch_tags(repo_path, progress=None):
    """Mirror the remote's tags, like ``git fetch origin +refs/tags/*:refs/tags/* --prune``.

    Returns ``(updated, pruned)`` tag names.
    """
    dulwich = _dulwich()
    with open_repo(repo_path) as repo:
        try:
            url = repo.get_config().get((b"remote", REMOTE_NAME), b"url")
        except KeyError:
            raise StandaloneUpdateError(
                "The git checkout at {} has no 'origin' remote.".format(repo_path)
            )
        client, remote_path = dulwich.get_transport_and_path(
            url.decode("utf-8"), config=repo.get_config_stack()
        )

        def is_tag(ref, sha):
            return ref.startswith(TAG_PREFIX) and not ref.endswith(PEELED_SUFFIX) and sha

        def determine_wants(refs, *_args, **_kwargs):
            wants = []
            for ref, sha in refs.items():
                if is_tag(ref, sha) and sha not in repo.object_store and sha not in wants:
                    wants.append(sha)
            return wants

        result = client.fetch(
            remote_path,
            repo,
            determine_wants=determine_wants,
            progress=progress,
            ref_prefix=[TAG_PREFIX],
        )
        remote_tags = {
            ref[len(TAG_PREFIX):]: sha
            for ref, sha in result.refs.items()
            if is_tag(ref, sha)
        }
        local_tags = repo.refs.as_dict(TAG_PREFIX)

        updated = []
        for name, sha in remote_tags.items():
            if local_tags.get(name) != sha:
                repo.refs[TAG_PREFIX + name] = sha
                updated.append(name.decode("utf-8", "replace"))
        pruned = []
        for name in local_tags:
            if name not in remote_tags:
                del repo.refs[TAG_PREFIX + name]
                pruned.append(name.decode("utf-8", "replace"))
        return updated, pruned


def _run_cancellable(operation, timeout, exit_event, description):
    """Run ``operation`` in a worker thread so exit_event and timeout stay responsive.

    A cancelled or timed-out operation keeps running in its daemon thread until
    the network call returns; it only touches its own Repo instance.
    """
    outcome = {}

    def run():
        try:
            outcome["value"] = operation()
        except BaseException as error:
            outcome["error"] = error

    worker = threading.Thread(target=run, name="pyappify-" + description, daemon=True)
    worker.start()
    deadline = time.monotonic() + timeout
    while worker.is_alive():
        _process._raise_if_exit_requested(exit_event)
        if time.monotonic() >= deadline:
            raise TimeoutError("Timed out while {}".format(description))
        worker.join(0.05)
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("value")


def _fetch_tags_logged(repo_path, timeout, exit_event):
    log = get_logger()
    log.info("pyappify fetching version tags for %s", repo_path)
    updated, pruned = _run_cancellable(
        lambda: fetch_tags(repo_path), timeout, exit_event, "fetching version tags"
    )
    if updated or pruned:
        log.info("pyappify fetched tags %s, pruned %s", updated, pruned)


# --- update notes -------------------------------------------------------------


def collect_commit_messages(repo, target_commit, hidden_commit=None):
    """Return up to 10 unique message lines of non-merge commits, newest first.

    Commits reachable from ``target_commit`` but not from ``hidden_commit``.
    """
    walker = repo.get_walker(
        include=[target_commit],
        exclude=[hidden_commit] if hidden_commit else None,
        order=_dulwich().ORDER_DATE,
    )
    messages = []
    seen = set()
    for entry in walker:
        commit = entry.commit
        if len(commit.parents) > 1:
            continue
        for line in commit.message.decode("utf-8", "replace").splitlines():
            line = line.strip()
            if line and line not in seen:
                seen.add(line)
                messages.append(line)
                if len(messages) >= MAX_UPDATE_NOTE_LINES:
                    return messages
    return messages


def notes_for_update(repo, target_commit, current_commit):
    """Notes for moving from ``current_commit`` to ``target_commit``.

    Falls back to the target commit's own message when nothing new is reachable,
    for example on a downgrade, as the launcher does.
    """
    messages = collect_commit_messages(repo, target_commit, current_commit)
    if messages:
        return messages
    message = repo[target_commit].message.decode("utf-8", "replace")
    return [line.strip() for line in message.splitlines() if line.strip()]


def list_versions(repo_path, number_versions, release_only):
    """Version history from local tags, in the launcher's response format."""
    with open_repo(repo_path) as repo:
        tags = local_version_tags(repo)
        if release_only:
            tags = [tag for tag in tags if is_release_version(tag)]
        versions = []
        for index, version in enumerate(tags[:number_versions]):
            previous = tags[index + 1] if index + 1 < len(tags) else None
            versions.append({
                "version": version,
                "previous_version": previous,
                "update_note": collect_commit_messages(
                    repo,
                    tag_commit(repo, version),
                    tag_commit(repo, previous) if previous else None,
                ),
            })
        return versions


# --- requirements -------------------------------------------------------------


def _parse_scalar(value):
    value = value.strip()
    if value[:1] in ("'", '"'):
        end = value.find(value[0], 1)
        if end > 0:
            return value[1:end]
    return value.split(" #", 1)[0].rstrip()


def _parse_app_config_without_yaml(text):
    """Read pyappify.yml when PyYAML is not installed.

    Only what the launcher reads is supported: top-level ``key: value`` scalars
    and a ``profiles`` list of flat ``key: value`` entries.
    """
    config = {}
    profiles = []
    in_profiles = False
    profile_indent = None
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip())
        if indent == 0:
            key, _, value = stripped.partition(":")
            key = key.strip()
            in_profiles = key == "profiles"
            if not in_profiles and value.strip():
                config[key] = _parse_scalar(value)
            continue
        if not in_profiles:
            continue
        if stripped.startswith("- ") or stripped == "-":
            profiles.append({})
            profile_indent = indent
            stripped = stripped[1:].strip()
            if not stripped:
                continue
        elif profile_indent is None or indent <= profile_indent:
            continue
        if profiles and ":" in stripped:
            key, value = stripped.split(":", 1)
            profiles[-1][key.strip()] = _parse_scalar(value)
    config["profiles"] = profiles
    return config


def parse_app_config(text):
    """Parse pyappify.yml into a dict whose ``profiles`` is a list of dicts."""
    try:
        import yaml
    except ImportError:
        return _parse_app_config_without_yaml(text)
    document = yaml.safe_load(text) or {}
    if not isinstance(document, dict):
        document = {}
    profiles = document.get("profiles")
    document["profiles"] = [
        profile for profile in profiles if isinstance(profile, dict)
    ] if isinstance(profiles, list) else []
    return document


def parse_profiles(text):
    return parse_app_config(text)["profiles"]


def select_profile(profiles, profile_name=None):
    """Return ``profile_name`` (or the first profile), inheriting unset keys from the first.

    Mirrors the launcher's profile inheritance; returns {} without profiles.
    """
    if not profiles:
        return {}
    first = profiles[0]
    profile = next(
        (item for item in profiles if str(item.get("name")) == profile_name), first
    )
    merged = dict(first)
    merged.update({key: value for key, value in profile.items() if value not in (None, "")})
    return merged


def requirements_at(repo, commit_id, profile_name=None):
    """Return ``(spec, pip_args, content)`` for a commit, as the launcher computes them.

    ``spec`` is the profile's ``requirements`` (a .txt file or a pip argument),
    inherited from the first profile when empty. ``content`` is that file, or
    pyproject.toml for a non-.txt spec, used to detect changes.
    """
    spec, pip_args = "", ""
    yml = read_file_at(repo, commit_id, PYAPPIFY_YML)
    if yml is not None:
        profile = select_profile(parse_profiles(yml.decode("utf-8", "replace")), profile_name)
        spec = str(profile.get("requirements") or "")
        pip_args = str(profile.get("pip_args") or "")
    elif read_file_at(repo, commit_id, DEFAULT_REQUIREMENTS) is not None:
        spec = DEFAULT_REQUIREMENTS

    if not spec:
        return "", pip_args, None
    content_path = spec if spec.endswith(".txt") else "pyproject.toml"
    return spec, pip_args, read_file_at(repo, commit_id, content_path)


# --- public entry points --------------------------------------------------------


def detect_app_version(start_dir=None):
    """Return the version tag at HEAD of the app's checkout, or None."""
    try:
        with open_repo(find_repo_path(start_dir)) as repo:
            return head_version(repo)
    except Exception:
        return None


def get_version_list(number_versions=10, release_only=True, timeout=120, exit_event=None):
    repo_path = find_repo_path()
    _fetch_tags_logged(repo_path, timeout, exit_event)
    _process._raise_if_exit_requested(exit_event)
    return list_versions(repo_path, number_versions, release_only)


def update_to_version(
    version, timeout=300, exit_event=None, app_version=None, app_profile=None
):
    """Prepare an update to ``version`` and start the console updater.

    The app must exit for the update to apply; the updater stops it after
    ``APP_EXIT_TIMEOUT_SECONDS`` and restarts it on the new version.
    """
    log = get_logger()
    repo_path = find_repo_path()
    _fetch_tags_logged(repo_path, timeout, exit_event)
    _process._raise_if_exit_requested(exit_event)

    with open_repo(repo_path) as repo:
        target_commit = tag_commit(repo, version)
        if has_local_changes(repo):
            raise StandaloneUpdateError(
                "Cannot update {}: tracked files have local changes. Commit or "
                "stash them first.".format(repo_path)
            )
        current_commit = repo.head()
        previous_version = app_version or head_version(repo)
        if previous_version == version:
            update_note = []
        else:
            update_note = notes_for_update(repo, target_commit, current_commit)
        job_dir = state_dir(repo)

    job = {
        "repo_path": repo_path,
        "version": version,
        "previous_version": previous_version,
        "previous_commit": current_commit.decode("ascii"),
        "update_note": update_note,
        "profile": app_profile,
        "pid": os.getpid(),
        "exit_timeout": APP_EXIT_TIMEOUT_SECONDS,
        "relaunch": {
            "argv": _relaunch_argv(),
            "cwd": os.getcwd(),
            "pythonpath": os.environ.get("PYTHONPATH"),
        },
        "refresh_shortcuts": True,
    }
    os.makedirs(job_dir, exist_ok=True)
    job_path = os.path.join(job_dir, JOB_FILE_NAME)
    with open(job_path, "w", encoding="utf-8") as job_file:
        json.dump(job, job_file, indent=2, ensure_ascii=False)

    _process._raise_if_exit_requested(exit_event)
    _start_updater(job_path, repo_path)
    log.info("pyappify started the standalone updater for %s; the app will restart", version)
    return {
        "updated": True,
        "version": version,
        "restart_required": True,
        "update_note": update_note,
    }


def _relaunch_argv():
    original = getattr(sys, "orig_argv", None) or [sys.executable] + sys.argv
    return [sys.executable] + list(original[1:])


def _console_python():
    """python.exe next to pythonw.exe, so the updater gets a visible console."""
    executable = sys.executable
    directory, name = os.path.split(executable)
    if name.lower() == "pythonw.exe":
        candidate = os.path.join(directory, "python.exe")
        if os.path.isfile(candidate):
            return candidate
    return executable


def _start_updater(job_path, repo_path):
    package_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        path for path in (package_parent, env.get("PYTHONPATH")) if path
    )
    env["PYTHONIOENCODING"] = "utf-8"
    kwargs = {"cwd": repo_path, "env": env, "close_fds": True}
    if os.name == "nt":
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(
        [_console_python(), "-m", "pyappify.standalone_updater", job_path], **kwargs
    )
