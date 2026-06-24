import DOMPurify from "dompurify";
import { html, type TemplateResult } from "lit";
import { unsafeHTML } from "lit/directives/unsafe-html.js";
import { marked } from "marked";

marked.setOptions({ async: false });

export function markdownToSafeHtml(markdown: string): string {
  const raw = marked.parse(markdown, { async: false }) as string;
  return DOMPurify.sanitize(raw, { USE_PROFILES: { html: true } });
}

export function renderMarkdown(markdown: string): TemplateResult {
  return html`${unsafeHTML(markdownToSafeHtml(markdown))}`;
}
