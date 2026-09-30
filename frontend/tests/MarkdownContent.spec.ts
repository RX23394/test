import { mount, type VueWrapper } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import MarkdownContent from "@/components/MarkdownContent.vue";
import { renderMarkdown } from "@/utils/markdown";

describe("MarkdownContent", () => {
  it("renders headings, emphasis, lists, links, and inline code", () => {
    const wrapper: VueWrapper = mount(MarkdownContent, {
      props: {
        content:
          "## OSPF\n\n**Area** design with `router-id`.\n\n- Backbone\n- Stub\n\n[Reference](https://example.com)",
      },
    });

    expect(wrapper.find("h2").text()).toBe("OSPF");
    expect(wrapper.find("strong").text()).toBe("Area");
    expect(wrapper.find("code").text()).toBe("router-id");
    expect(wrapper.findAll("li")).toHaveLength(2);
    expect(wrapper.find("a").attributes("rel")).toBe("noopener noreferrer");
  });

  it("renders safe citation buttons, emits clicks, and highlights the active source", async () => {
    const wrapper: VueWrapper = mount(MarkdownContent, {
      props: {
        content: "OSPF uses areas [S1]. Inline `[S2]` stays code.",
        activeCitationId: "S1",
      },
    });

    const reference = wrapper.find<HTMLButtonElement>(".citation-reference");
    expect(reference.text()).toBe("[S1]");
    expect(reference.classes()).toContain("is-active");
    expect(wrapper.find("code").text()).toBe("[S2]");
    expect(wrapper.findAll(".citation-reference")).toHaveLength(1);

    await reference.trigger("click");
    expect(wrapper.emitted("citationClick")).toEqual([["S1"]]);
  });

  it("highlights fenced code keywords, numbers, strings, and comments", () => {
    const html = renderMarkdown(
      '```typescript\nconst area = 12;\nconst name = "backbone"; // OSPF\n```',
    );

    expect(html).toContain('class="language-typescript"');
    expect(html).toContain('class="token-keyword">const</span>');
    expect(html).toContain('class="token-number">12</span>');
    expect(html).toContain('class="token-string">&quot;backbone&quot;</span>');
    expect(html).toContain('class="token-comment">// OSPF</span>');
  });

  it("escapes raw HTML before rendering Markdown", () => {
    const html = renderMarkdown("<script>alert('xss')</script> **safe**");

    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
    expect(html).toContain("<strong>safe</strong>");
  });
});
