from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

@dataclass
class QueueItem:
    source: Path
    status: str = "等待"
    output: Path | None = None
    error: str = ""

class BatchQueue:
    def __init__(self): self.items: list[QueueItem] = []
    def add(self, paths):
        known={str(x.source.resolve()) for x in self.items}
        for p in paths:
            q=Path(p)
            if q.is_file() and str(q.resolve()) not in known:
                self.items.append(QueueItem(q)); known.add(str(q.resolve()))
    def clear_waiting(self): self.items=[x for x in self.items if x.status not in ("等待","失败")]
    def next_waiting(self): return next((x for x in self.items if x.status=="等待"),None)
    def reset(self):
        for x in self.items:
            if x.status != "完成": x.status="等待"; x.error=""
