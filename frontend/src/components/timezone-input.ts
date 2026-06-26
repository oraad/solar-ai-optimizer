import { LitElement, css, html } from "lit";
import { customElement, property } from "lit/decorators.js";

import { t } from "../i18n.js";

let datalistSeq = 0;

let cachedTimezones: string[] | null = null;

export function ianaTimezones(): string[] {
  if (cachedTimezones) return cachedTimezones;
  try {
    cachedTimezones = Intl.supportedValuesOf("timeZone").slice().sort();
  } catch {
    cachedTimezones = [];
  }
  return cachedTimezones;
}

/** Searchable IANA timezone combobox with Auto option. */
@customElement("solar-timezone-input")
export class TimezoneInput extends LitElement {
  static styles = css`
    :host {
      display: block;
    }
    input {
      width: 100%;
      box-sizing: border-box;
      font: inherit;
      color: var(--text);
      background: var(--panel-2);
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      padding: 8px 10px;
      transition: border-color 0.15s ease, box-shadow 0.15s ease;
    }
    input:focus-visible {
      outline: none;
      border-color: var(--accent-2);
      box-shadow: var(--ring);
    }
    .hint {
      margin: 6px 0 0;
      font-size: 0.85rem;
      color: var(--muted);
    }
  `;

  @property() value = "auto";

  @property({ attribute: "resolved-hint" }) resolvedHint = "";

  private readonly datalistId = `dl-tz-${++datalistSeq}`;

  private displayLabel(tz: string): string {
    if (tz === "auto") return t("settings.timezone.auto");
    return tz;
  }

  private datalistOptions(): string[] {
    const opts = ["auto", ...ianaTimezones()];
    if (this.value && this.value !== "auto" && !opts.includes(this.value)) {
      opts.splice(1, 0, this.value);
    }
    return opts;
  }

  private normalizeInput(raw: string): string {
    const text = raw.trim();
    if (!text) return "auto";
    const autoLabel = t("settings.timezone.auto");
    if (text.toLowerCase() === "auto" || text === autoLabel) return "auto";
    return text;
  }

  private onCommit(e: Event): void {
    const next = this.normalizeInput((e.target as HTMLInputElement).value);
    this.dispatchEvent(
      new CustomEvent("timezone-change", {
        detail: next,
        bubbles: true,
        composed: true,
      }),
    );
  }

  render() {
    const opts = this.datalistOptions();
    const showResolved =
      (this.value || "auto").toLowerCase() === "auto" && this.resolvedHint;
    return html`
      <input
        type="text"
        autocomplete="off"
        list=${this.datalistId}
        .value=${this.displayLabel(this.value || "auto")}
        @change=${this.onCommit}
        @blur=${this.onCommit}
      />
      <datalist id=${this.datalistId}>
        ${opts.map(
          (tz) => html`<option value=${this.displayLabel(tz)}></option>`,
        )}
      </datalist>
      ${showResolved
        ? html`<p class="hint">
            ${t("settings.timezone.resolved", { tz: this.resolvedHint })}
          </p>`
        : null}
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "solar-timezone-input": TimezoneInput;
  }
}
