const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);
const form = $("#query-form");
let evaluationCases = [];

function esc(v) { return String(v ?? "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;"); }
function pct(v) { return `${(Number(v || 0) * 100).toFixed(1)}%`; }

async function loadHealth() {
  try { const r = await fetch('/health'); const d = await r.json();
    $('#health-dot').classList.add('ok'); $('#health-text').textContent='API 정상';
    $('#health-meta').textContent=`법령 문서 ${d.provision_count}건 · 도메인 ${d.domain_count}개 · ${d.version}`;
  } catch { $('#health-text').textContent='API 연결 실패'; }
}
async function loadDomains() {
  const r = await fetch('/domains'); if (!r.ok) return;
  (await r.json()).forEach(d => { const o=document.createElement('option'); o.value=d.domain_id; o.textContent=d.display_name; $('#domain').append(o); });
}

$$('.tab').forEach(btn => btn.addEventListener('click', () => {
  $$('.tab').forEach(x=>x.classList.remove('active')); $$('.panel').forEach(x=>x.classList.remove('active'));
  btn.classList.add('active'); $(`#${btn.dataset.tab}`).classList.add('active');
}));
$$('[data-question]').forEach(b => b.addEventListener('click',()=>{ $('#question').value=b.dataset.question; $('#question').focus(); }));

function renderQuery(data) {
  const st=data.evidence_status || {level:'insufficient',message:'근거 상태 없음'};
  $('#result-question').textContent=data.question; $('#evidence-badge').textContent=st.level; $('#evidence-badge').className=`evidence-badge ${st.level}`;
  $('#status-message').textContent=st.message; $('#result-list').innerHTML='';
  const ac=$('#answer-card');
  if ('answer' in data) {
    ac.hidden=false; $('#answer-content').textContent=data.answer || '(답변 없음)';
    $('#generation-badge').textContent=data.generation_status; $('#generation-badge').className=`generation ${data.generation_status}`;
    const cv=data.citation_validation || {}; $('#citation-status').innerHTML=`인용 검증: <strong>${cv.valid ? '통과' : '실패'}</strong>${cv.unsupported_articles?.length ? ` · 미지원 인용 ${esc(cv.unsupported_articles.join(', '))}` : ''}`;
  } else ac.hidden=true;
  (data.results || []).forEach(r => {
    const el=document.createElement('article'); el.className='result-card';
    el.innerHTML=`<div class="result-card-header"><h3><span class="rank">${r.rank}</span>${esc(r.citation)}</h3><span class="reason">${r.retrieval_reason==='direct'?'직접':'관련'}</span></div><p>${esc(r.text)}</p><div class="result-meta"><span>종합 ${Number(r.score).toFixed(4)}</span><span>키워드 ${Number(r.lexical_score).toFixed(4)}</span><span>의미 ${Number(r.semantic_score).toFixed(4)}</span><span>시행일 ${esc(r.effective_from||'미상')}</span>${r.source_url?`<a href="${esc(r.source_url)}" target="_blank" rel="noopener">공식 출처</a>`:''}</div>`;
    $('#result-list').append(el);
  });
  $('#prompt-panel').hidden=!data.prompt; $('#prompt-content').textContent=data.prompt || '';
  $('#result-section').hidden=false; $('#result-section').scrollIntoView({behavior:'smooth'});
}
form.addEventListener('submit', async e => {
  e.preventDefault(); const btn=$('#submit-button'); btn.disabled=true; btn.textContent='처리 중…';
  try {
    const mode=$('#mode').value; const body={question:$('#question').value.trim(),domain:$('#domain').value,top_k:Number($('#top-k').value)};
    if ($('#as-of-date').value) body.as_of_date=$('#as-of-date').value;
    const r=await fetch(`/${mode}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}); const d=await r.json();
    if(!r.ok) throw new Error(d.detail?.message || JSON.stringify(d.detail)); renderQuery(d);
  } catch(err) { alert(err.message || '요청 실패'); }
  finally { btn.disabled=false; btn.textContent='검증 실행'; }
});

function renderEvaluation(report) {
  const s=report.summary; $('#evaluation-empty').hidden=true; $('#evaluation-content').hidden=false;
  const metrics=[['통과율',pct(s.pass_rate)],['Top-1',pct(s.top1_accuracy)],['Hit@K',pct(s.hit_at_k)],['Recall@K',pct(s.mean_recall_at_k)],['MRR',Number(s.mean_reciprocal_rank).toFixed(3)],['Abstention',pct(s.abstention_accuracy)],['시행일',pct(s.temporal_accuracy)],['인용',s.citation_accuracy==null?'N/A':pct(s.citation_accuracy)],['평균 지연',`${Number(s.average_latency_ms).toFixed(2)} ms`]];
  $('#metric-grid').innerHTML=metrics.map(([k,v])=>`<article><span>${k}</span><strong>${v}</strong></article>`).join('');
  evaluationCases=report.cases || []; renderCases($('#case-filter').value);
}
function renderCases(filter) {
  const rows=evaluationCases.filter(c=>filter==='all'||(filter==='passed'&&c.passed)||(filter==='failed'&&!c.passed));
  $('#case-list').innerHTML=rows.map(c=>`<article class="case-card ${c.passed?'passed':'failed'}"><div><span class="case-status">${c.passed?'PASS':'FAIL'}</span><strong>${esc(c.case_id)}</strong><small>${esc(c.domain)}</small></div><h3>${esc(c.question)}</h3><dl><div><dt>예상</dt><dd>${esc(c.expected_document_ids.join(', ')||'abstain')}</dd></div><div><dt>검색</dt><dd>${esc(c.retrieved_document_ids.join(', ')||'없음')}</dd></div></dl><p>Top1 ${c.top1_hit?'✓':'✕'} · Abstention ${c.abstention_correct?'✓':'✕'} · 시행일 ${c.temporal_valid?'✓':'✕'} · 인용 ${c.citation_valid==null?'N/A':c.citation_valid?'✓':'✕'} · ${c.latency_ms}ms</p></article>`).join('') || '<div class="empty-state">조건에 맞는 사례가 없습니다.</div>';
}
$('#case-filter').addEventListener('change',e=>renderCases(e.target.value));
$('#load-report').addEventListener('click',async()=>{ try{const r=await fetch('/evaluation/latest');const d=await r.json();if(!r.ok)throw new Error(d.detail?.message||'리포트 없음');renderEvaluation(d);}catch(e){alert(e.message);} });
$('#run-evaluation').addEventListener('click',async e=>{const b=e.currentTarget;b.disabled=true;b.textContent='평가 중…';try{const r=await fetch('/evaluation/run',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});const d=await r.json();if(!r.ok)throw new Error(d.detail?.message||'평가 실패');renderEvaluation(d);}catch(err){alert(err.message);}finally{b.disabled=false;b.textContent='전체 평가 실행';}});

loadHealth(); loadDomains();
