<script setup lang="ts">
import { computed } from "vue";

import { renderMarkdown } from "@/utils/markdown";

const props = defineProps<{
  content: string;
  activeCitationId?: string | null;
}>();
const emit = defineEmits<{
  citationClick: [citationId: string];
}>();
const renderedContent = computed<string>(() => {
  const html = renderMarkdown(props.content);
  const citationId = props.activeCitationId?.toUpperCase();
  if (citationId === undefined || !/^S\d+$/.test(citationId)) {
    return html;
  }
  return html.replaceAll(
    `class="citation-reference" data-citation-id="${citationId}"`,
    `class="citation-reference is-active" data-citation-id="${citationId}"`,
  );
});

/** Emit a validated citation identifier from delegated rendered-content clicks. */
function handleContentClick(event: MouseEvent): void {
  const target = event.target;
  if (!(target instanceof Element)) {
    return;
  }
  const reference = target.closest<HTMLButtonElement>(".citation-reference");
  const citationId = reference?.dataset.citationId;
  if (citationId !== undefined && /^S\d+$/.test(citationId)) {
    emit("citationClick", citationId);
  }
}
</script>

<template>
  <!-- renderMarkdown escapes all source HTML before adding controlled markup. -->
  <div
    class="markdown-content"
    v-html="renderedContent"
    @click="handleContentClick"
  />
</template>

<style scoped>
.markdown-content {
  min-width: 0;
  overflow-wrap: anywhere;
  color: inherit;
  font-size: 0.92rem;
  line-height: 1.72;
}

.markdown-content :deep(> :first-child) {
  margin-top: 0;
}

.markdown-content :deep(> :last-child) {
  margin-bottom: 0;
}

.markdown-content :deep(p) {
  margin: 0.55em 0;
}

.markdown-content :deep(h1),
.markdown-content :deep(h2),
.markdown-content :deep(h3),
.markdown-content :deep(h4),
.markdown-content :deep(h5),
.markdown-content :deep(h6) {
  margin: 1em 0 0.45em;
  color: #162033;
  line-height: 1.3;
}

.markdown-content :deep(h1) {
  font-size: 1.35rem;
}

.markdown-content :deep(h2) {
  font-size: 1.18rem;
}

.markdown-content :deep(h3) {
  font-size: 1.05rem;
}

.markdown-content :deep(ul),
.markdown-content :deep(ol) {
  margin: 0.65em 0;
  padding-left: 1.5em;
}

.markdown-content :deep(li) {
  margin: 0.28em 0;
}

.markdown-content :deep(blockquote) {
  margin: 0.8em 0;
  padding: 0.45em 0.85em;
  border-left: 3px solid #60a5fa;
  color: #526079;
  background: #eff6ff;
}

.markdown-content :deep(a) {
  color: #2563eb;
  text-decoration: none;
}

.markdown-content :deep(a:hover) {
  text-decoration: underline;
}

.markdown-content :deep(.citation-reference) {
  display: inline-flex;
  align-items: center;
  margin: 0 2px;
  padding: 1px 5px;
  border: 1px solid #bfdbfe;
  border-radius: 5px;
  color: #1d4ed8;
  background: #eff6ff;
  font: inherit;
  font-size: 0.82em;
  font-weight: 700;
  cursor: pointer;
  transition: 0.18s ease;
}

.markdown-content :deep(.citation-reference:hover),
.markdown-content :deep(.citation-reference.is-active) {
  border-color: #2563eb;
  color: #fff;
  background: #2563eb;
  box-shadow: 0 0 0 3px rgb(37 99 235 / 12%);
}

.markdown-content :deep(:not(pre) > code) {
  padding: 0.14em 0.38em;
  border: 1px solid #dbe4f0;
  border-radius: 5px;
  color: #be123c;
  background: #f8fafc;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 0.84em;
}

.markdown-content :deep(.code-block) {
  margin: 0.9em 0;
  overflow: auto;
  border: 1px solid #263348;
  border-radius: 10px;
  color: #dbeafe;
  background: #111827;
}

.markdown-content :deep(.code-header) {
  position: sticky;
  left: 0;
  padding: 7px 13px;
  border-bottom: 1px solid #29364a;
  color: #7f91ad;
  background: #182235;
  font-family: ui-sans-serif, system-ui, sans-serif;
  font-size: 0.66rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.markdown-content :deep(.code-block code) {
  display: block;
  min-width: max-content;
  padding: 14px 16px;
  white-space: pre;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 0.82rem;
  line-height: 1.65;
}

.markdown-content :deep(.token-keyword) {
  color: #c084fc;
}

.markdown-content :deep(.token-string) {
  color: #86efac;
}

.markdown-content :deep(.token-comment) {
  color: #64748b;
  font-style: italic;
}

.markdown-content :deep(.token-number) {
  color: #fbbf24;
}

.markdown-content :deep(.token-plain) {
  color: #bfdbfe;
}
</style>
