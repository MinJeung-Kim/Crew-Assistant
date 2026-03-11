import styles from "./TypingIndicator.module.css";

export function TypingIndicator() {
  return (
    <div className={styles.container}>
      <div className={styles.avatar}>A</div>
      <div className={styles.bubble}>
        {[0, 1, 2].map((i) => (
          <div key={i} className={styles.dot} />
        ))}
      </div>
    </div>
  );
}