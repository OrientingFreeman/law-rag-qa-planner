from law_rag.domain.models import LegalProvision, SearchResult
from law_rag.generation.composer import build_composition_plan
from law_rag.generation.planner import build_answer_plan, bind_rendered_sentences
from law_rag.reasoning.legal_argument_graph import build_legal_argument_graph
from law_rag.reasoning.multi_path import build_multi_path_reasoning


def _result(document_id: str, article_no: str, text: str, sub_provisions=None, score: float = 0.95) -> SearchResult:
    provision = LegalProvision(
        document_id=document_id,
        law_id="pipa",
        law_name="개인정보 보호법",
        article_no=article_no,
        text=text,
    )
    return SearchResult(
        provision=provision,
        score=score,
        rank=1,
        evidence_role="primary",
        sub_provisions=sub_provisions or [],
    )


def test_multi_path_separates_alternative_transfer_bases():
    results = [_result(
        "pipa:28-8", "제28조의8",
        "개인정보는 국외로 이전하여서는 아니 된다. 다만 각 호의 어느 하나에 해당하면 이전할 수 있다.",
        [
            {"document_id": "pipa:28-8:1", "citation": "개인정보 보호법 제28조의8 제1항 제1호", "text": "1. 정보주체로부터 별도 동의를 받은 경우"},
            {"document_id": "pipa:28-8:2", "citation": "개인정보 보호법 제28조의8 제1항 제2호", "text": "2. 법률 또는 조약에 특별한 규정이 있는 경우"},
            {"document_id": "pipa:28-8:3", "citation": "개인정보 보호법 제28조의8 제1항 제3호", "text": "3. 계약 이행을 위하여 처리위탁이 필요한 경우"},
        ],
    )]
    composition = build_composition_plan(results, {"actions": ["국외이전"]})
    path = {"enabled": True, "issue_order": ["cross_border_transfer"], "steps": []}
    answer_plan = bind_rendered_sentences(build_answer_plan("국외이전 근거는?", composition, path))
    graph = build_legal_argument_graph("국외이전 근거는?", composition, answer_plan, path)
    missing = {"facts": [{"fact_id": "transfer_basis", "issue_id": "cross_border_transfer"}]}

    result = build_multi_path_reasoning(
        "국외이전 근거는?", composition, path,
        legal_argument_graph=graph, missing_fact_detector=missing,
    )

    alternatives = [row for row in result["paths"] if row["path_type"] == "alternative_basis"]
    assert result["validation"]["valid"] is True
    assert len(alternatives) == 3
    assert {row["branch_key"] for row in alternatives} == {"1", "2", "3"}
    assert all(row["status"] == "conditional" for row in alternatives)


def test_multi_path_builds_cumulative_path_for_two_issues():
    results = [
        _result("pipa:28-8", "제28조의8", "국외이전은 법정 근거가 필요하다."),
        _result("pipa:26", "제26조", "처리위탁은 문서로 하여야 한다."),
    ]
    composition = build_composition_plan(results, {"actions": ["국외이전", "처리위탁"]})
    path = {"enabled": True, "issue_order": ["cross_border_transfer", "processing_delegation"], "steps": []}
    answer_plan = bind_rendered_sentences(build_answer_plan("해외 업체에 위탁하려면?", composition, path))
    graph = build_legal_argument_graph("해외 업체에 위탁하려면?", composition, answer_plan, path)

    result = build_multi_path_reasoning(
        "해외 업체에 위탁하려면?", composition, path, legal_argument_graph=graph,
    )

    cumulative = [row for row in result["paths"] if row["path_type"] == "cumulative"]
    assert result["validation"]["valid"] is True
    assert len(cumulative) == 1
    assert cumulative[0]["depends_on_path_ids"] == [
        "path:cross_border_transfer:baseline",
        "path:processing_delegation:baseline",
    ]
    assert cumulative[0]["status"] == "available"


def test_compound_question_recommends_full_cumulative_path():
    results = [
        _result("pipa:28-8", "제28조의8", "국외이전은 법정 근거가 필요하다.", [
            {"document_id": "pipa:28-8:1", "citation": "개인정보 보호법 제28조의8 제1항 제1호", "text": "1. 정보주체로부터 별도 동의를 받은 경우"},
            {"document_id": "pipa:28-8:3", "citation": "개인정보 보호법 제28조의8 제1항 제3호", "text": "3. 계약 이행을 위하여 처리위탁이 필요한 경우"},
        ]),
        _result("pipa:26", "제26조", "처리위탁은 문서로 하여야 한다."),
    ]
    composition = build_composition_plan(results, {"actions": ["국외이전", "처리위탁"]})
    path = {"enabled": True, "issue_order": ["cross_border_transfer", "processing_delegation"], "steps": []}
    missing = {"facts": [
        {"fact_id": "transfer_country"}, {"fact_id": "delegation_purpose"},
        {"fact_id": "consent_obtained"}, {"fact_id": "contract_necessity"},
    ]}
    result = build_multi_path_reasoning("해외 업체에 위탁하려면?", composition, path, missing_fact_detector=missing)
    assert result["recommended_path_id"] == "path:cumulative:all_issues"
    assert result["cumulative_basis_path_count"] == 2


def test_alternative_paths_have_distinct_fact_sets_and_full_titles():
    results = [_result(
        "pipa:28-8", "제28조의8", "국외이전은 법정 근거가 필요하다.", [
            {"document_id": "pipa:28-8:1", "citation": "개인정보 보호법 제28조의8 제1항 제1호", "text": "1. 정보주체로부터 국외 이전에 관한 별도의 동의를 받은 경우"},
            {"document_id": "pipa:28-8:4", "citation": "개인정보 보호법 제28조의8 제1항 제4호", "text": "4. 개인정보를 이전받는 자가 보호위원회가 정하여 고시하는 인증을 받은 경우로서 필요한 조치를 모두 한 경우"},
        ],
    )]
    composition = build_composition_plan(results, {"actions": ["국외이전"]})
    path = {"enabled": True, "issue_order": ["cross_border_transfer"], "steps": []}
    missing = {"facts": [
        {"fact_id": "consent_obtained"}, {"fact_id": "recipient_certification"},
        {"fact_id": "certification_scope"},
    ]}
    result = build_multi_path_reasoning("국외이전 근거는?", composition, path, missing_fact_detector=missing)
    alternatives = {row["branch_key"]: row for row in result["paths"] if row["path_type"] == "alternative_basis"}
    assert alternatives["1"]["required_fact_ids"] != alternatives["4"]["required_fact_ids"]
    assert alternatives["1"]["citations"][0].endswith("제1호")
    assert "..." not in alternatives["4"]["title"]
    assert alternatives["4"]["display_title"].endswith("...")


def test_confidence_decomposition_and_recommendation_rank_are_exposed():
    results = [
        _result("pipa:28-8", "제28조의8", "국외이전은 법정 근거가 필요하다.", [
            {"document_id": "pipa:28-8:1", "citation": "개인정보 보호법 제28조의8 제1항 제1호", "text": "1. 정보주체로부터 별도 동의를 받은 경우"},
            {"document_id": "pipa:28-8:3", "citation": "개인정보 보호법 제28조의8 제1항 제3호", "text": "3. 계약 이행을 위하여 처리위탁이 필요한 경우"},
        ]),
        _result("pipa:26", "제26조", "처리위탁은 문서로 하여야 한다."),
    ]
    composition = build_composition_plan(results, {"actions": ["국외이전", "처리위탁"]})
    path = {"enabled": True, "issue_order": ["cross_border_transfer", "processing_delegation"], "steps": []}
    missing = {"facts": [{"fact_id": "transfer_basis"}, {"fact_id": "contract_necessity"}, {"fact_id": "consent_obtained"}]}
    result = build_multi_path_reasoning("해외 업체에 위탁하려면?", composition, path, missing_fact_detector=missing)
    assert result["recommended_path_rank"] == 1
    assert result["paths"][0]["path_id"] == result["recommended_path_id"]
    assert result["ranking_mode"] == "recommended_policy_override_then_recommendation_score_then_confidence"
    assert "fact_completeness" in result["paths"][0]["confidence_components"]


def test_candidate_pruning_limits_concrete_basis_paths():
    subs = [
        {"document_id": f"pipa:28-8:{i}", "citation": f"개인정보 보호법 제28조의8 제1항 제{i}호", "text": f"{i}. 국외이전 근거 {i}"}
        for i in range(1, 6)
    ]
    results = [
        _result("pipa:28-8", "제28조의8", "국외이전은 법정 근거가 필요하다.", subs),
        _result("pipa:26", "제26조", "처리위탁은 문서로 하여야 한다."),
    ]
    composition = build_composition_plan(results, {"actions": ["국외이전", "처리위탁"]})
    path = {"enabled": True, "issue_order": ["cross_border_transfer", "processing_delegation"], "steps": []}
    result = build_multi_path_reasoning("해외 업체에 위탁하려면?", composition, path)
    assert result["candidate_path_count"] == 13
    assert result["cumulative_basis_path_count"] == 3
    assert result["pruned_path_count"] == 4
    assert result["validation"]["dangling_dependency_ids"] == []


def test_legal_strategy_layer_separates_confidence_and_recommendation():
    results = [
        _result("pipa:28-8", "제28조의8", "국외이전은 법정 근거가 필요하다.", [
            {"document_id": "pipa:28-8:1", "citation": "개인정보 보호법 제28조의8 제1항 제1호", "text": "1. 정보주체로부터 별도 동의를 받은 경우"},
            {"document_id": "pipa:28-8:3", "citation": "개인정보 보호법 제28조의8 제1항 제3호", "text": "3. 계약 이행을 위하여 처리위탁이 필요한 경우"},
        ]),
        _result("pipa:26", "제26조", "처리위탁은 문서로 하여야 한다."),
    ]
    composition = build_composition_plan(results, {"actions": ["국외이전", "처리위탁"]})
    path = {"enabled": True, "issue_order": ["cross_border_transfer", "processing_delegation"], "steps": []}
    missing = {"facts": [{"fact_id": "transfer_basis"}, {"fact_id": "contract_necessity"}, {"fact_id": "consent_obtained"}]}
    result = build_multi_path_reasoning("해외 업체에 위탁하려면?", composition, path, missing_fact_detector=missing)
    recommended = result["paths"][0]
    assert result["strategy_layer"]["enabled"] is True
    assert result["recommended_path_confidence"] == recommended["confidence"]
    assert result["recommended_path_recommendation_score"] == recommended["recommendation_score"]
    assert recommended["strategy_profile"]["strategy_type"] == "issue_coverage_and_fact_gathering"
    assert len(recommended["recommendation_reasons"]) >= 2


def test_basis_three_strategy_exposes_legal_tradeoffs():
    results = [_result("pipa:28-8", "제28조의8", "국외이전은 법정 근거가 필요하다.", [
        {"document_id": "pipa:28-8:3", "citation": "개인정보 보호법 제28조의8 제1항 제3호", "text": "3. 계약 이행을 위하여 처리위탁이 필요한 경우"},
        {"document_id": "pipa:28-8:4", "citation": "개인정보 보호법 제28조의8 제1항 제4호", "text": "4. 인증을 받은 경우"},
    ])]
    composition = build_composition_plan(results, {"actions": ["국외이전"]})
    path = {"enabled": True, "issue_order": ["cross_border_transfer"], "steps": []}
    result = build_multi_path_reasoning("계약 이행을 위해 국외 처리위탁하려면?", composition, path)
    basis3 = next(row for row in result["paths"] if row.get("branch_key") == "3")
    assert basis3["strategy_profile"]["strategy_label"] == "계약 이행 필요성 기반 전략"
    assert basis3["strategy_profile"]["proof_burden"] == "high"
    assert basis3["recommendation_score"] != basis3["confidence"]


def test_strategy_ranking_and_comparison_are_transparent():
    results = [
        _result("pipa:28-8", "제28조의8", "국외이전은 법정 근거가 필요하다.", [
            {"document_id": "pipa:28-8:1", "citation": "개인정보 보호법 제28조의8 제1항 제1호", "text": "1. 정보주체로부터 별도 동의를 받은 경우"},
            {"document_id": "pipa:28-8:2", "citation": "개인정보 보호법 제28조의8 제1항 제2호", "text": "2. 특별한 법적 근거가 있는 경우"},
            {"document_id": "pipa:28-8:3", "citation": "개인정보 보호법 제28조의8 제1항 제3호", "text": "3. 계약 이행을 위하여 처리위탁이 필요한 경우"},
        ]),
        _result("pipa:26", "제26조", "처리위탁은 문서로 하여야 한다."),
    ]
    composition = build_composition_plan(results, {"actions": ["국외이전", "처리위탁"]})
    reasoning = {"enabled": True, "issue_order": ["cross_border_transfer", "processing_delegation"], "steps": []}
    missing = {"facts": [{"fact_id": "transfer_basis"}, {"fact_id": "contract_necessity"}, {"fact_id": "consent_obtained"}]}
    result = build_multi_path_reasoning("해외 업체에 위탁하려면?", composition, reasoning, missing_fact_detector=missing)
    paths = result["paths"]
    assert paths[0]["is_recommended"] is True
    remaining = paths[1:]
    assert [row["recommendation_score"] for row in remaining] == sorted(
        [row["recommendation_score"] for row in remaining], reverse=True
    )
    assert all(row["recommendation_reasons"] for row in remaining)
    comparison = result["strategy_comparison"]
    assert comparison["enabled"] is True
    assert comparison["recommended_path_id"] == result["recommended_path_id"]
    assert 1 <= len(comparison["alternatives"]) <= 3
    decision = result["decision_support"]
    assert decision["enabled"] is True
    assert decision["recommended_path_id"] == result["recommended_path_id"]
    assert decision["why_selected"]
    assert decision["why_not_selected"]
    assert decision["tradeoff_summary"]
    assert decision["when_to_switch"]
    assert decision["required_next_facts"] == paths[0]["missing_fact_ids"]



def test_strategy_comparison_uses_semantic_categories_and_distinct_switch_facts():
    from law_rag.reasoning.legal_strategy import build_decision_support, build_strategy_comparison, strategy_profile

    recommended = {
        "path_id": "path:cumulative:all_issues",
        "title": "복수 쟁점 누적 적용 경로",
        "recommendation_score": 0.78,
        "confidence": 0.66,
        "recommendation_reasons": ["전체 쟁점과 누락 사실을 먼저 확인합니다."],
        "missing_fact_ids": ["transfer_basis", "transfer_country", "transfer_items", "delegation_purpose", "delegate_identity", "subdelegation"],
        "strategy_profile": strategy_profile("cumulative", None, "conditional"),
    }
    alternatives = []
    branch_facts = {
        "2": ["special_legal_basis", "legal_basis_scope"],
        "3": ["contract_necessity", "delegation_or_storage", "transfer_notice_method"],
        "1": ["consent_obtained", "consent_notice_items", "recipient_identity"],
    }
    for index, branch in enumerate(("2", "3", "1"), start=1):
        alternatives.append({
            "path_id": f"path:cumulative:delegation+basis:{branch}",
            "title": f"누적 경로 {branch}",
            "recommendation_score": 0.78 - index * 0.01,
            "confidence": 0.67,
            "recommendation_reasons": ["추가 고유 요건 확인이 필요합니다."],
            "missing_fact_ids": list(recommended["missing_fact_ids"]) + branch_facts[branch],
            "strategy_profile": strategy_profile("cumulative_basis", branch, "conditional"),
        })
    paths = [recommended, *alternatives]

    comparison = build_strategy_comparison(paths, recommended)
    assert comparison["version"] == "1.1"
    for alternative in comparison["alternatives"]:
        assert alternative["advantages"]
        assert alternative["requirements"]
        assert alternative["risks"]
        assert "확인해야" not in alternative["advantages"][0]

    decision = build_decision_support(paths, recommended, "전체 쟁점 우선", comparison)
    assert decision["version"] == "1.1"
    switches = {row["target_path_id"]: row for row in decision["when_to_switch"]}
    basis2 = switches["path:cumulative:delegation+basis:2"]
    basis3 = switches["path:cumulative:delegation+basis:3"]
    basis1 = switches["path:cumulative:delegation+basis:1"]
    assert basis2["differentiating_fact_ids"] == branch_facts["2"]
    assert basis3["differentiating_fact_ids"] == branch_facts["3"]
    assert basis1["differentiating_fact_ids"] == branch_facts["1"]
    assert "특별 법적 근거" in basis2["condition"]
    assert "계약 체결·이행상 필요성" in basis3["condition"]
    assert "국외이전 별도 동의 취득" in basis1["condition"]


def test_reasoning_quality_and_failure_analysis_are_exposed():
    results = [
        _result("pipa:28-8", "제28조의8", "국외이전은 법정 근거가 필요하다.", [
            {"document_id": "pipa:28-8:1", "citation": "개인정보 보호법 제28조의8 제1항 제1호", "text": "1. 정보주체로부터 별도 동의를 받은 경우"},
            {"document_id": "pipa:28-8:2", "citation": "개인정보 보호법 제28조의8 제1항 제2호", "text": "2. 특별한 법적 근거가 있는 경우"},
            {"document_id": "pipa:28-8:3", "citation": "개인정보 보호법 제28조의8 제1항 제3호", "text": "3. 계약 이행을 위하여 처리위탁이 필요한 경우"},
        ]),
        _result("pipa:26", "제26조", "처리위탁은 문서로 하여야 한다."),
    ]
    composition = build_composition_plan(results, {"actions": ["국외이전", "처리위탁"]})
    reasoning = {"enabled": True, "issue_order": ["cross_border_transfer", "processing_delegation"], "steps": []}
    missing = {"facts": [{"fact_id": "transfer_basis"}, {"fact_id": "contract_necessity"}, {"fact_id": "consent_obtained"}]}
    result = build_multi_path_reasoning("해외 업체에 위탁하려면?", composition, reasoning, missing_fact_detector=missing)

    quality = result["reasoning_quality"]
    assert quality["enabled"] is True
    assert quality["version"] == "1.0"
    assert 0 <= quality["overall_score"] <= 1
    assert set(quality["components"]) == {
        "evidence_quality", "fact_completeness", "issue_coverage",
        "structural_integrity", "decision_clarity", "strategy_differentiation",
    }
    failure = result["failure_analysis"]
    assert failure["enabled"] is True
    assert failure["version"] == "1.0"
    assert failure["status"] in {"acceptable", "degraded", "blocked"}
    assert failure["validation_valid"] is True
    assert failure["safe_to_execute"] is False


def test_consistency_report_and_scenario_simulation_are_exposed():
    results = [
        _result("pipa:28-8", "제28조의8", "국외이전은 법정 근거가 필요하다.", [
            {"document_id": "pipa:28-8:1", "citation": "개인정보 보호법 제28조의8 제1항 제1호", "text": "1. 정보주체로부터 별도 동의를 받은 경우"},
            {"document_id": "pipa:28-8:2", "citation": "개인정보 보호법 제28조의8 제1항 제2호", "text": "2. 특별한 법적 근거가 있는 경우"},
            {"document_id": "pipa:28-8:3", "citation": "개인정보 보호법 제28조의8 제1항 제3호", "text": "3. 계약 이행을 위하여 처리위탁이 필요한 경우"},
        ]),
        _result("pipa:26", "제26조", "처리위탁은 문서로 하여야 한다."),
    ]
    composition = build_composition_plan(results, {"actions": ["국외이전", "처리위탁"]})
    reasoning = {"enabled": True, "issue_order": ["cross_border_transfer", "processing_delegation"], "steps": []}
    missing = {"facts": [
        {"fact_id": "transfer_basis"}, {"fact_id": "transfer_country"}, {"fact_id": "transfer_items"},
        {"fact_id": "recipient_safeguards"}, {"fact_id": "delegation_purpose"},
        {"fact_id": "delegate_identity"}, {"fact_id": "subdelegation"},
        {"fact_id": "special_legal_basis"}, {"fact_id": "legal_basis_scope"},
        {"fact_id": "contract_necessity"}, {"fact_id": "delegation_or_storage"},
        {"fact_id": "transfer_notice_method"}, {"fact_id": "consent_obtained"},
        {"fact_id": "consent_notice_items"}, {"fact_id": "recipient_identity"},
    ]}
    result = build_multi_path_reasoning("해외 업체에 위탁하려면?", composition, reasoning, missing_fact_detector=missing)

    consistency = result["consistency_report"]
    assert consistency["enabled"] is True
    assert consistency["version"] == "1.0"
    assert consistency["status"] == "consistent"
    assert consistency["consistent"] is True
    assert consistency["issue_count"] == 0

    simulation = result["scenario_simulation"]
    assert simulation["enabled"] is True
    assert simulation["version"] == "1.0"
    assert simulation["scenario_count"] == len(result["decision_support"]["when_to_switch"])
    assert simulation["scenarios"]
    for scenario in simulation["scenarios"]:
        assert scenario["assumed_true_fact_ids"]
        assert scenario["target_projection"] is not None
        assert scenario["projected_recommended_path_id"]
        assert scenario["top_projected_paths"]
