import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import ElementPlus, { ElMessage, type MessageHandler } from "element-plus";
import { createPinia, setActivePinia } from "pinia";
import { defineComponent } from "vue";
import {
  createMemoryHistory,
  createRouter,
  type Router,
} from "vue-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AuthUser } from "@/api/auth";
import MainLayout from "@/layouts/MainLayout.vue";
import { useAuthStore } from "@/stores/auth";

/** Create a layout test user with configurable administrator access. */
function createUser(isAdmin: boolean): AuthUser {
  return {
    id: 1,
    username: isAdmin ? "admin-user" : "standard-user",
    is_admin: isAdmin,
    is_active: true,
    created_at: "2026-07-16T00:00:00Z",
  };
}

/** Mount MainLayout with an authenticated in-memory Pinia and router. */
async function mountLayout(isAdmin: boolean): Promise<{
  wrapper: VueWrapper;
  router: Router;
  logout: ReturnType<typeof vi.fn>;
}> {
  const pinia = createPinia();
  setActivePinia(pinia);
  const authStore = useAuthStore();
  authStore.user = createUser(isAdmin);
  authStore.initialized = true;
  const logout = vi.fn().mockResolvedValue(undefined);
  authStore.logout = logout;
  const page = defineComponent({ template: "<div>main-content</div>" });
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", component: page, meta: { title: "\u804a\u5929" } },
      { path: "/login", name: "login", component: page },
    ],
  });
  await router.push("/");
  await router.isReady();
  const wrapper = mount(MainLayout, {
    attachTo: document.body,
    global: { plugins: [pinia, router, ElementPlus] },
  });
  return { wrapper, router, logout };
}

describe("MainLayout", () => {
  afterEach(() => {
    document.body.innerHTML = "";
    document.documentElement.classList.remove("dark");
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("renders header, sidebar navigation, user information, and main content", async () => {
    const { wrapper } = await mountLayout(false);
    const text = wrapper.text();

    expect(text).toContain("standard-user");
    expect(text).toContain("\u804a\u5929");
    expect(text).toContain("\u5386\u53f2\u8bb0\u5f55");
    expect(text).not.toContain("\u6587\u6863\u7ba1\u7406");
    expect(text).not.toContain("\u8bbe\u7f6e");
    expect(text).toContain("main-content");
    expect(text).not.toContain("\u7528\u6237\u7ba1\u7406");
    expect(wrapper.find('[aria-label="\u6253\u5f00\u5bfc\u822a\u83dc\u5355"]').exists()).toBe(true);
    wrapper.unmount();
  });

  it("shows user management only for an administrator", async () => {
    const { wrapper } = await mountLayout(true);
    const menuText = wrapper.find(".sidebar-menu").text();

    expect(wrapper.text()).toContain("admin-user");
    expect(wrapper.text()).toContain("\u7ba1\u7406\u5458");
    expect(menuText).toContain("\u7528\u6237\u7ba1\u7406");
    expect(menuText).toContain("\u6587\u6863\u7ba1\u7406");
    expect(menuText).not.toContain("\u5386\u53f2\u8bb0\u5f55");
    expect(wrapper.text()).toContain("ADMIN");
    wrapper.unmount();
  });

  it("logs out and navigates to the login page", async () => {
    const successMessage = vi
      .spyOn(ElMessage, "success")
      .mockReturnValue({ close: vi.fn() } as MessageHandler);
    const { wrapper, router, logout } = await mountLayout(false);
    const logoutButton = wrapper
      .findAll("button")
      .find((button) => button.text().includes("\u9000\u51fa\u767b\u5f55"));

    expect(logoutButton).toBeDefined();
    await logoutButton?.trigger("click");
    await flushPromises();

    expect(logout).toHaveBeenCalledOnce();
    expect(successMessage).toHaveBeenCalledWith("\u5df2\u9000\u51fa\u767b\u5f55");
    expect(router.currentRoute.value.fullPath).toBe("/login");
    wrapper.unmount();
  });

  it("toggles and persists dark mode", async () => {
    const { wrapper } = await mountLayout(false);
    const themeButton = wrapper.find('[aria-label="切换深色模式"]');

    await themeButton.trigger("click");

    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem("network-rag-theme")).toBe("dark");
    expect(wrapper.find('[aria-label="切换浅色模式"]').exists()).toBe(true);
    wrapper.unmount();
  });
});
