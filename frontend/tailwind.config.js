/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        workspace: "#0C0F17",
        panel: "rgba(18, 22, 34, 0.78)",
        card: "rgba(26, 32, 48, 0.85)",
        cardHover: "rgba(36, 44, 66, 0.95)",
        inputBg: "rgba(16, 20, 32, 0.9)",
        neonCyan: "#06B6D4",
        neonPurple: "#A855F7",
        neonIndigo: "#6366F1",
        neonEmerald: "#10B981",
        neonAmber: "#F59E0B",
        neonRose: "#F43F5E",
      },
      fontFamily: {
        body: ['Inter', '-apple-system', 'sans-serif'],
        display: ['Outfit', '-apple-system', 'sans-serif'],
      },
      boxShadow: {
        glowPurple: "0 0 35px rgba(168, 85, 247, 0.35)",
        glowCyan: "0 0 30px rgba(6, 182, 212, 0.4)",
        ambient: "0 20px 50px rgba(0, 0, 0, 0.6)",
      },
    },
  },
  plugins: [],
}
