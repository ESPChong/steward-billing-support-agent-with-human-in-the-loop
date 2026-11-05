import type { Customer, Stats, ThreadSummary } from "../types";

export default function ThreadSidebar({ threads, activeId, customers, customerId, stats,
  onSelect, onNew, onCustomer, onReplay }: {
  threads: ThreadSummary[]; activeId: string | null; customers: Customer[];
  customerId: string; stats: Stats | null;
  onSelect: (id: string) => void; onNew: () => void;
  onCustomer: (id: string) => void; onReplay: (id: string) => void;
}) {
  return (
    <nav className="sidebar">
      <div className="brand">
        <h1>Steward</h1>
        <p className="tagline">supervised billing agent</p>
      </div>
      <button className="new-chat" onClick={onNew}>＋ New conversation</button>
      <label className="picker">
        Customer
        <select value={customerId} onChange={(e) => onCustomer(e.target.value)}>
          {customers.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name} ({c.tier}, {c.status})
            </option>
          ))}
        </select>
      </label>
      <ul className="thread-list">
        {threads.map((t) => (
          <li key={t.thread_id} className={t.thread_id === activeId ? "active" : ""}>
            <button className="thread-title" onClick={() => onSelect(t.thread_id)}>
              {t.title || "(untitled)"}
            </button>
            <button className="replay-btn" title="Time-travel / fork"
              onClick={() => onReplay(t.thread_id)}>↺</button>
          </li>
        ))}
      </ul>
      {stats && (
        <footer className="stats">
          <div><b>{stats.threads}</b> threads</div>
          <div><b>{stats.refunds}</b> refunds</div>
          <div><b>{stats.escalations}</b> escalations</div>
          <div>👍 {stats.feedback_up} · 👎 {stats.feedback_down}</div>
        </footer>
      )}
    </nav>
  );
}