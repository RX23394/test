import { ref } from "vue";
import { defineStore } from "pinia";

import {
  deleteDocument,
  getDocumentErrorMessage,
  indexDocument,
  listDocuments,
  parseDocument,
  uploadDocument,
  type DocumentContent,
  type DocumentRecord,
} from "@/api/documents";

export type { DocumentContent, DocumentRecord } from "@/api/documents";

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

  /** Build all search indexes for one document. */
  async function index(documentId: number): Promise<void> {
    await indexDocument(documentId);
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
