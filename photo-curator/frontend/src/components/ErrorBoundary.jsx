import React from 'react'

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-immich-bg flex items-center justify-center p-8">
          <div className="bg-immich-surface border border-immich-error-border rounded-2xl p-6 max-w-lg w-full">
            <h2 className="text-immich-error font-semibold mb-2">Something went wrong</h2>
            <pre className="text-immich-muted text-xs font-mono whitespace-pre-wrap">
              {this.state.error?.message}
            </pre>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
