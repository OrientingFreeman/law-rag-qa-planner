from __future__ import annotations

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "law_rag.api.app:app",
        host=os.getenv("LAW_RAG_HOST", "127.0.0.1"),
        port=int(os.getenv("LAW_RAG_PORT", "8000")),
        reload=os.getenv("LAW_RAG_RELOAD", "false").lower() == "true",
    )


if __name__ == "__main__":
    main()
