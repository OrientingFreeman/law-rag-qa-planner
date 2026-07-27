from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


class JsonlRunLogger:
    def __init__(self, log_dir: str | Path | None = None) -> None:
        self.log_dir = Path(log_dir or os.getenv("LAW_RAG_LOG_DIR", "logs"))

    def write(self, payload: dict[str, object]) -> Path:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        path = self.log_dir / f"{now:%Y%m%d}.jsonl"
        record = {"timestamp": now.isoformat(), **payload}
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return path
