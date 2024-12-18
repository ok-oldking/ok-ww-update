from qfluentwidgets import SettingCard

from ok import Logger
from ok.gui.launcher.LinksBar import LinksBar

logger = Logger.get_logger(__name__)


class VersionCard(SettingCard):
    """ Sample card """

    def __init__(self, config, icon, title, version, debug, parent=None):
        super().__init__(icon, title, f'{version} {self.get_type(debug)}')
        links_bar = LinksBar(config)
        self.hBoxLayout.addWidget(links_bar)

    def get_type(self, debug=None):
        if debug is None and og.app.updater.to_update is not None:
            debug = og.app.updater.to_update.get('debug')
        return self.tr('Debug') if debug else self.tr('Release')
