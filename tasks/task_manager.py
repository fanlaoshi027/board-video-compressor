from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
import json


class TaskStatus(str, Enum):
    WAITING = "waiting"
    ANALYZING = "analyzing"
    COMPRESSING = "compressing"
    DONE = "done"
    FAILED = "failed"


@dataclass
class VideoTask:
    source: str
    output: str = ""
    status: str = TaskStatus.WAITING.value
    progress: float = 0.0
    message: str = ""


class TaskManager:
    def __init__(self, save_file: str = "tasks.json"):
        self.save_file = Path(save_file)
        self.tasks: list[VideoTask] = []
        self.load()

    def add(self, source: str, output: str = "") -> VideoTask:
        task = VideoTask(str(source), str(output))
        self.tasks.append(task)
        self.save()
        return task

    def remove(self, source: str):
        self.tasks = [t for t in self.tasks if t.source != str(source)]
        self.save()

    def update(self, task: VideoTask, **kwargs):
        for key, value in kwargs.items():
            if hasattr(task, key):
                setattr(task, key, value)
        self.save()

    def pending(self):
        return [t for t in self.tasks if t.status not in (
            TaskStatus.DONE.value,
            TaskStatus.FAILED.value,
        )]

    def save(self):
        self.save_file.write_text(
            json.dumps([asdict(t) for t in self.tasks], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load(self):
        if not self.save_file.exists():
            return
        try:
            data = json.loads(self.save_file.read_text(encoding="utf-8"))
            self.tasks = [VideoTask(**x) for x in data]
        except Exception:
            self.tasks = []
