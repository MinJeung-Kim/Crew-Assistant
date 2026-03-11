import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneLight } from "react-syntax-highlighter/dist/esm/styles/prism";
import type { Message } from "../../types/chat";
import { formatTime } from "../../utils";
import styles from "./MessageBubble.module.css";

interface Props {
  message: Message;
}

const ALLOWED_URL_SCHEMES = new Set(["http", "https", "mailto", "tel"]);
const LANGUAGE_CLASS_PATTERN = /language-([\w-]+)/;

function normalizeMarkdownContent(content: string): string {
  const hasCompactRows = content.includes("||");
  const looksLikeTable = /\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+/.test(content);

  if (!hasCompactRows || !looksLikeTable) {
    return content;
  }

  return content.replace(/\s*\|\|\s*/g, "\n");
}

function getSafeUrl(url: string | undefined): string | undefined {
  if (!url) return undefined;

  const trimmed = url.trim();
  if (!trimmed || trimmed.startsWith("//")) {
    return undefined;
  }

  const hasScheme = /^[a-zA-Z][a-zA-Z\d+.-]*:/.test(trimmed);
  if (!hasScheme) {
    return trimmed;
  }

  const scheme = trimmed.slice(0, trimmed.indexOf(":")).toLowerCase();
  return ALLOWED_URL_SCHEMES.has(scheme) ? trimmed : undefined;
}

const markdownComponents: Components = {
  code({ className, children, ...props }) {
    const match = LANGUAGE_CLASS_PATTERN.exec(className || "");
    const codeString = String(children).replace(/\n$/, "");
    const isCodeBlock = Boolean(match) || codeString.includes("\n");
    const language = match?.[1];

    if (isCodeBlock) {
      return (
        <div className={styles.codeBlock}>
          <div className={styles.codeHeader}>
            <span className={styles.codeLang}>{language ?? "text"}</span>
          </div>
          <SyntaxHighlighter
            style={oneLight}
            language={language}
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
    const safeHref = getSafeUrl(href);
    if (!safeHref) {
      return <span className={styles.unsafeLink}>{children}</span>;
    }

    return (
      <a href={safeHref} target="_blank" rel="noreferrer noopener" {...props}>
        {children}
      </a>
    );
  },
  img({ src, alt, ...props }) {
    const safeSrc = getSafeUrl(src);
    if (!safeSrc) {
      return <span className={styles.blockedMedia}>[blocked image]</span>;
    }

    return (
      <img
        src={safeSrc}
        alt={alt ?? "markdown image"}
        loading="lazy"
        referrerPolicy="no-referrer"
        {...props}
      />
    );
  },
};

export function MessageBubble({ message }: Props) {
  const isUser = message.role === "user";
  const markdownContent = normalizeMarkdownContent(message.content);

  return (
    <div
      className={`${styles.messageContainer} ${isUser ? styles.messageContainerUser : styles.messageContainerAssistant}`}
    >
      <div
        className={`${styles.messageRow} ${isUser ? styles.messageRowUser : styles.messageRowAssistant}`}
      >
        {!isUser && <Avatar label="A" variant="assistant" />}

        <div
          className={`${styles.bubble} ${isUser ? styles.bubbleUser : styles.bubbleAssistant}`}
        >
          <div className={styles.markdown}>
            <Markdown
              remarkPlugins={[remarkGfm]}
              skipHtml
              components={markdownComponents}
            >
              {markdownContent}
            </Markdown>
          </div>
        </div>

        {isUser && <Avatar label="U" variant="user" />}
      </div>

      <MessageMeta message={message} isUser={isUser} />
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
    <div className={`${styles.meta} ${isUser ? styles.metaUser : styles.metaAssistant}`}>
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