"""Pip index choices shared by the API and standalone updater.

An empty choice means "automatic": unless pip is already configured with an
index, the updater measures the mirrors below and uses the fastest one. The
result is cached in pip-index.json for a week, apart from the user's choice.
"""
import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

from . import standalone

PYPI_URL = "https://pypi.org/simple/"
ALIYUN_URL = "https://mirrors.aliyun.com/pypi/simple/"
PIP_INDEX_URLS = (
    "",
    PYPI_URL,
    ALIYUN_URL,
    "https://repo.huaweicloud.com/repository/pypi/simple/",
    "https://mirrors.cloud.tencent.com/pypi/simple/",
)
CONFIG_FILE_NAME = "pip-index.json"
AUTO_KEY = "auto_pip_index_url"
AUTO_CHECKED_KEY = "auto_checked_at"
AUTO_MAX_AGE = 7 * 24 * 3600
PROBE_TIMEOUT = 3.0
# Mirrors this close to the fastest count as a tie, and a tie goes to Aliyun.
TIE_RATIO = 1.2
TIE_SLACK = 0.03
DISABLE_ENV = "PYAPPIFY_AUTO_PIP_INDEX"


def config(url):
    return {"pip_index_url": url, "default": "", "options": list(PIP_INDEX_URLS)}


def config_path(repo_path=None):
    repo_path = standalone.find_repo_path(repo_path)
    return os.path.join(standalone.state_dir(repo_path), CONFIG_FILE_NAME)


def _read_document(repo_path):
    with open(config_path(repo_path), "r", encoding="utf-8") as source:
        return json.load(source)


def _read_document_quietly(repo_path):
    try:
        document = _read_document(repo_path)
    except (OSError, ValueError, UnicodeError):
        return {}
    return document if isinstance(document, dict) else {}


def read_url(repo_path=None, log=None):
    """Read the saved choice, using pip defaults if the file is invalid."""
    try:
        document = _read_document(repo_path)
    except FileNotFoundError:
        return ""
    except (ValueError, UnicodeError) as error:
        if log is not None:
            log.warning("Ignoring invalid pip-index.json; using pip defaults: %s", error)
        return ""
    if isinstance(document, dict) and "pip_index_url" not in document:
        return ""  # Only the automatic choice is cached; the user picked nothing.
    url = document.get("pip_index_url") if isinstance(document, dict) else None
    if not isinstance(url, str) or url not in PIP_INDEX_URLS:
        if log is not None:
            log.warning("Ignoring invalid pip-index.json; using pip defaults")
        return ""
    return url


def _write_fields(repo_path, **fields):
    path = config_path(repo_path)
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    document = _read_document_quietly(repo_path)
    document.update(fields)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=directory, delete=False
        ) as target:
            temporary = target.name
            json.dump(document, target, indent=2)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.remove(temporary)


def write_url(url, repo_path=None):
    _write_fields(repo_path, pip_index_url=url)


# -- automatic choice --

def probe(url, timeout=PROBE_TIMEOUT):
    """Seconds until ``url`` answers a simple-index request with 200, or None."""
    start = time.perf_counter()
    request = urllib.request.Request(url + "pip/", headers={"User-Agent": "pip"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                return None
            response.read(1)
    except Exception:
        return None
    return time.perf_counter() - start


def measure(urls=None, timeout=PROBE_TIMEOUT):
    """Probe every mirror in parallel; returns {url: seconds or None}."""
    urls = [url for url in (urls or PIP_INDEX_URLS) if url]
    with concurrent.futures.ThreadPoolExecutor(len(urls)) as pool:
        futures = {url: pool.submit(probe, url, timeout) for url in urls}
        return {url: future.result() for url, future in futures.items()}


def pick(timings):
    """Choose from measured timings: "" keeps pip's default (PyPI)."""
    answered = {url: seconds for url, seconds in timings.items() if seconds is not None}
    if not answered:
        return ""
    fastest = min(answered.values())
    limit = fastest * TIE_RATIO + TIE_SLACK
    tied = [url for url in PIP_INDEX_URLS if url in answered and answered[url] <= limit]
    if ALIYUN_URL in tied:
        return ALIYUN_URL
    winner = min(answered, key=answered.get)
    return "" if winner == PYPI_URL else winner


def pip_has_index_config():
    """True when the environment or pip's own config already names an index."""
    if os.environ.get("PIP_INDEX_URL"):
        return True
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "config", "list"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            encoding="utf-8", errors="replace", timeout=30, **kwargs
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return any(
        line.split("=", 1)[0].strip().endswith(".index-url")
        for line in (result.stdout or "").splitlines()
    )


def auto_url(repo_path=None, log=None, refresh=False):
    """The fastest mirror, cached for AUTO_MAX_AGE; "" means pip's default."""
    if os.environ.get(DISABLE_ENV) == "0":
        return ""
    document = _read_document_quietly(repo_path)
    cached = document.get(AUTO_KEY)
    checked = document.get(AUTO_CHECKED_KEY)
    if (not refresh and isinstance(cached, str) and cached in PIP_INDEX_URLS
            and isinstance(checked, (int, float)) and 0 <= time.time() - checked < AUTO_MAX_AGE):
        return cached
    if log is not None:
        log.info("Measuring pip mirror speed...")
    timings = measure()
    url = pick(timings)
    if log is not None:
        for name, seconds in timings.items():
            log.info("  %s: %s", name, "failed" if seconds is None else "{:.0f} ms".format(seconds * 1000))
        log.info("Using %s", url or "pip's default index")
    try:
        _write_fields(repo_path, **{AUTO_KEY: url, AUTO_CHECKED_KEY: time.time()})
    except OSError as error:
        if log is not None:
            log.warning("Could not cache the pip mirror choice: %s", error)
    return url


def forget_auto_url(repo_path=None):
    """Drop the cached automatic choice so the next install measures again."""
    try:
        _write_fields(repo_path, **{AUTO_KEY: None, AUTO_CHECKED_KEY: None})
    except OSError:
        pass
