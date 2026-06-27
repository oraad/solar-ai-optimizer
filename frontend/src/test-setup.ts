import { vi } from "vitest";

// Node 25+ exposes a broken experimental localStorage stub on globalThis that shadows
// jsdom's Storage (methods like getItem/clear are missing). Replace it with an in-memory shim.
if (typeof window !== "undefined") {
  const candidate = globalThis.localStorage;
  const isBroken = !candidate || typeof candidate.getItem !== "function";
  if (isBroken) {
    const data = new Map<string, string>();
    const memoryStorage: Storage = {
      get length() {
        return data.size;
      },
      clear() {
        data.clear();
      },
      getItem(key: string) {
        return data.has(key) ? (data.get(key) ?? null) : null;
      },
      setItem(key: string, value: string) {
        data.set(key, String(value));
      },
      removeItem(key: string) {
        data.delete(key);
      },
      key(index: number) {
        return Array.from(data.keys())[index] ?? null;
      },
    };
    Object.defineProperty(globalThis, "localStorage", {
      configurable: true,
      writable: true,
      value: memoryStorage,
    });
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      writable: true,
      value: memoryStorage,
    });
  }
}

// jsdom 29+ does not implement matchMedia; components use it for responsive/touch UI.
vi.stubGlobal(
  "matchMedia",
  vi.fn((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
);
