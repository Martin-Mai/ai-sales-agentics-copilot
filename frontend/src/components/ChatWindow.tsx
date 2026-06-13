import { useCallback, useEffect, useRef, useState } from 'react';
import { Loader2, Send } from 'lucide-react';
import MessageItem from './MessageItem';
import type { Message } from '../types';

interface ChatWindowProps {
  messages: Message[];
  streamingMessage: Message | null;
  statusLabel: string | null;
  isStreaming: boolean;
  disabled: boolean;
  onSend: (text: string) => void;
  conversationTitle?: string;
}

export default function ChatWindow({
  messages,
  streamingMessage,
  statusLabel,
  isStreaming,
  disabled,
  onSend,
  conversationTitle,
}: ChatWindowProps) {
  const [input, setInput] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingMessage?.content, statusLabel, scrollToBottom]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || disabled || isStreaming) return;
    onSend(text);
    setInput('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  };

  const displayMessages = streamingMessage
    ? [...messages, streamingMessage]
    : messages;

  return (
    <div className="flex h-full flex-1 flex-col overflow-hidden">
      <header className="flex shrink-0 items-center justify-between border-b border-slate-200/80 bg-white/70 px-6 py-4 backdrop-blur dark:border-slate-700/80 dark:bg-slate-900/70">
        <div>
          <h1 className="text-lg font-semibold text-slate-800 dark:text-slate-100">
            {conversationTitle ?? 'AI 销售助理'}
          </h1>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            智能 SQL 查询 · 评论检索 · 销售洞察
          </p>
        </div>
        {isStreaming && (
          <div className="flex items-center gap-2 rounded-full bg-brand-50 px-3 py-1.5 text-xs font-medium text-brand-600 dark:bg-brand-500/15 dark:text-brand-300">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            {statusLabel ?? 'AI 响应中…'}
          </div>
        )}
      </header>

      <div className="flex-1 overflow-y-auto bg-gradient-to-b from-slate-50/50 to-white dark:from-slate-900/50 dark:to-slate-900">
        {displayMessages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-4 px-6 text-center">
            <div className="rounded-2xl bg-gradient-to-br from-brand-500 to-indigo-600 p-4 text-white shadow-glow">
              <svg
                className="h-10 w-10"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={1.5}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z"
                />
              </svg>
            </div>
            <div>
              <h2 className="text-xl font-semibold text-slate-700 dark:text-slate-200">
                开始对话
              </h2>
              <p className="mt-1 max-w-md text-sm text-slate-500 dark:text-slate-400">
                试试问：「各区域销售额对比」或「用户对数码配件的评价」
              </p>
            </div>
          </div>
        ) : (
          <div className="mx-auto max-w-3xl py-4">
            {messages.map((msg) => (
              <MessageItem key={msg.id} message={msg} />
            ))}
            {streamingMessage && (
              <MessageItem
                message={streamingMessage}
                isStreaming={isStreaming}
                statusLabel={statusLabel}
              />
            )}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      <div className="shrink-0 border-t border-slate-200/80 bg-white/80 p-4 backdrop-blur dark:border-slate-700/80 dark:bg-slate-900/80">
        <div className="mx-auto flex max-w-3xl items-end gap-3">
          <div className="relative flex-1">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={handleInput}
              onKeyDown={handleKeyDown}
              disabled={disabled || isStreaming}
              placeholder={
                isStreaming ? 'AI 正在回复…' : '输入问题，Enter 发送，Shift+Enter 换行'
              }
              rows={1}
              className="w-full resize-none rounded-xl border border-slate-200 bg-white px-4 py-3 pr-12 text-sm text-slate-800 shadow-sm outline-none transition focus:border-brand-400 focus:ring-2 focus:ring-brand-500/20 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:focus:border-brand-500"
            />
          </div>
          <button
            type="button"
            onClick={handleSend}
            disabled={disabled || isStreaming || !input.trim()}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-brand-500 text-white shadow-sm transition hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-40"
            aria-label="发送消息"
          >
            {isStreaming ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : (
              <Send className="h-5 w-5" />
            )}
          </button>
        </div>
        <p className="mx-auto mt-2 max-w-3xl text-center text-[10px] text-slate-400">
          AI 可能产生不准确的信息，请以实际业务数据为准
        </p>
      </div>
    </div>
  );
}
