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
        'immich-success': {
          DEFAULT: '#4ade80',
          muted: 'rgba(20, 83, 45, 0.4)',
          border: '#166534',
        },
        'immich-error': {
          DEFAULT: '#f87171',
          muted: 'rgba(127, 29, 29, 0.4)',
          border: '#991b1b',
        },
        'immich-warning': {
          DEFAULT: '#facc15',
          muted: 'rgba(113, 63, 18, 0.4)',
          border: '#a16207',
        },
        'immich-info': {
          DEFAULT: '#60a5fa',
          muted: 'rgba(30, 58, 138, 0.4)',
          border: '#1e40af',
        },
      },
      fontFamily: {
        sans: ['system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
