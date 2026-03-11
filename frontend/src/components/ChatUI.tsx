import { useState } from "react";
import { useChat } from "../hooks/useChat";
import { Sidebar } from "./layout/Sidebar";
import { Header } from "./layout/Header";
import { ErrorBanner } from "./layout/ErrorBanner";
import { MessageList } from "./chat/MessageList";
import { ChatInput } from "./chat/ChatInput";
import { generateId } from "../utils";
import styles from "./ChatUI.module.css";

export default function ChatUI() {
  const [sessionName, setSessionName] = useState("Main Session");
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const { messages, isLoading, error, sendMessage, resetSession, clearError } =
    useChat();

  const handleSend = (input: string) => {
    sendMessage(input, sessionName);
  };

  const handleNewSession = () => {
    resetSession();
    setSessionName(`Session ${generateId()}`);
  };

  return (
    <div className={styles.container}>
      <Sidebar isOpen={sidebarOpen} />

      <div className={styles.mainContent}>
        <Header
          error={error}
          sessionName={sessionName}
          onSessionNameChange={setSessionName}
          onToggleSidebar={() => setSidebarOpen((v) => !v)}
        />

        {error && <ErrorBanner message={error} onClose={clearError} />}

        <MessageList messages={messages} isLoading={isLoading} />

        <ChatInput
          isLoading={isLoading}
          onSend={handleSend}
          onNewSession={handleNewSession}
        />
      </div>
    </div>
  );
}