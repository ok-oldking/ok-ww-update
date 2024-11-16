import os
import unittest

from ok.Capture import ImageCaptureMethod

from ok.interaction.DoNothingInteraction import DoNothingInteraction
from ok.logging.Logger import get_logger

logger = get_logger(__name__)
os.environ["PYTHONIOENCODING"] = "utf-8"


class TaskTestCase(unittest.TestCase):
    ok = None

    task = None
    config = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if TaskTestCase.ok is None:
            from ok.OK import OK

            TaskTestCase.ok = OK(self.config)

            TaskTestCase.ok.task_executor.debug_mode = True
            TaskTestCase.ok.device_manager.capture_method = ImageCaptureMethod([])
            TaskTestCase.ok.device_manager.interaction = DoNothingInteraction(self.ok.device_manager.capture_method)

    @classmethod
    def tearDownClass(cls):
        # This method will run once after all tests in this class
        TaskTestCase.ok.quit()
        logger.debug('All tests finished, resources cleaned up.')

    def set_image(self, image):
        self.ok.device_manager.capture_method.set_images([image])

    def tearDown(self):
        self.task.reset_scene()
