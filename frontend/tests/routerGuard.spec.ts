import type { RouteLocationNormalized } from "vue-router";
import { describe, expect, it } from "vitest";

import type { AuthUser } from "@/api/auth";
import { resolveRouteGuard } from "@/router";

const admin: AuthUser = {
  id: 1,
  username: "admin",
  is_admin: true,
  is_active: true,
  created_at: "2026-07-16T00:00:00Z",
};
const user: AuthUser = {
  ...admin,
  id: 2,
  username: "user",
  is_admin: false,
};

/** Build the route fields consumed by the pure route guard. */
function route(
  name: string,
  path: string,
  allowedRole?: "admin" | "user",
): RouteLocationNormalized {
  return {
    name,
    path,
    fullPath: path,
    hash: "",
    query: {},
    params: {},
    matched: [],
    redirectedFrom: undefined,
    meta: allowedRole ? { allowedRole } : {},
  };
}

describe("route guard", () => {
  it("redirects every unauthenticated route to login", () => {
    expect(resolveRouteGuard(route("home", "/", "user"), null)).toEqual({
      name: "login",
      query: { redirect: "/" },
    });
    expect(
      resolveRouteGuard(route("documents", "/documents", "admin"), null),
    ).toEqual({
      name: "login",
      query: { redirect: "/documents" },
    });
  });

  it("allows administrators only into document and user routes", () => {
    expect(resolveRouteGuard(route("documents", "/documents", "admin"), admin)).toBe(true);
    expect(resolveRouteGuard(route("users", "/admin/users", "admin"), admin)).toBe(true);
    expect(resolveRouteGuard(route("home", "/", "user"), admin)).toEqual({
      name: "documents",
    });
    expect(resolveRouteGuard(route("history", "/history", "user"), admin)).toEqual({
      name: "documents",
    });
  });

  it("allows standard users only into chat and history routes", () => {
    expect(resolveRouteGuard(route("home", "/", "user"), user)).toBe(true);
    expect(resolveRouteGuard(route("history", "/history", "user"), user)).toBe(true);
    expect(resolveRouteGuard(route("documents", "/documents", "admin"), user)).toEqual({
      name: "home",
    });
    expect(resolveRouteGuard(route("users", "/admin/users", "admin"), user)).toEqual({
      name: "home",
    });
  });

  it("redirects authenticated users away from login by role", () => {
    expect(resolveRouteGuard(route("login", "/login"), admin)).toEqual({
      name: "documents",
    });
    expect(resolveRouteGuard(route("login", "/login"), user)).toEqual({
      name: "home",
    });
    expect(resolveRouteGuard(route("login", "/login"), null)).toBe(true);
  });
});
