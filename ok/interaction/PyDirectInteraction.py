import time

import pydirectinput

from ok import BaseCaptureMethod
from ok import Logger
from ok import is_admin
from ok.interaction.BaseInteraction import BaseInteraction

logger = Logger.get_logger(__name__)

pydirectinput.FAILSAFE = False


class PyDirectInteraction(BaseInteraction):

    def __init__(self, capture: BaseCaptureMethod, hwnd_window):
        super().__init__(capture)
        self.hwnd_window = hwnd_window
        if not is_admin():
            logger.error(f"You must be an admin to use Win32Interaction")

    def send_key(self, key, down_time=0.01):
        if not self.capture.clickable():
            logger.error(f"can't click on {key}, because capture is not clickable")
            return
        pydirectinput.keyDown(str(key))
        time.sleep(down_time)
        pydirectinput.keyUp(str(key))

    def send_key_down(self, key):
        if not self.capture.clickable():
            logger.error(f"can't click on {key}, because capture is not clickable")
            return
        pydirectinput.keyDown(str(key))

    def send_key_up(self, key):
        if not self.capture.clickable():
            logger.error(f"can't click on {key}, because capture is not clickable")
            return
        pydirectinput.keyUp(str(key))

    def move(self, x, y):
        if not self.capture.clickable():
            return
        x, y = self.capture.get_abs_cords(x, y)
        pydirectinput.moveTo(x, y)

    def swipe(self, x1, y1, x2, y2, duration, settle_time=0.1):
        # Convert coordinates to integers
        x1, y1 = self.capture.get_abs_cords(x1, y1)
        x2, y2 = self.capture.get_abs_cords(x2, y2)

        # Move the mouse to the start point (x1, y1)
        pydirectinput.moveTo(x1, y1)
        time.sleep(0.1)  # Pause for a moment

        # Press the left mouse button down
        pydirectinput.mouseDown()

        # Calculate the relative movement (dx, dy)
        dx = x2 - x1
        dy = y2 - y1

        # Calculate the number of steps
        steps = int(duration / 100)  # 100 steps per second

        # Calculate the step size
        step_dx = dx / steps
        step_dy = dy / steps

        # Move the mouse to the end point (x2, y2) in small steps
        for i in range(steps):
            pydirectinput.moveTo(x1 + int(i * step_dx), y1 + int(i * step_dy))
            time.sleep(0.01)  # Sleep for 10ms
        if settle_time > 0:
            time.sleep(settle_time)
        # Release the left mouse button
        pydirectinput.mouseUp()

    def click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.01, move=False):
        super().click(x, y, name=name)
        if not self.capture.clickable():
            logger.info(f"window in background, not clickable")
            return
        # Convert the x, y position to lParam
        # lParam = win32api.MAKELONG(x, y)
        current_x, current_y = -1, -1
        if move_back:
            current_x, current_y = pydirectinput.position()
        if x != -1 and y != -1:
            x, y = self.capture.get_abs_cords(x, y)
            logger.info(f"left_click {x, y}")
            pydirectinput.moveTo(x, y)
        pydirectinput.click()
        if current_x != -1 and current_y != -1:
            pydirectinput.moveTo(current_x, current_y)

    def right_click(self, x=-1, y=-1, move_back=False, name=None):
        super().right_click(x, y, name=name)
        if not self.capture.clickable():
            logger.info(f"window in background, not clickable")
            return
        # Convert the x, y position to lParam
        # lParam = win32api.MAKELONG(x, y)
        current_x, current_y = -1, -1
        if move_back:
            current_x, current_y = pydirectinput.position()
        if x != -1 and y != -1:
            x, y = self.capture.get_abs_cords(x, y)
            logger.info(f"left_click {x, y}")
            pydirectinput.moveTo(x, y)
        pydirectinput.rightClick()
        if current_x != -1 and current_y != -1:
            pydirectinput.moveTo(current_x, current_y)

    def mouse_down(self, x=-1, y=-1, name=None, key="left"):
        if not self.capture.clickable():
            logger.info(f"window in background, not clickable")
            return
        if x != -1 and y != -1:
            x, y = self.capture.get_abs_cords(x, y)
            logger.info(f"left_click {x, y}")
            pydirectinput.moveTo(x, y)
        button = self.get_mouse_button(key)
        pydirectinput.mouseDown(button=button)

    def get_mouse_button(self, key):
        button = pydirectinput.LEFT if key == "left" else pydirectinput.RIGHT
        return button

    def mouse_up(self, key="left"):
        if not self.capture.clickable():
            logger.info(f"window in background, not clickable")
            return
        button = self.get_mouse_button(key)
        pydirectinput.mouseUp(button=button)

    def should_capture(self):
        return self.capture.clickable()

    def on_run(self):
        self.hwnd_window.bring_to_front()
