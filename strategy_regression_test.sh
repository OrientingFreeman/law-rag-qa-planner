#!/usr/bin/env bash
set -euo pipefail

API_URL="${LAW_RAG_API_URL:-http://127.0.0.1:8000/answer}"
PAYLOAD='{
  "question":"개인정보를 위탁하면서 국외 이전도 하는 경우 필요한 절차는?",
  "domain":"digital_business",
  "top_k":5
}'

response=$(curl -fsS -X POST "$API_URL" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD")

printf '%s\n' "$response" | python3 -m json.tool | tee output-strategy-full.txt
printf '%s\n' "$response" | python3 tools/summarize_multi_path.py | tee output2.txt

python3 - "$response" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
multi = payload.get("multi_path_reasoning") or {}
paths = multi.get("paths") or []
assert multi.get("strategy_layer", {}).get("enabled") is True, "strategy_layer missing"
assert paths, "multi_path_reasoning.paths is empty"
recommended = next((row for row in paths if row.get("is_recommended")), None)
assert recommended is not None, "recommended path missing"
for key in ("confidence", "recommendation_score", "strategy_profile", "recommendation_reasons"):
    assert key in recommended, f"recommended path missing {key}"
assert multi.get("recommended_path_id") == recommended.get("path_id")
assert multi.get("recommended_path_recommendation_score") == recommended.get("recommendation_score")
comparison = multi.get("strategy_comparison") or {}
assert comparison.get("enabled") is True, "strategy_comparison missing"
assert comparison.get("recommended_path_id") == recommended.get("path_id")
decision = multi.get("decision_support") or {}
assert decision.get("enabled") is True, "decision_support missing"
assert decision.get("recommended_path_id") == recommended.get("path_id")
assert decision.get("why_selected"), "decision_support.why_selected missing"
assert decision.get("why_not_selected"), "decision_support.why_not_selected missing"
assert decision.get("when_to_switch"), "decision_support.when_to_switch missing"
assert decision.get("required_next_facts") == recommended.get("missing_fact_ids")
print("strategy and decision-support output contract: PASS")
PY
