import { computed, ref } from "vue";
import { defineStore } from "pinia";

import {
  getCurrentUser,
  getAuthErrorMessage,
  loginRequest,
  logoutRequest,
  type AuthUser,
  type LoginCredentials,
} from "@/api/auth";

export type { AuthUser, LoginCredentials } from "@/api/auth";

export const useAuthStore = defineStore("auth", () => {
  const user = ref<AuthUser | null>(null);
  const initialized = ref(false);
  const loading = ref(false);
  const isAuthenticated = computed<boolean>(() => user.value !== null);

  /** Authenticate and keep only public user state in memory. */
  async function login(credentials: LoginCredentials): Promise<AuthUser> {
    loading.value = true;
    try {
      const authenticatedUser = await loginRequest(credentials);
      user.value = authenticatedUser;
      initialized.value = true;
      return authenticatedUser;
    } catch (error: unknown) {
      user.value = null;
      initialized.value = true;
      throw error;
    } finally {
      loading.value = false;
    }
  }

  /** Restore Cookie authentication after a browser refresh. */
  async function restoreSession(): Promise<void> {
    if (initialized.value) {
      return;
    }
    loading.value = true;
    try {
      user.value = await getCurrentUser();
    } catch {
      user.value = null;
    } finally {
      initialized.value = true;
      loading.value = false;
    }
  }

  /** Clear the server Cookie and all in-memory user state. */
  async function logout(): Promise<void> {
    loading.value = true;
    try {
      await logoutRequest();
    } finally {
      user.value = null;
      initialized.value = true;
      loading.value = false;
    }
  }

  /** Resolve a user-facing authentication error message. */
  function errorMessage(error: unknown): string | undefined {
    return getAuthErrorMessage(error);
  }

  return {
    user,
    initialized,
    loading,
    isAuthenticated,
    login,
    restoreSession,
    logout,
    errorMessage,
  };
});
