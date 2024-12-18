from PySide6.QtCore import Signal, QEvent
from PySide6.QtWidgets import QVBoxLayout
from qfluentwidgets import SplitTitleBar, LineEdit, PrimaryPushButton

from ok import Logger
from ok import og
from ok.gui.Communicate import communicate
from ok.gui.util.Alert import alert_error
from ok.gui.widget.BaseWindow import BaseWindow

logger = Logger.get_logger(__name__)


class ActWindow(BaseWindow):
    result_event = Signal(bool, str)

    def __init__(self, icon=None):
        super().__init__()
        self.user_closed = True

        self.setTitleBar(SplitTitleBar(self))
        self.titleBar.raise_()
        self.setWindowTitle(self.tr("软件激活"))

        if icon is not None:
            self.setWindowIcon(icon)

        self.vbox = QVBoxLayout()
        self.vbox.addStretch()
        self.setLayout(self.vbox)
        self.vbox.setContentsMargins(40, 40, 40, 40)

        self.key_input = LineEdit(self)
        self.vbox.addWidget(self.key_input)
        self.key_input.setPlaceholderText(self.tr("激活码"))
        self.key_input.setClearButtonEnabled(True)

        self.uid_input = LineEdit(self)
        self.uid_input.setPlaceholderText(self.tr("你的游戏编号, 如102630612345, 将会绑定此账号使用无法更改"))
        self.vbox.addWidget(self.uid_input)

        self.activate_btn = PrimaryPushButton(self.tr("激活"))
        self.vbox.addWidget(self.activate_btn)
        self.vbox.addStretch()

        self.result_event.connect(self.on_result)
        self.activate_btn.clicked.connect(self.activate)

    def activate(self):
        if not self.key_input.text():
            alert_error(self.tr("请输入激活码!"))
            return

        if not self.uid_input.text():
            alert_error(self.tr("请输入游戏编号!"))
            return

        og.handler.post(self.do_check_auth)
        self.show_loading()

    def on_result(self, success, message):
        logger.info(f'on_result: {success}, {message}')
        if success:
            self.user_closed = False
            self.close()
            og.app.do_show_main()
        else:
            alert_error(message)
        self.close_loading()

    def do_check_auth(self):
        success, result = og.app.check_auth(self.key_input.text(), self.uid_input.text())
        if success:
            self.result_event.emit(True, self.tr('验证成功!'))
        else:
            self.result_event.emit(False, self.tr('验证失败!'))

    def closeEvent(self, event):
        if og.ok.exit_event.is_set():
            logger.info("Window closed exit_event.is_set")
            event.accept()
            return
        else:
            logger.info(f"Window closed exit_event.is not set, self.user_closed {self.user_closed}")
            if self.user_closed:
                og.ok.quit()
            event.accept()

    def showEvent(self, event):
        if event.type() == QEvent.Show:
            logger.info("MessageWindow has fully displayed")
            communicate.start_success.emit()
        super().showEvent(event)
