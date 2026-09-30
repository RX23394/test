import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  getCurrentUser,
  loginRequest,
  type AuthUser,
} from "@/api/auth";
import apiClient from "@/api/api";

vi.mock("@/api/api", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

const user: AuthUser = {
  id: 1,
  username: "network-admin",
  is_admin: true,
  is_active: true,
  created_at: "2026-07-16T00:00:00Z",
};

describe("auth API", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("restores a refreshed session with GET api auth me", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: { status: "ok", data: user },
    });

    await expect(getCurrentUser()).resolves.toEqual(user);

    expect(apiClient.get).toHaveBeenCalledWith("/api/auth/me");
  });

  it("posts credentials without constructing a client-side token", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      data: { status: "ok", data: user },
    });

    await expect(
      loginRequest({
        username: "network-admin",
        password: "password123",
      }),
    ).resolves.toEqual(user);

    expect(apiClient.post).toHaveBeenCalledWith("/api/auth/login", {
      username: "network-admin",
      password: "password123",
    });
  });
});
