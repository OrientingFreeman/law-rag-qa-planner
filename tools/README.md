# Tools

## Legal knowledge-base validation

```bash
python tools/build_legal_knowledge_base.py
python tools/validate_legal_knowledge_base.py
python -m pytest tests/test_legal_knowledge_base.py -q
```

## K4 official amendment case validation

```bash
python tools/validate_amendment_case_candidates.py
python -m pytest tests/test_amendment_case_candidates.py -q
```

The selected case must match an article in the current corpus, an existing
knowledge-base concept, and an official evaluation case. All three legal-text
links must point to the National Law Information Center.

Run the selected case end to end:

```bash
python tools/run_k4_amendment_case.py
python -m pytest tests/test_k4_amendment_case.py -q
```

This compares isolated before/after Article 15 fixtures, traces impacted KB and
evaluation records, evaluates the 2025-10-02 effective-date boundary, and
regenerates `data/k4_amendment_impact_manifest.json` plus
`docs/K4_AMENDMENT_IMPACT_REPORT.md`.

## K5 amendment review and release gate

```bash
python tools/review_k5_amendment_update.py
python -m pytest tests/test_k5_amendment_review.py -q
```

The gate verifies the immutable K4 manifest hash, official-source provenance,
effective-date consistency, impact-review evidence, ordered role stages, and
test evidence. It emits `pass`, `revise`, or `reject`; a requested pass cannot
override failed gate conditions.

## K6 final KALI portfolio verification

```bash
python tools/run_kali_verification.py
```

This command reruns K1-K5 validators, evaluations and gates, executes targeted
and full regression tests, recalculates every portfolio count from JSON, and
fails when README or the KALI application summary contains a stale key number.
It regenerates `data/kali_final_verification.json` and
`docs/KALI_FINAL_VERIFICATION.md`.

The builder produces the reviewed legal-term/lay-term mappings from an
inspectable record list. The validator checks concept identifiers, relation
types, effective periods, and every statute/article/source-document reference
against `data/legal_corpus.json`.

## Legal KB amendment impact analysis

```bash
python tools/analyze_legal_kb_update.py \
  --baseline data/legal_corpus.json \
  --candidate /path/to/candidate_corpus.json \
  --output /tmp/kb_update_manifest.json \
  --mode official_amendment_review
python -m pytest tests/test_legal_kb_update.py -q
```

The analyzer classifies added, removed, content-changed, and temporal-metadata
changes. It traces affected terminology concepts and official evaluation cases,
rejects inconsistent effective periods, and emits an auditable update manifest.
The committed `data/kb_update_manifest.json` is a no-change baseline integrity
check, not a claim that an actual amendment was processed.

## Regression output helpers

To create a compact strategy-aware summary from a saved `/answer` response:

```bash
python3 tools/summarize_multi_path.py < answer-response.json > output2.txt
```

The summary intentionally includes both `confidence` and `recommendation_score`,
plus `recommendation_reasons` and `strategy_profile`, so strategy-layer fields
cannot disappear from compact verification output.
