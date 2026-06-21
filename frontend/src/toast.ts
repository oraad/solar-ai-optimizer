export type ToastVariant = "loading" | "info" | "success" | "error";

export interface ToastShowDetail {
  id: string;
  message: string;
  variant: ToastVariant;
  persistent: boolean;
  durationMs?: number;
}

export interface ToastUpdateDetail {
  id: string;
  message?: string;
  variant?: ToastVariant;
}

export interface ToastDismissDetail {
  id: string;
}

export const TOAST_SHOW = "solar-toast-show";
export const TOAST_UPDATE = "solar-toast-update";
export const TOAST_DISMISS = "solar-toast-dismiss";

const DEFAULT_DURATION_MS: Record<Exclude<ToastVariant, "loading">, number> = {
  info: 5000,
  success: 5000,
  error: 8000,
};

let idCounter = 0;

function nextId(provided?: string): string {
  return provided ?? `toast-${++idCounter}`;
}

export function showToast(opts: {
  message: string;
  variant: ToastVariant;
  id?: string;
  persistent?: boolean;
  durationMs?: number;
}): string {
  const id = nextId(opts.id);
  const persistent = opts.persistent ?? opts.variant === "loading";
  const durationMs =
    opts.durationMs ??
    (persistent || opts.variant === "loading" ? undefined : DEFAULT_DURATION_MS[opts.variant]);

  window.dispatchEvent(
    new CustomEvent<ToastShowDetail>(TOAST_SHOW, {
      detail: {
        id,
        message: opts.message,
        variant: opts.variant,
        persistent,
        durationMs,
      },
    }),
  );
  return id;
}

export function updateToast(
  id: string,
  opts: { message?: string; variant?: ToastVariant },
): void {
  window.dispatchEvent(
    new CustomEvent<ToastUpdateDetail>(TOAST_UPDATE, {
      detail: { id, ...opts },
    }),
  );
}

export function dismissToast(id: string): void {
  window.dispatchEvent(
    new CustomEvent<ToastDismissDetail>(TOAST_DISMISS, {
      detail: { id },
    }),
  );
}

export async function runWithToast(
  fn: () => Promise<void>,
  opts: { loading: string; success: string; id?: string },
): Promise<boolean> {
  const toastId = showToast({
    message: opts.loading,
    variant: "loading",
    id: opts.id,
    persistent: true,
  });
  try {
    await fn();
    dismissToast(toastId);
    showToast({ message: opts.success, variant: "success" });
    return true;
  } catch (e) {
    dismissToast(toastId);
    const msg = e instanceof Error ? e.message : String(e);
    showToast({
      message: msg.startsWith("Error:") ? msg : `Error: ${msg}`,
      variant: "error",
    });
    return false;
  }
}
