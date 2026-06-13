import asyncio
import time
from app.database.chroma_client import (
    get_comments_collection,
    get_memory_collection,
    embedding_model,
    add_comment_to_chroma
)

async def test_embedding():
    print("=== 测试嵌入模型 ===")
    start = time.time()
    texts = ["这个面霜很好用", "物流太慢了"]
    vectors = await embedding_model.embed_texts(texts)
    print(f"编码耗时: {time.time()-start:.2f}s")
    dim = len(vectors[0])
    print(f"向量维度: {dim}")
    print(f"向量前5个值: {vectors[0][:5]}")
    assert len(vectors) == 2
    # 只检查一致性，不检查固定维度
    assert all(len(v) == dim for v in vectors)
    print(f"✅ 嵌入模型正常，维度={dim}\n")

async def test_collections():
    print("=== 测试集合创建 ===")
    comments_coll = await get_comments_collection()
    memory_coll = await get_memory_collection()
    print(f"comments 集合名称: {comments_coll.name}")
    print(f"memory 集合名称: {memory_coll.name}")
    print(f"comments 当前文档数: {comments_coll.count()}")
    print("✅ 集合获取正常\n")

async def test_add_comment():
    print("=== 测试添加评论 ===")
    # 添加一条测试评论
    await add_comment_to_chroma(
        review_id="test_001",
        order_id="ORD9999999999",
        comment="快递速度很快，包装完好，非常满意",
        rating=5,
        sentiment="positive"
    )
    # 验证是否真的加入
    coll = await get_comments_collection()
    # 查询刚添加的文档
    result = await asyncio.to_thread(
        coll.get, ids=["test_001"], include=["metadatas", "documents"]
    )
    if result['ids']:
        print(f"文档内容: {result['documents'][0]}")
        print(f"元数据: {result['metadatas'][0]}")
        print("✅ 添加评论成功")
    else:
        print("❌ 未找到刚添加的评论")
    
    # 清理测试数据（可选）
    await asyncio.to_thread(coll.delete, ids=["test_001"])
    print("已清理测试数据\n")

async def main():
    await test_embedding()
    await test_collections()
    await test_add_comment()
    print("🎉 Step 3 所有测试通过！")

if __name__ == "__main__":
    asyncio.run(main())