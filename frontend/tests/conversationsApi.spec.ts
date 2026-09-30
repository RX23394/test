import { beforeEach, describe, expect, it, vi } from "vitest";

import apiClient from "@/api/api";
import {
  createConversation,
  deleteConversation,
  getConversation,
  listConversations,
  renameConversation,
} from "@/api/conversations";

vi.mock("@/api/api", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

const SUMMARY = {
  id: 4,
  title: "OSPF",
  created_at: "2026-07-16T00:00:00Z",
  updated_at: "2026-07-16T00:00:00Z",
};

describe("conversation API", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("uses the conversation CRUD and detail endpoints", async () => {
    vi.mocked(apiClient.get)
      .mockResolvedValueOnce({ data: { status: "ok", data: [SUMMARY] } })
      .mockResolvedValueOnce({
        data: {
          status: "ok",
          data: { conversation: SUMMARY, messages: [] },
        },
      });
    vi.mocked(apiClient.post).mockResolvedValue({
      data: { status: "ok", data: SUMMARY },
    });
    vi.mocked(apiClient.patch).mockResolvedValue({
      data: { status: "ok", data: { ...SUMMARY, title: "Areas" } },
    });
    vi.mocked(apiClient.delete).mockResolvedValue({ data: { status: "ok" } });

    await expect(listConversations()).resolves.toEqual([SUMMARY]);
    await expect(createConversation()).resolves.toEqual(SUMMARY);
    await expect(getConversation(4)).resolves.toEqual({
      conversation: SUMMARY,
      messages: [],
    });
    await expect(renameConversation(4, "Areas")).resolves.toMatchObject({
      title: "Areas",
    });
    await deleteConversation(4);

    expect(apiClient.get).toHaveBeenNthCalledWith(1, "/api/conversations");
    expect(apiClient.get).toHaveBeenNthCalledWith(2, "/api/conversations/4");
    expect(apiClient.post).toHaveBeenCalledWith("/api/conversations", {
      title: null,
    });
    expect(apiClient.patch).toHaveBeenCalledWith("/api/conversations/4", {
      title: "Areas",
    });
    expect(apiClient.delete).toHaveBeenCalledWith("/api/conversations/4");
  });
});
