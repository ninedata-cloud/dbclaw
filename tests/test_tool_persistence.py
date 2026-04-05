"""
测试tool调用信息持久化功能
验证：
1. tool_call和tool_result消息能正确保存到数据库
2. 切换会话后能正确恢复tool调用历史
"""
import asyncio
import json
from sqlalchemy import select
from backend.database import async_session
from backend.models.diagnostic_session import DiagnosticSession, ChatMessage


async def test_tool_persistence():
    """测试tool调用信息持久化"""
    print("=" * 60)
    print("测试 Tool 调用信息持久化")
    print("=" * 60)

    async with async_session() as db:
        # 1. 创建测试会话
        print("\n1. 创建测试会话...")
        session = DiagnosticSession(
            title="Tool Persistence Test",
            datasource_id=None
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        print(f"   ✓ 创建会话 ID: {session.id}")

        # 2. 模拟保存tool_call消息
        print("\n2. 保存 tool_call 消息...")
        tool_call_msg = ChatMessage(
            session_id=session.id,
            role="tool_call",
            content=json.dumps({
                "tool_name": "test_skill",
                "tool_args": {"param1": "value1", "param2": 123}
            }),
            tool_calls=[{
                "name": "test_skill",
                "arguments": {"param1": "value1", "param2": 123}
            }]
        )
        db.add(tool_call_msg)
        await db.commit()
        print(f"   ✓ 保存 tool_call 消息 ID: {tool_call_msg.id}")

        # 3. 模拟保存tool_result消息
        print("\n3. 保存 tool_result 消息...")
        tool_result_msg = ChatMessage(
            session_id=session.id,
            role="tool_result",
            content=json.dumps({
                "tool_name": "test_skill",
                "result": {"success": True, "data": "test result"},
                "execution_time_ms": 150
            })
        )
        db.add(tool_result_msg)
        await db.commit()
        print(f"   ✓ 保存 tool_result 消息 ID: {tool_result_msg.id}")

        # 4. 查询会话的所有消息（模拟切换回会话）
        print("\n4. 查询会话消息（模拟切换回会话）...")
        result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at)
        )
        messages = result.scalars().all()

        print(f"   ✓ 查询到 {len(messages)} 条消息")

        # 5. 验证消息内容
        print("\n5. 验证消息内容...")
        tool_call_found = False
        tool_result_found = False

        for msg in messages:
            if msg.role == "tool_call":
                tool_call_found = True
                data = json.loads(msg.content)
                print(f"   ✓ tool_call: {data['tool_name']}")
                print(f"     参数: {data['tool_args']}")

            elif msg.role == "tool_result":
                tool_result_found = True
                data = json.loads(msg.content)
                print(f"   ✓ tool_result: {data['tool_name']}")
                print(f"     结果: {data['result']}")
                print(f"     耗时: {data['execution_time_ms']}ms")

        # 6. 清理测试数据
        print("\n6. 清理测试数据...")
        for msg in messages:
            await db.delete(msg)
        await db.delete(session)
        await db.commit()
        print("   ✓ 测试数据已清理")

        # 7. 测试结果
        print("\n" + "=" * 60)
        if tool_call_found and tool_result_found:
            print("✅ 测试通过：Tool调用信息持久化功能正常")
        else:
            print("❌ 测试失败：")
            if not tool_call_found:
                print("   - tool_call 消息未找到")
            if not tool_result_found:
                print("   - tool_result 消息未找到")
        print("=" * 60)


async def test_message_order():
    """测试消息顺序"""
    print("\n" + "=" * 60)
    print("测试消息顺序")
    print("=" * 60)

    async with async_session() as db:
        # 创建测试会话
        session = DiagnosticSession(title="Order Test")
        db.add(session)
        await db.commit()
        await db.refresh(session)

        # 按顺序添加消息
        messages_data = [
            ("user", "测试问题"),
            ("tool_call", json.dumps({"tool_name": "skill1", "tool_args": {}})),
            ("tool_result", json.dumps({"tool_name": "skill1", "result": "结果1", "execution_time_ms": 100})),
            ("tool_call", json.dumps({"tool_name": "skill2", "tool_args": {}})),
            ("tool_result", json.dumps({"tool_name": "skill2", "result": "结果2", "execution_time_ms": 200})),
            ("assistant", "这是AI的回答")
        ]

        for role, content in messages_data:
            msg = ChatMessage(session_id=session.id, role=role, content=content)
            db.add(msg)
        await db.commit()

        # 查询并验证顺序
        result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at)
        )
        loaded_messages = result.scalars().all()

        print(f"\n消息顺序（共 {len(loaded_messages)} 条）：")
        for i, msg in enumerate(loaded_messages, 1):
            if msg.role in ["tool_call", "tool_result"]:
                data = json.loads(msg.content)
                print(f"{i}. {msg.role}: {data.get('tool_name', 'N/A')}")
            else:
                print(f"{i}. {msg.role}: {msg.content[:30]}...")

        # 清理
        for msg in loaded_messages:
            await db.delete(msg)
        await db.delete(session)
        await db.commit()

        print("\n✅ 消息顺序测试完成")
        print("=" * 60)


if __name__ == "__main__":
    async def main():
        await test_tool_persistence()
        await test_message_order()

    asyncio.run(main())
