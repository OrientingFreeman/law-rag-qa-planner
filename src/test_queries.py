from chunking import load_laws, create_chunks
from retriever import retrieve
from evaluation import evaluate_retrieval

test_cases = [
    {
        "query": "민법상 불법행위 손해배상 요건은?",
        "expected": "제750조"
    },
    {
        "query": "채무불이행 손해배상 규정은?",
        "expected": "제390조"
    },
    {
        "query": "개인정보 수집 요건은?",
        "expected": "제15조"
    }
]

def run_tests():
    laws = load_laws("data/sample_laws.json")
    chunks = create_chunks(laws)

    total = len(test_cases)
    correct = 0

    for case in test_cases:
        results = retrieve(case["query"], chunks)

        evaluation = evaluate_retrieval(
            case["query"],
            results,
            case["expected"]
        )

        if evaluation["retrieval_hit"]:
            correct += 1

        print(evaluation)

    accuracy = correct / total

    print(f"\nRetrieval Accuracy: {accuracy:.2f}")

if __name__ == "__main__":
    run_tests()
