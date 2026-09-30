import { beforeEach, describe, expect, it, vi } from "vitest";

import apiClient from "@/api/api";
import {
  createUser,
  listUsers,
  updateUserRole,
  updateUserStatus,
  type ManagedUser,
} from "@/api/users";

vi.mock("@/api/api", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  },
}));

const user: ManagedUser = {
  id: 2,
  username: "member",
  role: "user",
  is_admin: false,
  is_active: true,
  created_at: "2026-07-16T08:00:00Z",
};

describe("users API", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("lists and creates managed users", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: { status: "ok", data: [user] },
    });
    vi.mocked(apiClient.post).mockResolvedValue({
      data: { status: "ok", data: user },
    });

    await expect(listUsers()).resolves.toEqual([user]);
    await expect(
      createUser({ username: "member", password: "password", role: "user" }),
    ).resolves.toEqual(user);

    expect(apiClient.get).toHaveBeenCalledWith("/api/admin/users");
    expect(apiClient.post).toHaveBeenCalledWith("/api/admin/users", {
      username: "member",
      password: "password",
      role: "user",
    });
  });

  it("updates account status and role", async () => {
    vi.mocked(apiClient.patch).mockResolvedValue({
      data: { status: "ok", data: user },
    });

    await updateUserStatus(2, false);
    await updateUserRole(2, "admin");

    expect(apiClient.patch).toHaveBeenNthCalledWith(
      1,
      "/api/admin/users/2/status",
      { is_active: false },
    );
    expect(apiClient.patch).toHaveBeenNthCalledWith(
      2,
      "/api/admin/users/2/role",
      { role: "admin" },
    );
  });
});
