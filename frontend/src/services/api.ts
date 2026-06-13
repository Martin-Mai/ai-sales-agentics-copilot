import axios, { type AxiosInstance } from 'axios';
import type {
  ChartSpec,
  Conversation,
  ConversationResponse,
  Message,
  MessageResponse,
  UploadReviewsResponse,
  UploadSalesResponse,
} from '../types';
import { parseMessageContent } from '../utils/chartMessage';

const BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ||
  'http://localhost:8000';

const API_PREFIX = '/api/v1';

/** Axios 基础实例 — 所有 REST 请求统一走此客户端 */
export const baseAxios: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 60_000,
});

const USER_ID_KEY = 'sales_copilot_user_id';

export function getUserId(): string {
  let id = localStorage.getItem(USER_ID_KEY);
  if (!id) {
    id = `user_${crypto.randomUUID().slice(0, 8)}`;
    localStorage.setItem(USER_ID_KEY, id);
  }
  return id;
}

/** SSE data 行 JSON 载荷（兼容 LangGraph 新格式与现有 event 格式） */
interface StreamChunkPayload {
  content?: string;
  node_status?: string;
  text?: string;
  event?: string;
  node?: string;
  tool?: string;
  data?: ChartSpec | unknown;
}

function mapConversation(raw: ConversationResponse): Conversation {
  return {
    id: raw.conversation_id,
    title: raw.title,
    created_at: raw.created_at,
    updated_at: raw.updated_at,
  };
}

function mapMessage(raw: MessageResponse): Message {
  const { chart, content } = parseMessageContent(raw.content);
  return {
    id: raw.id,
    role: raw.role,
    content,
    timestamp: raw.timestamp,
    chart,
  };
}

function resolveNodeStatus(payload: StreamChunkPayload): string | undefined {
  if (payload.node_status) {
    return payload.node_status;
  }

  switch (payload.event) {
    case 'node_start':
      if (payload.node === 'planner') return 'thinking_planner';
      if (payload.node === 'sql_tool') return 'thinking_sql';
      if (payload.node === 'vector_tool') return 'thinking_vector';
      if (payload.node === 'chart_spec') return 'generating_chart';
      if (payload.node === 'insight') return 'generating';
      return payload.node ? `thinking_${payload.node}` : undefined;
    case 'planner_decision':
      if (payload.tool === 'sql_tool') return 'planning_sql';
      if (payload.tool === 'vector_tool') return 'planning_vector';
      return 'planning';
    case 'sql_result':
      return 'sql_done';
    case 'chart_spec':
      return 'chart_done';
    case 'reviews':
      return 'vector_done';
    default:
      return undefined;
  }
}

function resolveContent(payload: StreamChunkPayload): string {
  if (typeof payload.content === 'string') {
    return payload.content;
  }
  if (typeof payload.text === 'string') {
    return payload.text;
  }
  return '';
}

function resolveChartSpec(payload: StreamChunkPayload): ChartSpec | undefined {
  if (payload.event !== 'chart_spec' || !payload.data) {
    return undefined;
  }
  return payload.data as ChartSpec;
}

function parseStreamDataLine(line: string): {
  content: string;
  nodeStatus?: string;
  chartSpec?: ChartSpec;
} | null {
  const trimmed = line.trimEnd();
  if (!trimmed.startsWith('data:')) {
    return null;
  }

  const payloadStr = trimmed.slice(5).trimStart();
  if (!payloadStr || payloadStr === '[DONE]') {
    return null;
  }

  try {
    const payload = JSON.parse(payloadStr) as StreamChunkPayload;
    const content = resolveContent(payload);
    const nodeStatus = resolveNodeStatus(payload);
    const chartSpec = resolveChartSpec(payload);
    if (!content && !nodeStatus && !chartSpec) {
      return null;
    }
    return { content, nodeStatus, chartSpec };
  } catch {
    return null;
  }
}

/** 将 node_status 映射为 UI 可读文案 */
export function nodeStatusToLabel(nodeStatus?: string): string | null {
  if (!nodeStatus) return null;

  switch (nodeStatus) {
    case 'thinking_planner':
    case 'planning':
      return '正在分析您的问题…';
    case 'planning_sql':
      return '已规划：SQL 数据查询';
    case 'planning_vector':
      return '已规划：评论向量检索';
    case 'thinking_sql':
      return '正在查询销售数据库 (SQL)…';
    case 'thinking_vector':
      return '正在检索用户评论 (Vector)…';
    case 'generating':
    case 'thinking_insight':
      return '正在生成销售洞察…';
    case 'sql_done':
      return '数据库查询完成，正在整合结果…';
    case 'chart_done':
      return '图表已生成，正在撰写洞察…';
    case 'vector_done':
      return '评论检索完成，正在整合结果…';
    default:
      return '处理中…';
  }
}

// ─── 文件上传 ────────────────────────────────────────────────────────────────

const UPLOAD_TIMEOUT_SALES_MS = 120_000;
const UPLOAD_TIMEOUT_REVIEWS_MS = 600_000;

async function uploadCsv<T>(
  path: string,
  file: File,
  timeoutMs: number,
): Promise<T> {
  const formData = new FormData();
  formData.append('file', file);
  try {
    const { data } = await baseAxios.post<T>(path, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: timeoutMs,
    });
    return data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      const detail = error.response?.data?.detail;
      throw new Error(
        typeof detail === 'string' ? detail : (error.message || '上传失败'),
      );
    }
    throw error;
  }
}

export async function uploadSales(file: File): Promise<UploadSalesResponse> {
  return uploadCsv<UploadSalesResponse>(
    `${API_PREFIX}/upload/sales`,
    file,
    UPLOAD_TIMEOUT_SALES_MS,
  );
}

export async function uploadReviews(file: File): Promise<UploadReviewsResponse> {
  return uploadCsv<UploadReviewsResponse>(
    `${API_PREFIX}/upload/reviews`,
    file,
    UPLOAD_TIMEOUT_REVIEWS_MS,
  );
}

// ─── 会话管理 ────────────────────────────────────────────────────────────────

export async function fetchConversations(userId: string): Promise<Conversation[]> {
  const { data } = await baseAxios.get<ConversationResponse[]>(
    `${API_PREFIX}/conversations/user/${userId}`,
  );
  return data.map(mapConversation);
}

export async function createConversation(title = '新会话'): Promise<Conversation> {
  const { data } = await baseAxios.post<ConversationResponse>(
    `${API_PREFIX}/conversations`,
    { user_id: getUserId(), title },
  );
  return mapConversation(data);
}

export async function updateConversationTitle(
  id: string,
  title: string,
): Promise<Conversation> {
  const { data } = await baseAxios.put<ConversationResponse>(
    `${API_PREFIX}/conversations/${id}`,
    { title },
  );
  return mapConversation(data);
}

export async function deleteConversation(id: string): Promise<void> {
  await baseAxios.delete(`${API_PREFIX}/conversations/${id}`);
}

export async function fetchMessages(conversationId: string): Promise<Message[]> {
  const { data } = await baseAxios.get<MessageResponse[]>(
    `${API_PREFIX}/conversations/${conversationId}/messages`,
  );
  return data.map(mapMessage);
}

// ─── SSE 流式聊天 ────────────────────────────────────────────────────────────

/**
 * POST SSE 流式聊天 — 原生 fetch + ReadableStream 逐行解析
 * 工业级 buffer 处理：防截断 / 防粘包
 */
export const sendMessageStream = async (
  conversationId: string,
  userId: string,
  message: string,
  onChunk: (
    content: string,
    nodeStatus?: string,
    chartSpec?: ChartSpec,
  ) => void,
  onDone: () => void,
  onError: (error: unknown) => void,
): Promise<void> => {
  let reader: ReadableStreamDefaultReader<Uint8Array> | null = null;

  try {
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
      let detail = `请求失败 (${response.status})`;
      try {
        const errBody = (await response.json()) as { detail?: string };
        detail = errBody.detail ?? detail;
      } catch {
        /* 非 JSON 错误体，保留默认 detail */
      }
      throw new Error(detail);
    }

    if (!response.body) {
      throw new Error('无法读取响应流');
    }

    reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';

      for (const line of lines) {
        const parsed = parseStreamDataLine(line);
        if (parsed) {
          onChunk(parsed.content, parsed.nodeStatus, parsed.chartSpec);
        }
      }
    }

    if (buffer.trim()) {
      const parsed = parseStreamDataLine(buffer);
      if (parsed) {
        onChunk(parsed.content, parsed.nodeStatus, parsed.chartSpec);
      }
    }

    onDone();
  } catch (error) {
    onError(error);
  } finally {
    try {
      await reader?.cancel();
    } catch {
      /* 流已关闭时忽略 */
    }
  }
};
