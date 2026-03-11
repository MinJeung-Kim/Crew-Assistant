import { useEffect, useMemo, useState } from "react";
import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneLight } from "react-syntax-highlighter/dist/esm/styles/prism";
import type { Message } from "../../types/chat";
import { API_BASE } from "../../constants";
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
  const [translatedContent, setTranslatedContent] = useState<string | null>(null);
  const [showTranslated, setShowTranslated] = useState(false);
  const [isTranslating, setIsTranslating] = useState(false);
  const [translationError, setTranslationError] = useState<string | null>(null);

  const canTranslate = useMemo(
    () => !isUser && /[A-Za-z]/.test(message.content),
    [isUser, message.content]
  );

  const displayContent = showTranslated && translatedContent
    ? translatedContent
    : message.content;
  const markdownContent = normalizeMarkdownContent(displayContent);

  useEffect(() => {
    setTranslatedContent(null);
    setShowTranslated(false);
    setIsTranslating(false);
    setTranslationError(null);
  }, [message.id, message.content]);

  const handleTranslate = async () => {
    if (!canTranslate || isTranslating) return;

    if (translatedContent) {
      setShowTranslated((prev) => !prev);
      return;
    }

    setIsTranslating(true);
    setTranslationError(null);

    try {
      const res = await fetch(`${API_BASE}/translate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: message.content,
          target_language: "ko",
          preserve_markdown: true,
        }),
      });

      const payload = (await res.json().catch(() => ({}))) as {
        translated_text?: unknown;
        detail?: unknown;
      };

      if (!res.ok) {
        const detail =
          typeof payload.detail === "string"
            ? payload.detail
            : `HTTP ${res.status}`;
        throw new Error(detail);
      }

      const translatedText =
        typeof payload.translated_text === "string"
          ? payload.translated_text.trim()
          : "";
      if (!translatedText) {
        throw new Error("번역 결과가 비어 있습니다.");
      }

      setTranslatedContent(translatedText);
      setShowTranslated(true);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setTranslationError(msg);
    } finally {
      setIsTranslating(false);
    }
  };

  const translateButtonLabel = isTranslating
    ? "번역 중..."
    : showTranslated
      ? "원문 보기"
      : translatedContent
        ? "한국어 보기"
        : "한국어 번역";

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

      {!isUser && canTranslate && (
        <div className={styles.translateActions}>
          <button
            type="button"
            onClick={handleTranslate}
            className={styles.translateButton}
            disabled={isTranslating}
          >
            {translateButtonLabel}
          </button>
          {translationError && (
            <span className={styles.translationError}>{translationError}</span>
          )}
        </div>
      )}
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