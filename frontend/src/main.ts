import "uplot/dist/uPlot.min.css";
import { initI18n, t } from "./i18n.js";

void (async () => {
  await initI18n();
  const splash = document.querySelector("#boot-splash .boot-splash-sub");
  if (splash) splash.textContent = t("app.bootSub");
  const title = document.querySelector("#boot-splash h1");
  if (title) title.textContent = t("app.title");
  await import("./components/toast-host.js");
  await import("./components/app-root.js");
})();
