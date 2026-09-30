"""Board Video Compressor core modules."""

from .compressor import CompressOptions, CompressResult
from .task_manager import CompressionTask, TaskManager

__all__ = [
    "CompressOptions",
    "CompressResult",
    "CompressionTask",
    "TaskManager",
]
