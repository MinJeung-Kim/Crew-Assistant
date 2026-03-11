import { useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { IconSend } from "../icons";
import styles from "./ChatInput.module.css";

interface Props {
  isLoading: boolean;
  onSend: (text: string) => void;
  onNewSession: () => void;
}

export function ChatInput({ isLoading, onSend, onNewSession }: Props) {
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = () => {
    if (!input.trim() || isLoading) return;
    onSend(input.trim());
    setInput("");
    // 높이 초기화
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const canSend = input.trim() && !isLoading;

  return (
    <div className={styles.container}>
      <div className={styles.inputWrapper}>
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => {
            setInput(e.target.value);
            e.target.style.height = "auto";
            e.target.style.height =
              Math.min(e.target.scrollHeight, 120) + "px";
          }}
          onKeyDown={handleKeyDown}
          placeholder="예) 2026년 IT 트랜드 조사해서 보고서 형식으로 요약해줘"
          rows={1}
          className={styles.textarea}
        />
        <div className={styles.actions}>
          <button onClick={onNewSession} className={styles.newSessionButton}>
            New session
          </button>
          <button
            onClick={handleSend}
            disabled={!canSend}
            className={`${styles.sendButton} ${canSend ? styles.sendButtonEnabled : styles.sendButtonDisabled}`}
          >
            <IconSend />
            Send
          </button>
        </div>
      </div>
    </div>
  );
}