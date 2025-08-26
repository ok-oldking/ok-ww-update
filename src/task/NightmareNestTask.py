import time
import re
import cv2
import numpy as np
import win32api, win32gui, win32con

from qfluentwidgets import FluentIcon
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from ok import color_range_to_bound
from ok import Logger, TaskDisabledException, PostMessageInteraction
from ok import find_boxes_by_name
from src.task.BaseCombatTask import BaseCombatTask
from src.task.BaseWWTask import binarize_for_matching
from src.task.WWOneTimeTask import WWOneTimeTask

logger = Logger.get_logger(__name__)


class NightmareNestTask(WWOneTimeTask, BaseCombatTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_config = {'_enabled': True}
        self.trigger_interval = 0.1
        self.name = "Nightmare Nest Task"
        self.description = "Enable auto combat in Nightmare Nest"
        self.icon = FluentIcon.CALORIES
        self.last_is_click = False
        self._in_realm = False
        self.skip_f = 0
        self.status = -1
        self.stamina = 2
        self.last_purple_icon = None
        self.echo_list_cn = ["梦魇·振铎"]
        self.echo_list_tw = ["夢魘·振鐸"]
        self.echo_list_us = ["Nightmare: Tambourinist"]

    def run(self):
        WWOneTimeTask.run(self)
        test_picking_echo = False
        if test_picking_echo:
            chance = True
            circle = 0
            while True:
                dropped, has_more = self.yolo_find_echo(turn=True, use_color=False, time_out=12, threshold=0.25)
                self.sleep(0.5)
                circle += 1
                if not dropped and not has_more:
                    if chance:
                        self.log_info('find echo failed, have another chance')
                        chance = False
                    else:
                        self.log_info('find echo failed, tele to the next')
                        break
                else:
                    chance = True
                if circle >= 30:
                    break
        for echo_name in self.find_echo_list():
            self.ensure_main(time_out=180)
            self.openF2Book("gray_book_quest")
            self.click(0.04, 0.53)
            self.wait_hint(0.05, 0.04, 0.12, 0.08, r'敌迹探寻')
            self.click(0.13, 0.14, after_sleep=0.5)
            self.input_text(echo_name)
            self.click(0.39, 0.13, after_sleep=0.5)
            self.click(0.13, 0.24, after_sleep=0.5)
            self.click(0.89, 0.92)
            self.wait_hint(0.79, 0.91, 0.87, 0.95, r'快速旅行')
            if self.find_next_hint(0.90, 0.36, 0.94, 0.41, r'36'):
                self.log_info(f'{echo_name} is complete')
                continue
            self.click(0.89, 0.92)
            self.wait_in_team_and_world(raise_if_not_found=False)
            self.wait_until(self.in_combat, post_action=self.middle_click, time_out=10)
            if self.in_combat():
                self.log_info('wait combat')
                self.combat_once(wait_combat_time=0, raise_if_not_found=False)
            else:
                self.log_info(f'combat with {echo_name} error')
                continue
            self.log_info('find echo')
            self.pick_echo()
            chance = True
            circle = 0
            while True:
                dropped, has_more = self.yolo_find_echo(turn=True, use_color=False, time_out=12, threshold=0.25)
                self.sleep(0.5)
                circle += 1
                if not dropped and not has_more:
                    if chance:
                        self.log_info('find echo failed, have another chance')
                        chance = False
                    else:
                        self.log_info('find echo failed, tele to the next')
                        break
                else:
                    chance = True
                if circle >= 30:
                    break
        self.ensure_main(time_out=180)
        self.log_info(f'NightmareNestTask complete')

    def find_echo_list(self):
        if self.game_lang == 'zh_CN':
            return self.echo_list_cn
        elif self.game_lang == 'zh_TW':
            return self.echo_list_tw
        return self.echo_list_us

    def find_next_hint(self, x1, y1, x2, y2, s, box_name='hint_text'):
        texts = self.ocr(box=self.box_of_screen(x1, y1, x2, y2, hcenter=True),
                         target_height=540, name=box_name)
        fps_text = find_boxes_by_name(texts,
                                      re.compile(s, re.IGNORECASE))
        if fps_text:
            return True
        return False

    def wait_hint(self, x1, y1, x2, y2, hint, timeout=2):
        if self.wait_until(lambda: self.find_next_hint(x1, y1, x2, y2, hint), time_out=timeout):
            self.sleep(0.2)
            return True
        return False

    def walk_to_yolo_echo(self, time_out=8, update_function=None, echo_threshold=0.5):
        last_direction = None
        start = time.time()
        no_echo_start = 0
        while time.time() - start < time_out:
            self.next_frame()
            if self.find_one('pick_up_f_hcenter_vcenter', box=self.f_search_box, threshold=0.8):
                self._stop_last_direction(last_direction)
                if self.pick_f():
                    self.log_debug('pick echo success')
                return True
            if self.in_combat():
                self.log_debug('pick echo has_target return fail')
                self._stop_last_direction(last_direction)
                return False
            echos = self.find_echos(threshold=echo_threshold)
            if not echos:
                if no_echo_start == 0:
                    no_echo_start = time.time()
                elif time.time() - no_echo_start > 3:
                    self.log_debug(f'walk front to_echo, no echos found, have another chance')
                    self._stop_last_direction(last_direction)
                    return True
                next_direction = 'w'
            else:
                no_echo_start = 0
                echo = echos[0]
                center_distance = echo.center()[0] - self.width_of_screen(0.5)
                threshold = 0.05 if not last_direction else 0.15
                if abs(center_distance) < self.height_of_screen(threshold):
                    if echo.y + echo.height > self.height_of_screen(0.65):
                        next_direction = 's'
                    else:
                        next_direction = 'w'
                elif center_distance > 0:
                    next_direction = 'd'
                else:
                    next_direction = 'a'
            last_direction = self._walk_direction(last_direction, next_direction)
            if update_function is not None:
                update_function()
        self._stop_last_direction(last_direction)
