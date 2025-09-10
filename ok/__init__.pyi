import argparse
import ctypes
import logging
import queue
import re
import sys
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

import cv2
import numpy as np
import psutil
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

# Type Aliases for clarity
Frame = np.ndarray
ExceptionInfo = Tuple[type, BaseException, Any]

class Logger:
    """A wrapper class for logging messages with a specific name."""
    logger: object
    name: str

    def __init__(self, name: str) -> None: ...

    def debug(self, message: Any) -> None:
        """Logs a debug message."""
        ...

    def info(self, message: Any) -> None:
        """Logs an info message."""
        ...

    def warning(self, message: Any) -> None:
        """Logs a warning message."""
        ...

    def error(self, message: Any, exception: Optional[Exception] = ...) -> None:
        """Logs an error message, optionally with an exception."""
        ...

    def critical(self, message: Any) -> None:
        """Logs a critical message."""
        ...
    @staticmethod
    def call_stack() -> str:
        """Returns the current call stack as a formatted string."""
        ...
    @staticmethod
    def get_logger(name: str) -> Logger:
        """Gets a Logger instance for the given name."""
        ...
    @staticmethod
    def exception_to_str(exception: Exception) -> str:
        """Converts an exception object to a formatted string including its traceback."""
        ...


class InfoFilter(logging.Filter):
    """A logging filter that allows records with a level less than ERROR."""

    def filter(self, record: logging.LogRecord) -> bool: ...


def config_logger(config: Optional[Dict[str, Any]] = ..., name: str = ...) -> None:
    """
    Configures the global logger with handlers for stdout, stderr, and file rotation.

    Args:
        config (Optional[Dict[str, Any]]): Configuration dictionary. Must contain a 'debug' key.
        name (str): The base name for the log file.
    """
    ...

class SafeFileHandler(TimedRotatingFileHandler):
    """A TimedRotatingFileHandler that handles I/O errors on closed streams."""

    def emit(self, record: logging.LogRecord) -> None: ...


def init_class_by_name(module_name: str, class_name: str, *args: Any, **kwargs: Any) -> Any:
    """
    Dynamically imports a module and initializes a class from it.

    Args:
        module_name (str): The name of the module to import.
        class_name (str): The name of the class to initialize.
        *args: Positional arguments to pass to the class constructor.
        **kwargs: Keyword arguments to pass to the class constructor.

    Returns:
        An instance of the specified class.
    """
    ...

class ExitEvent(threading.Event):
    """
    An event class that signals exit to bound queues and stoppable objects.
    """
    queues: Set[queue.Queue]
    to_stops: Set[Any]

    def bind_queue(self, q: queue.Queue) -> None:
        """Binds a queue to be notified on exit."""
        ...

    def bind_stop(self, to_stop: Any) -> None:
        """Binds an object with a 'stop' method to be called on exit."""
        ...

    def set(self) -> None:
        """Sets the exit event and notifies all bound queues and objects."""
        ...

@dataclass(order=True)
class ScheduledTask:
    """A dataclass representing a task scheduled for future execution."""
    execute_at: float
    task: Callable

class Handler:
    """A handler that processes tasks from a priority queue in a separate thread."""

    def __init__(self, event: ExitEvent, name: Optional[str] = ...) -> None: ...

    def post(self, task: Callable, delay: float = ..., remove_existing: bool = ...,
             skip_if_running: bool = ...) -> bool:
        """
        Posts a task to the handler's queue.

        Args:
            task (Callable): The task to be executed.
            delay (float): Delay in seconds before the task is executed.
            remove_existing (bool): If True, removes any existing instances of the same task.
            skip_if_running (bool): If True, skips adding the task if it's currently executing.

        Returns:
            bool: True if the task was posted successfully, False otherwise.
        """
        ...

    def stop(self) -> None:
        """Stops the handler thread and clears the task queue."""
        ...


def read_json_file(file_path: str) -> Optional[Dict[str, Any]]:
    """Reads and parses a JSON file."""
    ...


def write_json_file(file_path: str, data: Any) -> bool:
    """Writes data to a JSON file."""
    ...
def is_admin() -> bool:
    """Checks if the current user has administrative privileges (Windows only)."""
    ...


def get_first_item(lst: List[Any], default: Optional[Any] = ...) -> Optional[Any]:
    """Gets the first item of a list or a default value if the list is empty."""
    ...


def safe_get(lst: List[Any], idx: int, default: Optional[Any] = ...) -> Optional[Any]:
    """Safely gets an item from a list by index, returning a default value on IndexError."""
    ...


def find_index_in_list(my_list: List[Any], target_string: str, default_index: int = ...) -> int:
    """Finds the index of a target string in a list, returning a default index if not found."""
    ...


def get_path_relative_to_exe(*files: str) -> str:
    """Constructs a path relative to the executable's directory or the script's directory."""
    ...


def get_relative_path(*files: str) -> str:
    """Constructs a path relative to the current working directory."""
    ...


def install_path_isascii() -> Tuple[bool, str]:
    """Checks if the installation path contains only ASCII characters."""
    ...


def resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and for PyInstaller."""
    ...


def ensure_dir_for_file(file_path: str) -> str:
    """Ensures that the directory for a given file path exists."""
    ...


def ensure_dir(directory: str, clear: bool = ...) -> str:
    """Ensures that a directory exists, creating it if necessary."""
    ...


def delete_if_exists(file_path: str) -> None:
    """Deletes a file or directory if it exists."""
    ...


def delete_folders_starts_with(path: str, starts_with: str) -> None:
    """Deletes all folders within a path that start with a given prefix."""
    ...


def handle_remove_error(func: Callable, path: str, exc_info: ExceptionInfo) -> None:
    """Error handler for shutil.rmtree."""
    ...


def sanitize_filename(filename: str) -> str:
    """Removes invalid characters from a filename."""
    ...


def clear_folder(folder_path: str) -> None:
    """Deletes all files and subdirectories within a folder."""
    ...


def find_first_existing_file(filenames: List[str], directory: str) -> Optional[str]:
    """Finds the first file from a list of filenames that exists in a directory."""
    ...


def get_path_in_package(base: str, file: str) -> str:
    """Gets the path of a file relative to a package's base directory."""
    ...


def dir_checksum(directory: str, excludes: Optional[List[str]] = ...) -> str:
    """Calculates the MD5 checksum of a directory's contents."""
    ...


def find_folder_with_file(root_folder: str, target_file: str) -> Optional[str]:
    """Finds a subfolder containing a specific file."""
    ...


def get_folder_size(folder_path: str) -> int:
    """Calculates the total size of all files in a folder."""
    ...


def run_in_new_thread(func: Callable) -> threading.Thread:
    """Runs a function in a new thread."""
    ...
def check_mutex() -> bool:
    """Checks for a mutex to prevent multiple instances of the application."""
    ...


def restart_as_admin() -> None:
    """Restarts the application with administrative privileges."""
    ...


def all_pids() -> List[int]:
    """Returns a list of all process IDs."""
    ...


def ratio_text_to_number(supported_ratio: str) -> float:
    """Converts a ratio string (e.g., '16:9') to a float."""
    ...
def data_to_base64(data: Union[Dict, List[Dict]]) -> str:
    """Serializes a dictionary or list to a base64 encoded JSON string."""
    ...
def base64_to_data(base64_str: str) -> Union[Dict, List[Dict]]:
    """Deserializes a base64 encoded JSON string to a dictionary or list."""
    ...


def get_readable_file_size(file_path: str) -> str:
    """Returns the size of a file in a human-readable format."""
    ...


def bytes_to_readable_size(size_bytes: int) -> str:
    """Converts bytes to a human-readable size string."""
    ...
def execute(game_cmd: str) -> bool:
    """Executes a command, typically to start a game."""
    ...


def get_path(input_string: str) -> str:
    """Extracts a file path from a string that may contain arguments."""
    ...

class Box:
    """Represents a rectangular box with coordinates, dimensions, and optional properties."""
    x: int
    y: int
    width: int
    height: int
    confidence: float
    name: Any

    def __init__(self, x: float, y: float, width: float = ..., height: float = ..., confidence: float = ...,
                 name: Optional[Any] = ..., to_x: int = ..., to_y: int = ...) -> None: ...

    def area(self) -> int:
        """Calculates the area of the box."""
        ...

    def in_boundary(self, boxes: List['Box']) -> List['Box']:
        """Finds which of the given boxes are contained within this box."""
        ...

    def scale(self, width_ratio: float, height_ratio: Optional[float] = ...) -> 'Box':
        """Scales the box by given ratios, keeping the center point the same."""
        ...

    def closest_distance(self, other: 'Box') -> float:
        """Calculates the closest distance between the boundaries of this box and another."""
        ...

    def center_distance(self, other: 'Box') -> float:
        """Calculates the distance between the center points of this box and another."""
        ...

    def relative_with_variance(self, relative_x: float = ..., relative_y: float = ...) -> Tuple[int, int]:
        """Returns a point within the box with random variance."""
        ...

    def copy(self, x_offset: int = ..., y_offset: int = ..., width_offset: int = ..., height_offset: int = ...,
             name: Optional[Any] = ...) -> 'Box':
        """Creates a copy of the box with optional offsets."""
        ...

    def crop_frame(self, frame: Frame) -> Frame:
        """Crops a portion of an image frame corresponding to the box."""
        ...

    def center(self) -> Tuple[int, int]:
        """Returns the center coordinates of the box."""
        ...

    def find_closest_box(self, direction: str, boxes: List['Box'], condition: Optional[Callable] = ...) -> Optional[
        'Box']:
        """Finds the closest box in a given direction from a list of boxes."""
        ...


def find_highest_confidence_box(boxes: List[Box]) -> Optional[Box]:
    """Finds the box with the highest confidence score in a list of boxes."""
    ...


def sort_boxes(boxes: List[Box]) -> List[Box]:
    """Sorts a list of boxes based on their position (top-to-bottom, left-to-right)."""
    ...


def find_box_by_name(boxes: List[Box], names: Union[str, re.Pattern, List[Union[str, re.Pattern]]]) -> Optional[Box]:
    """Finds the first box in a list that matches one of the given names or patterns."""
    ...


def get_bounding_box(boxes: List[Box]) -> Box:
    """Calculates the bounding box that encloses a list of boxes."""
    ...


def find_boxes_within_boundary(boxes: List[Box], boundary_box: Box, sort: bool = ...) -> List[Box]:
    """Finds all boxes that are within the boundaries of a given box."""
    ...


def average_width(boxes: List[Box]) -> int:
    """Calculates the average width of a list of boxes."""
    ...


def crop_image(image: Frame, box: Optional[Box] = ...) -> Frame:
    """Crops an image to the dimensions of a given box."""
    ...


def relative_box(frame_width: int, frame_height: int, x: float, y: float, to_x: float = ..., to_y: float = ...,
                 width: float = ..., height: float = ..., name: Optional[Any] = ..., confidence: float = ...) -> Box:
    """Creates a Box with coordinates and dimensions relative to a frame size."""
    ...


def find_boxes_by_name(boxes: List[Box], names: Union[str, re.Pattern, List[Union[str, re.Pattern]]]) -> List[Box]:
    """Finds all boxes in a list that match one of the given names or patterns."""
    ...


def is_close_to_pure_color(image: Frame, max_colors: int = ..., percent: float = ...) -> bool:
    """Checks if an image is predominantly composed of a single color."""
    ...


def get_mask_in_color_range(image: Frame, color_range: Dict) -> Tuple[Frame, int]:
    """Creates a mask for pixels within a specified color range."""
    ...


def get_connected_area_by_color(image: Frame, color_range: Dict, connectivity: int = ..., gray_range: int = ...) -> \
Tuple[int, np.ndarray, np.ndarray]:
    """Finds connected components of a specific color in an image."""
    ...


def color_range_to_bound(color_range: Dict) -> Tuple[np.ndarray, np.ndarray]:
    """Converts a color range dictionary to lower and upper numpy array bounds."""
    ...


def calculate_colorfulness(image: Frame, box: Optional[Box] = ...) -> float:
    """Calculates the colorfulness of an image or a region of it."""
    ...


def get_saturation(image: Frame, box: Optional[Box] = ...) -> float:
    """Calculates the average saturation of an image or a region of it."""
    ...


def find_color_rectangles(image: Frame, color_range: Dict, min_width: int, min_height: int, max_width: int = ...,
                          max_height: int = ..., threshold: float = ..., box: Optional[Box] = ...) -> List[Box]:
    """Finds rectangles of a specific color in an image."""
    ...


def is_pure_black(frame: Frame) -> bool:
    """Checks if an image is entirely black."""
    ...


def calculate_color_percentage(image: Frame, color_ranges: Dict, box: Optional[Box] = ...) -> float:
    """Calculates the percentage of pixels of a certain color in an image or region."""
    ...


def rgb_to_gray(rgb: Tuple[int, int, int]) -> float:
    """Converts an RGB color to grayscale."""
    ...


def create_non_black_mask(image: Frame) -> Frame:
    """Creates a binary mask identifying non-black pixels in an image."""
    ...

class CommunicateHandler(logging.Handler):
    """A logging handler that emits signals for the GUI."""

    def __init__(self) -> None: ...

    def emit(self, record: logging.LogRecord) -> None: ...

class App:
    """Main application class that manages the GUI and application logic."""
    global_config: Any
    app: QApplication
    ok_config: Dict
    auth_config: Dict
    locale: Any
    overlay: Any
    start_controller: Any
    loading_window: Any
    overlay_window: Any
    main_window: Any
    exit_event: ExitEvent
    icon: QIcon
    fire_base_analytics: Any
    to_translate: Set[str]
    po_translation: Any
    updater: Any
    config: Dict
    about: str
    title: str
    version: str
    debug: bool

    def __init__(self, config: Dict, task_executor: Any, exit_event: Optional[ExitEvent] = ...) -> None: ...

    def check_auth(self, key: Optional[str] = ..., uid: str = ...) -> Tuple[bool, Any]:
        """Checks the user's authentication status."""
        ...

    def trial(self) -> Tuple[bool, Any]:
        """Initiates a trial period for the application."""
        ...

    def quit(self) -> None:
        """Quits the application."""
        ...
    def tr(self, key: str) -> str:
        """Translates a given key string."""
        ...

    def request(self, path: str, params: Dict) -> Any:
        """Sends a request to the authentication server."""
        ...

    def gen_tr_po_files(self) -> str:
        """Generates .po translation files."""
        ...

    def show_message_window(self, title: str, message: str) -> None:
        """Displays a message window."""
        ...

    def show_already_running_error(self) -> None:
        """Shows an error message if another instance is running."""
        ...

    def show_path_ascii_error(self, path: str) -> None:
        """Shows an error message if the installation path is not ASCII."""
        ...

    def update_overlay(self, visible: bool, x: int, y: int, window_width: int, window_height: int, width: int,
                       height: int, scaling: float) -> None:
        """Updates the overlay window's position and size."""
        ...

    def show_main_window(self) -> None:
        """Shows the main application window after checking authentication."""
        ...

    def do_show_main(self) -> None:
        """Initializes and shows the main application window."""
        ...

    def exec(self) -> None:
        """Starts the application's event loop."""
        ...

def get_my_id() -> str:
    """Generates a unique ID based on the MAC address."""
    ...
def get_my_id_with_cwd() -> str:
    """Generates a unique ID based on the MAC address and current working directory."""
    ...

class Response:
    """Represents a response from a server request."""
    code: int
    message: str
    data: Any

class OK:
    """The main class that initializes and runs the application."""

    def __init__(self, config: Dict) -> None: ...
    @property
    def app(self) -> App: ...

    def start(self) -> None:
        """Starts the application, either GUI or command-line mode."""
        ...
    def do_init(self) -> bool:
        """Performs main initialization of application components."""
        ...

    def wait_task(self) -> None:
        """Waits for the exit event to be set in command-line mode."""
        ...

    def console_handler(self, event: Any) -> bool:
        """Handles console events like CTRL+C."""
        ...

    def quit(self) -> None:
        """Initiates the application shutdown sequence."""
        ...

    def init_device_manager(self) -> None:
        """Initializes the device manager."""
        ...

class BaseScene:
    """Base class for representing a scene or state in the application."""

    def reset(self) -> None: ...


class BaseTask:
    """Base class for all tasks."""
    name: str
    description: str
    config: Dict
    info: Dict
    default_config: Dict
    config_description: Dict
    config_type: Dict
    running: bool
    exit_after_task: bool
    trigger_interval: bool
    last_trigger_time: float
    start_time: float
    icon: Any
    supported_languages: List[str]

    def __init__(self, executor: Optional['TaskExecutor'] = ...) -> None: ...

    def run_task_by_class(self, cls: type) -> None:
        """Runs another task by its class type."""
        ...

    def post_init(self) -> None:
        """Called after the task is fully initialized."""
        ...

    def create_shortcut(self) -> None:
        """Creates a desktop shortcut to run this task."""
        ...

    def tr(self, message: str) -> str:
        """Translates a message string."""
        ...
    def should_trigger(self) -> bool:
        """Determines if the task should be triggered based on its interval."""
        ...
    def is_custom(self) -> bool:
        """Checks if the task is a custom user-defined task."""
        ...

    def add_first_run_alert(self, first_run_alert: str) -> None:
        """Adds a configuration for a first-run alert message."""
        ...

    def add_exit_after_config(self) -> None:
        """Adds a configuration option to exit after the task completes."""
        ...
    def get_status(self) -> str:
        """Gets the current status of the task."""
        ...

    def enable(self) -> None:
        """Enables the task."""
        ...
    @property
    def handler(self) -> Handler: ...

    def pause(self) -> None:
        """Pauses the task."""
        ...

    def unpause(self) -> None:
        """Unpauses the task."""
        ...
    @property
    def paused(self) -> bool: ...

    def log_info(self, message: str, notify: bool = ...) -> None:
        """Logs an informational message."""
        ...

    def log_debug(self, message: str, notify: bool = ...) -> None:
        """Logs a debug message."""
        ...

    def log_error(self, message: str, exception: Optional[Exception] = ..., notify: bool = ...) -> None:
        """Logs an error message."""
        ...

    def go_to_tab(self, tab: str) -> None:
        """Switches to a specific tab in the GUI."""
        ...

    def notification(self, message: str, title: Optional[str] = ..., error: bool = ..., tray: bool = ...,
                     show_tab: Optional[str] = ...) -> None:
        """Shows a notification."""
        ...
    @property
    def enabled(self) -> bool: ...

    def info_clear(self) -> None:
        """Clears the task's info dictionary."""
        ...

    def info_incr(self, key: str, inc: int = ...) -> None:
        """Increments a value in the info dictionary."""
        ...

    def info_add_to_list(self, key: str, item: Any) -> None:
        """Adds an item to a list in the info dictionary."""
        ...

    def info_set(self, key: str, value: Any) -> None:
        """Sets a value in the info dictionary."""
        ...

    def info_get(self, *args, **kwargs) -> Any:
        """Gets a value from the info dictionary."""
        ...

    def info_add(self, key: str, count: int = ...) -> None:
        """Adds to a value in the info dictionary."""
        ...

    def load_config(self) -> None:
        """Loads the task's configuration from a file."""
        ...

    def validate(self, key: str, value: Any) -> Tuple[bool, Optional[str]]:
        """Validates a configuration key-value pair."""
        ...

    def validate_config(self, key: str, value: Any) -> Optional[str]:
        """Provides custom validation logic for a configuration key-value pair."""
        ...

    def disable(self) -> None:
        """Disables the task."""
        ...
    @property
    def hwnd_title(self) -> str: ...

    def run(self) -> None:
        """The main execution logic of the task."""
        ...
    def trigger(self) -> bool:
        """The trigger condition for the task."""
        ...

    def on_destroy(self) -> None:
        """Called when the task is being destroyed."""
        ...

    def on_create(self) -> None:
        """Called when the task is created."""
        ...

    def set_executor(self, executor: 'TaskExecutor') -> None:
        """Sets the task executor for the task."""
        ...

    def find_boxes(self, boxes: List[Box], match: Optional[Any] = ..., boundary: Optional[Union[Box, str]] = ...) -> \
    List[Box]:
        """Filters a list of boxes by name match and/or boundary."""
        ...


class TaskDisabledException(Exception): ...


class CannotFindException(Exception): ...


class FinishedException(Exception): ...


class WaitFailedException(Exception): ...

class TaskExecutor:
    """Executes tasks in a loop, managing frames and device interactions."""
    device_manager: Any
    feature_set: Any
    wait_until_settle_time: float
    wait_scene_timeout: float
    exit_event: ExitEvent
    debug_mode: bool
    debug: bool
    global_config: Any
    ocr_target_height: int
    current_task: Optional[BaseTask]
    trigger_tasks: List['TriggerTask']
    onetime_tasks: List[BaseTask]
    scene: Optional[BaseScene]
    text_fix: Dict
    ocr_po_translation: Any
    config: Dict

    def __init__(self, device_manager: Any, wait_until_timeout: int = ..., wait_until_settle_time: int = ...,
                 exit_event: Optional[ExitEvent] = ..., feature_set: Optional[Any] = ..., ocr_lib: Optional[Any] = ...,
                 config_folder: Optional[str] = ..., debug: bool = ..., global_config: Optional[Any] = ...,
                 ocr_target_height: int = ..., config: Optional[Dict] = ...) -> None: ...
    @property
    def interaction(self) -> Any: ...
    @property
    def method(self) -> Any: ...

    def ocr_lib(self, name: str = ...) -> Any:
        """Gets the OCR library instance."""
        ...

    def nullable_frame(self) -> Optional[Frame]:
        """Returns the current frame, which may be None."""
        ...

    def check_frame_and_resolution(self, supported_ratio: str, min_size: Tuple[int, int], time_out: float = ...) -> \
    Tuple[bool, str]:
        """Checks if the captured frame has a supported resolution."""
        ...
    def can_capture(self) -> bool:
        """Checks if the device is ready for frame capture."""
        ...

    def next_frame(self) -> Frame:
        """Captures and returns the next frame from the device."""
        ...
    def is_executor_thread(self) -> bool:
        """Checks if the current thread is the executor's thread."""
        ...
    def connected(self) -> bool:
        """Checks if the capture method is connected."""
        ...
    @property
    def frame(self) -> Frame: ...

    def check_enabled(self, check_pause: bool = ...) -> None:
        """Checks if the current task is enabled, raising an exception if not."""
        ...

    def sleep(self, timeout: float) -> None:
        """Sleeps for a specified duration, periodically checking for exit events."""
        ...

    def pause(self, task: Optional[BaseTask] = ...) -> Optional[bool]:
        """Pauses the executor or a specific task."""
        ...

    def stop_current_task(self) -> None:
        """Stops the currently running task."""
        ...

    def start(self) -> None:
        """Starts the task execution loop."""
        ...

    def wait_condition(self, condition: Callable, time_out: int = ..., pre_action: Optional[Callable] = ...,
                       post_action: Optional[Callable] = ..., settle_time: int = ...,
                       raise_if_not_found: bool = ...) -> Any:
        """Waits for a condition to be met."""
        ...

    def reset_scene(self, check_enabled: bool = ...) -> None:
        """Resets the current scene and frame."""
        ...
    def active_trigger_task_count(self) -> int:
        """Returns the number of active trigger tasks."""
        ...

    def stop(self) -> None:
        """Stops the task executor."""
        ...

    def wait_until_done(self) -> None:
        """Waits for the executor thread to finish."""
        ...

    def get_all_tasks(self) -> List[BaseTask]:
        """Returns a list of all tasks."""
        ...
    def get_task_by_class_name(self, class_name: str) -> Optional[BaseTask]:
        """Gets a task by its class name."""
        ...

    def get_task_by_class(self, cls: type) -> Optional[BaseTask]:
        """Gets a task by its class type."""
        ...


def list_or_obj_to_str(val: Any) -> Optional[str]:
    """Converts a list or object to a string representation."""
    ...


def create_shortcut(exe_path: Optional[str] = ..., shortcut_name_post: Optional[str] = ...,
                    description: Optional[str] = ..., target_path: Optional[str] = ...,
                    arguments: Optional[str] = ...) -> Optional[str]:
    """Creates a shortcut for an executable."""
    ...


def prevent_sleeping(yes: bool = ...) -> None:
    """Prevents or allows the system to go to sleep."""
    ...

class ExecutorOperation:
    """Provides a set of operations that can be performed by a task."""
    _executor: TaskExecutor
    logger: Logger

    def __init__(self, executor: TaskExecutor) -> None: ...
    def exit_is_set(self) -> bool:
        """Checks if the exit event is set."""
        ...

    def get_task_by_class(self, cls: type) -> Any:
        """Gets a task instance by its class."""
        ...
    def box_in_horizontal_center(self, box: Box, off_percent: float = ...) -> bool:
        """Checks if a box is in the horizontal center of the screen."""
        ...
    @property
    def executor(self) -> TaskExecutor: ...
    @property
    def debug(self) -> bool: ...

    def clipboard(self) -> Any:
        """Gets the content of the clipboard."""
        ...

    def is_scene(self, the_scene: Any) -> bool:
        """Checks if the current scene is of a specific type."""
        ...

    def reset_scene(self) -> None:
        """Resets the current scene."""
        ...

    def click(self, x: Union[int, Box, List[Box]] = ..., y: int = ..., move_back: bool = ..., name: Optional[str] = ...,
              interval: int = ..., move: bool = ..., down_time: float = ..., after_sleep: int = ..., key: str = ...) -> \
    Optional[bool]:
        """Performs a click action."""
        ...

    def back(self, *args, **kwargs) -> None:
        """Performs a 'back' action (e.g., presses the ESC key)."""
        ...

    def middle_click(self, *args, **kwargs) -> Optional[bool]:
        """Performs a middle-click action."""
        ...

    def right_click(self, *args, **kwargs) -> Optional[bool]:
        """Performs a right-click action."""
        ...
    def is_adb(self) -> bool:
        """Checks if the current device is an ADB device."""
        ...

    def mouse_down(self, x: int = ..., y: int = ..., name: Optional[str] = ..., key: str = ...) -> None:
        """Presses a mouse button down."""
        ...

    def mouse_up(self, name: Optional[str] = ..., key: str = ...) -> None:
        """Releases a mouse button."""
        ...

    def swipe_relative(self, from_x: float, from_y: float, to_x: float, to_y: float, duration: float = ...,
                       settle_time: int = ...) -> None:
        """Performs a swipe using relative coordinates."""
        ...

    def input_text(self, text: str) -> None:
        """Inputs text."""
        ...
    @property
    def hwnd(self) -> Any: ...

    def scroll_relative(self, x: float, y: float, count: int) -> None:
        """Performs a scroll action at a relative position."""
        ...

    def scroll(self, x: int, y: int, count: int) -> None:
        """Performs a scroll action."""
        ...

    def swipe(self, from_x: int, from_y: int, to_x: int, to_y: int, duration: float = ..., after_sleep: float = ...,
              settle_time: int = ...) -> None:
        """Performs a swipe action."""
        ...

    def screenshot(self, name: Optional[str] = ..., frame: Optional[Frame] = ..., show_box: bool = ...,
                   frame_box: Optional[Box] = ...) -> None:
        """Takes a screenshot."""
        ...

    def click_box_if_name_match(self, boxes: List[Box], names: Union[str, List[str]], relative_x: float = ...,
                                relative_y: float = ...) -> Optional[Box]:
        """Clicks on a box if its name matches one of the given names."""
        ...

    def box_of_screen(self, x: float, y: float, to_x: float = ..., to_y: float = ..., width: float = ...,
                      height: float = ..., name: Optional[str] = ..., hcenter: bool = ...,
                      confidence: float = ...) -> Box:
        """Creates a box with coordinates relative to the screen size."""
        ...
    def out_of_ratio(self) -> bool:
        """Checks if the current screen aspect ratio is different from the supported ratio."""
        ...

    def ensure_in_front(self) -> None:
        """Ensures the application window is in the foreground (for ADB)."""
        ...

    def box_of_screen_scaled(self, original_screen_width: int, original_screen_height: int, x_original: int,
                             y_original: int, to_x: int = ..., to_y: int = ..., width_original: int = ...,
                             height_original: int = ..., name: Optional[str] = ..., hcenter: bool = ...,
                             confidence: float = ...) -> Box:
        """Creates a scaled box for screens with different aspect ratios."""
        ...
    def height_of_screen(self, percent: float) -> int:
        """Calculates a height based on a percentage of the screen height."""
        ...
    @property
    def screen_width(self) -> int: ...
    @property
    def screen_height(self) -> int: ...
    def width_of_screen(self, percent: float) -> int:
        """Calculates a width based on a percentage of the screen width."""
        ...

    def click_relative(self, x: float, y: float, move_back: bool = ..., hcenter: bool = ..., move: bool = ...,
                       after_sleep: int = ..., name: Optional[str] = ..., interval: int = ..., down_time: float = ...,
                       key: str = ...) -> None:
        """Performs a click at a relative position on the screen."""
        ...

    def middle_click_relative(self, x: float, y: float, move_back: bool = ..., down_time: float = ...) -> None:
        """Performs a middle-click at a relative position."""
        ...
    @property
    def height(self) -> int: ...
    @property
    def width(self) -> int: ...

    def move_relative(self, x: float, y: float) -> None:
        """Moves the mouse to a relative position."""
        ...

    def move(self, x: int, y: int) -> None:
        """Moves the mouse to an absolute position."""
        ...

    def click_box(self, box: Optional[Union[Box, List[Box], str]] = ..., relative_x: float = ...,
                  relative_y: float = ..., raise_if_not_found: bool = ..., move_back: bool = ...,
                  down_time: float = ..., after_sleep: int = ...) -> None:
        """Clicks on a given box."""
        ...

    def wait_scene(self, scene_type: Optional[type] = ..., time_out: int = ..., pre_action: Optional[Callable] = ...,
                   post_action: Optional[Callable] = ...) -> Any:
        """Waits for a specific scene to appear."""
        ...
    def sleep(self, timeout: float) -> bool:
        """Sleeps for a given duration."""
        ...

    def send_key(self, key: Any, down_time: float = ..., interval: int = ..., after_sleep: int = ...) -> bool:
        """Sends a key press."""
        ...

    def get_global_config(self, option: Any) -> Any:
        """Gets a global configuration option."""
        ...

    def get_global_config_desc(self, option: Any) -> Any:
        """Gets the description of a global configuration option."""
        ...

    def send_key_down(self, key: Any) -> None:
        """Sends a key down event."""
        ...

    def send_key_up(self, key: Any) -> None:
        """Sends a key up event."""
        ...

    def wait_until(self, condition: Callable, time_out: int = ..., pre_action: Optional[Callable] = ...,
                   post_action: Optional[Callable] = ..., settle_time: int = ...,
                   raise_if_not_found: bool = ...) -> Any:
        """Waits until a condition is met."""
        ...

    def wait_click_box(self, condition: Callable, time_out: int = ..., pre_action: Optional[Callable] = ...,
                       post_action: Optional[Callable] = ..., raise_if_not_found: bool = ...) -> Any:
        """Waits for a box to appear and then clicks it."""
        ...

    def next_frame(self) -> Frame:
        """Gets the next frame."""
        ...

    def adb_ui_dump(self) -> Any:
        """Dumps the UI hierarchy of an ADB device."""
        ...
    @property
    def frame(self) -> Frame: ...
    @staticmethod
    def draw_boxes(feature_name: Optional[str] = ..., boxes: Optional[List[Box]] = ..., color: str = ...,
                   debug: bool = ...) -> None:
        """Draws boxes on the screen for debugging."""
        ...

    def clear_box(self) -> None:
        """Clears all drawn boxes from the screen."""
        ...

    def calculate_color_percentage(self, color: Any, box: Union[Box, str]) -> float:
        """Calculates the percentage of a color within a box."""
        ...

    def adb_shell(self, *args, **kwargs) -> Any:
        """Executes a shell command on an ADB device."""
        ...

class TriggerTask(BaseTask):
    """A task that can be triggered based on certain conditions."""

    def __init__(self, *args, **kwargs) -> None: ...

    def on_create(self) -> None: ...

    def get_status(self) -> str: ...

    def enable(self) -> None: ...

    def disable(self) -> None: ...

class FindFeature(ExecutorOperation):
    """Provides methods for finding features (template matching) in an image."""

    def __init__(self, executor: TaskExecutor) -> None: ...

    def find_feature(self, feature_name: Optional[str] = ..., horizontal_variance: int = ...,
                     vertical_variance: int = ..., threshold: int = ..., use_gray_scale: bool = ..., x: int = ...,
                     y: int = ..., to_x: int = ..., to_y: int = ..., width: int = ..., height: int = ...,
                     box: Optional[Box] = ..., canny_lower: int = ..., canny_higher: int = ...,
                     frame_processor: Optional[Callable] = ..., template: Optional[Frame] = ...,
                     match_method: int = ..., screenshot: bool = ..., mask_function: Optional[Callable] = ...,
                     frame: Optional[Frame] = ...) -> List[Box]:
        """Finds all occurrences of a feature in an image."""
        ...

    def get_feature_by_name(self, name: str) -> Any:
        """Gets a pre-loaded feature by its name."""
        ...

    def get_box_by_name(self, name: Union[str, Box]) -> Box:
        """Gets a pre-defined box by its name."""
        ...

    def find_feature_and_set(self, features: Union[str, List[str]], horizontal_variance: int = ...,
                             vertical_variance: int = ..., threshold: int = ...) -> bool:
        """Finds features and sets them as attributes of the instance."""
        ...

    def wait_feature(self, feature: str, horizontal_variance: int = ..., vertical_variance: int = ...,
                     threshold: int = ..., time_out: int = ..., pre_action: Optional[Callable] = ...,
                     post_action: Optional[Callable] = ..., use_gray_scale: bool = ..., box: Optional[Box] = ...,
                     raise_if_not_found: bool = ..., canny_lower: int = ..., canny_higher: int = ...,
                     settle_time: int = ..., frame_processor: Optional[Callable] = ...) -> Any:
        """Waits for a feature to appear."""
        ...

    def wait_click_feature(self, feature: str, horizontal_variance: int = ..., vertical_variance: int = ...,
                           threshold: int = ..., relative_x: float = ..., relative_y: float = ..., time_out: int = ...,
                           pre_action: Optional[Callable] = ..., post_action: Optional[Callable] = ...,
                           box: Optional[Box] = ..., raise_if_not_found: bool = ..., use_gray_scale: bool = ...,
                           canny_lower: int = ..., canny_higher: int = ..., click_after_delay: int = ...,
                           settle_time: int = ..., after_sleep: int = ...) -> bool:
        """Waits for a feature to appear and then clicks it."""
        ...

    def find_one(self, feature_name: Optional[str] = ..., horizontal_variance: int = ..., vertical_variance: int = ...,
                 threshold: int = ..., use_gray_scale: bool = ..., box: Optional[Box] = ..., canny_lower: int = ...,
                 canny_higher: int = ..., frame_processor: Optional[Callable] = ..., template: Optional[Frame] = ...,
                 mask_function: Optional[Callable] = ..., frame: Optional[Frame] = ..., match_method: int = ...,
                 screenshot: bool = ...) -> Optional[Box]:
        """Finds the best match for a single feature."""
        ...
    def feature_exists(self, feature_name: str) -> bool:
        """Checks if a feature exists in the feature set."""
        ...

    def find_best_match_in_box(self, box: Box, to_find: List[str], threshold: float, use_gray_scale: bool = ...,
                               canny_lower: int = ..., canny_higher: int = ...,
                               frame_processor: Optional[Callable] = ..., mask_function: Optional[Callable] = ...) -> \
    Optional[Box]:
        """Finds the best matching feature from a list within a specific box."""
        ...

    def find_first_match_in_box(self, box: Box, to_find: List[str], threshold: float, use_gray_scale: bool = ...,
                                canny_lower: int = ..., canny_higher: int = ...,
                                frame_processor: Optional[Callable] = ..., mask_function: Optional[Callable] = ...) -> \
    Optional[Box]:
        """Finds the first matching feature from a list within a specific box."""
        ...

class OCR(FindFeature):
    """Provides Optical Character Recognition (OCR) functionalities."""
    ocr_default_threshold: float
    log_debug: bool

    def __init__(self, executor: TaskExecutor) -> None: ...

    def ocr(self, x: float = ..., y: float = ..., to_x: float = ..., to_y: float = ..., match: Optional[Any] = ...,
            width: int = ..., height: int = ..., box: Optional[Box] = ..., name: Optional[str] = ...,
            threshold: float = ..., frame: Optional[Frame] = ..., target_height: int = ..., use_grayscale: bool = ...,
            log: bool = ..., frame_processor: Optional[Callable] = ..., lib: str = ...) -> List[Box]:
        """Performs OCR on a specified region of an image."""
        ...

    def add_text_fix(self, fix: Dict[str, str]) -> None:
        """Adds custom text corrections to the OCR process."""
        ...

    def wait_click_ocr(self, x: float = ..., y: float = ..., to_x: float = ..., to_y: float = ..., width: int = ...,
                       height: int = ..., box: Optional[Box] = ..., name: Optional[str] = ...,
                       match: Optional[Any] = ..., threshold: float = ..., frame: Optional[Frame] = ...,
                       target_height: int = ..., time_out: int = ..., raise_if_not_found: bool = ...,
                       recheck_time: int = ..., after_sleep: int = ..., post_action: Optional[Callable] = ...,
                       log: bool = ..., settle_time: int = ..., lib: str = ...) -> Optional[List[Box]]:
        """Waits for specific text to appear and then clicks on it."""
        ...

    def wait_ocr(self, x: float = ..., y: float = ..., to_x: float = ..., to_y: float = ..., width: int = ...,
                 height: int = ..., name: Optional[str] = ..., box: Optional[Box] = ..., match: Optional[Any] = ...,
                 threshold: float = ..., frame: Optional[Frame] = ..., target_height: int = ..., time_out: int = ...,
                 post_action: Optional[Callable] = ..., raise_if_not_found: bool = ..., log: bool = ...,
                 settle_time: int = ..., lib: str = ...) -> Optional[List[Box]]:
        """Waits for specific text to appear."""
        ...


class CaptureException(Exception): ...

class BaseCaptureMethod:
    """Base class for all screen capture methods."""

    def __init__(self) -> None: ...

    def close(self) -> None:
        """Closes the capture method and releases resources."""
        ...
    @property
    def width(self) -> int: ...
    @property
    def height(self) -> int: ...
    def get_name(self) -> str:
        """Gets the name of the capture method."""
        ...

    def get_frame(self) -> Optional[Frame]:
        """Captures and returns a single frame."""
        ...
    def connected(self) -> bool:
        """Checks if the capture method is connected and ready."""
        ...


class HwndWindow:
    """Manages a window handle (HWND) and its properties."""

    def __init__(self, exit_event: ExitEvent, title: str, exe_name: Optional[str] = ..., frame_width: int = ...,
                 frame_height: int = ..., player_id: int = ..., hwnd_class: Optional[str] = ...,
                 global_config: Optional[Any] = ..., device_manager: Optional[Any] = ...) -> None: ...

    def stop(self) -> None:
        """Stops the window update thread."""
        ...

    def bring_to_front(self) -> None:
        """Brings the window to the foreground."""
        ...

    def try_resize_to(self, resize_to: List[Tuple[int, int]]) -> bool:
        """Tries to resize the window to one of the supported resolutions."""
        ...
    @property
    def hwnd_title(self) -> str: ...


class DeviceManager:
    """Manages devices (Windows, ADB) and their capture/interaction methods."""

    def __init__(self, app_config: Dict, exit_event: Optional[ExitEvent] = ...,
                 global_config: Optional[Any] = ...) -> None: ...

    def stop_hwnd(self) -> None:
        """Stops the process associated with the managed window."""
        ...

    def select_hwnd(self, exe: str, hwnd: int) -> None:
        """Selects a specific window handle to manage."""
        ...

    def refresh(self) -> None:
        """Refreshes the list of available devices."""
        ...
    @property
    def adb(self) -> Any: ...

    def adb_connect(self, addr: str, try_connect: bool = ...) -> Optional[Any]:
        """Connects to an ADB device."""
        ...

    def get_devices(self) -> List[Dict]:
        """Gets the list of detected devices."""
        ...

    def get_resolution(self, device: Optional[Any] = ...) -> Tuple[int, int]:
        """Gets the resolution of a device."""
        ...

    def set_preferred_device(self, imei: Optional[str] = ..., index: int = ...) -> None:
        """Sets the preferred device to use."""
        ...

    def get_preferred_device(self) -> Optional[Dict]:
        """Gets the currently preferred device."""
        ...

    def get_preferred_capture(self) -> str:
        """Gets the preferred capture method."""
        ...

    def set_capture(self, capture: str) -> None:
        """Sets the capture method to use."""
        ...

    def start(self) -> None:
        """Starts the device manager and initializes capture/interaction methods."""
        ...

    def shell(self, *args, **kwargs) -> Any:
        """Executes a shell command on the preferred device."""
        ...


class MainWindow:
    """The main window of the application GUI."""

    def __init__(self, app: App, config: Dict, ok_config: Dict, icon: QIcon, title: str, version: str,
                 debug: bool = ..., about: Optional[str] = ..., exit_event: Optional[ExitEvent] = ...,
                 global_config: Optional[Any] = ...) -> None: ...

    def closeEvent(self, event: QEvent) -> None:
        """Handles the window close event."""
        ...

class Config(dict):
    """A dictionary-like class for managing configuration files."""
    config_folder: str

    def __init__(self, name: str, default: Dict, folder: Optional[str] = ...,
                 validator: Optional[Callable] = ...) -> None: ...

    def save_file(self) -> None: ...

    def get_default(self, key: str) -> Any: ...

    def reset_to_default(self) -> None: ...

class Analytics:
    """Handles sending analytics data."""

    def __init__(self, app_config: Dict, exit_event: ExitEvent) -> None: ...
    @property
    def user_properties(self) -> Dict[str, str]: ...
    @property
    def client_id(self) -> str: ...

    def send_alive(self) -> None:
        """Sends a periodic 'alive' signal with system information."""
        ...

    def get_unique_client_id(self) -> str:
        """Generates a unique client ID based on user properties."""
        ...

class ConfigOption:
    """Represents a configuration option with its properties."""

    def __init__(self, name: str, default: Optional[Dict] = ..., description: str = ...,
                 config_description: Optional[Dict] = ..., config_type: Optional[Dict] = ...,
                 validator: Optional[Callable] = ..., icon: Any = ...) -> None: ...

class GlobalConfig:
    """Manages global configuration options."""

    def __init__(self, config_options: List[ConfigOption]) -> None: ...

    def get_config(self, option: Union[str, ConfigOption]) -> Config:
        """Gets a configuration object."""
        ...

    def get_config_desc(self, key: str) -> Optional[str]:
        """Gets the description for a configuration key."""
        ...

    def get_all_visible_configs(self) -> List[Tuple[str, Config, ConfigOption]]:
        """Gets all user-visible configurations."""
        ...

class FeatureSet:
    """Manages a set of features (templates) for image recognition."""

    def __init__(self, debug: bool, coco_json: str, default_horizontal_variance: float,
                 default_vertical_variance: float, default_threshold: float = ...,
                 feature_processor: Optional[Callable] = ...) -> None: ...
    def feature_exists(self, feature_name: str) -> bool:
        """Checks if a feature with the given name exists."""
        ...

    def get_box_by_name(self, mat: Frame, category_name: str) -> Optional[Box]:
        """Gets a pre-defined box associated with a feature."""
        ...

    def get_feature_by_name(self, mat: Frame, name: str) -> Optional[Any]:
        """Gets a feature object by its name."""
        ...

    def find_feature(self, mat: Frame, category_name: Union[str, List[str]], horizontal_variance: float = ...,
                     vertical_variance: float = ..., threshold: float = ..., use_gray_scale: bool = ..., x: int = ...,
                     y: int = ..., to_x: int = ..., to_y: int = ..., width: int = ..., height: int = ...,
                     box: Optional[Box] = ..., canny_lower: int = ..., canny_higher: int = ...,
                     frame_processor: Optional[Callable] = ..., template: Optional[Frame] = ...,
                     mask_function: Optional[Callable] = ..., match_method: int = ..., screenshot: bool = ...) -> List[
        Box]:
        """Finds occurrences of a feature in an image."""
        ...

class BaseInteraction:
    """Base class for device interaction methods."""

    def __init__(self, capture: BaseCaptureMethod) -> None: ...
    def should_capture(self) -> bool:
        """Determines if the screen should be captured before interaction."""
        ...

    def send_key(self, key: Any, down_time: float = ...) -> None: ...

    def send_key_down(self, key: Any) -> None: ...

    def send_key_up(self, key: Any) -> None: ...

    def move(self, x: int, y: int) -> None: ...

    def swipe(self, from_x: int, from_y: int, to_x: int, to_y: int, duration: float,
              settle_time: int = ...) -> None: ...

    def click(self, x: int = ..., y: int = ..., move_back: bool = ..., name: Optional[str] = ..., move: bool = ...,
              down_time: float = ..., key: str = ...) -> None: ...

    def on_run(self) -> None:
        """Called when a task starts running."""
        ...

    def input_text(self, text: str) -> None: ...

    def back(self, after_sleep: int = ...) -> None: ...

    def scroll(self, x: int, y: int, scroll_amount: int) -> None: ...

    def on_destroy(self) -> None:
        """Called when the interaction handler is being destroyed."""
        ...

class DiagnosisTask(BaseTask):
    """A task for diagnosing performance and system information."""

    def __init__(self, *args, **kwargs) -> None: ...

    def run(self) -> None: ...


def get_current_process_memory_usage() -> Tuple[float, float, Optional[float]]:
    """Gets the memory usage of the current process in MB."""
    ...
