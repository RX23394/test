import apiClient from "@/api/api";
import type { ResponseModel } from "@/api/auth";

export interface ConversationSummary {
  id: number;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationMessage {
  id: number;
  role: "assistant" | "user";
  content: string;
  created_at: string;
}

export interface ConversationDetail {
  conversation: ConversationSummary;
  messages: ConversationMessage[];
}

/** List the authenticated user's conversations. */
export async function listConversations(): Promise<ConversationSummary[]> {
  const response = await apiClient.get<ResponseModel<ConversationSummary[]>>(
    "/api/conversations",
  );
  return response.data.data ?? [];
}

/** Create a new conversation with an optional title. */
export async function createConversation(
  title: string | null = null,
): Promise<ConversationSummary> {
  const response = await apiClient.post<ResponseModel<ConversationSummary>>(
    "/api/conversations",
    { title },
  );
  if (response.data.data == null) {
    throw new Error("Conversation response is empty");
  }
  return response.data.data;
}

/** Load one conversation and all of its ordered messages. */
export async function getConversation(id: number): Promise<ConversationDetail> {
  const response = await apiClient.get<ResponseModel<ConversationDetail>>(
    `/api/conversations/${id}`,
  );
  if (response.data.data == null) {
    throw new Error("Conversation response is empty");
  }
  return response.data.data;
}

/** Persist a new conversation title. */
export async function renameConversation(
  id: number,
  title: string,
): Promise<ConversationSummary> {
  const response = await apiClient.patch<ResponseModel<ConversationSummary>>(
    `/api/conversations/${id}`,
    { title },
  );
  if (response.data.data == null) {
    throw new Error("Conversation response is empty");
  }
  return response.data.data;
}

/** Delete one conversation and its messages. */
export async function deleteConversation(id: number): Promise<void> {
  await apiClient.delete(`/api/conversations/${id}`);
}
