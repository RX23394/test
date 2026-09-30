import axios, { type AxiosResponse } from "axios";

import type { ResponseModel } from "@/api/auth";
import apiClient from "@/api/api";

export type UserRole = "admin" | "user";

export interface ManagedUser {
  id: number;
  username: string;
  role: UserRole;
  is_admin: boolean;
  is_active: boolean;
  created_at: string;
}

export interface ManagedUserCreate {
  username: string;
  password: string;
  role: UserRole;
}

/** Fetch every account visible to an administrator. */
export async function listUsers(): Promise<ManagedUser[]> {
  const response: AxiosResponse<ResponseModel<ManagedUser[]>> =
    await apiClient.get("/api/admin/users");
  return requireData(response.data);
}

/** Create a new active account with the selected role. */
export async function createUser(payload: ManagedUserCreate): Promise<ManagedUser> {
  const response: AxiosResponse<ResponseModel<ManagedUser>> =
    await apiClient.post("/api/admin/users", payload);
  return requireData(response.data);
}

/** Activate or deactivate a managed account. */
export async function updateUserStatus(
  userId: number,
  isActive: boolean,
): Promise<ManagedUser> {
  const response: AxiosResponse<ResponseModel<ManagedUser>> =
    await apiClient.patch(`/api/admin/users/${userId}/status`, {
      is_active: isActive,
    });
  return requireData(response.data);
}

/** Assign an administrator or standard user role. */
export async function updateUserRole(
  userId: number,
  role: UserRole,
): Promise<ManagedUser> {
  const response: AxiosResponse<ResponseModel<ManagedUser>> =
    await apiClient.patch(`/api/admin/users/${userId}/role`, { role });
  return requireData(response.data);
}

/** Return a uniform server message for a failed user request. */
export function getUserErrorMessage(error: unknown): string | undefined {
  if (!axios.isAxiosError<ResponseModel<unknown>>(error)) {
    return undefined;
  }
  return error.response?.data.message;
}

/** Extract successful data from the uniform response envelope. */
function requireData<T>(response: ResponseModel<T>): T {
  if (response.status !== "ok" || response.data === undefined) {
    throw new Error(response.message ?? "User request failed");
  }
  return response.data;
}
