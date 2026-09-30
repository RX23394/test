import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ChatStreamError,
  parseSseBlock,
  streamChatMessage,
  type ChatCitation,
} from "@/api/chat";

/** Build a fetch response whose body arrives in separate stream chunks. */
function createStreamResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller): void {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
  return new Response(body, { status: 200 });
}

describe("chat SSE API", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("posts with cookies and dispatches token and citation events", async () => {
    const citations: ChatCitation[] = [
      {
        id: "S1",
        document: "Cisco OSPF.pdf",
        page: 12,
        section: "Area",
        content: "source",
      },
    ];
    vi.mocked(fetch).mockResolvedValue(
      createStreamResponse([
        'event: token\ndata: {"status":"ok","data":"OSPF "}\n\n',
        'event: token\ndata: {"status":"ok","data":"answer"}\n\n',
        `event: citation\ndata: ${JSON.stringify({ status: "ok", data: citations })}\n\n`,
        'event: done\ndata: {"status":"ok"}\n\n',
      ]),
    );
    const onToken = vi.fn();
    const onCitation = vi.fn();
    const controller = new AbortController();

    await streamChatMessage(
      { conversation_id: 1, message: "What is OSPF?" },
      { onToken, onCitation },
      controller.signal,
    );

    expect(fetch).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/api/chat/stream",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_id: 1,
          message: "What is OSPF?",
        }),
        signal: controller.signal,
      }),
    );
    expect(onToken.mock.calls).toEqual([["OSPF "], ["answer"]]);
    expect(onCitation).toHaveBeenCalledWith(citations);
  });

  it("throws the server message from an SSE error event", async () => {
    vi.mocked(fetch).mockResolvedValue(
      createStreamResponse([
        'event: error\ndata: {"status":"error","message":"Token limit reached"}\n\n',
      ]),
    );

    await expect(
      streamChatMessage(
        { conversation_id: 1, message: "question" },
        { onToken: vi.fn(), onCitation: vi.fn() },
        new AbortController().signal,
      ),
    ).rejects.toEqual(new ChatStreamError("Token limit reached"));
  });

  it("rejects malformed event JSON and HTTP failures", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      createStreamResponse(["event: token\ndata: not-json\n\n"]),
    );
    await expect(
      streamChatMessage(
        { conversation_id: 1, message: "question" },
        { onToken: vi.fn(), onCitation: vi.fn() },
        new AbortController().signal,
      ),
    ).rejects.toThrow("Invalid streaming event data");

    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ status: "error", message: "Unauthorized" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await expect(
      streamChatMessage(
        { conversation_id: 1, message: "question" },
        { onToken: vi.fn(), onCitation: vi.fn() },
        new AbortController().signal,
      ),
    ).rejects.toThrow("Unauthorized");
  });

  it("parses CRLF blocks and joins repeated data fields", () => {
    expect(parseSseBlock("event: token\r\ndata: first\r\ndata: second")).toEqual({
      event: "token",
      data: "first\nsecond",
    });
  });
});
