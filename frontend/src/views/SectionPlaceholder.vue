<script setup lang="ts">
const EMPTY_DESCRIPTION = "\u529f\u80fd\u533a\u57df\u5df2\u51c6\u5907\u5c31\u7eea";
defineProps<{
  title: string;
  description: string;
}>();
</script>

<template>
  <section class="section-card">
    <p class="section-label">NETWORK RAG</p>
    <h2>{{ title }}</h2>
    <p>{{ description }}</p>
    <el-empty :description="EMPTY_DESCRIPTION" :image-size="96" />
  </section>
</template>

<style scoped>
.section-card {
  min-height: calc(100vh - 138px);
  padding: clamp(24px, 5vw, 44px);
  border: 1px solid #e7eaf0;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 8px 30px rgb(15 23 42 / 4%);
}

.section-label {
  margin: 0 0 8px;
  color: #2563eb;
  font-size: 0.68rem;
  font-weight: 750;
  letter-spacing: 0.14em;
}

h2 {
  margin: 0;
  color: #162033;
  font-size: 1.65rem;
  letter-spacing: -0.035em;
}

.section-card > p:not(.section-label) {
  max-width: 620px;
  margin: 10px 0 8px;
  color: #64748b;
  line-height: 1.65;
}
</style>
