import axios, { type AxiosResponse } from "axios";

import apiClient from "@/api/api";

export interface ResponseModel<T> {
  status: "ok" | "error";
  data?: T;
  message?: string;
}

export interface LoginCredentials {
  username: string;
  password: string;
}

export interface AuthUser {
  id: number;
  username: string;
  is_admin: boolean;
  is_active: boolean;
  created_at: string;
}

/** Authenticate with an HttpOnly Cookie response. */
export async function loginRequest(
  credentials: LoginCredentials,
): Promise<AuthUser> {
  const response: AxiosResponse<ResponseModel<AuthUser>> = await apiClient.post(
    "/api/auth/login",
    credentials,
  );
  return requireData(response.data);
}

/** Load the user represented by the current authentication Cookie. */
export async function getCurrentUser(): Promise<AuthUser> {
  const response: AxiosResponse<ResponseModel<AuthUser>> = await apiClient.get(
    "/api/auth/me",
  );
  return requireData(response.data);
}

/** Clear the server-managed authentication Cookie. */
export async function logoutRequest(): Promise<void> {
  await apiClient.post("/api/auth/logout");
}

/** Return a backend authentication error message when available. */
export function getAuthErrorMessage(error: unknown): string | undefined {
  if (!axios.isAxiosError<ResponseModel<unknown>>(error)) {
    return undefined;
  }
  return error.response?.data.message;
}

/** Extract successful payload data from the uniform API envelope. */
function requireData<T>(response: ResponseModel<T>): T {
  if (response.status !== "ok" || response.data === undefined) {
    throw new Error(response.message ?? "Authentication request failed");
  }
  return response.data;
}
