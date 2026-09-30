import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as authApi from "@/api/auth";
import apiClient from "@/api/api";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/api/auth", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/api/auth")>();
  return {
    ...original,
    loginRequest: vi.fn(),
    getCurrentUser: vi.fn(),
    logoutRequest: vi.fn(),
  };
});

const user: authApi.AuthUser = {
  id: 1,
  username: "network-admin",
  is_admin: true,
  is_active: true,
  created_at: "2026-07-16T00:00:00Z",
};

describe("auth store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it("uses Cookie credentials and never configures a bearer token", () => {
    expect(apiClient.defaults.withCredentials).toBe(true);
    expect(apiClient.defaults.headers.common.Authorization).toBeUndefined();
  });

  it("stores the authenticated user only in Pinia memory", async () => {
    vi.mocked(authApi.loginRequest).mockResolvedValue(user);
    const storageSpy = vi.spyOn(Storage.prototype, "setItem");
    const store = useAuthStore();

    await store.login({
      username: "network-admin",
      password: "password123",
    });

    expect(authApi.loginRequest).toHaveBeenCalledWith({
      username: "network-admin",
      password: "password123",
    });
    expect(store.user).toEqual(user);
    expect(store.isAuthenticated).toBe(true);
    expect(store.initialized).toBe(true);
    expect(storageSpy).not.toHaveBeenCalled();
    storageSpy.mockRestore();
  });

  it("restores the Cookie session once through GET auth me", async () => {
    vi.mocked(authApi.getCurrentUser).mockResolvedValue(user);
    const store = useAuthStore();

    await store.restoreSession();
    await store.restoreSession();

    expect(authApi.getCurrentUser).toHaveBeenCalledTimes(1);
    expect(store.user).toEqual(user);
    expect(store.isAuthenticated).toBe(true);
  });

  it("treats an expired Cookie as a signed-out initialized session", async () => {
    vi.mocked(authApi.getCurrentUser).mockRejectedValue(new Error("Unauthorized"));
    const store = useAuthStore();

    await expect(store.restoreSession()).resolves.toBeUndefined();

    expect(store.user).toBeNull();
    expect(store.isAuthenticated).toBe(false);
    expect(store.initialized).toBe(true);
  });

  it("clears in-memory state when login fails", async () => {
    vi.mocked(authApi.loginRequest).mockRejectedValue(new Error("Invalid login"));
    const store = useAuthStore();

    await expect(
      store.login({ username: "bad-user", password: "bad-password" }),
    ).rejects.toThrow("Invalid login");

    expect(store.user).toBeNull();
    expect(store.isAuthenticated).toBe(false);
    expect(store.loading).toBe(false);
  });
});
