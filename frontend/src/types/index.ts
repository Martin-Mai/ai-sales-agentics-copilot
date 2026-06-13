export type MessageRole = 'user' | 'assistant' | 'system';

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string | number;
  role: MessageRole;
  content: string;
  timestamp: string;
}

export interface UserInfo {
  id: string;
  name?: string;
}

/** 后端原始会话响应 */
export interface ConversationResponse {
  conversation_id: string;
  user_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

/** 后端原始消息响应 */
export interface MessageResponse {
  id: number;
  conversation_id: string;
  role: MessageRole;
  content: string;
  timestamp: string;
}

/** SSE 流式事件 */
export type StreamEventType =
  | 'node_start'
  | 'planner_decision'
  | 'sql_result'
  | 'reviews'
  | 'text_chunk'
  | 'message';

export interface StreamEvent {
  event: StreamEventType | string;
  node?: string;
  tool?: string;
  reason?: string;
  data?: unknown;
  text?: string;
}

export type AgentStatus =
  | 'idle'
  | 'planning'
  | 'sql_query'
  | 'vector_search'
  | 'generating'
  | 'done'
  | 'error';

export interface UploadSalesResponse {
  inserted: number;
}

export interface UploadReviewsResponse {
  inserted: number;
  chroma_written: number;
  skipped_rows: number;
}
