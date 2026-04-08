/** @type {import('tailwindcss').Config} */
import { themeExtend } from '../../shared/tailwind-tokens.js'

export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  theme: { extend: themeExtend },
  plugins: [],
}
