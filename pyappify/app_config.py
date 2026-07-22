import atexit
import json
import logging
import os
import tempfile
import threading


UPDATE_METHOD_MANUAL = "MANUAL_UPDATE"
UPDATE_METHOD_AUTO = "AUTO_UPDATE"
UPDATE_METHOD_AUTO_PRE_RELEASE = "AUTO_UPDATE_PRE_RELEASE"
UPDATE_METHODS = {
    UPDATE_METHOD_MANUAL,
    UPDATE_METHOD_AUTO,
    UPDATE_METHOD_AUTO_PRE_RELEASE,
}

_UNSET = object()
_LOG = logging.getLogger("pyappify.app_config")


class AppConfigAPI:
    """Thread-safe access to the app preferences stored by PyAppify."""

    def __init__(self, path=None, watch=False, watch_interval=0.5):
        self._lock = threading.RLock()
        self._path = None
        self._preferences = {
            "auto_start": False,
            "update_method": UPDATE_METHOD_AUTO,
        }
        self._listeners = set()
        self._watch_interval = watch_interval
        self._watch_stop = None
        self._watch_thread = None
        if path:
            self.configure(path, watch=watch, watch_interval=watch_interval)

    @property
    def path(self):
        with self._lock:
            return self._path

    def configure(self, path, watch=True, watch_interval=0.5):
        self.stop_watcher()
        normalized_path = os.path.abspath(os.path.expanduser(path)) if path else None
        with self._lock:
            self._path = normalized_path
            self._watch_interval = watch_interval
            self._preferences = {
                "auto_start": False,
                "update_method": UPDATE_METHOD_AUTO,
            }
        if normalized_path:
            self.refresh(notify=False)
            if watch:
                self.start_watcher()
        return normalized_path

    def _read_document(self):
        path = self.path
        if not path:
            raise RuntimeError("PYAPPIFY_APP_JSON_PATH is not configured")
        with open(path, "r", encoding="utf-8") as config_file:
            document = json.load(config_file)
        if not isinstance(document, dict):
            raise ValueError("app.json must contain a JSON object")
        return document

    @staticmethod
    def _preferences_from_document(document):
        auto_start = document.get("auto_start", False)
        update_method = document.get("update_method", UPDATE_METHOD_AUTO)
        if not isinstance(auto_start, bool):
            raise ValueError("auto_start must be a boolean")
        if not isinstance(update_method, str) or update_method not in UPDATE_METHODS:
            raise ValueError("Unsupported update_method: {}".format(update_method))
        return {
            "auto_start": auto_start,
            "update_method": update_method,
        }

    def _store_preferences(self, preferences, notify=True):
        with self._lock:
            changed = preferences != self._preferences
            self._preferences = dict(preferences)
            listeners = tuple(self._listeners) if changed and notify else ()
            result = dict(self._preferences)
        for listener in listeners:
            try:
                listener(dict(result))
            except Exception:
                _LOG.exception("An app config listener failed")
        return result

    def refresh(self, notify=True):
        with self._lock:
            preferences = self._preferences_from_document(self._read_document())
        return self._store_preferences(preferences, notify=notify)

    def get(self, refresh=True):
        if refresh and self.path:
            return self.refresh()
        with self._lock:
            return dict(self._preferences)

    def update(self, auto_start=_UNSET, update_method=_UNSET):
        if auto_start is not _UNSET and not isinstance(auto_start, bool):
            raise ValueError("auto_start must be a boolean")
        if update_method is not _UNSET and (
            not isinstance(update_method, str) or update_method not in UPDATE_METHODS
        ):
            raise ValueError("Unsupported update_method: {}".format(update_method))

        with self._lock:
            document = self._read_document()
            if auto_start is not _UNSET:
                document["auto_start"] = auto_start
            if update_method is not _UNSET:
                document["update_method"] = update_method
            preferences = self._preferences_from_document(document)
            config_dir = os.path.dirname(self._path) or os.curdir
            temporary_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=config_dir,
                    prefix=".app-json-",
                    suffix=".tmp",
                    delete=False,
                ) as temporary_file:
                    temporary_path = temporary_file.name
                    json.dump(document, temporary_file, indent=2, ensure_ascii=False)
                    temporary_file.write("\n")
                    temporary_file.flush()
                    os.fsync(temporary_file.fileno())
                os.replace(temporary_path, self._path)
                temporary_path = None
            finally:
                if temporary_path and os.path.exists(temporary_path):
                    os.unlink(temporary_path)
        return self._store_preferences(preferences)

    def add_listener(self, listener):
        if not callable(listener):
            raise TypeError("listener must be callable")
        with self._lock:
            self._listeners.add(listener)
        return listener

    def remove_listener(self, listener):
        with self._lock:
            self._listeners.discard(listener)

    def start_watcher(self):
        with self._lock:
            if not self._path:
                raise RuntimeError("PYAPPIFY_APP_JSON_PATH is not configured")
            if self._watch_thread and self._watch_thread.is_alive():
                return self._watch_thread
            stop_event = threading.Event()
            self._watch_stop = stop_event
            thread = threading.Thread(
                target=self._watch_loop,
                args=(stop_event,),
                name="pyappify-app-config-watch",
                daemon=True,
            )
            self._watch_thread = thread
            thread.start()
            return thread

    def stop_watcher(self):
        with self._lock:
            stop_event = self._watch_stop
            thread = self._watch_thread
            self._watch_stop = None
            self._watch_thread = None
        if stop_event:
            stop_event.set()
        if thread and thread is not threading.current_thread():
            thread.join(timeout=max(1.0, self._watch_interval * 2))

    def _watch_loop(self, stop_event):
        while not stop_event.wait(self._watch_interval):
            try:
                self.refresh()
            except (OSError, ValueError, json.JSONDecodeError):
                _LOG.exception("Failed to refresh app preferences from %s", self.path)


_api = AppConfigAPI()


def configure_app_json(path=None, watch=True, watch_interval=0.5):
    return _api.configure(path, watch=watch, watch_interval=watch_interval)


def get_app_json_path():
    return _api.path


def get_app_config():
    return _api.get()


def update_app_config(auto_start=_UNSET, update_method=_UNSET):
    return _api.update(auto_start=auto_start, update_method=update_method)


def get_auto_start():
    return get_app_config()["auto_start"]


def set_auto_start(auto_start):
    return update_app_config(auto_start=auto_start)["auto_start"]


def get_update_method():
    return get_app_config()["update_method"]


def set_update_method(update_method):
    return update_app_config(update_method=update_method)["update_method"]


def add_app_config_listener(listener):
    return _api.add_listener(listener)


def remove_app_config_listener(listener):
    _api.remove_listener(listener)


def start_app_config_watcher():
    return _api.start_watcher()


def stop_app_config_watcher():
    _api.stop_watcher()


atexit.register(stop_app_config_watcher)
