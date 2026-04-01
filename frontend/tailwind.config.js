/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ["\"Space Grotesk\"", "ui-sans-serif", "system-ui"],
        body: ["\"IBM Plex Sans\"", "ui-sans-serif", "system-ui"],
      },
      colors: {
        ink: "var(--color-ink)",
        paper: "var(--color-paper)",
        mist: "var(--color-mist)",
        ember: "var(--color-ember)",
        moss: "var(--color-moss)",
        ocean: "var(--color-ocean)",
        haze: "var(--color-haze)",
      },
      boxShadow: {
        card: "0 16px 40px -30px rgba(15, 23, 42, 0.45)",
      },
    },
  },
  plugins: [],
};
