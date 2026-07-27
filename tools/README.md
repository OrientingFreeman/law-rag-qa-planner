# Regression output helpers

To create a compact strategy-aware summary from a saved `/answer` response:

```bash
python3 tools/summarize_multi_path.py < answer-response.json > output2.txt
```

The summary intentionally includes both `confidence` and `recommendation_score`,
plus `recommendation_reasons` and `strategy_profile`, so strategy-layer fields
cannot disappear from compact verification output.
