import json
import sys
import time

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://localhost:8000"
API_PREFIX = "/api/v1/conversations"
USER_ID = f"test_user_{int(time.time())}"
FAKE_CONV_ID = "00000000-0000-0000-0000-000000000000"


def print_result(
    step: str,
    response: requests.Response,
    expected_status: int | list[int] = 200,
) -> bool:
    print(f"\n--- {step} ---")
    print(f"Status: {response.status_code}")
    try:
        data = response.json()
        print(f"Response: {json.dumps(data, indent=2, ensure_ascii=False)}")
    except Exception:
        print(f"Response text: {response.text!r}")

    allowed = (
        [expected_status]
        if isinstance(expected_status, int)
        else expected_status
    )
    if response.status_code not in allowed:
        print(f"❌ Expected {allowed}, got {response.status_code}")
        return False
    print("✅ OK")
    return True


def assert_field(data: dict, field: str, step: str) -> bool:
    if field not in data:
        print(f"❌ [{step}] 响应缺少字段: {field}")
        return False
    return True


def test_conversation_api() -> bool:
    session = requests.Session()
    all_passed = True

    def check(step: str, response: requests.Response, expected_status: int | list[int] = 200) -> bool:
        nonlocal all_passed
        ok = print_result(step, response, expected_status)
        all_passed = all_passed and ok
        return ok

    # 0. 创建会话（默认标题）
    resp = session.post(
        f"{BASE_URL}{API_PREFIX}",
        json={"user_id": USER_ID},
    )
    if not check("创建会话（默认标题）", resp, 201):
        return all_passed
    default_conv = resp.json()
    if not all(assert_field(default_conv, f, "创建会话（默认标题）") for f in ("conversation_id", "title", "created_at", "updated_at")):
        all_passed = False
        return all_passed
    if default_conv["title"] != "新会话":
        print(f"❌ 默认标题应为「新会话」，实际为: {default_conv['title']}")
        all_passed = False

    # 1. 创建会话（自定义标题）
    resp = session.post(
        f"{BASE_URL}{API_PREFIX}",
        json={"user_id": USER_ID, "title": "测试会话"},
    )
    if not check("创建会话", resp, 201):
        return all_passed
    created = resp.json()
    conv_id = created.get("conversation_id")
    if not conv_id:
        print("❌ 未返回 conversation_id")
        all_passed = False
        return all_passed
    if created.get("user_id") != USER_ID:
        print(f"❌ user_id 不匹配: {created.get('user_id')}")
        all_passed = False

    # 2. 获取用户会话列表
    resp = session.get(f"{BASE_URL}{API_PREFIX}/user/{USER_ID}")
    if not check("获取会话列表", resp, 200):
        return all_passed
    convs = resp.json()
    if not any(c["conversation_id"] == conv_id for c in convs):
        print("❌ 列表中未找到刚创建的会话")
        all_passed = False
    if convs and convs[0]["conversation_id"] != conv_id:
        print("⚠️ 列表未按 updated_at 倒序（最新修改的会话不在最前）")

    # 3. 修改会话标题
    resp = session.put(
        f"{BASE_URL}{API_PREFIX}/{conv_id}",
        json={"title": "新标题 - 已修改"},
    )
    if not check("修改会话标题", resp, 200):
        return all_passed
    if resp.json().get("title") != "新标题 - 已修改":
        print("❌ PUT 响应中的标题未更新")
        all_passed = False

    resp = session.get(f"{BASE_URL}{API_PREFIX}/user/{USER_ID}")
    if check("修改后获取会话列表", resp, 200):
        updated_title = next(
            (c["title"] for c in resp.json() if c["conversation_id"] == conv_id),
            None,
        )
        if updated_title != "新标题 - 已修改":
            print("❌ 标题修改未生效")
            all_passed = False
        if resp.json()[0]["conversation_id"] != conv_id:
            print("⚠️ 修改标题后列表未将目标会话排到最前（updated_at 倒序可能异常）")

    # 4. 获取会话消息（目前为空）
    resp = session.get(f"{BASE_URL}{API_PREFIX}/{conv_id}/messages")
    if not check("获取消息列表（空）", resp, 200):
        return all_passed
    if resp.json() != []:
        print("⚠️ 消息列表应为空，但返回了非空数据")
        all_passed = False

    # 5. 不存在的会话应返回 404
    resp = session.get(f"{BASE_URL}{API_PREFIX}/{FAKE_CONV_ID}/messages")
    check("获取不存在会话的消息（预期 404）", resp, 404)

    resp = session.put(
        f"{BASE_URL}{API_PREFIX}/{FAKE_CONV_ID}",
        json={"title": "不应成功"},
    )
    check("修改不存在会话（预期 404）", resp, 404)

    # 6. 软删除会话
    resp = session.delete(f"{BASE_URL}{API_PREFIX}/{conv_id}")
    check("软删除会话", resp, 204)

    # 7. 验证删除后不再出现在会话列表中
    resp = session.get(f"{BASE_URL}{API_PREFIX}/user/{USER_ID}")
    if check("删除后获取会话列表", resp, 200):
        if any(c["conversation_id"] == conv_id for c in resp.json()):
            print("❌ 会话被软删除后仍出现在列表中")
            all_passed = False
        else:
            print("✅ 软删除成功，会话已隐藏")

    # 8. 已删除会话的操作应返回 410 Gone
    resp = session.get(f"{BASE_URL}{API_PREFIX}/{conv_id}/messages")
    check("获取已删除会话的消息（预期 410）", resp, 410)

    resp = session.put(
        f"{BASE_URL}{API_PREFIX}/{conv_id}",
        json={"title": "不应成功"},
    )
    check("修改已删除会话（预期 410）", resp, 410)

    resp = session.delete(f"{BASE_URL}{API_PREFIX}/{conv_id}")
    check("重复删除已删除会话（预期 410）", resp, 410)

    if all_passed:
        print("\n🎉 所有测试通过！")
    else:
        print("\n❌ 部分测试未通过，请检查上方输出")

    return all_passed


if __name__ == "__main__":
    sys.exit(0 if test_conversation_api() else 1)
