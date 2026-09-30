import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import ElementPlus, { ElMessage, type MessageHandler } from "element-plus";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as chatApi from "@/api/chat";
import * as conversationsApi from "@/api/conversations";
import { useAuthStore } from "@/stores/auth";
import ChatView from "@/views/ChatView.vue";

vi.mock("@/api/chat", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/api/chat")>();
  return {
    ...original,
    streamChatMessage: vi.fn(),
  };
});

vi.mock("@/api/conversations", () => ({
  listConversations: vi.fn(),
  createConversation: vi.fn(),
  getConversation: vi.fn(),
  renameConversation: vi.fn(),
  deleteConversation: vi.fn(),
}));

/** Mount ChatView with an authenticated in-memory user. */
function mountChatView(): VueWrapper {
  const pinia = createPinia();
  setActivePinia(pinia);
  const authStore = useAuthStore();
  authStore.user = {
    id: 1,
    username: "network-admin",
    is_admin: true,
    is_active: true,
    created_at: "2026-07-16T00:00:00Z",
  };
  authStore.initialized = true;
  return mount(ChatView, {
    attachTo: document.body,
    global: { plugins: [pinia, ElementPlus] },
  });
}

/** Enter one question and click the enabled send button. */
async function submitQuestion(wrapper: VueWrapper, question: string): Promise<void> {
  await wrapper.find("textarea").setValue(question);
  const sendButton = wrapper
    .findAll("button")
    .find((button) => button.text().includes("\u53d1\u9001"));
  expect(sendButton).toBeDefined();
  await sendButton?.trigger("click");
}

describe("ChatView SSE", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(conversationsApi.listConversations).mockResolvedValue([
      {
        id: 1,
        title: "OSPF",
        created_at: "2026-07-16T00:00:00Z",
        updated_at: "2026-07-16T00:00:00Z",
      },
    ]);
    vi.mocked(conversationsApi.getConversation).mockResolvedValue({
      conversation: {
        id: 1,
        title: "OSPF",
        created_at: "2026-07-16T00:00:00Z",
        updated_at: "2026-07-16T00:00:00Z",
      },
      messages: [],
    });
  });

  afterEach(() => {
    document.body.innerHTML = "";
    vi.restoreAllMocks();
  });

  it("automatically loads persisted messages when a conversation is selected", async () => {
    vi.mocked(conversationsApi.getConversation).mockResolvedValue({
      conversation: {
        id: 1,
        title: "OSPF",
        created_at: "2026-07-16T00:00:00Z",
        updated_at: "2026-07-16T00:00:00Z",
      },
      messages: [
        {
          id: 7,
          role: "user",
          content: "Stored question",
          created_at: "2026-07-16T00:00:00Z",
        },
      ],
    });
    const wrapper = mountChatView();
    await flushPromises();

    expect(conversationsApi.getConversation).toHaveBeenCalledWith(1);
    expect(wrapper.text()).toContain("Stored question");
    wrapper.unmount();
  });

  it("appends streamed tokens, renders Markdown, and displays citations", async () => {
    let finishStream: () => void = () => undefined;
    vi.mocked(chatApi.streamChatMessage).mockImplementation(
      async (_payload, handlers): Promise<void> => {
        handlers.onToken("## OSPF\n\n");
        await new Promise<void>((resolve) => {
          finishStream = resolve;
        });
        handlers.onToken("**Link-state** protocol [S1].\n\n```python\narea = 0\n```");
        handlers.onCitation([
          {
            id: "S1",
            document: "Cisco OSPF.pdf",
            page: 12,
            section: "Area",
            content: "OSPF areas reduce link-state flooding.",
          },
        ]);
      },
    );
    const wrapper = mountChatView();
    const scroller = wrapper.find(".chat-scroll").element as HTMLElement;
    Object.defineProperty(scroller, "scrollHeight", {
      configurable: true,
      value: 900,
    });

    await flushPromises();
    await submitQuestion(wrapper, "What is OSPF?");
    await flushPromises();

    expect(chatApi.streamChatMessage).toHaveBeenCalledWith(
      { conversation_id: 1, message: "What is OSPF?" },
      expect.objectContaining({
        onToken: expect.any(Function),
        onCitation: expect.any(Function),
      }),
      expect.any(AbortSignal),
    );
    expect(wrapper.text()).toContain("What is OSPF?");
    expect(wrapper.find(".is-assistant h2").text()).toBe("OSPF");
    expect(wrapper.text()).toContain("\u6b63\u5728\u67e5\u8be2\u77e5\u8bc6\u5e93");
    expect(wrapper.text()).toContain("\u505c\u6b62\u751f\u6210");

    finishStream();
    await flushPromises();

    expect(wrapper.find(".is-assistant strong").text()).toBe("Link-state");
    expect(wrapper.find(".token-number").text()).toBe("0");
    expect(wrapper.text()).toContain("Cisco OSPF.pdf");
    expect(wrapper.find(".loading-row").exists()).toBe(false);
    expect(scroller.scrollTop).toBe(900);

    const inlineReference = wrapper.find(".citation-reference");
    await inlineReference.trigger("click");
    await flushPromises();
    expect(wrapper.find(".citation-reference").classes()).toContain(
      "is-active",
    );
    expect(document.body.textContent).toContain("OSPF areas reduce link-state flooding.");

    wrapper.unmount();
  });

  it("aborts the active request and removes an unused assistant placeholder", async () => {
    let receivedSignal: AbortSignal | undefined;
    vi.mocked(chatApi.streamChatMessage).mockImplementation(
      async (_payload, _handlers, signal): Promise<void> => {
        receivedSignal = signal;
        await new Promise<void>((_resolve, reject) => {
          signal.addEventListener(
            "abort",
            () => reject(new DOMException("Aborted", "AbortError")),
            { once: true },
          );
        });
      },
    );
    const messageSpy = vi
      .spyOn(ElMessage, "error")
      .mockReturnValue({ close: vi.fn() } as MessageHandler);
    const wrapper = mountChatView();

    await flushPromises();
    await submitQuestion(wrapper, "Stop this answer");
    await flushPromises();
    const stopButton = wrapper
      .findAll("button")
      .find((button) => button.text().includes("\u505c\u6b62\u751f\u6210"));
    expect(stopButton).toBeDefined();
    await stopButton?.trigger("click");
    await flushPromises();

    expect(receivedSignal?.aborted).toBe(true);
    expect(messageSpy).not.toHaveBeenCalled();
    expect(wrapper.find(".loading-row").exists()).toBe(false);
    expect(wrapper.findAll(".message-row")).toHaveLength(1);
    wrapper.unmount();
  });

  it("ends loading and shows a message after a stream failure", async () => {
    vi.mocked(chatApi.streamChatMessage).mockRejectedValue(
      new chatApi.ChatStreamError("Chat service unavailable"),
    );
    const messageSpy = vi
      .spyOn(ElMessage, "error")
      .mockReturnValue({ close: vi.fn() } as MessageHandler);
    const wrapper = mountChatView();

    await flushPromises();
    await submitQuestion(wrapper, "What is BGP?");
    await flushPromises();

    expect(messageSpy).toHaveBeenCalledWith("Chat service unavailable");
    expect(wrapper.find(".loading-row").exists()).toBe(false);
    expect(wrapper.text()).toContain("What is BGP?");
    expect(wrapper.findAll(".message-row")).toHaveLength(1);
    wrapper.unmount();
  });

  it("keeps blank submissions disabled", async () => {
    const wrapper = mountChatView();
    const sendButton = wrapper
      .findAll("button")
      .find((button) => button.text().includes("\u53d1\u9001"));

    expect(sendButton?.attributes("disabled")).toBeDefined();
    await wrapper.find("textarea").setValue("   ");
    expect(sendButton?.attributes("disabled")).toBeDefined();
    expect(chatApi.streamChatMessage).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it("sends with Ctrl+Enter but keeps plain Enter for multiline input", async () => {
    vi.mocked(chatApi.streamChatMessage).mockResolvedValue(undefined);
    const wrapper = mountChatView();
    await flushPromises();
    const textarea = wrapper.find("textarea");
    await textarea.setValue("Keyboard question");

    await textarea.trigger("keydown", { key: "Enter" });
    expect(chatApi.streamChatMessage).not.toHaveBeenCalled();

    await textarea.trigger("keydown", { key: "Enter", ctrlKey: true });
    await flushPromises();
    expect(chatApi.streamChatMessage).toHaveBeenCalledWith(
      { conversation_id: 1, message: "Keyboard question" },
      expect.any(Object),
      expect.any(AbortSignal),
    );
    wrapper.unmount();
  });
});
