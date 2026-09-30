import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import ElementPlus, { ElMessage, type MessageHandler } from "element-plus";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ChatCitation } from "@/api/chat";
import CitationDrawer from "@/components/CitationDrawer.vue";

const CITATION: ChatCitation = {
  id: "S1",
  document: "Cisco OSPF.pdf",
  page: 12,
  section: "Area",
  content: "OSPF areas reduce link-state flooding.",
};

/** Mount an open citation drawer with Element Plus installed. */
function mountDrawer(): VueWrapper {
  return mount(CitationDrawer, {
    attachTo: document.body,
    props: {
      modelValue: true,
      citation: CITATION,
    },
    global: { plugins: [ElementPlus] },
  });
}

describe("CitationDrawer", () => {
  afterEach(() => {
    document.body.innerHTML = "";
    vi.restoreAllMocks();
  });

  it("shows document metadata and a highlighted original excerpt", async () => {
    const wrapper = mountDrawer();
    await flushPromises();

    expect(document.body.textContent).toContain("Cisco OSPF.pdf");
    expect(document.body.textContent).toContain("12");
    expect(document.body.textContent).toContain("Area");
    const original = document.querySelector(".original-highlight");
    expect(original?.textContent).toBe(CITATION.content);
    wrapper.unmount();
  });

  it("copies the original excerpt and confirms success", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    const messageSpy = vi
      .spyOn(ElMessage, "success")
      .mockReturnValue({ close: vi.fn() } as MessageHandler);
    const wrapper = mountDrawer();
    await flushPromises();
    const copyButton = Array.from(document.querySelectorAll("button")).find(
      (button) => button.textContent?.includes("\u590d\u5236\u539f\u6587"),
    );

    expect(copyButton).toBeDefined();
    copyButton?.click();
    await flushPromises();

    expect(writeText).toHaveBeenCalledWith(CITATION.content);
    expect(messageSpy).toHaveBeenCalledWith("\u539f\u6587\u5df2\u590d\u5236");
    wrapper.unmount();
  });
});
