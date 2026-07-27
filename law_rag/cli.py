from __future__ import annotations

import argparse
import json
from datetime import date

from law_rag.service import LawRagService


def main() -> None:
    parser = argparse.ArgumentParser(description="확장형 법령 RAG 검색 데모")
    parser.add_argument("question", help="검색 질문")
    parser.add_argument("--domain", default="all", help="도메인 ID")
    parser.add_argument("--as-of", dest="as_of", help="기준일 YYYY-MM-DD")
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--data", default="data/legal_corpus.json")
    args = parser.parse_args()

    service = LawRagService(data_path=args.data)
    result = service.query(
        args.question,
        domain_id=args.domain,
        top_k=args.top_k,
        as_of_date=date.fromisoformat(args.as_of) if args.as_of else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
