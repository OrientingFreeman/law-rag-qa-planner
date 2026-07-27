from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from law_rag.ingestion.corpus_writer import merge_corpus
from law_rag.ingestion.sync import LawSyncManifest, OfficialCorpusSynchronizer
from law_rag.ingestion.official_source import (
    DEFAULT_SEARCH_URL,
    DEFAULT_SERVICE_URL,
    OfficialKoreanLawSource,
    OfficialLawApiError,
)


def _write_preview(path: str, provisions) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps([provision.to_dict() for provision in provisions], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="공식 법령 XML 검색·수집·정규화")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--xml", help="로컬 법령 XML 파일")
    source.add_argument("--law-id", help="국가법령정보센터 법령 ID")
    source.add_argument("--law-name", help="정확한 법령명. 목록 API에서 ID를 확인한 뒤 본문을 수집")
    source.add_argument("--manifest", help="여러 법령을 동기화할 JSON manifest")
    parser.add_argument("--domain", help="단건 수집 시 도메인 ID")
    parser.add_argument("--cache-dir", default=os.getenv("LAW_API_CACHE_DIR", "data/official_cache"))
    parser.add_argument("--allow-cache-fallback", action="store_true")
    parser.add_argument("--output", default="data/legal_corpus.json")
    parser.add_argument("--merge-output", action="store_true", help="manifest 결과를 기존 코퍼스에 병합합니다. 기본값은 manifest 스냅샷으로 교체입니다.")
    parser.add_argument("--preview", help="기존 코퍼스에 병합하지 않고 정규화 결과만 저장")
    parser.add_argument("--search-url", default=os.getenv("LAW_API_SEARCH_URL", DEFAULT_SEARCH_URL))
    parser.add_argument("--service-url", default=os.getenv("LAW_API_SERVICE_URL", DEFAULT_SERVICE_URL))
    parser.add_argument("--base-url", default=os.getenv("LAW_API_BASE_URL"), help=argparse.SUPPRESS)
    parser.add_argument("--oc", default=os.getenv("LAW_API_OC"))
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()

    adapter = OfficialKoreanLawSource()
    resolved = None
    try:
        if args.manifest:
            if not args.oc:
                parser.error("원격 동기화에는 --oc 또는 LAW_API_OC가 필요합니다.")
            result = OfficialCorpusSynchronizer(adapter).sync(
                LawSyncManifest.load(args.manifest),
                oc=args.oc, output=args.output, cache_dir=args.cache_dir,
                search_url=args.search_url, service_url=args.base_url or args.service_url,
                timeout=args.timeout, allow_cache_fallback=args.allow_cache_fallback,
                merge_output=args.merge_output,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if not args.domain:
            parser.error("단건 수집에는 --domain이 필요합니다.")
        if args.xml:
            provisions = adapter.load_file(args.xml, domain_id=args.domain)
        else:
            if not args.oc:
                parser.error("원격 수집에는 --oc 또는 LAW_API_OC가 필요합니다.")
            service_url = args.base_url or args.service_url
            if args.law_name:
                resolved, provisions = adapter.fetch_by_name(
                    law_name=args.law_name,
                    domain_id=args.domain,
                    oc=args.oc,
                    search_url=args.search_url,
                    service_url=service_url,
                    timeout=args.timeout,
                )
            else:
                provisions = adapter.fetch_by_id(
                    law_id=args.law_id,
                    domain_id=args.domain,
                    oc=args.oc,
                    service_url=service_url,
                    timeout=args.timeout,
                )
    except OfficialLawApiError as exc:
        raise SystemExit("수집 실패: {}".format(exc)) from exc

    if not provisions:
        raise SystemExit("파싱된 조문이 없습니다. XML 구조, 법령명 또는 법령 ID를 확인하세요.")

    if args.preview:
        _write_preview(args.preview, provisions)
        result = {"mode": "preview", "path": args.preview, "total": len(provisions)}
    else:
        result = merge_corpus(args.output, provisions)
        result["mode"] = "merge"
    result["parsed"] = len(provisions)
    result["law_id"] = provisions[0].law_id
    result["law_name"] = provisions[0].law_name
    if resolved:
        result["resolved_law_id"] = resolved.law_id
        result["resolved_effective_date"] = resolved.effective_date.isoformat() if resolved.effective_date else None
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
