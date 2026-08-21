const $ = (selector) => document.querySelector(selector);

function escapeHtml(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

async function readJsonResponse(response) {
  const body = await response.text();
  try { return body ? JSON.parse(body) : {}; }
  catch { throw new Error(`서버가 JSON이 아닌 응답을 반환했습니다. HTTP ${response.status}: ${body.slice(0, 160)}`); }
}

async function loadEnvironment() {
  try {
    const [healthResponse, configResponse] = await Promise.all([fetch("/health"), fetch("/demo-config")]);
    if (healthResponse.ok) {
      const health = await readJsonResponse(healthResponse);
      $("#brand-version").textContent = `v${health.version.replace(/^v/, "")}`;
    }
    if (configResponse.ok) {
      const config = await readJsonResponse(configResponse);
      if (!config.evaluation_run_enabled) $("#review-disabled-note").hidden = false;
    }
  } catch { $("#brand-version").textContent = "오프라인"; }
}

function documentLabel(document) {
  return `${document.law_name || document.law_id || "문서"} ${document.article_no || ""}`.trim();
}

function documentSnippet(document) {
  const value = String(document.text || "");
  return value.length > 500 ? `${value.slice(0, 500)}…` : value;
}

const reviewDecisionLabels = {
  approve: "승인",
  revise: "수정 요청",
  reject: "거절",
  deprecate: "사용 중단",
};

function reviewStatus(row) {
  if (!row.review_processed) return {label: "검수 필요", className: "failed"};
  const decision = row.latest_review?.decision || "";
  if (decision === "approve") return {label: "승인", className: "passed"};
  if (decision === "revise") return {label: "수정 요청", className: "review-revised"};
  return {label: reviewDecisionLabels[decision] || row.review_status, className: "failed"};
}

function reviewPanel(row) {
  if (!row.review_processed) return `<textarea class="review-comment" rows="2" placeholder="후보의 실제 비관련성·법적 구별 필요성을 확인하세요."></textarea>
    <div class="review-actions"><button class="secondary-button" data-decision="revise">수정 요청</button><button class="secondary-button review-reject" data-decision="reject">거절</button><button class="primary-button compact" data-decision="approve">승인</button></div>`;
  const review = row.latest_review || {};
  const comment = review.review_comment || "검수 의견 없음";
  return `<div class="review-record">
    <strong>${escapeHtml(reviewDecisionLabels[review.decision] || row.review_status)} 처리 완료</strong>
    <p>${escapeHtml(comment)}</p>
    <small>${escapeHtml(review.reviewer_id || "")}${review.reviewed_at ? ` · ${escapeHtml(review.reviewed_at)}` : ""}</small>
  </div>`;
}

function renderHardNegativeQueue(payload) {
  const pool = payload.candidate_pool || {};
  const hidden = payload.hidden_additional_count || 0;
  $("#hard-negative-summary").textContent = `${pool.dataset_id || "hard_negative_candidates"} · 선택 범위 ${pool.candidate_count || 0}건 / 전체 ${pool.total_candidate_count || 0}건 · 미처리 ${payload.pending_count || 0}건 · 처리 ${payload.processed_count || 0}건 · 추가 후보 숨김 ${hidden}건 · 표시 ${payload.returned_count || 0}건`;
  const rows = payload.candidates || [];
  $("#hard-negative-queue").innerHTML = rows.map((row) => {
    const positives = row.positive_documents || [];
    const negatives = row.hard_negative_documents || [];
    const status = reviewStatus(row);
    return `<article class="case-card review-case ${status.className}" data-case-id="${escapeHtml(row.candidate_id)}" data-target-type="training_candidate">
      <div><span class="case-status">${escapeHtml(status.label)}</span><strong>${escapeHtml(row.source?.case_id || row.candidate_id)}</strong><small>${escapeHtml(row.source?.method || "")}</small></div>
      <h3>${escapeHtml(row.query)}</h3>
      <p><b>실패 유형</b> ${escapeHtml((row.failure_types || []).join(", "))}${row.additional_candidate_count ? ` · <b>같은 사례 추가 후보</b> ${row.additional_candidate_count}건` : ""}</p>
      <details><summary><b>Positive</b> ${positives.map((item) => escapeHtml(documentLabel(item))).join(" · ") || "없음"}</summary>${positives.map((item) => `<p>${escapeHtml(documentSnippet(item))}</p>`).join("")}</details>
      <details><summary><b>Hard negative</b> ${negatives.map((item) => escapeHtml(documentLabel(item))).join(" · ") || "없음"}</summary>${negatives.map((item) => `<p>${escapeHtml(documentSnippet(item))}</p>`).join("")}</details>
      ${reviewPanel(row)}
    </article>`;
  }).join("") || '<div class="empty-state">현재 검수가 필요한 hard-negative 후보가 없습니다.</div>';
}

function syncCandidateVersions(pool) {
  const select = $("#hard-negative-version");
  const selected = select.value;
  const versions = pool.versions || [];
  select.innerHTML = '<option value="">전체 버전</option>' + versions.map((version) => `<option value="${escapeHtml(version)}">${escapeHtml(version)}</option>`).join("");
  select.value = versions.includes(selected) ? selected : "";
}

async function loadHardNegativeQueue() {
  try {
    const includeProcessed = $("#include-processed-hard-negatives").checked;
    const includeAdditional = $("#include-additional-hard-negatives").checked;
    const domain = $("#hard-negative-domain").value;
    const version = $("#hard-negative-version").value;
    const params = new URLSearchParams({
      include_processed: String(includeProcessed),
      one_per_case: String(!includeAdditional),
    });
    if (domain) params.set("domain", domain);
    if (version) params.set("candidate_pool_version", version);
    const response = await fetch(`/training/hard-negatives/queue?${params}`);
    const data = await readJsonResponse(response);
    if (!response.ok) throw new Error(data.detail?.message || "Hard-negative 후보를 불러오지 못했습니다.");
    syncCandidateVersions(data.candidate_pool || {});
    renderHardNegativeQueue(data);
  } catch (error) { window.alert(error.message); }
}

async function saveReview(card, decision) {
  if (card.dataset.saving === "true") return;
  const reviewerId = $("#reviewer-id").value.trim();
  const comment = card.querySelector(".review-comment").value.trim();
  if (!reviewerId) return window.alert("Reviewer ID를 입력하세요.");
  card.dataset.saving = "true";
  card.querySelectorAll("button[data-decision]").forEach((button) => { button.disabled = true; });
  try {
    const response = await fetch("/evaluation/reviews", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({target_type: "training_candidate", target_id: card.dataset.caseId, decision, reviewer_id: reviewerId, review_comment: comment}),
    });
    const data = await readJsonResponse(response);
    if (!response.ok) throw new Error(data.detail?.message || "검수 기록 저장에 실패했습니다.");
    await loadHardNegativeQueue();
  } catch (error) {
    card.dataset.saving = "false";
    card.querySelectorAll("button[data-decision]").forEach((button) => { button.disabled = false; });
    window.alert(error.message);
  }
}

$("#load-hard-negative-queue").addEventListener("click", loadHardNegativeQueue);
$("#include-processed-hard-negatives").addEventListener("change", loadHardNegativeQueue);
$("#include-additional-hard-negatives").addEventListener("change", loadHardNegativeQueue);
$("#hard-negative-domain").addEventListener("change", loadHardNegativeQueue);
$("#hard-negative-version").addEventListener("change", loadHardNegativeQueue);
$("#hard-negative-queue").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-decision]");
  if (button) saveReview(button.closest(".review-case"), button.dataset.decision);
});

loadEnvironment();
loadHardNegativeQueue();
