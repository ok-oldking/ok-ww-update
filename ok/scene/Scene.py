from abc import abstractmethod

from ok.logging.Logger import get_logger


class Scene(ExecutorOperation):
    name = None

    def __init__(self):
        super().__init__()
        self.name = self.__class__.__name__
        self.logger = get_logger(self.__class__.__name__)

    @abstractmethod
    def detect(self, frame):
        return False
