import { afterEach, describe, expect, it, vi } from 'vitest'
import { createRun, getRun, getRuns, getVariants } from './api'

function mockFetchOnce(body: unknown, ok = true, status = 200) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok,
      status,
      json: () => Promise.resolve(body),
    }),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('getVariants', () => {
  it('fetches the variant list from /api/variants', async () => {
    mockFetchOnce(['pipeline', 'agentic'])
    const variants = await getVariants()
    expect(variants).toEqual(['pipeline', 'agentic'])
    expect(fetch).toHaveBeenCalledWith('/api/variants')
  })

  it('throws when the response is not ok', async () => {
    mockFetchOnce({}, false, 500)
    await expect(getVariants()).rejects.toThrow('Failed to load variants: 500')
  })
})

describe('createRun', () => {
  it('posts topic and variant, returns the run id', async () => {
    mockFetchOnce({ run_id: 'abc123' })
    const runId = await createRun('a topic', 'pipeline')
    expect(runId).toBe('abc123')
    expect(fetch).toHaveBeenCalledWith('/api/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ topic: 'a topic', variant: 'pipeline' }),
    })
  })
})

describe('getRun', () => {
  it('fetches a single run record by id', async () => {
    const record = { run_id: 'abc123', status: 'done' }
    mockFetchOnce(record)
    const result = await getRun('abc123')
    expect(result).toEqual(record)
    expect(fetch).toHaveBeenCalledWith('/api/runs/abc123')
  })
})

describe('getRuns', () => {
  it('fetches the full run list', async () => {
    mockFetchOnce([{ run_id: 'a' }, { run_id: 'b' }])
    const result = await getRuns()
    expect(result).toHaveLength(2)
    expect(fetch).toHaveBeenCalledWith('/api/runs')
  })
})
