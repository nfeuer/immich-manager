const VARIANT_CLASSES = {
  primary: 'bg-immich-primary hover:bg-immich-primary-hover text-white focus-visible:ring-immich-primary',
  secondary: 'bg-immich-surface border border-immich-border text-immich-text hover:bg-immich-border/50 focus-visible:ring-immich-primary',
  danger: 'bg-immich-error hover:bg-immich-error/90 text-white focus-visible:ring-immich-error',
  warning: 'bg-immich-warning hover:bg-immich-warning/90 text-immich-bg focus-visible:ring-immich-warning',
  ghost: 'text-immich-muted hover:text-immich-text hover:bg-immich-border/50 focus-visible:ring-immich-primary',
}

const SIZE_CLASSES = {
  sm: 'min-h-[36px] px-3 py-1.5 text-xs',
  md: 'min-h-[44px] px-4 py-2 text-sm',
}

export default function Button({
  variant = 'primary',
  size = 'md',
  type = 'button',
  disabled = false,
  className = '',
  children,
  ...rest
}) {
  const variantClass = VARIANT_CLASSES[variant] ?? VARIANT_CLASSES.primary
  const sizeClass = SIZE_CLASSES[size] ?? SIZE_CLASSES.md
  return (
    <button
      type={type}
      disabled={disabled}
      className={`${sizeClass} ${variantClass} font-medium rounded-lg transition-colors duration-150 disabled:opacity-40 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 ${className}`}
      {...rest}
    >
      {children}
    </button>
  )
}
