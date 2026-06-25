/**
 * Generates ar.json and fr.json from en.json with full key parity.
 * Run: npx tsx scripts/generate-ar-fr.mts
 */
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "src", "locales");

type Json = string | number | boolean | null | Json[] | { [k: string]: Json };

const FR: Record<string, string> = {
  "Solar AI Optimizer": "Solar AI Optimizer",
  "Verifying access…": "Vérification de l'accès…",
  "Loading Solar AI Optimizer": "Chargement de Solar AI Optimizer",
  Overview: "Aperçu",
  Forecast: "Prévision",
  History: "Historique",
  Assistant: "Assistant",
  "Load shedding": "Délestage",
  Settings: "Paramètres",
  Shedding: "Délestage",
  Chat: "Chat",
  "Display preferences": "Préférences d'affichage",
  Language: "Langue",
  "Date format": "Format de date",
  "Locale (browser default)": "Locale (navigateur par défaut)",
  "DD/MM/YY": "JJ/MM/AA",
  "YYYY-MM-DD (ISO)": "AAAA-MM-JJ (ISO)",
  English: "English",
  Français: "Français",
  العربية: "العربية",
  OFF: "ARRÊT",
  ON: "MARCHE",
  "Loading…": "Chargement…",
  "Save changes": "Enregistrer",
  present: "présent",
  absent: "absent",
  unknown: "inconnu",
  never: "jamais",
  charging: "charge",
  discharging: "décharge",
  idle: "inactif",
  device: "appareil",
  devices: "appareils",
  auto: "auto",
  "Sign in with your local admin account.": "Connectez-vous avec votre compte administrateur local.",
  Username: "Nom d'utilisateur",
  Password: "Mot de passe",
  "Signing in…": "Connexion…",
  "Sign in": "Se connecter",
  "Signed in.": "Connecté.",
  "Error: {message}": "Erreur : {message}",
  ">24h": ">24 h",
  "{m}m": "{m} min",
  "{h}h": "{h} h",
  "{h}h {m}m": "{h} h {m} min",
  "Full in ~{duration}": "Plein dans ~{duration}",
  "Reserve in ~{duration}": "Réserve dans ~{duration}",
};

const AR: Record<string, string> = {
  "Solar AI Optimizer": "محسّن الطاقة الشمسية",
  "Verifying access…": "جارٍ التحقق من الوصول…",
  "Loading Solar AI Optimizer": "جارٍ تحميل محسّن الطاقة الشمسية",
  Overview: "نظرة عامة",
  Forecast: "التنبؤ",
  History: "السجل",
  Assistant: "المساعد",
  "Load shedding": "تخفيف الأحمال",
  Settings: "الإعدادات",
  Shedding: "تخفيف",
  Chat: "محادثة",
  "Display preferences": "تفضيلات العرض",
  Language: "اللغة",
  "Date format": "تنسيق التاريخ",
  "Locale (browser default)": "اللغة المحلية (افتراضي المتصفح)",
  "DD/MM/YY": "يوم/شهر/سنة",
  "YYYY-MM-DD (ISO)": "سنة-شهر-يوم (ISO)",
  OFF: "إيقاف",
  ON: "تشغيل",
  "Loading…": "جارٍ التحميل…",
  "Save changes": "حفظ التغييرات",
  present: "متصل",
  absent: "غير متصل",
  unknown: "غير معروف",
  never: "أبداً",
  charging: "شحن",
  discharging: "تفريغ",
  idle: "خامل",
  device: "جهاز",
  devices: "أجهزة",
  auto: "تلقائي",
  "Sign in with your local admin account.": "سجّل الدخول بحساب المسؤول المحلي.",
  Username: "اسم المستخدم",
  Password: "كلمة المرور",
  "Signing in…": "جارٍ تسجيل الدخول…",
  "Sign in": "تسجيل الدخول",
  "Signed in.": "تم تسجيل الدخول.",
  "Error: {message}": "خطأ: {message}",
  ">24h": ">24 س",
  "{m}m": "{m} د",
  "{h}h": "{h} س",
  "{h}h {m}m": "{h} س {m} د",
  "Full in ~{duration}": "ممتلئ خلال ~{duration}",
  "Reserve in ~{duration}": "الاحتياطي خلال ~{duration}",
};

function translateValue(value: string, map: Record<string, string>): string {
  return map[value] ?? value;
}

function walk(obj: Json, map: Record<string, string>): Json {
  if (typeof obj === "string") return translateValue(obj, map);
  if (Array.isArray(obj)) return obj.map((v) => walk(v, map));
  if (obj && typeof obj === "object") {
    const out: Record<string, Json> = {};
    for (const [k, v] of Object.entries(obj)) {
      out[k] = walk(v, map);
    }
    return out;
  }
  return obj;
}

function main() {
  const en = JSON.parse(readFileSync(join(root, "en.json"), "utf8")) as Json;
  writeFileSync(join(root, "fr.json"), JSON.stringify(walk(en, FR), null, 2) + "\n", "utf8");
  writeFileSync(join(root, "ar.json"), JSON.stringify(walk(en, AR), null, 2) + "\n", "utf8");
  console.log("Wrote fr.json and ar.json (partial translation map; untranslated strings keep English)");
}

main();
