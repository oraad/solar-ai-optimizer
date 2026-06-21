import { afterEach, describe, expect, it, vi } from "vitest";

import {
  TOAST_DISMISS,
  TOAST_SHOW,
  TOAST_UPDATE,
  dismissToast,
  runWithToast,
  showToast,
  updateToast,
} from "./toast.js";

describe("toast", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("showToast dispatches solar-toast-show", () => {
    const handler = vi.fn();
    window.addEventListener(TOAST_SHOW, handler);
    const id = showToast({ message: "Hello", variant: "success" });
    expect(id).toMatch(/^toast-/);
    expect(handler).toHaveBeenCalledOnce();
    const detail = (handler.mock.calls[0][0] as CustomEvent).detail;
    expect(detail.message).toBe("Hello");
    expect(detail.variant).toBe("success");
    expect(detail.persistent).toBe(false);
    expect(detail.durationMs).toBe(5000);
    window.removeEventListener(TOAST_SHOW, handler);
  });

  it("showToast uses persistent loading by default", () => {
    const handler = vi.fn();
    window.addEventListener(TOAST_SHOW, handler);
    showToast({ message: "Wait", variant: "loading" });
    const detail = (handler.mock.calls[0][0] as CustomEvent).detail;
    expect(detail.persistent).toBe(true);
    expect(detail.durationMs).toBeUndefined();
    window.removeEventListener(TOAST_SHOW, handler);
  });

  it("updateToast dispatches solar-toast-update", () => {
    const handler = vi.fn();
    window.addEventListener(TOAST_UPDATE, handler);
    updateToast("toast-1", { message: "Updated", variant: "info" });
    expect(handler).toHaveBeenCalledOnce();
    const detail = (handler.mock.calls[0][0] as CustomEvent).detail;
    expect(detail).toEqual({ id: "toast-1", message: "Updated", variant: "info" });
    window.removeEventListener(TOAST_UPDATE, handler);
  });

  it("dismissToast dispatches solar-toast-dismiss", () => {
    const handler = vi.fn();
    window.addEventListener(TOAST_DISMISS, handler);
    dismissToast("toast-2");
    expect(handler).toHaveBeenCalledOnce();
    const detail = (handler.mock.calls[0][0] as CustomEvent).detail;
    expect(detail).toEqual({ id: "toast-2" });
    window.removeEventListener(TOAST_DISMISS, handler);
  });

  it("runWithToast shows loading then success on resolve", async () => {
    const events: string[] = [];
    const onShow = (e: Event) => {
      const d = (e as CustomEvent).detail;
      events.push(`show:${d.variant}:${d.message}`);
    };
    const onDismiss = (e: Event) => {
      events.push(`dismiss:${(e as CustomEvent).detail.id}`);
    };
    window.addEventListener(TOAST_SHOW, onShow);
    window.addEventListener(TOAST_DISMISS, onDismiss);

    const ok = await runWithToast(
      async () => {
        /* noop */
      },
      { loading: "Working…", success: "Done." },
    );

    expect(ok).toBe(true);
    expect(events[0]).toBe("show:loading:Working…");
    expect(events[1]).toMatch(/^dismiss:toast-/);
    expect(events[2]).toBe("show:success:Done.");

    window.removeEventListener(TOAST_SHOW, onShow);
    window.removeEventListener(TOAST_DISMISS, onDismiss);
  });

  it("runWithToast shows loading then error on reject", async () => {
    const shown: Array<{ variant: string; message: string }> = [];
    const onShow = (e: Event) => {
      const d = (e as CustomEvent).detail;
      shown.push({ variant: d.variant, message: d.message });
    };
    window.addEventListener(TOAST_SHOW, onShow);

    const ok = await runWithToast(
      async () => {
        throw new Error("boom");
      },
      { loading: "Working…", success: "Done." },
    );

    expect(ok).toBe(false);
    expect(shown[0]).toEqual({ variant: "loading", message: "Working…" });
    expect(shown[1]).toEqual({ variant: "error", message: "Error: boom" });

    window.removeEventListener(TOAST_SHOW, onShow);
  });
});
