import re

from ok import Logger
from src.task.BaseCombatTask import BaseCombatTask
from src.task.WWOneTimeTask import WWOneTimeTask

logger = Logger.get_logger(__name__)


class DomainTask(WWOneTimeTask, BaseCombatTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.teleport_timeout = 100
        self.stamina_once = 0
        self._daily_task = False

    def make_sure_in_world(self):
        if (self.in_realm()):
            self.send_key('esc', after_sleep=1)
            self.wait_click_feature('gray_confirm_exit_button', relative_x=-1, raise_if_not_found=False,
                                    time_out=3, click_after_delay=0.5, threshold=0.7)
            self.wait_in_team_and_world(time_out=self.teleport_timeout)
        else:
            self.ensure_main()

    def open_F2_book_and_get_stamina(self):
        gray_book_boss = self.openF2Book('gray_book_boss')
        self.click_box(gray_book_boss, after_sleep=1)
        return self.get_stamina()

    def farm_in_domain(self, total_counter=0, current=0, back_up=0):
        if (self.stamina_once <= 0):
            raise RuntimeError('"self.stamina_once" must be override')
        # total counter
        if total_counter <= 0:
            self.log_info('0 time(s) farmed, 0 stamina used')
            self.make_sure_in_world()
            return
        # stamina
        if current + back_up < self.stamina_once:
            self.log_info('not enough stamina, 0 stamina used')
            self.make_sure_in_world()
            return
        # farm
        counter = total_counter
        total_used = 0
        while True:
            self.walk_until_f(time_out=4, backward_time=0, raise_if_not_found=True)
            self.pick_f()
            self.combat_once()
            self.sleep(3)
            self.walk_to_treasure()
            self.pick_f(handle_claim=False)
            used, remaining_total, remaining_current, _ = self.use_stamina(once=self.stamina_once, max_count=counter)
            if used == 0:
                self.log_info(f'not enough stamina')
                self.back()
                break
            total_used += used
            counter -= int(used / self.stamina_once)
            self.info_set('used stamina', total_used)
            self.sleep(4)
            if counter <= 0:
                self.log_info(f'{total_counter} time(s) farmed')
                break
            if self._daily_task and total_used >= 180 and remaining_current < self.stamina_once:
                self.log_info('daily stamina goal reached')
                break
            if remaining_total < self.stamina_once:
                self.log_info('used all stamina')
                break
            self.click(0.68, 0.84, after_sleep=2)  # farm again
            self.wait_in_team_and_world(time_out=self.teleport_timeout)
            self.sleep(1)
        #
        self.click(0.42, 0.84, after_sleep=2)  # back to world
        self.make_sure_in_world()
