import apiClient from "@/api/api";
import type { ResponseModel } from "@/api/auth";

export interface ChatCitation {
  id: string;
  document: string;
  page: number | null;
  section: string | null;
  content: string;
}

export interface ChatStreamRequest {
  conversation_id: number;
  message: string;
}

export interface ChatStreamHandlers {
  onToken: (token: string) => void;
  onCitation: (citations: ChatCitation[]) => void;
}

interface ParsedSseEvent {
  event: string;
  data: string;
}

export class ChatStreamError extends Error {
  /** Create a stable client-side streaming failure. */
  constructor(message: string) {
    super(message);
    this.name = "ChatStreamError";
  }
}

/** Open a POST SSE connection and dispatch events until done. */
export async function streamChatMessage(
  payload: ChatStreamRequest,
  handlers: ChatStreamHandlers,
  signal: AbortSignal,
): Promise<void> {
  const baseUrl = String(apiClient.defaults.baseURL ?? "").replace(/\/$/, "");
  const response = await fetch(`${baseUrl}/api/chat/stream`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  if (!response.ok) {
    throw new ChatStreamError(await readHttpError(response));
  }
  if (response.body === null) {
    throw new ChatStreamError("Streaming response body is unavailable");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        buffer += decoder.decode();
        if (buffer.trim()) {
          dispatchSseEvent(parseSseBlock(buffer), handlers);
        }
        return;
      }

      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split(/\r?\n\r?\n/);
      buffer = blocks.pop() ?? "";
      for (const block of blocks) {
        if (!block.trim()) {
          continue;
        }
        const event = parseSseBlock(block);
        if (event.event === "done") {
          return;
        }
        dispatchSseEvent(event, handlers);
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/** Parse one standard SSE block into its event name and joined data. */
export function parseSseBlock(block: string): ParsedSseEvent {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }
  return { event, data: dataLines.join("\n") };
}

/** Dispatch a parsed token, citation, error, or completion event. */
function dispatchSseEvent(
  event: ParsedSseEvent,
  handlers: ChatStreamHandlers,
): void {
  if (event.event === "done") {
    return;
  }

  let payload: ResponseModel<unknown>;
  try {
    payload = JSON.parse(event.data) as ResponseModel<unknown>;
  } catch {
    throw new ChatStreamError("Invalid streaming event data");
  }

  if (event.event === "error" || payload.status === "error") {
    throw new ChatStreamError(payload.message ?? "Answer generation failed");
  }
  if (event.event === "token") {
    if (typeof payload.data !== "string") {
      throw new ChatStreamError("Invalid token event data");
    }
    handlers.onToken(payload.data);
    return;
  }
  if (event.event === "citation") {
    handlers.onCitation(payload.data as ChatCitation[]);
  }
}

/** Read the uniform HTTP error envelope without leaking parse failures. */
async function readHttpError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as ResponseModel<unknown>;
    return payload.message ?? `Chat request failed (${response.status})`;
  } catch {
    return `Chat request failed (${response.status})`;
  }
}
