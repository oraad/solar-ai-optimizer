/** Shared scroll offset helpers for settings nav jump + scroll-spy. */

const CHROME_FALLBACK_PX = 72;
const SCROLL_BUFFER_PX = 8;

export function readAppChromeHeightPx(fallback = CHROME_FALLBACK_PX): number {
  const app = document.querySelector("solar-app");
  const raw = getComputedStyle(app ?? document.documentElement)
    .getPropertyValue("--app-chrome-height")
    .trim();
  const n = parseFloat(raw);
  return Number.isFinite(n) && n > 0 ? Math.ceil(n) : fallback;
}

export function readSettingsMobileNavHeightPx(): number {
  const panel = document.querySelector("solar-settings-panel");
  if (!panel) return 0;
  const raw = getComputedStyle(panel).getPropertyValue("--settings-mobile-nav-height").trim();
  const n = parseFloat(raw);
  return Number.isFinite(n) && n > 0 ? Math.ceil(n) : 0;
}

export function sectionObserverRootMargin(mobileNavHeight = 0): string {
  const top = readAppChromeHeightPx() + SCROLL_BUFFER_PX + mobileNavHeight;
  return `-${top}px 0px -60% 0px`;
}

export function releaseAfterProgrammaticScroll(
  onRelease: () => void,
  reduceMotion: boolean,
): void {
  if (reduceMotion) {
    onRelease();
    return;
  }
  let released = false;
  const release = () => {
    if (released) return;
    released = true;
    onRelease();
  };
  if ("onscrollend" in window) {
    window.addEventListener("scrollend", release, { once: true });
  }
  let lastY = window.scrollY;
  let stable = 0;
  const poll = () => {
    if (released) return;
    const y = window.scrollY;
    if (y === lastY) {
      stable += 1;
      if (stable >= 2) {
        release();
        return;
      }
    } else {
      stable = 0;
      lastY = y;
    }
    window.setTimeout(poll, 50);
  };
  window.setTimeout(poll, 50);
  window.setTimeout(release, 1200);
}
