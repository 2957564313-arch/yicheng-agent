from __future__ import annotations

from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2] / "app" / "web"


def test_chat_stream_is_part_of_the_latest_workspace() -> None:
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    javascript = (WEB_ROOT / "app.js").read_text(encoding="utf-8")

    assert html.index('id="conversation-stream"') < html.index(
        'class="panel assistant-panel"'
    )
    assert "function beginConversationTurn(query)" in javascript
    assert "function completeConversationTurn(answerText)" in javascript
    assert "setPanelHidden(conversationStream, !isChat);" in javascript


def test_history_restore_and_keyboard_send_are_available() -> None:
    javascript = (WEB_ROOT / "app.js").read_text(encoding="utf-8")

    assert 'data-history-index="${index}"' in javascript
    assert "restoreConversationSnapshot(item.query, item.answer);" in javascript
    assert "本机历史摘要" in javascript
    assert 'queryInput.addEventListener("keydown"' in javascript
    assert 'event.key !== "Enter" || event.shiftKey || event.isComposing' in javascript
