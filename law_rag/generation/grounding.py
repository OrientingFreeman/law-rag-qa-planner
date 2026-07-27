from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from law_rag.domain.models import SearchResult
from law_rag.generation.article_refs import extract_article_refs
from law_rag.ontology import DEFAULT_LEGAL_ONTOLOGY, OntologyMatch

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。])\s+|\n+")
_KOREAN_TOKEN = re.compile(r"[가-힣A-Za-z0-9]{2,}")
_LEGAL_SIGNAL = re.compile(r"(해야|하여야|할 수|금지|의무|요건|기간|책임|처벌|위반|따라|근거|포함|제공|동의)")
_META_SENTENCE = re.compile(r"^(결론|판단 순서|실무 체크리스트|쟁점별 법적 판단|적용 요건과 예외|실무상 조치|근거 조문|적용 규정(?:과 추론)?|핵심 항목·요건|예외·주의사항|추가 확인 사실|확인 한계|질문:|\[[^\]]+\]$|\d+\.\s*(?:처리위탁|국외 이전|공통)|처리위탁 계약과 수탁자 관리$|국외 이전 근거와 고지·동의$|공통 확인사항$)|추가 확인|추가 사실 확인|별도로 확인|단정하지|답변 한계|검색된 근거|검색된 법령 근거상|질문과 직접 관련된 요건|질문의 사실관계에 이 쟁점이 포함|본 답변은 .*일반적인 .*안내|실제 적용 시에는 .*종합적으로 검토|개별 사건의 .*달라질 수")
_STOPWORDS = {
    "개인정보", "보호법", "시행령", "따라", "대한", "관한", "사항", "경우", "해당",
    "그리고", "또는", "있습니다", "합니다", "해야", "하여야", "법적", "근거",
}


@dataclass(frozen=True)
class EvidenceUnit:
    citation: str
    article_no: str
    document_id: str
    text: str
    tokens: set[str]
    scope: str
    instrument_type: str
    semantic_labels: tuple[str, ...]





def _semantic_labels(text: str) -> tuple[str, ...]:
    return tuple(
        match.concept_id for match in DEFAULT_LEGAL_ONTOLOGY.match_text(text)
        if match.category != "legal_act"
    )

def _semantic_label_names(labels: Iterable[str]) -> list[str]:
    names: list[str] = []
    for label in labels:
        concept = DEFAULT_LEGAL_ONTOLOGY.get(label)
        names.append(concept.label if concept else label)
    return names

def _ontology_annotation(labels: Iterable[str]) -> dict[str, object]:
    matches: list[OntologyMatch] = []
    for label in labels:
        concept = DEFAULT_LEGAL_ONTOLOGY.get(label)
        if not concept:
            continue
        matches.append(OntologyMatch(
            concept_id=concept.concept_id,
            label=concept.label,
            category=concept.category,
            matched_aliases=(),
            confidence=1.0,
            parent_id=concept.parent_id,
            related_ids=concept.related_ids,
        ))
    return DEFAULT_LEGAL_ONTOLOGY.describe_matches(matches)

def _semantic_assignment(
    unit: EvidenceUnit,
    *,
    claim_labels: set[str],
    primary: EvidenceUnit | None,
    overlap: float,
    citation_supported: bool,
) -> tuple[bool, str, float]:
    unit_labels = set(unit.semantic_labels)
    shared = claim_labels & unit_labels
    if primary and unit.document_id == primary.document_id:
        confidence = max(overlap, 0.9 if shared else 0.72)
        return True, "primary_semantic_match" if shared else "primary_lexical_match", confidence
    if primary and _same_evidence_family(unit, primary):
        if unit.scope == "provision" and primary.scope == "sub_provision":
            return True, "hierarchical_parent", max(overlap, 0.82)
        if shared:
            return True, "same_family_semantic_match", max(overlap, 0.76)
        return False, "same_article_context_only", min(max(overlap, 0.15), 0.49)
    if shared:
        base = 0.78 if unit.instrument_type == "act" else 0.74
        return True, "implementing_semantic_match" if unit.instrument_type != "act" else "semantic_match", max(overlap, base)
    if citation_supported and overlap >= 0.32:
        return True, "lexical_match_within_cited_article", min(0.75, 0.5 + overlap / 2)
    return False, "context_preserved_not_assigned", min(max(overlap, 0.05), 0.45)


def _instrument_type(citation: str) -> str:
    if "시행규칙" in citation:
        return "enforcement_rule"
    if "시행령" in citation:
        return "enforcement_decree"
    return "act"


def _same_evidence_family(left: EvidenceUnit, right: EvidenceUnit) -> bool:
    return (
        left.document_id == right.document_id
        or left.document_id.startswith(f"{right.document_id}:")
        or right.document_id.startswith(f"{left.document_id}:")
    )


def _evidence_role(
    unit: EvidenceUnit,
    *,
    primary: EvidenceUnit | None,
    sentence: str,
    overlap: float,
) -> str:
    if primary is None:
        return "related"
    if unit.document_id == primary.document_id:
        return "primary"
    if unit.instrument_type in {"enforcement_decree", "enforcement_rule"}:
        return "implementing_regulation"
    if _same_evidence_family(unit, primary):
        if unit.scope == "provision" and primary.scope == "sub_provision":
            return "parent"
        if unit.scope == "sub_provision" and primary.scope == "provision":
            return "child"
        return "related"
    if unit.citation and unit.citation in sentence:
        return "primary"
    if overlap <= 0:
        return "related"
    return "supporting"

def _tokens(text: str) -> set[str]:
    return {token.lower() for token in _KOREAN_TOKEN.findall(text) if token not in _STOPWORDS}


def _evidence_units(results: Iterable[SearchResult]) -> list[EvidenceUnit]:
    evidence: list[EvidenceUnit] = []
    for result in results:
        provision = result.provision
        evidence.append(EvidenceUnit(
            citation=provision.citation_label(),
            article_no=provision.article_no.replace(" ", ""),
            document_id=provision.document_id,
            text=provision.text.strip(),
            tokens=_tokens(provision.text),
            scope="provision",
            instrument_type=_instrument_type(provision.citation_label()),
            semantic_labels=_semantic_labels(provision.text),
        ))
        for item in result.sub_provisions:
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            evidence.append(EvidenceUnit(
                citation=str(item.get("citation") or provision.citation_label()),
                article_no=provision.article_no.replace(" ", ""),
                document_id=str(item.get("document_id") or provision.document_id),
                text=text,
                tokens=_tokens(text),
                scope="sub_provision",
                instrument_type=_instrument_type(str(item.get("citation") or provision.citation_label())),
                semantic_labels=_semantic_labels(text),
            ))
    return evidence


def _best_unit(sentence_tokens: set[str], units: list[EvidenceUnit]) -> tuple[EvidenceUnit | None, float]:
    best: EvidenceUnit | None = units[0] if units else None
    best_overlap = 0.0
    for unit in units:
        overlap = (
            len(sentence_tokens & unit.tokens) / max(1, len(sentence_tokens))
            if sentence_tokens else 0.0
        )
        if overlap > best_overlap:
            best = unit
            best_overlap = overlap
    return best, best_overlap



def _supporting_units(
    sentence_tokens: set[str],
    units: list[EvidenceUnit],
    *,
    citation_supported: bool,
    limit: int = 8,
) -> list[tuple[EvidenceUnit, float]]:
    scored = []
    for unit in units:
        overlap = len(sentence_tokens & unit.tokens) / max(1, len(sentence_tokens)) if sentence_tokens else 0.0
        scored.append((unit, overlap))
    scored.sort(key=lambda row: (row[1], row[0].scope == "sub_provision"), reverse=True)
    positive = [row for row in scored if row[1] > 0]
    if citation_supported:
        # Legal audit output preserves the complete cited-article evidence set (within the
        # deterministic safety limit). Low-overlap rows remain visible but are classified
        # as parent, implementing regulation, or related rather than silently discarded.
        return scored[:limit]
    if positive:
        return positive[:limit]
    return []

def validate_grounding(answer: str, results: list[SearchResult]) -> dict[str, object]:
    """Validate legal claims and expose a deterministic claim-to-evidence audit trail.

    An explicit citation is supported only when its article exists in retrieved evidence. The
    validator still selects the most relevant paragraph or sub-provision so every supported claim
    records a citation, document ID, exact source excerpt, and support method.
    """
    evidence = _evidence_units(results)
    claim_rows: list[dict[str, object]] = []
    for raw in _SENTENCE_SPLIT.split(answer.strip()):
        sentence = raw.strip(" -•\t")
        if len(sentence) < 8 or _META_SENTENCE.search(sentence) or not _LEGAL_SIGNAL.search(sentence):
            continue

        claim_id = f"C{len(claim_rows) + 1}"
        cited_articles = set(extract_article_refs(sentence))
        sentence_tokens = _tokens(sentence)
        cited_units = [unit for unit in evidence if unit.article_no in cited_articles]
        candidate_units = cited_units or evidence
        best_unit, best_overlap = _best_unit(sentence_tokens, candidate_units)

        citation_supported = bool(cited_units)
        lexical_supported = best_overlap >= 0.32
        supported = citation_supported or lexical_supported
        support_method = (
            "explicit_citation"
            if citation_supported
            else "lexical_overlap"
            if lexical_supported
            else "unsupported"
        )
        supporting_units = _supporting_units(
            sentence_tokens, candidate_units, citation_supported=citation_supported
        ) if supported else []
        primary_unit = supporting_units[0][0] if supporting_units else best_unit
        claim_labels = set(_semantic_labels(sentence))
        supporting_evidence = []
        for unit, overlap in supporting_units:
            assigned, assignment_reason, assignment_confidence = _semantic_assignment(
                unit,
                claim_labels=claim_labels,
                primary=primary_unit,
                overlap=overlap,
                citation_supported=citation_supported,
            )
            role = _evidence_role(unit, primary=primary_unit, sentence=sentence, overlap=overlap)
            if not assigned and role not in {"parent"}:
                role = "contextual"
            supporting_evidence.append({
                "citation": unit.citation,
                "source_document_id": unit.document_id,
                "source_excerpt": unit.text,
                "evidence_scope": unit.scope,
                "instrument_type": unit.instrument_type,
                "overlap_score": round(overlap, 4),
                "role": role,
                "semantic_labels": _semantic_label_names(unit.semantic_labels),
                "semantic_label_ids": list(unit.semantic_labels),
                "ontology": _ontology_annotation(unit.semantic_labels),
                "assigned": assigned,
                "assignment_reason": assignment_reason,
                "assignment_confidence": round(assignment_confidence, 4),
            })
        assigned_evidence = [row for row in supporting_evidence if row["assigned"]]

        claim_rows.append({
            "claim_id": claim_id,
            "sentence": sentence,
            "supported": supported,
            "support_method": support_method,
            "supporting_citation": best_unit.citation if supported and best_unit else None,
            "supporting_citations": [row["citation"] for row in supporting_evidence],
            "supporting_evidence": supporting_evidence,
            "assigned_evidence": assigned_evidence,
            "semantic_labels": _semantic_label_names(claim_labels),
            "semantic_label_ids": sorted(claim_labels),
            "ontology": _ontology_annotation(sorted(claim_labels)),
            "source_document_id": best_unit.document_id if supported and best_unit else None,
            "source_excerpt": best_unit.text if supported and best_unit else None,
            "evidence_scope": best_unit.scope if supported and best_unit else None,
            "overlap_score": round(best_overlap, 4),
            "explicit_citation": bool(cited_articles),
            "cited_articles": sorted(cited_articles),
        })

    supported_count = sum(1 for row in claim_rows if row["supported"])
    total = len(claim_rows)
    coverage = round(supported_count / total, 4) if total else 1.0
    unsupported = [str(row["sentence"]) for row in claim_rows if not row["supported"]]
    return {
        "valid": not unsupported,
        "claim_count": total,
        "supported_claim_count": supported_count,
        "coverage": coverage,
        "unsupported_claims": unsupported,
        "claims": claim_rows,
        "audit": {
            "traceable_claim_count": sum(
                1 for row in claim_rows
                if row["supported"] and row["supporting_citation"] and row["source_document_id"]
            ),
            "supported_evidence_count": sum(len(row.get("supporting_evidence", [])) for row in claim_rows),
            "multi_source_claim_count": sum(1 for row in claim_rows if len(row.get("supporting_evidence", [])) > 1),
            "assigned_evidence_count": sum(len(row.get("assigned_evidence", [])) for row in claim_rows),
            "contextual_evidence_count": sum(
                1 for row in claim_rows for evidence_row in row.get("supporting_evidence", [])
                if not evidence_row.get("assigned", False)
            ),
            "semantic_assignment_coverage": round(
                sum(1 for row in claim_rows if row.get("assigned_evidence")) / max(1, len(claim_rows)), 4
            ),
            "evidence_role_counts": {
                role: sum(
                    1
                    for row in claim_rows
                    for evidence_row in row.get("supporting_evidence", [])
                    if evidence_row.get("role") == role
                )
                for role in (
                    "primary", "parent", "child", "implementing_regulation",
                    "supporting", "related", "contextual"
                )
            },
            "fully_traceable": all(
                (not row["supported"]) or (
                    row["supporting_citation"] is not None
                    and row["source_document_id"] is not None
                    and row["source_excerpt"] is not None
                )
                for row in claim_rows
            ),
        },
    }
