from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from law_rag.domain.models import LegalProvision
from law_rag.ingestion.corpus_writer import merge_corpus, replace_corpus
from law_rag.ingestion.json_source import JsonLegalDocumentSource
from law_rag.ingestion.official_source import OfficialKoreanLawSource, OfficialLawApiError


@dataclass(frozen=True, slots=True)
class LawSyncItem:
    domain_id: str
    law_name: Optional[str] = None
    law_id: Optional[str] = None
    enabled: bool = True

    @classmethod
    def from_dict(cls, value: dict) -> "LawSyncItem":
        domain_id = str(value.get("domain_id") or value.get("domain") or "").strip()
        law_name = str(value.get("law_name") or "").strip() or None
        law_id = str(value.get("law_id") or "").strip() or None
        if not domain_id:
            raise ValueError("manifest 항목에는 domain_id가 필요합니다.")
        if not law_name and not law_id:
            raise ValueError("manifest 항목에는 law_name 또는 law_id가 필요합니다.")
        return cls(domain_id=domain_id, law_name=law_name, law_id=law_id, enabled=bool(value.get("enabled", True)))


@dataclass(frozen=True, slots=True)
class LawSyncManifest:
    laws: tuple[LawSyncItem, ...]

    @classmethod
    def load(cls, path: str | Path) -> "LawSyncManifest":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        raw_laws = payload.get("laws") if isinstance(payload, dict) else payload
        if not isinstance(raw_laws, list):
            raise ValueError("manifest는 laws 배열 또는 배열 자체여야 합니다.")
        return cls(tuple(LawSyncItem.from_dict(item) for item in raw_laws if isinstance(item, dict)))


class OfficialCorpusSynchronizer:
    """Synchronize multiple official laws into one normalized corpus.

    A successful remote response is stored as normalized JSON cache. If a later
    API call fails, the cache can be used explicitly to keep local development
    and CI reproducible without silently treating stale data as fresh.
    """

    def __init__(self, source: Optional[OfficialKoreanLawSource] = None) -> None:
        self.source = source or OfficialKoreanLawSource()

    @staticmethod
    def _cache_key(item: LawSyncItem) -> str:
        raw = item.law_id or item.law_name or "law"
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in raw)
        return f"{item.domain_id}__{safe}.json"

    @staticmethod
    def _write_cache(path: Path, provisions: Iterable[LegalProvision]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "provisions": [item.to_dict() for item in provisions],
        }
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)

    @staticmethod
    def _read_cache(path: Path) -> list[LegalProvision]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = payload.get("provisions", [])
        source = JsonLegalDocumentSource()
        return [source.normalize(record, index) for index, record in enumerate(records)]

    def sync(
        self,
        manifest: LawSyncManifest,
        *,
        oc: str,
        output: str | Path,
        cache_dir: str | Path = "data/official_cache",
        search_url: str,
        service_url: str,
        timeout: int = 20,
        allow_cache_fallback: bool = False,
        merge_output: bool = False,
    ) -> dict:
        cache_root = Path(cache_dir)
        collected: list[LegalProvision] = []
        items: list[dict] = []
        failures: list[dict] = []

        for item in manifest.laws:
            if not item.enabled:
                items.append({"law_name": item.law_name, "law_id": item.law_id, "status": "skipped"})
                continue
            cache_path = cache_root / self._cache_key(item)
            try:
                if item.law_id:
                    provisions = self.source.fetch_by_id(
                        law_id=item.law_id,
                        domain_id=item.domain_id,
                        oc=oc,
                        service_url=service_url,
                        timeout=timeout,
                    )
                    resolved_id = item.law_id
                    resolved_name = provisions[0].law_name if provisions else item.law_name
                else:
                    record, provisions = self.source.fetch_by_name(
                        law_name=item.law_name or "",
                        domain_id=item.domain_id,
                        oc=oc,
                        search_url=search_url,
                        service_url=service_url,
                        timeout=timeout,
                    )
                    resolved_id = record.law_id
                    resolved_name = record.law_name
                self._write_cache(cache_path, provisions)
                status = "fetched"
            except OfficialLawApiError as exc:
                if not allow_cache_fallback or not cache_path.exists():
                    failures.append({"law_name": item.law_name, "law_id": item.law_id, "error": str(exc)})
                    continue
                provisions = self._read_cache(cache_path)
                resolved_id = provisions[0].law_id if provisions else item.law_id
                resolved_name = provisions[0].law_name if provisions else item.law_name
                status = "cached"

            collected.extend(provisions)
            items.append({
                "law_name": resolved_name,
                "law_id": resolved_id,
                "domain_id": item.domain_id,
                "status": status,
                "provisions": len(provisions),
                "cache_path": str(cache_path),
            })

        if failures:
            raise OfficialLawApiError("법령 동기화 실패: " + json.dumps(failures, ensure_ascii=False))
        if not collected:
            raise OfficialLawApiError("동기화된 법령 조문이 없습니다.")

        merge_result = merge_corpus(str(output), collected) if merge_output else replace_corpus(str(output), collected)
        return {
            "status": "completed",
            "laws": items,
            "fetched_laws": sum(1 for item in items if item["status"] == "fetched"),
            "cached_laws": sum(1 for item in items if item["status"] == "cached"),
            "parsed_provisions": len(collected),
            "corpus": merge_result,
        }
