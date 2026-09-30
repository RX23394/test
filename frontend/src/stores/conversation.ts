import { ref } from "vue";
import { defineStore } from "pinia";

import {
  createConversation,
  deleteConversation,
  getConversation,
  listConversations,
  renameConversation,
  type ConversationDetail,
  type ConversationSummary,
} from "@/api/conversations";

export type {
  ConversationDetail,
  ConversationSummary,
} from "@/api/conversations";

export const useConversationStore = defineStore("conversation", () => {
  const conversations = ref<ConversationSummary[]>([]);
  const loading = ref(false);

  /** Load the authenticated user's conversation summaries. */
  async function load(): Promise<void> {
    loading.value = true;
    try {
      conversations.value = await listConversations();
    } finally {
      loading.value = false;
    }
  }

  /** Create and prepend a conversation. */
  async function create(): Promise<ConversationSummary> {
    const conversation = await createConversation();
    conversations.value.unshift(conversation);
    return conversation;
  }

  /** Rename and merge a conversation summary. */
  async function rename(id: number, title: string): Promise<void> {
    const updated = await renameConversation(id, title);
    replace(updated);
  }

  /** Delete one conversation from the backend and local state. */
  async function remove(id: number): Promise<void> {
    await deleteConversation(id);
    conversations.value = conversations.value.filter(
      (conversation) => conversation.id !== id,
    );
  }

  /** Load one conversation with its ordered messages. */
  async function getDetail(id: number): Promise<ConversationDetail> {
    return getConversation(id);
  }

  /** Replace one conversation summary without reordering the list. */
  function replace(updated: ConversationSummary): void {
    conversations.value = conversations.value.map((conversation) =>
      conversation.id === updated.id ? updated : conversation,
    );
  }

  return { conversations, loading, load, create, rename, remove, getDetail };
});
