import {
  createRouter,
  createWebHistory,
  type RouteLocationNormalized,
  type RouteLocationRaw,
  type Router,
} from "vue-router";

import type { AuthUser } from "@/api/auth";
import MainLayout from "@/layouts/MainLayout.vue";
import { pinia } from "@/stores";
import { useAuthStore } from "@/stores/auth";
import ChatView from "@/views/ChatView.vue";
import DocumentsView from "@/views/DocumentsView.vue";
import LoginView from "@/views/LoginView.vue";
import SectionPlaceholder from "@/views/SectionPlaceholder.vue";
import UsersView from "@/views/UsersView.vue";

const router: Router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: "/",
      component: MainLayout,
      meta: { requiresAuth: true },
      children: [
        {
          path: "",
          name: "home",
          component: ChatView,
          meta: { title: "\u804a\u5929", allowedRole: "user" },
        },
        {
          path: "history",
          name: "history",
          component: ChatView,
          meta: { title: "\u5386\u53f2\u8bb0\u5f55", allowedRole: "user" },
        },
        {
          path: "documents",
          name: "documents",
          component: DocumentsView,
          meta: { title: "\u6587\u6863\u7ba1\u7406", allowedRole: "admin" },
        },
        {
          path: "admin/users",
          name: "users",
          component: UsersView,
          meta: { title: "\u7528\u6237\u7ba1\u7406", allowedRole: "admin" },
        },
      ],
    },
    {
      path: "/login",
      name: "login",
      component: LoginView,
      meta: { guestOnly: true, title: "\u767b\u5f55" },
    },
    {
      path: "/:pathMatch(.*)*",
      name: "not-found",
      component: SectionPlaceholder,
      props: { title: "Not Found", description: "Route not found" },
    },
  ],
});

router.beforeEach(async (to) => {
  const authStore = useAuthStore(pinia);
  await authStore.restoreSession();
  return resolveRouteGuard(to, authStore.user);
});

/** Resolve authentication and role access for every application route. */
export function resolveRouteGuard(
  to: RouteLocationNormalized,
  user: AuthUser | null,
): RouteLocationRaw | true {
  if (to.name === "login") {
    return user ? defaultRouteFor(user) : true;
  }

  if (!user) {
    return {
      name: "login",
      query: { redirect: to.fullPath },
    };
  }

  const userRole = user.is_admin ? "admin" : "user";
  if (to.name === "not-found" || to.meta.allowedRole !== userRole) {
    return defaultRouteFor(user);
  }

  return true;
}

/** Return the role-specific landing route. */
export function defaultRouteFor(user: AuthUser): RouteLocationRaw {
  return { name: user.is_admin ? "documents" : "home" };
}

export default router;
