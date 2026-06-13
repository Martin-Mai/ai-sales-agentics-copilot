import { useEffect, useState } from 'react';
import {
  Check,
  MessageSquarePlus,
  Moon,
  Pencil,
  Sun,
  Trash2,
  Upload,
  X,
} from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import type { Conversation } from '../types';

interface SidebarProps {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  onRename: (id: string, title: string) => void;
  isDark: boolean;
  onToggleTheme: () => void;
  loading?: boolean;
  disabled?: boolean;
}

function formatDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    if (diff < 86_400_000) {
      return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    }
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
  } catch {
    return '';
  }
}

export default function Sidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
  onDelete,
  onRename,
  isDark,
  onToggleTheme,
  loading,
  disabled,
}: SidebarProps) {
  const location = useLocation();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');

  useEffect(() => {
    if (editingId === null) return;
    const exists = conversations.some((c) => c.id === editingId);
    if (!exists) {
      setEditingId(null);
    }
  }, [conversations, editingId]);

  const startEdit = (conv: Conversation) => {
    if (disabled) return;
    setEditingId(conv.id);
    setEditTitle(conv.title);
  };

  const confirmEdit = () => {
    if (editingId && editTitle.trim()) {
      onRename(editingId, editTitle.trim());
    }
    setEditingId(null);
  };

  const cancelEdit = () => {
    setEditingId(null);
  };

  return (
    <aside className="flex h-full w-64 shrink-0 flex-col border-r border-slate-200/80 bg-white dark:border-slate-700/80 dark:bg-slate-900">
      <div className="flex items-center justify-between border-b border-slate-200/80 px-4 py-4 dark:border-slate-700/80">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-indigo-600 text-xs font-bold text-white">
            AI
          </div>
          <span className="font-semibold text-slate-800 dark:text-slate-100">
            销售助理
          </span>
        </div>
        <button
          type="button"
          onClick={onToggleTheme}
          className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
          aria-label="切换主题"
        >
          {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </button>
      </div>

      <div className="flex flex-col gap-2 p-3">
        <button
          type="button"
          onClick={onNew}
          disabled={disabled}
          className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-brand-300 bg-brand-50 px-4 py-2.5 text-sm font-medium text-brand-600 transition hover:border-brand-400 hover:bg-brand-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-brand-500/40 dark:bg-brand-500/10 dark:text-brand-300 dark:hover:bg-brand-500/20"
        >
          <MessageSquarePlus className="h-4 w-4" />
          新建对话
        </button>

        <Link
          to="/upload"
          className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm transition ${
            location.pathname === '/upload'
              ? 'bg-slate-100 font-medium text-slate-800 dark:bg-slate-800 dark:text-slate-100'
              : 'text-slate-600 hover:bg-slate-50 dark:text-slate-400 dark:hover:bg-slate-800/60'
          }`}
        >
          <Upload className="h-4 w-4" />
          数据上传
        </Link>
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-4">
        <p className="px-2 py-2 text-xs font-medium uppercase tracking-wider text-slate-400">
          历史会话
        </p>

        {loading ? (
          <p className="px-3 py-4 text-center text-xs text-slate-400">加载中…</p>
        ) : conversations.length === 0 ? (
          <p className="px-3 py-4 text-center text-xs text-slate-400">暂无会话</p>
        ) : (
          <ul className="space-y-0.5">
            {conversations.map((conv) => {
              const isActive = conv.id === activeId;
              const isEditing = editingId === conv.id;

              return (
                <li key={conv.id} className="group relative">
                  {isEditing ? (
                    <div className="flex items-center gap-1 rounded-xl bg-slate-100 px-2 py-1.5 dark:bg-slate-800">
                      <input
                        value={editTitle}
                        onChange={(e) => setEditTitle(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') confirmEdit();
                          if (e.key === 'Escape') cancelEdit();
                        }}
                        className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs outline-none focus:border-brand-400 dark:border-slate-600 dark:bg-slate-900"
                        autoFocus
                      />
                      <button
                        type="button"
                        onClick={confirmEdit}
                        className="rounded p-1 text-green-600 hover:bg-green-50 dark:hover:bg-green-500/10"
                      >
                        <Check className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={cancelEdit}
                        className="rounded p-1 text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => onSelect(conv.id)}
                      onDoubleClick={() => startEdit(conv)}
                      disabled={disabled && !isActive}
                      className={`flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-left text-sm transition ${
                        isActive
                          ? 'bg-brand-50 font-medium text-brand-700 dark:bg-brand-500/15 dark:text-brand-300'
                          : 'text-slate-600 hover:bg-slate-50 dark:text-slate-400 dark:hover:bg-slate-800/60'
                      } disabled:cursor-not-allowed disabled:opacity-60`}
                    >
                      <span className="min-w-0 flex-1 truncate">{conv.title}</span>
                      <span className="shrink-0 text-[10px] text-slate-400 group-hover:invisible">
                        {formatDate(conv.updated_at)}
                      </span>
                    </button>
                  )}

                  {!isEditing && (
                    <div className="absolute right-2 top-1/2 flex -translate-y-1/2 gap-0.5 opacity-0 transition group-hover:opacity-100">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          startEdit(conv);
                        }}
                        disabled={disabled}
                        className="rounded-lg bg-white p-1.5 text-slate-500 shadow-sm ring-1 ring-slate-200 hover:text-brand-600 disabled:opacity-50 dark:bg-slate-800 dark:ring-slate-600"
                        aria-label="修改标题"
                      >
                        <Pencil className="h-3 w-3" />
                      </button>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          onDelete(conv.id);
                        }}
                        disabled={disabled}
                        className="rounded-lg bg-white p-1.5 text-slate-500 shadow-sm ring-1 ring-slate-200 hover:text-red-500 disabled:opacity-50 dark:bg-slate-800 dark:ring-slate-600"
                        aria-label="删除会话"
                      >
                        <Trash2 className="h-3 w-3" />
                      </button>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </aside>
  );
}
