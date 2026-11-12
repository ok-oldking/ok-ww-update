"""The Tk update window; see :mod:`pyappify.updater_ui` for how it is started.

Everything that touches the network or the repository runs on worker
threads. They hand results back through :meth:`UpdaterWindow.post`, which the
Tk thread drains every few milliseconds, because Tk widgets must only be used
from the thread that created them.
"""
import json
import logging
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk

from . import _state, i18n, pip_index, standalone, standalone_updater, updater_ui
from .versions import is_release_version

NUMBER_VERSIONS = 30
MAX_LOG_LINES = 5000
SUCCESS_CLOSE_SECONDS = 4
STEP_PREPARE = "prepare"

THEME_SYSTEM = "system"
THEME_LIGHT = "light"
THEME_DARK = "dark"
THEME_CYCLE = (THEME_SYSTEM, THEME_LIGHT, THEME_DARK)
THEME_ICONS = {THEME_SYSTEM: "◐", THEME_LIGHT: "☀", THEME_DARK: "☾"}

PALETTES = {
    THEME_LIGHT: {
        "bg": "#f3f4f7",
        "surface": "#ffffff",
        "surface2": "#eef0f4",
        "hover": "#e4e7ed",
        "border": "#dfe2e8",
        "text": "#1b1f27",
        "muted": "#6a7281",
        "faint": "#9aa1ad",
        "accent": "#2f6fed",
        "accent_hover": "#245dd0",
        "accent_fg": "#ffffff",
        "accent_bg": "#e6eefe",
        "select": "#dce7fd",
        "success": "#15803d",
        "success_bg": "#e3f5e9",
        "warning": "#b45309",
        "warning_bg": "#fdf1df",
        "danger": "#c62828",
        "danger_bg": "#fdeaea",
        "scroll": "#cdd2da",
        "log_bg": "#fafbfc",
    },
    THEME_DARK: {
        "bg": "#14161b",
        "surface": "#1c1f26",
        "surface2": "#262a33",
        "hover": "#2e333d",
        "border": "#2c313b",
        "text": "#e7e9ee",
        "muted": "#9aa2b1",
        "faint": "#6b7381",
        "accent": "#5b8cff",
        "accent_hover": "#77a0ff",
        "accent_fg": "#0d1220",
        "accent_bg": "#1f2a44",
        "select": "#26365a",
        "success": "#4ade80",
        "success_bg": "#16301f",
        "warning": "#fbbf24",
        "warning_bg": "#33280f",
        "danger": "#f87171",
        "danger_bg": "#3a1d20",
        "scroll": "#3a404c",
        "log_bg": "#111318",
    },
}

MIRROR_KEYS = {
    "": "mirror_default",
    "https://pypi.org/simple/": "mirror_pypi",
    "https://pypi.tuna.tsinghua.edu.cn/simple": "mirror_tuna",
    "https://mirrors.aliyun.com/pypi/simple/": "mirror_aliyun",
    "https://mirrors.ustc.edu.cn/pypi/simple/": "mirror_ustc",
    "https://repo.huaweicloud.com/repository/pypi/simple/": "mirror_huawei",
    "https://mirrors.cloud.tencent.com/pypi/simple/": "mirror_tencent",
}

KIND_KEYS = {
    standalone.KIND_BRANCH: "kind_branch",
    standalone.KIND_LOCAL: "kind_local",
    standalone.KIND_PULL: "kind_pr",
}

# Fonts with CJK glyphs, in order of preference, for languages Segoe UI and
# most Western UI fonts cannot show well.
LANGUAGE_FONTS = {
    i18n.ZH_CN: ("Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC",
                 "Noto Sans SC", "WenQuanYi Micro Hei"),
    i18n.ZH_TW: ("Microsoft JhengHei UI", "Microsoft JhengHei", "PingFang TC", "Noto Sans CJK TC",
                 "Noto Sans TC"),
    i18n.JA: ("Yu Gothic UI", "Meiryo UI", "Meiryo", "Hiragino Sans", "Noto Sans CJK JP",
              "Noto Sans JP"),
    i18n.KO: ("Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans CJK KR", "Noto Sans KR"),
}

ACTIVE = standalone_updater.STATUS_ACTIVE
DONE = standalone_updater.STATUS_DONE
SKIPPED = standalone_updater.STATUS_SKIPPED
FAILED = standalone_updater.STATUS_FAILED
PENDING = "pending"


# --- platform helpers -----------------------------------------------------------


def _enable_dpi_awareness():
    if os.name != "nt":
        return
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def system_theme():
    """``THEME_DARK`` or ``THEME_LIGHT``, from the OS setting when it can be read."""
    try:
        if os.name == "nt":
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            ) as key:
                light, _kind = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return THEME_LIGHT if light else THEME_DARK
        if sys.platform == "darwin":
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True, text=True, timeout=2,
            )
            return THEME_DARK if "dark" in result.stdout.lower() else THEME_LIGHT
        gtk_theme = os.environ.get("GTK_THEME", "").lower()
        if "dark" in gtk_theme:
            return THEME_DARK
        result = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
            capture_output=True, text=True, timeout=2,
        )
        return THEME_DARK if "dark" in result.stdout.lower() else THEME_LIGHT
    except Exception:
        return THEME_LIGHT


def _set_title_bar_dark(root, dark):
    """Match the Windows title bar to the theme (Windows 10 1809 and later)."""
    if os.name != "nt":
        return
    try:
        import ctypes

        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()
        value = ctypes.c_int(1 if dark else 0)
        for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE, before 20H1
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
            ) == 0:
                break
        # SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_FRAMECHANGED: repaint the frame.
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x1 | 0x2 | 0x4 | 0x20)
    except Exception:
        pass


def _open_path(path):
    try:
        if os.name == "nt":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


def _short(text, limit=110):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


# --- theme ----------------------------------------------------------------------


class Theme:
    """ttk styles and colors for non-ttk widgets, switchable at runtime."""

    def __init__(self, root, mode):
        self.root = root
        self.style = ttk.Style(root)
        self.style.theme_use("clam")
        self.mode = mode if mode in THEME_CYCLE else THEME_SYSTEM
        self.resolved = None
        self.colors = {}
        self._widgets = []
        self._listeners = []
        dpi = root.winfo_fpixels("1i")
        self.scale = 1.0 if sys.platform == "darwin" else max(1.0, dpi / 96.0)
        self._make_fonts()

    def px(self, value):
        return int(round(value * self.scale))

    def _make_fonts(self):
        families = set(tkfont.families(self.root))
        default = tkfont.nametofont("TkDefaultFont")
        if os.name == "nt":
            family, size = "Segoe UI", 10
        elif sys.platform == "darwin":
            family, size = default.cget("family"), 13
        else:
            family, size = default.cget("family"), 10
        mono = next(
            (name for name in ("Cascadia Mono", "Consolas", "Menlo", "SF Mono",
                               "DejaVu Sans Mono", "Liberation Mono") if name in families),
            "TkFixedFont",
        )
        self.base_family = family
        self.families = families
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
            tkfont.nametofont(name).configure(family=family, size=size)
        self.fonts = {
            "body": tkfont.nametofont("TkDefaultFont"),
            "small": tkfont.Font(self.root, family=family, size=size - 1),
            "small_bold": tkfont.Font(self.root, family=family, size=size - 1, weight="bold"),
            "bold": tkfont.Font(self.root, family=family, size=size, weight="bold"),
            "h2": tkfont.Font(self.root, family=family, size=size + 1, weight="bold"),
            "title": tkfont.Font(self.root, family=family, size=size + 6, weight="bold"),
            "app": tkfont.Font(self.root, family=family, size=size + 3, weight="bold"),
            "icon": tkfont.Font(self.root, family=family, size=size + 5, weight="bold"),
            "mono": tkfont.Font(self.root, family=mono, size=size - 1)
            if mono != "TkFixedFont" else tkfont.nametofont("TkFixedFont"),
        }

    def set_language(self, language):
        """Use a font that has the glyphs of ``language``."""
        family = next(
            (name for name in LANGUAGE_FONTS.get(language, ()) if name in self.families),
            self.base_family,
        )
        for name in ("TkTextFont", "TkMenuFont", "TkHeadingFont"):
            tkfont.nametofont(name).configure(family=family)
        for key, font in self.fonts.items():
            if key != "mono":
                font.configure(family=family)

    def register(self, widget, **roles):
        """Color ``widget`` options from palette keys, now and on every theme change."""
        self._widgets.append((widget, roles))
        if self.colors:
            self._color(widget, roles)
        return widget

    def on_change(self, callback):
        self._listeners.append(callback)

    def _color(self, widget, roles):
        try:
            widget.configure(**{option: self.colors[key] for option, key in roles.items()})
        except tk.TclError:
            pass

    def set_mode(self, mode):
        self.mode = mode
        self.apply(force=True)

    def apply(self, force=False):
        resolved = system_theme() if self.mode == THEME_SYSTEM else self.mode
        if resolved == self.resolved and not force:
            return
        self.resolved = resolved
        self.colors = dict(PALETTES[resolved])
        self._configure_styles()
        self._widgets = [(w, r) for w, r in self._widgets if _exists(w)]
        for widget, roles in self._widgets:
            self._color(widget, roles)
        for callback in list(self._listeners):
            callback()
        _set_title_bar_dark(self.root, resolved == THEME_DARK)

    def _configure_styles(self):
        c, s, px, f = self.colors, self.style, self.px, self.fonts
        self.root.configure(background=c["bg"])
        s.configure(
            ".", background=c["bg"], foreground=c["text"], bordercolor=c["border"],
            lightcolor=c["bg"], darkcolor=c["bg"], troughcolor=c["surface2"],
            focuscolor=c["accent"], selectbackground=c["select"],
            selectforeground=c["text"], fieldbackground=c["surface"],
            insertcolor=c["text"], font=f["body"],
        )
        s.map(".", foreground=[("disabled", c["faint"])])

        for name, background in (("TFrame", "bg"), ("Card.TFrame", "surface")):
            s.configure(name, background=c[background])
        labels = {
            "TLabel": ("bg", "text", "body"),
            "Card.TLabel": ("surface", "text", "body"),
            "CardMuted.TLabel": ("surface", "muted", "small"),
            "CardBold.TLabel": ("surface", "text", "bold"),
            "CardH2.TLabel": ("surface", "text", "h2"),
            "CardTitle.TLabel": ("surface", "text", "title"),
            "AppName.TLabel": ("surface", "text", "app"),
            "Success.TLabel": ("surface", "success", "bold"),
            "Danger.TLabel": ("surface", "danger", "bold"),
            "StepTitle.TLabel": ("surface", "text", "small_bold"),
            "StepFailed.TLabel": ("surface", "danger", "small_bold"),
            "StepDetail.TLabel": ("surface", "muted", "body"),
        }
        for name, (background, foreground, font) in labels.items():
            s.configure(name, background=c[background], foreground=c[foreground], font=f[font])

        pad = (px(14), px(6))
        s.configure(
            "TButton", background=c["surface2"], foreground=c["text"],
            bordercolor=c["border"], lightcolor=c["surface2"], darkcolor=c["surface2"],
            padding=pad, relief="flat", focusthickness=0, anchor="center",
        )
        s.map(
            "TButton",
            background=[("disabled", c["surface2"]), ("pressed", c["border"]), ("active", c["hover"])],
            lightcolor=[("pressed", c["border"]), ("active", c["hover"])],
            darkcolor=[("pressed", c["border"]), ("active", c["hover"])],
            bordercolor=[("focus", c["accent"])],
        )
        s.configure(
            "Accent.TButton", background=c["accent"], foreground=c["accent_fg"],
            bordercolor=c["accent"], lightcolor=c["accent"], darkcolor=c["accent"],
            font=f["bold"], padding=(px(18), px(7)),
        )
        s.map(
            "Accent.TButton",
            background=[("disabled", c["surface2"]), ("pressed", c["accent_hover"]), ("active", c["accent_hover"])],
            lightcolor=[("disabled", c["surface2"]), ("active", c["accent_hover"])],
            darkcolor=[("disabled", c["surface2"]), ("active", c["accent_hover"])],
            bordercolor=[("disabled", c["border"]), ("focus", c["text"])],
            foreground=[("disabled", c["faint"])],
        )
        s.configure(
            "Ghost.TButton", background=c["surface"], foreground=c["muted"],
            bordercolor=c["surface"], lightcolor=c["surface"], darkcolor=c["surface"],
            padding=(px(8), px(4)), width=0,
        )
        s.map(
            "Ghost.TButton",
            background=[("pressed", c["hover"]), ("active", c["surface2"])],
            lightcolor=[("active", c["surface2"])], darkcolor=[("active", c["surface2"])],
            bordercolor=[("active", c["surface2"])],
            foreground=[("active", c["text"]), ("disabled", c["faint"])],
        )

        s.configure(
            "Ghost.TMenubutton", background=c["surface"], foreground=c["muted"],
            bordercolor=c["surface"], lightcolor=c["surface"], darkcolor=c["surface"],
            arrowcolor=c["muted"], padding=(px(8), px(4)), relief="flat", width=0,
        )
        s.map(
            "Ghost.TMenubutton",
            background=[("pressed", c["hover"]), ("active", c["surface2"])],
            lightcolor=[("active", c["surface2"])], darkcolor=[("active", c["surface2"])],
            bordercolor=[("active", c["surface2"])],
            foreground=[("active", c["text"])], arrowcolor=[("active", c["text"])],
        )
        s.configure(
            "Segment.Toolbutton", background=c["surface2"], foreground=c["muted"],
            bordercolor=c["surface2"], lightcolor=c["surface2"], darkcolor=c["surface2"],
            padding=(px(12), px(4)), anchor="center", font=f["small_bold"],
        )
        s.map(
            "Segment.Toolbutton",
            background=[("selected", c["surface"]), ("active", c["hover"])],
            lightcolor=[("selected", c["surface"]), ("active", c["hover"])],
            darkcolor=[("selected", c["surface"]), ("active", c["hover"])],
            bordercolor=[("selected", c["border"])],
            foreground=[("selected", c["text"]), ("active", c["text"])],
        )

        s.layout("Clean.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        s.configure(
            "Clean.Treeview", background=c["surface"], fieldbackground=c["surface"],
            foreground=c["text"], bordercolor=c["surface"], lightcolor=c["surface"],
            darkcolor=c["surface"], rowheight=px(32), borderwidth=0, relief="flat",
        )
        s.map(
            "Clean.Treeview",
            background=[("selected", c["select"])],
            foreground=[("selected", c["text"])],
        )
        s.configure(
            "Clean.Treeview.Heading", background=c["surface"], foreground=c["muted"],
            bordercolor=c["border"], lightcolor=c["surface"], darkcolor=c["surface"],
            relief="flat", font=f["small_bold"], padding=(px(1), px(6)),
        )
        s.map("Clean.Treeview.Heading", background=[("active", c["surface"])])

        for name, color, thickness in (
            ("Accent.Horizontal.TProgressbar", c["accent"], px(6)),
            ("Thin.Horizontal.TProgressbar", c["accent"], px(3)),
            ("Success.Horizontal.TProgressbar", c["success"], px(6)),
            ("Danger.Horizontal.TProgressbar", c["danger"], px(6)),
        ):
            s.configure(
                name, troughcolor=c["surface2"], background=color, bordercolor=c["surface2"],
                lightcolor=color, darkcolor=color, thickness=thickness,
            )

        s.configure(
            "TCombobox", fieldbackground=c["surface"], background=c["surface"],
            foreground=c["text"], arrowcolor=c["muted"], bordercolor=c["border"],
            lightcolor=c["surface"], darkcolor=c["surface"], padding=(px(8), px(5)),
            selectbackground=c["surface"], selectforeground=c["text"], arrowsize=px(12),
        )
        s.map(
            "TCombobox",
            fieldbackground=[("readonly", c["surface"])],
            background=[("readonly", c["surface"]), ("active", c["surface"])],
            foreground=[("readonly", c["text"])],
            selectbackground=[("readonly", c["surface"])],
            selectforeground=[("readonly", c["text"])],
            bordercolor=[("focus", c["accent"]), ("hover", c["faint"])],
            arrowcolor=[("hover", c["text"])],
        )
        for option, value in (
            ("background", c["surface"]), ("foreground", c["text"]),
            ("selectBackground", c["select"]), ("selectForeground", c["text"]),
        ):
            self.root.option_add("*TCombobox*Listbox." + option, value)
        self.root.option_add("*TCombobox*Listbox.font", f["body"])

        for orient, sticky in (("Vertical", "ns"), ("Horizontal", "ew")):
            name = "Thin.{}.TScrollbar".format(orient)
            s.layout(name, [("{}.Scrollbar.trough".format(orient), {
                "sticky": sticky,
                "children": [("{}.Scrollbar.thumb".format(orient), {"expand": "1", "sticky": "nswe"})],
            })])
            s.configure(
                name, troughcolor=c["surface"], background=c["scroll"], bordercolor=c["surface"],
                lightcolor=c["scroll"], darkcolor=c["scroll"], arrowsize=px(9), gripcount=0,
            )
            s.map(name, background=[("active", c["faint"])],
                  lightcolor=[("active", c["faint"])], darkcolor=[("active", c["faint"])])
        s.configure("TSeparator", background=c["border"])


def _exists(widget):
    try:
        return bool(widget.winfo_exists())
    except tk.TclError:
        return False


class UiLogHandler(logging.Handler):
    """Hands log records to the window from any thread."""

    def __init__(self, post, callback):
        super().__init__(logging.INFO)
        self._post = post
        self._callback = callback

    def emit(self, record):
        try:
            self._post(self._callback, record.levelno, record.created, self.format(record))
        except Exception:
            pass


# --- building blocks ------------------------------------------------------------


class AutoScrollbar(ttk.Scrollbar):
    """A scrollbar that is only packed while there is something to scroll."""

    def __init__(self, parent, pack_options, **kwargs):
        super().__init__(parent, orient="vertical", style="Thin.Vertical.TScrollbar", **kwargs)
        self._pack_options = pack_options

    def set(self, first, last):
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.pack_forget()
        elif not self.winfo_ismapped():
            self.pack(**self._pack_options)
        super().set(first, last)


def card(parent, theme, **kwargs):
    frame = tk.Frame(parent, highlightthickness=1, bd=0, **kwargs)
    return theme.register(frame, background="surface", highlightbackground="border",
                          highlightcolor="border")


class StepRow:
    """One step of the horizontal stepper: a status icon over its title."""

    def __init__(self, parent, theme, key, title):
        self.theme = theme
        self.key = key
        self.status = PENDING
        self.detail = ""
        self.angle = 0
        px = theme.px
        self.size = px(26)
        self.frame = ttk.Frame(parent, style="Card.TFrame")
        self.canvas = tk.Canvas(self.frame, width=self.size, height=self.size,
                                highlightthickness=0, bd=0)
        theme.register(self.canvas, background="surface")
        self.canvas.pack(side="top", pady=(0, px(6)))
        self.title = ttk.Label(self.frame, text=title, style="CardMuted.TLabel", anchor="center")
        self.title.pack(side="top")
        self.draw()

    def set(self, status, detail=None):
        self.status = status
        if detail is not None:
            self.detail = str(detail)
        self.title.configure(style="CardMuted.TLabel" if status in (PENDING, SKIPPED)
                             else "StepTitle.TLabel" if status != FAILED else "StepFailed.TLabel")
        self.draw()

    def draw(self):
        c, canvas, size = self.theme.colors, self.canvas, self.size
        if not c:
            return
        canvas.delete("all")
        pad = self.theme.px(2)
        box = (pad, pad, size - pad, size - pad)
        width = self.theme.px(2)
        if self.status == PENDING:
            canvas.create_oval(*box, outline=c["border"], width=width)
        elif self.status == ACTIVE:
            canvas.create_oval(*box, outline=c["surface2"], width=width)
            canvas.create_arc(*box, start=self.angle, extent=110, style="arc",
                              outline=c["accent"], width=width)
        elif self.status == DONE:
            canvas.create_oval(*box, fill=c["success"], outline=c["success"])
            points = [size * 0.30, size * 0.52, size * 0.45, size * 0.66, size * 0.71, size * 0.37]
            canvas.create_line(*points, fill=c["surface"], width=width, capstyle="round",
                               joinstyle="round")
        elif self.status == SKIPPED:
            canvas.create_oval(*box, outline=c["faint"], width=width)
            canvas.create_line(size * 0.33, size / 2, size * 0.67, size / 2, fill=c["faint"],
                               width=width, capstyle="round")
        else:
            canvas.create_oval(*box, fill=c["danger"], outline=c["danger"])
            a, b = size * 0.36, size * 0.64
            for line in ((a, a, b, b), (a, b, b, a)):
                canvas.create_line(*line, fill=c["surface"], width=width, capstyle="round")

    def spin(self):
        if self.status == ACTIVE:
            self.angle = (self.angle - 14) % 360
            self.draw()


# --- the window -----------------------------------------------------------------


class UpdaterWindow:
    def __init__(self, root, session=None, job=None, job_path=None):
        self.root = root
        self.session = session or {}
        self.job = job
        self.job_path = job_path
        self.queue = queue.Queue()
        self.exit_event = threading.Event()
        self.preferences = updater_ui.load_preferences()
        self.theme = Theme(root, self.preferences.get("theme", THEME_SYSTEM))
        self.language = i18n.resolve_language(self.preferences.get("language"))
        self.language_var = tk.StringVar(value=self.language)
        self.theme.set_language(self.language)
        self._texts = {}
        self.update_version = None
        self.repo_path = (job or {}).get("repo_path") or self.session.get("repo_path")
        self.versions = []
        self.release_only = tk.BooleanVar(value=True)
        self.busy = 0
        self.updating = False
        self.log_path = None
        self.log_open = bool(job)
        self.problem_count = 0
        self.close_after = None
        self.steps = {}
        self._chips = []
        self._badge_danger = False
        self.ui_handler = UiLogHandler(self.post, self._append_log)
        self.ui_handler.setFormatter(logging.Formatter("%(message)s"))
        self.list_log = logging.getLogger("pyappify.updater_ui")
        self.list_log.setLevel(logging.INFO)
        self.list_log.propagate = False
        self.list_log.handlers[:] = [self.ui_handler]
        _state.pkg().logger = self.list_log

        root.title(self.tr("update"))
        px = self.theme.px
        root.geometry("{}x{}".format(px(980), px(680)))
        root.minsize(px(760), px(540))
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._build()
        self.theme.apply(force=True)
        self.theme.on_change(self._on_theme_change)
        root.after(30, self._pump)
        root.after(50, self._spin)
        if os.name == "nt":
            root.after(3000, self._follow_system_theme)

    # -- threading --

    def post(self, callback, *args):
        self.queue.put((callback, args))

    def _pump(self):
        try:
            for _ in range(500):
                callback, args = self.queue.get_nowait()
                try:
                    callback(*args)
                except tk.TclError:
                    pass
        except queue.Empty:
            pass
        self.root.after(30, self._pump)

    def run_async(self, work, on_done=None, on_error=None, busy_text=None):
        if busy_text:
            self._set_busy(1, busy_text)

        def worker():
            try:
                result = work()
            except BaseException as error:  # reported in the window
                self.post(self._finish_async, busy_text, on_error or self.show_error, error)
            else:
                self.post(self._finish_async, busy_text, on_done, result)

        threading.Thread(target=worker, name="pyappify-updater-ui", daemon=True).start()

    def _finish_async(self, busy_text, callback, value):
        if busy_text:
            self._set_busy(-1)
        if callback and not self.exit_event.is_set():
            callback(value)

    # -- layout --

    def _build(self):
        theme, px = self.theme, self.theme.px
        root = self.root

        self.header = ttk.Frame(root, style="Card.TFrame", padding=(px(20), px(14)))
        self.header.pack(side="top", fill="x")
        self.app_icon = tk.Canvas(self.header, width=px(40), height=px(40), highlightthickness=0, bd=0)
        theme.register(self.app_icon, background="surface")
        self.app_icon.grid(row=0, column=0, rowspan=2, padx=(0, px(12)))
        self.app_label = ttk.Label(self.header, text="", style="AppName.TLabel")
        self.app_label.grid(row=0, column=1, sticky="sw")
        self.installed_label = ttk.Label(self.header, text="", style="CardMuted.TLabel")
        self.installed_label.grid(row=1, column=1, sticky="nw")
        self.header.columnconfigure(2, weight=1)
        self.language_button = ttk.Menubutton(self.header, style="Ghost.TMenubutton")
        self.language_menu = tk.Menu(self.language_button, tearoff=0, bd=0,
                                     font=theme.fonts["body"])
        theme.register(self.language_menu, background="surface", foreground="text",
                       activebackground="select", activeforeground="text", selectcolor="accent")
        for code in i18n.LANGUAGES:
            self.language_menu.add_radiobutton(
                label=i18n.LANGUAGE_NAMES[code], value=code, variable=self.language_var,
                command=lambda code=code: self.set_language(code),
            )
        self.language_button.configure(menu=self.language_menu)
        self.bind_text(self.language_button, lambda: i18n.LANGUAGE_NAMES[self.language])
        self.language_button.grid(row=0, column=3, rowspan=2, sticky="e", padx=(0, px(4)))
        self.theme_button = ttk.Button(self.header, style="Ghost.TButton", command=self.cycle_theme)
        self.bind_text(self.theme_button, lambda: "{}  {}".format(
            THEME_ICONS[self.theme.mode], self.tr("theme_" + self.theme.mode)))
        self.theme_button.grid(row=0, column=4, rowspan=2, sticky="e")
        ttk.Separator(root).pack(side="top", fill="x")

        self.banner = tk.Frame(root, bd=0, highlightthickness=1)
        theme.register(self.banner, background="danger_bg", highlightbackground="danger")
        self.banner_icon = tk.Label(self.banner, text="⚠", font=theme.fonts["h2"], bd=0)
        theme.register(self.banner_icon, background="danger_bg", foreground="danger")
        self.banner_icon.pack(side="left", padx=(px(14), px(8)), pady=px(8))
        self.banner_text = tk.Label(self.banner, text="", justify="left", anchor="w", bd=0,
                                    font=theme.fonts["body"])
        theme.register(self.banner_text, background="danger_bg", foreground="text")
        self.banner_text.pack(side="left", fill="x", expand=True, pady=px(8))
        self.banner_close = tk.Label(self.banner, text="✕", cursor="hand2", bd=0,
                                     font=theme.fonts["body"])
        theme.register(self.banner_close, background="danger_bg", foreground="muted")
        self.banner_close.pack(side="right", padx=px(14))
        self.banner_close.bind("<Button-1>", lambda _event: self.hide_banner())
        self.banner.bind("<Configure>", lambda event: self.banner_text.configure(
            wraplength=max(px(200), event.width - px(90))))

        self.footer = ttk.Frame(root, style="Card.TFrame", padding=(px(20), px(12)))
        self.footer.pack(side="bottom", fill="x")
        ttk.Separator(root).pack(side="bottom", fill="x")
        self.spinner = ttk.Progressbar(self.footer, mode="indeterminate", length=px(70),
                                       style="Thin.Horizontal.TProgressbar")
        self.status_label = ttk.Label(self.footer, text="", style="CardMuted.TLabel")
        self.status_label.pack(side="left")
        self.footer_buttons = ttk.Frame(self.footer, style="Card.TFrame")
        self.footer_buttons.pack(side="right")

        self.content = ttk.Frame(root, padding=(px(16), px(14), px(16), 0))
        self.content.pack(side="top", fill="both", expand=True)
        self._build_log_panel()
        self.manager_page = self._build_manager_page() if self.job is None else None
        self.progress_page = None

    def _build_manager_page(self):
        theme, px = self.theme, self.theme.px
        page = ttk.Frame(self.content)
        page.columnconfigure(0, weight=2, uniform="cards")
        page.columnconfigure(1, weight=3, uniform="cards")
        page.rowconfigure(0, weight=1)

        left = card(page, theme)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, px(12)))
        toolbar = ttk.Frame(left, style="Card.TFrame", padding=(px(14), px(12), px(10), px(8)))
        toolbar.pack(side="top", fill="x")
        self.bind_text(ttk.Label(toolbar, style="CardH2.TLabel"), "versions").pack(side="left")
        self.refresh_button = ttk.Button(toolbar, text="⟳", width=3, style="Ghost.TButton",
                                         command=self.refresh_versions)
        self.refresh_button.pack(side="right")
        segment = tk.Frame(toolbar, bd=0, highlightthickness=0, padx=px(2), pady=px(2))
        theme.register(segment, background="surface2")
        segment.pack(side="right", padx=(0, px(6)))
        for key, value in (("releases", True), ("all", False)):
            self.bind_text(ttk.Radiobutton(
                segment, value=value, variable=self.release_only,
                style="Segment.Toolbutton", command=self.refresh_versions,
            ), key).pack(side="left")

        tree_frame = ttk.Frame(left, style="Card.TFrame", padding=(px(4), 0, px(4), px(4)))
        tree_frame.pack(side="top", fill="both", expand=True)
        self.tree = ttk.Treeview(
            tree_frame, columns=("version", "kind", "status"), show="headings",
            style="Clean.Treeview", selectmode="browse",
        )
        for column, width, stretch in (
            ("version", 150, True), ("kind", 96, False), ("status", 112, False),
        ):
            self.tree.column(column, width=px(width), minwidth=px(70), stretch=stretch, anchor="w")
        self._translate_headings()
        scrollbar = AutoScrollbar(tree_frame, {"side": "right", "fill": "y", "before": self.tree},
                                  command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._on_select())

        right = card(page, theme)
        right.grid(row=0, column=1, sticky="nsew")
        self.notes = tk.Text(right, wrap="word", bd=0, highlightthickness=0, relief="flat",
                             padx=px(22), pady=px(18), cursor="arrow", height=10, width=40,
                             font=theme.fonts["body"], spacing3=px(2))
        theme.register(self.notes, background="surface", foreground="text",
                       selectbackground="select", selectforeground="text",
                       insertbackground="surface")
        notes_scroll = AutoScrollbar(right, {"side": "right", "fill": "y", "padx": (0, px(4)),
                                             "pady": px(4), "before": self.notes},
                                     command=self.notes.yview)
        self.notes.configure(yscrollcommand=notes_scroll.set)
        self.notes.pack(side="left", fill="both", expand=True)
        self.notes.bind("<Key>", lambda event: None if event.state & 0x4 else "break")

        mirror = card(page, theme)
        mirror.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(px(12), 0))
        inner = ttk.Frame(mirror, style="Card.TFrame", padding=(px(14), px(10)))
        inner.pack(fill="x")
        texts = ttk.Frame(inner, style="Card.TFrame")
        texts.pack(side="left")
        self.bind_text(ttk.Label(texts, style="CardBold.TLabel"), "mirror_title").pack(anchor="w")
        self.bind_text(ttk.Label(texts, style="CardMuted.TLabel"), "mirror_hint").pack(anchor="w")
        self.mirror_saved = ttk.Label(inner, text="", style="Success.TLabel")
        self.mirror_saved.pack(side="right", padx=(px(10), 0))
        self.mirror_urls = list(pip_index.PIP_INDEX_URLS)
        self.mirror_box = ttk.Combobox(
            inner, state="disabled", width=52, font=theme.fonts["body"],
        )
        self._translate_mirrors()
        self.mirror_box.pack(side="right")
        self.mirror_box.bind("<<ComboboxSelected>>", lambda _event: self._on_mirror_selected())
        self._make_update_button()
        page.pack(fill="both", expand=True)
        return page

    def _build_log_panel(self):
        theme, px = self.theme, self.theme.px
        self.log_card = card(self.root, theme)
        self.log_card.pack(side="bottom", fill="x", padx=px(16), pady=(px(12), px(14)),
                           before=self.content)
        bar = ttk.Frame(self.log_card, style="Card.TFrame", padding=(px(8), px(4)))
        bar.pack(side="top", fill="x")
        self.log_toggle = ttk.Button(bar, style="Ghost.TButton", command=self.toggle_log)
        self.log_toggle.pack(side="left")
        self.log_badge = tk.Label(bar, text="", bd=0, padx=px(7), pady=0,
                                  font=theme.fonts["small_bold"])
        theme.register(self.log_badge, background="warning_bg", foreground="warning")
        self.bind_text(ttk.Button(bar, style="Ghost.TButton", command=self.open_log_file),
                       "open_log_file").pack(side="right")
        self.bind_text(ttk.Button(bar, style="Ghost.TButton", command=self.copy_log),
                       "copy").pack(side="right")
        self.log_body = ttk.Frame(self.log_card, style="Card.TFrame")
        self.log_text = tk.Text(self.log_body, height=8, wrap="word", bd=0, highlightthickness=0,
                                padx=px(14), pady=px(8), font=theme.fonts["mono"], cursor="arrow")
        theme.register(self.log_text, background="log_bg", foreground="text",
                       selectbackground="select", selectforeground="text",
                       insertbackground="log_bg")
        log_scroll = AutoScrollbar(self.log_body, {"side": "right", "fill": "y",
                                                   "before": self.log_text},
                                   command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        self.log_text.bind("<Key>", lambda event: None if event.state & 0x4 else "break")
        self._layout_log()

    def _layout_log(self):
        self.bind_text(self.log_toggle, lambda: "{}  {}".format(
            "▾" if self.log_open else "▸", self.tr("log")))
        if self.log_open:
            self.log_body.pack(side="top", fill="both", expand=True)
            self.log_text.see("end")
        else:
            self.log_body.pack_forget()

    def _on_theme_change(self):
        c, fonts = self.theme.colors, self.theme.fonts
        self._retranslate()
        self._draw_app_icon()
        indent = fonts["mono"].measure("00:00:00  ")
        for tag, color in (("time", "faint"), ("info", "text"), ("warning", "warning"),
                           ("error", "danger"), ("detail", "muted")):
            self.log_text.tag_configure(tag, foreground=c[color], lmargin2=indent)
        if self.manager_page is not None:
            self.tree.tag_configure(standalone.RELATION_CURRENT, foreground=c["success"])
            self.tree.tag_configure(standalone.RELATION_NEWER, foreground=c["accent"])
            self.tree.tag_configure(standalone.RELATION_OLDER, foreground=c["text"])
            self.tree.tag_configure(standalone.RELATION_OTHER, foreground=c["text"])
            self.notes.tag_configure("title", font=fonts["title"], spacing3=self.theme.px(6))
            self.notes.tag_configure("meta", foreground=c["muted"], font=fonts["small"])
            self.notes.tag_configure("h2", font=fonts["h2"], spacing1=self.theme.px(16),
                                     spacing3=self.theme.px(6))
            self.notes.tag_configure("bullet", lmargin1=self.theme.px(4),
                                     lmargin2=self.theme.px(20), spacing1=self.theme.px(3))
            self.notes.tag_configure("dot", foreground=c["accent"])
            self.notes.tag_configure("empty", foreground=c["muted"])
            self._render_notes()
            self._style_mirror_popdown()
        for row in self.steps.values():
            row.draw()

    def _draw_app_icon(self):
        c, px, canvas = self.theme.colors, self.theme.px, self.app_icon
        canvas.delete("all")
        size, r = px(40), px(10)
        points = [r, 0, size - r, 0, size, 0, size, r, size, size - r, size, size,
                  size - r, size, r, size, 0, size, 0, size - r, 0, r, 0, 0]
        canvas.create_polygon(points, smooth=True, fill=c["accent"], outline="")
        canvas.create_text(size / 2, size / 2, text=(self._app_name()[:1] or "A").upper(),
                           fill=c["accent_fg"], font=self.theme.fonts["icon"])

    def _style_mirror_popdown(self):
        try:
            popdown = self.root.tk.call("ttk::combobox::PopdownWindow", self.mirror_box)
            c = self.theme.colors
            self.root.tk.call(popdown + ".f.l", "configure", "-background", c["surface"],
                              "-foreground", c["text"], "-selectbackground", c["select"],
                              "-selectforeground", c["text"])
        except tk.TclError:
            pass

    # -- small UI helpers --

    # -- translation --

    def tr(self, key, **values):
        return i18n.t(key, self.language, **values)

    def bind_text(self, widget, source, **values):
        """Show ``source`` on ``widget`` and show it again in each new language.

        ``source`` is a translation key (formatted with ``values``), a callable
        returning the text, or None for no text.
        """
        if callable(source):
            producer = source
        elif source is None:
            producer = lambda: ""  # noqa: E731
        else:
            producer = lambda: self.tr(source, **values)  # noqa: E731
        self._texts[str(widget)] = (widget, producer)
        widget.configure(text=producer())
        return widget

    def set_language(self, language):
        if language not in i18n.LANGUAGES:
            return
        self.language = language
        self.language_var.set(language)
        self.preferences["language"] = language
        updater_ui.save_preferences(self.preferences)
        self.theme.set_language(language)
        self._retranslate()
        if self.manager_page is not None:
            self._render_notes()

    def _retranslate(self):
        for name, (widget, producer) in list(self._texts.items()):
            if _exists(widget):
                widget.configure(text=producer())
            else:
                del self._texts[name]
        self.root.title(self.tr("window_title", app=self._app_name()))
        if self.manager_page is not None:
            self._translate_headings()
            self._translate_mirrors()
            if self.versions:
                self._show_versions(self.versions)

    def _translate_headings(self):
        for column in ("version", "kind", "status"):
            self.tree.heading(column, text=self.tr("column_" + column.replace("kind", "type")),
                              anchor="w")

    def _translate_mirrors(self):
        current = self.mirror_box.current()
        self.mirror_box.configure(values=[self._mirror_label(url) for url in self.mirror_urls])
        if current >= 0:
            self.mirror_box.current(current)

    def _make_update_button(self):
        self.update_button = ttk.Button(self.footer_buttons, style="Accent.TButton",
                                        state="disabled", command=self.start_manager_update)
        self.bind_text(self.update_button, "update")
        self.update_button.pack(side="right")

    def _app_name(self):
        name = self.session.get("app_name")
        if not name and self.repo_path:
            path = os.path.abspath(self.repo_path)
            if os.path.basename(path) == standalone.REPO_DIR_NAME:
                path = os.path.dirname(path)
            name = os.path.basename(path)
        return name or self.tr("app")

    def _set_identity(self, installed, **values):
        name = self._app_name()
        self.root.title(self.tr("window_title", app=name))
        self.app_label.configure(text=name)
        self.bind_text(self.installed_label, installed, **values)
        self._draw_app_icon()

    def _set_busy(self, delta, status=None):
        self.busy = max(0, self.busy + delta)
        if status:
            self.set_status(status)
        if self.busy:
            if not self.spinner.winfo_ismapped():
                self.spinner.pack(side="left", padx=(0, self.theme.px(10)), before=self.status_label)
                self.spinner.start(12)
        else:
            self.spinner.stop()
            self.spinner.pack_forget()

    def set_status(self, source, **values):
        """Show a translation key (or a callable's text) in the footer."""
        self.bind_text(self.status_label, source, **values)

    def show_error(self, error, title=None, log=True):
        if isinstance(error, InterruptedError) or self.exit_event.is_set():
            return
        message = str(error) or error.__class__.__name__
        self.bind_text(self.banner_text, lambda: (self.tr(title) + "\n" if title else "") + message)
        if not self.banner.winfo_ismapped():
            self.banner.pack(side="top", fill="x", padx=self.theme.px(16),
                             pady=(self.theme.px(12), 0), before=self.content)
        if log:
            self.list_log.error("%s", message)
        self.set_status("something_wrong")

    def hide_banner(self):
        self.banner.pack_forget()

    def toggle_log(self):
        self.log_open = not self.log_open
        self._layout_log()

    def _append_log(self, level, created, message):
        text = self.log_text
        stamp = time.strftime("%H:%M:%S", time.localtime(created))
        tag = "error" if level >= logging.ERROR else "warning" if level >= logging.WARNING else "info"
        if tag == "info" and message.startswith("  "):
            tag = "detail"
        at_end = text.yview()[1] >= 0.999
        text.insert("end", stamp + "  ", ("time",))
        text.insert("end", message + "\n", (tag,))
        lines = int(text.index("end-1c").split(".")[0])
        if lines > MAX_LOG_LINES:
            text.delete("1.0", "{}.0".format(lines - MAX_LOG_LINES))
        if at_end:
            text.see("end")
        if level >= logging.WARNING:
            self.problem_count += 1
            self.bind_text(self.log_badge, lambda: self.tr("issues", count=self.problem_count))
            if level >= logging.ERROR and not self._badge_danger:
                self._badge_danger = True
                self.theme.register(self.log_badge, background="danger_bg", foreground="danger")
            if not self.log_badge.winfo_ismapped():
                self.log_badge.pack(side="left", padx=(self.theme.px(4), 0))

    def copy_log(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.log_text.get("1.0", "end-1c"))
        self.set_status("log_copied")

    def open_log_file(self):
        path = self.log_path
        if not path and self.repo_path:
            try:
                path = os.path.join(standalone.state_dir(self.repo_path), standalone.LOG_FILE_NAME)
            except Exception:
                path = None
        if path and os.path.isfile(path):
            _open_path(path)
        else:
            self.set_status("no_log")

    def cycle_theme(self):
        index = THEME_CYCLE.index(self.theme.mode)
        mode = THEME_CYCLE[(index + 1) % len(THEME_CYCLE)]
        self.preferences["theme"] = mode
        updater_ui.save_preferences(self.preferences)
        self.theme.set_mode(mode)

    def _follow_system_theme(self):
        if self.theme.mode == THEME_SYSTEM:
            self.theme.apply()
        self.root.after(3000, self._follow_system_theme)

    def _spin(self):
        for row in self.steps.values():
            row.spin()
        self.root.after(40, self._spin)

    def _clear_footer_buttons(self):
        for child in self.footer_buttons.winfo_children():
            child.destroy()

    def _footer_button(self, key, command, accent=False):
        button = ttk.Button(self.footer_buttons, command=command,
                            style="Accent.TButton" if accent else "TButton")
        self.bind_text(button, key)
        button.pack(side="right", padx=(self.theme.px(8), 0))
        return button

    # -- manager: versions --

    def start_manager(self):
        def load():
            repo_path = self.repo_path or standalone.find_repo_path()
            version, ref = standalone.detect_app_checkout(standalone.app_files_dir(repo_path))
            return {
                "repo_path": repo_path,
                "version": self.session.get("app_version") or version,
                "ref": ref,
                "mirror": pip_index.read_url(repo_path, log=self.list_log),
            }

        self._set_identity("looking_for_app")
        self.run_async(load, self._on_loaded,
                       lambda error: self.show_error(error, "cannot_read_repository"),
                       busy_text="opening_repository")

    def _on_loaded(self, info):
        self.repo_path = info["repo_path"]
        version, ref = info["version"], info["ref"]

        def installed():
            text = version or self.tr("untagged_commit")
            if ref and ref != version:
                text = "{} · {}".format(text, ref)
            return self.tr("installed_version", version=text)

        self._set_identity(installed)
        self.mirror_box.configure(state="readonly")
        self._select_mirror(info["mirror"])
        self.refresh_versions()

    def refresh_versions(self):
        if not self.repo_path or self.updating:
            return
        release_only = bool(self.release_only.get())
        repo_path = self.repo_path
        self.refresh_button.state(["disabled"])

        def local():
            return standalone.list_versions(repo_path, NUMBER_VERSIONS, release_only,
                                            language=self.language)

        def remote():
            return standalone.get_version_list(
                NUMBER_VERSIONS, release_only, timeout=120,
                exit_event=self.exit_event, repo_path=repo_path, language=self.language,
            )

        def show_local(versions):
            if release_only == bool(self.release_only.get()):
                self._show_versions(versions)

        def show_remote(versions):
            self.refresh_button.state(["!disabled"])
            if release_only == bool(self.release_only.get()):
                self._show_versions(versions)
                newer = [v for v in versions if v.get("relation") == standalone.RELATION_NEWER]
                if newer:
                    self.set_status("newer_available", count=len(newer))
                else:
                    self.set_status("up_to_date")

        def remote_failed(error):
            self.refresh_button.state(["!disabled"])
            self.show_error(error, "check_failed")

        self.run_async(local, show_local, lambda error: None)
        self.run_async(remote, show_remote, remote_failed, busy_text="checking_for_updates")

    def _show_versions(self, versions):
        selected = self._selected_version()
        self.versions = versions
        self.tree.delete(*self.tree.get_children())
        for index, entry in enumerate(versions):
            relation = entry.get("relation") or standalone.RELATION_OTHER
            self.tree.insert("", "end", iid=str(index), tags=(relation,), values=(
                entry.get("title") or entry["version"],
                self._kind_label(entry),
                self.tr("relation_" + relation),
            ))
        pick = None
        if selected:
            pick = next((i for i, e in enumerate(versions) if e["version"] == selected["version"]
                         and e.get("kind") == selected.get("kind")), None)
        if pick is None:
            for relation in (standalone.RELATION_NEWER, standalone.RELATION_CURRENT):
                pick = next((i for i, e in enumerate(versions) if e.get("relation") == relation
                             and e.get("kind", standalone.KIND_TAG) == standalone.KIND_TAG), None)
                if pick is not None:
                    break
        if pick is None and versions:
            pick = 0
        if pick is not None:
            self.tree.selection_set(str(pick))
            self.tree.see(str(pick))
        self._on_select()

    def _kind_label(self, entry):
        kind = entry.get("kind") or standalone.KIND_TAG
        if kind == standalone.KIND_TAG:
            release = is_release_version(entry["version"])
            return self.tr("kind_release" if release else "kind_prerelease")
        return self.tr(KIND_KEYS[kind]) if kind in KIND_KEYS else kind

    def _selected_version(self):
        selection = self.tree.selection() if self.manager_page is not None else ()
        if not selection:
            return None
        index = int(selection[0])
        return self.versions[index] if index < len(self.versions) else None

    def _on_select(self):
        self._render_notes()
        entry = self._selected_version()
        if not entry or self.updating:
            self.bind_text(self.update_button, "update")
            self.update_button.configure(state="disabled")
            return
        relation = entry.get("relation")
        label = entry.get("title") if entry.get("kind") == standalone.KIND_PULL else entry["version"]
        key = {
            standalone.RELATION_NEWER: "update_to",
            standalone.RELATION_OLDER: "downgrade_to",
            standalone.RELATION_CURRENT: "is_installed",
        }.get(relation, "switch_to")
        self.bind_text(self.update_button, key, version=_short(label, 40))
        self.update_button.configure(
            state="disabled" if relation == standalone.RELATION_CURRENT else "normal")

    def _render_notes(self):
        if self.manager_page is None:
            return
        text, c, px = self.notes, self.theme.colors, self.theme.px
        text.delete("1.0", "end")
        for chip in self._chips:
            chip.destroy()
        self._chips = []
        entry = self._selected_version()
        if not entry:
            text.insert("end", self.tr("select_version"), ("empty",))
            return
        text.insert("end", (entry.get("title") or entry["version"]) + "\n", ("title",))
        relation = entry.get("relation")
        chips = [(self._kind_label(entry), "surface2", "muted")]
        if relation == standalone.RELATION_CURRENT:
            chips.insert(0, (self.tr("chip_installed"), "success_bg", "success"))
        elif relation == standalone.RELATION_NEWER:
            chips.insert(0, (self.tr("chip_newer"), "accent_bg", "accent"))
        elif relation == standalone.RELATION_OLDER:
            chips.insert(0, (self.tr("chip_older"), "warning_bg", "warning"))
        for label, background, foreground in chips:
            chip = tk.Label(text, text=label, bd=0, padx=px(8), pady=px(1),
                            font=self.theme.fonts["small_bold"],
                            background=c[background], foreground=c[foreground])
            self._chips.append(chip)
            text.window_create("end", window=chip, padx=px(2))
            text.insert("end", " ")
        meta = []
        if entry.get("commit"):
            meta.append(self.tr("meta_commit", commit=entry["commit"][:10]))
        if entry.get("previous_version"):
            meta.append(self.tr("meta_previous", version=entry["previous_version"]))
        if meta:
            text.insert("end", "   " + "  ·  ".join(meta), ("meta",))
        text.insert("end", "\n")

        kind = entry.get("kind") or standalone.KIND_TAG
        if kind == standalone.KIND_TAG and entry.get("previous_version"):
            heading = self.tr("changes_since", version=entry["previous_version"])
        elif kind == standalone.KIND_TAG:
            heading = self.tr("whats_in_version")
        else:
            heading = self.tr("changes_vs_installed")
        text.insert("end", heading + "\n", ("h2",))
        notes = (entry.get("localized_notes") or {}).get(self.language) or entry.get("update_note")
        notes = [str(note) for note in notes or [] if str(note).strip()]
        if not notes:
            text.insert("end", self.tr("no_notes"), ("empty",))
        for note in notes:
            text.insert("end", "●  ", ("bullet", "dot"))
            text.insert("end", note.lstrip("-*• ") + "\n", ("bullet",))

    # -- manager: pip mirror --

    def _mirror_label(self, url):
        name = self.tr(MIRROR_KEYS[url]) if url in MIRROR_KEYS else url
        if not url:
            return name
        host = url.split("://", 1)[-1].split("/", 1)[0]
        return "{}  —  {}".format(name, host)

    def _select_mirror(self, url):
        index = self.mirror_urls.index(url) if url in self.mirror_urls else 0
        self.mirror_box.current(index)
        self._current_mirror = self.mirror_urls[index]

    def _on_mirror_selected(self):
        self.mirror_box.selection_clear()
        url = self.mirror_urls[self.mirror_box.current()]
        if url == getattr(self, "_current_mirror", None):
            return
        repo_path = self.repo_path

        def saved(_result):
            self._current_mirror = url
            self.list_log.info("Pip mirror set to %s", url or "pip's default")
            self.bind_text(self.mirror_saved, "mirror_saved")
            self.root.after(2500, lambda: self.bind_text(self.mirror_saved, None))

        def failed(error):
            self._select_mirror(self._current_mirror)
            self.show_error(error, "mirror_failed")

        self.run_async(lambda: pip_index.write_url(url, repo_path), saved, failed)

    # -- updating --

    def start_manager_update(self):
        entry = self._selected_version()
        if not entry or self.updating:
            return
        pid = self.session.get("pid")
        if pid:
            label = entry.get("title") or entry["version"]
            if not messagebox.askokcancel(
                self.tr("confirm_title", app=self._app_name()),
                self.tr("confirm_body", app=self._app_name(), version=label),
                parent=self.root,
            ):
                return
        self._begin_update(entry["version"], entry.get("previous_version"), prepare=True)
        version = entry["version"]
        session, repo_path = self.session, self.repo_path

        def work():
            log = self._job_logger(repo_path)
            progress = self._progress_callback()
            progress(STEP_PREPARE, ACTIVE)
            try:
                job = standalone.prepare_update_job(
                    version,
                    timeout=300,
                    app_version=session.get("app_version"),
                    app_profile=session.get("app_profile"),
                    repo_path=repo_path,
                    pid=session.get("pid"),
                    relaunch=session.get("relaunch"),
                    exit_timeout=session.get("exit_timeout", updater_ui.APP_EXIT_TIMEOUT_SECONDS),
                    language=self.language,
                )
            except Exception as error:
                log.error("Could not prepare the update to %s: %s", version, error)
                progress(STEP_PREPARE, FAILED, str(error))
                raise
            progress(STEP_PREPARE, DONE)
            return self._run_job(job, log, progress)

        self.run_async(work, self._on_update_finished, self._on_update_failed)

    def start_job(self):
        job = self.job
        self.repo_path = job["repo_path"]
        self._set_identity("installed_version",
                           version=job.get("previous_version") or job["previous_commit"][:12])
        self._begin_update(job["version"], job.get("previous_version"), prepare=False)

        def work():
            log = self._job_logger(job["repo_path"], os.path.dirname(self.job_path))
            try:
                return self._run_job(job, log, self._progress_callback())
            finally:
                updater_ui._remove(self.job_path)

        self.run_async(work, self._on_update_finished, self._on_update_failed)

    def _job_logger(self, repo_path, directory=None):
        directory = directory or standalone.state_dir(repo_path)
        self.log_path = os.path.join(directory, standalone.LOG_FILE_NAME)
        log = standalone_updater._setup_logging(self.log_path, console=False)
        log.addHandler(self.ui_handler)
        _state.pkg().logger = log
        return log

    def _run_job(self, job, log, progress):
        try:
            return standalone_updater.run_job(job, log, progress)
        except Exception:
            log.exception("Update failed unexpectedly.")
            return False

    def _progress_callback(self):
        def progress(step, status, detail=None):
            self.post(self._on_progress, step, status, detail)
        return progress

    def _begin_update(self, version, previous, prepare):
        px = self.theme.px
        self.updating = True
        self.update_version = version
        self.hide_banner()
        if self.manager_page is not None:
            self.manager_page.pack_forget()
        self._clear_footer_buttons()
        page = ttk.Frame(self.content)
        page.pack(fill="both", expand=True)
        self.progress_page = page
        panel = card(page, self.theme)
        panel.pack(fill="both", expand=True)
        inner = ttk.Frame(panel, style="Card.TFrame", padding=(px(28), px(22)))
        inner.pack(fill="both", expand=True)
        self.progress_title = ttk.Label(inner, style="CardTitle.TLabel")
        self.bind_text(self.progress_title, "updating_to", version=version)
        self.progress_title.pack(anchor="w")
        self.progress_subtitle = ttk.Label(inner, style="CardMuted.TLabel")
        if previous:
            self.bind_text(self.progress_subtitle, "from_version", version=previous)
        else:
            self.bind_text(self.progress_subtitle, "keep_window_open")
        self.progress_subtitle.pack(anchor="w", pady=(px(2), px(18)))
        self.progress_bar = ttk.Progressbar(inner, mode="determinate", maximum=100,
                                            style="Accent.Horizontal.TProgressbar")
        self.progress_bar.pack(fill="x", pady=(0, px(18)))
        steps = ((STEP_PREPARE,) if prepare else ()) + standalone_updater.STEPS
        self.step_order = list(steps)
        self.steps = {}
        self.steps_frame = ttk.Frame(inner, style="Card.TFrame")
        self.steps_frame.pack(fill="x")
        for column, key in enumerate(steps + (standalone_updater.STEP_ROLLBACK,)):
            row = StepRow(self.steps_frame, self.theme, key, "")
            self.bind_text(row.title, "step_" + key)
            self.steps_frame.columnconfigure(column, weight=1, uniform="steps")
            if key != standalone_updater.STEP_ROLLBACK:
                row.frame.grid(row=0, column=column, sticky="n")
            self.steps[key] = row
        self.step_detail = ttk.Label(inner, style="StepDetail.TLabel")
        self.bind_text(self.step_detail, None)
        self.step_detail.pack(anchor="w", pady=(px(18), 0))
        if not self.log_open:
            self.toggle_log()
        self.set_status("updating_status")
        self._set_busy(1)

    def _on_progress(self, step, status, detail):
        row = self.steps.get(step)
        if row is None:
            return
        if step == standalone_updater.STEP_ROLLBACK and not row.frame.winfo_ismapped():
            row.frame.grid(row=0, column=len(self.step_order), sticky="n")
        row.set(status, detail)
        if status == ACTIVE:
            if detail and detail.startswith(standalone_updater.PIP_PROGRESS_PREFIXES):
                # pip's own output stays as pip wrote it.
                self.bind_text(self.step_detail, lambda: _short(detail))
            elif step != standalone_updater.STEP_DEPENDENCIES or not self._showing_pip():
                self.bind_text(self.step_detail, "detail_" + step, version=self.update_version)
        elif status == FAILED:
            self.bind_text(self.step_detail, None)
        finished = sum(1 for key in self.step_order if self.steps[key].status in (DONE, SKIPPED))
        active = any(self.steps[key].status == ACTIVE for key in self.step_order)
        value = (finished + (0.5 if active else 0)) / float(len(self.step_order)) * 100
        self.progress_bar.configure(value=max(self.progress_bar.cget("value"), value))

    def _showing_pip(self):
        return self.step_detail.cget("text").startswith(standalone_updater.PIP_PROGRESS_PREFIXES)

    def _on_update_finished(self, succeeded):
        self.updating = False
        self._set_busy(-1)
        version = self.update_version
        if not succeeded:
            failed = next((row for row in self.steps.values() if row.status == FAILED), None)
            reason = failed.detail if failed else ""
            self._on_update_failed(RuntimeError(reason or self.tr("see_log")))
            return
        self.progress_bar.configure(value=100, style="Success.Horizontal.TProgressbar")
        self.bind_text(self.progress_title, "updated_to", version=version)
        self.bind_text(self.installed_label, "installed_version", version=version)
        self.bind_text(self.step_detail, None)
        restarted = self.steps[standalone_updater.STEP_RESTART].status == DONE
        self.bind_text(self.progress_subtitle, "app_restarting" if restarted else "start_app_again")
        self.progress_subtitle.configure(style="Success.TLabel")
        self._clear_footer_buttons()
        self._footer_button("close", self.root.destroy, accent=True)
        keep = self._footer_button("keep_open", None)
        keep.configure(command=lambda: self._cancel_close(keep))
        self._countdown(SUCCESS_CLOSE_SECONDS)

    def _countdown(self, seconds):
        if seconds <= 0:
            self.root.destroy()
            return
        self.set_status("closing_in", seconds=seconds)
        self.close_after = self.root.after(1000, self._countdown, seconds - 1)

    def _cancel_close(self, button):
        if self.close_after:
            self.root.after_cancel(self.close_after)
            self.close_after = None
        button.destroy()
        self.set_status("update_complete")

    def _on_update_failed(self, error):
        if self.updating:
            self.updating = False
            self._set_busy(-1)
        self.progress_bar.configure(style="Danger.Horizontal.TProgressbar")
        self.bind_text(self.progress_title, "update_failed_to", version=self.update_version)
        self.bind_text(self.step_detail, None)
        rolled_back = self.steps[standalone_updater.STEP_ROLLBACK].status == DONE
        prepare_failed = (self.steps.get(STEP_PREPARE) is not None
                          and self.steps[STEP_PREPARE].status == FAILED)
        self.bind_text(self.progress_subtitle, "previous_restored" if rolled_back
                       else "nothing_changed" if prepare_failed else "check_log_below")
        self.progress_subtitle.configure(style="Danger.TLabel")
        self.show_error(error, "update_failed", log=False)
        self._clear_footer_buttons()
        self._footer_button("close", self.root.destroy, accent=self.manager_page is None)
        if self.manager_page is not None:
            self._footer_button("back_to_versions", self._back_to_manager, accent=True)

    def _back_to_manager(self):
        self.hide_banner()
        self.progress_page.destroy()
        self.progress_page = None
        self.steps = {}
        self._clear_footer_buttons()
        self._make_update_button()
        self.manager_page.pack(fill="both", expand=True)
        self.refresh_versions()

    def on_close(self):
        if self.updating:
            messagebox.showinfo(self.tr("in_progress_title"), self.tr("in_progress_body"),
                                parent=self.root)
            return
        self.exit_event.set()
        self.root.destroy()


# --- entry points -----------------------------------------------------------------


def _create_root():
    _enable_dpi_awareness()
    root = tk.Tk()
    root.withdraw()
    return root


def _show(root):
    root.update_idletasks()
    width, height = root.winfo_width(), root.winfo_height()
    x = max(0, (root.winfo_screenwidth() - width) // 2)
    y = max(0, (root.winfo_screenheight() - height) // 3)
    root.geometry("+{}+{}".format(x, y))
    root.deiconify()
    root.lift()
    root.focus_force()


def run_manager(session):
    root = _create_root()
    window = UpdaterWindow(root, session=session)
    _show(root)
    window.start_manager()
    root.mainloop()
    return 0


def run_job_window(job_path):
    """Show the progress of ``job_path``; raises TclError before the job starts without a display."""
    root = _create_root()
    with open(job_path, "r", encoding="utf-8") as job_file:
        job = json.load(job_file)
    window = UpdaterWindow(root, job=job, job_path=job_path)
    result = {"code": 1}
    original = window._on_update_finished

    def finished(succeeded):
        result["code"] = 0 if succeeded else 1
        original(succeeded)

    window._on_update_finished = finished
    _show(root)
    window.start_job()
    root.mainloop()
    return result["code"]
