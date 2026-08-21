from pathlib import Path


STATIC = Path("law_rag/api/static")


def test_console_contains_agent_trace_and_experiment_comparison_sections():
    html = (STATIC / "evaluation.html").read_text(encoding="utf-8")
    assert 'id="run-agent"' in html
    assert 'id="trace-list"' in html
    assert 'id="comparison-grid"' in html
    assert 'id="baseline-experiment"' in html
    assert 'id="agent-experiment"' in html
    assert 'id="run-baseline-experiment"' in html
    assert 'id="run-agent-experiment"' in html
    assert 'id="experiment-run-status"' in html
    assert 'id="comparison-case-list"' in html
    assert 'id="load-ablations"' in html
    assert 'id="ablation-methods"' in html
    assert 'id="ablation-comparisons"' in html


def test_console_script_renders_required_trace_evidence():
    script = (STATIC / "evaluation.js").read_text(encoding="utf-8")
    assert "run.execution_trace" in script
    assert "step.selected_evidence_ids" in script
    assert "step.search_strategy" in script
    assert "step.failure_reason" in script
    assert "run.retry_count" in script
    assert "run.stop_reason" in script
    assert 'fetch("/experiments/compare"' in script
    assert 'fetch("/experiments/run"' in script
    assert 'runSavedExperiment("baseline")' in script
    assert 'runSavedExperiment("agent")' in script
    assert 'fetch("/experiments/ablations")' in script
    assert "renderAblation" in script


def test_console_styles_are_responsive_without_chart_dependency():
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    assert ".trace-list" in css
    assert ".comparison-grid" in css
    assert ".experiment-selector" in css
    assert "@media(max-width:650px)" in css
    assert "chart" not in (STATIC / "evaluation.html").read_text(encoding="utf-8").lower()
