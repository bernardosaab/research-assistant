import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as api from './api'
import TraceCompare from './TraceCompare'
import type { RunRecord } from './types'

afterEach(() => {
  vi.restoreAllMocks()
})

function doneRun(overrides: Partial<RunRecord>): RunRecord {
  return {
    run_id: 'r1',
    status: 'done',
    topic: 't',
    variant: 'pipeline',
    created_at: '2026-08-25T00:00:00Z',
    brief: { topic: 't', markdown: '# t', sources: [] },
    trace: {
      variant: 'pipeline',
      topic: 't',
      duration_seconds: 3.2,
      llm_calls: 4,
      search_calls: 2,
      input_tokens: 100,
      output_tokens: 50,
    },
    error: null,
    ...overrides,
  }
}

describe('TraceCompare', () => {
  it('shows a placeholder when there are no completed runs', async () => {
    vi.spyOn(api, 'getRuns').mockResolvedValue([])
    render(<TraceCompare refreshKey={0} />)
    await waitFor(() => expect(screen.getByText(/No completed runs/)).toBeInTheDocument())
  })

  it('renders a row per completed run with its trace numbers', async () => {
    vi.spyOn(api, 'getRuns').mockResolvedValue([
      doneRun({ run_id: 'r1', variant: 'pipeline' }),
      doneRun({ run_id: 'r2', variant: 'agentic' }),
    ])
    render(<TraceCompare refreshKey={0} />)

    await waitFor(() => expect(screen.getAllByRole('row')).toHaveLength(3)) // header + 2 rows
    expect(screen.getByText('pipeline')).toBeInTheDocument()
    expect(screen.getByText('agentic')).toBeInTheDocument()
  })

  it('excludes runs that are not done', async () => {
    vi.spyOn(api, 'getRuns').mockResolvedValue([
      doneRun({ run_id: 'r1' }),
      { ...doneRun({ run_id: 'r2' }), status: 'running', trace: null },
    ])
    render(<TraceCompare refreshKey={0} />)

    await waitFor(() => expect(screen.getAllByRole('row')).toHaveLength(2)) // header + 1 row
  })
})
