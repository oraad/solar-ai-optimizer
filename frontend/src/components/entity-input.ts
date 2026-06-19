import { LitElement, css, html } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import { entityDisplayName, resolveEntity } from "../entity-resolve.js";
import type { EntityInfo } from "../types.js";

/** Entity picker: stores entity_id, displays HA friendly name; uses parent shared datalist. */
@customElement("solar-entity-input")
export class EntityInput extends LitElement {
  /** Light DOM so `list` can reference shared datalists in settings-panel. */
  createRenderRoot() {
    return this;
  }

  static styles = css`
    :host {
      display: block;
      flex: 1;
      min-width: 0;
    }
    input {
      width: 100%;
      box-sizing: border-box;
    }
  `;

  @property() entityId = "";

  @property({ attribute: false }) entities: EntityInfo[] = [];

  @property({ type: Array }) domains: string[] = ["sensor"];

  @property() placeholder = "";

  /** Shared datalist id from settings-panel, e.g. dl-sensor or dl-shed. */
  @property() listId = "";

  @state() private editing = false;

  @state() private editText = "";

  private displayValue(): string {
    if (this.editing) return this.editText;
    return entityDisplayName(this.entityId, this.entities);
  }

  private onFocus(): void {
    this.editing = true;
    this.editText = this.entityId;
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
    return html`
      <input
        type="text"
        placeholder=${this.placeholder}
        list=${this.listId || undefined}
        .value=${this.displayValue()}
        @focus=${this.onFocus}
        @blur=${this.onBlur}
        @change=${this.onChange}
        @input=${this.onInput}
      />
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "solar-entity-input": EntityInput;
  }
}
