const $ = (selector) => document.querySelector(selector);
let evaluationCases = [];

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function percent(value) {
  return `${(Number(value || 0) * 100).toFixed(1)}%`;
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
        $("#evaluation-disabled-note").hidden = false;
      }
    }
  } catch {
    $("#brand-version").textContent = "오프라인";
  }
}

function renderEvaluation(report) {
  const summary = report.summary;
  $("#evaluation-empty").hidden = true;
  $("#evaluation-content").hidden = false;
  const metrics = [
    ["통과율", percent(summary.pass_rate)],
    ["Top-1 정확도", percent(summary.top1_accuracy)],
    ["Hit@K", percent(summary.hit_at_k)],
    ["평균 Recall@K", percent(summary.mean_recall_at_k)],
    ["MRR", Number(summary.mean_reciprocal_rank).toFixed(3)],
    ["답변 유보 정확도", percent(summary.abstention_accuracy)],
    ["시행일 정확도", percent(summary.temporal_accuracy)],
    ["인용 정확도", summary.citation_accuracy == null ? "해당 없음" : percent(summary.citation_accuracy)],
    ["평균 지연", `${Number(summary.average_latency_ms).toFixed(2)} ms`],
  ];
  $("#metric-grid").innerHTML = metrics.map(([key, value]) => `<article><span>${key}</span><strong>${value}</strong></article>`).join("");
  evaluationCases = report.cases || [];
  renderCases($("#case-filter").value);
}

function renderCases(filter) {
  const cases = evaluationCases.filter((item) => filter === "all" || (filter === "passed" && item.passed) || (filter === "failed" && !item.passed));
  $("#case-list").innerHTML = cases.map((item) => `<article class="case-card ${item.passed ? "passed" : "failed"}"><div><span class="case-status">${item.passed ? "통과" : "실패"}</span><strong>${escapeHtml(item.case_id)}</strong><small>${escapeHtml(item.domain)}</small></div><h3>${escapeHtml(item.question)}</h3><dl><div><dt>예상 문서</dt><dd>${escapeHtml(item.expected_document_ids.join(", ") || "답변 유보")}</dd></div><div><dt>검색 문서</dt><dd>${escapeHtml(item.retrieved_document_ids.join(", ") || "없음")}</dd></div></dl><p>Top-1 ${item.top1_hit ? "✓" : "✕"} · 답변 유보 ${item.abstention_correct ? "✓" : "✕"} · 시행일 ${item.temporal_valid ? "✓" : "✕"} · 인용 ${item.citation_valid == null ? "해당 없음" : item.citation_valid ? "✓" : "✕"} · ${item.latency_ms}ms</p></article>`).join("") || '<div class="empty-state">조건에 맞는 평가 사례가 없습니다.</div>';
}

$("#case-filter").addEventListener("change", (event) => renderCases(event.target.value));
$("#load-report").addEventListener("click", async () => {
  try {
    const response = await fetch("/evaluation/latest");
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail?.message || "저장된 평가 리포트가 없습니다.");
    renderEvaluation(data);
  } catch (error) {
    window.alert(error.message);
  }
});

$("#run-evaluation").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  button.textContent = "전체 평가 실행 중…";
  try {
    const response = await fetch("/evaluation/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail?.message || "평가를 실행하지 못했습니다.");
    renderEvaluation(data);
  } catch (error) {
    window.alert(error.message);
  } finally {
    button.disabled = false;
    button.textContent = "전체 평가 실행";
  }
});

loadEnvironment();
