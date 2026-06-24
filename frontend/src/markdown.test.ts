import { describe, expect, it } from "vitest";

import { markdownToSafeHtml } from "./markdown.js";

describe("markdownToSafeHtml", () => {
  it("renders headings and lists", () => {
    const html = markdownToSafeHtml("## Heading\n\n- one\n- two");
    expect(html).toContain("<h2");
    expect(html).toContain("Heading");
    expect(html).toContain("<ul");
    expect(html).toContain("<li");
  });

  it("strips script tags", () => {
    const html = markdownToSafeHtml('<script>alert(1)</script>\n\n## Safe');
    expect(html).not.toContain("<script");
    expect(html).toContain("Safe");
  });

  it("strips inline event handlers", () => {
    const html = markdownToSafeHtml('![x](x" onerror="alert(1))');
    expect(html).not.toContain("onerror");
  });
});
