import axios, { type AxiosProgressEvent, type AxiosResponse } from "axios";

import apiClient from "@/api/api";
import type { ResponseModel } from "@/api/auth";

export type DocumentStatus =
  | "pending"
  | "processing"
  | "completed"
  | "indexed"
  | "failed";

export interface DocumentRecord {
  id: number;
  filename: string;
  original_filename: string;
  sha256: string;
  file_size: number;
  uploader_id: number;
  status: DocumentStatus;
  created_at: string;
}

export interface DocumentContent {
  filename: string;
  pages: Array<{
    page_number: number;
    text: string;
  }>;
}

/** Fetch administrator-visible documents with optional server-side search. */
export async function listDocuments(search = ""): Promise<DocumentRecord[]> {
  const response: AxiosResponse<ResponseModel<DocumentRecord[]>> =
    await apiClient.get("/api/admin/documents", {
      params: search ? { search } : undefined,
    });
  return requireData(response.data);
}

/** Upload one document and report browser transfer progress. */
export async function uploadDocument(
  file: File,
  onProgress: (percentage: number) => void,
): Promise<DocumentRecord> {
  const formData = new FormData();
  formData.append("file", file);
  const response: AxiosResponse<ResponseModel<DocumentRecord>> =
    await apiClient.post("/api/admin/documents", formData, {
      timeout: 120_000,
      onUploadProgress: (event: AxiosProgressEvent): void => {
        if (event.total) {
          onProgress(Math.round((event.loaded * 100) / event.total));
        }
      },
    });
  return requireData(response.data);
}

/** Parse a stored document and return its normalized textual content. */
export async function parseDocument(id: number): Promise<DocumentContent> {
  const response: AxiosResponse<ResponseModel<DocumentContent>> =
    await apiClient.post(`/api/admin/documents/${id}/parse`, undefined, {
      timeout: 120_000,
    });
  return requireData(response.data);
}

/** Build search indexes for a parsed document. */
export async function indexDocument(id: number): Promise<void> {
  await apiClient.post(`/api/admin/documents/${id}/index`, undefined, {
    timeout: 300_000,
  });
}

/** Permanently delete a document and all of its indexes. */
export async function deleteDocument(id: number): Promise<void> {
  await apiClient.delete(`/api/admin/documents/${id}`);
}

/** Return the uniform API error message when one is available. */
export function getDocumentErrorMessage(error: unknown): string | undefined {
  if (!axios.isAxiosError<ResponseModel<unknown>>(error)) {
    return undefined;
  }
  return error.response?.data.message;
}

/** Extract successful payload data from the uniform API envelope. */
function requireData<T>(response: ResponseModel<T>): T {
  if (response.status !== "ok" || response.data === undefined) {
    throw new Error(response.message ?? "Document request failed");
  }
  return response.data;
}
