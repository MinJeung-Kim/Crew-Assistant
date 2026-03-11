import type { Message } from "../../types/chat";
import { formatTime } from "../../utils";
import styles from "./MessageBubble.module.css";

interface Props {
  message: Message;
}

export function MessageBubble({ message }: Props) {
  const isUser = message.role === "user";

  return (
    <div
      className={`${styles.messageContainer} ${isUser ? styles.messageContainerUser : styles.messageContainerAssistant}`}
    >
      {!isUser && <Avatar label="A" variant="assistant" />}

      <div
        className={`${styles.bubbleWrapper} ${isUser ? styles.bubbleWrapperUser : styles.bubbleWrapperAssistant}`}
      >
        <div
          className={`${styles.bubble} ${isUser ? styles.bubbleUser : styles.bubbleAssistant}`}
        >
          {message.content}
        </div>

        <MessageMeta message={message} isUser={isUser} />
      </div>

      {isUser && <Avatar label="U" variant="user" />}
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

interface AvatarProps {
  label: string;
  variant: "user" | "assistant";
}

function Avatar({ label, variant }: AvatarProps) {
  return (
    <div
      className={`${styles.avatar} ${variant === "user" ? styles.avatarUser : styles.avatarAssistant}`}
    >
      {label}
    </div>
  );
}

interface MetaProps {
  message: Message;
  isUser: boolean;
}

function MessageMeta({ message, isUser }: MetaProps) {
  return (
    <div className={styles.meta}>
      {message.source && (
        <>
          <span className={styles.metaSource}>{message.source}</span>
          <span className={styles.metaDot}>·</span>
        </>
      )}
      {!isUser && (
        <>
          <span className={styles.metaAssistant}>Assistant</span>
          <span className={styles.metaDot}>·</span>
        </>
      )}
      <span>{formatTime(message.timestamp)}</span>
    </div>
  );
}