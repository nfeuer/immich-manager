import '@testing-library/jest-dom'

// jsdom doesn't expose webkitdirectory on HTMLInputElement by default.
// Define it so SUPPORTS_WEBKITDIRECTORY evaluates to true in Import.jsx,
// exercising the happy-path branch in tests.
if (typeof HTMLInputElement !== 'undefined' && !('webkitdirectory' in HTMLInputElement.prototype)) {
  Object.defineProperty(HTMLInputElement.prototype, 'webkitdirectory', {
    configurable: true,
    get() { return this.getAttribute('webkitdirectory') !== null },
    set(v) { v ? this.setAttribute('webkitdirectory', '') : this.removeAttribute('webkitdirectory') },
  })
}
