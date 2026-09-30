import { ref } from "vue";
import { defineStore } from "pinia";

import {
  createUser,
  getUserErrorMessage,
  listUsers,
  updateUserRole,
  updateUserStatus,
  type ManagedUser,
  type ManagedUserCreate,
  type UserRole,
} from "@/api/users";

export type {
  ManagedUser,
  ManagedUserCreate,
  UserRole,
} from "@/api/users";

export const useAdminStore = defineStore("admin", () => {
  const users = ref<ManagedUser[]>([]);
  const loading = ref(false);
  const saving = ref(false);

  /** Load every account visible to the current administrator. */
  async function loadUsers(): Promise<void> {
    loading.value = true;
    try {
      users.value = await listUsers();
    } finally {
      loading.value = false;
    }
  }

  /** Create and prepend a managed user account. */
  async function addUser(payload: ManagedUserCreate): Promise<ManagedUser> {
    saving.value = true;
    try {
      const user = await createUser(payload);
      users.value.unshift(user);
      return user;
    } finally {
      saving.value = false;
    }
  }

  /** Persist and merge an account activation state. */
  async function setUserActive(userId: number, isActive: boolean): Promise<void> {
    const updated = await updateUserStatus(userId, isActive);
    replaceUser(updated);
  }

  /** Persist and merge an account role. */
  async function setUserRole(userId: number, role: UserRole): Promise<void> {
    const updated = await updateUserRole(userId, role);
    replaceUser(updated);
  }

  /** Replace one account in local state. */
  function replaceUser(updated: ManagedUser): void {
    users.value = users.value.map((user) =>
      user.id === updated.id ? updated : user,
    );
  }

  /** Resolve a user-facing message from a failed administrator action. */
  function errorMessage(error: unknown): string | undefined {
    return getUserErrorMessage(error);
  }

  return {
    users,
    loading,
    saving,
    loadUsers,
    addUser,
    setUserActive,
    setUserRole,
    errorMessage,
  };
});
