import { LitElement, html } from "lit";
import { customElement, state } from "lit/decorators.js";

import { api } from "../api.js";
import { t } from "../i18n.js";
import { LocaleController } from "../locale-controller.js";
import { runWithToast } from "../toast.js";

const LOGIN_STYLE_ID = "solar-login-page-styles";

// Rendered in light DOM (see createRenderRoot below) so the browser's native
// password manager can see and offer to save the form's inputs — shadow DOM
// hides forms from autofill/"save password" heuristics in some browsers.
// Component styles therefore can't rely on `static styles` (only adopted
// into a shadow root); inject plain CSS into the document once instead,
// same pattern as info-tip.ts's ensurePopoverStyles.
function ensureLoginStyles(): void {
  if (document.getElementById(LOGIN_STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = LOGIN_STYLE_ID;
  style.textContent = `
    solar-login-page {
      display: grid;
      min-height: 100%;
      place-items: center;
      padding: 24px;
      box-sizing: border-box;
      font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
      color: var(--text, #e6e9ef);
    }
    solar-login-page .card {
      width: min(420px, 100%);
      box-sizing: border-box;
      position: relative;
      background: var(--panel, #151a21);
      border: 1px solid var(--border, #2a313c);
      border-radius: var(--radius, 14px);
      padding: var(--card-pad, 18px);
      box-shadow: var(--shadow, 0 1px 2px rgba(0, 0, 0, 0.3), 0 6px 20px rgba(0, 0, 0, 0.25));
    }
    solar-login-page h1 {
      margin: 0 0 6px;
      font-size: 1.25rem;
    }
    solar-login-page .sub {
      margin: 0 0 20px;
      color: var(--muted, #94a0b0);
      font-size: 0.85rem;
    }
    solar-login-page label {
      display: block;
      font-size: 0.78rem;
      color: var(--muted, #94a0b0);
      margin-bottom: 6px;
    }
    solar-login-page input {
      font: inherit;
      width: 100%;
      box-sizing: border-box;
      color: var(--text, #e6e9ef);
      background: var(--panel-2, #1c222b);
      border: 1px solid var(--border, #2a313c);
      border-radius: var(--radius-sm, 9px);
      padding: 8px 10px;
      margin-bottom: 14px;
      transition: border-color 0.15s ease, box-shadow 0.15s ease;
    }
    solar-login-page input:-webkit-autofill,
    solar-login-page input:-webkit-autofill:hover,
    solar-login-page input:-webkit-autofill:focus {
      -webkit-text-fill-color: var(--text, #e6e9ef);
      -webkit-box-shadow: 0 0 0 1000px var(--panel-2, #1c222b) inset;
      box-shadow: 0 0 0 1000px var(--panel-2, #1c222b) inset;
      transition: background-color 99999s ease-in-out 0s;
    }
    solar-login-page input:focus-visible {
      outline: none;
      border-color: var(--accent-2, #4cc2ff);
      box-shadow: var(--ring, 0 0 0 3px rgba(76, 194, 255, 0.35));
    }
    solar-login-page button {
      font: inherit;
      font-weight: 600;
      color: var(--text, #e6e9ef);
      background: var(--panel-2, #1c222b);
      border: 1px solid var(--border, #2a313c);
      border-radius: var(--radius-sm, 9px);
      padding: 8px 14px;
      cursor: pointer;
      -webkit-tap-highlight-color: transparent;
      transition: background 0.15s ease, border-color 0.15s ease, transform 0.05s ease,
        box-shadow 0.15s ease;
    }
    solar-login-page button:hover {
      background: var(--panel-3, #232a34);
      border-color: var(--border-strong, #39414e);
    }
    solar-login-page button:active { transform: translateY(1px); }
    solar-login-page button:focus-visible {
      outline: none;
      box-shadow: var(--ring, 0 0 0 3px rgba(76, 194, 255, 0.35));
    }
    solar-login-page button:disabled { opacity: 0.5; cursor: not-allowed; }
    solar-login-page button.primary {
      width: 100%;
      margin-top: 4px;
      background: var(--accent, #ffb020);
      background: linear-gradient(
        180deg,
        var(--accent, #ffb020),
        color-mix(in srgb, var(--accent, #ffb020) 82%, black)
      );
      color: #1a1205;
      border-color: transparent;
    }
    solar-login-page button.primary:hover { filter: brightness(1.06); }
    @media (hover: none) {
      solar-login-page button:hover {
        background: var(--panel-2, #1c222b);
        border-color: var(--border, #2a313c);
      }
      solar-login-page button.primary:hover { filter: none; }
    }
    @media (prefers-reduced-motion: reduce) {
      solar-login-page * {
        animation-duration: 0.001ms !important;
        transition-duration: 0.001ms !important;
      }
    }
  `;
  document.head.appendChild(style);
}

@customElement("solar-login-page")
export class LoginPage extends LitElement {
  constructor() {
    super();
    new LocaleController(this);
  }

  createRenderRoot() {
    return this;
  }

  connectedCallback(): void {
    super.connectedCallback();
    ensureLoginStyles();
  }

  @state() private busy = false;

  private async submit(e: Event): Promise<void> {
    e.preventDefault();
    if (this.busy) return;
    const form = e.currentTarget as HTMLFormElement;
    const data = new FormData(form);
    const username = String(data.get("username") ?? "").trim();
    const password = String(data.get("password") ?? "");
    this.busy = true;
    const ok = await runWithToast(
      async () => {
        await api.login(username, password);
      },
      { loading: t("login.toastLoading"), success: t("login.toastSuccess") },
    );
    if (ok) {
      this.dispatchEvent(new CustomEvent("solar-login-success", { bubbles: true, composed: true }));
    }
    this.busy = false;
  }

  render() {
    return html`
      <div class="card">
        <h1>${t("app.title")}</h1>
        <p class="sub">${t("login.sub")}</p>
        <form method="post" action="#" @submit=${this.submit}>
          <label for="username">${t("login.username")}</label>
          <input
            id="username"
            name="username"
            type="text"
            autocomplete="username"
            placeholder=${t("login.placeholder")}
            spellcheck="false"
            autocapitalize="off"
            required
          />
          <label for="password">${t("login.password")}</label>
          <input
            id="password"
            name="password"
            type="password"
            autocomplete="current-password"
            required
          />
          <button class="primary" type="submit" ?disabled=${this.busy}>
            ${this.busy ? t("login.signingIn") : t("login.signIn")}
          </button>
        </form>
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "solar-login-page": LoginPage;
  }
}
