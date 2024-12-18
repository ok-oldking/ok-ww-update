from ok import TaskExecutor
from ok.gui.widget.Tab import Tab


class CustomTab(Tab):
    def __init__(self):
        super().__init__()
        self.executor: TaskExecutor | None = None

    def get_task(self, cls):
        return self.executor.get_task_by_class(cls)

    @property
    def name(self):
        return "CustomTab"
