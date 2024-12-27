from qfluentwidgets import BodyLabel

from ok import Logger
from ok import og
from ok.gui.about.VersionCard import VersionCard
from ok.gui.widget.Tab import Tab

logger = Logger.get_logger(__name__)


class ActTab(Tab):
    def __init__(self, config):
        super().__init__()
        self.version_card = VersionCard(config, config.get('gui_icon'), config.get('gui_title'), config.get('version'),
                                        config.get('debug'), self)
        # Create a QTextEdit instance
        self.add_widget(self.version_card)

        expire_time_label = BodyLabel("到期时间:{}".format(og.get_expire_util_str()))

        # Set the layout on the widget
        self.add_widget(expire_time_label)
