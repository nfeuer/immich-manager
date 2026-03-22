/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        'immich-primary': '#4250af',
        'immich-bg': '#0f0f11',
        'immich-surface': '#1a1a27',
        'immich-border': '#2a2a3d',
        'immich-text': '#f1f0ff',
        'immich-muted': '#7c7c9a',
      },
      fontFamily: {
        sans: ['system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
