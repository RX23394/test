import { expect, test } from "@playwright/test";

import { installMockApi, loginAs } from "./helpers/mockApi";

test("login and role guards enforce administrator and user access", async ({
  page,
}) => {
  await installMockApi(page);

  await page.goto("/documents");
  await expect(page).toHaveURL(/\/login/);

  await loginAs(page, "standard-user");
  await expect(page).toHaveURL("/");
  await expect(page.getByText("历史记录").first()).toBeVisible();
  await expect(page.getByText("文档管理")).toHaveCount(0);

  await page.goto("/admin/users");
  await expect(page).toHaveURL("/");
});

test("administrator uploads and deletes a document", async ({ page }) => {
  const state = await installMockApi(page);
  await loginAs(page, "network-admin");
  await expect(page).toHaveURL("/documents");

  await page.locator('input[type="file"]').setInputFiles({
    name: "network-guide.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("network guide data"),
  });

  const documentRow = page.locator("tbody tr").filter({
    hasText: "network-guide.txt",
  });
  await expect(documentRow).toContainText("Indexed");

  await documentRow.getByRole("button", { name: "删除" }).click();
  await page.locator(".el-message-box").getByRole("button", { name: "删除" }).click();

  await expect(documentRow).toHaveCount(0);
  expect(state.deletedDocumentIds).toEqual([10]);
});

test("administrator selects and batch deletes documents", async ({ page }) => {
  const state = await installMockApi(page);
  state.documents.push(
    {
      id: 21,
      filename: "stored-udp.txt",
      original_filename: "RFC768_UDP.txt",
      sha256: "a".repeat(64),
      file_size: 5896,
      uploader_id: 1,
      status: "indexed",
      created_at: "2026-07-16T08:00:00Z",
    },
    {
      id: 22,
      filename: "stored-tcp.txt",
      original_filename: "RFC9293_TCP.txt",
      sha256: "b".repeat(64),
      file_size: 12000,
      uploader_id: 1,
      status: "indexed",
      created_at: "2026-07-16T08:00:00Z",
    },
  );

  await loginAs(page, "network-admin");
  await page.getByRole("checkbox", { name: "全选文档" }).check();
  await page.getByRole("button", { name: /批量删除.*2/ }).click();
  await page.locator(".el-message-box").getByRole("button", { name: "批量删除" }).click();

  await expect(page.getByText("RFC768_UDP.txt")).toHaveCount(0);
  await expect(page.getByText("RFC9293_TCP.txt")).toHaveCount(0);
  expect(state.deletedDocumentIds).toEqual([21, 22]);
});

test("user chats with Ctrl+Enter and opens a citation", async ({ page }) => {
  await installMockApi(page);
  await loginAs(page, "standard-user");
  await expect(page).toHaveURL("/");

  const composer = page.getByLabel("Chat message");
  await composer.fill("What is OSPF?");
  await composer.press("Control+Enter");

  await expect(page.getByText("OSPF answer")).toBeVisible();
  await page.getByRole("button", { name: /Network Guide\.pdf/ }).click();
  await expect(page.locator(".original-highlight")).toContainText(
    "OSPF is a link-state routing protocol.",
  );
});

test("user switches and deletes conversations", async ({ page }) => {
  const state = await installMockApi(page);
  await loginAs(page, "standard-user");

  await page.locator(".conversation-select", { hasText: "BGP" }).click();
  await expect(page.getByText("Stored BGP question")).toBeVisible();

  const bgpConversation = page.locator(".conversation-item").filter({ hasText: "BGP" });
  await bgpConversation.getByRole("button", { name: "删除" }).click();
  await page.locator(".el-message-box").getByRole("button", { name: "OK" }).click();

  await expect(bgpConversation).toHaveCount(0);
  expect(state.deletedConversationIds).toEqual([2]);
});
