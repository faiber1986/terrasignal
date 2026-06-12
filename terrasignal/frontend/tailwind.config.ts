import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Risk bands — used consistently across queue, dashboard, drill-downs.
        band: {
          green: "#15803d",
          amber: "#b45309",
          red: "#b91c1c",
        },
        ink: {
          DEFAULT: "#0f172a",
          muted: "#475569",
          faint: "#94a3b8",
        },
        surface: {
          DEFAULT: "#ffffff",
          sunken: "#f8fafc",
          border: "#e2e8f0",
        },
        brand: {
          DEFAULT: "#0e7490",
          dark: "#155e75",
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
