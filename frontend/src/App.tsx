import { useEffect, useReducer } from "react";
import { api, approveStream, chatStream } from "./api";
import ChatPanel from "./components/ChatPanel";
import Timeline from "./components/Timeline";
import ApprovalPanel from "./components/ApprovalPanel";
import ThreadSidebar from "./components/ThreadSidebar";
import ReplayDrawer from "./components/ReplayDrawer";
import type { InterruptPayload, Msg, Stats, Step, ThreadDetail, ThreadSummary, Customer } from "./types";

interface State {
  threads: ThreadSummary[];
  customers: Customer[];
  customerId: string;
  activeId: string | null;
  messages: Msg[];
  steps: Step[];
  tokens: string;
  interrupt: InterruptPayload | null;
  busy: boolean;
  status: "idle" | "streaming" | "awaiting" | "done";
  feedbackGiven: boolean;
  replayFor: string | null;
  stats: Stats | null;
}

const initial: State = {
  threads: [], customers: [], customerId: "cus_001", activeId: null,
  messages: [], steps: [], tokens: "", interrupt: null, busy: false,
  status: "idle", feedbackGiven: false, replayFor: null, stats: null,
};

type Action =
  | { type: "meta"; threads?: ThreadSummary[]; customers?: Customer[]; stats?: Stats }
  | { type: "customer"; id: string }
  | { type: "new" }
  | { type: "user"; text: string }
  | { type: "sse"; event: string; data: any }
  | { type: "load"; detail: ThreadDetail }
  | { type: "replay"; threadId: string | null }
  | { type: "feedbackDone" };

function reducer(s: State, a: Action): State {
  switch (a.type) {
    case "meta":
      return {
        ...s,
        threads: a.threads ?? s.threads,
        customers: a.customers ?? s.customers,
        stats: a.stats ?? s.stats,
        customerId: s.customers.length ? s.customerId : s.customerId,
      };
    case "customer":
      return { ...s, customerId: a.id };
    case "new":
      return { ...s, activeId: null, messages: [], steps: [], tokens: "", interrupt: null,
               status: "idle", feedbackGiven: false };
    case "user":
      return { ...s, messages: [...s.messages, { role: "user", content: a.text }],
               busy: true, status: "streaming", interrupt: null };
    case "sse": {
      const d = a.data;
      switch (a.event) {
        case "start":
        case "resume":
          return { ...s, activeId: d.thread_id, busy: true, status: "streaming", interrupt: null };
        case "step":
          return { ...s, steps: [...s.steps, { label: d.label, detail: d.detail, ts: new Date().toISOString() }] };
        case "token":
          return { ...s, tokens: s.tokens + d.text };
        case "interrupt":
          return { ...s, interrupt: d.payload, busy: false, status: "awaiting" };
        case "done":
          return { ...s, messages: [...s.messages, { role: "assistant", content: d.final_reply }],
                   tokens: "", busy: false, status: "done", interrupt: null, feedbackGiven: false };
        default:
          return s;
      }
    }
    case "load": {
      const d = a.detail;
      const steps: Step[] = [];
      let feedbackGiven = false;
      for (const ev of d.events) {
        if (ev.kind === "step") steps.push({ label: ev.payload.label, detail: ev.payload.detail, ts: ev.ts });
        else if (ev.kind === "action") steps.push({ label: "action_executed", detail: ev.payload });
        else if (ev.kind === "escalation") steps.push({ label: "escalated", detail: ev.payload });
        else if (ev.kind === "interrupt") steps.push({ label: "awaiting_approval", detail: ev.payload });
        else if (ev.kind === "resume") steps.push({ label: ev.payload.approved ? "action_approved" : "action_rejected", detail: ev.payload });
        else if (ev.kind === "feedback") feedbackGiven = true;
      }
      return { ...s, activeId: d.thread.thread_id, messages: d.messages, steps,
               interrupt: d.pending_interrupt, tokens: "",
               status: d.pending_interrupt ? "awaiting" : "idle", feedbackGiven };
    }
    case "replay":
      return { ...s, replayFor: a.threadId };
    case "feedbackDone":
      return { ...s, feedbackGiven: true };
    default:
      return s;
  }
}

export default function App() {
  const [s, dispatch] = useReducer(reducer, initial);

  const refresh = async () => {
    const [threads, stats] = await Promise.all([api.threads(), api.stats()]);
    dispatch({ type: "meta", threads, stats });
  };

  useEffect(() => {
    (async () => {
      const [threads, customers, stats] = await Promise.all([api.threads(), api.customers(), api.stats()]);
      dispatch({ type: "meta", threads, customers, stats });
    })();
  }, []);

  const send = async (text: string) => {
    dispatch({ type: "user", text });
    for await (const ev of chatStream({ thread_id: s.activeId, customer_id: s.customerId, message: text }))
      dispatch({ type: "sse", event: ev.event, data: ev.data });
    refresh();
  };

  const decide = async (approved: boolean, feedback: string) => {
    if (!s.activeId) return;
    dispatch({ type: "sse", event: "resume", data: { thread_id: s.activeId } });
    for await (const ev of approveStream(s.activeId, approved, feedback))
      dispatch({ type: "sse", event: ev.event, data: ev.data });
    refresh();
  };

  const select = async (id: string) => dispatch({ type: "load", detail: await api.thread(id) });

  const fork = async (checkpointId: string) => {
    const { thread_id } = await api.fork(s.replayFor!, checkpointId);
    dispatch({ type: "replay", threadId: null });
    await select(thread_id);
    refresh();
  };

  const rate = async (rating: 1 | -1) => {
    if (!s.activeId) return;
    await api.feedback(s.activeId, rating);
    dispatch({ type: "feedbackDone" });
  };

  return (
    <div className="app">
      <ThreadSidebar
        threads={s.threads} activeId={s.activeId} customers={s.customers}
        customerId={s.customerId} stats={s.stats}
        onSelect={select} onNew={() => dispatch({ type: "new" })}
        onCustomer={(id) => dispatch({ type: "customer", id })}
        onReplay={(id) => dispatch({ type: "replay", threadId: id })}
      />
      <ChatPanel
        messages={s.messages} tokens={s.tokens} busy={s.busy || s.status === "awaiting"}
        onSend={send}
      />
      <aside className="rail">
        <Timeline steps={s.steps} />
        {s.interrupt && <ApprovalPanel payload={s.interrupt} busy={s.busy} onDecision={decide} />}
        {s.status === "done" && !s.interrupt && s.activeId && (
          <FeedbackButtons given={s.feedbackGiven} onRate={rate} />
        )}
      </aside>
      {s.replayFor && (
        <ReplayDrawer threadId={s.replayFor} onClose={() => dispatch({ type: "replay", threadId: null })}
          onFork={fork} />
      )}
    </div>
  );
}