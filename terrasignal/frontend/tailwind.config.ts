import type { Config } from "tailwindcss";

// Colors are CSS variables (see globals.css :root / .dark) so every token
// flips with the `dark` class — rgb(var(...) / <alpha-value>) keeps Tailwind's
// opacity modifiers (e.g. bg-band-green/10) working under dark mode too.
function themeColor(name: string) {
  return `rgb(var(--color-${name}) / <alpha-value>)`;
}

const config: Config = {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Risk bands — used consistently across queue, dashboard, drill-downs.
        band: {
          green: themeColor("band-green"),
          amber: themeColor("band-amber"),
          red: themeColor("band-red"),
        },
        ink: {
          DEFAULT: themeColor("ink"),
          muted: themeColor("ink-muted"),
          faint: themeColor("ink-faint"),
        },
        surface: {
          DEFAULT: themeColor("surface"),
          sunken: themeColor("surface-sunken"),
          border: themeColor("surface-border"),
        },
        brand: {
          DEFAULT: themeColor("brand"),
          dark: themeColor("brand-dark"),
        },
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
