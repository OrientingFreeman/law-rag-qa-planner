import json
from pathlib import Path

from tools.validate_precedent_poc import validate


def test_precedent_poc_has_valid_official_sources_and_statute_links():
    errors = validate(
        Path("data/precedent_poc.json"),
        Path("evaluation/datasets/precedent_poc_cases.json"),
        Path("data/legal_corpus.json"),
    )
    assert errors == []


def test_precedent_poc_expansion_has_expected_coverage():
    precedents = json.loads(Path("data/precedent_poc.json").read_text(encoding="utf-8"))["precedents"]
    cases = json.loads(
        Path("evaluation/datasets/precedent_poc_cases.json").read_text(encoding="utf-8")
    )["cases"]
    assert len(precedents) == 10
    assert len(cases) == 20
    assert {row["expected_law_id"] for row in cases} == {
        "001706", "001872", "010199", "011357"
    }
