import { LitElement, css, html } from "lit";
import { customElement, property, state } from "lit/decorators.js";

const POPOVER_STYLE_ID = "solar-info-tip-popover-styles";

function ensurePopoverStyles(): void {
  if (document.getElementById(POPOVER_STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = POPOVER_STYLE_ID;
  style.textContent = `
    .solar-info-tip-popover {
      display: none;
      position: fixed;
      z-index: 10000;
      width: max-content;
      max-width: min(280px, calc(100% - 24px));
      padding: 8px 10px;
      border-radius: var(--radius-sm, 9px);
      border: 1px solid var(--border-strong, #39414e);
      background: var(--panel-3, #232a34);
      color: var(--text, #e6e9ef);
      font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
      font-size: 0.75rem;
      font-weight: 400;
      font-style: normal;
      line-height: 1.45;
      text-transform: none;
      letter-spacing: normal;
      box-shadow: var(--shadow-lg, 0 10px 40px rgba(0, 0, 0, 0.4));
      pointer-events: none;
      white-space: normal;
    }
    .solar-info-tip-popover.open {
      display: block;
    }
  `;
  document.head.appendChild(style);
}

/** Circled “i” with a hover/focus/click tooltip explaining a setting or action. */
@customElement("solar-info-tip")
export class InfoTip extends LitElement {
  static styles = css`
    :host {
      display: inline-flex;
      vertical-align: middle;
      margin-inline-start: 4px;
      flex-shrink: 0;
    }
    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 15px;
      height: 15px;
      border-radius: 50%;
      border: 1px solid var(--muted);
      color: var(--muted);
      font-size: 0.62rem;
      font-weight: 700;
      font-style: italic;
      font-family: Georgia, "Times New Roman", serif;
      line-height: 1;
      cursor: help;
      background: var(--panel-2);
      padding: 0;
      box-shadow: none;
      -webkit-tap-highlight-color: transparent;
    }
    @media (hover: none), (pointer: coarse) {
      .btn {
        width: 28px;
        height: 28px;
        font-size: 0.72rem;
      }
    }
    .btn:hover,
    .btn:focus-visible,
    .btn[aria-expanded="true"] {
      color: var(--accent-2);
      border-color: var(--accent-2);
      outline: none;
      box-shadow: var(--ring);
    }
    .wrap {
      display: inline-flex;
    }
  `;

  @property() text = "";

  @state() private open = false;
  @state() private touchOnly = false;

  private portalEl: HTMLDivElement | null = null;
  private touchMql?: MediaQueryList;
  private onTouchModeChange = (): void => {
    this.touchOnly = this.touchMql?.matches ?? false;
    if (this.touchOnly) this.close();
  };

  private onDocClick = (e: Event) => {
    if (!this.open) return;
    const path = e.composedPath();
    if (path.includes(this)) return;
    if (this.portalEl && path.includes(this.portalEl)) return;
    this.close();
  };

  private onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Escape") this.close();
  };

  connectedCallback(): void {
    super.connectedCallback();
    this.touchMql = window.matchMedia("(hover: none)");
    this.touchOnly = this.touchMql.matches;
    this.touchMql.addEventListener("change", this.onTouchModeChange);
    document.addEventListener("click", this.onDocClick, true);
    document.addEventListener("keydown", this.onKeyDown);
    window.addEventListener("scroll", this.reposition, true);
    window.addEventListener("resize", this.reposition);
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this.touchMql?.removeEventListener("change", this.onTouchModeChange);
    document.removeEventListener("click", this.onDocClick, true);
    document.removeEventListener("keydown", this.onKeyDown);
    window.removeEventListener("scroll", this.reposition, true);
    window.removeEventListener("resize", this.reposition);
    this.removePortal();
  }

  private ensurePortal(): HTMLDivElement {
    ensurePopoverStyles();
    if (!this.portalEl) {
      this.portalEl = document.createElement("div");
      this.portalEl.className = "solar-info-tip-popover";
      this.portalEl.setAttribute("role", "tooltip");
      document.body.appendChild(this.portalEl);
    }
    return this.portalEl;
  }

  private removePortal(): void {
    this.portalEl?.remove();
    this.portalEl = null;
  }

  private reposition = (): void => {
    if (!this.open || !this.portalEl) return;
    const btn = this.shadowRoot?.querySelector(".btn") as HTMLElement | null;
    if (!btn) return;

    const rect = btn.getBoundingClientRect();
    const pop = this.portalEl;
    const popH = pop.offsetHeight || 80;
    const gap = 8;

    let top = rect.top - popH - gap;
    if (top < 8) top = rect.bottom + gap;

    pop.style.top = `${top}px`;
    pop.style.left = `${rect.left + rect.width / 2}px`;
    pop.style.transform = "translateX(-50%)";
  };

  private openTip(): void {
    if (!this.text) return;
    this.open = true;
    const pop = this.ensurePortal();
    pop.textContent = this.text;
    pop.classList.add("open");
    requestAnimationFrame(() => {
      this.reposition();
      requestAnimationFrame(() => this.reposition());
    });
  }

  private close(): void {
    this.open = false;
    if (this.portalEl) {
      this.portalEl.classList.remove("open");
    }
  }

  private toggle(e: Event): void {
    e.preventDefault();
    e.stopPropagation();
    if (this.open) this.close();
    else this.openTip();
  }

  render() {
    if (!this.text) return null;
    return html`
      <span class="wrap">
        <button
          type="button"
          class="btn"
          aria-label="More information"
          aria-expanded=${this.open}
          @click=${this.toggle}
          @mouseenter=${() => {
            if (!this.touchOnly) this.openTip();
          }}
          @mouseleave=${() => {
            if (!this.touchOnly) this.close();
          }}
          @focus=${() => {
            if (!this.touchOnly) this.openTip();
          }}
          @blur=${() => {
            if (!this.touchOnly) this.close();
          }}
        >
          i
        </button>
      </span>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "solar-info-tip": InfoTip;
  }
}
