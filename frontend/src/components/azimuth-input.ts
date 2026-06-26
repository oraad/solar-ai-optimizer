import { LitElement, css, html } from "lit";
import { customElement, property } from "lit/decorators.js";

/** Compact azimuth compass (0° = north, 90° = east) beside a numeric input. */
@customElement("solar-azimuth-input")
export class AzimuthInput extends LitElement {
  static styles = css`
    :host {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    input[type="number"] {
      flex: 1;
      min-width: 0;
      box-sizing: border-box;
    }
    .compass {
      flex-shrink: 0;
      width: 44px;
      height: 44px;
      border-radius: 50%;
      border: 1px solid var(--border);
      background: var(--panel-2);
      position: relative;
    }
    .compass::before {
      content: "N";
      position: absolute;
      top: 2px;
      left: 50%;
      transform: translateX(-50%);
      font-size: 0.55rem;
      color: var(--muted);
      font-weight: 700;
    }
    .needle {
      position: absolute;
      inset: 6px;
      transform-origin: center center;
    }
    .needle::after {
      content: "";
      position: absolute;
      left: 50%;
      top: 2px;
      width: 2px;
      height: calc(50% - 2px);
      margin-left: -1px;
      border-radius: 1px;
      background: var(--accent);
    }
  `;

  @property({ type: Number }) value = 180;

  private normalizeAzimuth(n: number): number {
    if (!Number.isFinite(n)) return 0;
    return ((n % 360) + 360) % 360;
  }

  private onInput(e: Event): void {
    const n = Number((e.target as HTMLInputElement).value);
    this.value = this.normalizeAzimuth(n);
    this.dispatchEvent(
      new CustomEvent("azimuth-change", { detail: this.value, bubbles: true, composed: true }),
    );
  }

  render() {
    const az = this.normalizeAzimuth(this.value);
    return html`
      <div
        class="compass"
        role="img"
        aria-label=${`Azimuth ${az} degrees`}
      >
        <div class="needle" style="transform: rotate(${az}deg)"></div>
      </div>
      <input
        type="number"
        step="1"
        min="0"
        max="360"
        .value=${String(az)}
        @input=${this.onInput}
      />
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "solar-azimuth-input": AzimuthInput;
  }
}
