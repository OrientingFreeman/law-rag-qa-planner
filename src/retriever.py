import _bootstrap  # noqa: F401
from law_rag.domain.config import DomainRegistry
from law_rag.retrieval.hybrid import HybridRetriever
from chunking import create_chunks, load_laws


def retrieve(query, chunks, top_k=3, domain_id=None):
    provisions = [chunk["provision"] for chunk in chunks]
    domain = DomainRegistry("domains").load_all().get(domain_id)
    return [
        result.to_legacy_dict()
        for result in HybridRetriever(provisions).retrieve(query, domain=domain, top_k=top_k)
    ]


if __name__ == "__main__":
    chunks = create_chunks(load_laws("data/sample_laws.json"))
    for result in retrieve("민법상 불법행위 손해배상 요건은 무엇인가요?", chunks):
        print("score:", round(result["score"], 4))
        print(result["chunk"]["text"])
        print("-" * 50)
