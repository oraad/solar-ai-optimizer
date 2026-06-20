import { LitElement, css, html } from "lit";
import { customElement, state } from "lit/decorators.js";

import { api } from "../api.js";
import { sharedStyles } from "../styles.js";

@customElement("solar-login-page")
export class LoginPage extends LitElement {
  /** Light DOM so password managers can discover the login form reliably. */
  createRenderRoot() {
    return this;
  }

  static styles = [
    sharedStyles,
    css`
      :host {
        display: grid;
        min-height: 100vh;
        place-items: center;
        padding: 24px;
        box-sizing: border-box;
      }
      .card {
        width: min(420px, 100%);
      }
      h1 {
        margin: 0 0 6px;
        font-size: 1.25rem;
      }
      .sub {
        margin: 0 0 20px;
        color: var(--muted);
        font-size: 0.85rem;
      }
      label {
        display: block;
        font-size: 0.78rem;
        color: var(--muted);
        margin-bottom: 6px;
      }
      input {
        width: 100%;
        box-sizing: border-box;
        margin-bottom: 14px;
      }
      button.primary {
        width: 100%;
        margin-top: 4px;
      }
      .err {
        margin: 0 0 12px;
        padding: 8px 10px;
        border-radius: var(--radius-sm);
        font-size: 0.82rem;
        color: var(--bad);
        background: color-mix(in srgb, var(--bad) 12%, var(--panel-2));
        border: 1px solid var(--border);
      }
    `,
  ];

  @state() private error = "";
  @state() private busy = false;

  private async submit(e: Event): Promise<void> {
    e.preventDefault();
    if (this.busy) return;
    const form = e.currentTarget as HTMLFormElement;
    const data = new FormData(form);
    const username = String(data.get("username") ?? "").trim();
    const password = String(data.get("password") ?? "");
    this.busy = true;
    this.error = "";
    try {
      await api.login(username, password);
      this.dispatchEvent(new CustomEvent("solar-login-success", { bubbles: true, composed: true }));
    } catch (err) {
      this.error = err instanceof Error ? err.message : "Login failed";
    } finally {
      this.busy = false;
    }
  }

  render() {
    return html`
      <div class="card">
        <h1>Solar AI Optimizer</h1>
        <p class="sub">Sign in with your local admin account.</p>
        ${this.error ? html`<div class="err">${this.error}</div>` : null}
        <form method="post" action="#" @submit=${this.submit}>
          <label for="username">Username</label>
          <input
            id="username"
            name="username"
            type="text"
            autocomplete="username"
            placeholder="admin"
            spellcheck="false"
            autocapitalize="off"
            required
          />
          <label for="password">Password</label>
          <input
            id="password"
            name="password"
            type="password"
            autocomplete="current-password"
            required
          />
          <button class="primary" type="submit" ?disabled=${this.busy}>
            ${this.busy ? "Signing in…" : "Sign in"}
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
