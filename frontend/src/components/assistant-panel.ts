import { LitElement, css, html } from "lit";
import { customElement, query, state } from "lit/decorators.js";

import { api } from "../api.js";
import { assistantHelp } from "../field-help.js";
import { labelWithTip } from "../label-tip.js";
import { sharedStyles } from "../styles.js";
import "./info-tip.js";

interface Msg {
  role: "you" | "assistant";
  text: string;
  blocked?: boolean;
  blockReason?: string | null;
}

@customElement("solar-assistant-panel")
export class AssistantPanel extends LitElement {
  static styles = [
    sharedStyles,
    css`
      .log {
        display: flex; flex-direction: column; gap: 10px; margin-bottom: 14px;
        height: 420px; max-height: 55vh; overflow-y: auto; padding-right: 4px;
      }
      @media (max-width: 760px) { .log { height: 320px; } }
      .row { display: flex; flex-direction: column; gap: 3px; max-width: 85%; }
      .row.you { align-self: flex-end; align-items: flex-end; }
      .row.assistant { align-self: flex-start; align-items: flex-start; }
      .badge { font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); padding: 0 4px; }
      .bubble { padding: 9px 13px; border-radius: 13px; font-size: 0.88rem; line-height: 1.45; white-space: pre-wrap; }
      .you .bubble { background: var(--panel-2); border: 1px solid var(--border); border-bottom-right-radius: 4px; }
      .assistant .bubble {
        background: color-mix(in srgb, var(--accent-2) 14%, var(--panel));
        background: rgba(76,194,255,0.12);
        border: 1px solid color-mix(in srgb, var(--accent-2) 30%, var(--border));
        border-bottom-left-radius: 4px;
      }
      .typing { display: inline-flex; gap: 4px; padding: 11px 14px; }
      .typing span { width: 6px; height: 6px; border-radius: 50%; background: var(--muted); animation: blink 1.2s infinite; }
      .typing span:nth-child(2) { animation-delay: 0.2s; }
      .typing span:nth-child(3) { animation-delay: 0.4s; }
      @keyframes blink { 0%, 60%, 100% { opacity: 0.25; } 30% { opacity: 1; } }
      .inputrow { display: flex; gap: 8px; }
      .inputrow input { flex: 1; }
      label.apply { display: flex; align-items: center; gap: 6px; color: var(--muted); font-size: 0.8rem; margin-top: 10px; }
      .apply-row {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-top: 10px;
        color: var(--muted);
        font-size: 0.8rem;
      }
      .apply-row label { margin: 0; cursor: pointer; display: inline-flex; align-items: center; }
      .hint { color: var(--muted); font-size: 0.78rem; margin-top: 8px; }
      .banner {
        padding: 8px 12px; border-radius: var(--radius-sm); margin-bottom: 6px;
        font-size: 0.8rem; border: 1px solid var(--border);
        background: color-mix(in srgb, var(--bad) 12%, var(--panel-2));
        color: var(--bad);
      }
    `,
  ];

  @state() private msgs: Msg[] = [];
  @state() private input = "";
  @state() private apply = false;
  @state() private busy = false;
  @query(".log") private logEl!: HTMLDivElement;

  updated(): void {
    if (this.logEl) this.logEl.scrollTop = this.logEl.scrollHeight;
  }

  private async send(): Promise<void> {
    const q = this.input.trim();
    if (!q || this.busy) return;
    this.msgs = [...this.msgs, { role: "you", text: q }];
    this.input = "";
    this.busy = true;
    try {
      const res = await api.ask(q, this.apply);
      let text = res.answer;
      if (res.applied) text += "  [override applied]";
      else if (res.intent && !this.apply) text += "  [intent detected; tick 'apply' to execute]";
      this.msgs = [
        ...this.msgs,
        {
          role: "assistant",
          text,
          blocked: res.blocked,
          blockReason: res.block_reason,
        },
      ];
    } catch (e) {
      this.msgs = [...this.msgs, { role: "assistant", text: `Error: ${(e as Error).message}` }];
    } finally {
      this.busy = false;
    }
  }

  render() {
    return html`
      <div class="card">
        <h3>Assistant</h3>
        <div class="log">
          ${this.msgs.length === 0
            ? html`<p class="label">Ask things like "why did you grid-charge?", "force charge now", or "set reserve to 60%".</p>`
            : this.msgs.map(
                (m) => html`
                  <div class="row ${m.role}">
                    <span class="badge">${m.role}</span>
                    ${m.blocked && m.blockReason === "kill_switch_confirm_required"
                      ? html`<div class="banner">
                          Kill switch blocked — include a confirmation word in your message
                          (e.g. <strong>engage kill switch confirm</strong>) with Apply checked.
                        </div>`
                      : null}
                    <div class="bubble">${m.text}</div>
                  </div>
                `,
              )}
          ${this.busy
            ? html`
                <div class="row assistant">
                  <span class="badge">assistant</span>
                  <div class="bubble typing"><span></span><span></span><span></span></div>
                </div>
              `
            : null}
        </div>
        <div class="inputrow">
          <input
            type="text"
            placeholder="Ask or command..."
            .value=${this.input}
            @input=${(e: Event) => (this.input = (e.target as HTMLInputElement).value)}
            @keydown=${(e: KeyboardEvent) => { if (e.key === "Enter") void this.send(); }}
          />
          <button class="primary" @click=${() => void this.send()} ?disabled=${this.busy}>Send</button>
        </div>
        <div class="apply-row checkbox-row">
          <input type="checkbox" .checked=${this.apply} @change=${(e: Event) => (this.apply = (e.target as HTMLInputElement).checked)} />
          <label>${labelWithTip("Allow assistant to apply control commands", assistantHelp("apply"))}</label>
        </div>
        <div class="hint">
          The LLM only writes explanations. Commands are parsed deterministically
          and applied only with the checkbox above.
        </div>
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "solar-assistant-panel": AssistantPanel;
  }
}
