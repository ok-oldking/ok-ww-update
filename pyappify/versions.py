"""Version comparison and update-note helpers."""
import re

# Version tags, parsed and ordered the same way as the launcher
# (src-tauri/src/git.rs, src/versions.ts) and pyappify-action (versions.js):
#
#   [prefix] [v] N[.N[.N[.N]]] [prerelease word [number]]
#
# - prefix: a name ending in "-", "_" or "/" (release-, app-v, app/), ignored for ordering.
# - one to four number parts; missing parts count as 0 (v1.2 == v1.2.0). A single number
#   needs the v (v5, app-v5), so plain numbers, pr/7 and commit hashes are no versions.
# - the prerelease word may follow with or without "-", "." or "_", and so may its number:
#   1.2.3-beta.2, 1.2.3b2, 1.2.3rc1, 1.2.3-preview, 1.2.3.post1, in any case.
#   dev < alpha (a) < beta (b) < any other word < rc (c, pre, preview) < release < post.
#   A missing prerelease number sorts before any number.
_VERSION_TAG_RE = re.compile(
    r"^([A-Za-z][A-Za-z0-9_.-]*?[-_/])??([vV])?(\d+(?:\.\d+){0,3})"
    r"(?:[-._]?([A-Za-z]+)(?:[-._]?(\d+))?)?$"
)
_OTHER_RANK = 3
_RELEASE_RANK = 5
_WORD_RANK = {
    "dev": 0,
    "alpha": 1, "a": 1,
    "beta": 2, "b": 2,
    "rc": 4, "c": 4, "pre": 4, "preview": 4,
    "post": 6,
}
# Without version tags, an app's versions are its most recent commits on the
# default branch, newest first, named by their first COMMIT_VERSION_LENGTH hex digits.
RECENT_COMMIT_VERSIONS = 30
COMMIT_VERSION_LENGTH = 7
_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")


def _parse_version_tag(tag_name):
    match = _VERSION_TAG_RE.match(tag_name or "")
    if not match:
        return None
    prefix, v, numbers, word, number = match.groups()
    parts = [int(part) for part in numbers.split(".")]
    if len(parts) == 1 and not v:
        return None
    return match, parts, (word or "").lower(), number


def version_tag_key(tag_name):
    """Return a sort key for a version tag, or None if it is not a version tag."""
    parsed = _parse_version_tag(tag_name)
    if parsed is None:
        return None
    _match, parts, word, number = parsed
    parts = parts + [0] * (4 - len(parts))
    rank = _WORD_RANK.get(word, _OTHER_RANK) if word else _RELEASE_RANK
    # A missing prerelease number sorts before any number, like Rust's Option.
    number_key = -1 if number is None else int(number)
    return tuple(parts) + (rank, number_key, word if rank == _OTHER_RANK else "")


def version_without_prefix(tag_name):
    """The version part of a version tag without its name prefix and ``v``, or None."""
    parsed = _parse_version_tag(tag_name)
    return None if parsed is None else tag_name[parsed[0].start(3):]


def is_version_tag(tag_name):
    return version_tag_key(tag_name) is not None


def is_release_version(tag_name):
    """A release or post release tag, or a commit version."""
    if is_commit_version(tag_name):
        return True
    key = version_tag_key(tag_name)
    return key is not None and key[4] >= _RELEASE_RANK


def is_commit_version(version):
    """A commit version: 7 to 40 hex digits that are no version tag."""
    return bool(_COMMIT_RE.match(version or "")) and not is_version_tag(version)


def sort_version_tags(tag_names):
    """Return the version tags in ``tag_names``, newest first; equal versions by name."""
    keyed = [(version_tag_key(name), name) for name in tag_names]
    keyed = sorted((item for item in keyed if item[0] is not None), key=lambda item: item[1])
    return [name for _key, name in sorted(keyed, key=lambda item: item[0], reverse=True)]


def select_kept_tags(tag_names, keep):
    """Return the version tags a repository keeps, newest first.

    The ``keep`` newest releases and the prereleases newer than the oldest of
    them, as the launcher's ``keep_releases`` does. With fewer releases than
    ``keep`` every version tag is kept.
    """
    kept = []
    releases = 0
    for name in sort_version_tags(tag_names):
        if releases >= keep:
            break
        if is_release_version(name):
            releases += 1
        kept.append(name)
    return kept


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


def entry_notes(entry, language=None):
    """A version entry's notes in ``language``, a locale such as ``zh_CN`` or ``ja``.

    Its ``localized_notes`` (present when the notes come from the app's
    changelogs) in ``language``, else its ``update_note``.
    """
    if language:
        from .i18n import language_from_locale

        language = language_from_locale(language)
    localized = entry.get("localized_notes") if language else None
    if isinstance(localized, dict) and isinstance(localized.get(language), list):
        return localized[language]
    raw_notes = entry.get("update_note") or []
    return raw_notes if isinstance(raw_notes, list) else [raw_notes]


def calculate_update_notes(update_notes, current_version, target_version, language=None):
    """Return descending notes without including versions newer than the target.

    With ``language`` (such as ``"zh-CN"``), versions whose notes come from the
    app's changelogs show them in that language; see :func:`entry_notes`.
    """
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
        notes.extend(entry_notes(item, language))
    return [str(note) for note in notes]
