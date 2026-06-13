/**
 * Phase 5: 前端 API 层端到端集成测试
 * 镜像 frontend/src/services/api.ts 的契约与 SSE 解析逻辑
 */
import axios from 'axios';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BASE_URL = (process.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
const API_PREFIX = '/api/v1';
const USER_ID = `phase5_user_${Date.now()}`;

const SALES_CSV = path.resolve(__dirname, '../../backend/数据测试/sales_data.csv');
const REVIEWS_CSV = path.resolve(__dirname, '../../backend/数据测试/reviews_data.csv');

const baseAxios = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 60_000,
});

let passed = 0;
let failed = 0;

function ok(step) {
  passed += 1;
  console.log(`✅ ${step}`);
}

function fail(step, detail) {
  failed += 1;
  console.log(`❌ ${step}${detail ? `: ${detail}` : ''}`);
}

function section(title) {
  console.log(`\n=== ${title} ===`);
}

function resolveNodeStatus(payload) {
  if (payload.node_status) return payload.node_status;
  switch (payload.event) {
    case 'node_start':
      if (payload.node === 'planner') return 'thinking_planner';
      if (payload.node === 'sql_tool') return 'thinking_sql';
      if (payload.node === 'vector_tool') return 'thinking_vector';
      if (payload.node === 'insight') return 'generating';
      return payload.node ? `thinking_${payload.node}` : undefined;
    case 'planner_decision':
      if (payload.tool === 'sql_tool') return 'planning_sql';
      if (payload.tool === 'vector_tool') return 'planning_vector';
      return 'planning';
    case 'sql_result':
      return 'sql_done';
    case 'reviews':
      return 'vector_done';
    default:
      return undefined;
  }
}

function resolveContent(payload) {
  if (typeof payload.content === 'string') return payload.content;
  if (typeof payload.text === 'string') return payload.text;
  return '';
}

function parseStreamDataLine(line) {
  const trimmed = line.trimEnd();
  if (!trimmed.startsWith('data:')) return null;
  const payloadStr = trimmed.slice(5).trimStart();
  if (!payloadStr || payloadStr === '[DONE]') return null;
  try {
    const payload = JSON.parse(payloadStr);
    const content = resolveContent(payload);
    const nodeStatus = resolveNodeStatus(payload);
    if (!content && !nodeStatus) return null;
    return { content, nodeStatus, raw: payload };
  } catch {
    return null;
  }
}

function nodeStatusToLabel(nodeStatus) {
  const map = {
    thinking_planner: '正在分析您的问题…',
    planning: '正在分析您的问题…',
    planning_sql: '已规划：SQL 数据查询',
    planning_vector: '已规划：评论向量检索',
    thinking_sql: '正在查询销售数据库 (SQL)…',
    thinking_vector: '正在检索用户评论 (Vector)…',
    generating: '正在生成销售洞察…',
    thinking_insight: '正在生成销售洞察…',
    sql_done: '数据库查询完成，正在整合结果…',
    vector_done: '评论检索完成，正在整合结果…',
  };
  return map[nodeStatus] ?? '处理中…';
}

async function sendMessageStream(conversationId, userId, message) {
  const response = await fetch(`${BASE_URL}${API_PREFIX}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      conversation_id: conversationId,
      user_id: userId,
      message,
    }),
  });

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const err = await response.json();
      detail = err.detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let accumulated = '';
  const nodeStatuses = new Set();
  const statusLabels = new Set();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      const parsed = parseStreamDataLine(line);
      if (!parsed) continue;
      if (parsed.nodeStatus) {
        nodeStatuses.add(parsed.nodeStatus);
        statusLabels.add(nodeStatusToLabel(parsed.nodeStatus));
      }
      if (parsed.content) accumulated += parsed.content;
    }
  }

  if (buffer.trim()) {
    const parsed = parseStreamDataLine(buffer);
    if (parsed?.content) accumulated += parsed.content;
    if (parsed?.nodeStatus) {
      nodeStatuses.add(parsed.nodeStatus);
      statusLabels.add(nodeStatusToLabel(parsed.nodeStatus));
    }
  }

  return { accumulated, nodeStatuses, statusLabels };
}

async function testHealth() {
  section('5.0 健康检查 & 前端可达性');
  try {
    const { data, status } = await axios.get(`${BASE_URL}/health`, { timeout: 5000 });
    if (status === 200 && data.status === 'ok') {
      ok(`后端 /health 正常 (model=${data.model})`);
    } else {
      fail('后端 /health', JSON.stringify(data));
    }
  } catch (e) {
    fail('后端 /health', e.message);
    return false;
  }

  try {
    const frontendUrl = process.env.FRONTEND_URL || 'http://localhost:5173';
    const res = await fetch(frontendUrl, { signal: AbortSignal.timeout(5000) });
    if (res.ok) {
      ok(`前端页面可达 ${frontendUrl}`);
    } else {
      fail('前端页面', `HTTP ${res.status}`);
    }
  } catch {
    console.log('⚠️  前端 dev server 未启动（跳过 UI 可达性检查，API 层仍继续测）');
  }
  return true;
}

async function testConversationFlow() {
  section('5.1 会话管理（createConversation / fetch / rename / delete）');

  let conv;
  try {
    const { data, status } = await baseAxios.post(`${API_PREFIX}/conversations`, {
      user_id: USER_ID,
      title: 'Phase5-会话测试',
    });
    if (status !== 201 || !data.conversation_id) {
      fail('createConversation', `status=${status}`);
      return null;
    }
    conv = { id: data.conversation_id, title: data.title };
    ok(`createConversation → id=${conv.id}`);
  } catch (e) {
    fail('createConversation', e.message);
    return null;
  }

  try {
    const { data } = await baseAxios.get(`${API_PREFIX}/conversations/user/${USER_ID}`);
    const found = data.some((c) => c.conversation_id === conv.id);
    if (found) ok('fetchConversations 列表含新会话');
    else fail('fetchConversations', '未找到新会话');
  } catch (e) {
    fail('fetchConversations', e.message);
  }

  const newTitle = 'Phase5-已重命名';
  try {
    const { data } = await baseAxios.put(`${API_PREFIX}/conversations/${conv.id}`, {
      title: newTitle,
    });
    if (data.title === newTitle) ok('updateConversationTitle 成功');
    else fail('updateConversationTitle', `title=${data.title}`);
  } catch (e) {
    fail('updateConversationTitle', e.message);
  }

  try {
    const { data } = await baseAxios.get(`${API_PREFIX}/conversations/${conv.id}/messages`);
    if (Array.isArray(data) && data.length === 0) ok('fetchMessages 空列表');
    else fail('fetchMessages', `length=${data?.length}`);
  } catch (e) {
    fail('fetchMessages', e.message);
  }

  return conv;
}

async function testStreamChat(convId, message, label, expectStatuses = []) {
  section(`5.2 SSE 流式 — ${label}`);
  console.log(`问题: ${message}`);

  try {
    const { accumulated, nodeStatuses, statusLabels } = await sendMessageStream(
      convId,
      USER_ID,
      message,
    );

    if (!accumulated.trim()) {
      fail(label, '未收到任何 content');
      return false;
    }
    if (accumulated.includes('处理失败')) {
      fail(label, accumulated.slice(0, 120));
      return false;
    }

    ok(`${label} 流式回复 ${accumulated.length} 字`);
    console.log(`  节点状态: ${[...nodeStatuses].join(', ') || '(无)'}`);
    console.log(`  UI 文案: ${[...statusLabels].join(' → ') || '(无)'}`);
    console.log(`  预览: ${accumulated.slice(0, 120)}...`);

    for (const expected of expectStatuses) {
      if (nodeStatuses.has(expected)) {
        ok(`${label} 含预期状态 ${expected}`);
      } else {
        fail(`${label} 缺少状态 ${expected}`);
      }
    }

    const { data: msgs } = await baseAxios.get(
      `${API_PREFIX}/conversations/${convId}/messages`,
    );
    const userMsg = msgs.some((m) => m.role === 'user' && m.content === message);
    const assistantMsg = msgs.some(
      (m) => m.role === 'assistant' && m.content.length > 0 && !m.content.startsWith('处理失败'),
    );
    if (userMsg && assistantMsg) ok(`${label} 消息已持久化`);
    else fail(`${label} 消息持久化`, `user=${userMsg} assistant=${assistantMsg}`);

    return true;
  } catch (e) {
    fail(label, e.message);
    return false;
  }
}

async function testUpload() {
  section('5.4 上传页 API 回归（uploadSales / uploadReviews）');

  if (!fs.existsSync(SALES_CSV)) {
    console.log(`⚠️  跳过上传测试：未找到 ${SALES_CSV}`);
    return;
  }

  try {
    const form = new FormData();
    form.append('file', new Blob([fs.readFileSync(SALES_CSV)]), 'sales_data.csv');
    const { data, status } = await axios.post(`${BASE_URL}${API_PREFIX}/upload/sales`, form, {
      timeout: 120_000,
    });
    if (status === 200 && data.inserted > 0) {
      ok(`uploadSales inserted=${data.inserted}`);
    } else {
      fail('uploadSales', JSON.stringify(data));
    }
  } catch (e) {
    fail('uploadSales', e.message);
  }

  if (!fs.existsSync(REVIEWS_CSV)) {
    console.log(`⚠️  跳过 reviews 上传：未找到 ${REVIEWS_CSV}`);
    return;
  }

  try {
    console.log('uploadReviews 写入向量索引中，可能需要 1-3 分钟…');
    const form = new FormData();
    form.append('file', new Blob([fs.readFileSync(REVIEWS_CSV)]), 'reviews_data.csv');
    const { data, status } = await axios.post(`${BASE_URL}${API_PREFIX}/upload/reviews`, form, {
      timeout: 600_000,
    });
    if (status === 200 && data.inserted > 0 && data.chroma_written > 0) {
      ok(
        `uploadReviews inserted=${data.inserted} chroma=${data.chroma_written} skipped=${data.skipped_rows ?? 0}`,
      );
    } else {
      fail('uploadReviews', JSON.stringify(data));
    }
  } catch (e) {
    fail('uploadReviews', e.message);
  }
}

async function main() {
  console.log(`Phase 5 E2E | BASE_URL=${BASE_URL} | USER_ID=${USER_ID}`);

  const healthy = await testHealth();
  if (!healthy) {
    console.log('\n❌ 后端未启动，请先运行: cd backend && python run.py');
    process.exit(1);
  }

  await testUpload();

  const conv = await testConversationFlow();
  if (!conv) {
    console.log(`\n结果: ${passed} 通过, ${failed} 失败`);
    process.exit(1);
  }

  await testStreamChat(conv.id, '各区域销售额对比', 'SQL 路由', [
    'thinking_sql',
    'sql_done',
  ]);

  const convVector = (
    await baseAxios.post(`${API_PREFIX}/conversations`, {
      user_id: USER_ID,
      title: 'Phase5-Vector',
    })
  ).data.conversation_id;

  await testStreamChat(convVector, '用户对数码配件的评价', 'Vector 路由', [
    'thinking_vector',
    'vector_done',
  ]);

  const convCombo = (
    await baseAxios.post(`${API_PREFIX}/conversations`, {
      user_id: USER_ID,
      title: 'Phase5-组合',
    })
  ).data.conversation_id;

  await testStreamChat(
    convCombo,
    '9月份哪个区域销售额最低？为什么？',
    'SQL+Vector 组合',
    ['sql_done', 'vector_done'],
  );

  try {
    await baseAxios.delete(`${API_PREFIX}/conversations/${conv.id}`);
    ok('deleteConversation 成功');
  } catch (e) {
    fail('deleteConversation', e.message);
  }

  section('汇总');
  console.log(`通过: ${passed} | 失败: ${failed}`);
  if (failed === 0) {
    console.log('\n🎉 Phase 5 所有自动化测试通过！');
    console.log('\n手动 UI 验收（浏览器）:');
    console.log('  1. 打开 http://localhost:5173/chat');
    console.log('  2. 新建会话 → 发送上述 3 个问题');
    console.log('  3. F12 → Network → 查看 chat/stream SSE 流');
    console.log('  4. 侧边栏测试重命名 / 删除 / 切换会话');
  } else {
    console.log('\n❌ 部分测试失败，请检查上方输出');
  }

  process.exit(failed > 0 ? 1 : 0);
}

main();
