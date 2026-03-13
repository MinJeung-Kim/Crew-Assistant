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
import { ToolsPage } from "./tools/ToolsPage";
import { generateId } from "../utils";
import {
  buildCrewReportExport,
  buildDownloadFileName,
  buildHistoryExportPayload,
  downloadReportAsPdf,
  downloadReportAsDoc,
  triggerBlobDownload,
  type DownloadFormat,
} from "../utils/chatExport";
import { uploadKnowledgeFile } from "../services/knowledgeApi";
import styles from "./ChatUI.module.css";

interface ChatWorkspaceProps {
  error: string | null;
  isLoading: boolean;
  messages: ReturnType<typeof useChat>["messages"];
  onToggleSidebar: () => void;
  onSend: (input: string) => void;
  onNewSession: () => void;
  onDownload: (format: DownloadFormat) => void;
  canDownload: boolean;
  onTranslateMessage: (id: string, translatedContent: string, showTranslated: boolean) => void;
  onUploadKnowledge: (file: File) => void;
  isUploadingKnowledge: boolean;
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
  onTranslateMessage,
  onUploadKnowledge,
  isUploadingKnowledge,
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
        onUploadKnowledge={onUploadKnowledge}
        isUploadingKnowledge={isUploadingKnowledge}
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

      <MessageList messages={messages} isLoading={isLoading} onTranslateMessage={onTranslateMessage} />

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
  const [isUploadingKnowledge, setIsUploadingKnowledge] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const {
    messages,
    crewGraph,
    crewProgress,
    isLoading,
    error,
    sendMessage,
    stopStreaming,
    appendAssistantMessage,
    resetSession,
    clearError,
    updateMessageTranslation,
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

  const handleDownload = (format: DownloadFormat) => {
    const exportedAt = new Date();
    const content = buildCrewReportExport(sessionName, exportedAt, messages);
    if (format === "pdf") {
      downloadReportAsPdf(sessionName, content);
      return;
    }
    const ext = format === "doc" ? "doc" : "md";
    const fileName = buildDownloadFileName("report", sessionName, exportedAt, ext);
    if (format === "doc") {
      downloadReportAsDoc(sessionName, content, fileName);
      return;
    }
    triggerBlobDownload(content, "text/markdown;charset=utf-8", fileName);
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
    const payload = buildHistoryExportPayload(
      sessionName,
      exportedAt,
      messages,
      crewGraph,
      crewProgress
    );
    const fileName = buildDownloadFileName("history", sessionName, exportedAt, "json");
    triggerBlobDownload(
      JSON.stringify(payload, null, 2),
      "application/json;charset=utf-8",
      fileName
    );
  };

  const handleUploadKnowledge = async (file: File) => {
    if (isUploadingKnowledge) return;

    setIsUploadingKnowledge(true);
    try {
      const { chunkCount, totalChunks } = await uploadKnowledgeFile(file);

      appendAssistantMessage(
        [
          `회사 자료 업로드 완료: ${file.name}`,
          `- 신규 청크: ${chunkCount}`,
          `- 누적 청크: ${totalChunks}`,
          "이제 답변 시 회사 문서를 우선 참고합니다.",
        ].join("\n"),
        "rag-index"
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      appendAssistantMessage(
        `회사 자료 업로드 실패: ${msg}`,
        "rag-index"
      );
    } finally {
      setIsUploadingKnowledge(false);
    }
  };

  const canDownload = messages.some((msg) => msg.source === "crewai");
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
          <Route path="/env" element={<Navigate to="/tools" replace />} />
          <Route path="/agents" element={<Navigate to="/flow" replace />} />
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
                canDownload={canDownload}              onTranslateMessage={updateMessageTranslation}                onUploadKnowledge={handleUploadKnowledge}
                isUploadingKnowledge={isUploadingKnowledge}
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
                page.path === "/flow" ? (
                  <CrewFlowPage
                    crewGraph={crewGraph}
                    crewProgress={crewProgress}
                    onToggleSidebar={toggleSidebar}
                  />
                ) : page.path === "/tools" ? (
                  <ToolsPage onToggleSidebar={toggleSidebar} />
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