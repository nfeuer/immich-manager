import { describe, it, expect } from 'vitest'
import { metricColor, metricBarColor } from '../utils/thresholds.js'

describe('metricColor', () => {
  it('returns green class below 70', () => {
    expect(metricColor(50)).toBe('text-immich-success')
  })
  it('returns yellow class between 70 and 85', () => {
    expect(metricColor(75)).toBe('text-immich-warning')
  })
  it('returns red class above 85', () => {
    expect(metricColor(90)).toBe('text-immich-error')
  })
  it('returns yellow at exactly 70', () => {
    expect(metricColor(70)).toBe('text-immich-warning')
  })
  it('returns red at exactly 85', () => {
    expect(metricColor(85)).toBe('text-immich-error')
  })
})

describe('metricBarColor', () => {
  it('returns green bar below 70', () => {
    expect(metricBarColor(50)).toBe('bg-immich-success')
  })
  it('returns yellow bar between 70 and 85', () => {
    expect(metricBarColor(75)).toBe('bg-immich-warning')
  })
  it('returns red bar above 85', () => {
    expect(metricBarColor(90)).toBe('bg-immich-error')
  })
})
