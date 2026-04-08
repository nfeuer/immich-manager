export default function Skeleton({ className = '', width, height }) {
  const style = {}
  if (width) style.width = width
  if (height) style.height = height
  return (
    <div
      aria-hidden="true"
      className={`animate-pulse bg-immich-border/40 rounded-lg ${className}`}
      style={style}
    />
  )
}
