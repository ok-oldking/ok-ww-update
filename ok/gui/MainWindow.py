from PySide6.QtCore import Signal, Qt, QEvent, QSize, QCoreApplication
from PySide6.QtGui import QScreen
from PySide6.QtWidgets import QMenu, QSystemTrayIcon
from qfluentwidgets import FluentIcon, NavigationItemPosition, MSFluentWindow, InfoBar, InfoBarPosition, MessageBox

from ok import Config
from ok import ConfigOption
from ok import Logger
from ok import init_class_by_name
from ok import og
from ok.gui.Communicate import communicate
from ok.gui.about.AboutTab import AboutTab
from ok.gui.act.ActTab import ActTab
from ok.gui.debug.DebugTab import DebugTab
from ok.gui.settings.SettingTab import SettingTab
from ok.gui.start.StartTab import StartTab
from ok.gui.tasks.OneTimeTaskTab import OneTimeTaskTab
from ok.gui.tasks.TriggerTaskTab import TriggerTaskTab
from ok.gui.util.Alert import alert_error
from ok.gui.util.app import show_info_bar
from ok.gui.widget.StartLoadingDialog import StartLoadingDialog

auto_start_config_option = ConfigOption('Auto Start Game', {
    'Auto Start Game When App Starts': False
}, icon=FluentIcon.GAME)

logger = Logger.get_logger(__name__)


class MainWindow(MSFluentWindow):
    act = Signal()

    def __init__(self, app, config, ok_config, icon, title, version, debug=False, about=None, exit_event=None):
        super().__init__()
        logger.info('main window __init__')
        self.app = app
        self.ok_config = ok_config
        self.auto_start_config = og.executor.global_config.get_config(auto_start_config_option)
        self.main_window_config = Config('main_window', {'last_version': 'v0.0.0'})
        self.original_layout = None
        self.exit_event = exit_event
        self.start_tab = StartTab(exit_event)
        self.onetime_tab = None
        self.trigger_tab = None
        self.emulator_starting_dialog = None
        og.set_dpi_scaling(self)
        self.do_not_quit = False

        self.act.connect(self.show_act)

        self.addSubInterface(self.start_tab, FluentIcon.PLAY, self.tr('Capture'))

        if len(og.executor.onetime_tasks) > 0:
            self.onetime_tab = OneTimeTaskTab()
            self.first_task_tab = self.onetime_tab
            self.addSubInterface(self.onetime_tab, FluentIcon.BOOK_SHELF, self.tr('Tasks'))
        if len(og.executor.trigger_tasks) > 0:
            self.trigger_tab = TriggerTaskTab()
            if self.first_task_tab is None:
                self.first_task_tab = self.trigger_tab
            self.addSubInterface(self.trigger_tab, FluentIcon.ROBOT, self.tr('Triggers'))

        if custom_tabs := config.get('custom_tabs'):
            for tab in custom_tabs:
                tab_obj = init_class_by_name(tab[0], tab[1])
                tab_obj.executor = og.executor
                self.addSubInterface(tab_obj, tab_obj.icon, tab_obj.name)

        if debug:
            debug_tab = DebugTab(config, exit_event)
            self.addSubInterface(debug_tab, FluentIcon.DEVELOPER_TOOLS, self.tr('Debug'),
                                 position=NavigationItemPosition.BOTTOM)

        self.about_tab = AboutTab(config, self.app.updater)
        self.addSubInterface(self.about_tab, FluentIcon.QUESTION, self.tr('About'),
                             position=NavigationItemPosition.BOTTOM)

        if config.get('auth'):
            self.act_tab = ActTab(config)
            self.addSubInterface(self.act_tab, FluentIcon.CERTIFICATE, self.tr('激活'),
                                 position=NavigationItemPosition.BOTTOM)

        setting_tab = SettingTab()
        self.addSubInterface(setting_tab, FluentIcon.SETTING, self.tr('Settings'),
                             position=NavigationItemPosition.BOTTOM)

        # Styling the tabs and content if needed, for example:
        dev = self.tr('Debug')
        release = self.tr('Release')
        self.setWindowTitle(f'{title} {version} {dev if debug else release}')

        communicate.executor_paused.connect(self.executor_paused)
        communicate.tab.connect(self.navigate_tab)
        communicate.task_done.connect(self.activateWindow)
        communicate.must_update.connect(self.must_update)

        # Create a context menu for the tray
        menu = QMenu()
        exit_action = menu.addAction(self.tr("Exit"))
        exit_action.triggered.connect(self.tray_quit)

        self.tray = QSystemTrayIcon(icon, parent=self)

        # Set the context menu and show the tray icon
        self.tray.setContextMenu(menu)
        self.tray.show()
        self.tray.setToolTip(title)

        # if og.device_manager.config.get("preferred") is None or self.onetime_tab is None:
        #     self.switchTo(self.start_tab)

        communicate.capture_error.connect(self.capture_error)
        communicate.notification.connect(self.show_notification)
        communicate.config_validation.connect(self.config_validation)
        communicate.starting_emulator.connect(self.starting_emulator)
        if self.about_tab is not None and version != self.main_window_config.get('last_version'):
            logger.info(f'first run show about tab last version:{self.main_window_config.get("last_version")}')
            self.main_window_config['last_version'] = version
            self.switchTo(self.about_tab)
        og.handler.post(self.do_check_auth, delay=20 * 60)
        logger.info('main window __init__ done')

    def tray_quit(self):
        logger.info('main window tray_quit')
        self.app.quit()

    def must_update(self):
        logger.info('must_update show_window')
        title = self.tr('Update')
        content = QCoreApplication.translate('app', 'The current version {} must be updated').format(
            og.app.updater.starting_version)
        w = MessageBox(title, content, self.window())
        og.executor.pause()
        if w.exec():
            logger.info('Yes button is pressed')
            og.app.updater.run()
        else:
            logger.info('No button is pressed')
            self.app.quit()

    def showEvent(self, event):
        if event.type() == QEvent.Show:
            logger.info("Window has fully displayed")
            communicate.start_success.emit()
            if self.auto_start_config.get('Auto Start Game When App Starts'):
                og.app.start_controller.start()
        super().showEvent(event)

    def set_window_size(self, width, height, min_width, min_height):
        screen = QScreen.availableGeometry(self.screen())
        if (self.ok_config['window_width'] > 0 and self.ok_config['window_height'] > 0 and
                self.ok_config['window_y'] > 0 and self.ok_config['window_x'] > 0):
            x, y, width, height = (self.ok_config['window_x'], self.ok_config['window_y'],
                                   self.ok_config['window_width'], self.ok_config['window_height'])
            if self.ok_config['window_maximized']:
                self.setWindowState(Qt.WindowMaximized)
            else:
                self.setGeometry(x, y, width, height)
        else:
            x = int((screen.width() - width) / 2)
            y = int((screen.height() - height) / 2)
            self.setGeometry(x, y, width, height)

        self.setMinimumSize(QSize(min_width, min_height))

    def do_check_auth(self):
        auth_result, result = og.app.check_auth()
        if not auth_result:
            if not result or result.code == 401:  # no local key or remote check error
                logger.debug(f'auth failed')
                self.do_not_quit = True
                self.act.emit()
                return
        logger.debug(f'auth ok')
        og.handler.post(self.do_check_auth, delay=20 * 60)

    def show_act(self):
        self.close()
        from ok.gui.widget.ActWindow import ActWindow
        act_window = ActWindow(og.app.icon)
        act_window.show()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Resize or event.type() == QEvent.Move:
            og.handler.post(self.update_ok_config, remove_existing=True, skip_if_running=True, delay=1)
        return super().eventFilter(obj, event)

    def update_ok_config(self):
        if self.isMaximized():
            self.ok_config['window_maximized'] = True
        else:
            self.ok_config['window_maximized'] = False
            geometry = self.geometry()
            self.ok_config['window_x'] = geometry.x()
            self.ok_config['window_y'] = geometry.y()
            self.ok_config['window_width'] = geometry.width()
            self.ok_config['window_height'] = geometry.height()
        logger.info(f'Window geometry updated in ok_config {self.ok_config}')

    def starting_emulator(self, done, error, seconds_left):
        if error:
            self.switchTo(self.start_tab)
            alert_error(error, True)
        if done:
            if self.emulator_starting_dialog:
                self.emulator_starting_dialog.close()
        else:
            if self.emulator_starting_dialog is None:
                self.emulator_starting_dialog = StartLoadingDialog(seconds_left,
                                                                   self)
            else:
                self.emulator_starting_dialog.set_seconds_left(seconds_left)
            self.emulator_starting_dialog.show()

    def config_validation(self, message):
        title = self.tr('Error')
        InfoBar.error(
            title=title,
            content=message,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=5000,  # won't disappear automatically
            parent=self.window()
        )
        self.tray.showMessage(title, message)

    def show_notification(self, message, title=None, error=False, tray=False):
        show_info_bar(self.window(), message, title, error)
        if tray:
            self.tray.showMessage(title, message, QSystemTrayIcon.Critical if error else QSystemTrayIcon.Information,
                                  5000)

    def capture_error(self):
        self.show_notification(self.tr('Please check whether the game window is selected correctly!'),
                               self.tr('Capture Error'), error=True)

    def navigate_tab(self, index):
        logger.debug(f'navigate_tab {index}')
        if index == "start":
            self.switchTo(self.start_tab)
        elif index == "onetime" and self.onetime_tab is not None:
            self.switchTo(self.onetime_tab)
        elif index == "trigger" and self.trigger_tab is not None:
            self.switchTo(self.trigger_tab)

    def executor_paused(self, paused):
        if not paused and self.stackedWidget.currentIndex() == 0:
            self.switchTo(self.first_task_tab)
        self.show_notification(self.tr("Start Success.") if not paused else self.tr("Pause Success."), tray=True)

    def closeEvent(self, event):
        if og.app.exit_event.is_set():
            logger.info("Window closed exit_event.is_set")
            event.accept()
            return
        else:
            logger.info("Window closed exit_event.is not set")
            if not self.do_not_quit:
                self.exit_event.set()
            event.accept()
