import type { Components } from 'react-markdown';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  Bot,
  Database,
  Loader2,
  Search,
  Sparkles,
  User,
  Wrench,
} from 'lucide-react';
import type { Message } from '../types';
import ChartCard from './ChartCard';

interface MessageItemProps {
  message: Message;
  isStreaming?: boolean;
  activeNodeStatus?: string | null;
}

/** 将 SSE node_status 映射为带 emoji 的 UI 文案 */
export function nodeStatusToDisplayLabel(nodeStatus?: string | null): string | null {
  if (!nodeStatus) return null;

  switch (nodeStatus) {
    case 'thinking_sql':
    case 'planning_sql':
    case 'sql_done':
      return '🔍 正在分析多维销售数据库…';
    case 'thinking_vector':
    case 'planning_vector':
    case 'vector_search':
    case 'vector_done':
      return '🤖 正在检索知识库…';
    case 'thinking_planner':
    case 'planning':
      return '💡 正在理解您的问题…';
    case 'generating':
    case 'thinking_insight':
      return '✨ 正在生成销售洞察…';
    case 'generating_chart':
    case 'chart_done':
      return '📊 正在生成数据图表…';
    default:
      if (nodeStatus.includes('sql')) {
        return '🔍 正在分析多维销售数据库…';
      }
      if (nodeStatus.includes('vector')) {
        return '🤖 正在检索知识库…';
      }
      return '⏳ 处理中…';
  }
}

function formatTime(timestamp: string): string {
  try {
    return new Date(timestamp).toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return '';
  }
}

function RoleIcon({ role }: { role: Message['role'] }) {
  if (role === 'user') {
    return (
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-500 text-white">
        <User className="h-4 w-4" />
      </div>
    );
  }
  if (role === 'system') {
    return (
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-red-500/15 text-red-600 dark:text-red-400">
        <Wrench className="h-4 w-4" />
      </div>
    );
  }
  return (
    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-indigo-600 text-white shadow-glow">
      <Bot className="h-4 w-4" />
    </div>
  );
}

function StatusCardIcon({ label }: { label: string }) {
  if (label.includes('数据库') || label.includes('🔍')) {
    return <Database className="h-4 w-4 shrink-0" />;
  }
  if (label.includes('知识库') || label.includes('🤖')) {
    return <Search className="h-4 w-4 shrink-0" />;
  }
  if (label.includes('洞察') || label.includes('✨')) {
    return <Sparkles className="h-4 w-4 shrink-0" />;
  }
  if (label.includes('图表') || label.includes('📊')) {
    return <Sparkles className="h-4 w-4 shrink-0" />;
  }
  return <Loader2 className="h-4 w-4 shrink-0 animate-spin" />;
}

const markdownComponents: Components = {
  img: ({ src, alt }) => (
    <figure className="my-4 overflow-hidden rounded-xl border border-slate-200/80 bg-slate-50 shadow-sm dark:border-slate-700 dark:bg-slate-800/50">
      <img
        src={src}
        alt={alt ?? 'chart'}
        className="mx-auto max-h-[480px] w-full object-contain p-2"
        loading="lazy"
      />
      {alt && alt !== 'chart' && (
        <figcaption className="border-t border-slate-200/80 px-4 py-2 text-center text-xs text-slate-500 dark:border-slate-700 dark:text-slate-400">
          {alt}
        </figcaption>
      )}
    </figure>
  ),
  table: ({ children }) => (
    <div className="my-4 overflow-x-auto rounded-xl border border-slate-200/80 shadow-sm dark:border-slate-700">
      <table className="w-full min-w-[480px] border-collapse text-left text-sm">
        {children}
      </table>
    </div>
  ),
  thead: ({ children }) => (
    <thead className="bg-gradient-to-r from-slate-100 to-slate-50 dark:from-slate-800 dark:to-slate-800/80">
      {children}
    </thead>
  ),
  tbody: ({ children }) => (
    <tbody className="divide-y divide-slate-100 dark:divide-slate-700/80">
      {children}
    </tbody>
  ),
  tr: ({ children }) => (
    <tr className="transition hover:bg-brand-50/40 dark:hover:bg-brand-500/5">
      {children}
    </tr>
  ),
  th: ({ children }) => (
    <th className="whitespace-nowrap px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="px-4 py-2.5 text-slate-700 dark:text-slate-200">
      {children}
    </td>
  ),
};

export default function MessageItem({
  message,
  isStreaming = false,
  activeNodeStatus,
}: MessageItemProps) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';
  const statusLabel = nodeStatusToDisplayLabel(activeNodeStatus);

  return (
    <div
      className={`flex gap-3 px-4 py-3 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}
    >
      <RoleIcon role={message.role} />

      <div
        className={`flex max-w-[85%] flex-col gap-1.5 ${isUser ? 'items-end' : 'items-start'}`}
      >
        <div
          className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-sm ${
            isUser
              ? 'rounded-tr-md bg-brand-500 text-white'
              : isSystem
                ? 'rounded-tl-md border border-red-200/60 bg-red-50 text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300'
                : 'rounded-tl-md border border-slate-200/80 bg-white text-slate-800 dark:border-slate-700 dark:bg-slate-800/80 dark:text-slate-100'
          }`}
        >
          {isSystem ? (
            <p className="text-sm font-medium">{message.content}</p>
          ) : isUser ? (
            <p className="whitespace-pre-wrap">{message.content}</p>
          ) : (
            <>
              {statusLabel && isStreaming && !message.content && !message.chart && (
                <div className="flex items-center gap-3 rounded-xl border border-brand-200/50 bg-gradient-to-r from-brand-50 to-indigo-50 px-4 py-3 text-sm text-brand-700 dark:border-brand-500/30 dark:from-brand-500/10 dark:to-indigo-500/10 dark:text-brand-300">
                  <StatusCardIcon label={statusLabel} />
                  <span className="animate-pulse-soft">{statusLabel}</span>
                </div>
              )}

              {message.chart && <ChartCard spec={message.chart} />}

              {message.content ? (
                <div className="markdown-body">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={markdownComponents}
                  >
                    {message.content}
                  </ReactMarkdown>
                  {isStreaming && (
                    <span className="ml-0.5 inline-block h-4 w-0.5 animate-blink bg-brand-500 align-middle" />
                  )}
                </div>
              ) : isStreaming ? (
                <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  <span>{statusLabel ?? '思考中…'}</span>
                </div>
              ) : null}

              {statusLabel && isStreaming && message.content && (
                <div className="mt-3 flex items-center gap-2 rounded-lg border border-slate-200/60 bg-slate-50 px-3 py-2 text-xs text-slate-600 dark:border-slate-600 dark:bg-slate-900/50 dark:text-slate-400">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  <span>{statusLabel}</span>
                </div>
              )}
            </>
          )}
        </div>

        {message.timestamp && (
          <span className="px-1 text-[10px] text-slate-400">
            {formatTime(message.timestamp)}
          </span>
        )}
      </div>
    </div>
  );
}
