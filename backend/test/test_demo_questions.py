"""全量 Demo 问题集成测试 — 覆盖 SQL / Vector / 混合归因 / 边界场景。"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from typing import Callable

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:8000"
CONV_API = "/api/v1/conversations"
CHAT_STREAM_API = "/api/v1/chat/stream"
USER_ID = f"demo_test_{int(time.time())}"
STREAM_TIMEOUT = 180


@dataclass
class TestCase:
    category: str
    message: str
    expect_tool: str | None = None  # planner 路由期望
    expect_events: list[str] = field(default_factory=list)
    expect_chart: str | None = None  # bar | line | pie | None
    expect_year_clarify: bool = False
    expect_no_data: bool = False
    validator: Callable[[list[dict], str], str | None] | None = None


def parse_sse_stream(response: requests.Response) -> list[dict]:
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


def run_chat(session: requests.Session, conv_id: str, message: str) -> tuple[list[dict], str]:
    resp = session.post(
        f"{BASE_URL}{CHAT_STREAM_API}",
        json={"conversation_id": conv_id, "user_id": USER_ID, "message": message},
        stream=True,
        timeout=STREAM_TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    events = parse_sse_stream(resp)
    insight = "".join(e.get("text", "") for e in events if e.get("event") == "text_chunk")
    return events, insight


def get_planner_tool(events: list[dict]) -> str | None:
    for e in events:
        if e.get("event") == "planner_decision":
            return e.get("tool")
    return None


def get_chart_type(events: list[dict]) -> str | None:
    for e in events:
        if e.get("event") == "chart_spec":
            data = e.get("data") or {}
            return data.get("type")
    return None


def has_event(events: list[dict], name: str) -> bool:
    return any(e.get("event") == name for e in events)


def get_sql_result(events: list[dict]):
    for e in events:
        if e.get("event") == "sql_result":
            return e.get("data")
    return None


def get_reviews(events: list[dict]) -> list:
    for e in events:
        if e.get("event") == "reviews":
            data = e.get("data")
            return data if isinstance(data, list) else []
    return []


# ── 测试用例定义 ──────────────────────────────────────────────

TEST_CASES: list[TestCase] = [
    # 主 Demo 6 张
    TestCase("主Demo", "2025年各区域销售额对比，哪个区域最高？", expect_tool="sql_tool", expect_events=["sql_result", "chart_spec"], expect_chart="bar"),
    TestCase("主Demo", "2025年各月销售额趋势如何？哪个月是高峰？", expect_tool="sql_tool", expect_events=["sql_result", "chart_spec"], expect_chart="line"),
    TestCase("主Demo", "2025年线上和线下渠道的销售额占比分别是多少？", expect_tool="sql_tool", expect_events=["sql_result", "chart_spec"]),
    TestCase("主Demo", "2025年夏季（6-8月）食品饮料品类卖得怎么样？", expect_tool="sql_tool", expect_events=["sql_result"]),
    TestCase("主Demo", "2025年华东区销售表现如何？用户主要反馈什么？", expect_tool="sql_tool", expect_events=["sql_result", "reviews"]),
    TestCase("主Demo", "用户对物流和发货速度有哪些负面评价？", expect_tool="vector_tool", expect_events=["reviews"]),
    # 基础统计
    TestCase("基础统计", "2025年总销售额是多少？", expect_tool="sql_tool", expect_events=["sql_result"]),
    TestCase("基础统计", "2025年一共下了多少笔订单？", expect_tool="sql_tool", expect_events=["sql_result"]),
    TestCase("基础统计", "2025年线上渠道的平均客单价是多少？", expect_tool="sql_tool", expect_events=["sql_result"]),
    # 对比排名
    TestCase("对比排名", "2025年各品类销售额排名，哪个品类最高？", expect_tool="sql_tool", expect_events=["sql_result", "chart_spec"], expect_chart="bar"),
    TestCase("主Demo", "2025年8月份各区域销售额对比", expect_tool="sql_tool", expect_events=["sql_result", "chart_spec"]),
    TestCase("对比排名", "2025年各区域销售额占比", expect_tool="sql_tool", expect_events=["sql_result", "chart_spec"]),
    # 混合归因
    TestCase("混合归因", "2025年哪个区域销售额最低？可能是什么原因？用户怎么说？", expect_tool="sql_tool", expect_events=["sql_result", "reviews"]),
    TestCase("混合归因", "2025年线下渠道表现如何？用户对线下购物体验有什么评价？", expect_tool="sql_tool", expect_events=["sql_result", "reviews"]),
    TestCase("混合归因", "2025年数码配件在11-12月销售很好，用户满意吗？", expect_tool="sql_tool", expect_events=["sql_result", "reviews"]),
    # 纯舆情
    TestCase("纯舆情", "用户对产品质量有哪些差评？", expect_tool="vector_tool", expect_events=["reviews"]),
    TestCase("纯舆情", "客服态度相关的用户反馈怎么样？", expect_tool="vector_tool", expect_events=["reviews"]),
    TestCase("纯舆情", "包装破损或物流问题，用户怎么说的？", expect_tool="vector_tool", expect_events=["reviews"]),
    # 边界
    TestCase("边界", "9月份哪个区域销售额最低？", expect_year_clarify=True),
    TestCase("边界", "2025年9月份哪个区域销售额最低？", expect_tool="sql_tool", expect_events=["sql_result"]),
    TestCase("边界", "2025年华东区线上渠道的办公文具销售额", expect_tool="sql_tool", expect_events=["sql_result"]),
    TestCase("边界", "2028年9月份哪个区域销售额最低？", expect_no_data=True),
    # 业务决策
    TestCase("业务决策", "2025年线上和线下渠道差异明显吗？渠道策略上有什么建议？", expect_tool="sql_tool", expect_events=["sql_result", "reviews"]),
    TestCase("业务决策", "2025年用户差评主要集中在哪些环节？运营上优先改进什么？", expect_tool="vector_tool", expect_events=["reviews"]),
]


def validate_case(case: TestCase, events: list[dict], insight: str) -> list[str]:
    errors: list[str] = []

    if case.expect_year_clarify:
        if "请补充年份" not in insight and "未指定具体年份" not in insight and "请补充完整年份" not in insight:
            errors.append("期望年份澄清，但 Insight 未包含澄清提示")
        if has_event(events, "sql_result"):
            errors.append("年份澄清场景不应执行 SQL")
        return errors

    if case.expect_no_data:
        if "无匹配订单" not in insight:
            errors.append("期望无数据提示，但 Insight 未包含「无匹配订单」")
        if has_event(events, "chart_spec"):
            errors.append("无数据场景不应生成图表")
        sql = get_sql_result(events)
        if sql not in (None, {}, ""):
            errors.append(f"无数据场景 sql_result 应为空，实际: {sql}")
        return errors

    if "处理失败" in insight:
        errors.append(f"Insight 含错误: {insight[:150]}")
        return errors

    if not insight.strip():
        errors.append("Insight 为空")
        return errors

    if case.expect_tool:
        actual_tool = get_planner_tool(events)
        # Planner 决策可能被图路由 override（如 requires_sql_first），以实际 SSE 事件为准
        if case.expect_tool == "sql_tool" and not has_event(events, "sql_result"):
            errors.append(f"期望 SQL 查询，但未收到 sql_result（planner={actual_tool}）")
        elif case.expect_tool == "vector_tool" and not has_event(events, "reviews"):
            errors.append(f"期望评论检索，但未收到 reviews（planner={actual_tool}）")
        elif actual_tool != case.expect_tool and case.expect_tool == "vector_tool":
            if has_event(events, "sql_result"):
                pass  # 混合链路：先 SQL 后 Vector 也合理
            else:
                errors.append(f"路由期望 {case.expect_tool}，实际 {actual_tool}")

    for evt in case.expect_events:
        if not has_event(events, evt):
            errors.append(f"缺少 SSE 事件: {evt}")

    if case.expect_chart:
        chart = get_chart_type(events)
        if chart != case.expect_chart:
            errors.append(f"图表期望 {case.expect_chart}，实际 {chart}")

    if case.validator:
        msg = case.validator(events, insight)
        if msg:
            errors.append(msg)

    return errors


def main() -> int:
    session = requests.Session()

    # 健康检查
    try:
        r = session.get(f"{BASE_URL}/health", timeout=10)
        if r.status_code != 200:
            print(f"❌ 健康检查失败: {r.status_code}")
            return 1
        print(f"✅ 服务正常: {r.json()}")
    except Exception as exc:
        print(f"❌ 无法连接后端: {exc}")
        return 1

    # 创建会话
    resp = session.post(f"{BASE_URL}{CONV_API}", json={"user_id": USER_ID, "title": "Demo全量测试"})
    if resp.status_code != 201:
        print(f"❌ 创建会话失败: {resp.text}")
        return 1
    conv_id = resp.json()["conversation_id"]
    print(f"会话 ID: {conv_id}\n")

    passed = 0
    failed = 0
    failures: list[tuple[TestCase, list[str]]] = []

    for i, case in enumerate(TEST_CASES, 1):
        label = f"[{i}/{len(TEST_CASES)}] [{case.category}]"
        print(f"{label} {case.message}")
        try:
            events, insight = run_chat(session, conv_id, case.message)
            errors = validate_case(case, events, insight)
            tool = get_planner_tool(events)
            chart = get_chart_type(events)
            sql = get_sql_result(events)
            reviews = get_reviews(events)
            if errors:
                failed += 1
                failures.append((case, errors))
                print(f"  ❌ FAIL: {'; '.join(errors)}")
                print(f"     tool={tool} chart={chart} sql={'有' if sql else '无'} reviews={len(reviews)}")
                print(f"     insight: {insight[:120]}...")
            else:
                passed += 1
                print(f"  ✅ PASS tool={tool} chart={chart} reviews={len(reviews)}")
        except Exception as exc:
            failed += 1
            failures.append((case, [str(exc)]))
            print(f"  ❌ EXCEPTION: {exc}")

    print("\n" + "=" * 60)
    print(f"结果: {passed} 通过 / {failed} 失败 / {len(TEST_CASES)} 总计")
    if failures:
        print("\n失败详情:")
        for case, errors in failures:
            print(f"  - [{case.category}] {case.message}")
            for e in errors:
                print(f"      · {e}")
        return 1
    print("🎉 全部 Demo 测试通过！")
    return 0


if __name__ == "__main__":
    sys.exit(main())
