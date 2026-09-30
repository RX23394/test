<script setup lang="ts">
import { reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  ElMessage,
  type FormInstance,
  type FormRules,
} from "element-plus";

import { type LoginCredentials, useAuthStore } from "@/stores/auth";

const COPY = {
  title: "\u767b\u5f55 Network RAG",
  subtitle: "\u4f7f\u7528\u4f60\u7684\u8d26\u6237\u8bbf\u95ee\u7f51\u7edc\u5de5\u7a0b\u77e5\u8bc6\u5e93",
  username: "\u7528\u6237\u540d",
  password: "\u5bc6\u7801",
  usernamePlaceholder: "\u8bf7\u8f93\u5165\u7528\u6237\u540d",
  passwordPlaceholder: "\u8bf7\u8f93\u5165\u5bc6\u7801",
  submit: "\u767b\u5f55",
  security: "\u767b\u5f55\u51ed\u8bc1\u7531\u5b89\u5168\u7684 HttpOnly Cookie \u7ba1\u7406",
  invalidLogin: "\u767b\u5f55\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u7528\u6237\u540d\u548c\u5bc6\u7801",
  retryLogin: "\u767b\u5f55\u5931\u8d25\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5",
} as const;

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const formRef = ref<FormInstance>();
const form = reactive<LoginCredentials>({
  username: "",
  password: "",
});
const rules: FormRules<LoginCredentials> = {
  username: [
    { required: true, message: COPY.usernamePlaceholder, trigger: "blur" },
    { min: 3, max: 64, message: "\u7528\u6237\u540d\u957f\u5ea6\u4e3a 3-64 \u4e2a\u5b57\u7b26", trigger: "blur" },
  ],
  password: [
    { required: true, message: COPY.passwordPlaceholder, trigger: "blur" },
    { min: 8, max: 256, message: "\u5bc6\u7801\u81f3\u5c11\u9700\u8981 8 \u4e2a\u5b57\u7b26", trigger: "blur" },
  ],
};

/** Validate credentials, authenticate with Cookie, and navigate home. */
async function submitLogin(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) {
    return;
  }

  try {
    await authStore.login({ ...form });
    await router.replace(resolveRedirect());
  } catch (error: unknown) {
    ElMessage.error(getLoginErrorMessage(error));
  }
}

/** Return a local redirect path or the current role's landing page. */
function resolveRedirect(): string {
  const redirect = route.query.redirect;
  if (
    typeof redirect === "string" &&
    redirect.startsWith("/") &&
    !redirect.startsWith("//")
  ) {
    return redirect;
  }
  return authStore.user?.is_admin ? "/documents" : "/";
}

/** Extract a safe backend error message for Element Plus feedback. */
function getLoginErrorMessage(error: unknown): string {
  const apiMessage = authStore.errorMessage(error);
  if (apiMessage) return apiMessage;
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return COPY.retryLogin;
}
</script>

<template>
  <main class="login-page">
    <section class="login-panel" aria-labelledby="login-title">
      <div class="brand" aria-hidden="true">NR</div>
      <p class="eyebrow">NETWORK KNOWLEDGE</p>
      <h1 id="login-title">{{ COPY.title }}</h1>
      <p class="subtitle">{{ COPY.subtitle }}</p>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        class="login-form"
        @submit.prevent="submitLogin"
      >
        <el-form-item :label="COPY.username" prop="username">
          <el-input
            v-model="form.username"
            name="username"
            autocomplete="username"
            :placeholder="COPY.usernamePlaceholder"
            size="large"
            clearable
          />
        </el-form-item>

        <el-form-item :label="COPY.password" prop="password">
          <el-input
            v-model="form.password"
            name="password"
            type="password"
            autocomplete="current-password"
            :placeholder="COPY.passwordPlaceholder"
            size="large"
            show-password
            @keyup.enter="submitLogin"
          />
        </el-form-item>

        <el-button
          type="primary"
          native-type="submit"
          size="large"
          class="submit-button"
          :loading="authStore.loading"
        >
          {{ COPY.submit }}
        </el-button>
      </el-form>

      <p class="security-note">{{ COPY.security }}</p>
    </section>
  </main>
</template>

<style scoped>
.login-page {
  display: grid;
  min-height: 100vh;
  place-items: center;
  padding: 32px 20px;
  background:
    radial-gradient(circle at 20% 10%, rgb(37 99 235 / 16%), transparent 34%),
    radial-gradient(circle at 90% 85%, rgb(14 165 233 / 14%), transparent 30%),
    #f5f7fb;
}

.login-panel {
  width: min(100%, 420px);
  padding: 42px 40px 36px;
  border: 1px solid rgb(148 163 184 / 22%);
  border-radius: 20px;
  background: rgb(255 255 255 / 94%);
  box-shadow: 0 24px 70px rgb(15 23 42 / 12%);
  backdrop-filter: blur(18px);
}

.brand {
  display: grid;
  width: 48px;
  height: 48px;
  margin-bottom: 24px;
  place-items: center;
  border-radius: 14px;
  color: #fff;
  background: linear-gradient(135deg, #2563eb, #0284c7);
  box-shadow: 0 10px 24px rgb(37 99 235 / 24%);
  font-weight: 750;
  letter-spacing: -0.04em;
}

.eyebrow {
  margin: 0 0 8px;
  color: #2563eb;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.14em;
}

h1 {
  margin: 0;
  color: #0f172a;
  font-size: clamp(1.65rem, 5vw, 2rem);
  line-height: 1.2;
  letter-spacing: -0.035em;
}

.subtitle {
  margin: 10px 0 30px;
  color: #64748b;
  font-size: 0.95rem;
}

.login-form :deep(.el-form-item__label) {
  color: #334155;
  font-weight: 600;
}

.login-form :deep(.el-input__wrapper) {
  border-radius: 10px;
}

.submit-button {
  width: 100%;
  margin-top: 8px;
  border-radius: 10px;
  font-weight: 650;
}

.security-note {
  margin: 22px 0 0;
  color: #94a3b8;
  font-size: 0.76rem;
  text-align: center;
}

@media (max-width: 520px) {
  .login-page {
    padding: 0;
    background: #fff;
  }

  .login-panel {
    min-height: 100vh;
    padding: 56px 24px 32px;
    border: 0;
    border-radius: 0;
    box-shadow: none;
  }
}
</style>
