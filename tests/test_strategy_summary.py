from tools.summarize_multi_path import summarize


def test_compact_summary_keeps_strategy_fields():
    payload = {
        "metadata": {"service_version": "4.7.1"},
        "multi_path_reasoning": {
            "version": "1.3",
            "recommended_path_id": "path:a",
            "recommended_path_confidence": 0.66,
            "recommended_path_recommendation_score": 0.72,
            "strategy_layer": {"enabled": True},
            "strategy_comparison": {"enabled": True, "alternatives": [{"path_id": "path:b"}]},
            "decision_support": {"enabled": True, "recommended_path_id": "path:a", "required_next_facts": ["fact:a"]},
            "reasoning_quality": {"enabled": True, "overall_score": 0.82},
            "failure_analysis": {"enabled": True, "status": "degraded"},
            "paths": [{
                "rank": 1,
                "path_id": "path:a",
                "confidence": 0.66,
                "recommendation_score": 0.72,
                "recommendation_reasons": ["사실확인이 우선입니다."],
                "strategy_profile": {"strategy_label": "사실확인 전략", "legal_risk": "low"},
            }],
        },
    }
    compact = summarize(payload)["multi_path_reasoning"]
    assert compact["recommended_path_recommendation_score"] == 0.72
    assert compact["paths"][0]["recommendation_score"] == 0.72
    assert compact["paths"][0]["recommendation_reasons"]
    assert compact["paths"][0]["strategy_profile"]["strategy_label"] == "사실확인 전략"
    assert compact["strategy_comparison"]["enabled"] is True
    assert compact["decision_support"]["recommended_path_id"] == "path:a"
    assert compact["reasoning_quality"]["overall_score"] == 0.82
    assert compact["failure_analysis"]["status"] == "degraded"
