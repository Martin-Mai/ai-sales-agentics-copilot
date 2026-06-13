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

interface MessageItemProps {
  message: Message;
  isStreaming?: boolean;
  statusLabel?: string | null;
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
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-amber-500/15 text-amber-600 dark:text-amber-400">
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

function SystemStatusIcon({ label }: { label: string }) {
  if (label.includes('SQL') || label.includes('数据库')) {
    return <Database className="h-3.5 w-3.5" />;
  }
  if (label.includes('Vector') || label.includes('评论') || label.includes('检索')) {
    return <Search className="h-3.5 w-3.5" />;
  }
  if (label.includes('洞察') || label.includes('规划')) {
    return <Sparkles className="h-3.5 w-3.5" />;
  }
  return <Loader2 className="h-3.5 w-3.5 animate-spin" />;
}

export default function MessageItem({
  message,
  isStreaming = false,
  statusLabel,
}: MessageItemProps) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';

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
                ? 'rounded-tl-md border border-amber-200/60 bg-amber-50 text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200'
                : 'rounded-tl-md border border-slate-200/80 bg-white text-slate-800 dark:border-slate-700 dark:bg-slate-800/80 dark:text-slate-100'
          }`}
        >
          {isSystem ? (
            <div className="flex items-center gap-2 text-xs font-medium">
              <SystemStatusIcon label={message.content} />
              <span className="animate-pulse-soft">{message.content}</span>
            </div>
          ) : isUser ? (
            <p className="whitespace-pre-wrap">{message.content}</p>
          ) : (
            <>
              {statusLabel && isStreaming && !message.content && (
                <div className="mb-2 flex items-center gap-2 rounded-lg bg-brand-50 px-3 py-2 text-xs text-brand-700 dark:bg-brand-500/10 dark:text-brand-300">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  <span className="animate-pulse-soft">{statusLabel}</span>
                </div>
              )}
              {message.content ? (
                <div className="markdown-body">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
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
