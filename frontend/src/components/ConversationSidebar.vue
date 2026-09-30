<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { storeToRefs } from "pinia";

import {
  type ConversationSummary,
  useConversationStore,
} from "@/stores/conversation";

const props = defineProps<{ selectedId: number | null }>();
const emit = defineEmits<{
  select: [conversationId: number];
}>();

const COPY = {
  title: "\u4f1a\u8bdd",
  create: "\u65b0\u5efa\u4f1a\u8bdd",
  untitled: "\u65b0\u5bf9\u8bdd",
  rename: "\u91cd\u547d\u540d",
  renamePrompt: "\u8bf7\u8f93\u5165\u65b0\u7684\u4f1a\u8bdd\u540d\u79f0",
  delete: "\u5220\u9664",
  deleteConfirm: "\u786e\u5b9a\u5220\u9664\u8be5\u4f1a\u8bdd\u53ca\u5168\u90e8\u6d88\u606f\u5417\uff1f",
  failure: "\u4f1a\u8bdd\u64cd\u4f5c\u5931\u8d25",
  empty: "\u6682\u65e0\u4f1a\u8bdd",
} as const;

const conversationStore = useConversationStore();
const { conversations, loading } = storeToRefs(conversationStore);
const loadError = ref("");

onMounted(() => {
  void initialize();
});

/** Load conversations and ensure the chat always has an active target. */
async function initialize(): Promise<void> {
  loadError.value = "";
  try {
    await conversationStore.load();
    if (conversations.value.length === 0) {
      await handleCreate();
    } else {
      emit("select", conversations.value[0].id);
    }
  } catch (error: unknown) {
    loadError.value = getErrorMessage(error);
    ElMessage.error(getErrorMessage(error));
  }
}

/** Create and select a new conversation. */
async function handleCreate(): Promise<void> {
  try {
    const conversation = await conversationStore.create();
    emit("select", conversation.id);
  } catch (error: unknown) {
    ElMessage.error(getErrorMessage(error));
  }
}

/** Prompt for and persist a conversation title. */
async function handleRename(conversation: ConversationSummary): Promise<void> {
  try {
    const result = await ElMessageBox.prompt(COPY.renamePrompt, COPY.rename, {
      inputValue: conversation.title ?? COPY.untitled,
      inputPattern: /\S/,
    });
    await conversationStore.rename(conversation.id, result.value.trim());
  } catch (error: unknown) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(getErrorMessage(error));
    }
  }
}

/** Confirm deletion, select a neighbor, and keep one conversation available. */
async function handleDelete(conversation: ConversationSummary): Promise<void> {
  try {
    await ElMessageBox.confirm(COPY.deleteConfirm, COPY.delete, { type: "warning" });
    await conversationStore.remove(conversation.id);
    if (conversations.value.length === 0) {
      await handleCreate();
    } else if (props.selectedId === conversation.id) {
      emit("select", conversations.value[0].id);
    }
  } catch (error: unknown) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(getErrorMessage(error));
    }
  }
}

/** Return a stable user-facing API error message. */
function getErrorMessage(error: unknown): string {
  return error instanceof Error && error.message ? error.message : COPY.failure;
}
</script>

<template>
  <aside class="conversation-sidebar">
    <div class="conversation-header">
      <h3>{{ COPY.title }}</h3>
      <el-button type="primary" size="small" @click="handleCreate">
        {{ COPY.create }}
      </el-button>
    </div>

    <div v-if="loading" class="conversation-skeleton">
      <el-skeleton :rows="4" animated />
    </div>
    <div v-else-if="loadError" class="conversation-empty">
      <p>{{ loadError }}</p>
      <el-button size="small" @click="initialize">重试</el-button>
    </div>
    <div v-else-if="conversations.length === 0" class="conversation-empty">
      {{ COPY.empty }}
    </div>
    <div v-else class="conversation-list">
      <div
        v-for="conversation in conversations"
        :key="conversation.id"
        class="conversation-item"
        :class="{ 'is-active': selectedId === conversation.id }"
      >
        <button
          type="button"
          class="conversation-select"
          @click="emit('select', conversation.id)"
        >
          {{ conversation.title ?? COPY.untitled }}
        </button>
        <div class="conversation-actions">
          <button type="button" @click="handleRename(conversation)">
            {{ COPY.rename }}
          </button>
          <button type="button" @click="handleDelete(conversation)">
            {{ COPY.delete }}
          </button>
        </div>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.conversation-sidebar {
  display: flex;
  width: 240px;
  min-width: 210px;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid #e4e9f1;
  border-radius: 16px;
  background: #fff;
}
.conversation-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 16px;
  border-bottom: 1px solid #edf0f5;
}
.conversation-header h3 { margin: 0; color: #334155; font-size: 0.9rem; }
.conversation-list { min-height: 0; padding: 8px; overflow-y: auto; }
.conversation-item { margin-bottom: 5px; padding: 7px; border-radius: 9px; }
.conversation-item:hover, .conversation-item.is-active { background: #eff6ff; }
.conversation-select {
  width: 100%; padding: 3px; overflow: hidden; border: 0; color: #334155;
  background: transparent; font: inherit; font-size: 0.8rem; text-align: left;
  text-overflow: ellipsis; white-space: nowrap; cursor: pointer;
}
.conversation-actions { display: none; gap: 8px; padding: 5px 3px 0; }
.conversation-item:hover .conversation-actions,
.conversation-item.is-active .conversation-actions { display: flex; }
.conversation-actions button {
  padding: 0; border: 0; color: #64748b; background: transparent;
  font-size: 0.68rem; cursor: pointer;
}
.conversation-actions button:hover { color: #2563eb; }
.conversation-empty { padding: 24px 12px; color: #94a3b8; font-size: 0.76rem; text-align: center; }
.conversation-empty p { margin: 0 0 10px; }
.conversation-skeleton { padding: 16px; }
@media (max-width: 760px) {
  .conversation-sidebar { width: 100%; min-width: 0; max-height: 180px; }
  .conversation-list { display: flex; gap: 6px; overflow-x: auto; }
  .conversation-item { min-width: 170px; }
}
</style>
