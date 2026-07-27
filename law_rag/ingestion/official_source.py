from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from law_rag.domain.models import LegalProvision
from law_rag.ingestion.xml_parser import KoreanLawXmlParser

DEFAULT_SEARCH_URL = "https://www.law.go.kr/DRF/lawSearch.do"
DEFAULT_SERVICE_URL = "https://www.law.go.kr/DRF/lawService.do"


class OfficialLawApiError(RuntimeError):
    """Raised when the official API cannot return a usable law payload."""


@dataclass(frozen=True, slots=True)
class LawSearchRecord:
    law_id: str
    law_name: str
    mst: Optional[str] = None
    current_history_code: Optional[str] = None
    promulgation_date: Optional[date] = None
    effective_date: Optional[date] = None
    ministry: Optional[str] = None
    detail_link: Optional[str] = None


def _clean(value: Optional[str]) -> str:
    """Normalize CDATA/text whitespace and Unicode compatibility forms."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value or "")).strip()


def _normalized_law_name(value: str) -> str:
    return re.sub(r"\s+", "", _clean(value))


def _tag(node: ET.Element) -> str:
    return node.tag.split("}")[-1]


def _child_text(node: ET.Element, names: set[str]) -> Optional[str]:
    for child in node.iter():
        if _tag(child) in names:
            text = _clean("".join(child.itertext()))
            if text:
                return text
    return None


def _parse_date(value: Optional[str]) -> Optional[date]:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) != 8:
        return None
    try:
        return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
    except ValueError:
        return None


def _redact_url(url: str) -> str:
    """Remove OC from URLs before persistence, logs, and diagnostics."""
    try:
        parts = urlsplit(url)
        safe_query = urlencode(
            [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key.upper() != "OC"]
        )
        return urlunsplit((parts.scheme, parts.netloc, parts.path, safe_query, parts.fragment))
    except ValueError:
        return re.sub(r"([?&])OC=[^&#\s]*", r"\1OC=[REDACTED]", url, flags=re.IGNORECASE)


def _redact_text(value: object) -> str:
    text = str(value)
    text = re.sub(r"([?&])OC=[^&#\s'\"]*", r"\1OC=[REDACTED]", text, flags=re.IGNORECASE)
    text = re.sub(r"\bOC\s*[=:]\s*[^,;\s'\"]+", "OC=[REDACTED]", text, flags=re.IGNORECASE)
    return text


def _public_url(base_url: str, params: dict[str, str]) -> str:
    safe = {key: value for key, value in params.items() if key.upper() != "OC"}
    return base_url + ("&" if "?" in base_url else "?") + urlencode(safe)


class OfficialKoreanLawSource:
    """Client for the Korean Ministry of Government Legislation Open API."""

    def __init__(
        self,
        parser: Optional[KoreanLawXmlParser] = None,
        transport: Optional[Callable[[str, int], bytes]] = None,
    ) -> None:
        self.parser = parser or KoreanLawXmlParser()
        self.transport = transport or self._download

    @staticmethod
    def _download(url: str, timeout: int) -> bytes:
        request = Request(url, headers={"User-Agent": "law-rag-qa-planner/1.4.2"})
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.read()
        except HTTPError as exc:
            raise OfficialLawApiError("국가법령정보 API가 HTTP {} 오류를 반환했습니다.".format(exc.code)) from exc
        except URLError as exc:
            raise OfficialLawApiError("국가법령정보 API에 연결할 수 없습니다: {}".format(_redact_text(exc.reason))) from exc

    @staticmethod
    def _request_url(base_url: str, params: dict[str, str]) -> str:
        return base_url + ("&" if "?" in base_url else "?") + urlencode(params)

    def _transport(self, url: str, timeout: int) -> bytes:
        try:
            return self.transport(url, timeout)
        except OfficialLawApiError as exc:
            raise OfficialLawApiError(_redact_text(exc)) from exc
        except Exception as exc:
            raise OfficialLawApiError("국가법령정보 API 요청 실패: {}".format(_redact_text(exc))) from exc

    @staticmethod
    def _validate_xml(payload: bytes, *, operation: str, require_search_meta: bool = False) -> ET.Element:
        if not payload.strip():
            raise OfficialLawApiError("{} 응답이 비어 있습니다.".format(operation))
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as exc:
            preview = _redact_text(payload[:160].decode("utf-8", errors="replace"))
            raise OfficialLawApiError("{} 응답이 XML이 아닙니다: {!r}".format(operation, preview)) from exc

        result_code = _child_text(root, {"resultCode"})
        result_msg = _child_text(root, {"resultMsg"})
        if result_code and result_code != "00":
            raise OfficialLawApiError("{} 실패(resultCode={}): {}".format(operation, result_code, result_msg or "메시지 없음"))

        if require_search_meta:
            total_text = _child_text(root, {"totalCnt"})
            if total_text is None:
                raise OfficialLawApiError("{} 응답에 totalCnt가 없습니다.".format(operation))
            try:
                total = int(total_text.replace(",", ""))
            except ValueError as exc:
                raise OfficialLawApiError("{} 응답의 totalCnt가 정수가 아닙니다: {!r}".format(operation, total_text)) from exc
            if total < 0:
                raise OfficialLawApiError("{} 응답의 totalCnt가 음수입니다: {}".format(operation, total))

        error_text = _child_text(root, {"error", "오류", "message", "메시지"})
        if error_text:
            raise OfficialLawApiError("{} 실패: {}".format(operation, error_text))
        return root

    def load_file(self, path: str, *, domain_id: str, source_url: Optional[str] = None) -> list[LegalProvision]:
        xml_bytes = Path(path).read_bytes()
        return self.parser.parse(
            xml_bytes,
            domain_id=domain_id,
            source_url=_redact_url(source_url or Path(path).resolve().as_uri()),
            checked_at=date.today(),
        )

    def search_laws(
        self,
        *,
        query: str,
        oc: str,
        search_url: str = DEFAULT_SEARCH_URL,
        display: int = 20,
        timeout: int = 20,
    ) -> list[LawSearchRecord]:
        params = {
            "OC": oc,
            "target": "law",
            "type": "XML",
            "search": "1",
            "query": query,
            "display": str(max(1, min(display, 100))),
        }
        payload = self._transport(self._request_url(search_url, params), timeout)
        root = self._validate_xml(payload, operation="법령 목록 검색", require_search_meta=True)
        total = int((_child_text(root, {"totalCnt"}) or "0").replace(",", ""))
        records: list[LawSearchRecord] = []
        candidate_nodes = [node for node in root.iter() if _tag(node) in {"law", "법령"}]
        diagnostics: list[str] = []
        for node in candidate_nodes:
            law_id = _child_text(node, {"법령ID"})
            law_name = _child_text(node, {"법령명한글", "법령명_한글", "법령명"})
            mst = _child_text(node, {"법령일련번호"})
            if not law_id or not law_name:
                diagnostics.append(
                    "tag={} law_id={} law_name={} mst={}".format(
                        _tag(node), bool(law_id), bool(law_name), bool(mst)
                    )
                )
                continue
            detail_link = _child_text(node, {"법령상세링크"})
            records.append(
                LawSearchRecord(
                    law_id=law_id,
                    law_name=law_name,
                    mst=mst,
                    current_history_code=_child_text(node, {"현행연혁코드"}),
                    promulgation_date=_parse_date(_child_text(node, {"공포일자"})),
                    effective_date=_parse_date(_child_text(node, {"시행일자"})),
                    ministry=_child_text(node, {"소관부처명", "소관부처"}),
                    detail_link=_redact_url(detail_link) if detail_link else None,
                )
            )
        if total > 0 and not records:
            diagnostic = "; ".join(diagnostics[:5]) or "law/법령 요소를 찾지 못함"
            raise OfficialLawApiError(
                "법령 목록 검색 결과는 {}건이지만 파싱된 후보가 없습니다. 진단: {}".format(total, diagnostic)
            )
        return records

    def resolve_law(
        self,
        *,
        law_name: str,
        oc: str,
        search_url: str = DEFAULT_SEARCH_URL,
        timeout: int = 20,
    ) -> LawSearchRecord:
        records = self.search_laws(query=law_name, oc=oc, search_url=search_url, timeout=timeout)
        wanted = _normalized_law_name(law_name)
        exact = [record for record in records if _normalized_law_name(record.law_name) == wanted]
        if len(exact) == 1:
            return exact[0]
        if not exact:
            candidates = ", ".join(record.law_name for record in records[:5]) or "없음"
            raise OfficialLawApiError("정확히 일치하는 법령을 찾지 못했습니다. 검색 후보: {}".format(candidates))
        raise OfficialLawApiError("동일한 법령명 후보가 여러 건입니다. --law-id를 사용하세요.")

    def _fetch_body(
        self,
        *,
        params: dict[str, str],
        domain_id: str,
        service_url: str,
        timeout: int,
    ) -> list[LegalProvision]:
        payload = self._transport(self._request_url(service_url, params), timeout)
        self._validate_xml(payload, operation="법령 본문 조회")
        return self.parser.parse(
            payload,
            domain_id=domain_id,
            source_url=_public_url(service_url, params),
            checked_at=date.today(),
        )

    def fetch_by_id(
        self,
        *,
        law_id: str,
        domain_id: str,
        oc: str,
        service_url: str = DEFAULT_SERVICE_URL,
        timeout: int = 20,
    ) -> list[LegalProvision]:
        return self._fetch_body(
            params={"OC": oc, "target": "eflaw", "type": "XML", "ID": law_id},
            domain_id=domain_id,
            service_url=service_url,
            timeout=timeout,
        )

    def fetch_by_mst(
        self,
        *,
        mst: str,
        domain_id: str,
        oc: str,
        service_url: str = DEFAULT_SERVICE_URL,
        timeout: int = 20,
    ) -> list[LegalProvision]:
        return self._fetch_body(
            params={"OC": oc, "target": "eflaw", "type": "XML", "MST": mst},
            domain_id=domain_id,
            service_url=service_url,
            timeout=timeout,
        )

    def fetch_by_name(
        self,
        *,
        law_name: str,
        domain_id: str,
        oc: str,
        search_url: str = DEFAULT_SEARCH_URL,
        service_url: str = DEFAULT_SERVICE_URL,
        timeout: int = 20,
    ) -> tuple[LawSearchRecord, list[LegalProvision]]:
        record = self.resolve_law(law_name=law_name, oc=oc, search_url=search_url, timeout=timeout)
        if record.mst:
            provisions = self.fetch_by_mst(
                mst=record.mst,
                domain_id=domain_id,
                oc=oc,
                service_url=service_url,
                timeout=timeout,
            )
        else:
            provisions = self.fetch_by_id(
                law_id=record.law_id,
                domain_id=domain_id,
                oc=oc,
                service_url=service_url,
                timeout=timeout,
            )
        return record, provisions

    def fetch(
        self,
        *,
        base_url: str,
        law_id: str,
        domain_id: str,
        oc: Optional[str] = None,
        timeout: int = 20,
    ) -> list[LegalProvision]:
        if not oc:
            raise OfficialLawApiError("원격 수집에는 OC 인증값이 필요합니다.")
        return self.fetch_by_id(
            law_id=law_id,
            domain_id=domain_id,
            oc=oc,
            service_url=base_url,
            timeout=timeout,
        )
