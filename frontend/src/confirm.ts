export interface ConfirmDialogOptions {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  requireText?: string;
}

export interface ConfirmRequestDetail {
  id: string;
  opts: ConfirmDialogOptions;
}

export interface ConfirmResponseDetail {
  id: string;
  confirmed: boolean;
}

export const CONFIRM_REQUEST = "solar-confirm-request";
export const CONFIRM_RESPONSE = "solar-confirm-response";

let idCounter = 0;

export function confirmDialog(opts: ConfirmDialogOptions): Promise<boolean> {
  const id = `confirm-${++idCounter}`;
  return new Promise<boolean>((resolve) => {
    const handler = (e: Event): void => {
      const detail = (e as CustomEvent<ConfirmResponseDetail>).detail;
      if (detail?.id !== id) return;
      window.removeEventListener(CONFIRM_RESPONSE, handler);
      resolve(detail.confirmed);
    };
    window.addEventListener(CONFIRM_RESPONSE, handler);
    window.dispatchEvent(
      new CustomEvent<ConfirmRequestDetail>(CONFIRM_REQUEST, {
        detail: { id, opts },
      }),
    );
  });
}
