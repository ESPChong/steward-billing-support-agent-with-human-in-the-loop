import type { Step } from "../types";

const LABELS: Record<string, string> = {
  classified: "Intent classified",
  tool_call: "Tool call",
  tool_result: "Tool result",
  action_requested: "Action requested — approval needed",
  action_approved: "Approved by reviewer",
  action_rejected: "Rejected by reviewer — revising",
  action_executed: "Action executed",
  draft_ready: "Reply drafted",
  draft_approved: "Reply approved",
  draft_rejected: "Reply sent back for revision",
  escalated: "Escalated to human",
  escalation_requested: "Escalation requested",
  awaiting_approval: "Paused for approval",
};

export default function Timeline({ steps }: { steps: Step[] }) {
  return (
    <section className="timeline card">
      <h3>Agent steps</h3>
      {steps.length === 0 && <p className="muted">Live agent activity will appear here.</p>}
      <ul>
        {steps.map((s, i) => (
          <li key={i} className={s.label}>
            <span className="dot" />
            <div>
              <div className="lbl">{LABELS[s.label] ?? s.label}</div>
              {s.detail?.tool && (
                <code className="detail" data-testid="step-tool">
                  {s.detail.tool}
                  {s.detail.args ? " " + JSON.stringify(s.detail.args) : ""}
                </code>
              )}
              {s.label === "classified" && s.detail && (
                <div className="detail">
                  {s.detail.intent} · conf {Number(s.detail.confidence ?? 0).toFixed(2)} · {s.detail.sentiment}
                </div>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}