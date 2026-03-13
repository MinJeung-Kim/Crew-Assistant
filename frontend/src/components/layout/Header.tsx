import { useRef, useState, useEffect, type ChangeEvent } from "react";
import {
  IconRefresh, IconStop, IconExpand, IconClock, IconMenu,
} from "../icons";
import type { DownloadFormat } from "../../utils/chatExport";
import styles from "./Header.module.css";

const HEADER_ICON_ACTIONS = [
  { id: "refresh", label: "Refresh", icon: <IconRefresh /> },
  { id: "stop", label: "Stop", icon: <IconStop /> },
  { id: "expand", label: "Expand", icon: <IconExpand /> },
  { id: "history", label: "History", icon: <IconClock /> },
] as const;

const DOWNLOAD_FORMATS: { format: DownloadFormat; label: string }[] = [
  { format: "md", label: "Markdown (.md)" },
  { format: "pdf", label: "PDF (.pdf)" },
  { format: "doc", label: "Word (.doc)" },
];

interface Props {
  error: string | null;
  onToggleSidebar: () => void;
  onNewSession: () => void;
  onDownload: (format: DownloadFormat) => void;
  canDownload: boolean;
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
}

export function Header({
  error,
  onToggleSidebar,
  onNewSession,
  onDownload,
  canDownload,
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
}: Props) {
  const uploadInputRef = useRef<HTMLInputElement>(null);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const downloadRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!dropdownOpen) return;
    const handler = (e: MouseEvent) => {
      if (!downloadRef.current?.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [dropdownOpen]);

  const handleUploadClick = () => {
    uploadInputRef.current?.click();
  };

  const handleUploadChange = (event: ChangeEvent<HTMLInputElement>) => {
    const selectedFile = event.target.files?.[0];
    if (!selectedFile) return;
    onUploadKnowledge(selectedFile);
    event.target.value = "";
  };

  const handleIconAction = (actionId: (typeof HEADER_ICON_ACTIONS)[number]["id"]) => {
    if (actionId === "refresh") {
      onRefresh();
      return;
    }

    if (actionId === "stop") {
      onStop();
      return;
    }

    if (actionId === "expand") {
      onToggleFullscreen();
      return;
    }

    onHistory();
  };

  const isActionDisabled = (actionId: (typeof HEADER_ICON_ACTIONS)[number]["id"]) => {
    if (actionId === "refresh") return !canRefresh;
    if (actionId === "stop") return !canStop;
    if (actionId === "history") return !canHistory;
    return false;
  };

  const getActionLabel = (actionId: (typeof HEADER_ICON_ACTIONS)[number]["id"], fallback: string) => {
    if (actionId === "expand") {
      return isFullscreen ? "Exit Fullscreen" : "Enter Fullscreen";
    }
    return fallback;
  };

  return (
    <div className={styles.header}>
      {/* Left */}
      <div className={styles.left}>
        <button
          onClick={onToggleSidebar}
          className={styles.menuButton}
        >
          <IconMenu />
        </button>
        <div>
          <div className={styles.title}>Chat</div>
          <div className={styles.subtitle}>
            Direct gateway chat session for quick interventions.
          </div>
        </div>
      </div>

      {/* Right */}
      <div className={styles.right}>
        {error && <ErrorBadge message={error} />}

        <button
          type="button"
          onClick={onNewSession}
          className={styles.actionButton}
        >
          New session
        </button>

        <div ref={downloadRef} className={styles.downloadWrapper}>
          <button
            type="button"
            disabled={!canDownload}
            onClick={() => setDropdownOpen((o) => !o)}
            className={`${styles.actionButton} ${styles.downloadButton}`}
          >
            Download
            <span className={styles.chevron}>{dropdownOpen ? "▴" : "▾"}</span>
          </button>
          {dropdownOpen && (
            <div className={styles.downloadDropdown}>
              {DOWNLOAD_FORMATS.map(({ format, label }) => (
                <button
                  key={format}
                  type="button"
                  className={styles.dropdownItem}
                  onClick={() => {
                    onDownload(format);
                    setDropdownOpen(false);
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
          )}
        </div>

        <button
          type="button"
          onClick={handleUploadClick}
          disabled={isUploadingKnowledge}
          className={`${styles.actionButton} ${styles.uploadButton}`}
        >
          {isUploadingKnowledge ? "Uploading..." : "Upload File"}
        </button>

        <input
          ref={uploadInputRef}
          type="file"
          accept=".txt,.md,.markdown,.pdf,.docx"
          className={styles.hiddenInput}
          onChange={handleUploadChange}
        />

        {HEADER_ICON_ACTIONS.map((action) => (
          <button
            key={action.id}
            type="button"
            className={styles.iconButton}
            onClick={() => handleIconAction(action.id)}
            disabled={isActionDisabled(action.id)}
            title={getActionLabel(action.id, action.label)}
            aria-label={getActionLabel(action.id, action.label)}
          >
            <span className={styles.iconGlyph}>{action.icon}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function ErrorBadge({ message }: { message: string }) {
  return (
    <div className={styles.errorBadge}>
      <div className={styles.errorDot} />
      {message}
    </div>
  );
}