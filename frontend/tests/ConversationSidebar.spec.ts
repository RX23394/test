import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import ElementPlus, { ElMessageBox } from "element-plus";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as conversationApi from "@/api/conversations";
import ConversationSidebar from "@/components/ConversationSidebar.vue";

vi.mock("@/api/conversations", () => ({
  listConversations: vi.fn(),
  createConversation: vi.fn(),
  renameConversation: vi.fn(),
  deleteConversation: vi.fn(),
}));

const FIRST = {
  id: 1,
  title: "OSPF",
  created_at: "2026-07-16T00:00:00Z",
  updated_at: "2026-07-16T00:00:00Z",
};
const SECOND = { ...FIRST, id: 2, title: "BGP" };

/** Mount the sidebar with Element Plus installed. */
function mountSidebar(selectedId: number | null = null): VueWrapper {
  const pinia = createPinia();
  setActivePinia(pinia);
  return mount(ConversationSidebar, {
    props: { selectedId },
    global: { plugins: [pinia, ElementPlus] },
  });
}

describe("ConversationSidebar", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(conversationApi.listConversations).mockResolvedValue([FIRST, SECOND]);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads conversations, selects the newest, and creates a conversation", async () => {
    vi.mocked(conversationApi.createConversation).mockResolvedValue({
      ...FIRST,
      id: 3,
      title: null,
    });
    const wrapper = mountSidebar();
    await flushPromises();

    expect(wrapper.text()).toContain("OSPF");
    expect(wrapper.emitted("select")?.[0]).toEqual([1]);

    const createButton = wrapper
      .findAll("button")
      .find((button) => button.text().includes("\u65b0\u5efa\u4f1a\u8bdd"));
    await createButton?.trigger("click");
    await flushPromises();
    expect(conversationApi.createConversation).toHaveBeenCalledWith();
    expect(wrapper.emitted("select")?.at(-1)).toEqual([3]);
  });

  it("renames and deletes conversations through confirmed actions", async () => {
    vi.spyOn(ElMessageBox, "prompt").mockResolvedValue({
      value: "OSPF Areas",
      action: "confirm",
    } as never);
    vi.spyOn(ElMessageBox, "confirm").mockResolvedValue("confirm" as never);
    vi.mocked(conversationApi.renameConversation).mockResolvedValue({
      ...FIRST,
      title: "OSPF Areas",
    });
    vi.mocked(conversationApi.deleteConversation).mockResolvedValue(undefined);
    const wrapper = mountSidebar(1);
    await flushPromises();

    const renameButton = wrapper
      .findAll("button")
      .find((button) => button.text() === "\u91cd\u547d\u540d");
    await renameButton?.trigger("click");
    await flushPromises();
    expect(conversationApi.renameConversation).toHaveBeenCalledWith(1, "OSPF Areas");
    expect(wrapper.text()).toContain("OSPF Areas");

    const deleteButton = wrapper
      .findAll("button")
      .find((button) => button.text() === "\u5220\u9664");
    await deleteButton?.trigger("click");
    await flushPromises();
    expect(conversationApi.deleteConversation).toHaveBeenCalledWith(1);
    expect(wrapper.emitted("select")?.at(-1)).toEqual([2]);
  });
});
