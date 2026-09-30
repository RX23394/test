import { computed, ref, toRaw } from "vue";
import { defineStore } from "pinia";

import { streamChatMessage, type ChatCitation } from "@/api/chat";
import { useConversationStore } from "@/stores/conversation";

export type { ChatCitation } from "@/api/chat";

export interface ChatMessage {
  id: number;
  role: "assistant" | "user";
  content: string;
  citations?: ChatCitation[];
}

export const useChatStore = defineStore("chat", () => {
  const conversationStore = useConversationStore();
  const messages = ref<ChatMessage[]>([]);
  const draft = ref("");
  const loading = ref(false);
  const historyLoading = ref(false);
  const activeConversationId = ref<number | null>(null);
  const abortController = ref<AbortController | null>(null);
  let nextMessageId = 1;

  const canSend = computed<boolean>(
    () =>
      draft.value.trim().length > 0 &&
      !loading.value &&
      activeConversationId.value !== null,
  );

  /** Stream one answer into the active conversation. */
  async function send(): Promise<void> {
    const content = draft.value.trim();
    if (!content || loading.value || activeConversationId.value === null) {
      return;
    }
    const conversationId = activeConversationId.value;
    messages.value.push({ id: nextMessageId++, role: "user", content });
    draft.value = "";
    loading.value = true;
    const assistantMessage: ChatMessage = {
      id: nextMessageId++,
      role: "assistant",
      content: "",
    };
    messages.value.push(assistantMessage);
    const controller = new AbortController();
    abortController.value = controller;
    try {
      await streamChatMessage(
        { conversation_id: conversationId, message: content },
        {
          onToken(token: string): void {
            assistantMessage.content += token;
          },
          onCitation(citations: ChatCitation[]): void {
            assistantMessage.citations = citations;
          },
        },
        controller.signal,
      );
    } catch (error: unknown) {
      removeEmptyAssistantMessage(assistantMessage);
      if (!isAbortError(error, controller.signal)) {
        throw error;
      }
    } finally {
      loading.value = false;
      if (abortController.value === controller) {
        abortController.value = null;
      }
    }
  }

  /** Stop the active streaming response. */
  function stop(): void {
    abortController.value?.abort();
  }

  /** Load messages for the selected conversation. */
  async function selectConversation(conversationId: number): Promise<void> {
    if (activeConversationId.value === conversationId && messages.value.length > 0) {
      return;
    }
    abortController.value?.abort();
    activeConversationId.value = conversationId;
    historyLoading.value = true;
    messages.value = [];
    try {
      const detail = await conversationStore.getDetail(conversationId);
      if (activeConversationId.value !== conversationId) {
        return;
      }
      messages.value = detail.messages.map((message) => ({
        id: message.id,
        role: message.role,
        content: message.content,
      }));
      nextMessageId = Math.max(0, ...messages.value.map((message) => message.id)) + 1;
    } finally {
      if (activeConversationId.value === conversationId) {
        historyLoading.value = false;
      }
    }
  }

  /** Remove an assistant placeholder with no streamed content. */
  function removeEmptyAssistantMessage(message: ChatMessage): void {
    if (message.content || (message.citations?.length ?? 0) > 0) {
      return;
    }
    messages.value = messages.value.filter(
      (candidate) => toRaw(candidate) !== message,
    );
  }

  /** Return whether an error is an intentional stream cancellation. */
  function isAbortError(error: unknown, signal: AbortSignal): boolean {
    return signal.aborted || (error instanceof Error && error.name === "AbortError");
  }

  return {
    messages,
    draft,
    loading,
    historyLoading,
    activeConversationId,
    canSend,
    send,
    stop,
    selectConversation,
  };
});
