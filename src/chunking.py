import _bootstrap  # noqa: F401
from law_rag.domain.models import format_provision_text
from law_rag.ingestion.json_source import JsonLegalDocumentSource


def load_laws(path: str):
    return JsonLegalDocumentSource().load(path)


def create_chunks(laws):
    return [
        {
            "text": format_provision_text(law),
            "metadata": {
                **law.to_dict(),
                "clause_no": law.paragraph_no,
                "effective_date": law.effective_from.isoformat() if law.effective_from else None,
                "content": law.text,
            },
            "provision": law,
        }
        for law in laws
    ]


if __name__ == "__main__":
    for chunk in create_chunks(load_laws("data/sample_laws.json")):
        print(chunk)
