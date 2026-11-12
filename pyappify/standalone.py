"""Updating a git checkout of the app without the PyAppify launcher.

Used when no launcher executable was found and ``PYAPPIFY_VERSION`` is not
set. Versions are the checkout's version tags, the same ones the launcher
uses. Git access goes through Dulwich, so git itself does not need to be
installed (``pip install "pyappify[standalone]"``).

Two layouts are supported:

- a plain git clone the app runs from (updates refuse to overwrite local
  changes to tracked files). When test versions are listed, it also offers,
  before the version tags: the remote's default branch, its local branches
  (``local/<branch>``) and the open pull requests of a GitHub remote
  (``pr/<number>``);
- the launcher's layout, where the app runs from ``<app>/working`` and
  ``<app>/repo`` is a bare repository whose work tree is ``working``. Files the
  app creates in ``working`` are kept; tracked files are forced to the new
  version, as the launcher does. An install from older launchers, where
  ``repo`` was a full clone copied into ``working``, is converted to this
  layout by the first update.

``update_to_version`` only prepares the update while the app runs. The checkout
and the dependency sync happen in ``python -m pyappify.standalone_updater``,
which opens its own console window for the log, waits for the app to exit
(stopping it after a grace period, as the launcher does) and then restarts it.
"""
import functools
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import types
import urllib.request
from contextlib import contextmanager

from . import _process, changelog, i18n
from ._state import get_logger
from .versions import is_release_version, is_version_tag, select_kept_tags, sort_version_tags

REMOTE_NAME = b"origin"
TAG_PREFIX = b"refs/tags/"
PEELED_SUFFIX = b"^{}"
HEAD_REF = b"HEAD"
BRANCH_PREFIX = b"refs/heads/"
REMOTE_BRANCH_PREFIX = b"refs/remotes/origin/"
REMOTE_HEAD_REF = REMOTE_BRANCH_PREFIX + HEAD_REF
# Pull request heads: refs/pull/<n>/head on the remote, kept locally under
# refs/pyappify/pull/<n> so they never mix with the user's own refs.
REMOTE_PULL_REF = b"refs/pull/%d/head"
LOCAL_PULL_PREFIX = b"refs/pyappify/pull/"

# What a version of a plain git clone can be, besides a version tag.
KIND_BRANCH = "branch"  # the remote's default branch; the version is its name
KIND_LOCAL = "local"    # a local branch; the version is "local/<branch>"
KIND_PULL = "pr"        # an open pull request; the version is "pr/<number>"
KIND_TAG = "tag"
LOCAL_VERSION_PREFIX = "local/"
PULL_VERSION_PREFIX = "pr/"
MAX_LOCAL_BRANCHES = 10
MAX_PULL_REQUESTS = 10
PULL_REQUEST_TIMEOUT_SECONDS = 15
STALE_LOCK_SECONDS = 60

# How a listed version relates to the checked-out commit.
RELATION_CURRENT = "current"
RELATION_NEWER = "newer"
RELATION_OLDER = "older"
RELATION_OTHER = "other"
MAX_UPDATE_NOTE_LINES = 10
PYAPPIFY_YML = "pyappify.yml"
DEFAULT_REQUIREMENTS = "requirements.txt"
STATE_DIR_NAME = "pyappify"
JOB_FILE_NAME = "update-job.json"
LOG_FILE_NAME = "update.log"
APP_EXIT_TIMEOUT_SECONDS = 10

# The launcher's layout: <app>/repo (bare git data) and <app>/working (files).
REPO_DIR_NAME = "repo"
WORKING_DIR_NAME = "working"
MIGRATING_GIT_DIR_NAME = "repo.git.migrating"
OLD_CHECKOUT_DIR_NAME = "repo.checkout.old"
LAYOUT_STATE_DIR_NAME = "pyappify-update"


class StandaloneUpdateError(RuntimeError):
    """A standalone update cannot be listed, prepared or applied."""


@functools.lru_cache(maxsize=None)
def _dulwich():
    try:
        from dulwich import porcelain
        from dulwich.client import get_transport_and_path
        from dulwich.errors import NotGitRepository
        from dulwich.graph import can_fast_forward
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
        can_fast_forward=can_fast_forward,
        tree_lookup_path=tree_lookup_path,
        Repo=Repo,
        ORDER_DATE=ORDER_DATE,
    )


# --- repository access ----------------------------------------------------


def find_repo_path(start_dir=None, environ=None):
    """Return the app's repository: a plain checkout's root, or ``<app>/repo``.

    ``PYAPPIFY_REPO_PATH`` overrides the search upward from ``start_dir`` (the
    current directory by default). A ``working`` folder with a ``repo`` folder
    next to it is the launcher's layout.
    """
    environ = os.environ if environ is None else environ
    dulwich = _dulwich()
    configured = environ.get("PYAPPIFY_REPO_PATH")
    start = configured or start_dir or os.getcwd()
    if configured and is_launcher_layout(configured):
        return os.path.abspath(configured)
    if not configured:
        layout_repo = find_launcher_layout(start)
        if layout_repo:
            return layout_repo
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


def find_launcher_layout(start_dir):
    """Return ``<app>/repo`` when ``start_dir`` is inside ``<app>/working``, else None."""
    path = os.path.abspath(start_dir)
    while True:
        if os.path.basename(path) == WORKING_DIR_NAME:
            base = os.path.dirname(path)
            repo_path = os.path.join(base, REPO_DIR_NAME)
            if os.path.isdir(os.path.join(base, MIGRATING_GIT_DIR_NAME)):
                # A migration was interrupted; finishing it restores ``repo``.
                migrate_to_bare_layout(repo_path)
            if is_launcher_layout(repo_path):
                return repo_path
        parent = os.path.dirname(path)
        if parent == path:
            return None
        path = parent


def is_bare_repo(repo_path):
    """Return whether ``repo_path`` is a git directory without its own checkout."""
    return os.path.isfile(os.path.join(repo_path, "HEAD")) and not os.path.exists(
        os.path.join(repo_path, ".git")
    )


def is_launcher_layout(repo_path):
    """Return whether ``repo_path`` is ``<app>/repo`` of the launcher's layout.

    That is a bare repository named ``repo``, or (from older launchers) a full
    clone named ``repo`` with a ``working`` copy next to it.
    """
    repo_path = os.path.abspath(repo_path)
    if os.path.basename(repo_path) != REPO_DIR_NAME:
        return False
    if is_bare_repo(repo_path):
        return True
    return os.path.isdir(os.path.join(repo_path, ".git")) and os.path.isdir(
        work_tree_for(repo_path)
    )


def work_tree_for(repo_path):
    """The ``working`` folder next to ``<app>/repo``."""
    return os.path.join(os.path.dirname(os.path.abspath(repo_path)), WORKING_DIR_NAME)


def app_files_dir(repo_path):
    """The folder holding the app's files: ``working`` for the launcher's layout."""
    return work_tree_for(repo_path) if is_launcher_layout(repo_path) else repo_path


@contextmanager
def open_repo(repo_path):
    """Open a repository; a bare launcher ``repo`` gets ``working`` as its work tree."""
    dulwich = _dulwich()
    if is_launcher_layout(repo_path) and is_bare_repo(repo_path):
        work_tree = work_tree_for(repo_path)
        os.makedirs(work_tree, exist_ok=True)
        repo = dulwich.Repo(controldir=repo_path, worktree=work_tree)
    else:
        repo = dulwich.Repo(repo_path)
    try:
        yield repo
    finally:
        repo.close()


def state_dir(repo_path):
    """Directory for the update job and log, never tracked by git.

    Inside ``.git`` for a plain checkout. For the launcher's layout it is next
    to ``repo``, which the updater may move while converting an old install.
    """
    if is_launcher_layout(repo_path):
        return os.path.join(os.path.dirname(os.path.abspath(repo_path)), LAYOUT_STATE_DIR_NAME)
    with open_repo(repo_path) as repo:
        return os.path.join(repo.controldir(), STATE_DIR_NAME)


def migrate_to_bare_layout(repo_path, log=None):
    """Convert an older launcher install into the bare ``repo`` layout.

    Older launchers kept a full clone in ``repo`` and copied its files into
    ``working``. The clone's git data becomes the bare ``repo`` and its
    duplicate files are deleted; the index is kept, since it describes the
    files that were copied into ``working``. Matches the launcher's migration,
    so either one can finish a migration the other started.
    """
    log = log or get_logger()
    base = os.path.dirname(os.path.abspath(repo_path))
    git_dir = os.path.join(repo_path, ".git")
    moved_git_dir = os.path.join(base, MIGRATING_GIT_DIR_NAME)
    old_checkout = os.path.join(base, OLD_CHECKOUT_DIR_NAME)

    if os.path.isdir(git_dir):
        log.info("Moving %s to the shared-checkout layout (git data in repo, app files in working)...", repo_path)
        _set_core_bare(os.path.join(git_dir, "config"))
        os.rename(git_dir, moved_git_dir)
    if os.path.isdir(moved_git_dir):
        if os.path.exists(repo_path):
            if os.path.exists(old_checkout):
                shutil.rmtree(old_checkout)
            os.rename(repo_path, old_checkout)
        os.rename(moved_git_dir, repo_path)
        with open_repo(repo_path) as repo:
            link_submodule_work_trees(repo, log)
    if os.path.exists(old_checkout):
        shutil.rmtree(old_checkout, ignore_errors=True)
        if os.path.exists(old_checkout):
            log.warning("Could not remove the old checkout at %s; it can be deleted manually.", old_checkout)
        else:
            log.info("Removed the old duplicate checkout at %s.", old_checkout)


def _set_core_bare(config_path):
    from dulwich.config import ConfigFile

    config = ConfigFile.from_path(config_path)
    config.set((b"core",), b"bare", True)
    config.write_to_path(config_path)


def link_submodule_work_trees(repo, log=None):
    """Point each submodule folder in the work tree at its git data in ``<repo>/modules``.

    Like the launcher: after converting an old install (whose copies skipped
    ``.git``) a submodule folder in ``working`` has no ``.git`` link, so it is
    added and the submodule's ``core.worktree`` is pointed at ``working``.
    """
    from dulwich.config import ConfigFile, read_submodules

    log = log or get_logger()
    work_tree = os.path.abspath(repo.path)
    gitmodules = os.path.join(work_tree, ".gitmodules")
    if not os.path.isfile(gitmodules):
        return
    git_dir = os.path.abspath(repo.controldir())
    for path, _url, name in read_submodules(gitmodules):
        path = path.decode("utf-8")
        name = name.decode("utf-8")
        module_work_tree = os.path.join(work_tree, path)
        if os.path.exists(os.path.join(module_work_tree, ".git")):
            continue
        module_git_dir = os.path.join(git_dir, "modules", name)
        if not os.path.isfile(os.path.join(module_git_dir, "HEAD")):
            continue
        os.makedirs(module_work_tree, exist_ok=True)
        link = os.path.relpath(module_git_dir, module_work_tree).replace(os.sep, "/")
        with open(os.path.join(module_work_tree, ".git"), "w", encoding="utf-8") as link_file:
            link_file.write("gitdir: {}\n".format(link))
        config_path = os.path.join(module_git_dir, "config")
        config = ConfigFile.from_path(config_path)
        config.set(
            (b"core",),
            b"worktree",
            os.path.relpath(module_work_tree, module_git_dir).replace(os.sep, "/").encode("utf-8"),
        )
        config.write_to_path(config_path)
        log.info("Linked submodule '%s' at %s to %s", name, module_work_tree, module_git_dir)


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


def _read_tag_targets(repo):
    """Return ``{tag name: (sha, peeled commit or None)}`` in one pass over the refs.

    Dulwich re-parses ``packed-refs`` for every ref it resolves, which takes
    seconds in a repository with a thousand tags, so the file is read once here.
    A missing peeled commit means the sha still has to be peeled.
    """
    git_dir = repo.commondir()
    targets = {}
    try:
        with open(os.path.join(git_dir, "packed-refs"), "rb") as packed:
            lines = packed.read().splitlines()
    except OSError:
        lines = []
    fully_peeled = bool(lines) and lines[0].startswith(b"#") and b"fully-peeled" in lines[0]
    last = None
    for line in lines:
        if line.startswith(b"#") or not line.strip():
            continue
        if line.startswith(b"^"):
            if last is not None:
                targets[last] = (targets[last][0], line[1:].strip())
            continue
        sha, _, ref = line.partition(b" ")
        ref = ref.strip()
        if not ref.startswith(TAG_PREFIX):
            last = None
            continue
        last = ref[len(TAG_PREFIX):].decode("utf-8", "replace")
        # In a fully-peeled file a tag without a "^" line already names its commit.
        targets[last] = (sha, sha if fully_peeled else None)

    tags_dir = os.path.join(git_dir, "refs", "tags")
    for folder, _dirs, files in os.walk(tags_dir):
        for file_name in files:
            path = os.path.join(folder, file_name)
            try:
                with open(path, "rb") as loose:
                    sha = loose.read().strip()
            except OSError:
                continue
            name = os.path.relpath(path, tags_dir).replace(os.sep, "/")
            targets[name] = (sha, None)  # a loose ref overrides a packed one
    return targets


def _peel_to_commit(repo, sha):
    """Follow annotated tag objects from ``sha`` to the object they name."""
    obj = repo[sha]
    while obj.type_name == b"tag":
        sha = obj.object[1]
        obj = repo[sha]
    return sha


def head_version(repo):
    """Return the newest version tag at HEAD, or None."""
    try:
        head = repo.head()
    except KeyError:
        return None
    try:
        targets = _read_tag_targets(repo)
    except Exception:
        targets = None
    if targets is None:
        for tag in local_version_tags(repo):
            if tag_commit(repo, tag) == head:
                return tag
        return None
    for tag in sort_version_tags(targets):
        sha, peeled = targets[tag]
        if peeled is None:
            try:
                peeled = _peel_to_commit(repo, sha)
            except Exception:
                continue
        if peeled == head:
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


# --- branches and pull requests -----------------------------------------------


def _ref(repo, name):
    try:
        return repo.refs[name]
    except KeyError:
        return None


def _pull_ref(number):
    return LOCAL_PULL_PREFIX + b"%d" % int(number)


def _followed_ref(repo, name):
    """The ref a symbolic ref points at, or None."""
    try:
        names, _sha = repo.refs.follow(name)
    except KeyError:
        return None
    return names[-1] if len(names) > 1 else None


def head_ref(repo):
    """Return the checked-out branch or stored pull request label, or None."""
    head = repo.refs.read_loose_ref(HEAD_REF)
    if not head:
        return None
    if head.startswith(b"ref: "):
        target = head[5:].strip()
        if target.startswith(BRANCH_PREFIX):
            return target[len(BRANCH_PREFIX):].decode("utf-8", "replace")
        return None
    targets = dict(repo.refs.get_packed_refs())
    for ref in repo.refs.allkeys():
        if ref.startswith(LOCAL_PULL_PREFIX):
            loose = repo.refs.read_loose_ref(ref)
            if loose is not None:
                targets[ref] = loose
    numbers = [
        int(ref[len(LOCAL_PULL_PREFIX):])
        for ref, sha in targets.items()
        if ref.startswith(LOCAL_PULL_PREFIX)
        and ref[len(LOCAL_PULL_PREFIX):].isdigit() and sha == head
    ]
    return "pr#{}".format(min(numbers)) if numbers else None


def head_branch(repo):
    """Name of the checked-out branch, or None when HEAD is detached."""
    target = _followed_ref(repo, HEAD_REF)
    if target and target.startswith(BRANCH_PREFIX):
        return target[len(BRANCH_PREFIX):].decode("utf-8", "replace")
    return None


def default_branch(repo):
    """Name of the remote's default branch as last fetched, or None."""
    target = _followed_ref(repo, REMOTE_HEAD_REF)
    if target and target.startswith(REMOTE_BRANCH_PREFIX) and _ref(repo, target):
        return target[len(REMOTE_BRANCH_PREFIX):].decode("utf-8", "replace")
    for name in ("main", "master"):
        if _ref(repo, REMOTE_BRANCH_PREFIX + name.encode("ascii")):
            return name
    return None


def is_ancestor(repo, ancestor, commit):
    """Return whether ``commit`` is ``ancestor`` or descends from it."""
    try:
        return _dulwich().can_fast_forward(repo, ancestor, commit)
    except Exception:
        return False


def commit_relation(repo, head, commit):
    """How ``commit`` relates to the checked-out ``head`` commit."""
    if head is None:
        return RELATION_OTHER
    if commit == head:
        return RELATION_CURRENT
    if is_ancestor(repo, head, commit):
        return RELATION_NEWER
    if is_ancestor(repo, commit, head):
        return RELATION_OLDER
    return RELATION_OTHER


def branch_target(repo, name):
    """Commit an update to the remote branch ``name`` checks out.

    That is the fetched remote tip, which a local branch of that name is
    fast-forwarded to. Local commits the remote does not have are kept: they
    are the target when the remote has nothing new, and an error when both
    sides have new commits.
    """
    remote = _ref(repo, REMOTE_BRANCH_PREFIX + name.encode("utf-8"))
    if remote is None:
        raise StandaloneUpdateError("Branch '{}' does not exist on the remote.".format(name))
    local = _ref(repo, BRANCH_PREFIX + name.encode("utf-8"))
    if local is None or local == remote or is_ancestor(repo, local, remote):
        return remote
    if is_ancestor(repo, remote, local):
        return local
    raise StandaloneUpdateError(
        "Cannot update to '{0}': the local branch '{0}' and origin/{0} have "
        "diverged. Merge or rebase it first.".format(name)
    )


def version_kind(version):
    """Classify a version string; anything unprefixed that is no tag is a branch."""
    if is_version_tag(version):
        return KIND_TAG
    if version.startswith(PULL_VERSION_PREFIX) and version[len(PULL_VERSION_PREFIX):].isdigit():
        return KIND_PULL
    if version.startswith(LOCAL_VERSION_PREFIX) and len(version) > len(LOCAL_VERSION_PREFIX):
        return KIND_LOCAL
    return KIND_BRANCH


def resolve_version(repo, version, tags_only=False):
    """Return ``(kind, commit, branch)`` for a version of the checkout.

    ``branch`` is the local branch to check out; None leaves HEAD detached at
    ``commit``, as for version tags and pull requests. ``tags_only`` is for the
    launcher's layout, whose versions are always tags.
    """
    kind = KIND_TAG if tags_only else version_kind(version)
    if kind == KIND_PULL:
        number = version[len(PULL_VERSION_PREFIX):]
        commit = _ref(repo, _pull_ref(number))
        if commit is None:
            raise StandaloneUpdateError("Pull request #{} was not fetched.".format(number))
        return kind, commit, None
    if kind == KIND_LOCAL:
        branch = version[len(LOCAL_VERSION_PREFIX):]
        commit = _ref(repo, BRANCH_PREFIX + branch.encode("utf-8"))
        if commit is None:
            raise StandaloneUpdateError("Local branch '{}' does not exist.".format(branch))
        return kind, commit, branch
    if kind == KIND_BRANCH and _ref(repo, REMOTE_BRANCH_PREFIX + version.encode("utf-8")):
        return kind, branch_target(repo, version), version
    # A version tag, or a tag whose name is not in the version format.
    return KIND_TAG, tag_commit(repo, version), None


def _with_ref_lock(operation):
    """Run a ref update, removing a lock file that a killed process left behind.

    Dulwich, like git, takes ``<ref>.lock`` for every ref it writes. An app
    closed in the middle of a fetch leaves that file, and every later update
    of the ref would fail. A lock younger than ``STALE_LOCK_SECONDS`` may be
    another process at work and is reported instead.
    """
    from dulwich.file import FileLocked

    try:
        return operation()
    except FileLocked as error:
        lock = os.fsdecode(error.lockfilename)
        try:
            age = time.time() - os.path.getmtime(lock)
        except OSError:
            age = None  # released in the meantime
        if age is not None:
            if age < STALE_LOCK_SECONDS:
                raise StandaloneUpdateError(
                    "The repository is being changed by another process ({} exists). "
                    "Try again in a moment.".format(lock)
                )
            get_logger().warning("pyappify removing stale lock %s", lock)
            os.remove(lock)
        return operation()


def set_ref(repo, ref, sha):
    _with_ref_lock(lambda: repo.refs.__setitem__(ref, sha))


def delete_ref(repo, ref):
    _with_ref_lock(lambda: repo.refs.__delitem__(ref))


def set_symbolic_ref(repo, ref, target):
    _with_ref_lock(lambda: repo.refs.set_symbolic_ref(ref, target))


def attach_branch(repo, branch, commit):
    """Point the local ``branch`` at ``commit`` and make it the checked-out branch.

    The work tree must already be at ``commit``.
    """
    ref = BRANCH_PREFIX + branch.encode("utf-8")
    set_ref(repo, ref, commit)
    set_symbolic_ref(repo, HEAD_REF, ref)


# --- fetching ---------------------------------------------------------------

# Written by the launcher from pyappify.yml's ``keep_releases``.
KEEP_RELEASES_CONFIG = (b"pyappify", b"keepreleases")


def _positive_int(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def keep_releases(repo):
    """How many releases the repository keeps, or None to keep every tag.

    Read from the repository config the launcher writes, else from the
    ``keep_releases`` of pyappify.yml at HEAD.
    """
    try:
        return _positive_int(repo.get_config().get(*KEEP_RELEASES_CONFIG).decode("ascii"))
    except (KeyError, UnicodeDecodeError):
        pass
    try:
        yml = read_file_at(repo, repo.head(), PYAPPIFY_YML)
    except KeyError:
        return None
    if yml is None:
        return None
    return _positive_int(parse_app_config(yml.decode("utf-8", "replace")).get("keep_releases"))


def head_tags(repo):
    """Names of the local tags pointing at HEAD."""
    try:
        head = repo.head()
    except KeyError:
        return set()
    tags = set()
    for name in repo.refs.as_dict(TAG_PREFIX):
        try:
            if repo.get_peeled(TAG_PREFIX + name) == head:
                tags.add(name)
        except KeyError:
            pass
    return tags


def remote_url(repo):
    """URL of the checkout's ``origin`` remote."""
    try:
        return repo.get_config().get((b"remote", REMOTE_NAME), b"url").decode("utf-8")
    except KeyError:
        raise StandaloneUpdateError(
            "The git checkout at {} has no 'origin' remote.".format(repo.path)
        )


def _remote_client(repo):
    return _dulwich().get_transport_and_path(
        remote_url(repo), config=repo.get_config_stack()
    )


def fetch_tags(repo_path, progress=None):
    """Fetch the remote's tags; return ``(updated, pruned)`` tag names.

    The launcher's layout mirrors them, like ``git fetch origin
    +refs/tags/*:refs/tags/* --prune``, and with ``keep_releases`` (see
    :func:`keep_releases`) fetches and keeps only the kept version tags, plus
    the tags of the checked-out commit.

    A plain clone is a developer's own repository: every tag is fetched and
    none is deleted, whatever ``keep_releases`` says.
    """
    managed = is_launcher_layout(repo_path)
    with open_repo(repo_path) as repo:
        client, remote_path = _remote_client(repo)

        def is_tag(ref, sha):
            return ref.startswith(TAG_PREFIX) and not ref.endswith(PEELED_SUFFIX) and sha

        keep = keep_releases(repo) if managed else None
        protected = head_tags(repo) if keep is not None else set()

        def wanted_tags(refs):
            """Remote tag names (bytes) to keep, mapped to their sha."""
            tags = {
                ref[len(TAG_PREFIX):]: sha for ref, sha in refs.items() if is_tag(ref, sha)
            }
            if keep is None:
                return tags
            kept = {
                name.encode("utf-8")
                for name in select_kept_tags(
                    [name.decode("utf-8", "replace") for name in tags], keep
                )
            }
            kept |= protected
            return {name: sha for name, sha in tags.items() if name in kept}

        def determine_wants(refs, *_args, **_kwargs):
            wants = []
            for sha in wanted_tags(refs).values():
                if sha not in repo.object_store and sha not in wants:
                    wants.append(sha)
            return wants

        result = client.fetch(
            remote_path,
            repo,
            determine_wants=determine_wants,
            progress=progress,
            ref_prefix=[TAG_PREFIX],
        )
        remote_tags = wanted_tags(result.refs)
        local_tags = repo.refs.as_dict(TAG_PREFIX)

        updated = []
        for name, sha in remote_tags.items():
            if local_tags.get(name) != sha:
                set_ref(repo, TAG_PREFIX + name, sha)
                updated.append(name.decode("utf-8", "replace"))
        pruned = []
        for name in local_tags if managed else ():
            if name not in remote_tags:
                delete_ref(repo, TAG_PREFIX + name)
                pruned.append(name.decode("utf-8", "replace"))
        return updated, pruned


def fetch_branches(repo_path, pull_numbers=(), prune_pulls=False, progress=None):
    """Fetch the remote's default branch and the heads of ``pull_numbers``.

    The default branch goes to ``refs/remotes/origin/<branch>``, with
    ``refs/remotes/origin/HEAD`` pointing at it; pull request heads go to
    ``refs/pyappify/pull/<number>``. ``prune_pulls`` drops the stored heads of
    every other pull request. Local branches are never touched. Returns the
    default branch's name, or None if the remote does not tell.
    """
    with open_repo(repo_path) as repo:
        client, remote_path = _remote_client(repo)
        pull_refs = {REMOTE_PULL_REF % number: number for number in pull_numbers}
        fallback_refs = [
            BRANCH_PREFIX + name.encode("utf-8")
            for name in (default_branch(repo), "main", "master") if name
        ]

        def determine_wants(refs, *_args, **_kwargs):
            wanted = [refs.get(HEAD_REF)] if refs.get(HEAD_REF) else [
                refs.get(ref) for ref in fallback_refs
            ]
            wanted.extend(refs.get(ref) for ref in pull_refs)
            wants = []
            for sha in wanted:
                if sha and sha not in repo.object_store and sha not in wants:
                    wants.append(sha)
            return wants

        result = client.fetch(
            remote_path,
            repo,
            determine_wants=determine_wants,
            progress=progress,
            ref_prefix=[HEAD_REF, BRANCH_PREFIX] + list(pull_refs),
        )
        refs = result.refs

        branch_ref = (getattr(result, "symrefs", None) or {}).get(HEAD_REF)
        if not (branch_ref and branch_ref.startswith(BRANCH_PREFIX) and refs.get(branch_ref)):
            # No symref from the remote: a branch at the remote HEAD's commit.
            head_sha = refs.get(HEAD_REF)
            candidates = fallback_refs + sorted(ref for ref in refs if ref.startswith(BRANCH_PREFIX))
            branch_ref = next(
                (ref for ref in candidates if refs.get(ref) and refs[ref] == (head_sha or refs[ref])),
                None,
            )

        branch = None
        if branch_ref and refs[branch_ref] in repo.object_store:
            name = branch_ref[len(BRANCH_PREFIX):]
            set_ref(repo, REMOTE_BRANCH_PREFIX + name, refs[branch_ref])
            set_symbolic_ref(repo, REMOTE_HEAD_REF, REMOTE_BRANCH_PREFIX + name)
            branch = name.decode("utf-8", "replace")

        kept = set()
        for ref, number in pull_refs.items():
            sha = refs.get(ref)
            if sha and sha in repo.object_store:
                set_ref(repo, _pull_ref(number), sha)
                kept.add(b"%d" % number)
        if prune_pulls:
            for name in repo.refs.as_dict(LOCAL_PULL_PREFIX):
                if name not in kept:
                    delete_ref(repo, LOCAL_PULL_PREFIX + name)
        return branch


_GITHUB_URL_RE = re.compile(
    r"^(?:https?://(?:[^@/]+@)?github\.com/|(?:ssh://)?git@github\.com[:/])"
    r"([^/]+)/([^/]+?)(?:\.git)?/?$"
)


def github_repository(url):
    """Return ``(owner, name)`` of a github.com remote URL, or None."""
    match = _GITHUB_URL_RE.match(url or "")
    return match.groups() if match else None


def list_pull_requests(url, limit=MAX_PULL_REQUESTS, timeout=PULL_REQUEST_TIMEOUT_SECONDS):
    """Open pull requests of a GitHub remote as ``[(number, title)]``, newest first.

    Asks the public GitHub API; remotes on other hosts have none.
    """
    repository = github_repository(url)
    if not repository:
        return []
    request = urllib.request.Request(
        "https://api.github.com/repos/{}/{}/pulls?state=open&per_page={}".format(
            repository[0], repository[1], limit
        ),
        headers={"Accept": "application/vnd.github+json", "User-Agent": "pyappify"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        pulls = json.loads(response.read().decode("utf-8"))
    return [
        (int(pull["number"]), str(pull.get("title") or "").strip())
        for pull in pulls if isinstance(pull, dict) and "number" in pull
    ][:limit]


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


def _fetch_branches_logged(repo_path, timeout, exit_event, pull_numbers=None):
    """Fetch the default branch and pull requests; return ``[(number, title)]``.

    ``pull_numbers`` fetches just those; None looks up the open pull requests,
    which is best effort: without them the default branch is still fetched.
    """
    log = get_logger()

    def fetch():
        if pull_numbers is None:
            try:
                with open_repo(repo_path) as repo:
                    url = remote_url(repo)
                pulls = list_pull_requests(url)
            except Exception as error:
                log.warning("pyappify could not list pull requests: %s", error)
                pulls = []
        else:
            pulls = [(number, "") for number in pull_numbers]
        branch = fetch_branches(
            repo_path, [number for number, _title in pulls], prune_pulls=pull_numbers is None
        )
        log.info("pyappify fetched default branch %s and %s pull requests", branch, len(pulls))
        return pulls

    log.info("pyappify fetching branches for %s", repo_path)
    return _run_cancellable(fetch, timeout, exit_event, "fetching branches")


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


def commit_notes_for_update(repo, target_commit, current_commit):
    """Commit-message notes for moving from ``current_commit`` to ``target_commit``.

    Falls back to the target commit's own message when nothing new is reachable,
    for example on a downgrade, as the launcher does.
    """
    messages = collect_commit_messages(repo, target_commit, current_commit)
    if messages:
        return messages
    message = repo[target_commit].message.decode("utf-8", "replace")
    return [line.strip() for line in message.splitlines() if line.strip()]


def read_changelogs(repo, commit_id):
    """``{language: parsed changelog}`` for the changelog files in ``commit_id``."""
    changelogs = {}
    for language in i18n.LANGUAGES:
        data = read_file_at(repo, commit_id, changelog.changelog_path(language))
        if data is not None:
            changelogs[language] = changelog.parse_changelog(data.decode("utf-8-sig", "replace"))
    return changelogs


def version_tags_by_commit(repo):
    """``{commit id: [version tag, ...]}``, each list newest first."""
    try:
        targets = _read_tag_targets(repo)
    except Exception:
        targets = None
    tags = {}
    for tag in (sort_version_tags(targets) if targets is not None else local_version_tags(repo)):
        try:
            if targets is None:
                commit = tag_commit(repo, tag)
            else:
                sha, commit = targets[tag]
                commit = commit if commit is not None else _peel_to_commit(repo, sha)
        except Exception:
            continue
        tags.setdefault(commit, []).append(tag)
    return tags


def changelog_notes(repo, target_commit, hidden_commit, tags_by_commit, commit_notes):
    """``{language: notes}`` for moving to ``target_commit``, or None without a changelog.

    A language's notes come from the changelogs in ``target_commit`` (see
    :mod:`pyappify.changelog`) when its version tag has an entry in that
    language or in English: the entries of every version tag reachable from
    ``target_commit`` but not from ``hidden_commit``, newest first, or the
    target's own when nothing is (a downgrade). Other languages get
    ``commit_notes()``. None when no language has an entry.
    """
    target_versions = list(tags_by_commit.get(target_commit) or ())
    if not target_versions:
        return None
    changelogs = read_changelogs(repo, target_commit)
    languages = [
        language for language in i18n.LANGUAGES
        if any(changelog.has_entry(changelogs, version, language) for version in target_versions)
    ]
    if not languages:
        return None
    versions = list(target_versions)
    walker = repo.get_walker(
        include=[target_commit],
        exclude=[hidden_commit] if hidden_commit else None,
        order=_dulwich().ORDER_DATE,
    )
    for entry in walker:
        if entry.commit.id != target_commit:
            versions.extend(tags_by_commit.get(entry.commit.id) or ())
    fallback = None
    notes = {}
    for language in i18n.LANGUAGES:
        if language in languages:
            notes[language] = changelog.notes_for_versions(changelogs, versions, language)
        else:
            fallback = commit_notes() if fallback is None else fallback
            notes[language] = fallback
    return notes


def _resolve_notes(repo, target_commit, hidden_commit, tags_by_commit, language, commit_notes):
    """``(notes in language, {language: notes} or None)``: changelog, else commit messages."""
    localized = changelog_notes(repo, target_commit, hidden_commit, tags_by_commit, commit_notes)
    if localized is not None:
        return localized[language] if language in localized else localized[changelog.ENGLISH], localized
    return commit_notes(), None


def notes_for_update(repo, target_commit, current_commit, language=None, tags_by_commit=None):
    """Notes for moving from ``current_commit`` to ``target_commit`` in ``language``.

    The changelog's notes when the target is a version with an entry, else
    commit messages (see :func:`commit_notes_for_update`). ``language``
    defaults to :func:`pyappify.i18n.resolve_language`.
    """
    notes, _localized = _resolve_notes(
        repo, target_commit, current_commit,
        version_tags_by_commit(repo) if tags_by_commit is None else tags_by_commit,
        language or i18n.resolve_language(),
        lambda: commit_notes_for_update(repo, target_commit, current_commit),
    )
    return notes


def _version_entry(kind, version, title, commit, relation, notes, previous=None):
    update_note, localized = notes
    entry = {
        "version": version,
        "previous_version": previous,
        "update_note": update_note,
        "kind": kind,
        "title": title,
        "commit": commit.decode("ascii"),
        "relation": relation,
    }
    if localized is not None:
        # The changelog's notes in every language, to switch without listing again.
        entry["localized_notes"] = localized
    return entry


def _commit_time(repo, commit):
    try:
        return repo[commit].commit_time
    except Exception:
        return 0


def list_branch_versions(repo, pulls=(), language=None, tags_by_commit=None):
    """The branch versions of a plain clone, from already fetched refs.

    In order: the remote's default branch, the local branches (the checked-out
    one first, then the most recently committed) and the pull requests in
    ``pulls``, given as ``[(number, title)]``.
    """
    try:
        head = repo.head()
    except KeyError:
        head = None
    current_branch = head_branch(repo)
    language = language or i18n.resolve_language()
    if tags_by_commit is None:
        tags_by_commit = version_tags_by_commit(repo)

    def entry(kind, version, title, commit, on_branches=None):
        relation = commit_relation(repo, head, commit)
        # The checked-out commit through another branch is still a switch.
        if relation == RELATION_CURRENT and on_branches and current_branch not in on_branches:
            relation = RELATION_OTHER
        notes = _resolve_notes(
            repo, commit, head, tags_by_commit, language,
            lambda: commit_notes_for_update(repo, commit, head),
        )
        return _version_entry(kind, version, title, commit, relation, notes)

    versions = []
    default = default_branch(repo)
    if default:
        try:
            commit = branch_target(repo, default)
        except StandaloneUpdateError:
            # Diverged: list the remote tip; updating to it reports the reason.
            commit = repo.refs[REMOTE_BRANCH_PREFIX + default.encode("utf-8")]
        versions.append(entry(KIND_BRANCH, default, default, commit, (None, default)))

    branches = [
        (name.decode("utf-8", "replace"), commit)
        for name, commit in repo.refs.as_dict(BRANCH_PREFIX).items()
    ]
    branches = sorted(
        (item for item in branches if item[0] != default),
        key=lambda item: (item[0] != current_branch, -_commit_time(repo, item[1]), item[0]),
    )
    for name, commit in branches[:MAX_LOCAL_BRANCHES]:
        versions.append(entry(
            KIND_LOCAL, LOCAL_VERSION_PREFIX + name, "{} (local)".format(name), commit, (name,)
        ))

    for number, title in pulls:
        commit = _ref(repo, _pull_ref(number))
        if commit is not None:
            versions.append(entry(
                KIND_PULL,
                "{}{}".format(PULL_VERSION_PREFIX, number),
                "#{} {}".format(number, title).strip(),
                commit,
            ))
    return versions


def list_versions(repo_path, number_versions, release_only, pulls=(), language=None):
    """Version history from local refs, in the launcher's response format.

    Each entry also has its ``kind``, a ``title`` to show, its ``commit`` and
    its ``relation`` to the checked-out commit. A plain clone that also wants
    test versions lists its branches and ``pulls`` before the version tags; see
    :func:`list_branch_versions`.

    ``update_note`` is in ``language`` (default
    :func:`pyappify.i18n.resolve_language`). An entry whose notes come from the
    app's changelogs also has ``localized_notes``: ``{language: notes}`` for
    every launcher language.
    """
    language = language or i18n.resolve_language()
    with open_repo(repo_path) as repo:
        tags_by_commit = version_tags_by_commit(repo)
        versions = []
        if not release_only and not is_launcher_layout(repo_path):
            versions.extend(list_branch_versions(repo, pulls, language, tags_by_commit))
        try:
            head = repo.head()
        except KeyError:
            head = None
        tags = local_version_tags(repo)
        if release_only:
            tags = [tag for tag in tags if is_release_version(tag)]
        for index, version in enumerate(tags[:number_versions]):
            previous = tags[index + 1] if index + 1 < len(tags) else None
            commit = tag_commit(repo, version)
            previous_commit = tag_commit(repo, previous) if previous else None
            notes = _resolve_notes(
                repo, commit, previous_commit, tags_by_commit, language,
                lambda: collect_commit_messages(repo, commit, previous_commit),
            )
            versions.append(_version_entry(
                KIND_TAG,
                version,
                version,
                commit,
                commit_relation(repo, head, commit),
                notes,
                previous,
            ))
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


def detect_app_checkout(start_dir=None):
    """Return the checkout's version and plain-clone ref label, or None values."""
    try:
        repo_path = find_repo_path(start_dir)
        with open_repo(repo_path) as repo:
            version = head_version(repo)
            ref = None if is_launcher_layout(repo_path) else head_ref(repo)
            return version, ref
    except Exception:
        return None, None


def detect_app_ref(start_dir=None):
    """Return the plain clone's branch or pull request label, or None."""
    try:
        repo_path = find_repo_path(start_dir)
        if is_launcher_layout(repo_path):
            return None
        with open_repo(repo_path) as repo:
            return head_ref(repo)
    except Exception:
        return None


def detect_app_version(start_dir=None):
    """Return the version tag at HEAD of the app's checkout, or None."""
    try:
        with open_repo(find_repo_path(start_dir)) as repo:
            return head_version(repo)
    except Exception:
        return None


def is_plain_checkout(start_dir=None):
    """Return whether the app runs from a plain git clone, not the launcher's layout."""
    try:
        return not is_launcher_layout(find_repo_path(start_dir))
    except Exception:
        return False


def get_version_list(
    number_versions=10, release_only=True, timeout=120, exit_event=None, repo_path=None,
    language=None,
):
    repo_path = repo_path or find_repo_path()
    _fetch_tags_logged(repo_path, timeout, exit_event)
    pulls = ()
    if not release_only and not is_launcher_layout(repo_path):
        _process._raise_if_exit_requested(exit_event)
        pulls = _fetch_branches_logged(repo_path, timeout, exit_event)
    _process._raise_if_exit_requested(exit_event)
    return list_versions(repo_path, number_versions, release_only, pulls, language)


def update_to_version(
    version, timeout=300, exit_event=None, app_version=None, app_profile=None, language=None
):
    """Prepare an update to ``version`` and start the updater.

    The app must exit for the update to apply; the updater stops it after
    ``APP_EXIT_TIMEOUT_SECONDS`` and restarts it on the new version. The
    updater shows a progress window when Tk is available (see
    :mod:`pyappify.updater_ui`), else a console window.
    """
    log = get_logger()
    job = prepare_update_job(
        version,
        timeout=timeout,
        exit_event=exit_event,
        app_version=app_version,
        app_profile=app_profile,
        pid=os.getpid(),
        relaunch=relaunch_info(),
        language=language,
    )
    job_path = write_update_job(job)
    _process._raise_if_exit_requested(exit_event)
    _start_updater(job_path)
    log.info("pyappify started the standalone updater for %s; the app will restart", version)
    return {
        "updated": True,
        "version": version,
        "restart_required": True,
        "update_note": job["update_note"],
    }


def prepare_update_job(
    version,
    timeout=300,
    exit_event=None,
    app_version=None,
    app_profile=None,
    repo_path=None,
    pid=None,
    relaunch=None,
    exit_timeout=APP_EXIT_TIMEOUT_SECONDS,
    language=None,
):
    """Fetch what ``version`` needs and return the updater job for it.

    Nothing in the app's files changes yet. ``update_note`` is in ``language``
    (default :func:`pyappify.i18n.resolve_language`). ``pid`` is the app process the
    updater stops first and ``relaunch`` (see :func:`relaunch_info`) how it
    restarts the app; without them the updater does neither.
    """
    repo_path = repo_path or find_repo_path()
    managed = is_launcher_layout(repo_path)
    kind = KIND_TAG if managed else version_kind(version)
    # A local branch needs nothing from the remote, so it also works offline.
    if kind != KIND_LOCAL:
        _fetch_tags_logged(repo_path, timeout, exit_event)
        if kind != KIND_TAG:
            _process._raise_if_exit_requested(exit_event)
            pull_numbers = [int(version[len(PULL_VERSION_PREFIX):])] if kind == KIND_PULL else []
            _fetch_branches_logged(repo_path, timeout, exit_event, pull_numbers)
    _process._raise_if_exit_requested(exit_event)

    with open_repo(repo_path) as repo:
        _kind, target_commit, _branch = resolve_version(repo, version, tags_only=managed)
        # The launcher's layout is managed: tracked files are forced to the new
        # version, as the launcher does. A plain clone may hold the user's work.
        if not managed and has_local_changes(repo):
            raise StandaloneUpdateError(
                "Cannot update {}: tracked files have local changes. Commit or "
                "stash them first.".format(repo_path)
            )
        current_commit = repo.head()
        previous_ref = _followed_ref(repo, HEAD_REF)
        previous_version = app_version or head_version(repo)
        if previous_version == version:
            update_note = []
        else:
            update_note = notes_for_update(repo, target_commit, current_commit, language)

    return {
        "repo_path": repo_path,
        "version": version,
        "previous_version": previous_version,
        "previous_commit": current_commit.decode("ascii"),
        # The branch that was checked out, restored if the update fails.
        "previous_ref": previous_ref.decode("utf-8") if previous_ref else None,
        "update_note": update_note,
        "profile": app_profile,
        "pid": pid,
        "exit_timeout": exit_timeout,
        "relaunch": relaunch or {"argv": None, "cwd": None, "pythonpath": None},
        "refresh_shortcuts": bool(relaunch),
    }


def write_update_job(job):
    """Write ``job`` to the state dir and return its path."""
    job_dir = state_dir(job["repo_path"])
    os.makedirs(job_dir, exist_ok=True)
    job_path = os.path.join(job_dir, JOB_FILE_NAME)
    with open(job_path, "w", encoding="utf-8") as job_file:
        json.dump(job, job_file, indent=2, ensure_ascii=False)
    return job_path


def relaunch_info():
    """How the updater restarts this process: its command, folder and PYTHONPATH."""
    return {
        "argv": _relaunch_argv(),
        "cwd": os.getcwd(),
        "pythonpath": os.environ.get("PYTHONPATH"),
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


def _gui_python():
    """pythonw.exe next to python.exe, so a window opens without a console."""
    executable = sys.executable
    directory, name = os.path.split(executable)
    if name.lower() == "python.exe":
        candidate = os.path.join(directory, "pythonw.exe")
        if os.path.isfile(candidate):
            return candidate
    return executable


def _start_updater(job_path):
    from . import updater_ui

    package_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        path for path in (package_parent, env.get("PYTHONPATH")) if path
    )
    env["PYTHONIOENCODING"] = "utf-8"
    # Started from the job's folder, never from inside ``repo``: Windows will
    # not move a folder that is a process's current directory, and the updater
    # may move ``repo`` while converting an old launcher install.
    kwargs = {"cwd": os.path.dirname(job_path), "env": env, "close_fds": True}
    if updater_ui.can_show_window():
        python = _gui_python()
        command = [python, "-m", "pyappify.updater_ui", "--job", job_path]
        console = False
    else:
        python = _console_python()
        command = [python, "-m", "pyappify.standalone_updater", job_path]
        console = True
    if os.name == "nt":
        if console:
            window = subprocess.CREATE_NEW_CONSOLE
        elif os.path.basename(python).lower() == "pythonw.exe":
            window = subprocess.DETACHED_PROCESS
        else:
            window = subprocess.CREATE_NO_WINDOW
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | window
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(command, **kwargs)
