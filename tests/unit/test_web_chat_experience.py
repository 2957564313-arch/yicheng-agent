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


def test_server_history_and_keyboard_send_are_available() -> None:
    javascript = (WEB_ROOT / "app.js").read_text(encoding="utf-8")

    assert 'data-thread-id="${escapeHtml(item.id)}"' in javascript
    assert "async function openConversationThread(threadId)" in javascript
    assert "服务端对话记录" in javascript
    assert 'localStorage.removeItem("yicheng_conversation_history")' in javascript
    assert "data-history-index" not in javascript
    assert 'queryInput.addEventListener("keydown"' in javascript
    assert (
        'event.key !== "Enter" || event.shiftKey || event.isComposing'
        in javascript
    )


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
    assert "formatDuration(metrics.buffer_minutes || 0)" in javascript
    assert "formatDuration(metrics.travel_minutes || 0)" in javascript
    assert (
        'document.body.classList.toggle("has-plan-result", active);'
        in javascript
    )
    assert "body.has-plan-result .composer-column" in styles
    assert ".result-summary { grid-template-columns: repeat(6" in styles
    assert 'data-kind="buffer"]' in styles
    assert "const items = [...(data.plan?.items || [])].filter(" in javascript
    assert 'item.item_type !== "meal"' in javascript


def test_fresh_homepage_stays_clean_until_the_user_runs_a_plan() -> None:
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    javascript = (WEB_ROOT / "app.js").read_text(encoding="utf-8")

    assert '<body class="has-plan-result">' not in html
    assert '<section class="visual-grid" hidden>' in html
    assert "正在加载默认规划，请稍候…" not in html
    assert 'id="new-conversation"' not in html
    assert "最近使用" not in html
    assert "对话与分支已保存" not in html
    assert "工作区导航" not in html
    assert "需要时展开一项，重点始终留在中间对话区。" not in html
    assert 'id="tools-toggle"' in html and '定位' in html
    assert 'data-schedule-mode="day"' not in html
    assert 'data-schedule-mode="week"' not in html
    assert 'id="save-state" class="status subtle" hidden' in html
    assert "async function loadDemos()" in javascript
    assert "if (autoRun && demos.length)" not in javascript
    assert "await loadDemos().catch" in javascript
    assert 'setPanelHidden(visualGrid, !isChat || !hasPlanResult);' in javascript
    assert "if (!keepResultMode) setResultMode(false);" in javascript
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
    assert "if (!keepResultMode) setResultMode(false);" in javascript
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
    assert "固定课程和锁定安排的时间绝对不变" in javascript
    assert "function formatDuration(minutes)" in javascript
    assert 'item.location_raw || (item.location_id' in javascript
    assert '? "高峰拥挤"' in javascript
    assert "这是你明确给出的固定安排" not in javascript
    assert "高德返回" not in javascript


def test_second_course_reminder_control_is_wired_to_settings() -> None:
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    javascript = (WEB_ROOT / "app.js").read_text(encoding="utf-8")

    assert 'id="reminder-activity"' in html
    assert "settings.activity_lead_min ?? 30" in javascript
    assert "activity_lead_min: Number(reminderActivity.value)" in javascript


def test_current_conversation_has_a_right_side_quick_outline() -> None:
    javascript = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    styles = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")

    assert "本次对话" in javascript
    assert "function syncConversationOutline()" in javascript
    assert '.conversation-message.user-message' in javascript
    assert 'target.scrollIntoView({ behavior: "smooth"' in javascript
    assert "new MutationObserver(syncConversationOutline)" in javascript
    assert ".conversation-outline.is-open" in styles
    assert ".conversation-outline button::before" in styles
    assert "position: fixed" in styles
    assert "document.body.append(conversationOutline)" in javascript
    assert 'id="conversation-outline-count"' not in javascript
    assert '<span>${index + 1}</span>' not in javascript
    assert "conversationMessageLabel(message)" in javascript
    assert "if (toolsToggle) toolsToggle.hidden = !hasMultipleTurns;" in javascript
    assert "data-thread-rename" in javascript
    assert "data-thread-delete" in javascript
    assert "data-thread-menu-toggle" in javascript
    assert "function closeHistoryMenus" in javascript
    assert 'event.key === "Escape"' in javascript
    assert ".history-menu-trigger" in styles
    assert ".history-item-menu[hidden]" in styles
    assert "async function renameConversationThread" in javascript
    assert "async function deleteConversationThread" in javascript


def test_schedule_marks_verified_holidays_and_pending_makeup_days() -> None:
    javascript = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    styles = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")

    assert 'calendar-context`' in javascript
    assert 'holiday ? "休" : "补"' in javascript
    assert 'context.course_action === "makeup"' in javascript
    assert "已自动停用课表中的固定课程" in javascript
    assert ".schedule-month-cell.is-holiday" in styles
    assert ".schedule-month-cell.is-workday" in styles
    assert "button.primary:disabled" in styles
