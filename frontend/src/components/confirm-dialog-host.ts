import { LitElement, css, html, nothing } from "lit";
import { customElement, state } from "lit/decorators.js";

import { t } from "../i18n.js";
import {
  CONFIRM_REQUEST,
  CONFIRM_RESPONSE,
  type ConfirmDialogOptions,
  type ConfirmRequestDetail,
  type ConfirmResponseDetail,
} from "../confirm.js";

interface ConfirmEntry extends ConfirmDialogOptions {
  id: string;
}

@customElement("solar-confirm-dialog-host")
export class ConfirmDialogHost extends LitElement {
  static styles = css`
    :host {
      font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
    }
    .backdrop {
      position: fixed;
      inset: 0;
      z-index: 10100;
      background: rgba(0, 0, 0, 0.55);
      animation: fade-in 0.15s ease;
    }
    @media (prefers-reduced-motion: reduce) {
      .backdrop { animation: none; }
    }
    @keyframes fade-in {
      from { opacity: 0; }
      to { opacity: 1; }
    }
    .dialog {
      position: fixed;
      z-index: 10101;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      width: min(440px, calc(100vw - 32px));
      background: var(--panel-2, #1c222b);
      border: 1px solid var(--border-strong, #39414e);
      border-radius: var(--radius, 14px);
      box-shadow: var(--shadow-lg, 0 10px 40px rgba(0, 0, 0, 0.4));
      padding: 24px;
      display: flex;
      flex-direction: column;
      gap: 14px;
      color: var(--text, #e6e9ef);
      animation: dialog-in 0.18s ease;
      outline: none;
    }
    @media (prefers-reduced-motion: reduce) {
      .dialog { animation: none; }
    }
    @keyframes dialog-in {
      from { opacity: 0; transform: translate(-50%, calc(-50% + 8px)); }
      to { opacity: 1; transform: translate(-50%, -50%); }
    }
    .dialog.danger {
      border-color: color-mix(in srgb, var(--bad, #e5484d) 50%, var(--border-strong, #39414e));
    }
    h2 {
      margin: 0;
      font-size: 1rem;
      font-weight: 700;
      line-height: 1.3;
      color: var(--text, #e6e9ef);
    }
    .dialog.danger h2 {
      color: var(--bad, #e5484d);
    }
    .message {
      margin: 0;
      font-size: 0.88rem;
      line-height: 1.55;
      color: var(--muted, #94a0b0);
      white-space: pre-wrap;
    }
    .require-label {
      display: block;
      font-size: 0.82rem;
      font-weight: 600;
      color: var(--muted, #94a0b0);
      margin-bottom: -6px;
    }
    input[type="text"] {
      font: inherit;
      width: 100%;
      box-sizing: border-box;
      color: var(--text, #e6e9ef);
      background: var(--panel, #151a21);
      border: 1px solid var(--border, #2a313c);
      border-radius: var(--radius-sm, 9px);
      padding: 8px 10px;
      transition: border-color 0.15s ease, box-shadow 0.15s ease;
    }
    input[type="text"]:focus-visible {
      outline: none;
      border-color: var(--accent-2, #4cc2ff);
      box-shadow: 0 0 0 3px rgba(76, 194, 255, 0.35);
    }
    .actions {
      display: flex;
      justify-content: flex-end;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 4px;
    }
    button {
      font: inherit;
      font-weight: 600;
      cursor: pointer;
      border-radius: var(--radius-sm, 9px);
      padding: 8px 18px;
      border: 1px solid var(--border, #2a313c);
      transition: background 0.15s ease, border-color 0.15s ease, transform 0.05s ease,
        box-shadow 0.15s ease;
      -webkit-tap-highlight-color: transparent;
    }
    button:active { transform: translateY(1px); }
    button:focus-visible {
      outline: none;
      box-shadow: 0 0 0 3px rgba(76, 194, 255, 0.35);
    }
    button:disabled { opacity: 0.45; cursor: not-allowed; }
    .cancel-btn {
      color: var(--text, #e6e9ef);
      background: var(--panel-3, #232a34);
      border-color: var(--border, #2a313c);
    }
    .cancel-btn:hover:not(:disabled) {
      background: var(--panel-2, #1c222b);
      border-color: var(--border-strong, #39414e);
    }
    .confirm-btn.primary {
      background: var(--accent, #ffb020);
      background: linear-gradient(180deg, var(--accent, #ffb020), color-mix(in srgb, var(--accent, #ffb020) 82%, black));
      color: #1a1205;
      border-color: transparent;
    }
    .confirm-btn.primary:hover:not(:disabled) { filter: brightness(1.06); }
    .confirm-btn.danger {
      background: rgba(229, 72, 77, 0.18);
      color: var(--bad, #e5484d);
      border-color: rgba(229, 72, 77, 0.5);
    }
    .confirm-btn.danger:hover:not(:disabled) { background: rgba(229, 72, 77, 0.3); }
    @media (max-width: 480px) {
      .actions { flex-direction: column-reverse; }
      button { min-height: 44px; }
    }
    @media (hover: none) {
      .cancel-btn:hover { background: var(--panel-3, #232a34); border-color: var(--border, #2a313c); }
      .confirm-btn.primary:hover { filter: none; }
      .confirm-btn.danger:hover { background: rgba(229, 72, 77, 0.18); }
    }
  `;

  @state() private entry: ConfirmEntry | null = null;
  @state() private inputValue = "";

  private previousFocus: Element | null = null;

  connectedCallback(): void {
    super.connectedCallback();
    window.addEventListener(CONFIRM_REQUEST, this.onRequest as EventListener);
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    window.removeEventListener(CONFIRM_REQUEST, this.onRequest as EventListener);
    window.removeEventListener("keydown", this.onWindowKeydown);
  }

  private onRequest = (e: Event): void => {
    const detail = (e as CustomEvent<ConfirmRequestDetail>).detail;
    if (!detail) return;
    if (this.entry) {
      // A second request arrived while one is still pending (e.g. two
      // operator actions fired in quick succession) — auto-decline the
      // stale one instead of queuing/rejecting, then show the new request.
      const stale = this.entry;
      window.dispatchEvent(
        new CustomEvent<ConfirmResponseDetail>(CONFIRM_RESPONSE, {
          detail: { id: stale.id, confirmed: false },
        }),
      );
    }
    this.previousFocus = document.activeElement;
    this.inputValue = "";
    this.entry = { id: detail.id, ...detail.opts };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", this.onWindowKeydown);
    void this.updateComplete.then(() => this.focusFirst());
  };

  private focusFirst(): void {
    const input = this.shadowRoot?.querySelector<HTMLElement>("input");
    if (input) {
      input.focus();
      return;
    }
    // Focus cancel button by default (safer for destructive actions)
    const cancel = this.shadowRoot?.querySelector<HTMLElement>(".cancel-btn");
    cancel?.focus();
  }

  private respond(confirmed: boolean): void {
    const entry = this.entry;
    if (!entry) return;
    this.entry = null;
    this.inputValue = "";
    document.body.style.overflow = "";
    window.removeEventListener("keydown", this.onWindowKeydown);
    if (this.previousFocus instanceof HTMLElement) {
      this.previousFocus.focus();
    }
    window.dispatchEvent(
      new CustomEvent<ConfirmResponseDetail>(CONFIRM_RESPONSE, {
        detail: { id: entry.id, confirmed },
      }),
    );
  }

  private onWindowKeydown = (e: KeyboardEvent): void => {
    if (!this.entry) return;
    if (e.key === "Escape") {
      e.preventDefault();
      this.respond(false);
      return;
    }
    if (e.key === "Tab") {
      const focusable = [
        ...( this.shadowRoot?.querySelectorAll<HTMLElement>(
          'button:not([disabled]), input:not([disabled])',
        ) ?? []),
      ];
      if (focusable.length === 0) return;
      const active = this.shadowRoot?.activeElement as HTMLElement | null;
      const idx = active ? focusable.indexOf(active) : -1;
      if (e.shiftKey) {
        e.preventDefault();
        const prev = idx <= 0 ? focusable[focusable.length - 1] : focusable[idx - 1];
        prev.focus();
      } else {
        e.preventDefault();
        const next = idx >= focusable.length - 1 ? focusable[0] : focusable[idx + 1];
        next.focus();
      }
    }
  };

  private get canConfirm(): boolean {
    if (!this.entry?.requireText) return true;
    return this.inputValue === this.entry.requireText;
  }

  render() {
    if (!this.entry) return nothing;
    const entry = this.entry;
    const confirmLabel = entry.confirmLabel ?? t("ui.confirm.confirm");
    const cancelLabel = entry.cancelLabel ?? t("ui.confirm.cancel");

    return html`
      <div
        class="backdrop"
        aria-hidden="true"
        @click=${() => this.respond(false)}
      ></div>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        class="dialog ${entry.danger ? "danger" : ""}"
      >
        <h2 id="confirm-title">${entry.title}</h2>
        <p class="message">${entry.message}</p>
        ${entry.requireText
          ? html`
              <label class="require-label" for="confirm-require-input">
                ${t("ui.confirm.typeToConfirm", { text: entry.requireText })}
              </label>
              <input
                id="confirm-require-input"
                type="text"
                autocomplete="off"
                spellcheck="false"
                .value=${this.inputValue}
                @input=${(e: InputEvent) => {
                  this.inputValue = (e.target as HTMLInputElement).value;
                }}
                @keydown=${(e: KeyboardEvent) => {
                  if (e.key === "Enter" && this.canConfirm) this.respond(true);
                }}
              />
            `
          : nothing}
        <div class="actions">
          <button type="button" class="cancel-btn" @click=${() => this.respond(false)}>
            ${cancelLabel}
          </button>
          <button
            type="button"
            class="confirm-btn ${entry.danger ? "danger" : "primary"}"
            ?disabled=${!this.canConfirm}
            @click=${() => this.respond(true)}
          >
            ${confirmLabel}
          </button>
        </div>
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "solar-confirm-dialog-host": ConfirmDialogHost;
  }
}
