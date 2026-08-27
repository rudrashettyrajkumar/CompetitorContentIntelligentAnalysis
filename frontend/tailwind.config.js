/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0f172a",
        panel: "#ffffff",
        muted: "#64748b",
        line: "#e2e8f0",
        brand: "#4f46e5",
      },
    },
  },
  plugins: [],
};
