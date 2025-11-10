import { useState } from "react";
import ChatLauncher from "../components/ChatLauncher";
import AgentChatWidget from "../components/AgentChatWidget";
import styles from "./Home.module.css";

export default function Home() {
  const [open, setOpen] = useState(false);

  return (
    <main className={styles.container}>
      <div className={styles.heroCard}>
        <h1 className={styles.title}>Welcome</h1>
        <p className={styles.subtitle}>
          AWS Cloud Bedrock Agent for Danske Bank onboarding and credit journey.
        </p>

        <p className={styles.info}>
          <strong>Juan Pablo Rafael Zúñiga Hidalgo</strong> ·{" "}
          <a
            className={styles.link}
            href="mailto:juanpablo.zunigah@gmail.com"
          >
            juanpablo.zunigah@gmail.com
          </a>
          +46729971641
        </p>

        <a
          className={styles.link}
          href="https://se.linkedin.com/in/jpzuniga/en"
          target="_blank"
          rel="noreferrer"
        >
          https://se.linkedin.com/in/jpzuniga/en
        </a>

        <p className={styles.footerNote}>
          Building modern AI-powered onboarding solutions with AWS Bedrock.
        </p>
      </div>

      {!open && <ChatLauncher onOpen={() => setOpen(true)} />}
      <AgentChatWidget open={open} onClose={() => setOpen(false)} />
    </main>
  );
}
