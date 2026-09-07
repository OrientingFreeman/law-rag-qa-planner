from __future__ import annotations

import argparse
import json
from pathlib import Path

from law_rag.reasoning.printed_page_decisions import decisions_from_review_queue, save_private_printed_page_decisions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export approved high-confidence printed-page decisions")
    parser.add_argument("queue", help="Private OCR review queue JSON")
    parser.add_argument("--output", required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--reviewed-at", required=True)
    parser.add_argument("--verified-label-absent", default="", help="Comma-separated physical page numbers")
    parser.add_argument("--approve-high-confidence", action="store_true", required=True)
    args = parser.parse_args(argv)
    queue = json.loads(Path(args.queue).read_text(encoding="utf-8"))
    absent = {int(value) for value in args.verified_label_absent.split(",") if value.strip()}
    payload = decisions_from_review_queue(queue, reviewer=args.reviewer, reviewed_at=args.reviewed_at, verified_absent_pages=absent)
    output = save_private_printed_page_decisions(payload, args.output)
    print(json.dumps({"output": str(output), "decision_count": len(payload["decisions"]), "verified_absent_count": len(absent)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
