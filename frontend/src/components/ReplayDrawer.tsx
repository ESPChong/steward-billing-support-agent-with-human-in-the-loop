import { useEffect, useState } from "react";
import { api } from "../api";
import type { Checkpoint } from "../types";

export default function ReplayDrawer({ threadId, onClose, onFork }: {
  threadId: string; onClose: () => void; onFork: (checkpointId: string) => void;
}) {
  const [cps, setCps] = useState<Checkpoint[]>([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api.checkpoints(threadId).then(setCps).catch(() => setCps([]));
  }, [threadId]);
  return (
    <div className="drawer-overlay" onClick={onClose}>
      <div className="drawer card" onClick={(e) => e.stopPropagation()}>
        <h3>Replay / time travel</h3>
        <p className="muted">
          Fork the conversation from any checkpoint. The branch re-runs under a new thread id —
          approve differently and watch the path diverge.
        </p>
        {cps.length === 0 && <p className="muted">No checkpoints yet.</p>}
        <ul>
          {cps.map((c) => (
            <li key={c.checkpoint_id}>
              <div>
                <div>step {c.step ?? "?"}</div>
                <code className="muted">{c.checkpoint_id?.slice(0, 16)}…</code>
              </div>
              <button
                disabled={busy || !c.checkpoint_id}
                onClick={async () => { setBusy(true); onFork(c.checkpoint_id!); }}>
                Fork here
              </button>
            </li>
          ))}
        </ul>
        <button className="ghost" onClick={onClose}>Close</button>
      </div>
    </div>
  );
}