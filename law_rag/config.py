from __future__ import annotations

import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv


def load_environment(env_file: str | Path | None = None) -> Path | None:
    """Load project environment variables without overriding process values.

    Priority: existing OS environment > .env file > application defaults.
    LAW_RAG_ENV_FILE may point to a non-default dotenv file.
    """
    configured = env_file or os.getenv("LAW_RAG_ENV_FILE")
    if configured:
        path = Path(configured).expanduser().resolve()
        if path.is_file():
            load_dotenv(dotenv_path=path, override=False)
            return path
        return None

    discovered = find_dotenv(filename=".env", usecwd=True)
    if not discovered:
        return None
    path = Path(discovered).resolve()
    load_dotenv(dotenv_path=path, override=False)
    return path
