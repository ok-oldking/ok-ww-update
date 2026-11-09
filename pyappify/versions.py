"""Version comparison and update-note helpers."""
import re

# Same tag format and ordering as the launcher (src-tauri/src/git.rs):
# v1.2.3, 1.2.3, v1.2.3-beta, v1.2.3.rc.2 ... with alpha < beta < rc < release.
_VERSION_TAG_RE = re.compile(
    r"^v?(\d+)\.(\d+)\.(\d+)(?:(?:-|\.)(alpha|beta|rc)(?:\.(\d+))?)?$"
)
_PRERELEASE_RANK = {"alpha": 0, "beta": 1, "rc": 2, None: 3}


def version_tag_key(tag_name):
    """Return a sort key for a version tag, or None if it is not a version tag."""
    match = _VERSION_TAG_RE.match(tag_name or "")
    if not match:
        return None
    major, minor, patch, prerelease, number = match.groups()
    # A missing prerelease number sorts before any number, like Rust's Option.
    number_key = -1 if number is None else int(number)
    return int(major), int(minor), int(patch), _PRERELEASE_RANK[prerelease], number_key


def is_version_tag(tag_name):
    return version_tag_key(tag_name) is not None


def is_release_version(tag_name):
    key = version_tag_key(tag_name)
    return key is not None and key[3] == _PRERELEASE_RANK[None]


def sort_version_tags(tag_names):
    """Return the version tags in ``tag_names``, newest first."""
    keyed = [(version_tag_key(name), name) for name in tag_names]
    return [name for key, name in sorted(
        (item for item in keyed if item[0] is not None),
        key=lambda item: item[0],
        reverse=True,
    )]


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


def is_supported_pyappify_version(version):
    """Return whether a PyAppify version is valid and supports version checks."""
    if not isinstance(version, str) or not version:
        return False

    normalized = version[1:] if version.startswith("v") else version
    parts = normalized.split(".")
    if not parts or any(not part.isdigit() for part in parts):
        return False

    return tuple(int(part) for part in parts) >= (1, 2, 2)


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
