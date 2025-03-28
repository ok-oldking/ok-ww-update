from PySide6.QtCore import QRectF
from PySide6.QtGui import QPainter, QPixmap, QPainterPath, Qt
from PySide6.QtWidgets import QWidget

import os
from ok import og


class ImageWidget(QWidget):
    cache = {}

    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        if image_path in self.cache:
            self.image = self.cache[image_path]
        else:
            self.image = QPixmap(image_path)
            self.image = self.image.scaled(round(self.image.width() / 2),
                                           round(self.image.height() / 2),
                                           Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.cache[image_path] = self.image

        self.setFixedSize(self.image.size())

    def paintEvent(self, event):
        painter = QPainter(self)
        path = QPainterPath()
        rect = QRectF(self.rect())
        radius = round(self.image.width() / 6)  # Adjust the radius for rounded corners
        path.addRoundedRect(rect, radius, radius)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, self.image)

    @staticmethod
    def check_exist(image_path):
        if image_path in ImageWidget.cache:
            return ImageWidget.cache.get(image_path)
        else:
            if os.path.exists(image_path):
                image = QPixmap(image_path)
                image = image.scaled(round(image.width() / og.dpi_scaling),
                                     round(image.height() / og.dpi_scaling),
                                     Qt.KeepAspectRatio, Qt.SmoothTransformation)
                ImageWidget.cache[image_path] = image
            else:
                ImageWidget.cache[image_path] = False
