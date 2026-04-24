/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        mono: ['"JetBrains Mono"', '"SF Mono"', 'Menlo', 'monospace'],
      },
      colors: {
        term: {
          bg: '#0a0a0a',
          panel: '#111111',
          border: '#1f1f1f',
          dim: '#6b7280',
          fg: '#e5e7eb',
          accent: '#34d399',
          warn: '#fbbf24',
          err: '#f87171',
          link: '#60a5fa',
        },
      },
    },
  },
  plugins: [],
}
