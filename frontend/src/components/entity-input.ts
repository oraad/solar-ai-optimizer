import { LitElement, css, html } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { ifDefined } from "lit/directives/if-defined.js";

import { filterEntitiesByDomains } from "../entity-datalists.js";
import { entityDisplayName, resolveEntity } from "../entity-resolve.js";
import type { EntityInfo } from "../types.js";

let datalistSeq = 0;

/** Entity picker: stores entity_id, displays HA friendly name; datalist lives in shadow root. */
@customElement("solar-entity-input")
export class EntityInput extends LitElement {
  static styles = css`
    :host {
      display: block;
      flex: 1;
      min-width: 0;
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
  `;

  @property() entityId = "";

  @property({ attribute: false }) entities: EntityInfo[] = [];

  @property({ attribute: false, type: Array }) domains: string[] = ["sensor"];

  @property() placeholder = "";

  @state() private editing = false;

  @state() private editText = "";

  private readonly datalistId = `dl-ei-${++datalistSeq}`;

  private filteredEntities(): EntityInfo[] {
    return filterEntitiesByDomains(this.entities, this.domains);
  }

  private displayValue(): string {
    if (this.editing) return this.editText;
    return entityDisplayName(this.entityId, this.entities);
  }

  private onFocus(e: FocusEvent): void {
    const input = e.target as HTMLInputElement;
    this.editing = true;
    this.editText = this.entityId;
    // After Lit applies entity_id for editing, select so typing replaces the value.
    void this.updateComplete.then(() => input.select());
  }

  private commit(raw: string): void {
    const resolved = resolveEntity(raw, this.entities, this.domains);
    const next = resolved ?? (raw.trim() || null);
    this.editing = false;
    this.editText = "";
    this.dispatchEvent(
      new CustomEvent("entity-id-change", {
        detail: next,
        bubbles: true,
        composed: true,
      }),
    );
  }

  private onBlur(e: FocusEvent): void {
    this.commit((e.target as HTMLInputElement).value);
  }

  private onChange(e: Event): void {
    const val = (e.target as HTMLInputElement).value;
    const resolved = resolveEntity(val, this.entities, this.domains);
    if (resolved) {
      this.editing = false;
      this.editText = "";
      this.dispatchEvent(
        new CustomEvent("entity-id-change", {
          detail: resolved,
          bubbles: true,
          composed: true,
        }),
      );
    }
  }

  private onInput(e: Event): void {
    this.editText = (e.target as HTMLInputElement).value;
  }

  render() {
    const opts = this.filteredEntities();
    const listAttr = opts.length ? this.datalistId : undefined;
    return html`
      <input
        type="text"
        autocomplete="off"
        placeholder=${this.placeholder}
        list=${ifDefined(listAttr)}
        .value=${this.displayValue()}
        @focus=${this.onFocus}
        @blur=${this.onBlur}
        @change=${this.onChange}
        @input=${this.onInput}
      />
      ${opts.length
        ? html`<datalist id=${this.datalistId}>
            ${opts.map((e) => html`<option value=${e.entity_id}>${e.name}</option>`)}
          </datalist>`
        : null}
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "solar-entity-input": EntityInput;
  }
}
