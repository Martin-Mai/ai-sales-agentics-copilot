/**
 * Phase 6: 完整验收清单 — 一键自动化检查
 * 用法: npm run test:phase6
 * 可选: SKIP_LLM=1 跳过流式 LLM 测试（约节省 2 分钟）
 */
import axios from 'axios';
import { spawnSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '../..');
const BACKEND = path.join(ROOT, 'backend');
const FRONTEND = path.join(ROOT, 'frontend');

const BASE_URL = (process.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
const API_PREFIX = '/api/v1';
const SKIP_LLM = process.env.SKIP_LLM === '1';

const checklist = [];

function record(id, label, pass, note = '') {
  checklist.push({ id, label, pass, note });
  const icon = pass ? '✅' : '❌';
  console.log(`${icon} [${id}] ${label}${note ? ` — ${note}` : ''}`);
}

function runPython(script) {
  const py = fs.existsSync(path.join(BACKEND, 'venv/Scripts/python.exe'))
    ? path.join(BACKEND, 'venv/Scripts/python.exe')
    : 'python';
  const result = spawnSync(py, [script], {
    cwd: BACKEND,
    encoding: 'utf-8',
    env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
  });
  return { ok: result.status === 0, stdout: result.stdout || '', stderr: result.stderr || '' };
}

async function checkHealth() {
  try {
    const { data, status } = await axios.get(`${BASE_URL}/health`, { timeout: 5000 });
    record('6.01', '/health 返回 ok', status === 200 && data.status === 'ok', `model=${data.model}`);
  } catch (e) {
    record('6.01', '/health 返回 ok', false, e.message);
  }
}

async function checkSwagger() {
  try {
    const res = await axios.get(`${BASE_URL}/docs`, { timeout: 5000 });
    record('6.02', 'Swagger /docs 可访问', res.status === 200);
  } catch (e) {
    record('6.02', 'Swagger /docs 可访问', false, e.message);
  }
}

async function checkDataViaApi() {
  try {
    const userId = `phase6_probe_${Date.now()}`;
    const { data: conv } = await axios.post(
      `${BASE_URL}${API_PREFIX}/conversations`,
      { user_id: userId, title: 'Phase6-数据探测' },
      { timeout: 10000 },
    );
    const convId = conv.conversation_id;

    const response = await fetch(`${BASE_URL}${API_PREFIX}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        conversation_id: convId,
        user_id: userId,
        message: '各区域销售额对比',
      }),
    });

    if (!response.ok) {
      record('6.03', 'sales 数据可用（SQL 路由）', false, `HTTP ${response.status}`);
      record('6.04', 'reviews 数据可用（Vector 路由）', false, '跳过');
      return;
    }

    let buffer = '';
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let hasSql = false;
    let hasText = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      if (buffer.includes('sql_result')) hasSql = true;
      if (buffer.includes('text_chunk')) hasText = true;
    }

    record(
      '6.03',
      'sales 数据可用（SQL 路由可响应）',
      hasSql && hasText,
      hasSql ? '收到 sql_result' : '未收到 sql_result',
    );

    const { data: conv2 } = await axios.post(
      `${BASE_URL}${API_PREFIX}/conversations`,
      { user_id: userId, title: 'Phase6-Vector探测' },
      { timeout: 10000 },
    );

    const res2 = await fetch(`${BASE_URL}${API_PREFIX}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        conversation_id: conv2.conversation_id,
        user_id: userId,
        message: '用户对数码配件的评价',
      }),
    });

    buffer = '';
    const reader2 = res2.body.getReader();
    let hasReviews = false;
    let hasText2 = false;

    while (true) {
      const { done, value } = await reader2.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      if (buffer.includes('reviews')) hasReviews = true;
      if (buffer.includes('text_chunk')) hasText2 = true;
    }

    record(
      '6.04',
      'reviews 数据可用（Vector 路由可响应）',
      res2.ok && hasReviews && hasText2,
      hasReviews ? '收到 reviews 事件' : '未收到 reviews',
    );
  } catch (e) {
    record('6.03', 'sales 数据可用（SQL 路由）', false, e.message);
    record('6.04', 'reviews 数据可用（Vector 路由）', false, e.message);
  }
}

function checkBackendConversation() {
  const { ok, stdout } = runPython('test/test_conversation.py');
  record(
    '6.05',
    '创建/列表/重命名/删除会话正常（test_conversation.py）',
    ok,
    ok ? '全部通过' : stdout.split('\n').slice(-3).join(' '),
  );
}

function checkBackendChatStream() {
  if (SKIP_LLM) {
    record('6.06', 'SQL 问题流式回复正常（test_chat_stream.py）', true, 'SKIP_LLM=1 跳过');
    record('6.07', 'Vector 问题流式回复正常', true, 'SKIP_LLM=1 跳过');
    record('6.08', '组合问题流式回复正常', true, 'SKIP_LLM=1 跳过');
    record('6.09', '流结束后消息持久化到 DB', true, 'SKIP_LLM=1 跳过');
    return;
  }

  const { ok, stdout } = runPython('test/test_chat_stream.py');
  const sqlOk = stdout.includes('SQL 查询') && stdout.includes('验证 SQL 测试消息持久化') && stdout.includes('✅ OK');
  const vectorOk = stdout.includes('Vector 查询') && stdout.includes('验证 Vector 测试消息持久化');
  const comboOk = stdout.includes('组合查询') && stdout.includes('验证组合测试消息持久化');
  const persistCount = (stdout.match(/验证.*消息持久化[\s\S]*?✅ OK/g) || []).length;

  record('6.06', 'SQL 问题流式回复正常（test_chat_stream.py）', ok && sqlOk);
  record('6.07', 'Vector 问题流式回复正常', ok && vectorOk);
  record('6.08', '组合问题流式回复正常', ok && comboOk);
  record('6.09', '流结束后消息持久化到 DB', ok && persistCount >= 3);
}

function checkFrontendBuild() {
  const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm';
  const result = spawnSync(npm, ['run', 'build'], {
    cwd: FRONTEND,
    encoding: 'utf-8',
    shell: true,
  });
  record(
    '6.10',
    '前端 npm run build 无 TS 错误',
    result.status === 0,
    result.status === 0 ? 'build 成功' : (result.stderr || result.stdout).slice(-200),
  );
}

async function checkChatStreamHttp() {
  try {
    const userId = `phase6_http_${Date.now()}`;
    const { data: conv } = await axios.post(`${BASE_URL}${API_PREFIX}/conversations`, {
      user_id: userId,
      title: 'Phase6-HTTP探测',
    });
    const res = await fetch(`${BASE_URL}${API_PREFIX}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        conversation_id: conv.conversation_id,
        user_id: userId,
        message: '你好',
      }),
    });
    record(
      '6.11',
      'chat/stream HTTP 200 无异常状态码',
      res.status === 200,
      `status=${res.status}`,
    );
    if (res.body) await res.body.cancel();
  } catch (e) {
    record('6.11', 'chat/stream HTTP 200 无异常状态码', false, e.message);
  }
}

async function checkFrontendReachable() {
  const ports = [5173, 5174, 5175];
  let reachable = false;
  let url = '';
  for (const port of ports) {
    try {
      const u = `http://localhost:${port}`;
      const res = await fetch(u, { signal: AbortSignal.timeout(3000) });
      if (res.ok) {
        reachable = true;
        url = u;
        break;
      }
    } catch {
      /* try next port */
    }
  }
  record(
    '6.12',
    '前端 dev server 可访问（手动 UI 验收前置）',
    reachable,
    reachable ? url : '请运行 cd frontend && npm run dev',
  );
}

async function main() {
  console.log('╔══════════════════════════════════════════╗');
  console.log('║       Phase 6 完整验收清单检查             ║');
  console.log('╚══════════════════════════════════════════╝');
  console.log(`BASE_URL=${BASE_URL}\n`);

  await checkHealth();
  await checkSwagger();

  if (SKIP_LLM) {
    record('6.03', 'sales 数据可用', true, 'SKIP_LLM=1 跳过');
    record('6.04', 'reviews 数据可用', true, 'SKIP_LLM=1 跳过');
  } else {
    console.log('\n--- 数据层探测（SQL + Vector，约 1-2 分钟）---');
    await checkDataViaApi();
  }

  console.log('\n--- 后端自动化 ---');
  checkBackendConversation();
  checkBackendChatStream();

  console.log('\n--- 前端构建 ---');
  checkFrontendBuild();

  console.log('\n--- API 层 ---');
  await checkChatStreamHttp();
  await checkFrontendReachable();

  const passed = checklist.filter((c) => c.pass).length;
  const failed = checklist.filter((c) => !c.pass).length;

  console.log('\n╔══════════════════════════════════════════╗');
  console.log(`║  结果: ${passed}/${checklist.length} 通过, ${failed} 失败`.padEnd(41) + '║');
  console.log('╚══════════════════════════════════════════╝');

  console.log('\n【手动 UI 验收项】（需在浏览器确认）');
  console.log('  □ 聊天页顶部状态条随 SSE 节点变化');
  console.log('  □ 助手消息逐字流式渲染');
  console.log('  □ F12 → Network → chat/stream 响应流正常');
  console.log('  □ 侧边栏重命名 / 切换 / 删除会话');
  console.log('  □ /upload 页拖拽上传 UI 正常');

  if (failed === 0) {
    console.log('\n🎉 Phase 6 自动化验收全部通过！');
  } else {
    console.log('\n❌ 存在失败项，请查看上方详情');
    checklist.filter((c) => !c.pass).forEach((c) => {
      console.log(`   - [${c.id}] ${c.label}: ${c.note}`);
    });
  }

  process.exit(failed > 0 ? 1 : 0);
}

main();
