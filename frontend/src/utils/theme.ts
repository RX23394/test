const THEME_STORAGE_KEY = "network-rag-theme";

/** Apply a dark or light theme to the document root. */
export function applyTheme(dark: boolean): void {
  document.documentElement.classList.toggle("dark", dark);
  document.documentElement.style.colorScheme = dark ? "dark" : "light";
  localStorage.setItem(THEME_STORAGE_KEY, dark ? "dark" : "light");
}

/** Initialize the saved theme or follow the operating-system preference. */
export function initializeTheme(): boolean {
  const savedTheme = localStorage.getItem(THEME_STORAGE_KEY);
  const prefersDark = window.matchMedia?.("(prefers-color-scheme: dark)").matches;
  const dark = savedTheme ? savedTheme === "dark" : (prefersDark ?? false);
  applyTheme(dark);
  return dark;
}
