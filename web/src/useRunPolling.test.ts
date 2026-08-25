import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from './api'
import { useRunPolling } from './useRunPolling'
import type { RunRecord } from './types'

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

function record(overrides: Partial<RunRecord>): RunRecord {
  return {
    run_id: 'r1',
    status: 'running',
    topic: 't',
    variant: 'pipeline',
    created_at: '2026-08-25T00:00:00Z',
    brief: null,
    trace: null,
    error: null,
    ...overrides,
  }
}

describe('useRunPolling', () => {
  it('polls immediately and stops once status is done', async () => {
    const getRunSpy = vi
      .spyOn(api, 'getRun')
      .mockResolvedValueOnce(record({ status: 'running' }))
      .mockResolvedValueOnce(record({ status: 'done' }))

    const { result } = renderHook(() => useRunPolling('r1'))

    await waitFor(() => expect(result.current.record?.status).toBe('running'))
    expect(getRunSpy).toHaveBeenCalledTimes(1)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })

    await waitFor(() => expect(result.current.record?.status).toBe('done'))
    expect(getRunSpy).toHaveBeenCalledTimes(2)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000)
    })
    expect(getRunSpy).toHaveBeenCalledTimes(2)
  })

  it('does nothing when runId is null', () => {
    const getRunSpy = vi.spyOn(api, 'getRun')
    const { result } = renderHook(() => useRunPolling(null))
    expect(result.current.record).toBeNull()
    expect(getRunSpy).not.toHaveBeenCalled()
  })

  it('sets an error and stops polling if a request fails', async () => {
    vi.spyOn(api, 'getRun').mockRejectedValue(new Error('network down'))
    const { result } = renderHook(() => useRunPolling('r1'))

    await waitFor(() =>
      expect(result.current.error).toBe('Lost contact with the backend while polling this run.'),
    )
  })
})
