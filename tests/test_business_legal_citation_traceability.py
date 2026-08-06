import json

from law_rag.generation.providers import DeterministicProvider
from law_rag.service import LawRagService


def test_multi_issue_answer_citations_are_bound_and_issue_attributed():
    with open("evaluation/datasets/business_legal_multi_issue_cases.json", encoding="utf-8") as file:
        row = json.load(file)[-1]
    service = LawRagService(
        data_path="data/legal_corpus.json",
        domains_path="domains",
        llm_provider=DeterministicProvider(),
    )
    response = service.answer(row["question"], top_k=row["top_k"])
    plan = response["composition"]["answer_plan"]
    cited_sentences = [
        sentence
        for section in plan["sections"]
        for sentence in section["sentences"]
        if sentence["citations"]
    ]

    assert cited_sentences
    for sentence in cited_sentences:
        assert sentence["issue_id"]
        bound = {binding["citation"] for binding in sentence["citation_bindings"]}
        assert set(sentence["citations"]) <= bound


def test_multi_issue_answer_uses_korean_issue_headings():
    with open("evaluation/datasets/business_legal_multi_issue_cases.json", encoding="utf-8") as file:
        row = json.load(file)[-1]
    service = LawRagService(
        data_path="data/legal_corpus.json",
        domains_path="domains",
        llm_provider=DeterministicProvider(),
    )
    response = service.answer(row["question"], top_k=row["top_k"])

    headings = {
        line.split(". ", 1)[1]
        for line in response["answer"].splitlines()
        if line.startswith("### ")
    }
    assert {"특허 신규성", "공지예외", "직무발명", "업무상 프로그램 저작자"} <= headings
    assert "patent_novelty" not in response["answer"]
