const $ = (selector) => document.querySelector(selector);
let evaluationCases = [];
let savedComparison = null;

function escapeHtml(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

function percent(value) {
  return value == null ? "해당 없음" : `${(Number(value) * 100).toFixed(1)}%`;
}

function statusLabel(status) {
  return {completed: "완료", warning: "경고", abstained: "보류", failed: "실패", skipped: "건너뜀", running: "실행 중"}[status] || status;
}

async function readJsonResponse(response) {
  const body = await response.text();
  try {
    return body ? JSON.parse(body) : {};
  } catch {
    throw new Error(`서버가 JSON이 아닌 응답을 반환했습니다. HTTP ${response.status}: ${body.slice(0, 160)}`);
  }
}

async function loadEnvironment() {
  try {
    const [healthResponse, configResponse] = await Promise.all([fetch("/health"), fetch("/demo-config")]);
    if (healthResponse.ok) {
      const health = await healthResponse.json();
      $("#brand-version").textContent = `v${health.version.replace(/^v/, "")}`;
    }
    if (configResponse.ok) {
      const config = await configResponse.json();
      if (!config.evaluation_run_enabled) {
        $("#run-evaluation").hidden = true;
        document.querySelectorAll(".experiment-run-button").forEach((button) => { button.hidden = true; });
        $("#evaluation-disabled-note").hidden = false;
        $("#review-disabled-note").hidden = false;
        $("#experiment-run-status").textContent = "현재 서버 설정에서는 신규 실험 실행이 비활성화되어 있습니다.";
      }
    }
  } catch {
    $("#brand-version").textContent = "오프라인";
  }
}

function renderReviewQueue(payload) {
  const dataset = payload.dataset || {};
  $("#review-dataset-summary").textContent = `${dataset.dataset_id || "dataset"} v${dataset.dataset_version || "?"} · ${payload.queue_count || 0}건 표시 · ${String(dataset.content_sha256 || "").slice(0, 12)}`;
  const rows = payload.cases || [];
  $("#review-queue").innerHTML = rows.map((row) => `<article class="case-card review-case ${row.review_status === "approved" ? "passed" : "failed"}" data-case-id="${escapeHtml(row.case_id)}" data-target-type="evaluation_case">
    <div><span class="case-status">${escapeHtml(row.review_status)}</span><strong>${escapeHtml(row.case_id)}</strong><small>${escapeHtml(row.category || "")}</small></div>
    <h3>${escapeHtml(row.question)}</h3>
    <textarea class="review-comment" rows="2" placeholder="수정 요청·거절 시 검수 의견을 입력하세요.">${escapeHtml(row.latest_review?.review_comment || "")}</textarea>
    <div class="review-actions">
      <button class="secondary-button" data-decision="revise">수정 요청</button>
      <button class="secondary-button review-reject" data-decision="reject">거절</button>
      <button class="primary-button compact" data-decision="approve">승인</button>
    </div>
  </article>`).join("") || '<div class="empty-state">현재 검수가 필요한 사례가 없습니다.</div>';
}

async function loadReviewQueue() {
  try {
    const includeApproved = $("#include-approved-reviews").checked;
    const response = await fetch(`/evaluation/reviews/queue?include_approved=${includeApproved}`);
    const data = await readJsonResponse(response);
    if (!response.ok) throw new Error(data.detail?.message || "검수 큐를 불러오지 못했습니다.");
    renderReviewQueue(data);
  } catch (error) { window.alert(error.message); }
}

async function saveReview(card, decision) {
  const reviewerId = $("#reviewer-id").value.trim();
  const comment = card.querySelector(".review-comment").value.trim();
  if (!reviewerId) return window.alert("Reviewer ID를 입력하세요.");
  try {
    const response = await fetch("/evaluation/reviews", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({target_type: "evaluation_case", target_id: card.dataset.caseId, decision, reviewer_id: reviewerId, review_comment: comment}),
    });
    const data = await readJsonResponse(response);
    if (!response.ok) throw new Error(data.detail?.message || "검수 기록 저장에 실패했습니다.");
    await loadReviewQueue();
  } catch (error) { window.alert(error.message); }
}

function renderAgent(run) {
  $("#agent-empty").hidden = true;
  $("#agent-content").hidden = false;
  const response = run.response || {};
  const confidence = response.confidence || {};
  $("#agent-summary").innerHTML = `
    <article><span>실행 결과</span><strong>${escapeHtml(run.outcome)}</strong></article>
    <article><span>검색 전략</span><strong>${escapeHtml(run.config.search_strategy)}</strong></article>
    <article><span>재시도</span><strong>${Number(run.retry_count || 0)}회</strong></article>
    <article><span>최종 신뢰도</span><strong>${confidence.score == null ? "해당 없음" : Number(confidence.score).toFixed(3)}</strong></article>
    <article><span>품질 판정</span><strong>${escapeHtml(run.final_quality || "보류")}</strong></article>
    <article><span>중단 사유</span><strong>${escapeHtml(run.stop_reason || "없음")}</strong></article>`;
  $("#trace-list").innerHTML = (run.execution_trace || []).map((step, index) => {
    const evidence = step.selected_evidence_ids || [];
    const warnings = step.warnings || [];
    return `<article class="trace-step ${escapeHtml(step.status)}">
      <div class="trace-index">${index + 1}</div>
      <div class="trace-body"><div class="trace-heading"><strong>${escapeHtml(step.step_name)}</strong><span class="trace-status ${escapeHtml(step.status)}">${escapeHtml(statusLabel(step.status))}</span></div>
      <p>${step.duration_ms == null ? "실행되지 않음" : `${Number(step.duration_ms).toFixed(2)}ms`} · 신뢰도 ${step.confidence == null ? "해당 없음" : Number(step.confidence).toFixed(3)}</p>
      ${step.search_strategy ? `<p>검색 전략: <b>${escapeHtml(step.search_strategy)}</b></p>` : ""}
      ${evidence.length ? `<div class="trace-chips">${evidence.map((id) => `<span>${escapeHtml(id)}</span>`).join("")}</div>` : ""}
      ${warnings.length ? `<p class="trace-warning">${warnings.map(escapeHtml).join(" · ")}</p>` : ""}
      ${step.failure_reason ? `<p class="trace-failure">${escapeHtml(step.failure_reason)}</p>` : ""}</div>
    </article>`;
  }).join("");
}

async function runAgent(event) {
  const button = event.currentTarget;
  button.disabled = true;
  button.textContent = "실행 중…";
  try {
    const response = await fetch("/agent/runs", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        question: $("#agent-question").value,
        domain: $("#agent-domain").value,
        top_k: Number($("#agent-top-k").value),
        search_strategy: $("#agent-strategy").value,
        max_retries: 1,
      }),
    });
    const data = await readJsonResponse(response);
    if (!response.ok) throw new Error(data.detail?.message || "Agent 실행에 실패했습니다.");
    renderAgent(data);
  } catch (error) { window.alert(error.message); }
  finally { button.disabled = false; button.textContent = "Agent 실행"; }
}

function metricCard(label, baseline, agent, formatter = percent) {
  const delta = baseline == null || agent == null ? null : Number(agent) - Number(baseline);
  return `<article><span>${escapeHtml(label)}</span><div><b>Baseline ${formatter(baseline)}</b><b>Agent ${formatter(agent)}</b></div><small>${delta == null ? "비교 불가" : `변화 ${delta >= 0 ? "+" : ""}${formatter(delta)}`}</small></article>`;
}

function renderVerifiedComparison(report) {
  $("#comparison-empty").hidden = true;
  $("#comparison-content").hidden = false;
  const baseline = report.baseline;
  const agent = report.agent;
  $("#comparison-grid").innerHTML = [
    metricCard("전체 통과율", baseline.overall_pass_rate, agent.overall_pass_rate),
    metricCard("Top-1 정확도", baseline.top1_accuracy, agent.top1_accuracy),
    metricCard("Hit@K", baseline.hit_at_k, agent.hit_at_k),
    metricCard("보류 대상 정확도", baseline.expected_abstention_accuracy, agent.expected_abstention_accuracy),
    metricCard("불필요한 보류율", baseline.false_abstention_rate, agent.false_abstention_rate),
    metricCard("평균 응답시간", baseline.average_latency_ms, agent.average_latency_ms, (v) => v == null ? "해당 없음" : `${Number(v).toFixed(1)}ms`),
  ].join("");
  const comparison = report.comparison;
  $("#comparison-counts").innerHTML = [
    ["개선", comparison.improved_cases], ["악화", comparison.regressed_cases],
    ["동일 통과", comparison.unchanged_pass_cases], ["동일 실패", comparison.unchanged_failure_cases],
  ].map(([label, value]) => `<article><span>${label}</span><strong>${value}건</strong></article>`).join("");
  $("#comparison-tradeoff").textContent = `안전한 보류는 개선됐지만 평균 응답시간은 ${Number(comparison.average_latency_ms_delta).toFixed(1)}ms 증가했고, 불필요한 보류율은 ${(Number(comparison.false_abstention_rate_delta) * 100).toFixed(1)}%p 증가했습니다. 재시도 품질 개선률은 ${(Number(agent.retry_improvement_rate || 0) * 100).toFixed(1)}%입니다.`;
}

async function loadVerifiedComparison() {
  try {
    const response = await fetch("/experiments/verified-summary");
    const data = await readJsonResponse(response);
    if (!response.ok) throw new Error(data.detail?.message || "검증 결과를 불러오지 못했습니다.");
    renderVerifiedComparison(data);
  } catch (error) { window.alert(error.message); }
}

function renderAblation(report) {
  $("#ablation-empty").hidden = true;
  $("#ablation-content").hidden = false;
  const counts = report.summary?.status_counts || {};
  $("#ablation-summary").innerHTML = [
    ["완료", counts.completed || 0], ["미실행", counts.not_run || 0],
    ["사용 불가", counts.unavailable || 0], ["실패", counts.failed || 0],
  ].map(([label, value]) => `<article><span>${label}</span><strong>${value}개</strong></article>`).join("");
  const methods = report.ablation?.methods || [];
  $("#ablation-methods").innerHTML = methods.map((row) => {
    const metrics = row.result?.metrics;
    const detail = metrics
      ? `Top-1 ${percent(metrics.top1_accuracy)} · Hit@K ${percent(metrics.hit_at_k)} · MRR ${Number(metrics.mrr).toFixed(3)} · ${Number(metrics.average_latency_ms).toFixed(1)}ms`
      : escapeHtml(row.availability_reason || row.error || "실행 결과 없음");
    return `<article class="case-card ${row.status === "failed" ? "failed" : row.status === "completed" ? "passed" : ""}"><div><span class="case-status">${escapeHtml(row.status)}</span><strong>${escapeHtml(row.method)}</strong><small>baseline ${escapeHtml(row.baseline_method || "없음")}</small></div><p>${detail}</p></article>`;
  }).join("") || '<div class="empty-state">Ablation method가 없습니다.</div>';
  const comparisons = report.ablation?.comparisons || [];
  $("#ablation-comparisons").innerHTML = comparisons.map((row) => {
    const delta = row.metric_deltas || {};
    return `<article class="case-card ${row.regression_status === "regressed" ? "failed" : "passed"}"><div><span class="case-status">${escapeHtml(row.regression_status)}</span><strong>${escapeHtml(row.baseline_method)} → ${escapeHtml(row.treatment_method)}</strong></div><p>Hit@K ${Number(delta.hit_at_k || 0) >= 0 ? "+" : ""}${Number(delta.hit_at_k || 0).toFixed(4)} · MRR ${Number(delta.mrr || 0) >= 0 ? "+" : ""}${Number(delta.mrr || 0).toFixed(4)} · latency ${Number(delta.average_latency_ms || 0) >= 0 ? "+" : ""}${Number(delta.average_latency_ms || 0).toFixed(1)}ms</p><small>악화 지표: ${escapeHtml((row.quality_regressions || []).join(", ") || "없음")}</small></article>`;
  }).join("") || '<div class="empty-state">함께 완료된 baseline과 treatment가 없어 비교 수치가 없습니다.</div>';
}

async function loadAblations() {
  try {
    const response = await fetch("/experiments/ablations");
    const rows = await readJsonResponse(response);
    if (!response.ok) throw new Error(rows.detail?.message || "Ablation 결과를 불러오지 못했습니다.");
    if (!rows.length) return;
    renderAblation(rows[0]);
  } catch (error) { window.alert(error.message); }
}

async function loadExperiments() {
  try {
    const response = await fetch("/experiments");
    const rows = await readJsonResponse(response);
    if (!response.ok) throw new Error(rows.detail?.message || "실험 목록을 불러오지 못했습니다.");
    const baseline = rows.filter((row) => row.config.mode === "baseline");
    const agents = rows.filter((row) => row.config.mode === "agent");
    $("#baseline-experiment").innerHTML = '<option value="">선택</option>' + baseline.map((row) => `<option value="${escapeHtml(row.experiment_id)}">${escapeHtml(row.experiment_id)} · ${row.dataset.case_count}건</option>`).join("");
    $("#agent-experiment").innerHTML = '<option value="">선택</option>' + agents.map((row) => `<option value="${escapeHtml(row.experiment_id)}">${escapeHtml(row.experiment_id)} · ${row.dataset.case_count}건</option>`).join("");
  } catch (error) { window.alert(error.message); }
}

async function runSavedExperiment(mode) {
  const label = mode === "baseline" ? "Baseline" : "Agent";
  if (!window.confirm(`${label} 실험을 61개 전체 데이터로 실행할까요? 완료될 때까지 이 페이지를 닫지 마세요.`)) return;
  const buttons = document.querySelectorAll(".experiment-run-button");
  buttons.forEach((button) => { button.disabled = true; });
  const status = $("#experiment-run-status");
  status.className = "experiment-run-status running";
  status.textContent = `${label} 실험 실행 중… 61개 문항을 순차 평가하고 있습니다.`;
  try {
    const response = await fetch("/experiments/run", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({mode, search_strategy: "hybrid", max_retries: 1, abstention_policy: true}),
    });
    const data = await readJsonResponse(response);
    if (!response.ok) throw new Error(data.detail?.message || `${label} 실험 실행에 실패했습니다.`);
    await loadExperiments();
    const select = mode === "baseline" ? $("#baseline-experiment") : $("#agent-experiment");
    select.value = data.experiment_id;
    status.className = "experiment-run-status completed";
    status.textContent = `${label} 실험 저장 완료: ${data.experiment_id} · ${data.dataset?.case_count || data.cases?.length || 0}건`;
  } catch (error) {
    status.className = "experiment-run-status failed";
    status.textContent = error.message;
  } finally {
    buttons.forEach((button) => { button.disabled = false; });
  }
}

function renderComparisonCases(group) {
  const rows = savedComparison?.case_groups?.[group] || [];
  $("#comparison-case-list").innerHTML = rows.map((row) => `<article class="case-card ${group === "regressed" ? "failed" : "passed"}">
    <div><span class="case-status">${escapeHtml(group)}</span><strong>${escapeHtml(row.case_id)}</strong></div>
    <p>Baseline: ${escapeHtml((row.baseline_failures || []).join(", ") || "통과")}</p>
    <p>Agent: ${escapeHtml((row.candidate_failures || []).join(", ") || "통과")}</p>
    <p>Trace Run ID: ${escapeHtml(row.candidate_run_id || "없음")}</p>
  </article>`).join("") || '<div class="empty-state">해당 사례가 없습니다.</div>';
}

async function compareExperiments() {
  const baselineId = $("#baseline-experiment").value;
  const agentId = $("#agent-experiment").value;
  if (!baselineId || !agentId) return window.alert("비교할 두 실험을 선택하세요.");
  try {
    const response = await fetch("/experiments/compare", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({baseline_experiment_id: baselineId, candidate_experiment_id: agentId})});
    const data = await readJsonResponse(response);
    if (!response.ok) throw new Error(data.detail?.message || "실험 비교에 실패했습니다.");
    savedComparison = data;
    $("#saved-comparison").hidden = false;
    $("#saved-comparison-counts").innerHTML = Object.entries(data.counts).map(([label, value]) => `<article><span>${escapeHtml(label)}</span><strong>${value}건</strong></article>`).join("");
    renderComparisonCases($("#comparison-filter").value);
  } catch (error) { window.alert(error.message); }
}

function renderEvaluation(report) {
  const summary = report.summary;
  $("#evaluation-empty").hidden = true;
  $("#evaluation-content").hidden = false;
  const metrics = [["통과율", percent(summary.pass_rate)], ["Top-1 정확도", percent(summary.top1_accuracy)], ["Hit@K", percent(summary.hit_at_k)], ["평균 Recall@K", percent(summary.mean_recall_at_k)], ["MRR", Number(summary.mean_reciprocal_rank).toFixed(3)], ["답변 유보 정확도", percent(summary.abstention_accuracy)], ["시행일 정확도", percent(summary.temporal_accuracy)], ["인용 정확도", summary.citation_accuracy == null ? "해당 없음" : percent(summary.citation_accuracy)], ["평균 지연", `${Number(summary.average_latency_ms).toFixed(2)} ms`]];
  $("#metric-grid").innerHTML = metrics.map(([key, value]) => `<article><span>${key}</span><strong>${value}</strong></article>`).join("");
  evaluationCases = report.cases || [];
  renderCases($("#case-filter").value);
}

function renderCases(filter) {
  const cases = evaluationCases.filter((item) => filter === "all" || (filter === "passed" && item.passed) || (filter === "failed" && !item.passed));
  $("#case-list").innerHTML = cases.map((item) => `<article class="case-card ${item.passed ? "passed" : "failed"}"><div><span class="case-status">${item.passed ? "통과" : "실패"}</span><strong>${escapeHtml(item.case_id)}</strong><small>${escapeHtml(item.domain)}</small></div><h3>${escapeHtml(item.question)}</h3><p>Top-1 ${item.top1_hit ? "✓" : "✕"} · 답변 유보 ${item.abstention_correct ? "✓" : "✕"} · ${item.latency_ms}ms</p></article>`).join("") || '<div class="empty-state">조건에 맞는 평가 사례가 없습니다.</div>';
}

async function loadLegacyReport() {
  try { const response = await fetch("/evaluation/latest"); const data = await readJsonResponse(response); if (!response.ok) throw new Error(data.detail?.message || "저장된 평가 리포트가 없습니다."); renderEvaluation(data); }
  catch (error) { window.alert(error.message); }
}

async function runLegacyEvaluation(event) {
  const button = event.currentTarget; button.disabled = true; button.textContent = "실행 중…";
  try { const response = await fetch("/evaluation/run", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"}); const data = await readJsonResponse(response); if (!response.ok) throw new Error(data.detail?.message || "평가 실행 실패"); renderEvaluation(data); }
  catch (error) { window.alert(error.message); }
  finally { button.disabled = false; button.textContent = "전체 평가 실행"; }
}

$("#run-agent").addEventListener("click", runAgent);
$("#load-review-queue").addEventListener("click", loadReviewQueue);
$("#include-approved-reviews").addEventListener("change", loadReviewQueue);
$("#review-queue").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-decision]");
  if (button) saveReview(button.closest(".review-case"), button.dataset.decision);
});
$("#load-verified-comparison").addEventListener("click", loadVerifiedComparison);
$("#load-ablations").addEventListener("click", loadAblations);
$("#load-experiments").addEventListener("click", loadExperiments);
$("#run-baseline-experiment").addEventListener("click", () => runSavedExperiment("baseline"));
$("#run-agent-experiment").addEventListener("click", () => runSavedExperiment("agent"));
$("#compare-experiments").addEventListener("click", compareExperiments);
$("#comparison-filter").addEventListener("change", (event) => renderComparisonCases(event.target.value));
$("#case-filter").addEventListener("change", (event) => renderCases(event.target.value));
$("#load-report").addEventListener("click", loadLegacyReport);
$("#run-evaluation").addEventListener("click", runLegacyEvaluation);

loadEnvironment();
loadReviewQueue();
loadVerifiedComparison();
loadAblations();
loadExperiments();
