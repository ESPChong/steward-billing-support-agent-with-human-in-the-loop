import type { 
  Checkpoint, 
  Stats, 
  ThreadDetail, 
  ThreadSummary, 
  Customer, 
  StreamRequestBody
} from "./types";

const BASE = "/api";

/** POST + SSE reader (EventSource is GET-only, so we parse the stream by hand). */
export async function* streamSSE(url: string, body: StreamRequestBody): AsyncGenerator<{ event: string; data: any }> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) throw new Error(`SSE request failed: ${res.status}`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      let event = "message";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (data && event !== "message") yield { event, data: JSON.parse(data) };
    }
  }
}

export const chatStream = (body: { thread_id: string | null; customer_id: string; message: string }) =>
  streamSSE(`${BASE}/chat/stream`, body);

export const approveStream = (thread_id: string, approved: boolean, feedback: string) =>
  streamSSE(`${BASE}/threads/${thread_id}/approve`, { approved, feedback });

const json = async (r: Response) => {
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
};

export const api = {
  threads: (): Promise<ThreadSummary[]> => fetch(`${BASE}/threads`).then(json),
  thread: (id: string): Promise<ThreadDetail> => fetch(`${BASE}/threads/${id}`).then(json),
  customers: (): Promise<Customer[]> => fetch(`${BASE}/customers`).then(json),
  stats: (): Promise<Stats> => fetch(`${BASE}/stats`).then(json),
  checkpoints: (id: string): Promise<Checkpoint[]> =>
    fetch(`${BASE}/threads/${id}/checkpoints`).then(json),
  fork: (id: string, checkpoint_id: string): Promise<{ thread_id: string }> =>
    fetch(`${BASE}/threads/${id}/fork`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ checkpoint_id }),
    }).then(json),
  feedback: (id: string, rating: 1 | -1) =>
    fetch(`${BASE}/threads/${id}/feedback`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rating }),
    }).then(json),
};