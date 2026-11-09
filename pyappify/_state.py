"""Access to the runtime state kept on the ``pyappify`` package.

Public state such as ``pid``, ``logger`` and ``pyappify_executable`` lives on
the package itself so applications (and tests) can assign it directly, for
example ``pyappify.logger = my_logger``. Submodules look it up through
:func:`pkg` at call time instead of copying it at import time.
"""
import logging
import sys

_console_logger = None


def pkg():
    return sys.modules[__package__]


def get_logger():
    """Return the logger assigned to ``pyappify.logger`` or a console logger."""
    global _console_logger

    logger = getattr(pkg(), "logger", None)
    if logger is not None:
        return logger
    if _console_logger is None:
        _console_logger = logging.getLogger("pyappify")
        if not _console_logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
            _console_logger.addHandler(handler)
        _console_logger.setLevel(logging.INFO)
        _console_logger.propagate = False
    return _console_logger
