import logging
import os
from typing import List, Optional
from rich.logging import RichHandler

class WarningAccumulatorHandler(logging.Handler):
    """
    Custom logging handler that accumulates warnings and errors for the pipeline
    summary and quality report while passing them along to standard log streams.
    """
    def __init__(self) -> None:
        super().__init__()
        self.warnings: List[str] = []
        self.errors: List[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            log_entry = self.format(record)
            if record.levelno == logging.WARNING:
                self.warnings.append(log_entry)
            elif record.levelno >= logging.ERROR:
                self.errors.append(log_entry)
        except Exception:
            self.handleError(record)

# Singleton accumulator instance
accumulator = WarningAccumulatorHandler()

def setup_logger(
    name: str = "pipeline",
    log_file: Optional[str] = None,
    console_level: int = logging.INFO
) -> logging.Logger:
    """
    Sets up a logger with RichHandler for console output and FileHandler for full debug tracing.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    
    # Avoid duplicate handlers if setup is called multiple times
    logger.handlers = []

    # Configure formats
    file_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    accumulator.setFormatter(file_formatter)
    logger.addHandler(accumulator)

    # Rich console logging handler
    console_handler = RichHandler(
        rich_tracebacks=True,
        markup=True,
        show_time=True,
        show_path=False
    )
    console_handler.setLevel(console_level)
    logger.addHandler(console_handler)

    # File logging handler (always logs at DEBUG level)
    if log_file:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setFormatter(file_formatter)
            file_handler.setLevel(logging.DEBUG)
            logger.addHandler(file_handler)
        except Exception as e:
            # Fallback output in case file initialization fails
            logger.warning(f"Could not initialize file logger at {log_file}: {e}")

    return logger

def get_warnings() -> List[str]:
    """Returns the accumulated list of warnings."""
    return accumulator.warnings

def get_errors() -> List[str]:
    """Returns the accumulated list of errors."""
    return accumulator.errors

def clear_accumulators() -> None:
    """Resets the accumulated lists of warnings and errors."""
    accumulator.warnings.clear()
    accumulator.errors.clear()
