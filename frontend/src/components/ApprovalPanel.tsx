import { useState } from "react";
import type { InterruptPayload } from "../types";

export default function ApprovalPanel({ payload, busy, onDecision }: {
  payload: InterruptPayload; busy: boolean;
  onDecision: (approved: boolean, feedback: string) => void;
}) {
  const [feedback, setFeedback] = useState("");
  const [rejecting, setRejecting] = useState(false);
  const submit = (approved: boolean) => {
    if (!busy) onDecision(approved, feedback);
  };
  return (
    <section className="approval card" data-testid="approval-panel">
      <h3>{payload.kind === "action" ? "Action needs approval" : "Reply needs review"}</h3>
      {payload.kind === "action" ? (
        <>
          <div className="tool" data-testid="approval-tool">
            <strong>{payload.action?.tool}</strong>
            <pre>{JSON.stringify(payload.action?.args, null, 2)}</pre>
          </div>
          {payload.policy_ref && <div className="chip">Policy: {payload.policy_ref}</div>}
        </>
      ) : (
        <blockquote className="draft">{payload.draft}</blockquote>
      )}
      {payload.reasons?.length ? (
        <ul className="reasons">
          {payload.reasons.map((r, i) => <li key={i}>{r}</li>)}
        </ul>
      ) : null}
      {rejecting && (
        <textarea
          className="feedback-input"
          placeholder="Feedback for the agent — it will revise (max 2 rejections, then escalate)"
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
        />
      )}
      <div className="approval-actions">
        {!rejecting ? (
          <>
            <button className="primary" data-testid="approve-btn" disabled={busy}
              onClick={() => submit(true)}>Approve</button>
            <button className="ghost" disabled={busy} onClick={() => setRejecting(true)}>Request changes</button>
          </>
        ) : (
          <>
            <button className="danger" data-testid="reject-btn" disabled={busy}
              onClick={() => { submit(false); setRejecting(false); }}>Send back</button>
            <button className="ghost" disabled={busy} onClick={() => setRejecting(false)}>Cancel</button>
          </>
        )}
      </div>
    </section>
  );
}