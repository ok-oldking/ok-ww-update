"""Pip index choices shared by the API and standalone updater."""
import json
import os
import tempfile

from . import standalone

PIP_INDEX_URLS = (
    "",
    "https://pypi.org/simple/",
    "https://pypi.tuna.tsinghua.edu.cn/simple",
    "https://mirrors.aliyun.com/pypi/simple/",
    "https://mirrors.ustc.edu.cn/pypi/simple/",
    "https://repo.huaweicloud.com/repository/pypi/simple/",
    "https://mirrors.cloud.tencent.com/pypi/simple/",
)
CONFIG_FILE_NAME = "pip-index.json"


def config(url):
    return {"pip_index_url": url, "default": "", "options": list(PIP_INDEX_URLS)}


def config_path(repo_path=None):
    repo_path = standalone.find_repo_path(repo_path)
    return os.path.join(standalone.state_dir(repo_path), CONFIG_FILE_NAME)


def read_url(repo_path=None, log=None):
    """Read the saved choice, using pip defaults if the file is invalid."""
    try:
        with open(config_path(repo_path), "r", encoding="utf-8") as source:
            document = json.load(source)
    except FileNotFoundError:
        return ""
    except (ValueError, UnicodeError) as error:
        if log is not None:
            log.warning("Ignoring invalid pip-index.json; using pip defaults: %s", error)
        return ""
    url = document.get("pip_index_url") if isinstance(document, dict) else None
    if not isinstance(url, str) or url not in PIP_INDEX_URLS:
        if log is not None:
            log.warning("Ignoring invalid pip-index.json; using pip defaults")
        return ""
    return url


def write_url(url, repo_path=None):
    path = config_path(repo_path)
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=directory, delete=False
        ) as target:
            temporary = target.name
            json.dump({"pip_index_url": url}, target, indent=2)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.remove(temporary)
