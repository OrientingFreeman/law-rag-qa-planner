import json
from pathlib import Path


def load_laws(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def create_chunks(laws):
    chunks = []

    for law in laws:
        chunk_text = f"""
법령명: {law['law_name']}
조문: {law['article_no']}
항: {law['clause_no']}
주제: {law['topic']}
시행일자: {law['effective_date']}
내용: {law['content']}
""".strip()

        chunks.append({
            "text": chunk_text,
            "metadata": {
                "document_type": law["document_type"],
                "law_name": law["law_name"],
                "article_no": law["article_no"],
                "clause_no": law["clause_no"],
                "effective_date": law["effective_date"],
                "authority": law["authority"],
                "reliability": law["reliability"],
                "topic": law["topic"],
                "keywords": law["keywords"]
            }
        })

    return chunks


if __name__ == "__main__":
    laws = load_laws("data/sample_laws.json")
    chunks = create_chunks(laws)

    for chunk in chunks:
        print(chunk)
