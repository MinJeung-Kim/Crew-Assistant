import styles from "./ErrorBanner.module.css";

interface Props {
  message: string;
  onClose: () => void;
}

export function ErrorBanner({ message, onClose }: Props) {
  return (
    <div className={styles.banner}>
      <span>{message}</span>
      <button onClick={onClose} className={styles.closeButton}>
        ×
      </button>
    </div>
  );
}