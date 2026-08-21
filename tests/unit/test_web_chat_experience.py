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
    assert 'event.key !== "Enter" || event.shiftKey || event.isComposing' in javascript


def test_mobile_overflow_guards_and_compact_result_summary_are_present() -> None:
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
    assert 'id="result-reminder-card"' in html
    assert 'id="result-reminders"' in html
    assert "function renderResultDashboard(data)" in javascript
    assert "metrics.buffer_minutes > 0" in javascript
    assert "metrics.travel_minutes > 0" in javascript
    assert 'const reminderMarker = "再替你留意";' in javascript
    assert '!["meal", "buffer"].includes(item.item_type)' in javascript
    assert 'document.body.classList.toggle("has-plan-result", active);' in javascript
    assert "body.has-plan-result .composer-column" in styles
    assert ".result-summary { grid-template-columns: repeat(auto-fit" in styles
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
    assert 'id="tools-toggle"' in html and "定位" in html
    assert 'data-schedule-mode="day"' not in html
    assert 'data-schedule-mode="week"' not in html
    assert 'id="save-state" class="status subtle" hidden' in html
    assert 'id="mode"' not in html
    assert "智能联网" not in html and "强制实时" not in html
    assert 'const planningMode = "live";' in javascript
    assert "mode: planningMode" in javascript
    assert 'id="debug-panel"' not in html
    assert "初期调试信息" not in html
    assert "当前为公开测试版" not in html
    assert "课程、调课、停课与补课均以杭助同步结果为准" not in html
    assert 'id="demo-buttons"' not in html
    assert 'id="sidebar-demo-buttons"' not in html
    assert "async function loadDemos()" not in javascript
    assert "setPanelHidden(visualGrid, !isChat || !hasPlanResult);" in javascript
    assert "if (!keepResultMode) setResultMode(false);" in javascript
    assert "homepageModeKey" not in javascript


def test_sidebar_prioritizes_workspace_navigation_before_history() -> None:
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    styles = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")

    assert "<h2>我的空间</h2>" in html
    assert html.index('class="workspace-nav"') < html.index(
        'class="history-section-label"'
    )
    assert html.index("<strong>对话历史</strong>") < html.index(
        'id="history-list"'
    )
    assert ".history-sidebar .history-heading h2" in styles
    assert "font: 820 22px/1.2" in styles
    assert "margin: 24px 6px 10px" in styles


def test_sidebar_merges_hduhelp_and_timetable_after_preferences() -> None:
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    javascript = (WEB_ROOT / "app.js").read_text(encoding="utf-8")

    nav_start = html.index('class="workspace-nav"')
    nav_end = html.index("</nav>", nav_start)
    nav = html[nav_start:nav_end]
    assert nav.index("对话") < nav.index("日程") < nav.index("偏好") < nav.index("校园数据")
    assert 'data-view="hduhelp"' not in nav
    assert 'data-view="timetable"' not in nav
    assert 'data-view="campus-data"' in nav
    assert "杭助 · 课表" in nav
    assert 'id="campus-data-workspace"' in html
    assert '"chat", "schedule", "campus-data", "preferences"' in javascript
    assert 'class="academic-calendar"' not in html
    assert "function renderAcademicCalendar" not in javascript
    assert "async function loadAcademicCalendar" not in javascript
    assert "杭助中的实际安排优先" not in html
    assert "记录取消后，下次同步会从日程中移除" not in html


def test_self_hosted_accounts_replace_external_login_choices() -> None:
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    javascript = (WEB_ROOT / "app.js").read_text(encoding="utf-8")

    assert 'data-auth-view="login"' in html
    assert 'data-auth-view="register"' in html
    assert 'data-auth-view="test"' in html
    assert "/api/v1/auth/account/login" in javascript
    assert "/api/v1/auth/register" in javascript
    assert "/api/v1/auth/test-session" in javascript
    assert "/api/v1/auth/login" in javascript
    assert "正在进入共享测试空间" in javascript
    assert "setBootstrapView" in javascript
    assert "微信扫码" not in html
    assert "统一认证" not in html
    assert "hduhelp-wechat" not in html
    assert "/api/v1/auth/session" not in javascript


def test_result_request_can_be_edited_without_leaving_dashboard() -> None:
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    javascript = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    styles = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")

    assert 'id="result-request-input"' in html
    assert "function setInlineRequestEditing(active)" in javascript
    assert 'resultRequest.classList.toggle("is-editing", active);' in javascript
    assert "submitQuery(query, { keepResultMode: true })" in javascript
    assert "if (!keepResultMode) setResultMode(false);" in javascript
    assert ".result-request.is-editing" in styles


def test_demo_scenarios_are_removed_from_the_product_ui() -> None:
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    javascript = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    styles = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")

    assert "场景演示" not in html
    assert "复位演示" not in html
    assert "data-demo" not in javascript
    assert "weekly-demo" not in html
    assert "loadWeeklyDemos" not in javascript
    assert ".demo-strip" not in styles
    assert ".sidebar-demos" not in styles


def test_result_dashboard_can_return_to_the_main_conversation() -> None:
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    javascript = (WEB_ROOT / "app.js").read_text(encoding="utf-8")

    assert 'id="result-back-chat"' in html
    assert 'id="result-reopen"' in html
    assert "function returnToConversation()" in javascript
    assert 'resultBackChat?.addEventListener("click", returnToConversation);' in javascript
    assert 'button.dataset.view === "chat"' in javascript
    assert "setResultMode(false);" in javascript
    assert 'queryInput?.focus({ preventScroll: true });' in javascript
    assert 'resultReopen?.addEventListener("click"' in javascript
    assert "resultReopen.hidden = !lastResultData?.plan;" in javascript
    assert 'if (document.body.classList.contains("has-plan-result")) {' in javascript


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
    assert "function renderResultActionOutcome(action, before, after)" in javascript
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
    assert "const removalOnly = changes.length > 0" in javascript
    assert "if (waitingDelta && !removalOnly)" in javascript
    assert "async function resolveRequestBaseline(query)" in javascript
    assert "async function publishedAgendaPlan(query)" in javascript
    assert 'item.source === "plan" && item.plan_id' in javascript
    assert "old_plan_id: baselinePlan?.id || null" in javascript
    assert "publishedPlanId" in javascript
    assert "function cacheResultSnapshot(data)" in javascript
    assert "function restoreResultSnapshot(" in javascript
    assert 'updatesPublishedAgenda' in javascript
    assert '"更新日程"' in javascript
    assert '"调整方案已保存，确认后更新日程"' in javascript
    assert "previousPublishedPlanId" in javascript
    assert "固定课程和锁定安排的时间绝对不变" in javascript
    assert "function formatDuration(minutes)" in javascript
    assert "item.location_raw || (item.location_id" in javascript
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
    assert ".conversation-message.user-message" in javascript
    assert 'target.scrollIntoView({ behavior: "smooth"' in javascript
    assert "new MutationObserver(syncConversationOutline)" in javascript
    assert ".conversation-outline.is-open" in styles
    assert ".conversation-outline button::before" in styles
    assert "position: fixed" in styles
    assert "document.body.append(conversationOutline)" in javascript
    assert 'id="conversation-outline-count"' not in javascript
    assert "<span>${index + 1}</span>" not in javascript
    assert "conversationMessageLabel(message)" in javascript
    assert "if (toolsToggle) toolsToggle.hidden = !hasTurns;" in javascript
    assert "const hasTurns = messages.length > 0;" in javascript
    assert "data-thread-rename" in javascript
    assert "data-thread-delete" in javascript
    assert "data-thread-menu-toggle" in javascript
    assert "function closeHistoryMenus" in javascript
    assert 'event.key === "Escape"' in javascript
    assert ".history-menu-trigger" in styles
    assert ".history-item-menu[hidden]" in styles
    assert "async function renameConversationThread" in javascript
    assert "async function deleteConversationThread" in javascript
    assert 'message.querySelector(".message-content, .message-bubble")' in javascript
    assert "right: 34px" in styles


def test_conversation_uses_one_brand_logo_and_omits_user_role_badges() -> None:
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    javascript = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    styles = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")

    assert '/assets/yicheng-logo.png?v=20260821-1' in html
    assert 'class="assistant-avatar" src="/assets/yicheng-logo.png?v=20260821-1"' in html
    assert 'class="message-avatar assistant-message-avatar" src="/assets/yicheng-logo.png?v=20260821-1"' in javascript
    assert '${isUser ? "你" : "易"}' not in javascript
    assert '${isUser ? "你" : "易程智策"}' not in javascript
    assert ".assistant-message-avatar" in styles


def test_schedule_marks_verified_holidays_and_pending_makeup_days() -> None:
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    javascript = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    styles = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")

    assert 'data-schedule-view="day" role="tab" aria-selected="true">日</button>' in html
    assert 'data-schedule-view="week" role="tab" aria-selected="false">周</button>' in html
    assert 'data-schedule-view="month" role="tab" aria-selected="false">月</button>' in html
    assert "calendar-context`" in javascript
    assert 'class="schedule-calendar-badge-mark"' in javascript
    assert 'holiday ? "休" : "补"' in javascript
    assert "实际补课课程以杭助同步结果为准" in javascript
    assert "2025年法定节假日数据尚未核验" not in javascript
    assert 'id="timetable-term-view"' in (WEB_ROOT / "index.html").read_text(
        encoding="utf-8"
    )


def test_day_schedule_allows_manual_edits_but_locks_authoritative_items() -> None:
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    javascript = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    styles = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")

    assert 'id="schedule-add"' in html
    assert 'id="schedule-editor"' in html
    assert 'id="schedule-editor-name" required' in html
    assert 'id="schedule-editor-start" type="time" required' in html
    assert 'id="schedule-editor-end" type="time" required' in html
    assert "固定课表和杭助预约不会被改动" in javascript
    assert 'item.source === "course" || item.source === "external"' in javascript
    assert 'data-schedule-edit="${escapeHtml(item.id)}"' in javascript
    assert 'method: itemId ? "PUT" : "POST"' in javascript
    assert '{ method: "DELETE" }' in javascript
    assert 'scheduleAdd?.addEventListener("click"' in javascript
    assert ".schedule-editor::backdrop" in styles
    assert 'const lockLabel = "锁定";' in javascript
    assert "课表锁定" not in javascript
    assert "杭助锁定" not in javascript
    assert 'class="schedule-event-more"' in javascript
    assert '<svg viewBox="0 0 24 24" aria-hidden="true">' in javascript
    assert 'title="调整时间或删除">•••' not in javascript
    assert ".schedule-event-lock" in styles
    assert 'app.js?v=20260821-7' in (WEB_ROOT / "index.html").read_text(
        encoding="utf-8"
    )
    assert "styles.css?v=20260821-7" in (WEB_ROOT / "index.html").read_text(
        encoding="utf-8"
    )
    assert 'term.current ? "（当前）"' not in javascript
    assert 'timetableTermView?.addEventListener("change"' in javascript
    assert "function renderTimetableTerms" in javascript
    assert "item.start_at))}—${escapeHtml(timePart(item.end_at))" in javascript
    assert ".schedule-month-cell.is-holiday" in styles
    assert ".schedule-month-cell.is-workday" in styles
    assert ".schedule-calendar-badge small" in styles
    assert "button.primary:disabled" in styles
