import { useEffect, useRef } from "react";
import type { Message } from "../../types/chat";
import { MessageBubble } from "./MessageBubble"; 
import { TypingIndicator } from "./TypingIndicator";
import styles from "./MessageList.module.css";

interface Props {
  messages: Message[];
  isLoading: boolean;
  onTranslateMessage?: (id: string, translatedContent: string, showTranslated: boolean) => void;
}

export function MessageList({ messages, isLoading, onTranslateMessage }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className={styles.messageList}>
      {messages.map((msg) => (
        <MessageBubble
          key={msg.id}
          message={msg}
          onTranslate={(translatedContent, showTranslated) =>
            onTranslateMessage?.(msg.id, translatedContent, showTranslated)
          }
        />
      ))}
      {isLoading && <TypingIndicator />}
      <div ref={bottomRef} />
    </div>
  );
}