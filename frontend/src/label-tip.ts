import { html, type TemplateResult } from "lit";

import "./components/info-tip.js";

/** Label text with an optional circled-info tooltip. */
export function labelWithTip(label: string, help?: string): TemplateResult {
  return html`${label}${help ? html`<solar-info-tip .text=${help}></solar-info-tip>` : null}`;
}
