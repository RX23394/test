<script setup lang="ts">
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";

import { useAuthStore } from "@/stores/auth";
import { applyTheme } from "@/utils/theme";

interface NavigationItem {
  path: string;
  label: string;
  role: "admin" | "user";
}

const COPY = {
  openMenu: "\u6253\u5f00\u5bfc\u822a\u83dc\u5355",
  admin: "\u7ba1\u7406\u5458",
  user: "\u666e\u901a\u7528\u6237",
  logout: "\u9000\u51fa\u767b\u5f55",
} as const;

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const mobileMenuOpen = ref(false);
const darkMode = ref(document.documentElement.classList.contains("dark"));
const navigationItems: NavigationItem[] = [
  { path: "/", label: "\u804a\u5929", role: "user" },
  { path: "/history", label: "\u5386\u53f2\u8bb0\u5f55", role: "user" },
  {
    path: "/documents",
    label: "\u6587\u6863\u7ba1\u7406",
    role: "admin",
  },
  { path: "/admin/users", label: "\u7528\u6237\u7ba1\u7406", role: "admin" },
];
const visibleNavigationItems = computed<NavigationItem[]>(() => {
  const role = authStore.user?.is_admin ? "admin" : "user";
  return navigationItems.filter((item) => item.role === role);
});
const pageTitle = computed<string>(() =>
  typeof route.meta.title === "string" ? route.meta.title : "Network RAG",
);
const userInitial = computed<string>(() =>
  authStore.user?.username.slice(0, 1).toUpperCase() ?? "U",
);

/** Close the mobile navigation after a route is selected. */
function closeMobileMenu(): void {
  mobileMenuOpen.value = false;
}

/** Toggle and persist the application color theme. */
function toggleDarkMode(): void {
  darkMode.value = !darkMode.value;
  applyTheme(darkMode.value);
}

/** Clear the Cookie session and return to the login page. */
async function handleLogout(): Promise<void> {
  try {
    await authStore.logout();
    ElMessage.success("\u5df2\u9000\u51fa\u767b\u5f55");
  } catch {
    ElMessage.error("\u9000\u51fa\u767b\u5f55\u5931\u8d25\uff0c\u8bf7\u91cd\u8bd5");
  } finally {
    await router.replace({ name: "login" });
  }
}
</script>

<template>
  <el-container class="app-shell">
    <el-aside width="248px" class="desktop-sidebar">
      <div class="sidebar-brand">
        <span class="brand-mark">NR</span>
        <div>
          <strong>Network RAG</strong>
          <small>Knowledge Console</small>
        </div>
      </div>

      <el-menu
        router
        :default-active="route.path"
        class="sidebar-menu"
        @select="closeMobileMenu"
      >
        <el-menu-item
          v-for="item in visibleNavigationItems"
          :key="item.path"
          :index="item.path"
        >
          <span class="menu-dot" aria-hidden="true" />
          <span>{{ item.label }}</span>
        </el-menu-item>
      </el-menu>

      <div class="sidebar-footer">AI-powered network knowledge</div>
    </el-aside>

    <el-drawer
      v-model="mobileMenuOpen"
      direction="ltr"
      size="280px"
      :with-header="false"
      class="mobile-drawer"
    >
      <div class="sidebar-brand drawer-brand">
        <span class="brand-mark">NR</span>
        <div>
          <strong>Network RAG</strong>
          <small>Knowledge Console</small>
        </div>
      </div>
      <el-menu
        router
        :default-active="route.path"
        class="sidebar-menu drawer-menu"
        @select="closeMobileMenu"
      >
        <el-menu-item
          v-for="item in visibleNavigationItems"
          :key="item.path"
          :index="item.path"
        >
          <span class="menu-dot" aria-hidden="true" />
          <span>{{ item.label }}</span>
        </el-menu-item>
      </el-menu>
    </el-drawer>

    <el-container class="content-shell">
      <el-header class="app-header">
        <div class="header-leading">
          <el-button
            class="mobile-menu-button"
            text
            :aria-label="COPY.openMenu"
            @click="mobileMenuOpen = true"
          >
            <span class="hamburger" aria-hidden="true">MENU</span>
          </el-button>
          <div>
            <p class="header-kicker">WORKSPACE</p>
            <h1>{{ pageTitle }}</h1>
          </div>
        </div>

        <div class="user-actions">
          <el-button
            class="theme-button"
            circle
            :aria-label="darkMode ? '切换浅色模式' : '切换深色模式'"
            @click="toggleDarkMode"
          >
            {{ darkMode ? "☀" : "☾" }}
          </el-button>
          <el-avatar :size="38" class="user-avatar">
            {{ userInitial }}
          </el-avatar>
          <div class="user-copy">
            <strong>{{ authStore.user?.username }}</strong>
            <span>{{ authStore.user?.is_admin ? COPY.admin : COPY.user }}</span>
          </div>
          <el-tag v-if="authStore.user?.is_admin" size="small" effect="plain">
            ADMIN
          </el-tag>
          <el-button
            :loading="authStore.loading"
            class="logout-button"
            @click="handleLogout"
          >
            {{ COPY.logout }}
          </el-button>
        </div>
      </el-header>

      <el-main class="app-main">
        <RouterView />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
  background: #f4f6fa;
}

.desktop-sidebar {
  position: fixed;
  z-index: 20;
  inset: 0 auto 0 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid rgb(148 163 184 / 16%);
  color: #dbeafe;
  background: #111c33;
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 82px;
  padding: 0 22px;
  border-bottom: 1px solid rgb(255 255 255 / 8%);
}

.brand-mark {
  display: grid;
  width: 38px;
  height: 38px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 11px;
  color: #fff;
  background: linear-gradient(135deg, #3b82f6, #06b6d4);
  box-shadow: 0 8px 20px rgb(37 99 235 / 26%);
  font-size: 0.9rem;
  font-weight: 800;
  letter-spacing: -0.04em;
}

.sidebar-brand strong,
.sidebar-brand small {
  display: block;
}

.sidebar-brand strong {
  color: #f8fafc;
  font-size: 0.96rem;
}

.sidebar-brand small {
  margin-top: 3px;
  color: #7f91ad;
  font-size: 0.66rem;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.sidebar-menu {
  flex: 1;
  padding: 16px 12px;
  border-right: 0;
  background: transparent;
}

.sidebar-menu :deep(.el-menu-item) {
  height: 46px;
  margin: 4px 0;
  border-radius: 10px;
  color: #9eacc1;
  font-weight: 550;
}

.sidebar-menu :deep(.el-menu-item:hover) {
  color: #e2e8f0;
  background: rgb(255 255 255 / 6%);
}

.sidebar-menu :deep(.el-menu-item.is-active) {
  color: #fff;
  background: linear-gradient(90deg, rgb(37 99 235 / 38%), rgb(14 165 233 / 13%));
}

.menu-dot {
  width: 7px;
  height: 7px;
  margin-right: 14px;
  border: 1px solid currentcolor;
  border-radius: 50%;
}

.sidebar-menu :deep(.is-active) .menu-dot {
  border-color: #60a5fa;
  background: #60a5fa;
  box-shadow: 0 0 0 4px rgb(96 165 250 / 12%);
}

.sidebar-footer {
  padding: 20px 22px;
  color: #53647f;
  font-size: 0.68rem;
  text-align: center;
}

.content-shell {
  min-width: 0;
  margin-left: 248px;
}

.app-header {
  position: sticky;
  z-index: 10;
  top: 0;
  display: flex;
  height: 82px;
  align-items: center;
  justify-content: space-between;
  padding: 0 30px;
  border-bottom: 1px solid #e7eaf0;
  background: rgb(255 255 255 / 88%);
  backdrop-filter: blur(16px);
}

.header-leading,
.user-actions {
  display: flex;
  align-items: center;
}

.header-leading {
  gap: 10px;
}

.header-kicker {
  margin: 0 0 2px;
  color: #94a3b8;
  font-size: 0.62rem;
  font-weight: 700;
  letter-spacing: 0.15em;
}

.app-header h1 {
  margin: 0;
  color: #172033;
  font-size: 1.18rem;
  letter-spacing: -0.025em;
}

.user-actions {
  gap: 11px;
}

.user-avatar {
  color: #1d4ed8;
  background: #dbeafe;
  font-weight: 700;
}

.user-copy strong,
.user-copy span {
  display: block;
}

.user-copy strong {
  color: #273449;
  font-size: 0.86rem;
}

.user-copy span {
  margin-top: 2px;
  color: #94a3b8;
  font-size: 0.7rem;
}

.logout-button {
  margin-left: 6px;
  border-radius: 9px;
}

.theme-button {
  flex: 0 0 auto;
  color: #475569;
}

.mobile-menu-button {
  display: none;
}

.hamburger {
  font-size: 1.35rem;
}

.app-main {
  min-width: 0;
  padding: 28px 30px;
}

.drawer-brand {
  margin: -20px -20px 0;
  background: #111c33;
}

.drawer-menu :deep(.el-menu-item) {
  color: #475569;
}

.drawer-menu :deep(.el-menu-item:hover),
.drawer-menu :deep(.el-menu-item.is-active) {
  color: #1d4ed8;
  background: #eff6ff;
}

@media (max-width: 860px) {
  .desktop-sidebar {
    display: none;
  }

  .content-shell {
    margin-left: 0;
  }

  .mobile-menu-button {
    display: inline-flex;
    margin-left: -10px;
  }

  .app-header {
    padding: 0 18px;
  }

  .app-main {
    padding: 22px 18px;
  }

  .user-copy,
  .user-actions .el-tag {
    display: none;
  }
}

@media (max-width: 540px) {
  .app-header {
    height: 70px;
  }

  .header-kicker,
  .logout-button {
    display: none;
  }

  .app-header h1 {
    font-size: 1rem;
  }

  .app-main {
    padding: 14px 12px;
  }

  .user-actions {
    gap: 7px;
  }

  .user-avatar {
    display: none;
  }
}
</style>
