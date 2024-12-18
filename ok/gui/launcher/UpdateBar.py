from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QWidget, QHBoxLayout, QSpacerItem, QSizePolicy, QVBoxLayout
from qfluentwidgets import PushButton, ComboBox, FluentIcon, PrimaryPushButton, BodyLabel

from ok import Logger
from ok.gui.Communicate import communicate
from ok.gui.launcher.DownloadBar import DownloadBar
from ok.gui.launcher.LinksBar import LinksBar
from ok.update.GitUpdater import GitUpdater, is_newer_or_eq_version

logger = Logger.get_logger(__name__)


class UpdateBar(QWidget):

    def __init__(self, config, updater: GitUpdater):
        super().__init__()
        self.updater = updater

        self.layout = QVBoxLayout()

        # self.log_scroll_area = SmoothScrollArea()
        # self.scroll_widget = QWidget(self.log_scroll_area)
        self.version_log_label = BodyLabel(self.tr("Checking for Updates..."))
        self.version_log_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.version_log_label.setWordWrap(True)

        if config.get('links'):
            self.links_bar = LinksBar(config)
            self.layout.addWidget(self.links_bar)

        self.download_bar = DownloadBar()
        self.layout.addWidget(self.download_bar)

        self.hbox_layout = QHBoxLayout()
        self.layout.addLayout(self.hbox_layout)
        self.hbox_layout.addItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))
        self.hbox_layout.setSpacing(20)

        # self.version_log_hbox_layout = QHBoxLayout()
        self.layout.addWidget(self.version_log_label)

        # self.version_log_hbox_layout.addWidget(self.log_scroll_area)

        self.update_hbox_layout = QHBoxLayout()
        self.layout.addLayout(self.update_hbox_layout)
        self.update_hbox_layout.addItem(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))
        self.update_hbox_layout.setSpacing(20)

        communicate.update_logs.connect(self.update_logs)

        self.delete_dependencies_button = PushButton(self.tr("Delete Downloaded Dependencies"), icon=FluentIcon.DELETE)
        self.delete_dependencies_button.clicked.connect(self.updater.clear_dependencies)
        self.hbox_layout.addWidget(self.delete_dependencies_button)

        communicate.versions.connect(self.update_versions)
        communicate.update_running.connect(self.update_running)
        self.update_source_box = QHBoxLayout()

        self.update_source_box.setSpacing(6)

        self.hbox_layout.addLayout(self.update_source_box, stretch=0)
        self.source_label = BodyLabel(self.tr("Update Source:"))
        self.update_source_box.addWidget(self.source_label, stretch=0)

        self.update_sources = ComboBox()
        self.update_source_box.addWidget(self.update_sources, stretch=0)
        self.update_source_box.addSpacing(10)
        sources = config.get('git_update').get('sources')
        source_names = [QCoreApplication.translate('app', source['name']) for source in sources]
        self.update_sources.addItems(source_names)
        self.update_sources.setCurrentIndex(self.updater.launcher_config.get('source_index'))

        self.update_sources.currentTextChanged.connect(self.update_source)

        self.check_update_button = PushButton(self.tr("Check for Update"), icon=FluentIcon.SYNC)
        self.hbox_layout.addWidget(self.check_update_button)
        self.check_update_button.clicked.connect(self.updater.list_all_versions)

        self.version_label = BodyLabel()
        self.version_label_target = BodyLabel()
        self.update_hbox_layout.addWidget(self.version_label)

        self.current_version = ComboBox()
        self.update_hbox_layout.addWidget(self.current_version)
        self.update_hbox_layout.addWidget(self.version_label_target)
        self.current_version.addItems([self.updater.launcher_config.get(
            'app_version')])
        self.version_label.setText(self.tr('Current Version:'))
        self.version_label_target.setText(self.tr('TargetVersion:'))

        self.version_list = ComboBox()
        self.update_hbox_layout.addWidget(self.version_list)
        self.version_list.currentTextChanged.connect(self.version_selection_changed)

        self.update_button = PrimaryPushButton(self.tr("Update"), icon=FluentIcon.UP)
        self.update_button.clicked.connect(self.update_clicked)
        self.update_hbox_layout.addWidget(self.update_button)

        self.set_op_btn_visible(False)

        self.setLayout(self.layout)

    def update_source(self):
        if self.update_sources.currentText():
            self.updater.update_source(self.update_sources.currentIndex())

    def version_selection_changed(self, text):
        self.update_update_btns(text)
        self.updater.version_selection_changed(text)

    def update_update_btns(self, text):
        if text:
            cmp = is_newer_or_eq_version(text, self.updater.launcher_config.get('app_version'))
            if cmp >= 0:
                self.update_button.setText(self.tr("Update"))
                self.update_button.setIcon(icon=FluentIcon.UP)
            else:
                self.update_button.setText(self.tr("Downgrade"))
                self.update_button.setIcon(icon=FluentIcon.DOWN)
            self.update_button.setDisabled(cmp == 0)

    def update_logs(self, logs):
        if logs:
            self.version_log_label.setText(logs)
        else:
            self.version_log_label.setText(self.tr("This is the newest version"))
        self.version_log_label.setVisible(logs is not None)

    def update_clicked(self):
        self.updater.update_to_version(self.version_list.currentText())
        self.update_button.setDisabled(True)
        self.check_update_button.setDisabled(True)

    def update_running(self, running):
        logger.info(f'update_running {running}')
        self.update_button.setDisabled(running)
        self.check_update_button.setDisabled(running)
        self.update_sources.setDisabled(running)
        self.version_list.setDisabled(running)
        self.delete_dependencies_button.setDisabled(running)
        self.set_op_btn_visible(not running)
        if running:
            self.version_log_label.setText(self.tr("Checking for Updates..."))

    def update_versions(self, versions):
        if not versions:  # fetch version error
            self.version_list.clear()
            self.version_label.setText(self.tr("This is the newest version"))
        else:
            current_items = [self.version_list.itemText(i) for i in range(self.version_list.count())]
            if current_items != versions:
                self.version_list.clear()
                self.version_list.addItems(versions)
                self.set_op_btn_visible(len(versions) != 0)

    def set_op_btn_visible(self, visible):
        for i in reversed(range(self.update_hbox_layout.count())):
            widget = self.update_hbox_layout.itemAt(i).widget()
            if widget is not None:
                widget.setVisible(visible)
