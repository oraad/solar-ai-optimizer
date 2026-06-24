import { LitElement, css, html } from "lit";
import { customElement, state } from "lit/decorators.js";

import {
  TOAST_DISMISS,
  TOAST_SHOW,
  TOAST_UPDATE,
  type ToastDismissDetail,
  type ToastShowDetail,
  type ToastUpdateDetail,
  type ToastVariant,
} from "../toast.js";

interface ToastEntry {
  id: string;
  message: string;
  variant: ToastVariant;
  persistent: boolean;
}

const MAX_VISIBLE = 3;

@customElement("solar-toast-host")
export class ToastHost extends LitElement {
  static styles = css`
    :host {
      position: fixed;
      bottom: max(20px, var(--safe-bottom, env(safe-area-inset-bottom, 0px)));
      right: max(20px, var(--safe-right, env(safe-area-inset-right, 0px)));
      z-index: 10000;
      display: flex;
      flex-direction: column-reverse;
      gap: 10px;
      max-width: min(380px, calc(100% - 40px));
      pointer-events: none;
      font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
    }
    .toast {
      pointer-events: auto;
      display: flex;
      align-items: flex-start;
      gap: 10px;
      padding: 12px 14px;
      border-radius: var(--radius-sm, 9px);
      border: 1px solid var(--border-strong, #39414e);
      background: var(--panel-3, #232a34);
      color: var(--text, #e6e9ef);
      box-shadow: var(--shadow-lg, 0 10px 40px rgba(0, 0, 0, 0.4));
      font-size: 0.82rem;
      line-height: 1.4;
      animation: toast-in 0.22s ease;
    }
    @media (prefers-reduced-motion: reduce) {
      .toast {
        animation: none;
      }
    }
    @keyframes toast-in {
      from {
        opacity: 0;
        transform: translateY(8px);
      }
      to {
        opacity: 1;
        transform: none;
      }
    }
    .toast.success {
      border-color: color-mix(in srgb, var(--good, #3ecf8e) 45%, var(--border-strong, #39414e));
    }
    .toast.error {
      border-color: color-mix(in srgb, var(--bad, #f07178) 45%, var(--border-strong, #39414e));
    }
    .toast.info {
      border-color: color-mix(in srgb, var(--accent, #e8b84a) 45%, var(--border-strong, #39414e));
    }
    .spinner {
      width: 16px;
      height: 16px;
      flex-shrink: 0;
      margin-top: 1px;
      border: 2px solid var(--muted, #8b95a8);
      border-top-color: var(--accent-2, #6ad);
      border-radius: 50%;
      animation: spin 0.7s linear infinite;
    }
    @media (prefers-reduced-motion: reduce) {
      .spinner {
        animation: none;
        border-top-color: var(--muted, #8b95a8);
      }
    }
    @keyframes spin {
      to {
        transform: rotate(360deg);
      }
    }
    .body {
      flex: 1;
      min-width: 0;
      word-break: break-word;
    }
    .dismiss {
      flex-shrink: 0;
      border: none;
      background: transparent;
      color: var(--muted, #8b95a8);
      cursor: pointer;
      padding: 0 0 0 4px;
      font-size: 1.1rem;
      line-height: 1;
    }
    .dismiss:hover {
      color: var(--text, #e6e9ef);
    }
  `;

  @state() private toasts: ToastEntry[] = [];

  private timers = new Map<string, number>();

  connectedCallback(): void {
    super.connectedCallback();
    window.addEventListener(TOAST_SHOW, this.onShow as EventListener);
    window.addEventListener(TOAST_UPDATE, this.onUpdate as EventListener);
    window.addEventListener(TOAST_DISMISS, this.onDismiss as EventListener);
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    window.removeEventListener(TOAST_SHOW, this.onShow as EventListener);
    window.removeEventListener(TOAST_UPDATE, this.onUpdate as EventListener);
    window.removeEventListener(TOAST_DISMISS, this.onDismiss as EventListener);
    for (const timer of this.timers.values()) {
      window.clearTimeout(timer);
    }
    this.timers.clear();
  }

  private onShow = (e: Event): void => {
    const detail = (e as CustomEvent<ToastShowDetail>).detail;
    if (!detail) return;

    this.clearTimer(detail.id);
    const entry: ToastEntry = {
      id: detail.id,
      message: detail.message,
      variant: detail.variant,
      persistent: detail.persistent,
    };

    this.toasts = [entry, ...this.toasts.filter((t) => t.id !== detail.id)].slice(0, MAX_VISIBLE);

    if (!detail.persistent && detail.durationMs) {
      this.timers.set(
        detail.id,
        window.setTimeout(() => this.removeToast(detail.id), detail.durationMs),
      );
    }
  };

  private onUpdate = (e: Event): void => {
    const detail = (e as CustomEvent<ToastUpdateDetail>).detail;
    if (!detail) return;

    const idx = this.toasts.findIndex((t) => t.id === detail.id);
    if (idx < 0) return;

    const current = this.toasts[idx];
    const nextVariant = detail.variant ?? current.variant;
    const updated: ToastEntry = {
      ...current,
      message: detail.message ?? current.message,
      variant: nextVariant,
      persistent: nextVariant === "loading" ? current.persistent : false,
    };
    this.toasts = [...this.toasts.slice(0, idx), updated, ...this.toasts.slice(idx + 1)];

    if (updated.variant !== "loading" && !updated.persistent) {
      this.clearTimer(detail.id);
      const duration = updated.variant === "error" ? 8000 : 5000;
      this.timers.set(
        detail.id,
        window.setTimeout(() => this.removeToast(detail.id), duration),
      );
    }
  };

  private onDismiss = (e: Event): void => {
    const detail = (e as CustomEvent<ToastDismissDetail>).detail;
    if (detail?.id) this.removeToast(detail.id);
  };

  private clearTimer(id: string): void {
    const timer = this.timers.get(id);
    if (timer != null) {
      window.clearTimeout(timer);
      this.timers.delete(id);
    }
  }

  private removeToast(id: string): void {
    this.clearTimer(id);
    this.toasts = this.toasts.filter((t) => t.id !== id);
  }

  render() {
    return html`
      ${this.toasts.map(
        (t) => html`
          <div class="toast ${t.variant}" role="status" aria-live="polite">
            ${t.variant === "loading" ? html`<span class="spinner" aria-hidden="true"></span>` : null}
            <span class="body">${t.message}</span>
            ${t.persistent || t.variant === "error"
              ? html`
                  <button
                    type="button"
                    class="dismiss"
                    aria-label="Dismiss"
                    @click=${() => this.removeToast(t.id)}
                  >
                    ×
                  </button>
                `
              : null}
          </div>
        `,
      )}
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "solar-toast-host": ToastHost;
  }
}
