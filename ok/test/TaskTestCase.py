from ok.Capture import ImageCaptureMethod

import unittest
from ok.interaction.DoNothingInteraction import DoNothingInteraction
from ok.logging.Logger import get_logger

logger = get_logger(__name__)


class TaskTestCase(unittest.TestCase):
    _ok = None
    task_class = None
    task = None
    config = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if TaskTestCase._ok is None:
            from ok.OK import OK

            TaskTestCase._ok = OK(self.config)
            TaskTestCase._ok.task_executor.debug_mode = True
            TaskTestCase._ok.device_manager.capture_method = ImageCaptureMethod(
                TaskTestCase._ok.device_manager.exit_event, [])
            TaskTestCase._ok.device_manager.interaction = DoNothingInteraction(
                TaskTestCase._ok.device_manager.capture_method)

        self.task = self.task_class()
        self.task.feature_set = TaskTestCase._ok.feature_set
        self.task._executor = TaskTestCase._ok.task_executor

    @classmethod
    def tearDownClass(cls):
        # This method will run once after all tests in this class
        TaskTestCase._ok.quit()
        logger.debug('All tests finished, resources cleaned up.')

    def set_image(self, image):
        self._ok.device_manager.capture_method.set_images([image])

    def tearDown(self):
        self.task.reset_scene()
