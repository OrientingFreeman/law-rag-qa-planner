from copy import deepcopy

import pytest

from tools.evaluate_legal_knowledge_base import (
    DEFAULT_CASES,
    DEFAULT_CORPUS,
    DEFAULT_KB,
    evaluate,
    load_json,
    predict,
    validate_cases,
)


def _fixtures():
    return load_json(DEFAULT_CASES), load_json(DEFAULT_KB), load_json(DEFAULT_CORPUS)


def test_dataset_has_30_unique_structured_cases():
    cases, kb, corpus = _fixtures()
    assert len(cases) == 30
    assert len({case["case_id"] for case in cases}) == 30
    assert validate_cases(cases, kb, corpus) == []


def test_explicit_lay_term_maps_to_expected_concept():
    _, kb, _ = _fixtures()
    result = predict("알바생이 근로기준법상 어떤 개념인가요?", "2026-08-04", kb)
    assert result["concept_id"] == "labor_worker"
    assert result["article_refs"] == ["제2조"]


def test_longer_specific_mapping_beats_competing_legal_term():
    _, kb, _ = _fixtures()
    result = predict("외주업체에 고객정보 맡기기는 제3자 제공과 어떻게 다른가요?", "2026-08-04", kb)
    assert result["concept_id"] == "pipa_processing_delegation"


def test_unknown_expression_abstains():
    _, kb, _ = _fixtures()
    result = predict("종합소득세 신고기한은 언제인가요?", "2026-08-04", kb)
    assert result["abstained"] is True
    assert result["reason"] == "no_active_explicit_mapping"


def test_mapping_before_effective_period_abstains():
    _, kb, _ = _fixtures()
    result = predict("개인정보의 수집·이용 근거는?", "2025-09-01", kb)
    assert result["abstained"] is True


def test_invalid_abstention_gold_is_rejected():
    cases, kb, corpus = _fixtures()
    broken = deepcopy(cases)
    broken[-1]["expected_concept_ids"] = ["pipa_collection_use"]
    assert any("abstention case must not contain gold" in error for error in validate_cases(broken, kb, corpus))


def test_unknown_gold_concept_is_rejected():
    cases, kb, corpus = _fixtures()
    broken = deepcopy(cases)
    broken[0]["expected_concept_ids"] = ["not_a_concept"]
    assert any("unknown concepts" in error for error in validate_cases(broken, kb, corpus))


def test_evaluation_produces_declared_metrics():
    cases, kb, corpus = _fixtures()
    report = evaluate(cases, kb, corpus)
    assert report["evaluation_mode"] == "deterministic_explicit_vocabulary_lookup"
    assert set(report["metrics"]) == {
        "case_count", "answerable_case_count", "abstention_case_count",
        "overall_exact_match", "concept_top1_accuracy", "article_precision",
        "article_recall", "abstention_accuracy", "temporal_accuracy",
    }
    assert len(report["details"]) == len(cases)
