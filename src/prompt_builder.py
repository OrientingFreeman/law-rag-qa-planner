from chunking import load_laws, create_chunks
from retriever import retrieve


def build_prompt(query, retrieved_results):
    evidence_text = "\n\n".join(
        [result["chunk"]["text"] for result in retrieved_results]
    )

    prompt = f"""
당신은 법령 기반 QA 시스템입니다.

다음 원칙을 반드시 지키세요.
1. 제공된 근거 문서만 사용하세요.
2. 근거 문서에 없는 내용은 추측하지 마세요.
3. 법령명과 조문 번호를 반드시 포함하세요.
4. 근거가 부족하면 '제공된 문서만으로는 확인할 수 없습니다'라고 답하세요.

[사용자 질문]
{query}

[근거 문서]
{evidence_text}

[답변]
""".strip()

    return prompt


if __name__ == "__main__":
    laws = load_laws("data/sample_laws.json")
    chunks = create_chunks(laws)

    query = "민법상 불법행위 손해배상 요건은 무엇인가요?"
    results = retrieve(query, chunks)

    prompt = build_prompt(query, results)
    print(prompt)
