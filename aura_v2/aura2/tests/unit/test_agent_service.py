from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from services import agent_service
from services.agent_service import _prepare_turn, _unresolved_tool_calls


def test_unresolved_tool_calls_ignores_calls_with_tool_results():
    messages = [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "calculator", "args": {}, "id": "call_done"},
                {"name": "weather", "args": {}, "id": "call_missing"},
            ],
        ),
        ToolMessage(content="2", tool_call_id="call_done"),
    ]

    assert _unresolved_tool_calls(messages) == [("call_missing", "weather")]


@pytest.mark.asyncio
async def test_prepare_turn_completes_orphaned_calls_with_unknown_outcome():
    state = SimpleNamespace(
        tasks=[],
        values={
            "messages": [
                HumanMessage(content="Send the email"),
                AIMessage(
                    content="",
                    tool_calls=[{"name": "gmail_send", "args": {}, "id": "call_orphan"}],
                ),
            ]
        },
    )

    class FakeAgent:
        def __init__(self):
            self.updated = None

        async def aget_state(self, config):
            return state

        async def aupdate_state(self, config, values):
            self.updated = values

    agent = FakeAgent()

    assert await _prepare_turn(agent, {}) is None
    [tool_result] = agent.updated["messages"]
    assert isinstance(tool_result, ToolMessage)
    assert tool_result.tool_call_id == "call_orphan"
    assert tool_result.status == "error"
    assert "outcome is unknown" in tool_result.content
    assert "Do not retry it automatically" in tool_result.content


@pytest.mark.asyncio
async def test_prepare_turn_preserves_pending_approval_without_repair():
    state = SimpleNamespace(
        tasks=[
            SimpleNamespace(
                interrupts=[
                    SimpleNamespace(
                        value={
                            "action_requests": [
                                {"name": "gmail_send", "arguments": {"to": "user@example.com"}}
                            ],
                            "review_configs": [
                                {"allowed_decisions": ["approve", "reject"]}
                            ],
                        }
                    )
                ]
            )
        ],
        values={"messages": []},
    )

    class FakeAgent:
        async def aget_state(self, config):
            return state

        async def aupdate_state(self, config, values):
            pytest.fail("pending approval history must not be modified")

    assert await _prepare_turn(FakeAgent(), {}) == {
        "type": "approval_required",
        "tool_name": "gmail_send",
        "args": {"to": "user@example.com"},
        "allowed_decisions": ["approve", "reject"],
    }


@pytest.mark.asyncio
async def test_stream_turn_does_not_run_new_message_during_pending_approval(monkeypatch):
    state = SimpleNamespace(
        tasks=[
            SimpleNamespace(
                interrupts=[
                    SimpleNamespace(
                        value={
                            "action_requests": [{"name": "gmail_send", "arguments": {}}],
                            "review_configs": [{}],
                        }
                    )
                ]
            )
        ],
        values={"messages": []},
    )

    class FakeAgent:
        async def aget_state(self, config):
            return state

        async def aupdate_state(self, config, values):
            pytest.fail("pending approval history must not be modified")

        async def astream(self, *args, **kwargs):
            pytest.fail("model must not run before the pending approval is resolved")

    monkeypatch.setattr(agent_service, "get_agent", FakeAgent)
    events = [
        event
        async for event in agent_service.stream_turn(
            context=SimpleNamespace(thread_id="thread"),
            user_message="A new message",
        )
    ]

    assert [event["type"] for event in events] == ["approval_required", "error"]
    assert "This message was not processed" in events[1]["message"]
