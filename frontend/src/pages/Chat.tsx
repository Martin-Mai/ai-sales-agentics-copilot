import { useCallback, useEffect, useState } from 'react';
import ChatWindow from '../components/ChatWindow';
import Sidebar from '../components/Sidebar';
import {
  createConversation,
  deleteConversation,
  fetchConversations,
  fetchMessages,
  sendMessageStream,
  updateConversationTitle,
} from '../services/api';
import type { Conversation, Message, ChartSpec } from '../types';

const MOCK_USER_ID = 'user_9527';
const USER_ID_STORAGE_KEY = 'sales_copilot_user_id';
const THEME_KEY = 'sales_copilot_theme';

function getInitialTheme(): boolean {
  const stored = localStorage.getItem(THEME_KEY);
  if (stored === 'dark') return true;
  if (stored === 'light') return false;
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function createTempMessage(
  role: Message['role'],
  content: string,
): Message {
  return {
    id: `temp-${role}-${Date.now()}`,
    role,
    content,
    timestamp: new Date().toISOString(),
  };
}

export default function Chat() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(
    null,
  );
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [activeNodeStatus, setActiveNodeStatus] = useState<string | null>(null);
  const [loadingConversations, setLoadingConversations] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [isDark, setIsDark] = useState(getInitialTheme);

  useEffect(() => {
    localStorage.setItem(USER_ID_STORAGE_KEY, MOCK_USER_ID);
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', isDark);
    localStorage.setItem(THEME_KEY, isDark ? 'dark' : 'light');
  }, [isDark]);

  const loadConversations = useCallback(async () => {
    setLoadingConversations(true);
    try {
      const list = await fetchConversations(MOCK_USER_ID);
      setConversations(list);
      return list;
    } catch (err) {
      console.error('加载会话失败', err);
      return [];
    } finally {
      setLoadingConversations(false);
    }
  }, []);

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
        setCurrentConversationId(list[0].id);
      }
    });
  }, [loadConversations]);

  useEffect(() => {
    if (currentConversationId) {
      void loadMessages(currentConversationId);
    } else {
      setMessages([]);
    }
  }, [currentConversationId, loadMessages]);

  const handleNewConversation = async () => {
    if (isLoading) return;
    try {
      const conv = await createConversation('新会话');
      setConversations((prev) => [conv, ...prev]);
      setCurrentConversationId(conv.id);
      setMessages([]);
      setActiveNodeStatus(null);
    } catch (err) {
      console.error('创建会话失败', err);
    }
  };

  const handleSelect = (id: string) => {
    if (isLoading) return;
    setCurrentConversationId(id);
    setActiveNodeStatus(null);
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm('确定删除此会话？')) return;
    try {
      await deleteConversation(id);
      setConversations((prev) => {
        const next = prev.filter((c) => c.id !== id);
        if (currentConversationId === id) {
          setCurrentConversationId(next[0]?.id ?? null);
          if (!next[0]) {
            setMessages([]);
          }
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

  const appendAssistantContent = (content: string) => {
    setMessages((prev) => {
      const next = [...prev];
      const lastIndex = next.length - 1;
      const last = next[lastIndex];
      if (!last || last.role !== 'assistant') return prev;
      next[lastIndex] = { ...last, content: last.content + content };
      return next;
    });
  };

  const appendAssistantChart = (chartSpec: ChartSpec) => {
    setMessages((prev) => {
      const next = [...prev];
      const lastIndex = next.length - 1;
      const last = next[lastIndex];
      if (!last || last.role !== 'assistant') return prev;
      next[lastIndex] = { ...last, chart: chartSpec };
      return next;
    });
  };

  const handleSend = async (text: string) => {
    let conversationId = currentConversationId;

    if (!conversationId) {
      try {
        const conv = await createConversation(text.slice(0, 30));
        setConversations((prev) => [conv, ...prev]);
        conversationId = conv.id;
        setCurrentConversationId(conv.id);
      } catch (err) {
        console.error('创建会话失败', err);
        return;
      }
    }

    const userMsg = createTempMessage('user', text);
    const assistantPlaceholder = createTempMessage('assistant', '');

    setMessages((prev) => [...prev, userMsg, assistantPlaceholder]);
    setIsLoading(true);
    setActiveNodeStatus(null);

    const handleChunk = (
      content: string,
      nodeStatus?: string,
      chartSpec?: ChartSpec,
    ) => {
      if (nodeStatus) {
        setActiveNodeStatus(nodeStatus);
      }
      if (chartSpec) {
        appendAssistantChart(chartSpec);
      }
      if (content) {
        appendAssistantContent(content);
      }
    };

    const handleDone = async () => {
      setActiveNodeStatus(null);
      setIsLoading(false);
      if (conversationId) {
        await loadMessages(conversationId);
        const list = await loadConversations();
        setConversations(list);
      }
    };

    const handleError = (error: unknown) => {
      setActiveNodeStatus(null);
      setIsLoading(false);
      const errorText =
        error instanceof Error ? error.message : '发送失败，请稍后重试';
      setMessages((prev) => {
        const withoutEmptyAssistant =
          prev.length > 0 && prev[prev.length - 1].role === 'assistant' &&
          prev[prev.length - 1].content === ''
            ? prev.slice(0, -1)
            : prev;
        return [
          ...withoutEmptyAssistant,
          createTempMessage('system', errorText),
        ];
      });
    };

    await sendMessageStream(
      conversationId,
      MOCK_USER_ID,
      text,
      handleChunk,
      handleDone,
      handleError,
    );
  };

  const activeConversation = conversations.find(
    (c) => c.id === currentConversationId,
  );

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar
        conversations={conversations}
        activeId={currentConversationId}
        onSelect={handleSelect}
        onNew={handleNewConversation}
        onDelete={handleDelete}
        onRename={handleRename}
        isDark={isDark}
        onToggleTheme={() => setIsDark((d) => !d)}
        loading={loadingConversations}
        disabled={isLoading}
      />
      <main className="flex flex-1 flex-col overflow-hidden">
        {loadingMessages && messages.length === 0 && currentConversationId ? (
          <div className="flex flex-1 items-center justify-center text-sm text-slate-400">
            加载消息中…
          </div>
        ) : (
          <ChatWindow
            messages={messages}
            isLoading={isLoading}
            activeNodeStatus={activeNodeStatus}
            onSend={handleSend}
            conversationTitle={activeConversation?.title}
          />
        )}
      </main>
    </div>
  );
}
