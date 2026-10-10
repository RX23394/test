import type { Page, Route } from "@playwright/test";

interface MockUser {
  id: number;
  username: string;
  is_admin: boolean;
  is_active: boolean;
  created_at: string;
}

interface MockDocument {
  id: number;
  filename: string;
  original_filename: string;
  sha256: string;
  file_size: number;
  uploader_id: number;
  status: "pending" | "processing" | "completed" | "indexed" | "failed";
  created_at: string;
}

interface MockConversation {
  id: number;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface MockApiState {
  currentUser: MockUser | null;
  documents: MockDocument[];
  conversations: MockConversation[];
  deletedDocumentIds: number[];
  deletedConversationIds: number[];
}

const now = "2026-07-16T08:00:00Z";

/** Install deterministic backend routes for one Playwright page. */
export async function installMockApi(page: Page): Promise<MockApiState> {
  const state: MockApiState = {
    currentUser: null,
    documents: [],
    conversations: [
      { id: 1, title: "OSPF", created_at: now, updated_at: now },
      { id: 2, title: "BGP", created_at: now, updated_at: now },
    ],
    deletedDocumentIds: [],
    deletedConversationIds: [],
  };

  await page.route("http://127.0.0.1:8000/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    if (method === "OPTIONS") {
      await route.fulfill({ status: 204, headers: corsHeaders() });
      return;
    }
    if (path === "/api/auth/me") {
      await fulfillJson(
        route,
        state.currentUser
          ? { status: "ok", data: state.currentUser }
          : { status: "error", message: "Authentication required" },
        state.currentUser ? 200 : 401,
      );
      return;
    }
    if (path === "/api/auth/login") {
      const payload = request.postDataJSON() as { username: string };
      const isAdmin = payload.username.includes("admin");
      state.currentUser = {
        id: isAdmin ? 1 : 2,
        username: payload.username,
        is_admin: isAdmin,
        is_active: true,
        created_at: now,
      };
      await fulfillJson(route, { status: "ok", data: state.currentUser });
      return;
    }
    if (path === "/api/auth/logout") {
      state.currentUser = null;
      await fulfillJson(route, { status: "ok" });
      return;
    }
    if (path === "/api/admin/documents" && method === "GET") {
      await fulfillJson(route, { status: "ok", data: state.documents });
      return;
    }
    if (path === "/api/admin/documents" && method === "POST") {
      const document: MockDocument = {
        id: 10,
        filename: "stored-guide.txt",
        original_filename: "network-guide.txt",
        sha256: "f".repeat(64),
        file_size: 17,
        uploader_id: 1,
        status: "pending",
        created_at: now,
      };
      state.documents.unshift(document);
      await fulfillJson(route, { status: "ok", data: document }, 201);
      return;
    }
    const documentMatch = path.match(/^\/api\/admin\/documents\/(\d+)$/);
    if (documentMatch && method === "DELETE") {
      const documentId = Number(documentMatch[1]);
      state.deletedDocumentIds.push(documentId);
      state.documents = state.documents.filter((item) => item.id !== documentId);
      await fulfillJson(route, { status: "ok" });
      return;
    }
    if (/^\/api\/admin\/documents\/\d+\/parse$/.test(path)) {
      await fulfillJson(route, {
        status: "ok",
        data: {
          filename: "network-guide.txt",
          pages: [{ page_number: 1, text: "Network guide preview" }],
        },
      });
      return;
    }
    if (/^\/api\/admin\/documents\/\d+\/index\/async$/.test(path)) {
      const document = state.documents[0];
      if (document) document.status = "indexed";
      await fulfillJson(
        route,
        {
          status: "ok",
          data: {
            document_id: document?.id ?? 10,
            job_id: "e2e-job",
            status: "processing",
          },
        },
        202,
      );
      return;
    }
    if (path === "/api/admin/users") {
      await fulfillJson(route, {
        status: "ok",
        data: state.currentUser ? [state.currentUser] : [],
      });
      return;
    }
    if (path === "/api/conversations" && method === "GET") {
      await fulfillJson(route, { status: "ok", data: state.conversations });
      return;
    }
    const conversationMatch = path.match(/^\/api\/conversations\/(\d+)$/);
    if (conversationMatch && method === "GET") {
      const conversationId = Number(conversationMatch[1]);
      const conversation = state.conversations.find(
        (item) => item.id === conversationId,
      );
      await fulfillJson(route, {
        status: "ok",
        data: {
          conversation,
          messages:
            conversationId === 2
              ? [
                  {
                    id: 20,
                    role: "user",
                    content: "Stored BGP question",
                    created_at: now,
                  },
                ]
              : [],
        },
      });
      return;
    }
    if (conversationMatch && method === "DELETE") {
      const conversationId = Number(conversationMatch[1]);
      state.deletedConversationIds.push(conversationId);
      state.conversations = state.conversations.filter(
        (item) => item.id !== conversationId,
      );
      await fulfillJson(route, { status: "ok" });
      return;
    }
    if (path === "/api/chat/stream") {
      const citation = [
        {
          id: "S1",
          document: "Network Guide.pdf",
          page: 12,
          section: "OSPF",
          content: "OSPF is a link-state routing protocol.",
        },
      ];
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        headers: corsHeaders(),
        body:
          'event: token\ndata: {"status":"ok","data":"OSPF answer [S1]."}\n\n' +
          `event: citation\ndata: ${JSON.stringify({ status: "ok", data: citation })}\n\n` +
          'event: done\ndata: {"status":"ok"}\n\n',
      });
      return;
    }

    await fulfillJson(route, { status: "error", message: "Not mocked" }, 404);
  });

  return state;
}

/** Authenticate through the visible login form. */
export async function loginAs(page: Page, username: string): Promise<void> {
  await page.goto("/login");
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill("password123");
  await page.getByRole("button", { name: "登录" }).click();
}

/** Fulfill one request with the application's uniform JSON envelope. */
async function fulfillJson(
  route: Route,
  body: object,
  status = 200,
): Promise<void> {
  await route.fulfill({
    status,
    contentType: "application/json",
    headers: corsHeaders(),
    body: JSON.stringify(body),
  });
}

/** Return CORS headers for the mocked API origin. */
function corsHeaders(): Record<string, string> {
  return {
    "access-control-allow-origin": "http://127.0.0.1:4173",
    "access-control-allow-credentials": "true",
    "access-control-allow-headers": "Content-Type",
    "access-control-allow-methods": "GET,POST,PATCH,DELETE,OPTIONS",
  };
}
