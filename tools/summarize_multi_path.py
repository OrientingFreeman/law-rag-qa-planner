#!/usr/bin/env python3
"""Render an audit-friendly compact view of multi-path reasoning JSON.

Reads a complete /answer response from stdin and preserves the distinction
between analytical confidence and execution recommendation priority.
"""
from __future__ import annotations

import json
import sys
from typing import Any


def _path_summary(path: dict[str, Any]) -> dict[str, Any]:
    profile = path.get("strategy_profile") or {}
    return {
        "rank": path.get("rank"),
        "confidence_rank": path.get("confidence_rank"),
        "is_recommended": path.get("is_recommended", False),
        "path_id": path.get("path_id"),
        "path_type": path.get("path_type"),
        "title": path.get("title"),
        "status": path.get("status"),
        "score": path.get("score"),
        "confidence": path.get("confidence"),
        "recommendation_score": path.get("recommendation_score"),
        "recommendation_reasons": path.get("recommendation_reasons", []),
        "strategy_profile": {
            "strategy_type": profile.get("strategy_type"),
            "strategy_label": profile.get("strategy_label"),
            "legal_risk": profile.get("legal_risk"),
            "implementation_cost": profile.get("implementation_cost"),
            "implementation_speed": profile.get("implementation_speed"),
            "proof_burden": profile.get("proof_burden"),
            "reversibility": profile.get("reversibility"),
            "execution_ready": profile.get("execution_ready"),
            "tradeoffs": profile.get("tradeoffs", []),
        },
        "missing_fact_ids": path.get("missing_fact_ids", []),
        "depends_on_path_ids": path.get("depends_on_path_ids", []),
    }


def summarize(payload: dict[str, Any]) -> dict[str, Any]:
    multi = payload.get("multi_path_reasoning") or {}
    return {
        "service_version": (payload.get("metadata") or {}).get("service_version"),
        "multi_path_reasoning": {
            "version": multi.get("version"),
            "path_count": multi.get("path_count"),
            "candidate_path_count": multi.get("candidate_path_count"),
            "pruned_path_count": multi.get("pruned_path_count"),
            "alternative_path_count": multi.get("alternative_path_count"),
            "cumulative_path_count": multi.get("cumulative_path_count"),
            "status_counts": multi.get("status_counts", {}),
            "recommended_path_id": multi.get("recommended_path_id"),
            "recommended_path_confidence": multi.get("recommended_path_confidence"),
            "recommended_path_recommendation_score": multi.get("recommended_path_recommendation_score"),
            "recommendation_reason": multi.get("recommendation_reason"),
            "ranking_mode": multi.get("ranking_mode"),
            "strategy_layer": multi.get("strategy_layer", {}),
            "strategy_comparison": multi.get("strategy_comparison", {}),
            "decision_support": multi.get("decision_support", {}),
            "reasoning_quality": multi.get("reasoning_quality", {}),
            "failure_analysis": multi.get("failure_analysis", {}),
            "consistency_report": multi.get("consistency_report", {}),
            "scenario_simulation": multi.get("scenario_simulation", {}),
            "validation": multi.get("validation", {}),
            "paths": [_path_summary(row) for row in multi.get("paths", []) if isinstance(row, dict)],
        },
    }


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(f"invalid JSON input: {exc}", file=sys.stderr)
        return 2
    if not isinstance(payload, dict):
        print("expected a JSON object", file=sys.stderr)
        return 2
    json.dump(summarize(payload), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
