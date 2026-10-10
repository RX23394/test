<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { storeToRefs } from "pinia";

import {
  type DocumentContent,
  type DocumentRecord,
  useDocumentStore,
} from "@/stores/document";

type DisplayStatus =
  | "Uploading"
  | "Parsing"
  | "Indexing"
  | "Indexed"
  | "Deleting"
  | "Failed";

interface UploadingRow {
  key: string;
  filename: string;
  fileSize: number;
  progress: number;
  status: DisplayStatus;
}

const documentStore = useDocumentStore();
const { documents, loading } = storeToRefs(documentStore);
const uploadingRows = ref<UploadingRow[]>([]);
const transientStatuses = ref<Record<number, DisplayStatus>>({});
const search = ref("");
const dragActive = ref(false);
const fileInput = ref<HTMLInputElement>();
const previewVisible = ref(false);
const previewLoading = ref(false);
const selectedDocument = ref<DocumentRecord>();
const previewContent = ref<DocumentContent>();
const loadError = ref("");
const selectedDocumentIds = ref<Set<number>>(new Set());
const batchDeleting = ref(false);

const indexedCount = computed<number>(
  () => documents.value.filter((document) => document.status === "indexed").length,
);
const processingCount = computed<number>(
  () =>
    uploadingRows.value.length +
    documents.value.filter((document) =>
      ["pending", "processing", "completed"].includes(document.status),
    ).length,
);
const selectedDocuments = computed<DocumentRecord[]>(() =>
  documents.value.filter((document) => selectedDocumentIds.value.has(document.id)),
);
const allDocumentsSelected = computed<boolean>(
  () =>
    documents.value.length > 0 &&
    selectedDocuments.value.length === documents.value.length,
);
const someDocumentsSelected = computed<boolean>(
  () => selectedDocuments.value.length > 0 && !allDocumentsSelected.value,
);

/** Load the current document list using the active search term. */
async function loadDocuments(): Promise<void> {
  loadError.value = "";
  try {
    await documentStore.load(search.value.trim());
    const visibleIds = new Set(documents.value.map((document) => document.id));
    selectedDocumentIds.value = new Set(
      [...selectedDocumentIds.value].filter((id) => visibleIds.has(id)),
    );
  } catch {
    loadError.value = "文档列表加载失败，请稍后重试";
    ElMessage.error("文档列表加载失败，请稍后重试");
  }
}

/** Open the native file chooser. */
function openFilePicker(): void {
  fileInput.value?.click();
}

/** Upload files selected through the native picker. */
async function handleFileSelection(event: Event): Promise<void> {
  const target = event.target as HTMLInputElement;
  await processFiles(Array.from(target.files ?? []));
  target.value = "";
}

/** Accept dropped files and start their upload workflows. */
async function handleDrop(event: DragEvent): Promise<void> {
  dragActive.value = false;
  await processFiles(Array.from(event.dataTransfer?.files ?? []));
}

/** Validate and process files sequentially for predictable status updates. */
async function processFiles(files: File[]): Promise<void> {
  for (const file of files) {
    if (!isSupportedFile(file)) {
      ElMessage.warning(`${file.name}：仅支持 PDF、DOCX、MD、TXT`);
      continue;
    }
    if (file.size > 50 * 1024 * 1024) {
      ElMessage.warning(`${file.name}：文件不能超过 50 MB`);
      continue;
    }
    await processFile(file);
  }
}

/** Upload, parse, and index a single document. */
async function processFile(file: File): Promise<void> {
  const digest = await calculateSha256(file);
  if (digest && documentStore.hasDigest(digest)) {
    ElMessage.warning(`“${file.name}”内容已存在（SHA256 重复）`);
    return;
  }

  const key = `${file.name}-${file.size}-${Date.now()}`;
  uploadingRows.value.unshift({
    key,
    filename: file.name,
    fileSize: file.size,
    progress: 0,
    status: "Uploading",
  });

  try {
    const document = await documentStore.upload(file, (progress) => {
      updateUploadProgress(key, progress);
    });
    removeUploadingRow(key);
    await runIndexPipeline(document);
  } catch (error: unknown) {
    const row = uploadingRows.value.find((item) => item.key === key);
    if (row) {
      row.status = "Failed";
    }
    const message = documentStore.errorMessage(error);
    if (message === "Document already exists") {
      ElMessage.warning(`“${file.name}”内容已存在（SHA256 重复）`);
    } else {
      ElMessage.error(`${file.name} 上传失败`);
    }
  }
}

/** Parse and index an uploaded document while updating its visible state. */
async function runIndexPipeline(document: DocumentRecord): Promise<void> {
  try {
    transientStatuses.value[document.id] = "Parsing";
    await documentStore.parse(document.id);
    transientStatuses.value[document.id] = "Indexing";
    // Indexing runs in the background now, so the row follows the polled state.
    const finished = await documentStore.index(document.id);
    if (!finished || finished.status === "failed") {
      throw new Error("indexing did not complete");
    }
    transientStatuses.value[document.id] = "Indexed";
    document.status = finished.status;
    ElMessage.success(`${document.original_filename} 已完成索引`);
  } catch {
    transientStatuses.value[document.id] = "Failed";
    document.status = "failed";
    ElMessage.error(`${document.original_filename} 处理失败`);
  }
}

/** Show document metadata and normalized content in a dialog. */
async function showDocument(document: DocumentRecord): Promise<void> {
  selectedDocument.value = document;
  previewContent.value = undefined;
  previewVisible.value = true;
  previewLoading.value = true;
  try {
    previewContent.value = await documentStore.parse(document.id);
  } catch {
    ElMessage.error("文档内容加载失败");
  } finally {
    previewLoading.value = false;
  }
}

/** Confirm and permanently remove one document. */
async function confirmDelete(document: DocumentRecord): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `删除“${document.original_filename}”后无法恢复。`,
      "删除文档",
      { confirmButtonText: "删除", cancelButtonText: "取消", type: "warning" },
    );
    await documentStore.remove(document.id);
    selectedDocumentIds.value.delete(document.id);
    delete transientStatuses.value[document.id];
    ElMessage.success("文档已删除");
  } catch (error: unknown) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error("删除失败，请稍后重试");
    }
  }
}

/** Select or clear every currently visible document. */
function toggleAllDocuments(event: Event): void {
  const checked = (event.target as HTMLInputElement).checked;
  selectedDocumentIds.value = checked
    ? new Set(documents.value.map((document) => document.id))
    : new Set();
}

/** Update selection for one document row. */
function toggleDocument(documentId: number, event: Event): void {
  const nextSelection = new Set(selectedDocumentIds.value);
  if ((event.target as HTMLInputElement).checked) {
    nextSelection.add(documentId);
  } else {
    nextSelection.delete(documentId);
  }
  selectedDocumentIds.value = nextSelection;
}

/** Confirm and delete all selected documents in one user action. */
async function confirmBatchDelete(): Promise<void> {
  const targets = selectedDocuments.value;
  if (targets.length === 0) return;

  try {
    await ElMessageBox.confirm(
      `确定删除已选择的 ${targets.length} 个文档吗？删除后无法恢复。`,
      "批量删除文档",
      { confirmButtonText: "批量删除", cancelButtonText: "取消", type: "warning" },
    );
  } catch (error: unknown) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error("无法打开批量删除确认框");
    }
    return;
  }

  batchDeleting.value = true;
  const failedIds = new Set<number>();
  let deletedCount = 0;
  try {
    for (const document of targets) {
      try {
        await documentStore.remove(document.id);
        delete transientStatuses.value[document.id];
        deletedCount += 1;
      } catch {
        failedIds.add(document.id);
      }
    }
  } finally {
    batchDeleting.value = false;
    selectedDocumentIds.value = failedIds;
  }

  if (failedIds.size === 0) {
    ElMessage.success(`已删除 ${deletedCount} 个文档`);
  } else if (deletedCount > 0) {
    ElMessage.warning(
      `已删除 ${deletedCount} 个文档，${failedIds.size} 个删除失败`,
    );
  } else {
    ElMessage.error("批量删除失败，请稍后重试");
  }
}

/** Resolve a backend or transient status to the required display stage. */
function displayStatus(document: DocumentRecord): DisplayStatus {
  const transient = transientStatuses.value[document.id];
  if (transient) {
    return transient;
  }
  const statusMap: Record<DocumentRecord["status"], DisplayStatus> = {
    pending: "Parsing",
    processing: "Parsing",
    completed: "Indexing",
    indexed: "Indexed",
    pending_delete: "Deleting",
    failed: "Failed",
  };
  return statusMap[document.status];
}

/** Return the visual class for a processing status. */
function statusClass(status: DisplayStatus): string {
  return `status-${status.toLowerCase()}`;
}

/** Format a byte count into a concise human-readable value. */
function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Format an ISO date for the local browser locale. */
function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

/** Check the supported extension allow-list. */
function isSupportedFile(file: File): boolean {
  return /\.(pdf|docx|md|txt)$/i.test(file.name);
}

/** Calculate a browser-native SHA-256 digest when Web Crypto is available. */
async function calculateSha256(file: File): Promise<string> {
  if (!globalThis.crypto?.subtle) {
    return "";
  }
  const hash = await globalThis.crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(hash), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}

/** Update a temporary upload row's transfer percentage. */
function updateUploadProgress(key: string, progress: number): void {
  const row = uploadingRows.value.find((item) => item.key === key);
  if (row) {
    row.progress = progress;
  }
}

/** Remove a completed temporary upload row. */
function removeUploadingRow(key: string): void {
  uploadingRows.value = uploadingRows.value.filter((item) => item.key !== key);
}

onMounted(loadDocuments);
</script>

<template>
  <section class="documents-page">
    <header class="page-heading">
      <div>
        <p class="eyebrow">KNOWLEDGE BASE</p>
        <h2>文档管理</h2>
        <p>上传资料并跟踪解析与索引状态。</p>
      </div>
      <div class="summary">
        <div><strong>{{ documents.length }}</strong><span>全部文档</span></div>
        <div><strong>{{ indexedCount }}</strong><span>已索引</span></div>
        <div><strong>{{ processingCount }}</strong><span>处理中</span></div>
      </div>
    </header>

    <div
      class="upload-zone"
      :class="{ 'is-dragging': dragActive }"
      @click="openFilePicker"
      @dragenter.prevent="dragActive = true"
      @dragover.prevent="dragActive = true"
      @dragleave.prevent="dragActive = false"
      @drop.prevent="handleDrop"
    >
      <input
        ref="fileInput"
        class="file-input"
        type="file"
        accept=".pdf,.docx,.md,.txt"
        multiple
        @change="handleFileSelection"
      />
      <div class="upload-icon">↑</div>
      <div>
        <strong>拖拽文档到这里，或点击上传</strong>
        <p>支持 PDF、DOCX、Markdown、TXT，单个文件最大 50 MB</p>
      </div>
      <el-button type="primary" @click.stop="openFilePicker">选择文件</el-button>
    </div>

    <div class="document-card">
      <div class="toolbar">
        <div>
          <h3>知识库文件</h3>
          <span>按文件名或 SHA256 搜索</span>
        </div>
        <div class="toolbar-actions">
          <el-button
            type="danger"
            plain
            :disabled="selectedDocuments.length === 0"
            :loading="batchDeleting"
            @click="confirmBatchDelete"
          >
            批量删除<span v-if="selectedDocuments.length">（{{ selectedDocuments.length }}）</span>
          </el-button>
          <form class="search-form" @submit.prevent="loadDocuments">
            <el-input v-model="search" clearable placeholder="搜索文件名或 SHA256" />
            <el-button type="primary" native-type="submit">搜索</el-button>
          </form>
        </div>
      </div>

      <el-alert
        v-if="loadError"
        class="state-error"
        type="error"
        :title="loadError"
        show-icon
        :closable="false"
      >
        <el-button size="small" @click="loadDocuments">重新加载</el-button>
      </el-alert>

      <div class="table-wrap">
        <div v-if="loading" class="state-skeleton">
          <el-skeleton :rows="5" animated />
        </div>
        <table v-else>
          <thead>
            <tr>
              <th class="selection-column">
                <input
                  type="checkbox"
                  aria-label="全选文档"
                  :checked="allDocumentsSelected"
                  :indeterminate="someDocumentsSelected"
                  :disabled="documents.length === 0 || batchDeleting"
                  @change="toggleAllDocuments"
                />
              </th>
              <th>文件</th><th>状态</th><th>大小</th><th>上传时间</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in uploadingRows" :key="row.key">
              <td class="selection-column" />
              <td><div class="file-cell"><span class="file-badge">DOC</span><div><strong>{{ row.filename }}</strong><small>正在上传</small></div></div></td>
              <td><span class="status-pill" :class="statusClass(row.status)"><i />{{ row.status }}</span></td>
              <td>{{ formatBytes(row.fileSize) }}</td>
              <td><el-progress :percentage="row.progress" :stroke-width="6" /></td>
              <td><span class="muted">请稍候</span></td>
            </tr>
            <tr v-for="document in documents" :key="document.id">
              <td class="selection-column">
                <input
                  type="checkbox"
                  :aria-label="`选择 ${document.original_filename}`"
                  :checked="selectedDocumentIds.has(document.id)"
                  :disabled="batchDeleting"
                  @change="toggleDocument(document.id, $event)"
                />
              </td>
              <td><div class="file-cell"><span class="file-badge">{{ document.original_filename.split('.').pop()?.toUpperCase() }}</span><div><strong>{{ document.original_filename }}</strong><small :title="document.sha256">SHA256 · {{ document.sha256.slice(0, 12) }}…</small></div></div></td>
              <td><span class="status-pill" :class="statusClass(displayStatus(document))"><i />{{ displayStatus(document) }}</span></td>
              <td>{{ formatBytes(document.file_size) }}</td>
              <td>{{ formatDate(document.created_at) }}</td>
              <td><div class="row-actions"><el-button link type="primary" @click="showDocument(document)">查看</el-button><el-button link type="danger" @click="confirmDelete(document)">删除</el-button></div></td>
            </tr>
            <tr v-if="!loading && documents.length === 0 && uploadingRows.length === 0">
              <td colspan="6" class="empty-state">暂无文档，拖拽文件开始构建知识库。</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <el-dialog v-model="previewVisible" width="min(760px, 92vw)" title="文档详情">
      <div v-if="selectedDocument" class="document-detail">
        <div class="detail-grid">
          <div><span>文件名</span><strong>{{ selectedDocument.original_filename }}</strong></div>
          <div><span>大小</span><strong>{{ formatBytes(selectedDocument.file_size) }}</strong></div>
          <div class="hash-detail"><span>SHA256</span><code>{{ selectedDocument.sha256 }}</code></div>
        </div>
        <div v-loading="previewLoading" class="preview-panel">
          <pre v-if="previewContent">{{ previewContent.pages.map((page) => page.text).join("\n\n") }}</pre>
          <p v-else-if="!previewLoading">暂无可预览内容</p>
        </div>
      </div>
    </el-dialog>
  </section>
</template>

<style scoped>
.documents-page { display: grid; gap: 22px; max-width: 1440px; margin: 0 auto; }
.page-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; }
.eyebrow { margin: 0 0 7px; color: #2563eb; font-size: .72rem; font-weight: 800; letter-spacing: .13em; }
.page-heading h2 { margin: 0; color: #172033; font-size: 1.75rem; letter-spacing: -.03em; }
.page-heading p:not(.eyebrow) { margin: 8px 0 0; color: #64748b; }
.summary { display: flex; gap: 10px; }
.summary div { min-width: 102px; padding: 13px 16px; border: 1px solid #e2e8f0; border-radius: 12px; background: #fff; }
.summary strong, .summary span { display: block; }
.summary strong { color: #172033; font-size: 1.25rem; }
.summary span { margin-top: 2px; color: #94a3b8; font-size: .76rem; }
.upload-zone { display: flex; min-height: 132px; align-items: center; gap: 18px; padding: 24px 30px; border: 1.5px dashed #b9c6d8; border-radius: 16px; background: #f9fbff; cursor: pointer; transition: .2s ease; }
.upload-zone:hover, .upload-zone.is-dragging { border-color: #2563eb; background: #eff6ff; box-shadow: 0 10px 30px rgb(37 99 235 / 8%); }
.upload-icon { display: grid; width: 48px; height: 48px; flex: none; place-items: center; border-radius: 13px; color: #fff; background: #2563eb; font-size: 1.6rem; font-weight: 300; }
.upload-zone > div:nth-child(3) { flex: 1; }
.upload-zone strong { color: #1e293b; font-size: .98rem; }
.upload-zone p { margin: 6px 0 0; color: #8492a6; font-size: .82rem; }
.file-input { display: none; }
.document-card { overflow: hidden; border: 1px solid #e2e8f0; border-radius: 16px; background: #fff; box-shadow: 0 8px 24px rgb(15 23 42 / 4%); }
.toolbar { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 20px 24px; border-bottom: 1px solid #edf0f4; }
.toolbar h3 { margin: 0; color: #1e293b; font-size: 1rem; }
.toolbar span { display: block; margin-top: 4px; color: #94a3b8; font-size: .75rem; }
.toolbar-actions { display: flex; align-items: center; justify-content: flex-end; gap: 10px; }
.search-form { display: flex; width: min(410px, 100%); gap: 9px; }
.table-wrap { overflow-x: auto; }
table { width: 100%; min-width: 850px; border-collapse: collapse; }
th { padding: 12px 20px; color: #7b8799; background: #fafbfc; font-size: .72rem; font-weight: 700; letter-spacing: .04em; text-align: left; }
td { padding: 15px 20px; border-top: 1px solid #f0f2f5; color: #536174; font-size: .82rem; }
.selection-column { width: 44px; padding-right: 4px; text-align: center; }
.selection-column input { width: 16px; height: 16px; accent-color: #2563eb; cursor: pointer; }
.selection-column input:disabled { cursor: not-allowed; }
.file-cell { display: flex; align-items: center; gap: 12px; min-width: 260px; }
.file-cell > div { min-width: 0; }
.file-cell strong, .file-cell small { display: block; max-width: 340px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-cell strong { color: #273449; font-size: .84rem; }
.file-cell small { margin-top: 4px; color: #9aa6b6; font-size: .68rem; }
.file-badge { display: grid; width: 38px; height: 38px; flex: none; place-items: center; border-radius: 9px; color: #2563eb; background: #eff6ff; font-size: .58rem; font-weight: 800; }
.status-pill { display: inline-flex; align-items: center; gap: 7px; padding: 5px 9px; border-radius: 999px; font-size: .7rem; font-weight: 700; }
.status-pill i { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.status-uploading, .status-parsing, .status-indexing { color: #2563eb; background: #eff6ff; }
.status-parsing i, .status-indexing i { animation: pulse 1.2s infinite; }
.status-indexed { color: #15803d; background: #ecfdf3; }
.status-deleting { color: #b45309; background: #fffbeb; }
.status-failed { color: #dc2626; background: #fef2f2; }
.row-actions { display: flex; white-space: nowrap; }
.muted { color: #9aa6b6; }
.empty-state { padding: 52px 20px; color: #94a3b8; text-align: center; }
.detail-grid { display: grid; grid-template-columns: 2fr 1fr; gap: 12px; }
.detail-grid > div { padding: 12px 14px; border-radius: 10px; background: #f8fafc; }
.detail-grid span, .detail-grid strong { display: block; }
.detail-grid span { margin-bottom: 5px; color: #94a3b8; font-size: .7rem; }
.hash-detail { grid-column: 1 / -1; }
.hash-detail code { overflow-wrap: anywhere; color: #475569; font-size: .75rem; }
.preview-panel { min-height: 240px; max-height: 50vh; margin-top: 16px; overflow: auto; border: 1px solid #e2e8f0; border-radius: 10px; background: #fbfcfe; }
.preview-panel pre { margin: 0; padding: 18px; color: #334155; font: .8rem/1.7 ui-monospace, monospace; white-space: pre-wrap; }
.preview-panel p { padding: 40px; color: #94a3b8; text-align: center; }
@keyframes pulse { 50% { opacity: .25; } }
@media (max-width: 900px) { .page-heading { align-items: flex-start; flex-direction: column; } .summary { width: 100%; } .summary div { flex: 1; min-width: 0; } .upload-zone { align-items: flex-start; flex-wrap: wrap; } .toolbar { align-items: stretch; flex-direction: column; } .toolbar-actions { align-items: stretch; flex-direction: column-reverse; } .search-form { width: 100%; } }
@media (max-width: 560px) { .summary { gap: 6px; } .summary div { padding: 10px; } .upload-zone { padding: 20px; } .upload-zone .el-button { width: 100%; } .detail-grid { grid-template-columns: 1fr; } }
</style>
