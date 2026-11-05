import { useState } from "react";
import type { Msg } from "../types";

export default function ChatPanel({ messages, tokens, busy, onSend }: {
  messages: Msg[]; tokens: string; busy: boolean; onSend: (text: string) => void;
}) {
  const [text, setText] = useState("");
  const submit = (e: React.SyntheticEvent) => {
    e.preventDefault();
    if (!text.trim() || busy) return;
    onSend(text.trim());
    setText("");
  };
  return (
    <main className="chat">
      <div className="messages" data-testid="messages">
        {messages.map((m, i) => (
          <div key={i} className={`bubble ${m.role}`}>{m.content}</div>
        ))}
        {tokens && <div className="bubble assistant streaming">{tokens}<span className="cursor" /></div>}
        {!messages.length && !tokens && (
          <div className="empty">
            <h2>Steward</h2>
            <p>A supervised billing support agent — it reads freely, drafts replies,
               and pauses for your approval before any write action.</p>
            <p className="hint">Try: “I think I was charged twice for my subscription this month.”</p>
          </div>
        )}
      </div>
      <form className="composer" onSubmit={submit}>
        <textarea
          value={text}
          placeholder={busy ? "Agent working…" : "Describe your billing issue"}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(e); }
          }}
        />
        <button type="submit" disabled={busy || !text.trim()}>Send</button>
      </form>
    </main>
  );
}