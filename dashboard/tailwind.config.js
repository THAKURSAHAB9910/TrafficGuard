/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Plus Jakarta Sans', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      colors: {
        slate: {
          950: '#060913',
          900: '#0b1120',
          850: '#10182c',
          800: '#1e293b',
          700: '#334155',
        }
      }
    },
  },
  plugins: [],
}
