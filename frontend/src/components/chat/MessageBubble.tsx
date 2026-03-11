import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneLight } from "react-syntax-highlighter/dist/esm/styles/prism";
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
          <div className={styles.markdown}>
            <Markdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeRaw]}
              components={{
                code({ className, children, ...props }) {
                  const match = /language-([\w-]+)/.exec(className || "");
                  const codeString = String(children).replace(/\n$/, "");
                  const isCodeBlock = Boolean(match) || codeString.includes("\n");
                  const language = match?.[1] ?? "text";
                  
                  if (isCodeBlock) {
                    return (
                      <div className={styles.codeBlock}>
                        <div className={styles.codeHeader}>
                          <span className={styles.codeLang}>{language}</span>
                        </div>
                        <SyntaxHighlighter
                          style={oneLight}
                          language={match?.[1]}
                          PreTag="div"
                          wrapLongLines
                          customStyle={{
                            margin: 0,
                            borderRadius: "0 0 10px 10px",
                            fontSize: "13px",
                            background: "#f8fafc",
                          }}
                        >
                          {codeString}
                        </SyntaxHighlighter>
                      </div>
                    );
                  }
                  
                  return (
                    <code className={styles.inlineCode} {...props}>
                      {children}
                    </code>
                  );
                },
                table({ children }) {
                  return (
                    <div className={styles.tableWrapper}>
                      <table>{children}</table>
                    </div>
                  );
                },
                a({ href, children, ...props }) {
                  return (
                    <a href={href} target="_blank" rel="noreferrer noopener" {...props}>
                      {children}
                    </a>
                  );
                },
              }}
            >
              {message.content}
            </Markdown>
          </div>
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