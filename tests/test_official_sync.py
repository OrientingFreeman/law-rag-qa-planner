from pathlib import Path

import pytest

from law_rag.ingestion.official_source import OfficialKoreanLawSource, OfficialLawApiError
from law_rag.ingestion.sync import LawSyncItem, LawSyncManifest, OfficialCorpusSynchronizer


SEARCH = Path("tests/fixtures/official_law_search.xml").read_bytes()
BODY = Path("tests/fixtures/official_law_body.xml").read_bytes()


def test_manifest_accepts_name_and_id(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(
        '{"laws":[{"law_name":"개인정보 보호법","domain_id":"digital_business"},'
        '{"law_id":"011357","domain":"digital_business","enabled":false}]}',
        encoding="utf-8",
    )
    manifest = LawSyncManifest.load(path)
    assert len(manifest.laws) == 2
    assert manifest.laws[0].law_name == "개인정보 보호법"
    assert manifest.laws[1].enabled is False


def test_manifest_rejects_missing_identity():
    with pytest.raises(ValueError):
        LawSyncItem.from_dict({"domain_id": "digital_business"})


def test_sync_fetches_caches_and_merges(tmp_path):
    def transport(url, timeout):
        return SEARCH if "lawSearch.do" in url else BODY

    source = OfficialKoreanLawSource(transport=transport)
    syncer = OfficialCorpusSynchronizer(source)
    result = syncer.sync(
        LawSyncManifest((LawSyncItem(domain_id="digital_business", law_name="개인정보 보호법"),)),
        oc="secret@example.com",
        output=tmp_path / "corpus.json",
        cache_dir=tmp_path / "cache",
        search_url="https://example.test/lawSearch.do",
        service_url="https://example.test/lawService.do",
    )
    assert result["fetched_laws"] == 1
    assert result["parsed_provisions"] > 0
    assert (tmp_path / "corpus.json").exists()
    assert list((tmp_path / "cache").glob("*.json"))
    assert "secret" not in (tmp_path / "corpus.json").read_text(encoding="utf-8")


def test_sync_uses_cache_only_when_explicitly_allowed(tmp_path):
    good = OfficialCorpusSynchronizer(
        OfficialKoreanLawSource(transport=lambda url, timeout: SEARCH if "lawSearch.do" in url else BODY)
    )
    manifest = LawSyncManifest((LawSyncItem(domain_id="digital_business", law_name="개인정보 보호법"),))
    good.sync(
        manifest, oc="secret", output=tmp_path / "first.json", cache_dir=tmp_path / "cache",
        search_url="https://example.test/lawSearch.do", service_url="https://example.test/lawService.do",
    )

    def fail(url, timeout):
        raise OfficialLawApiError("offline")

    offline = OfficialCorpusSynchronizer(OfficialKoreanLawSource(transport=fail))
    result = offline.sync(
        manifest, oc="secret", output=tmp_path / "offline.json", cache_dir=tmp_path / "cache",
        search_url="https://example.test/lawSearch.do", service_url="https://example.test/lawService.do",
        allow_cache_fallback=True,
    )
    assert result["cached_laws"] == 1
    assert (tmp_path / "offline.json").exists()


def test_real_search_xml_fields_and_mst_body_lookup():
    requested_urls = []

    def transport(url, timeout):
        requested_urls.append(url)
        return SEARCH if "lawSearch.do" in url else BODY

    source = OfficialKoreanLawSource(transport=transport)
    record, provisions = source.fetch_by_name(
        law_name="개인정보 보호법",
        domain_id="digital_business",
        oc="secret@example.com",
        search_url="https://example.test/lawSearch.do",
        service_url="https://example.test/lawService.do",
    )
    assert record.law_name == "개인정보 보호법"
    assert record.law_id == "011357"
    assert record.mst == "270351"
    assert record.current_history_code == "현행"
    assert record.effective_date.isoformat() == "2024-03-15"
    assert record.detail_link == "/DRF/lawService.do?MST=270351"
    assert provisions
    assert any("MST=270351" in url for url in requested_urls)
    assert not any("ID=011357" in url for url in requested_urls if "lawService.do" in url)


def test_search_metadata_failure_and_parse_diagnostic():
    failed = b"<LawSearch><totalCnt>0</totalCnt><resultCode>99</resultCode><resultMsg>denied</resultMsg></LawSearch>"
    source = OfficialKoreanLawSource(transport=lambda url, timeout: failed)
    with pytest.raises(OfficialLawApiError, match="resultCode=99"):
        source.search_laws(query="민법", oc="secret")

    malformed_candidate = """<LawSearch><totalCnt>1</totalCnt><resultCode>00</resultCode><resultMsg>success</resultMsg><law><법령일련번호>1</법령일련번호></law></LawSearch>""".encode()
    source = OfficialKoreanLawSource(transport=lambda url, timeout: malformed_candidate)
    with pytest.raises(OfficialLawApiError, match="파싱된 후보가 없습니다.*진단"):
        source.search_laws(query="민법", oc="secret")


def test_oc_is_redacted_from_transport_errors():
    def fail(url, timeout):
        raise RuntimeError("request failed: " + url)

    source = OfficialKoreanLawSource(transport=fail)
    with pytest.raises(OfficialLawApiError) as caught:
        source.search_laws(query="민법", oc="very-secret")
    message = str(caught.value)
    assert "very-secret" not in message
    assert "OC=[REDACTED]" in message


def test_manifest_sync_replaces_existing_corpus_by_default(tmp_path):
    existing = tmp_path / "corpus.json"
    existing.write_text('[{"document_id":"legacy:1","law_id":"legacy","law_name":"Legacy","article_no":"제1조","text":"legacy","effective_from":"2020-01-01","is_current":true,"domain_tags":["digital_business"]}]', encoding="utf-8")
    source = OfficialKoreanLawSource(transport=lambda url, timeout: SEARCH if "lawSearch.do" in url else BODY)
    result = OfficialCorpusSynchronizer(source).sync(
        LawSyncManifest((LawSyncItem(domain_id="digital_business", law_name="개인정보 보호법"),)),
        oc="secret", output=existing, cache_dir=tmp_path / "cache",
        search_url="https://example.test/lawSearch.do", service_url="https://example.test/lawService.do",
    )
    payload = existing.read_text(encoding="utf-8")
    assert "legacy:1" not in payload
    assert result["corpus"]["mode"] == "replace"


def test_manifest_sync_can_merge_when_explicitly_requested(tmp_path):
    existing = tmp_path / "corpus.json"
    existing.write_text('[{"document_id":"legacy:1","law_id":"legacy","law_name":"Legacy","article_no":"제1조","text":"legacy","effective_from":"2020-01-01","is_current":true,"domain_tags":["digital_business"]}]', encoding="utf-8")
    source = OfficialKoreanLawSource(transport=lambda url, timeout: SEARCH if "lawSearch.do" in url else BODY)
    OfficialCorpusSynchronizer(source).sync(
        LawSyncManifest((LawSyncItem(domain_id="digital_business", law_name="개인정보 보호법"),)),
        oc="secret", output=existing, cache_dir=tmp_path / "cache",
        search_url="https://example.test/lawSearch.do", service_url="https://example.test/lawService.do",
        merge_output=True,
    )
    assert "legacy:1" in existing.read_text(encoding="utf-8")
