import { css } from "lit";

// Shared utility styles for all components. Design tokens (--bg, --accent, ...)
// are defined globally on :root in index.html so they inherit into every shadow
// tree and can be switched via [data-theme]. Components only consume them here.
export const sharedStyles = css`
  :host {
    font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
    color: var(--text);
  }

  .card {
    position: relative;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: var(--card-pad, 18px);
    box-shadow: var(--shadow);
    transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
  }
  .card:hover {
    border-color: var(--border-strong);
  }
  .card.busy {
    opacity: 0.7;
    pointer-events: none;
  }

  .card h3 {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 0 0 14px;
    font-size: 0.82rem;
    font-weight: 700;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }
  .card h3::before {
    content: "";
    width: 3px;
    height: 13px;
    border-radius: 2px;
    background: linear-gradient(180deg, var(--accent), var(--accent-2));
  }

  .grid {
    display: grid;
    gap: var(--gap, 16px);
  }

  .row {
    display: flex;
    gap: 12px;
    align-items: center;
    flex-wrap: wrap;
  }

  .metric {
    font-size: var(--metric, 2rem);
    font-weight: 700;
    line-height: 1.1;
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.01em;
  }

  .label {
    color: var(--muted);
    font-size: 0.8rem;
  }

  .pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 600;
    border: 1px solid var(--border);
    white-space: nowrap;
  }

  .pill.good { background: rgba(47, 191, 113, 0.15); color: var(--good); border-color: rgba(47, 191, 113, 0.3); }
  .pill.warn { background: rgba(240, 162, 2, 0.15); color: var(--warn); border-color: rgba(240, 162, 2, 0.3); }
  .pill.bad { background: rgba(229, 72, 77, 0.15); color: var(--bad); border-color: rgba(229, 72, 77, 0.3); }
  .pill.critical { background: rgba(255, 45, 85, 0.18); color: var(--critical); border-color: rgba(255, 45, 85, 0.35); }
  .pill.muted { color: var(--muted); }

  button {
    font: inherit;
    font-weight: 600;
    color: var(--text);
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 8px 14px;
    cursor: pointer;
    transition: background 0.15s ease, border-color 0.15s ease, transform 0.05s ease,
      box-shadow 0.15s ease;
  }
  button:hover { background: var(--panel-3); border-color: var(--border-strong); }
  button:active { transform: translateY(1px); }
  button:focus-visible { outline: none; box-shadow: var(--ring); }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  button.primary {
    background: var(--accent);
    background: linear-gradient(180deg, var(--accent), color-mix(in srgb, var(--accent) 82%, black));
    color: #1a1205;
    border-color: transparent;
  }
  button.primary:hover { filter: brightness(1.06); }
  button.danger { background: rgba(229, 72, 77, 0.15); color: var(--bad); border-color: rgba(229, 72, 77, 0.45); }
  button.danger:hover { background: rgba(229, 72, 77, 0.25); }

  input[type="number"],
  input[type="text"],
  input[type="password"],
  select,
  textarea {
    font: inherit;
    color: var(--text);
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 8px 10px;
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
  }
  input:focus-visible,
  select:focus-visible,
  textarea:focus-visible {
    outline: none;
    border-color: var(--accent-2);
    box-shadow: var(--ring);
  }
  input[type="checkbox"] {
    width: 16px;
    height: 16px;
    accent-color: var(--accent-2);
    cursor: pointer;
  }

  .checkbox-row {
    flex-direction: row;
    align-items: center;
    gap: 8px;
  }
  .checkbox-row label {
    order: 1;
    margin: 0;
    cursor: pointer;
  }
  .checkbox-row input[type="checkbox"] {
    order: 0;
    flex-shrink: 0;
  }

  a { color: var(--accent-2); }

  .dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
  .dot.on { background: var(--good); box-shadow: 0 0 8px var(--good); }
  .dot.off { background: var(--muted); }

  /* Loading shimmer for empty states. */
  .skeleton {
    border-radius: var(--radius-sm);
    background: linear-gradient(
      90deg,
      var(--panel-2) 25%,
      var(--panel-3) 37%,
      var(--panel-2) 63%
    );
    background-size: 400% 100%;
    animation: shimmer 1.4s ease infinite;
  }
  @keyframes shimmer {
    0% { background-position: 100% 0; }
    100% { background-position: 0 0; }
  }

  @media (prefers-reduced-motion: reduce) {
    * { animation-duration: 0.001ms !important; transition-duration: 0.001ms !important; }
  }
`;
