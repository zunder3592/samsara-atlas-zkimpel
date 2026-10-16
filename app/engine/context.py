from dataclasses import dataclass, field
from typing import Any
import time


@dataclass
class ExecutionContext:
    case_id: int
    inputs: dict
    artifacts: dict
    step_outputs: dict[str, Any] = field(default_factory=dict)
    trace: list[dict] = field(default_factory=list)  # never populated - see P016
    started_at: float = field(default_factory=time.time)
