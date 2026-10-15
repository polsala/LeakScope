import { create } from "zustand";
import { dictionaries, type Key, type Locale } from "./i18n";
type Theme = "dark" | "light" | "system";
const storedLocale = localStorage.getItem("leakscope.locale");
const storedTheme = localStorage.getItem("leakscope.theme");
export const useUI = create<{
  locale: Locale;
  theme: Theme;
  token: string;
  collapsed: boolean;
  notice: string;
  setLocale: (v: Locale) => void;
  setTheme: (v: Theme) => void;
  setToken: (v: string) => void;
  setCollapsed: (v: boolean) => void;
  notify: (v: string) => void;
}>((set) => ({
  locale: storedLocale === "es" || storedLocale === "en" ? storedLocale : "ca",
  theme:
    storedTheme === "light" || storedTheme === "system" ? storedTheme : "dark",
  token: sessionStorage.getItem("leakscope.token") || "",
  collapsed: false,
  notice: "",
  setLocale: (locale) => {
    localStorage.setItem("leakscope.locale", locale);
    set({ locale });
  },
  setTheme: (theme) => {
    localStorage.setItem("leakscope.theme", theme);
    set({ theme });
  },
  setToken: (token) => {
    sessionStorage.setItem("leakscope.token", token);
    set({ token });
  },
  setCollapsed: (collapsed) => set({ collapsed }),
  notify: (notice) => set({ notice }),
}));
export function useT() {
  const locale = useUI((s) => s.locale);
  return (key: Key) => dictionaries[locale][key];
}
