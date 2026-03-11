import { useEffect, useRef, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { NAV_ITEMS } from "../constants/navigation";
import { useChat } from "../hooks/useChat";
import { Sidebar } from "./layout/Sidebar";
import { Header } from "./layout/Header";
import { ErrorBanner } from "./layout/ErrorBanner";
import { MessageList } from "./chat/MessageList";
import { ChatInput } from "./chat/ChatInput";
import { IconMenu } from "./icons";
import { CrewFlowPage } from "./flow/CrewFlowPage";
import { generateId } from "../utils";
import styles from "./ChatUI.module.css";

interface ChatWorkspaceProps {
  error: string | null;
  isLoading: boolean;
  messages: ReturnType<typeof useChat>["messages"];
  onToggleSidebar: () => void;
  onSend: (input: string) => void;
  onNewSession: () => void;
  onDownload: () => void;
  canDownload: boolean;
  onRefresh: () => void;
  onStop: () => void;
  onToggleFullscreen: () => void;
  onHistory: () => void;
  canRefresh: boolean;
  canStop: boolean;
  canHistory: boolean;
  isFullscreen: boolean;
  onClearError: () => void;
}

interface PlaceholderPageProps {
  title: string;
  description: string;
  onToggleSidebar: () => void;
}

function ChatWorkspace({
  error,
  isLoading,
  messages,
  onToggleSidebar,
  onSend,
  onNewSession,
  onDownload,
  canDownload,
  onRefresh,
  onStop,
  onToggleFullscreen,
  onHistory,
  canRefresh,
  canStop,
  canHistory,
  isFullscreen,
  onClearError,
}: ChatWorkspaceProps) {
  return (
    <>
      <Header
        error={error}
        onToggleSidebar={onToggleSidebar}
        onNewSession={onNewSession}
        onDownload={onDownload}
        canDownload={canDownload}
        onRefresh={onRefresh}
        onStop={onStop}
        onToggleFullscreen={onToggleFullscreen}
        onHistory={onHistory}
        canRefresh={canRefresh}
        canStop={canStop}
        canHistory={canHistory}
        isFullscreen={isFullscreen}
      />

      {error && <ErrorBanner message={error} onClose={onClearError} />}

      <MessageList messages={messages} isLoading={isLoading} />

      <ChatInput
        isLoading={isLoading}
        onSend={onSend}
      />
    </>
  );
}

function PlaceholderPage({ title, description, onToggleSidebar }: PlaceholderPageProps) {
  return (
    <div className={styles.placeholderPage}>
      <div className={styles.placeholderHeader}>
        <div className={styles.placeholderHeaderLeft}>
          <button
            type="button"
            onClick={onToggleSidebar}
            className={styles.placeholderMenuButton}
          >
            <IconMenu />
          </button>
          <div>
            <div className={styles.placeholderTitle}>{title}</div>
            <div className={styles.placeholderSubtitle}>{description}</div>
          </div>
        </div>
      </div>

      <div className={styles.placeholderBody}>
        <div className={styles.placeholderCard}>
          <h2>{title}</h2>
          <p>
            메뉴 이동은 연결되었습니다. 이 영역에 {title} 페이지의 실제 기능 컴포넌트를
            추가하면 됩니다.
          </p>
        </div>
      </div>
    </div>
  );
}

export default function ChatUI() {
  const [sessionName, setSessionName] = useState("Main Session");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const {
    messages,
    crewGraph,
    isLoading,
    error,
    sendMessage,
    stopStreaming,
    resetSession,
    clearError,
  } = useChat();

  useEffect(() => {
    const syncFullscreenState = () => {
      setIsFullscreen(Boolean(document.fullscreenElement));
    };

    document.addEventListener("fullscreenchange", syncFullscreenState);
    return () => {
      document.removeEventListener("fullscreenchange", syncFullscreenState);
    };
  }, []);

  const handleSend = (input: string) => {
    sendMessage(input, sessionName);
  };

  const handleNewSession = () => {
    resetSession();
    setSessionName(`Session ${generateId()}`);
  };

  const handleDownload = () => {
    const exportedAt = new Date();
    const safeSession =
      sessionName
        .replace(/[^a-zA-Z0-9-_]+/g, "_")
        .replace(/^_+|_+$/g, "") || "session";

    const content = [
      "# Chat Export",
      "",
      `- Session: ${sessionName}`,
      `- Exported At: ${exportedAt.toISOString()}`,
      "",
      ...messages.map((msg) => {
        const roleLabel = msg.role === "user" ? "User" : "Assistant";
        const sourceLine = msg.source ? `- Source: ${msg.source}\n` : "";
        return `## ${roleLabel}\n- Time: ${msg.timestamp.toISOString()}\n${sourceLine}\n${msg.content}\n`;
      }),
    ].join("\n");

    const blob = new Blob([content], {
      type: "text/markdown;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);

    const link = document.createElement("a");
    link.href = url;
    link.download = `chat-${safeSession}-${exportedAt
      .toISOString()
      .replace(/:/g, "-")}.md`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    URL.revokeObjectURL(url);
  };

  const handleRefresh = () => {
    if (isLoading) return;
    const lastUserMessage = [...messages].reverse().find((msg) => msg.role === "user");
    if (!lastUserMessage) return;

    sendMessage(lastUserMessage.content, sessionName);
  };

  const handleStop = () => {
    stopStreaming();
  };

  const handleToggleFullscreen = async () => {
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
        return;
      }

      const target = containerRef.current ?? document.documentElement;
      await target.requestFullscreen();
    } catch {
      // Ignore fullscreen API failures (e.g., unsupported browser context).
    }
  };

  const handleHistory = () => {
    const exportedAt = new Date();
    const safeSession =
      sessionName
        .replace(/[^a-zA-Z0-9-_]+/g, "_")
        .replace(/^_+|_+$/g, "") || "session";

    const payload = {
      session: sessionName,
      exported_at: exportedAt.toISOString(),
      entries: messages.map((msg) => ({
        role: msg.role,
        source: msg.source ?? null,
        timestamp: msg.timestamp.toISOString(),
        content: msg.content,
      })),
      crew_graph: crewGraph,
    };

    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: "application/json;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);

    const link = document.createElement("a");
    link.href = url;
    link.download = `history-${safeSession}-${exportedAt
      .toISOString()
      .replace(/:/g, "-")}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    URL.revokeObjectURL(url);
  };

  const canDownload = messages.length > 0;
  const canRefresh = messages.some((msg) => msg.role === "user") && !isLoading;
  const canStop = isLoading;
  const canHistory = messages.length > 0;

  const toggleSidebar = () => {
    setSidebarOpen((open) => !open);
  };

  const nonChatPages = NAV_ITEMS.filter((item) => item.path !== "/chat");

  return (
    <div className={styles.container} ref={containerRef}>
      <Sidebar isOpen={sidebarOpen} />

      <div className={styles.mainContent}>
        <Routes>
          <Route path="/" element={<Navigate to="/chat" replace />} />
          <Route
            path="/chat"
            element={
              <ChatWorkspace
                error={error}
                isLoading={isLoading}
                messages={messages}
                onToggleSidebar={toggleSidebar}
                onSend={handleSend}
                onNewSession={handleNewSession}
                onDownload={handleDownload}
                canDownload={canDownload}
                onRefresh={handleRefresh}
                onStop={handleStop}
                onToggleFullscreen={handleToggleFullscreen}
                onHistory={handleHistory}
                canRefresh={canRefresh}
                canStop={canStop}
                canHistory={canHistory}
                isFullscreen={isFullscreen}
                onClearError={clearError}
              />
            }
          />
          {nonChatPages.map((page) => (
            <Route
              key={page.path}
              path={page.path}
              element={
                page.path === "/agents" ? (
                  <CrewFlowPage
                    crewGraph={crewGraph}
                    onToggleSidebar={toggleSidebar}
                  />
                ) : (
                  <PlaceholderPage
                    title={page.label}
                    description={page.description}
                    onToggleSidebar={toggleSidebar}
                  />
                )
              }
            />
          ))}
          <Route path="*" element={<Navigate to="/chat" replace />} />
        </Routes>
      </div>
    </div>
  );
}