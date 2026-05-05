from chunking import load_laws, create_chunks


def keyword_score(query, chunk):
    score = 0
    metadata = chunk["metadata"]

    for keyword in metadata["keywords"]:
        if keyword in query:
            score += 2

    if metadata["law_name"] in query:
        score += 3

    if metadata["topic"] in query:
        score += 2

    if metadata["article_no"] in query:
        score += 3

    return score


def retrieve(query, chunks, top_k=3):
    scored_results = []

    for chunk in chunks:
        score = keyword_score(query, chunk)

        if score > 0:
            scored_results.append({
                "score": score,
                "chunk": chunk
            })

    scored_results.sort(key=lambda x: x["score"], reverse=True)

    return scored_results[:top_k]


if __name__ == "__main__":
    laws = load_laws("data/sample_laws.json")
    chunks = create_chunks(laws)

    query = "민법상 불법행위 손해배상 요건은 무엇인가요?"
    results = retrieve(query, chunks)

    for result in results:
        print("score:", result["score"])
        print(result["chunk"]["text"])
        print("-" * 50)
