import axios from 'axios';
import type {
  Conversation,
  ConversationResponse,
  Message,
  MessageResponse,
  StreamEvent,
  UploadReviewsResponse,
  UploadSalesResponse,
} from '../types';

const BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ||
  'http://localhost:8000';

const API_PREFIX = '/api/v1';

export const apiClient = axios.create({
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

function mapConversation(raw: ConversationResponse): Conversation {
  return {
    id: raw.conversation_id,
    title: raw.title,
    created_at: raw.created_at,
    updated_at: raw.updated_at,
  };
}

function mapMessage(raw: MessageResponse): Message {
  return {
    id: raw.id,
    role: raw.role,
    content: raw.content,
    timestamp: raw.timestamp,
  };
}

export async function fetchConversations(userId: string): Promise<Conversation[]> {
  const { data } = await apiClient.get<ConversationResponse[]>(
    `${API_PREFIX}/conversations/user/${userId}`,
  );
  return data.map(mapConversation);
}

export async function createConversation(
  userId: string,
  title = '新会话',
): Promise<Conversation> {
  const { data } = await apiClient.post<ConversationResponse>(
    `${API_PREFIX}/conversations`,
    { user_id: userId, title },
  );
  return mapConversation(data);
}

export async function updateConversationTitle(
  id: string,
  title: string,
): Promise<Conversation> {
  const { data } = await apiClient.put<ConversationResponse>(
    `${API_PREFIX}/conversations/${id}`,
    { title },
  );
  return mapConversation(data);
}

export async function deleteConversation(id: string): Promise<void> {
  await apiClient.delete(`${API_PREFIX}/conversations/${id}`);
}

export async function fetchMessages(conversationId: string): Promise<Message[]> {
  const { data } = await apiClient.get<MessageResponse[]>(
    `${API_PREFIX}/conversations/${conversationId}/messages`,
  );
  return data.map(mapMessage);
}

export async function uploadSales(file: File): Promise<UploadSalesResponse> {
  const formData = new FormData();
  formData.append('file', file);
  const { data } = await apiClient.post<UploadSalesResponse>(
    `${API_PREFIX}/upload/sales`,
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  );
  return data;
}

export async function uploadReviews(file: File): Promise<UploadReviewsResponse> {
  const formData = new FormData();
  formData.append('file', file);
  const { data } = await apiClient.post<UploadReviewsResponse>(
    `${API_PREFIX}/upload/reviews`,
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  );
  return data;
}

function parseSSELine(
  line: string,
  currentEvent: string,
): { event: StreamEvent | null; nextEvent: string } {
  if (line.startsWith('event:')) {
    return { event: null, nextEvent: line.slice(6).trim() };
  }
  if (line.startsWith('data:')) {
    const payload = line.slice(5).trim();
    try {
      const parsed = JSON.parse(payload) as StreamEvent;
      if (!parsed.event) {
        parsed.event = currentEvent;
      }
      return { event: parsed, nextEvent: currentEvent };
    } catch {
      return {
        event: { event: currentEvent, text: payload },
        nextEvent: currentEvent,
      };
    }
  }
  return { event: null, nextEvent: currentEvent };
}

/**
 * POST SSE 流式聊天 — 使用 fetch + ReadableStream 逐行解析
 */
export async function sendMessageStream(
  conversationId: string,
  userId: string,
  message: string,
  onChunk: (event: StreamEvent) => void,
  onDone: () => void,
  onError: (error: Error) => void,
  signal?: AbortSignal,
): Promise<void> {
  try {
    const response = await fetch(`${BASE_URL}${API_PREFIX}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify({
        conversation_id: conversationId,
        user_id: userId,
        message,
      }),
      signal,
    });

    if (!response.ok) {
      let detail = `请求失败 (${response.status})`;
      try {
        const errBody = await response.json();
        detail = errBody.detail ?? detail;
      } catch {
        /* ignore */
      }
      throw new Error(detail);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('无法读取响应流');
    }

    const decoder = new TextDecoder();
    let buffer = '';
    let currentEvent = 'message';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';

      for (const line of lines) {
        const trimmed = line.trimEnd();
        if (!trimmed) continue;

        const { event, nextEvent } = parseSSELine(trimmed, currentEvent);
        currentEvent = nextEvent;
        if (event) {
          onChunk(event);
        }
      }
    }

    onDone();
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      onDone();
      return;
    }
    onError(err instanceof Error ? err : new Error(String(err)));
  }
}

export function streamEventToStatus(event: StreamEvent): string | null {
  switch (event.event) {
    case 'node_start':
      if (event.node === 'planner') return '正在分析您的问题…';
      if (event.node === 'sql_tool') return '正在查询销售数据库 (SQL)…';
      if (event.node === 'vector_tool') return '正在检索用户评论 (Vector)…';
      if (event.node === 'insight') return '正在生成销售洞察…';
      return '处理中…';
    case 'planner_decision':
      if (event.tool === 'sql_tool') return '已规划：SQL 数据查询';
      if (event.tool === 'vector_tool') return '已规划：评论向量检索';
      return '已规划：直接生成洞察';
    case 'sql_result':
      return '数据库查询完成，正在整合结果…';
    case 'reviews':
      return '评论检索完成，正在整合结果…';
    default:
      return null;
  }
}
