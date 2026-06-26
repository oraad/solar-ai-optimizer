/** Shared window event wiring for forecast/history uPlot components. */
export type ChartLifecycleHost = {
  requestUpdate: () => void;
};

export type ChartLifecycleOptions = {
  onThemeChange?: () => void;
  onDateFormatChange?: () => void;
  onLocaleChange?: () => void;
  localeReload?: () => void | Promise<void>;
};

export function bindChartLifecycle(
  host: ChartLifecycleHost,
  options: ChartLifecycleOptions,
): () => void {
  const onTheme = () => {
    options.onThemeChange?.();
  };
  const onDateFormat = () => {
    options.onDateFormatChange?.();
  };
  const onLocale = () => {
    options.onLocaleChange?.();
    options.localeReload?.();
    host.requestUpdate();
  };

  window.addEventListener("solar-theme-change", onTheme);
  window.addEventListener("solar-date-format-change", onDateFormat);
  window.addEventListener("solar-site-timezone-change", onDateFormat);
  window.addEventListener("solar-locale-change", onLocale);

  return () => {
    window.removeEventListener("solar-theme-change", onTheme);
    window.removeEventListener("solar-date-format-change", onDateFormat);
    window.removeEventListener("solar-site-timezone-change", onDateFormat);
    window.removeEventListener("solar-locale-change", onLocale);
  };
}
