from __future__ import annotations

from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2] / "app" / "web"


def test_chat_stream_is_part_of_the_latest_workspace() -> None:
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    javascript = (WEB_ROOT / "app.js").read_text(encoding="utf-8")

    assert html.index('id="conversation-stream"') < html.index(
        'class="panel assistant-panel"'
    )
    assert "function beginConversationTurn(query," in javascript
    assert "function completeConversationTurn(answerText)" in javascript
    assert "setPanelHidden(conversationStream, !isChat);" in javascript


def test_history_restore_and_keyboard_send_are_available() -> None:
    javascript = (WEB_ROOT / "app.js").read_text(encoding="utf-8")

    assert 'data-history-index="${index}"' in javascript
    assert (
        "restoreConversationSnapshot(item.query, item.answer);" in javascript
    )
    assert "本机历史摘要" in javascript
    assert 'queryInput.addEventListener("keydown"' in javascript
    assert (
        'event.key !== "Enter" || event.shiftKey || event.isComposing'
        in javascript
    )
    assert "response: responseData || null" in javascript
    assert "if (item.response?.plan)" in javascript
    assert "renderResponse(item.response);" in javascript


def test_mobile_overflow_guards_and_compact_result_summary_are_present() -> (
    None
):
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    javascript = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    styles = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")

    assert 'id="result-summary"' in html
    assert "function renderResultSummary(data)" in javascript
    assert "overflow-x: clip" in styles
    assert "@media (max-width: 520px)" in styles
    assert ".result-summary { grid-template-columns: repeat(2" in styles


def test_result_first_dashboard_keeps_key_plan_information_together() -> None:
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    javascript = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    styles = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")

    assert 'id="result-request"' in html
    assert 'class="result-dashboard-grid"' in html
    assert 'id="result-constraints"' in html
    assert 'id="result-sources"' in html
    assert "function renderResultDashboard(data)" in javascript
    assert "[`${metrics.buffer_minutes || 0}分钟`" in javascript
    assert "[`${metrics.travel_minutes || 0}分钟`" in javascript
    assert (
        'document.body.classList.toggle("has-plan-result", active);'
        in javascript
    )
    assert "body.has-plan-result .composer-column" in styles
    assert ".result-summary { grid-template-columns: repeat(6" in styles
    assert 'data-kind="buffer"]' in styles
    assert "const items = [...(data.plan?.items || [])].sort(" in javascript


def test_fresh_homepage_opens_with_a_result_showcase() -> None:
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    javascript = (WEB_ROOT / "app.js").read_text(encoding="utf-8")

    assert '<body class="has-plan-result">' in html
    assert "正在加载默认规划，请稍候…" in html
    assert "async function loadDemos({ autoRun = false } = {})" in javascript
    assert "if (autoRun && demos.length)" in javascript
    assert (
        'await runDemo(demoButtons.querySelector("button"), demos[0]);'
        in javascript
    )
    assert "autoRun: !requestedThreadId && serverConversationThreads.length === 0" in javascript
    assert "homepageModeKey" not in javascript


def test_result_request_can_be_edited_without_leaving_dashboard() -> None:
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    javascript = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    styles = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")

    assert 'id="result-request-input"' in html
    assert "function setInlineRequestEditing(active)" in javascript
    assert (
        'resultRequest.classList.toggle("is-editing", active);' in javascript
    )
    assert "submitQuery(query, { keepResultMode: true })" in javascript
    assert "if (!keepResultMode) document.body.classList.remove" in javascript
    assert ".result-request.is-editing" in styles


def test_demo_scenarios_move_into_result_sidebar() -> None:
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    javascript = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    styles = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")

    assert 'id="sidebar-demo-buttons"' in html
    assert "<h2>场景演示</h2>" in html
    assert "const sidebarDemoButtons" in javascript
    assert "sidebarDemoButtons.innerHTML = demoMarkup;" in javascript
    assert 'document.querySelectorAll("[data-demo]")' in javascript
    assert "body.has-plan-result .sidebar-demos { display: block; }" in styles
    assert "body.has-plan-result .history-heading" in styles
    assert "const bindDemoToCurrentVisitor" in javascript
    assert "user_id: consoleUserId" in javascript
    assert "thread_id: consoleThreadId" in javascript


def test_switching_demo_keeps_dashboard_visible_without_forced_scroll() -> (
    None
):
    javascript = (WEB_ROOT / "app.js").read_text(encoding="utf-8")

    assert (
        'const keepResultMode = document.body.classList.contains("has-plan-result");'
        in javascript
    )
    assert (
        "beginConversationTurn(demo.query, { keepResultMode });" in javascript
    )
    assert (
        'const wasActive = document.body.classList.contains("has-plan-result");'
        in javascript
    )
    assert "if (wasActive) return;" in javascript


def test_result_dashboard_has_icons_sources_and_four_quick_actions() -> None:
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    javascript = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    styles = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")

    assert 'id="result-quick-actions"' in html
    assert html.count("data-result-action=") == 4
    assert "function dashboardIcon(name" in javascript
    assert 'name: "高德地图"' in javascript
    assert 'name: "高德天气"' in javascript
    assert "const resultActionQueries" in javascript
    assert "submitQuery(query, { keepResultMode: true })" in javascript
    assert ".timeline-kind-icon" in styles
    assert ".result-source-icon" in styles
    assert 'id="result-action-status"' in html
    assert (
        "function renderResultActionOutcome(action, before, after)"
        in javascript
    )
    assert ".result-action-status.is-unchanged" in styles
    assert ".result-quick-actions button:first-child" not in styles
    assert "function currentBaseRequirement()" in javascript
    assert "split(/\\n调整要求：/u, 1)" in javascript
    assert 'id="result-change-summary"' in html
    assert "const changesByTask = new Map" in javascript
    assert "timeline-change-badge" in javascript
    assert ".timeline-item.has-change .content" in styles
    assert ".result-change-chip.travel-change" in styles
    assert "function planIdleMinutes(plan)" in javascript
    assert ".result-change-chip.waiting-change" in styles
    assert "const hasPreviousPlan = Boolean(data.previous_plan);" in javascript


def test_second_course_reminder_control_is_wired_to_settings() -> None:
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    javascript = (WEB_ROOT / "app.js").read_text(encoding="utf-8")

    assert 'id="reminder-activity"' in html
    assert "settings.activity_lead_min ?? 30" in javascript
    assert "activity_lead_min: Number(reminderActivity.value)" in javascript
