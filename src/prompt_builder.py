import _bootstrap  # noqa: F401
from law_rag.domain.models import SearchResult
from law_rag.generation.prompt import build_grounded_prompt
from chunking import create_chunks, load_laws
from retriever import retrieve


def build_prompt(query, retrieved_results):
    results = []
    for rank, result in enumerate(retrieved_results, start=1):
        provision = result["chunk"].get("provision")
        if provision is None:
            continue
        results.append(SearchResult(provision=provision, score=result["score"], rank=rank))
    if results:
        return build_grounded_prompt(query, results)

    evidence_text = "\n\n".join(result["chunk"]["text"] for result in retrieved_results)
    return f"""당신은 법령 정보 검색 보조 시스템입니다.
제공된 근거만 사용하고, 근거가 부족하면 확인할 수 없다고 답하세요.

[사용자 질문]\n{query}\n\n[검색 근거]\n{evidence_text or '검색된 근거 없음'}"""


if __name__ == "__main__":
    chunks = create_chunks(load_laws("data/sample_laws.json"))
    print(build_prompt("민법상 불법행위 손해배상 요건은 무엇인가요?", retrieve("민법상 불법행위 손해배상 요건은 무엇인가요?", chunks)))
