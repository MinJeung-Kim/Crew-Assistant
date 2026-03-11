import {
  IconRefresh, IconStop, IconExpand, IconClock, IconMenu,
} from "../icons";
import styles from "./Header.module.css";

interface Props {
  error: string | null;
  onToggleSidebar: () => void;
  onNewSession: () => void;
  onDownload: () => void;
  canDownload: boolean;
}

export function Header({
  error,
  onToggleSidebar,
  onNewSession,
  onDownload,
  canDownload,
}: Props) {
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

        <button
          type="button"
          onClick={onDownload}
          disabled={!canDownload}
          className={`${styles.actionButton} ${styles.downloadButton}`}
        >
          Download
        </button>

        {[<IconRefresh />, <IconStop />, <IconExpand />, <IconClock />].map(
          (icon, i) => (
            <button key={i} className={styles.iconButton}>
              {icon}
            </button>
          )
        )}
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