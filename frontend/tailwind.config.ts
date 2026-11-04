import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-outfit)", "system-ui", "sans-serif"],
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "Consolas",
          "monospace",
        ],
      },
      colors: {
        background: "#090a0f",
        foreground: "#f4f4f6",
        card: {
          DEFAULT: "#111218",
          foreground: "#f4f4f6",
          border: "#1f212a",
        },
        popover: {
          DEFAULT: "#13141b",
          foreground: "#f4f4f6",
        },
        surface: {
          DEFAULT: "#14151d",
          hover: "#1a1c26",
          active: "#212330",
          subtle: "#0e0f15",
          border: "#232533",
        },
        primary: {
          DEFAULT: "#BCDDDC",
          foreground: "#090a0f",
          hover: "#72B0AB",
          muted: "rgba(188, 221, 220, 0.12)",
          light: "#BCDDDC",
          dark: "#72B0AB",
        },
        secondary: {
          DEFAULT: "#232533",
          foreground: "#e2e4ea",
          hover: "#2c2e3f",
        },
        muted: {
          DEFAULT: "#191a24",
          foreground: "#8f93a3",
        },
        accent: {
          DEFAULT: "#38bdf8",
          foreground: "#041521",
        },
        status: {
          healthy: "#72B0AB",
          warning: "#f59e0b",
          unhealthy: "#ef4444",
          offline: "#71717a",
          info: "#06b6d4",
        },
        emerald: {
          50: "#f4faf9",
          100: "#e6f4f3",
          200: "#d2ebe9",
          300: "#BCDDDC",
          400: "#BCDDDC",
          500: "#72B0AB",
          600: "#5c9691",
          700: "#487874",
          800: "#385e5b",
          900: "#2d4b49",
          950: "#162726",
        },
        border: "#232533",
        input: "#1d1f2a",
        ring: "#72B0AB",
      },
      borderRadius: {
        lg: "0.5rem",
        md: "0.375rem",
        sm: "0.25rem",
      },
    },
  },
  plugins: [],
};

export default config;
