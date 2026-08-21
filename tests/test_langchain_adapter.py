import pytest

langchain_core = pytest.importorskip("langchain_core")

from law_rag.generation.providers import DeterministicProvider
from law_rag.integrations.langchain import LawRagLangChainRetriever
from law_rag.service import LawRagService


def test_langchain_adapter_preserves_native_result_order_and_metadata():
    service = LawRagService(
        data_path="tests/fixtures/legal_corpus.json",
        domains_path="domains",
        llm_provider=DeterministicProvider(),
    )
    question = "개인정보 수집 동의 요건은?"
    native = service.retrieve(question, domain_id="digital_business", top_k=3)
    adapter = LawRagLangChainRetriever(service=service, domain_id="digital_business", top_k=3)
    documents = adapter.invoke(question)

    assert [doc.metadata["document_id"] for doc in documents] == [
        row["document_id"] for row in native["results"]
    ]
    assert [doc.metadata["rank"] for doc in documents] == [row["rank"] for row in native["results"]]
    assert all(doc.metadata["adapter"] == "law_rag_langchain" for doc in documents)
    assert [doc.page_content for doc in documents] == [row["text"] for row in native["results"]]
