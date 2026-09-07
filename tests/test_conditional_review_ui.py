from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "law_rag" / "api" / "static"


def test_conditional_review_panel_is_part_of_existing_answer_card():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    answer_start = html.index('id="answer-card"')
    panel_start = html.index('id="conditional-review-panel"')
    answer_end = html.index("</article>", panel_start)

    assert answer_start < panel_start < answer_end
    assert 'id="review-status-badge"' in html
    assert 'id="review-conclusion"' in html
    assert 'id="review-issue-list"' in html
    assert "v=4.27.6" in html


def test_conditional_review_renderer_uses_v9_api_fields_and_safe_dom_text():
    script = (STATIC / "app.js").read_text(encoding="utf-8")

    assert "function renderConditionalReview(data)" in script
    assert "data.conditional_review || {}" in script
    assert "data.practical_action_generator?.actions" in script
    assert "review.priority_facts" in script
    assert "review.issue_reviews" in script
    assert "review.fact_issue_action_links" in script
    assert "issueLink.fact_ids" in script
    assert "issueLink.action_ids" in script
    assert "element.textContent = text || ''" in script
    assert "renderConditionalReview(data);" in script
    assert "renderConditionalReview({});" in script


def test_conditional_review_styles_are_responsive_and_status_specific():
    css = (STATIC / "app.css").read_text(encoding="utf-8")

    assert ".conditional-review" in css
    assert ".review-status.needs-facts" in css
    assert ".priority-1" in css
    assert ".review-columns{display:grid;grid-template-columns:1fr 1fr" in css
    assert "@media(max-width:760px)" in css
    assert ".review-columns{grid-template-columns:1fr}" in css


def test_hard_negative_review_queue_has_dedicated_ui():
    evaluation_html = (STATIC / "evaluation.html").read_text(encoding="utf-8")
    html = (STATIC / "training-review.html").read_text(encoding="utf-8")
    script = (STATIC / "training-review.js").read_text(encoding="utf-8")

    assert 'id="hard-negative-queue"' not in evaluation_html
    assert 'id="hard-negative-queue"' in html
    assert 'id="include-processed-hard-negatives"' in html
    assert 'id="hard-negative-domain"' in html
    assert 'id="hard-negative-version"' in html
    assert 'id="include-additional-hard-negatives"' in html
    assert "Positive" in html
    assert "Hard negative" in html
    assert "승인" in html
    assert "거절" in html
    assert "function loadHardNegativeQueue()" in script
    assert 'params.set("domain", domain)' in script
    assert 'one_per_case: String(!includeAdditional)' in script
    assert 'params.set("candidate_pool_version", version)' in script
    assert 'data-target-type="training_candidate"' in script
    assert 'target_type: "training_candidate"' in script
    assert 'include_processed: String(includeProcessed)' in script
    assert "function reviewPanel(row)" in script
    assert 'class="review-record"' in script
    assert 'if (!row.review_processed)' in script
    assert 'card.dataset.saving = "true"' in script
    assert ".review-record" in (STATIC / "app.css").read_text(encoding="utf-8")
