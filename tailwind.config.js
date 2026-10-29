/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./frontend/index.html", "./frontend/app.js"],
  // The existing stylesheet owns base styles, so Tailwind's preflight stays off.
  corePlugins: { preflight: false },
  theme: {
    extend: {
      colors: {
        // Read the live theme tokens, so utilities follow light and dark mode.
        brand: "var(--brand)",
        "brand-soft": "var(--brand-soft)",
        surface: "var(--surface)",
        "surface-2": "var(--surface-2)",
        ink: "var(--text)",
        "ink-2": "var(--text-2)",
        "ink-3": "var(--text-3)",
        good: "var(--good)",
        "good-soft": "var(--good-soft)",
        warn: "var(--warn)",
        "warn-soft": "var(--warn-soft)",
        bad: "var(--bad)",
        "bad-soft": "var(--bad-soft)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(14px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        "pop-in": {
          "0%": { opacity: "0", transform: "scale(.85)" },
          "70%": { opacity: "1", transform: "scale(1.04)" },
          "100%": { transform: "scale(1)" },
        },
        "slide-in": {
          "0%": { opacity: "0", transform: "translateX(-10px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-6px)" },
        },
        "ring-pulse": {
          "0%": { boxShadow: "0 0 0 0 color-mix(in srgb, var(--brand) 45%, transparent)" },
          "100%": { boxShadow: "0 0 0 14px transparent" },
        },
      },
      animation: {
        "fade-up": "fade-up .6s cubic-bezier(.2,.7,.2,1) both",
        "fade-in": "fade-in .4s ease both",
        "pop-in": "pop-in .45s cubic-bezier(.2,.8,.2,1) both",
        "slide-in": "slide-in .4s cubic-bezier(.2,.7,.2,1) both",
        shimmer: "shimmer 1.6s linear infinite",
        float: "float 5s ease-in-out infinite",
        "ring-pulse": "ring-pulse 1.8s ease-out infinite",
      },
      transitionTimingFunction: {
        spring: "cubic-bezier(.2,.8,.2,1)",
      },
    },
  },
  plugins: [],
};
