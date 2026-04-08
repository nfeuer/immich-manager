import { useState, useRef, useCallback, useEffect } from 'react'

const ARM_TIMEOUT_MS = 3000

/**
 * Two-click confirmation for low-stakes actions.
 *
 * Usage:
 *   const { isArmed, trigger } = useInlineConfirm()
 *   <button onClick={() => trigger('backup', doBackup)}>
 *     {isArmed('backup') ? 'Click again to confirm' : 'Backup Now'}
 *   </button>
 */
export function useInlineConfirm() {
  const [armedKeys, setArmedKeys] = useState(() => new Set())
  const timersRef = useRef(new Map())

  const disarm = useCallback((key) => {
    setArmedKeys((prev) => {
      if (!prev.has(key)) return prev
      const next = new Set(prev)
      next.delete(key)
      return next
    })
    const timer = timersRef.current.get(key)
    if (timer != null) {
      clearTimeout(timer)
      timersRef.current.delete(key)
    }
  }, [])

  const arm = useCallback((key) => {
    setArmedKeys((prev) => {
      const next = new Set(prev)
      next.add(key)
      return next
    })
    const existing = timersRef.current.get(key)
    if (existing != null) clearTimeout(existing)
    const timer = setTimeout(() => disarm(key), ARM_TIMEOUT_MS)
    timersRef.current.set(key, timer)
  }, [disarm])

  const trigger = useCallback((key, handler) => {
    if (armedKeys.has(key)) {
      disarm(key)
      handler()
    } else {
      arm(key)
    }
  }, [armedKeys, arm, disarm])

  const isArmed = useCallback((key) => armedKeys.has(key), [armedKeys])

  useEffect(() => {
    const timers = timersRef.current
    return () => {
      for (const timer of timers.values()) clearTimeout(timer)
      timers.clear()
    }
  }, [])

  return { isArmed, trigger }
}
