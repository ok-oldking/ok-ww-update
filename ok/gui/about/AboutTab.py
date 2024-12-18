from qfluentwidgets import BodyLabel

from ok import Logger
from ok.gui.about.VersionCard import VersionCard
from ok.gui.widget.Tab import Tab

logger = Logger.get_logger(__name__)


class AboutTab(Tab):
    def __init__(self, config):
        super().__init__()
        self.version_card = VersionCard(config, config.get('gui_icon'), config.get('gui_title'), config.get('version'),
                                        config.get('debug'), self)
        # Create a QTextEdit instance
        self.addWidget(self.version_card)

        if about := config.get('about'):
            about_label = BodyLabel()
            about_label.setText(about)
            about_label.setWordWrap(True)
            about_label.setOpenExternalLinks(True)

            # Set the layout on the widget
            self.addWidget(about_label)

            self.addWidget(about_label)

    def update_update_buttons(self):
        if og.app.updater.latest_release:
            self.latest_label.setText(self.get_version_text(og.app.updater.latest_release))
        has_release_asset = og.app.updater.latest_release is not None and og.app.updater.latest_release.get(
            'release_asset') is not None
        self.download_latest_button.setVisible(has_release_asset)
        has_release_debug = og.app.updater.latest_release is not None and og.app.updater.latest_release.get(
            'debug_asset') is not None
        self.download_latest_debug_button.setVisible(has_release_debug)
        self.latest_label.setVisible(has_release_asset or has_release_debug)

        if og.app.updater.stable_release:
            self.stable_label.setText(self.get_version_text(og.app.updater.stable_release))

        has_release_asset = og.app.updater.stable_release is not None and og.app.updater.stable_release.get(
            'release_asset') is not None
        self.download_stable_button.setVisible(has_release_asset)
        has_release_debug = og.app.updater.stable_release is not None and og.app.updater.stable_release.get(
            'debug_asset') is not None
        self.download_stable_debug_button.setVisible(has_release_debug)
        self.stable_label.setVisible(has_release_asset or has_release_debug)

        self.download_latest_button.setDisabled(og.app.updater.downloading)
        self.download_stable_button.setDisabled(og.app.updater.downloading)
        self.download_stable_debug_button.setDisabled(og.app.updater.downloading)
        self.download_latest_debug_button.setDisabled(og.app.updater.downloading)

    def update_update(self, error):
        self.update_update_buttons()


def text_to_html_paragraphs(text):
    # Split the text into lines
    lines = text.split('\n')

    # Wrap each line in a <p> tag and join them
    return ''.join(f'<p>{line}</p>' for line in lines)
