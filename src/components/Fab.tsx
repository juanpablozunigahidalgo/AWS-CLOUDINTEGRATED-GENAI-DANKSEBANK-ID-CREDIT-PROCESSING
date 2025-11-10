import styles from "./Fab.module.css";

export default function Fab({ onClick }: { onClick: () => void }) {
  return (
    <button className={styles.fab} onClick={onClick} aria-label="Open chat">💬</button>
  );
}
