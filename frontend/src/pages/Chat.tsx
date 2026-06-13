import { useCallback, useEffect, useRef, useState } from 'react';
import ChatWindow from '../components/ChatWindow';
import Sidebar from '../components/Sidebar';
import {
  createConversation,
  deleteConversation,
  fetchConversations,
  fetchMessages,
  getUserId,
  sendMessageStream,
  streamEventToStatus,
  updateConversationTitle,
} from '../services/api';
import type { Conversation, Message, StreamEvent } from '../types';

const THEME_KEY = 'sales_copilot_theme';

function getInitialTheme(): boolean {
  const stored = localStorage.getItem(THEME_KEY);
  if (stored === 'dark') return true;
  if (stored === 'light') return false;
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

export default function Chat() {
  const userId = getUserId();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [streamingMessage, setStreamingMessage] = useState<Message | null>(null);
  const [statusLabel, setStatusLabel] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [loadingConversations, setLoadingConversations] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [isDark, setIsDark] = useState(getInitialTheme);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', isDark);
    localStorage.setItem(THEME_KEY, isDark ? 'dark' : 'light');
  }, [isDark]);

  const loadConversations = useCallback(async () => {
    setLoadingConversations(true);
    try {
      const list = await fetchConversations(userId);
      setConversations(list);
      return list;
    } catch (err) {
      console.error('加载会话失败', err);
      return [];
    } finally {
      setLoadingConversations(false);
    }
  }, [userId]);

  const loadMessages = useCallback(async (conversationId: string) => {
    setLoadingMessages(true);
    try {
      const msgs = await fetchMessages(conversationId);
      setMessages(msgs);
    } catch (err) {
      console.error('加载消息失败', err);
      setMessages([]);
    } finally {
      setLoadingMessages(false);
    }
  }, []);

  useEffect(() => {
    void loadConversations().then((list) => {
      if (list.length > 0) {
        setActiveId(list[0].id);
      }
    });
  }, [loadConversations]);

  useEffect(() => {
    if (activeId) {
      void loadMessages(activeId);
    } else {
      setMessages([]);
    }
  }, [activeId, loadMessages]);

  const handleNewConversation = async () => {
    try {
      const conv = await createConversation(userId);
      setConversations((prev) => [conv, ...prev]);
      setActiveId(conv.id);
      setMessages([]);
      setStreamingMessage(null);
      setStatusLabel(null);
    } catch (err) {
      console.error('创建会话失败', err);
    }
  };

  const handleSelect = (id: string) => {
    if (isStreaming) return;
    setActiveId(id);
    setStreamingMessage(null);
    setStatusLabel(null);
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm('确定删除此会话？')) return;
    try {
      await deleteConversation(id);
      setConversations((prev) => {
        const next = prev.filter((c) => c.id !== id);
        if (activeId === id) {
          setActiveId(next[0]?.id ?? null);
        }
        return next;
      });
    } catch (err) {
      console.error('删除会话失败', err);
    }
  };

  const handleRename = async (id: string, title: string) => {
    try {
      const updated = await updateConversationTitle(id, title);
      setConversations((prev) =>
        prev.map((c) => (c.id === id ? updated : c)),
      );
    } catch (err) {
      console.error('更新标题失败', err);
    }
  };

  const handleSend = async (text: string) => {
    let conversationId = activeId;

    if (!conversationId) {
      try {
        const conv = await createConversation(userId, text.slice(0, 30));
        setConversations((prev) => [conv, ...prev]);
        conversationId = conv.id;
        setActiveId(conv.id);
      } catch (err) {
        console.error('创建会话失败', err);
        return;
      }
    }

    const now = new Date().toISOString();
    const userMsg: Message = {
      id: `temp-user-${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: now,
    };

    const assistantPlaceholder: Message = {
      id: `temp-assistant-${Date.now()}`,
      role: 'assistant',
      content: '',
      timestamp: now,
    };

    setMessages((prev) => [...prev, userMsg]);
    setStreamingMessage(assistantPlaceholder);
    setStatusLabel('正在分析您的问题…');
    setIsStreaming(true);

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    let accumulated = '';

    const handleChunk = (event: StreamEvent) => {
      const status = streamEventToStatus(event);
      if (status) {
        setStatusLabel(status);
      }

      if (event.event === 'text_chunk' && event.text) {
        accumulated += event.text;
        setStreamingMessage((prev) =>
          prev ? { ...prev, content: accumulated } : prev,
        );
      }
    };

    const handleDone = async () => {
      setIsStreaming(false);
      setStatusLabel(null);
      setStreamingMessage(null);

      if (conversationId) {
        await loadMessages(conversationId);
        const list = await loadConversations();
        setConversations(list);
      }
    };

    const handleError = (error: Error) => {
      setIsStreaming(false);
      setStatusLabel(null);
      setStreamingMessage(null);
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          role: 'system',
          content: error.message,
          timestamp: new Date().toISOString(),
        },
      ]);
    };

    await sendMessageStream(
      conversationId,
      userId,
      text,
      handleChunk,
      handleDone,
      handleError,
      controller.signal,
    );
  };

  const activeConversation = conversations.find((c) => c.id === activeId);

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar
        conversations={conversations}
        activeId={activeId}
        onSelect={handleSelect}
        onNew={handleNewConversation}
        onDelete={handleDelete}
        onRename={handleRename}
        isDark={isDark}
        onToggleTheme={() => setIsDark((d) => !d)}
        loading={loadingConversations}
      />
      <main className="flex flex-1 flex-col overflow-hidden">
        {loadingMessages && messages.length === 0 && activeId ? (
          <div className="flex flex-1 items-center justify-center text-sm text-slate-400">
            加载消息中…
          </div>
        ) : (
          <ChatWindow
            messages={messages}
            streamingMessage={streamingMessage}
            statusLabel={statusLabel}
            isStreaming={isStreaming}
            disabled={false}
            onSend={handleSend}
            conversationTitle={activeConversation?.title}
          />
        )}
      </main>
    </div>
  );
}
