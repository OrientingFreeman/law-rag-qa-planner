def evaluate_retrieval(query, retrieved_results, expected_article_no):
    retrieved_articles = [
        result["chunk"]["metadata"]["article_no"]
        for result in retrieved_results
    ]

    top1_article = retrieved_articles[0] if retrieved_articles else None

    hit_at_k = expected_article_no in retrieved_articles
    top1_hit = top1_article == expected_article_no

    return {
        "query": query,
        "expected_article_no": expected_article_no,
        "retrieved_articles": retrieved_articles,
        "top1_article": top1_article,
        "hit_at_k": hit_at_k,
        "top1_hit": top1_hit
    }


if __name__ == "__main__":
    from chunking import load_laws, create_chunks
    from retriever import retrieve

    laws = load_laws("data/sample_laws.json")
    chunks = create_chunks(laws)

    query = "민법상 불법행위 손해배상 요건은 무엇인가요?"
    results = retrieve(query, chunks)

    evaluation = evaluate_retrieval(
        query=query,
        retrieved_results=results,
        expected_article_no="제750조"
    )

    print(evaluation)
