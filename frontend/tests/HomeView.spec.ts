import { mount, type VueWrapper } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import HomeView from "@/views/HomeView.vue";

describe("HomeView", () => {
  it("renders the project title", () => {
    const wrapper: VueWrapper = mount(HomeView);

    expect(wrapper.text()).toContain("Network RAG");
    expect(wrapper.text()).toContain("\u804a\u5929\u5de5\u4f5c\u533a\u5df2\u5c31\u7eea");
  });
});
