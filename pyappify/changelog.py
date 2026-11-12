"""Patch notes from human-written changelog files, one per language.

An app keeps ``CHANGELOG.md`` (English) at the root of its repository and may
add ``CHANGELOG.<language>.md`` for each launcher language, for example
``CHANGELOG.zh-CN.md`` or ``CHANGELOG.ja.md``::

    # Changelog

    ## v1.3.0 (2026-11-12)
    - Added a dark theme
    - Fixed a crash when a folder name
      contained emoji

    ## v1.2.0
    - First public release

``## <version>`` starts a version; ``[v1.3.0]``, ``1.3.0`` and trailing text
such as a date also match the tag ``v1.3.0``. ``- `` or ``* `` starts a note
and an indented line continues it. Everything else, including ``### Added``
style sub-headings, is ignored.

The changelogs are read from the version being installed. When that version has
an entry in the reader's language or in English, the notes are the entries of
every version tag the update brings in, each in the reader's language or else
English. Otherwise, as for every branch and pull request, they are commit
messages. The PyAppify launcher reads the same files the same way.
"""

ENGLISH = "en"
CHANGELOG_FILE = "CHANGELOG.md"


def changelog_path(language):
    """The file holding ``language``'s notes: ``CHANGELOG.md`` or ``CHANGELOG.<language>.md``."""
    if not language or language == ENGLISH:
        return CHANGELOG_FILE
    return "CHANGELOG.{}.md".format(language)


def version_key(version):
    """``[v1.3.0]`` and ``1.3.0`` both name the tag ``v1.3.0``: compare without them."""
    version = str(version).strip().strip("[]").strip()
    if version[:1] in ("v", "V") and version[1:2].isdigit():
        version = version[1:]
    return version


def parse_changelog(text):
    """``{version key: [note, ...]}`` for each ``## <version>`` section of ``text``."""
    notes = {}
    current = None
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if raw_line.startswith("## "):
            words = line[3:].split()
            current = notes.setdefault(version_key(words[0]), []) if words else None
        elif raw_line.startswith("# "):
            current = None
        elif current is None or not line or line.startswith("#"):
            continue
        elif line.startswith(("- ", "* ")):
            current.append(line[2:].strip())
        elif raw_line[:1] in (" ", "\t") and current:
            current[-1] = "{} {}".format(current[-1], line)
    return notes


def notes_for_versions(changelogs, versions, language):
    """The notes of ``versions`` (newest first) in ``language``, English where missing.

    ``changelogs`` maps a language to a parsed changelog. Repeated notes are
    shown once.
    """
    localized = changelogs.get(language) or {}
    english = changelogs.get(ENGLISH) or {}
    notes = []
    seen = set()
    for version in versions:
        key = version_key(version)
        for note in localized.get(key) or english.get(key) or []:
            if note and note not in seen:
                seen.add(note)
                notes.append(note)
    return notes


def has_entry(changelogs, version, language):
    """Whether ``version`` is in ``language``'s changelog or the English one."""
    key = version_key(version)
    return any(key in (changelogs.get(name) or {}) for name in (language, ENGLISH))
