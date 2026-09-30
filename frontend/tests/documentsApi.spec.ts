import { beforeEach, describe, expect, it, vi } from "vitest";

import apiClient from "@/api/api";
import {
  deleteDocument,
  indexDocument,
  listDocuments,
  parseDocument,
  uploadDocument,
  type DocumentRecord,
} from "@/api/documents";

vi.mock("@/api/api", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

const document: DocumentRecord = {
  id: 7,
  filename: "stored.txt",
  original_filename: "guide.txt",
  sha256: "a".repeat(64),
  file_size: 12,
  uploader_id: 1,
  status: "pending",
  created_at: "2026-07-16T08:00:00Z",
};

describe("documents API", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("lists documents with a search parameter", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: { status: "ok", data: [document] },
    });

    await expect(listDocuments("guide")).resolves.toEqual([document]);
    expect(apiClient.get).toHaveBeenCalledWith("/api/admin/documents", {
      params: { search: "guide" },
    });
  });

  it("uploads a file and forwards transfer progress", async () => {
    vi.mocked(apiClient.post).mockImplementation(async (_url, _body, config) => {
      config?.onUploadProgress?.({
        loaded: 5,
        total: 10,
        bytes: 5,
        lengthComputable: true,
      });
      return { data: { status: "ok", data: document } };
    });
    const onProgress = vi.fn();

    await expect(
      uploadDocument(new File(["content"], "guide.txt"), onProgress),
    ).resolves.toEqual(document);

    expect(onProgress).toHaveBeenCalledWith(50);
  });

  it("calls parse, index, and delete endpoints", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      data: {
        status: "ok",
        data: { filename: "guide.txt", pages: [] },
      },
    });
    vi.mocked(apiClient.delete).mockResolvedValue({ data: { status: "ok" } });

    await parseDocument(7);
    await indexDocument(7);
    await deleteDocument(7);

    expect(apiClient.post).toHaveBeenCalledWith(
      "/api/admin/documents/7/parse",
      undefined,
      expect.any(Object),
    );
    expect(apiClient.post).toHaveBeenCalledWith(
      "/api/admin/documents/7/index",
      undefined,
      expect.any(Object),
    );
    expect(apiClient.delete).toHaveBeenCalledWith("/api/admin/documents/7");
  });
});
