export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        teal:    { DEFAULT: "#0F6E62", dark: "#0A5249", mid: "#1A8C7D", tint: "#E6F4F2" },
        ink:     { DEFAULT: "#14233A", muted: "#4B5D73" },
        surface: "#F7F8F6",
        paper:   "#FFFFFF",
        line:    "#E3E6E1",
        pass:    { DEFAULT: "#2E7D54", bg: "#EAF6EF" },
        fail:    { DEFAULT: "#C0392B", bg: "#FDECEA" },
        partial: { DEFAULT: "#C77D11", bg: "#FEF4E3" },
        seal:    "#B23A3A",
      },
      fontFamily: {
        sans: ["'Be Vietnam Pro'", "-apple-system", "BlinkMacSystemFont", "'Segoe UI'", "sans-serif"],
        mono: ["'IBM Plex Mono'", "'SF Mono'", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
