import styles from "./ChatLauncher.module.css";
import chatPng from "./Ask.png"; // put any 64x64/128x128 png in /public

export default function ChatLauncher({ onOpen }: { onOpen: () => void }) {
  return (
    <button className={styles.fab} onClick={onOpen} aria-label="Open chat">
      <span className={styles.badge} />
      <img className={styles.icon} src={chatPng} alt="Chat" />
    </button>
  );
}
