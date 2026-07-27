from __future__ import annotations

from law_rag.domain.models import SearchResult
from law_rag.ontology import DEFAULT_LEGAL_ONTOLOGY, LegalOntology

_SCOPE_TERMS = (
    "영상정보", "고정형 영상정보처리기기", "이동형 영상정보처리기기",
    "공공기관", "아동", "생체정보", "신용정보", "유전정보", "범죄경력",
)

# These aliases are too generic to establish a legal issue by themselves.
_GENERIC_INHERITED_ALIASES = {"목적", "공개", "책임", "인증", "동의", "계약"}

def _target_concepts(plan: object) -> set[str]:
    ontology = getattr(plan, "ontology", {}) or {}
    rows = ontology.get("concepts", []) if isinstance(ontology, dict) else []
    targets = {str(r.get("concept_id")) for r in rows if isinstance(r, dict) and r.get("category") == "legal_act"}
    return targets

def matched_issue_ids(result: SearchResult, plan: object, *, ontology: LegalOntology = DEFAULT_LEGAL_ONTOLOGY) -> set[str]:
    """Return legal-act issues actually established by an evidence unit.

    A descendant concept may establish its parent issue only when it matched a
    sufficiently specific alias. This prevents generic words such as ``목적``
    from turning unrelated provisions into processing-delegation evidence.
    """
    targets = _target_concepts(plan)
    if not targets:
        return set()
    p = result.provision
    searchable = " ".join(filter(None, [p.article_title, p.topic, p.text]))
    matches = ontology.match_text(searchable)
    issues: set[str] = set()
    for match in matches:
        if match.concept_id in targets and match.category == "legal_act":
            issues.add(match.concept_id)
            continue
        parent_id = match.parent_id
        specific_aliases = {
            alias.strip() for alias in match.matched_aliases
            if alias.strip() and alias.strip() not in _GENERIC_INHERITED_ALIASES and len(alias.strip()) >= 3
        }
        if parent_id in targets and specific_aliases:
            issues.add(parent_id)
    return issues


def ontology_alignment(result: SearchResult, plan: object, *, ontology: LegalOntology = DEFAULT_LEGAL_ONTOLOGY) -> tuple[float, set[str]]:
    targets = _target_concepts(plan)
    if not targets:
        return 0.5, set()
    p = result.provision
    searchable = " ".join(filter(None, [p.article_title, p.topic, p.text]))
    matched = {m.concept_id for m in ontology.match_text(searchable)}
    inherited = matched_issue_ids(result, plan, ontology=ontology)
    direct = targets.intersection(matched)
    coverage = len(inherited) / len(targets)
    if direct:
        score = min(1.0, 0.78 + 0.22 * coverage)
    elif inherited:
        score = 0.62 + 0.20 * coverage
    else:
        score = 0.0
    return score, matched

def rerank_with_ontology(question: str, plan: object, results: list[SearchResult], *, ontology: LegalOntology = DEFAULT_LEGAL_ONTOLOGY) -> list[SearchResult]:
    if not results:
        return []
    for result in results:
        alignment, matched = ontology_alignment(result, plan, ontology=ontology)
        result.ontology_score = alignment
        targets = _target_concepts(plan)
        issues = matched_issue_ids(result, plan, ontology=ontology)
        issue_coverage = len(issues) / len(targets) if targets else 1.0
        result.issue_coverage_score = issue_coverage
        text = " ".join(filter(None, [result.provision.article_title, result.provision.text]))
        mismatch = any(term in text and term not in question for term in _SCOPE_TERMS)
        # calibrated weighted score: preserve distinctions and avoid saturation
        base = max(0.0, min(result.score, 1.0))
        if not targets:
            result.score = min(base, 0.995)
            continue
        calibrated = base * 0.68 + alignment * 0.22 + issue_coverage * 0.10
        if alignment == 0.0:
            calibrated *= 0.58
        if mismatch:
            calibrated *= 0.48
        result.score = max(0.0, min(calibrated, 0.995))
    results.sort(key=lambda x: (x.score, x.semantic_score, x.lexical_score), reverse=True)
    for rank, result in enumerate(results, 1): result.rank = rank
    return results

def ensure_compound_concept_coverage(plan: object, results: list[SearchResult], *, limit: int, ontology: LegalOntology = DEFAULT_LEGAL_ONTOLOGY) -> list[SearchResult]:
    targets = list(_target_concepts(plan))
    if len(targets) < 2 or not results: return results[:limit]
    selected=[]; ids=set()
    for target in targets:
        candidates=[]
        for result in results:
            ontology_alignment(result, plan, ontology=ontology)
            if target in matched_issue_ids(result, plan, ontology=ontology):
                candidates.append(result)
        if candidates:
            result=max(candidates, key=lambda x:x.score)
            if result.provision.document_id not in ids:
                selected.append(result); ids.add(result.provision.document_id)
    for result in results:
        if len(selected)>=limit: break
        if result.provision.document_id not in ids:
            selected.append(result); ids.add(result.provision.document_id)
    selected.sort(key=lambda x:x.score, reverse=True)
    for rank,result in enumerate(selected[:limit],1): result.rank=rank
    return selected[:limit]



def annotate_ontology_metadata(plan: object, results: list[SearchResult], *, ontology: LegalOntology = DEFAULT_LEGAL_ONTOLOGY) -> list[SearchResult]:
    """Refresh ontology metadata without changing retrieval scores or order."""
    targets = _target_concepts(plan)
    for result in results:
        alignment, _ = ontology_alignment(result, plan, ontology=ontology)
        issues = matched_issue_ids(result, plan, ontology=ontology)
        result.ontology_score = alignment
        result.issue_coverage_score = len(issues) / len(targets) if targets else 1.0
        result.issue_ids = sorted(issues)
    return results

def filter_graph_evidence(plan: object, results: list[SearchResult]) -> list[SearchResult]:
    """Remove candidates that cannot be connected to a requested issue.

    Explicit graph-related retrievals are retained only when the retriever has
    supplied a positive legal relation score.
    """
    targets = _target_concepts(plan)
    if not targets:
        return results
    kept = [
        result for result in results
        if result.issue_coverage_score > 0.0 or result.relation_score > 0.0
    ]
    for rank, result in enumerate(kept, 1):
        result.rank = rank
    return kept
