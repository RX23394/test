import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as chatApi from "@/api/chat";
import * as conversationApi from "@/api/conversations";
import * as documentApi from "@/api/documents";
import * as usersApi from "@/api/users";
import { useAdminStore } from "@/stores/admin";
import { useChatStore } from "@/stores/chat";
import { useConversationStore } from "@/stores/conversation";
import { useDocumentStore } from "@/stores/document";

vi.mock("@/api/chat", () => ({ streamChatMessage: vi.fn() }));
vi.mock("@/api/conversations", () => ({
  createConversation: vi.fn(),
  deleteConversation: vi.fn(),
  getConversation: vi.fn(),
  listConversations: vi.fn(),
  renameConversation: vi.fn(),
}));
vi.mock("@/api/documents", () => ({
  deleteDocument: vi.fn(),
  getDocumentErrorMessage: vi.fn(),
  listDocuments: vi.fn(),
  parseDocument: vi.fn(),
  startDocumentIndexing: vi.fn(),
  uploadDocument: vi.fn(),
}));
vi.mock("@/api/users", () => ({
  createUser: vi.fn(),
  getUserErrorMessage: vi.fn(),
  listUsers: vi.fn(),
  updateUserRole: vi.fn(),
  updateUserStatus: vi.fn(),
}));

const document = {
  id: 1,
  filename: "stored.txt",
  original_filename: "guide.txt",
  sha256: "a".repeat(64),
  file_size: 10,
  uploader_id: 1,
  status: "pending" as const,
  created_at: "2026-07-16T00:00:00Z",
};
const user = {
  id: 2,
  username: "member",
  role: "user" as const,
  is_admin: false,
  is_active: true,
  created_at: "2026-07-16T00:00:00Z",
};
const conversation = {
  id: 3,
  title: "OSPF",
  created_at: "2026-07-16T00:00:00Z",
  updated_at: "2026-07-16T00:00:00Z",
};

describe("domain Pinia stores", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it("documentStore owns document loading and deletion", async () => {
    vi.mocked(documentApi.listDocuments).mockResolvedValue([document]);
    vi.mocked(documentApi.deleteDocument).mockResolvedValue(undefined);
    const store = useDocumentStore();

    await store.load();
    expect(store.documents).toEqual([document]);
    expect(store.hasDigest(document.sha256)).toBe(true);

    await store.remove(document.id);
    expect(store.documents).toEqual([]);
  });

  it("documentStore polls until background indexing finishes", async () => {
    vi.useFakeTimers();
    try {
      vi.mocked(documentApi.startDocumentIndexing).mockResolvedValue({
        document_id: document.id,
        job_id: "job-1",
        status: "processing",
      });
      vi.mocked(documentApi.listDocuments)
        .mockResolvedValueOnce([{ ...document, status: "processing" }])
        .mockResolvedValueOnce([{ ...document, status: "indexed" }]);
      const store = useDocumentStore();

      const pending = store.index(document.id);
      await vi.advanceTimersByTimeAsync(2000);
      const finished = await pending;

      expect(documentApi.startDocumentIndexing).toHaveBeenCalledWith(document.id);
      expect(finished?.status).toBe("indexed");
      expect(store.documents[0].status).toBe("indexed");
    } finally {
      vi.useRealTimers();
    }
  });

  it("adminStore owns users, status, and role updates", async () => {
    vi.mocked(usersApi.listUsers).mockResolvedValue([user]);
    vi.mocked(usersApi.updateUserStatus).mockResolvedValue({
      ...user,
      is_active: false,
    });
    vi.mocked(usersApi.updateUserRole).mockResolvedValue({
      ...user,
      role: "admin",
      is_admin: true,
    });
    const store = useAdminStore();

    await store.loadUsers();
    await store.setUserActive(user.id, false);
    expect(store.users[0].is_active).toBe(false);
    await store.setUserRole(user.id, "admin");
    expect(store.users[0].role).toBe("admin");
  });

  it("conversationStore owns conversation mutations", async () => {
    vi.mocked(conversationApi.listConversations).mockResolvedValue([conversation]);
    vi.mocked(conversationApi.renameConversation).mockResolvedValue({
      ...conversation,
      title: "OSPF areas",
    });
    const store = useConversationStore();

    await store.load();
    await store.rename(conversation.id, "OSPF areas");

    expect(store.conversations[0].title).toBe("OSPF areas");
  });

  it("chatStore owns history and streamed message state", async () => {
    vi.mocked(conversationApi.getConversation).mockResolvedValue({
      conversation,
      messages: [],
    });
    vi.mocked(chatApi.streamChatMessage).mockImplementation(
      async (_payload, handlers) => {
        handlers.onToken("Answer");
        handlers.onCitation([]);
      },
    );
    const store = useChatStore();

    await store.selectConversation(conversation.id);
    store.draft = "Question";
    await store.send();

    expect(store.messages.map((message) => message.content)).toEqual([
      "Question",
      "Answer",
    ]);
  });
});
