import type { ReactiveController, ReactiveElement } from "lit";

import { LOCALE_CHANGE_EVENT } from "./i18n.js";

/** Re-render a Lit host when the active locale changes. */
export class LocaleController implements ReactiveController {
  constructor(private host: ReactiveElement) {
    host.addController(this);
  }

  private onChange = (): void => {
    this.host.requestUpdate();
  };

  hostConnected(): void {
    window.addEventListener(LOCALE_CHANGE_EVENT, this.onChange);
  }

  hostDisconnected(): void {
    window.removeEventListener(LOCALE_CHANGE_EVENT, this.onChange);
  }
}
