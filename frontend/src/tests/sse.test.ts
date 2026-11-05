import { describe, expect, it, vi } from "vitest";
import { streamSSE } from "../api";

function sseResponse(chunks: string[]) {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(c) { chunks.forEach((ch) => c.enqueue(encoder.encode(ch))); c.close(); },
  });
  return { ok: true, body: stream } as Response;
}

describe("streamSSE", () => {
  it("parses events, including ones split across chunks", async () => {
    vi.stubGlobal("fetch", vi.fn(async () =>
      sseResponse([
        'event: start\ndata: {"thread_id":"t1"}\n\n',
        'event: ste', 'p\ndata: {"thread_id":"t1","label":"classified"}\n\n',
        'event: done\ndata: {"thread_id":"t1","final_reply":"ok"}\n\n',
      ])));
    const seen: string[] = [];
    for await (const ev of streamSSE("/api/chat/stream", { thread_id: "t1", customer_id: "c1", message: "hello" })) seen.push(ev.event);
    expect(seen).toEqual(["start", "step", "done"]);
  });
});