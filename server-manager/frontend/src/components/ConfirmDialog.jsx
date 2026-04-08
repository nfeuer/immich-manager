import { useEffect, useRef } from 'react'

const VARIANT_CLASSES = {
  danger: 'bg-immich-error hover:bg-immich-error/90 focus-visible:ring-immich-error',
  warning: 'bg-immich-warning hover:bg-immich-warning/90 text-immich-bg focus-visible:ring-immich-warning',
  primary: 'bg-immich-primary hover:bg-immich-primary-hover focus-visible:ring-immich-primary',
}

export default function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  confirmVariant = 'primary',
  onConfirm,
  onCancel,
}) {
  const dialogRef = useRef(null)

  useEffect(() => {
    const dlg = dialogRef.current
    if (!dlg) return
    if (open && !dlg.open) {
      dlg.showModal()
    } else if (!open && dlg.open) {
      dlg.close()
    }
  }, [open])

  // When the native dialog closes via Escape or backdrop, propagate cancel
  useEffect(() => {
    const dlg = dialogRef.current
    if (!dlg) return
    const handleClose = () => {
      if (onCancel) onCancel()
    }
    dlg.addEventListener('close', handleClose)
    return () => dlg.removeEventListener('close', handleClose)
  }, [onCancel])

  const confirmClass =
    (confirmVariant === 'warning' ? '' : 'text-white ') +
    (VARIANT_CLASSES[confirmVariant] ?? VARIANT_CLASSES.primary)

  return (
    <dialog
      ref={dialogRef}
      className="bg-immich-surface border border-immich-border rounded-2xl p-6 max-w-md w-[calc(100%-2rem)] backdrop:bg-immich-bg/80 text-immich-text"
      aria-labelledby="confirm-dialog-title"
      aria-describedby="confirm-dialog-description"
    >
      <h2 id="confirm-dialog-title" className="text-lg font-semibold mb-2">{title}</h2>
      <p id="confirm-dialog-description" className="text-sm text-immich-muted mb-6">{description}</p>
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 text-sm font-medium text-immich-text border border-immich-border rounded-lg hover:bg-immich-border/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-immich-primary transition-colors min-h-[44px]"
        >
          {cancelLabel}
        </button>
        <button
          type="button"
          onClick={onConfirm}
          className={`px-4 py-2 text-sm font-medium rounded-lg focus:outline-none focus-visible:ring-2 transition-colors min-h-[44px] ${confirmClass}`}
        >
          {confirmLabel}
        </button>
      </div>
    </dialog>
  )
}
