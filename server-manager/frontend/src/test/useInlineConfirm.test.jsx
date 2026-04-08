import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useInlineConfirm } from '../hooks/useInlineConfirm.js'

describe('useInlineConfirm', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('arms a key on first trigger and does not call the handler', () => {
    const { result } = renderHook(() => useInlineConfirm())
    const handler = vi.fn()

    act(() => {
      result.current.trigger('alpha', handler)
    })

    expect(handler).not.toHaveBeenCalled()
    expect(result.current.isArmed('alpha')).toBe(true)
  })

  it('calls the handler and disarms on second trigger while armed', () => {
    const { result } = renderHook(() => useInlineConfirm())
    const handler = vi.fn()

    act(() => {
      result.current.trigger('alpha', handler)
    })
    act(() => {
      result.current.trigger('alpha', handler)
    })

    expect(handler).toHaveBeenCalledTimes(1)
    expect(result.current.isArmed('alpha')).toBe(false)
  })

  it('auto-disarms after 3 seconds', () => {
    const { result } = renderHook(() => useInlineConfirm())
    const handler = vi.fn()

    act(() => {
      result.current.trigger('alpha', handler)
    })
    expect(result.current.isArmed('alpha')).toBe(true)

    act(() => {
      vi.advanceTimersByTime(3000)
    })

    expect(result.current.isArmed('alpha')).toBe(false)
  })

  it('supports multiple independent keys', () => {
    const { result } = renderHook(() => useInlineConfirm())
    const handlerA = vi.fn()
    const handlerB = vi.fn()

    act(() => {
      result.current.trigger('alpha', handlerA)
    })
    act(() => {
      result.current.trigger('beta', handlerB)
    })

    expect(result.current.isArmed('alpha')).toBe(true)
    expect(result.current.isArmed('beta')).toBe(true)

    act(() => {
      result.current.trigger('alpha', handlerA)
    })

    expect(handlerA).toHaveBeenCalledTimes(1)
    expect(handlerB).not.toHaveBeenCalled()
    expect(result.current.isArmed('alpha')).toBe(false)
    expect(result.current.isArmed('beta')).toBe(true)
  })
})
