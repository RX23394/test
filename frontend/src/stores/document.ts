import { ref } from "vue";
import { defineStore } from "pinia";

import {
  deleteDocument,
  getDocumentErrorMessage,
  listDocuments,
  parseDocument,
  startDocumentIndexing,
  uploadDocument,
  type DocumentContent,
  type DocumentRecord,
} from "@/api/documents";

export type { DocumentContent, DocumentRecord } from "@/api/documents";

const INDEX_POLL_INTERVAL_MS = 1500;
const INDEX_POLL_ATTEMPTS = 40;

/** Wait for one polling interval while background indexing runs. */
function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, milliseconds);
  });
}

export const useDocumentStore = defineStore("document", () => {
  const documents = ref<DocumentRecord[]>([]);
  const loading = ref(false);

  /** Load documents using an optional server-side search term. */
  async function load(search = ""): Promise<void> {
    loading.value = true;
    try {
      documents.value = await listDocuments(search);
    } finally {
      loading.value = false;
    }
  }

  /** Upload one file and add its metadata to the store. */
  async function upload(
    file: File,
    onProgress: (percentage: number) => void,
  ): Promise<DocumentRecord> {
    const document = await uploadDocument(file, onProgress);
    documents.value.unshift(document);
    return document;
  }

  /** Parse one stored document for processing or preview. */
  async function parse(documentId: number): Promise<DocumentContent> {
    return parseDocument(documentId);
  }

  /** Claim background indexing and poll until the document leaves processing.
   *
   * Returns the refreshed record, or undefined when indexing did not finish
   * inside the polling window.
   */
  async function index(documentId: number): Promise<DocumentRecord | undefined> {
    await startDocumentIndexing(documentId);
    for (let attempt = 0; attempt < INDEX_POLL_ATTEMPTS; attempt += 1) {
      const records = await listDocuments();
      const record = records.find((item) => item.id === documentId);
      if (record && record.status !== "processing") {
        documents.value = records;
        return record;
      }
      await delay(INDEX_POLL_INTERVAL_MS);
    }
    return undefined;
  }

  /** Delete one document and remove it from local state. */
  async function remove(documentId: number): Promise<void> {
    await deleteDocument(documentId);
    documents.value = documents.value.filter(
      (document) => document.id !== documentId,
    );
  }

  /** Return whether a SHA-256 digest already exists in the knowledge base. */
  function hasDigest(digest: string): boolean {
    return documents.value.some((document) => document.sha256 === digest);
  }

  /** Resolve a user-facing message from a failed document action. */
  function errorMessage(error: unknown): string | undefined {
    return getDocumentErrorMessage(error);
  }

  return {
    documents,
    loading,
    load,
    upload,
    parse,
    index,
    remove,
    hasDigest,
    errorMessage,
  };
});
