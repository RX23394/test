<script setup lang="ts">
const COPY = {
  title: "\u5f00\u59cb\u4e00\u6b21\u77e5\u8bc6\u5e93\u5bf9\u8bdd",
  description: "\u4ece\u5df2\u7d22\u5f15\u7684\u7f51\u7edc\u6587\u6863\u4e2d\u68c0\u7d22\u7b54\u6848\uff0c\u5e76\u67e5\u770b\u53ef\u8ffd\u6eaf\u7684\u539f\u6587\u5f15\u7528\u3002",
  ready: "\u804a\u5929\u5de5\u4f5c\u533a\u5df2\u5c31\u7eea",
} as const;
</script>

<template>
  <section class="chat-home">
    <div class="welcome-copy">
      <p>AI NETWORK ASSISTANT</p>
      <h2>{{ COPY.title }}</h2>
      <span>{{ COPY.description }}</span>
    </div>

    <div class="chat-stage">
      <div class="stage-mark">NR</div>
      <h3>Network RAG</h3>
      <p>{{ COPY.ready }}</p>
    </div>
  </section>
</template>

<style scoped>
.chat-home {
  min-height: calc(100vh - 138px);
  overflow: hidden;
  border: 1px solid #e7eaf0;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 8px 30px rgb(15 23 42 / 4%);
}

.welcome-copy {
  padding: clamp(26px, 5vw, 46px);
  border-bottom: 1px solid #edf0f5;
  background: linear-gradient(130deg, #f8fbff, #fff 60%);
}

.welcome-copy > p {
  margin: 0 0 8px;
  color: #2563eb;
  font-size: 0.68rem;
  font-weight: 750;
  letter-spacing: 0.14em;
}

h2 {
  margin: 0 0 10px;
  color: #162033;
  font-size: clamp(1.45rem, 4vw, 2rem);
  letter-spacing: -0.04em;
}

.welcome-copy span {
  color: #64748b;
  line-height: 1.65;
}

.chat-stage {
  display: grid;
  min-height: 360px;
  place-items: center;
  align-content: center;
  color: #94a3b8;
  text-align: center;
}

.stage-mark {
  display: grid;
  width: 56px;
  height: 56px;
  margin-bottom: 14px;
  place-items: center;
  border-radius: 16px;
  color: #2563eb;
  background: #eff6ff;
  font-weight: 800;
}

.chat-stage h3,
.chat-stage p {
  margin: 0;
}

.chat-stage h3 {
  color: #334155;
  font-size: 1rem;
}

.chat-stage p {
  margin-top: 5px;
  font-size: 0.82rem;
}
</style>
