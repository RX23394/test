import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import ElementPlus, { ElMessage, type MessageHandler } from "element-plus";
import { createPinia, setActivePinia, type Pinia } from "pinia";
import { defineComponent } from "vue";
import {
  createMemoryHistory,
  createRouter,
  type Router,
} from "vue-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as authApi from "@/api/auth";
import LoginView from "@/views/LoginView.vue";

vi.mock("@/api/auth", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/api/auth")>();
  return {
    ...original,
    loginRequest: vi.fn(),
    getCurrentUser: vi.fn(),
    logoutRequest: vi.fn(),
  };
});

const authenticatedUser: authApi.AuthUser = {
  id: 1,
  username: "network-admin",
  is_admin: true,
  is_active: true,
  created_at: "2026-07-16T00:00:00Z",
};

/** Create an isolated router for LoginView navigation assertions. */
function createTestRouter(): Router {
  const page = defineComponent({ template: "<div>page</div>" });
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", name: "home", component: page },
      { path: "/documents", name: "documents", component: page },
      { path: "/login", name: "login", component: LoginView },
    ],
  });
}

/** Mount the login page with real Pinia, Router, and Element Plus plugins. */
async function mountLoginView(): Promise<{
  wrapper: VueWrapper;
  router: Router;
  pinia: Pinia;
}> {
  const pinia = createPinia();
  setActivePinia(pinia);
  const router = createTestRouter();
  await router.push("/login");
  await router.isReady();
  const wrapper = mount(LoginView, {
    attachTo: document.body,
    global: { plugins: [pinia, router, ElementPlus] },
  });
  return { wrapper, router, pinia };
}

/** Fill valid credentials and submit the login form. */
async function submitCredentials(wrapper: VueWrapper): Promise<void> {
  await wrapper.find('input[name="username"]').setValue("network-admin");
  await wrapper.find('input[name="password"]').setValue("password123");
  await wrapper.find("form").trigger("submit");
  await flushPromises();
}

describe("LoginView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("navigates an administrator to documents after login", async () => {
    vi.mocked(authApi.loginRequest).mockResolvedValue(authenticatedUser);
    const { wrapper, router } = await mountLoginView();

    await submitCredentials(wrapper);

    expect(authApi.loginRequest).toHaveBeenCalledWith({
      username: "network-admin",
      password: "password123",
    });
    expect(router.currentRoute.value.fullPath).toBe("/documents");
    wrapper.unmount();
  });

  it("navigates a standard user to chat after login", async () => {
    vi.mocked(authApi.loginRequest).mockResolvedValue({
      ...authenticatedUser,
      is_admin: false,
    });
    const { wrapper, router } = await mountLoginView();

    await submitCredentials(wrapper);

    expect(router.currentRoute.value.fullPath).toBe("/");
    wrapper.unmount();
  });

  it("shows Element Plus Message when login fails", async () => {
    vi.mocked(authApi.loginRequest).mockRejectedValue(
      new Error("Invalid username or password"),
    );
    const messageSpy = vi
      .spyOn(ElMessage, "error")
      .mockReturnValue({ close: vi.fn() } as MessageHandler);
    const { wrapper, router } = await mountLoginView();

    await submitCredentials(wrapper);

    expect(messageSpy).toHaveBeenCalledWith("Invalid username or password");
    expect(router.currentRoute.value.fullPath).toBe("/login");
    wrapper.unmount();
    messageSpy.mockRestore();
  });
});
