<script setup lang="ts">
import { ElMessage } from "element-plus";

import type { ChatCitation } from "@/stores/chat";

const props = defineProps<{
  modelValue: boolean;
  citation: ChatCitation | null;
}>();
const emit = defineEmits<{
  "update:modelValue": [value: boolean];
}>();

const COPY = {
  title: "\u5f15\u7528\u8be6\u60c5",
  document: "\u6587\u6863",
  page: "\u9875\u7801",
  section: "\u7ae0\u8282",
  original: "\u539f\u6587",
  copy: "\u590d\u5236\u539f\u6587",
  copySuccess: "\u539f\u6587\u5df2\u590d\u5236",
  copyFailure: "\u590d\u5236\u5931\u8d25\uff0c\u8bf7\u624b\u52a8\u590d\u5236",
  empty: "-",
} as const;

/** Copy the database-backed source excerpt to the system clipboard. */
async function copyOriginal(): Promise<void> {
  if (props.citation === null) {
    return;
  }
  try {
    await navigator.clipboard.writeText(props.citation.content);
    ElMessage.success(COPY.copySuccess);
  } catch {
    ElMessage.error(COPY.copyFailure);
  }
}

/** Forward drawer visibility changes to the parent model. */
function updateVisibility(value: boolean): void {
  emit("update:modelValue", value);
}
</script>

<template>
  <el-drawer
    :model-value="modelValue"
    :title="COPY.title"
    direction="rtl"
    size="min(440px, 92vw)"
    append-to-body
    class="citation-drawer"
    @update:model-value="updateVisibility"
  >
    <div v-if="citation" class="citation-drawer-content">
      <el-descriptions :column="1" border>
        <el-descriptions-item :label="COPY.document">
          {{ citation.document }}
        </el-descriptions-item>
        <el-descriptions-item :label="COPY.page">
          {{ citation.page ?? COPY.empty }}
        </el-descriptions-item>
        <el-descriptions-item :label="COPY.section">
          {{ citation.section ?? COPY.empty }}
        </el-descriptions-item>
      </el-descriptions>

      <section class="original-section">
        <div class="original-heading">
          <h3>{{ COPY.original }}</h3>
          <el-button type="primary" plain size="small" @click="copyOriginal">
            {{ COPY.copy }}
          </el-button>
        </div>
        <mark class="original-highlight">{{ citation.content }}</mark>
      </section>
    </div>
  </el-drawer>
</template>

<style scoped>
.citation-drawer-content {
  display: grid;
  gap: 24px;
}

.original-section {
  display: grid;
  gap: 12px;
}

.original-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.original-heading h3 {
  margin: 0;
  color: #334155;
  font-size: 0.92rem;
}

.original-highlight {
  display: block;
  padding: 16px;
  border: 1px solid #fde68a;
  border-radius: 10px;
  color: #713f12;
  background: #fffbeb;
  font-size: 0.88rem;
  line-height: 1.75;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
