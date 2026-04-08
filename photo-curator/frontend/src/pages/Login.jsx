import ImmichLogoIcon from '../components/ImmichLogoIcon'

export default function Login({ loginUrl }) {
  return (
    <div className="min-h-screen bg-immich-bg flex items-center justify-center">
      <div className="bg-immich-surface border border-immich-border rounded-xl p-8 max-w-sm w-full text-center">
        <div className="flex justify-center mb-4">
          <ImmichLogoIcon className="w-16 h-16" />
        </div>
        <h1 className="text-immich-text text-xl font-semibold mb-2">Photo Curator</h1>
        <p className="text-immich-muted text-sm mb-6">Sign in with your Immich account to continue.</p>
        {loginUrl ? (
          <a
            href={loginUrl}
            className="inline-block w-full px-4 py-2 bg-immich-primary text-white font-medium rounded-lg hover:opacity-90 transition-opacity focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary"
          >
            Sign in via Immich
          </a>
        ) : (
          <p className="text-immich-muted text-sm">
            Unable to reach the server. Is Photo Curator running?
          </p>
        )}
      </div>
    </div>
  )
}
