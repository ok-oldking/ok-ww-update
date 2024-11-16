import sys

from PySide6.QtCore import Qt, QTranslator, QCoreApplication
from PySide6.QtWidgets import QApplication
from qfluentwidgets import FluentTranslator, qconfig, InfoBar, InfoBarPosition
from qfluentwidgets import (setTheme)

from ok.gui import resources
from ok.gui.common.config import cfg
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


def init_app_config():
    logger.debug(
        f'resources.qt_resource_name {resources.qt_resource_name} cfg.themeMode {cfg.themeMode.value}')
    locale = cfg.get(cfg.language).value
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)
    translator = FluentTranslator(locale)
    app.installTranslator(translator)
    translator = QTranslator(app)

    if translator.load(locale.name(), ":/i18n"):
        translator.setParent(app)
        app.installTranslator(translator)
        QCoreApplication.installTranslator(translator)
        logger.info(f"translator install success {locale}, {QCoreApplication.translate('MainWindow', 'Debug')}")
    else:
        logger.info(f"No translation available for {locale}, falling back to English/default.")
    qconfig.theme = cfg.themeMode.value
    setTheme(qconfig.theme)
    return app, locale


def get_localized_app_config(config, key):
    locale = cfg.get(cfg.language).value.name()

    if config.get(locale):
        config_dict = config.get(locale)
    else:
        config_dict = config.get('default')
    if config_dict:
        return config_dict.get(key)


def show_info_bar(window, message, title=None, error=False):
    bar = InfoBar.error if error else InfoBar.info
    title = QCoreApplication.translate('app', title)
    message = QCoreApplication.translate('app', message)
    if title is None:
        title = f"{QCoreApplication.translate('app', 'Error') if error else QCoreApplication.translate('app', 'Info')}:"
    bar(
        title=title,
        content=message,
        orient=Qt.Horizontal,
        isClosable=True,
        position=InfoBarPosition.TOP,
        duration=5000,  # won't disappear automatically
        parent=window
    )


def center_window(app, window):
    screen = app.primaryScreen()
    size = screen.size()
    # Calculate half the screen size
    half_screen_width = size.width() / 2
    half_screen_height = size.height() / 2
    window.move(half_screen_width / 2, half_screen_height / 2)
