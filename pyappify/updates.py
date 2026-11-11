"""Listing app versions and updating the app to one of them.

With the PyAppify launcher present, requests go to the launcher. Without it
(the app runs from a plain git clone), the standalone Dulwich backend in
:mod:`pyappify.standalone` handles them.
"""
import os

from . import _process, launcher, standalone, pip_index
from .pip_index import PIP_INDEX_URLS
from ._state import pkg
from .versions import is_supported_pyappify_version


def _is_python_test():
    return "PYAPPIFY_PYTHON_TEST" in os.environ


def uses_launcher():
    """Return whether the app was started by, or ships with, the PyAppify launcher."""
    state = pkg()
    return bool(state.pyappify_version or state.pyappify_executable)


def is_local_checkout():
    """Return whether the app runs from a plain git clone, without the launcher.

    Such a checkout also lists its default branch, local branches and pull
    requests as versions when ``release_only`` is false.
    """
    if uses_launcher() or _is_python_test():
        return False
    return standalone.is_plain_checkout()


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

    if uses_launcher():
        pyappify_version = pkg().pyappify_version
        if not is_supported_pyappify_version(pyappify_version):
            raise RuntimeError(
                "PyAppify does not support checking for updates for "
                f"pyappify_version: {pyappify_version}"
            )
    elif not _is_python_test():
        return standalone.get_version_list(
            number_versions, release_only, timeout=timeout, exit_event=exit_event
        )

    if _is_python_test():
        if _process._wait_for_exit(exit_event, 5):
            _process._raise_if_exit_requested(exit_event)
        return _get_mock_version_list(number_versions)

    response = launcher._run_launcher_api(
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


def get_versions(number_versions=10, release_only=True, timeout=120, exit_event=None):
    """Alias for get_version_list."""
    return get_version_list(number_versions, release_only, timeout, exit_event)


def update_to_version(version, timeout=300, exit_event=None):
    """Update the app, cancelling with InterruptedError on exit_event."""
    if not isinstance(version, str) or not version.strip():
        raise ValueError("version must be a non-empty string")
    if _is_python_test():
        _process._raise_if_exit_requested(exit_event)
        return {"updated": True, "version": version, "mocked": True}
    if not uses_launcher():
        state = pkg()
        return standalone.update_to_version(
            version,
            timeout=timeout,
            exit_event=exit_event,
            app_version=state.app_version,
            app_profile=state.app_profile,
        )
    response = launcher._run_launcher_api(
        ["--update-to-version", version],
        timeout=timeout,
        exit_event=exit_event,
    )
    if not isinstance(response, dict) or not response.get("updated"):
        raise RuntimeError("PyAppify returned an invalid update response")
    return response


def _get_mock_version_list(number_versions):
    """Return deterministic launcher data for UI and integration tests."""
    current = pkg().app_version or "v1.0.0"
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


_test_pip_index_url = ""


def _require_pip_index_api():
    if os.environ.get("PYAPPIFY_PIP_INDEX_API") != "1":
        raise RuntimeError("This PyAppify launcher does not support choosing the pip index")


def _validate_pip_index_response(response):
    if (not isinstance(response, dict)
            or not isinstance(response.get("pip_index_url"), str)
            or not isinstance(response.get("default"), str)
            or not isinstance(response.get("options"), list)
            or not all(isinstance(url, str) for url in response["options"])):
        raise RuntimeError("PyAppify returned an invalid pip-index response")
    return response


def get_pip_index_config(timeout=10, exit_event=None):
    """Return the selected pip index, default and available options.

    An empty index means pip's system default. Unsupported launchers raise
    RuntimeError immediately; launcher errors and cancellation propagate.
    """
    if _is_python_test():
        _process._raise_if_exit_requested(exit_event)
        return pip_index.config(_test_pip_index_url)
    if uses_launcher():
        _require_pip_index_api()
        return _validate_pip_index_response(launcher._run_launcher_api(
            ["--get-pip-index-url"], timeout=timeout, exit_event=exit_event
        ))
    _process._raise_if_exit_requested(exit_event)
    return pip_index.config(pip_index.read_url())


def set_pip_index_url(url, timeout=10, exit_event=None):
    """Choose an index for future dependency installs; empty uses pip defaults.

    Unsupported launchers raise RuntimeError without starting a request.
    """
    global _test_pip_index_url
    if not isinstance(url, str):
        raise TypeError("url must be a string")
    if not _is_python_test() and uses_launcher():
        _require_pip_index_api()
        return _validate_pip_index_response(launcher._run_launcher_api(
            ["--set-pip-index-url", url or "default"],
            timeout=timeout, exit_event=exit_event
        ))
    if url not in PIP_INDEX_URLS:
        raise ValueError("Unsupported pip index URL: {}".format(url))
    _process._raise_if_exit_requested(exit_event)
    if _is_python_test():
        _test_pip_index_url = url
    else:
        pip_index.write_url(url)
    return pip_index.config(url)
