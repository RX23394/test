<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { storeToRefs } from "pinia";

import {
  type ChatCitation,
  type ChatMessage,
  useChatStore,
} from "@/stores/chat";
import CitationDrawer from "@/components/CitationDrawer.vue";
import ConversationSidebar from "@/components/ConversationSidebar.vue";
import MarkdownContent from "@/components/MarkdownContent.vue";
import { useAuthStore } from "@/stores/auth";

const COPY = {
  heading: "\u7f51\u7edc\u77e5\u8bc6\u52a9\u624b",
  description: "\u57fa\u4e8e\u5df2\u7d22\u5f15\u6587\u6863\u56de\u7b54\uff0c\u652f\u6301 Markdown \u548c\u4ee3\u7801\u9ad8\u4eae",
  emptyTitle: "\u5f00\u59cb\u4e00\u6b21\u5bf9\u8bdd",
  emptyDescription: "\u8f93\u5165\u7f51\u7edc\u5de5\u7a0b\u95ee\u9898\uff0c\u4f8b\u5982 OSPF Area \u7684\u4f5c\u7528",
  placeholder: "\u8f93\u5165\u95ee\u9898\uff0cCtrl + Enter \u53d1\u9001",
  send: "\u53d1\u9001",
  stop: "\u505c\u6b62\u751f\u6210",
  thinking: "\u6b63\u5728\u67e5\u8be2\u77e5\u8bc6\u5e93",
  failure: "\u56de\u7b54\u751f\u6210\u5931\u8d25\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5",
  sources: "\u53c2\u8003\u6765\u6e90",
} as const;

const authStore = useAuthStore();
const chatStore = useChatStore();
const {
  messages,
  draft,
  loading,
  historyLoading,
  activeConversationId,
  canSend,
} = storeToRefs(chatStore);
const chatScroller = ref<HTMLElement>();
const selectedCitation = ref<ChatCitation | null>(null);
const selectedMessageId = ref<number | null>(null);
const citationDrawerVisible = ref(false);

watch(
  [() => messages.value.length, loading],
  () => {
    void scrollToBottom();
  },
  { flush: "post" },
);

/** Stream one answer and append every token to the active assistant message. */
async function sendMessage(): Promise<void> {
  try {
    await chatStore.send();
  } catch (error: unknown) {
    ElMessage.error(getChatErrorMessage(error));
  }
}

/** Stop the active stream while preserving tokens already received. */
function stopGeneration(): void {
  chatStore.stop();
}

/** Switch conversations and automatically load persisted ordered messages. */
async function selectConversation(conversationId: number): Promise<void> {
  try {
    await chatStore.selectConversation(conversationId);
  } catch (error: unknown) {
    ElMessage.error(getChatErrorMessage(error));
  }
}

/** Open a citation belonging to a specific assistant answer. */
function openCitation(message: ChatMessage, citationId: string): void {
  const citation = message.citations?.find((item) => item.id === citationId);
  if (citation !== undefined) {
    openCitationDetails(message.id, citation);
  }
}

/** Open the source drawer and mark its reference as selected. */
function openCitationDetails(messageId: number, citation: ChatCitation): void {
  selectedMessageId.value = messageId;
  selectedCitation.value = citation;
  citationDrawerVisible.value = true;
}

/** Return whether a citation reference is the currently highlighted source. */
function isCitationSelected(messageId: number, citationId: string): boolean {
  return (
    selectedMessageId.value === messageId &&
    selectedCitation.value?.id === citationId
  );
}

/** Return the active inline citation identifier for one assistant answer. */
function activeCitationId(messageId: number): string | null {
  return selectedMessageId.value === messageId ? selectedCitation.value?.id ?? null : null;
}

/** Synchronize drawer visibility and clear highlighting when it closes. */
function updateCitationDrawer(value: boolean): void {
  citationDrawerVisible.value = value;
  if (!value) {
    selectedCitation.value = null;
    selectedMessageId.value = null;
  }
}

/** Keep the newest message and loading indicator visible. */
async function scrollToBottom(): Promise<void> {
  await nextTick();
  const element = chatScroller.value;
  if (element !== undefined) {
    element.scrollTop = element.scrollHeight;
  }
}

/** Return a client-safe message from a streaming request failure. */
function getChatErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return COPY.failure;
}
</script>

<template>
  <div class="chat-workspace">
    <ConversationSidebar
      :selected-id="activeConversationId"
      @select="selectConversation"
    />
    <section class="chat-page">
    <header class="chat-heading">
      <div>
        <p>RAG CHAT</p>
        <h2>{{ COPY.heading }}</h2>
        <span>{{ COPY.description }}</span>
      </div>
      <el-tag effect="plain" type="success">Knowledge Ready</el-tag>
    </header>

    <div ref="chatScroller" class="chat-scroll" aria-live="polite">
      <div v-if="historyLoading" class="chat-skeleton">
        <el-skeleton :rows="6" animated />
      </div>
      <div v-else-if="messages.length === 0 && !loading" class="empty-chat">
        <div class="empty-mark">AI</div>
        <h3>{{ COPY.emptyTitle }}</h3>
        <p>{{ COPY.emptyDescription }}</p>
      </div>

      <div
        v-for="message in messages"
        v-show="!historyLoading"
        :key="message.id"
        class="message-row"
        :class="`is-${message.role}`"
      >
        <el-avatar :size="34" class="message-avatar">
          {{
            message.role === "assistant"
              ? "AI"
              : authStore.user?.username.slice(0, 1).toUpperCase()
          }}
        </el-avatar>
        <article class="message-bubble">
          <MarkdownContent
            v-if="message.role === 'assistant'"
            :content="message.content"
            :active-citation-id="activeCitationId(message.id)"
            @citation-click="openCitation(message, $event)"
          />
          <p v-else class="user-content">{{ message.content }}</p>

          <div
            v-if="message.citations && message.citations.length > 0"
            class="citation-list"
          >
            <span class="citation-label">{{ COPY.sources }}</span>
            <button
              v-for="citation in message.citations"
              :key="citation.id"
              type="button"
              class="citation-chip"
              :class="{
                'is-active': isCitationSelected(message.id, citation.id),
              }"
              @click="openCitationDetails(message.id, citation)"
            >
              [{{ citation.id }}] {{ citation.document }}
              <template v-if="citation.page !== null"> ? Page {{ citation.page }}</template>
            </button>
          </div>
        </article>
      </div>

      <div v-if="loading" class="message-row is-assistant loading-row">
        <el-avatar :size="34" class="message-avatar">AI</el-avatar>
        <div class="message-bubble loading-bubble" role="status">
          <span class="loading-dots" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          <span>{{ COPY.thinking }}</span>
        </div>
      </div>
    </div>

    <footer class="composer">
      <el-input
        v-model="draft"
        type="textarea"
        :rows="2"
        resize="none"
        :placeholder="COPY.placeholder"
        :disabled="loading"
        aria-label="Chat message"
        @keydown.ctrl.enter.exact.prevent="sendMessage"
      />
      <el-button
        v-if="loading"
        type="danger"
        plain
        class="send-button stop-button"
        @click="stopGeneration"
      >
        {{ COPY.stop }}
      </el-button>
      <el-button
        v-else
        type="primary"
        class="send-button"
        :disabled="!canSend"
        @click="sendMessage"
      >
        {{ COPY.send }}
      </el-button>
    </footer>

    <CitationDrawer
      :model-value="citationDrawerVisible"
      :citation="selectedCitation"
      @update:model-value="updateCitationDrawer"
    />
    </section>
  </div>
</template>

<style scoped>
.chat-workspace {
  display: flex;
  height: calc(100vh - 138px);
  min-height: 520px;
  gap: 14px;
}

.chat-page {
  display: grid;
  height: 100%;
  min-height: 520px;
  min-width: 0;
  flex: 1;
  grid-template-rows: auto 1fr auto;
  overflow: hidden;
  border: 1px solid #e4e9f1;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 8px 30px rgb(15 23 42 / 4%);
}

.chat-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 20px 24px;
  border-bottom: 1px solid #edf0f5;
  background: linear-gradient(120deg, #f8fbff, #fff 68%);
}

.chat-heading p,
.chat-heading h2,
.chat-heading span {
  margin: 0;
}

.chat-heading p {
  margin-bottom: 4px;
  color: #2563eb;
  font-size: 0.62rem;
  font-weight: 750;
  letter-spacing: 0.14em;
}

.chat-heading h2 {
  color: #162033;
  font-size: 1.15rem;
  letter-spacing: -0.025em;
}

.chat-heading div > span {
  display: block;
  margin-top: 4px;
  color: #8491a5;
  font-size: 0.76rem;
}

.chat-scroll {
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  padding: 28px clamp(18px, 4vw, 42px);
  scroll-behavior: smooth;
}

.chat-skeleton {
  max-width: 820px;
  padding: 16px 0;
}

.empty-chat {
  display: grid;
  height: 100%;
  min-height: 280px;
  place-items: center;
  align-content: center;
  text-align: center;
}

.empty-mark {
  display: grid;
  width: 58px;
  height: 58px;
  margin-bottom: 14px;
  place-items: center;
  border-radius: 17px;
  color: #2563eb;
  background: #eff6ff;
  font-weight: 800;
}

.empty-chat h3,
.empty-chat p {
  margin: 0;
}

.empty-chat h3 {
  color: #334155;
  font-size: 1rem;
}

.empty-chat p {
  max-width: 420px;
  margin-top: 7px;
  color: #94a3b8;
  font-size: 0.82rem;
}

.message-row {
  display: flex;
  align-items: flex-start;
  gap: 11px;
  max-width: min(820px, 92%);
  margin-bottom: 22px;
}

.message-row.is-user {
  flex-direction: row-reverse;
  margin-left: auto;
}

.message-avatar {
  flex: 0 0 auto;
  color: #1d4ed8;
  background: #dbeafe;
  font-size: 0.72rem;
  font-weight: 750;
}

.is-user .message-avatar {
  color: #fff;
  background: #334155;
}

.message-bubble {
  min-width: 0;
  padding: 12px 15px;
  border: 1px solid #e5eaf1;
  border-radius: 4px 14px 14px;
  color: #344258;
  background: #f8fafc;
}

.is-user .message-bubble {
  border-color: #2563eb;
  border-radius: 14px 4px 14px 14px;
  color: #fff;
  background: #2563eb;
}

.user-content {
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-size: 0.92rem;
  line-height: 1.65;
}

.citation-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid #e1e7ef;
}

.citation-label {
  width: 100%;
  color: #8491a5;
  font-size: 0.68rem;
  font-weight: 650;
}

.citation-chip {
  padding: 4px 7px;
  border: 1px solid transparent;
  border-radius: 6px;
  color: #3b5f91;
  background: #eaf2ff;
  font-family: inherit;
  font-size: 0.68rem;
  cursor: pointer;
  transition: 0.18s ease;
}

.citation-chip:hover,
.citation-chip.is-active {
  border-color: #2563eb;
  color: #fff;
  background: #2563eb;
  box-shadow: 0 0 0 3px rgb(37 99 235 / 10%);
}

.loading-bubble {
  display: flex;
  align-items: center;
  gap: 9px;
  color: #7b8799;
  font-size: 0.78rem;
}

.loading-dots {
  display: inline-flex;
  gap: 3px;
}

.loading-dots i {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #60a5fa;
  animation: pulse 1.1s infinite ease-in-out;
}

.loading-dots i:nth-child(2) {
  animation-delay: 0.15s;
}

.loading-dots i:nth-child(3) {
  animation-delay: 0.3s;
}

.composer {
  display: flex;
  align-items: flex-end;
  gap: 11px;
  padding: 16px 20px;
  border-top: 1px solid #e8ecf2;
  background: #fff;
}

.composer :deep(.el-textarea__inner) {
  min-height: 44px !important;
  padding: 11px 13px;
  border-radius: 11px;
  line-height: 1.55;
  box-shadow: 0 0 0 1px #dce3ec inset;
}

.send-button {
  min-width: 84px;
  height: 44px;
  border-radius: 10px;
  font-weight: 650;
}

@keyframes pulse {
  0%,
  70%,
  100% {
    opacity: 0.35;
    transform: translateY(0);
  }

  35% {
    opacity: 1;
    transform: translateY(-3px);
  }
}

@media (max-width: 680px) {
  .chat-workspace {
    height: calc(100vh - 114px);
    min-height: 460px;
    flex-direction: column;
  }

  .chat-page {
    height: auto;
    min-height: 460px;
    border-radius: 12px;
  }

  .chat-heading {
    padding: 15px 16px;
  }

  .chat-heading .el-tag,
  .chat-heading div > span {
    display: none;
  }

  .chat-scroll {
    padding: 20px 13px;
  }

  .message-row {
    max-width: 96%;
  }

  .composer {
    padding: 12px;
  }

  .send-button {
    min-width: 68px;
  }
}
</style>
