from __future__ import annotations

from typing import Any

try:
    from langchain_core.callbacks import CallbackManagerForRetrieverRun
    from langchain_core.documents import Document
    from langchain_core.retrievers import BaseRetriever
except ImportError as exc:  # pragma: no cover - exercised when optional extra is absent
    raise ImportError(
        "LangChain integration is optional. Install with: pip install -e '.[langchain]'"
    ) from exc


class LawRagLangChainRetriever(BaseRetriever):
    """Expose the existing retriever through LangChain without replacing it."""

    service: Any
    domain_id: str = "all"
    top_k: int = 5
    search_strategy: str = "hybrid"
    query_rewrite: bool = True
    reranking: bool = True

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun,
    ) -> list[Document]:
        response = self.service.retrieve(
            query,
            domain_id=None if self.domain_id == "all" else self.domain_id,
            top_k=self.top_k,
            search_strategy=self.search_strategy,
            query_rewrite=self.query_rewrite,
            reranking=self.reranking,
        )
        documents: list[Document] = []
        for result in response.get("results", []):
            metadata = {key: value for key, value in result.items() if key != "text"}
            metadata["adapter"] = "law_rag_langchain"
            documents.append(Document(page_content=str(result.get("text", "")), metadata=metadata))
        return documents
