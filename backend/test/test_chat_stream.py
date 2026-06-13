"""Step 6: POST /chat/stream 流式 Agent 对话测试脚本。"""

import json
import sys
import time

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://localhost:8000"
CONV_API = "/api/v1/conversations"
CHAT_STREAM_API = "/api/v1/chat/stream"
USER_ID = f"chat_test_user_{int(time.time())}"
FAKE_CONV_ID = "00000000-0000-0000-0000-000000000000"
STREAM_TIMEOUT = 120


def print_step(step: str) -> None:
    print(f"\n--- {step} ---")


def create_conversation(session: requests.Session, title: str) -> str | None:
    resp = session.post(
        f"{BASE_URL}{CONV_API}",
        json={"user_id": USER_ID, "title": title},
    )
    print_step(f"创建会话: {title}")
    print(f"Status: {resp.status_code}")
    if resp.status_code != 201:
        print(f"Response: {resp.text!r}")
        return None
    data = resp.json()
    conv_id = data.get("conversation_id")
    print(f"conversation_id: {conv_id}")
    print("✅ OK")
    return conv_id


def parse_sse_stream(response: requests.Response) -> list[dict]:
    """解析 SSE 响应，返回 data 字段的 JSON 对象列表。"""
    events: list[dict] = []
    current_event: str | None = None

    for raw_line in response.iter_lines(decode_unicode=True):
        if not raw_line:
            continue
        if raw_line.startswith("event:"):
            current_event = raw_line[len("event:") :].strip()
            continue
        if raw_line.startswith("data:"):
            payload = raw_line[len("data:") :].strip()
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                data = {"raw": payload}
            if current_event and "event" not in data:
                data["event"] = current_event
            events.append(data)
            current_event = None

    return events


def consume_chat_stream(
    session: requests.Session,
    conversation_id: str,
    message: str,
    step: str,
) -> tuple[bool, list[dict], str]:
    print_step(step)
    print(f"Message: {message}")

    resp = session.post(
        f"{BASE_URL}{CHAT_STREAM_API}",
        json={
            "conversation_id": conversation_id,
            "user_id": USER_ID,
            "message": message,
        },
        stream=True,
        timeout=STREAM_TIMEOUT,
    )
    print(f"Status: {resp.status_code}")

    if resp.status_code != 200:
        print(f"Response: {resp.text!r}")
        print("❌ 流式请求失败")
        return False, [], ""

    events = parse_sse_stream(resp)
    event_types = [e.get("event") for e in events]
    print(f"收到 {len(events)} 个 SSE 事件: {event_types}")

    for evt in events:
        evt_type = evt.get("event")
        if evt_type == "planner_decision":
            print(f"  路由: {evt.get('tool')} — {evt.get('reason', '')[:80]}")
        elif evt_type == "sql_result":
            print(f"  SQL 结果: {json.dumps(evt.get('data'), ensure_ascii=False)[:200]}")
        elif evt_type == "reviews":
            reviews = evt.get("data", [])
            print(f"  评论条数: {len(reviews) if isinstance(reviews, list) else 0}")
        elif evt_type == "text_chunk":
            pass

    insight_text = "".join(
        e.get("text", "") for e in events if e.get("event") == "text_chunk"
    )
    if insight_text:
        preview = insight_text[:300] + ("..." if len(insight_text) > 300 else "")
        print(f"Insight 预览: {preview}")

    has_failure = "处理失败" in insight_text
    has_text_chunk = "text_chunk" in event_types

    if has_failure:
        print(f"❌ Insight 含错误: {insight_text[:200]}")
        return False, events, insight_text

    if not has_text_chunk:
        print("❌ 未收到 text_chunk 事件")
        return False, events, insight_text

    print("✅ OK")
    return True, events, insight_text


def verify_messages(
    session: requests.Session,
    conversation_id: str,
    expected_user_message: str,
    step: str,
) -> bool:
    print_step(step)
    resp = session.get(f"{BASE_URL}{CONV_API}/{conversation_id}/messages")
    print(f"Status: {resp.status_code}")

    if resp.status_code != 200:
        print(f"Response: {resp.text!r}")
        print("❌ 获取消息失败")
        return False

    messages = resp.json()
    print(f"消息数量: {len(messages)}")

    user_msgs = [m for m in messages if m["role"] == "user"]
    assistant_msgs = [m for m in messages if m["role"] == "assistant"]

    ok = True
    if not any(m["content"] == expected_user_message for m in user_msgs):
        print(f"❌ 未找到 user 消息: {expected_user_message!r}")
        ok = False

    if not assistant_msgs:
        print("❌ 未找到 assistant 回复")
        ok = False
    elif assistant_msgs[-1]["content"].startswith("处理失败"):
        print(f"❌ assistant 回复为错误: {assistant_msgs[-1]['content'][:200]}")
        ok = False
    else:
        preview = assistant_msgs[-1]["content"][:200]
        print(f"assistant 回复预览: {preview}...")

    if ok:
        print("✅ OK")
    return ok


def test_chat_stream_api() -> bool:
    session = requests.Session()
    all_passed = True

    # 0. 健康检查
    print_step("健康检查")
    resp = session.get(f"{BASE_URL}/health")
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        print(f"Response: {json.dumps(resp.json(), ensure_ascii=False)}")
        print("✅ OK")
    else:
        print("❌ 服务未启动或 /health 异常")
        all_passed = False
        return all_passed

    # 1. SQL 路由测试
    conv_sql = create_conversation(session, "Step6-SQL测试")
    if not conv_sql:
        return False

    ok, events, _ = consume_chat_stream(
        session,
        conv_sql,
        "各区域销售额对比",
        "流式对话 — SQL 查询（各区域销售额对比）",
    )
    all_passed = all_passed and ok

    if ok:
        event_types = {e.get("event") for e in events}
        if "planner_decision" not in event_types:
            print("⚠️ 未收到 planner_decision 事件")
        if "sql_result" not in event_types:
            print("⚠️ 未收到 sql_result 事件（可能路由到了其他工具）")

    all_passed = all_passed and verify_messages(
        session,
        conv_sql,
        "各区域销售额对比",
        "验证 SQL 测试消息持久化",
    )

    # 2. Vector 路由测试
    conv_vector = create_conversation(session, "Step6-Vector测试")
    if not conv_vector:
        return False

    ok, events, _ = consume_chat_stream(
        session,
        conv_vector,
        "用户对数码配件的评价",
        "流式对话 — Vector 查询（用户对数码配件的评价）",
    )
    all_passed = all_passed and ok

    if ok:
        event_types = {e.get("event") for e in events}
        if "reviews" not in event_types:
            print("⚠️ 未收到 reviews 事件（可能路由到了其他工具）")

    all_passed = all_passed and verify_messages(
        session,
        conv_vector,
        "用户对数码配件的评价",
        "验证 Vector 测试消息持久化",
    )

    # 3. SQL + Vector 组合测试
    conv_combo = create_conversation(session, "Step6-组合测试")
    if not conv_combo:
        return False

    ok, _, _ = consume_chat_stream(
        session,
        conv_combo,
        "9月份哪个区域销售额最低？为什么？",
        "流式对话 — SQL+Vector 组合查询",
    )
    all_passed = all_passed and ok

    all_passed = all_passed and verify_messages(
        session,
        conv_combo,
        "9月份哪个区域销售额最低？为什么？",
        "验证组合测试消息持久化",
    )

    # 4. 无效 conversation_id 应返回 404
    print_step("无效 conversation_id（预期 404）")
    resp = session.post(
        f"{BASE_URL}{CHAT_STREAM_API}",
        json={
            "conversation_id": FAKE_CONV_ID,
            "user_id": USER_ID,
            "message": "测试",
        },
        timeout=30,
    )
    print(f"Status: {resp.status_code}")
    if resp.status_code == 404:
        print("✅ OK")
    else:
        print(f"❌ 预期 404，实际 {resp.status_code}")
        all_passed = False

    if all_passed:
        print("\n🎉 Step 6 所有测试通过！")
    else:
        print("\n❌ Step 6 部分测试未通过，请检查上方输出")

    return all_passed


if __name__ == "__main__":
    sys.exit(0 if test_chat_stream_api() else 1)
