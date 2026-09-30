from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json
from typing import Callable


@dataclass
class CompressionTask:
    input_file: str
    output_file: str
    status: str = "waiting"
    progress: float = 0.0
    stage: str = "waiting"
    error: str = ""

    def to_dict(self):
        return asdict(self)


class TaskManager:
    def __init__(self, state_file: str = "tasks.json"):
        self.state_file = Path(state_file)
        self.tasks: list[CompressionTask] = []
        self.load()

    def add(self, task: CompressionTask):
        self.tasks.append(task)
        self.save()

    def update(self, index: int, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self.tasks[index], key):
                setattr(self.tasks[index], key, value)
        self.save()

    def save(self):
        self.state_file.write_text(
            json.dumps([x.to_dict() for x in self.tasks], ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def load(self):
        if not self.state_file.exists():
            return
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            self.tasks = [CompressionTask(**x) for x in data]
        except Exception:
            self.tasks = []

    def pending(self):
        return [x for x in self.tasks if x.status not in ("done", "failed")]
