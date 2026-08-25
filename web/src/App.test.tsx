import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as api from './api'
import App from './App'
import type { RunRecord } from './types'

afterEach(() => {
  vi.restoreAllMocks()
})

function runningRecord(): RunRecord {
  return {
    run_id: 'run-1',
    status: 'running',
    topic: 'a topic',
    variant: 'pipeline',
    created_at: '2026-08-25T00:00:00Z',
    brief: null,
    trace: null,
    error: null,
  }
}

function doneRecord(): RunRecord {
  return {
    run_id: 'run-1',
    status: 'done',
    topic: 'a topic',
    variant: 'pipeline',
    created_at: '2026-08-25T00:00:00Z',
    brief: { topic: 'a topic', markdown: '# The Brief', sources: [] },
    trace: {
      variant: 'pipeline',
      topic: 'a topic',
      duration_seconds: 3.2,
      llm_calls: 4,
      search_calls: 2,
      input_tokens: 100,
      output_tokens: 50,
    },
    error: null,
  }
}

describe('App', () => {
  it('submitting a topic starts polling and shows the running state', async () => {
    vi.spyOn(api, 'getVariants').mockResolvedValue(['pipeline'])
    vi.spyOn(api, 'createRun').mockResolvedValue('run-1')
    vi.spyOn(api, 'getRun').mockResolvedValue(runningRecord())
    vi.spyOn(api, 'getRuns').mockResolvedValue([])

    const user = userEvent.setup()
    render(<App />)

    await waitFor(() => expect(screen.getByRole('combobox')).toHaveValue('pipeline'))
    await user.type(screen.getByLabelText('Topic'), 'a topic')
    await user.click(screen.getByRole('button', { name: 'Run' }))

    await waitFor(() => expect(screen.getByText(/Researching/)).toBeInTheDocument())
  })

  it('renders the past-runs comparison section', async () => {
    vi.spyOn(api, 'getVariants').mockResolvedValue([])
    vi.spyOn(api, 'getRuns').mockResolvedValue([])
    render(<App />)
    await waitFor(() => expect(screen.getByText('Past runs')).toBeInTheDocument())
  })

  it('refetches past runs exactly once after a run reaches a terminal status', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      vi.spyOn(api, 'getVariants').mockResolvedValue(['pipeline'])
      vi.spyOn(api, 'createRun').mockResolvedValue('run-1')
      const getRunSpy = vi
        .spyOn(api, 'getRun')
        .mockResolvedValueOnce(runningRecord())
        .mockResolvedValueOnce(doneRecord())
      const getRunsSpy = vi
        .spyOn(api, 'getRuns')
        .mockResolvedValueOnce([])
        .mockResolvedValueOnce([doneRecord()])

      const user = userEvent.setup()
      render(<App />)

      await waitFor(() => expect(screen.getByRole('combobox')).toHaveValue('pipeline'))
      await user.type(screen.getByLabelText('Topic'), 'a topic')
      await user.click(screen.getByRole('button', { name: 'Run' }))

      await waitFor(() => expect(screen.getByText(/Researching/)).toBeInTheDocument())
      expect(getRunSpy).toHaveBeenCalledTimes(1)
      expect(getRunsSpy).toHaveBeenCalledTimes(1)

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000)
      })

      await waitFor(() => expect(screen.getByText('The Brief')).toBeInTheDocument())
      expect(screen.queryByText(/Researching/)).not.toBeInTheDocument()

      expect(getRunSpy).toHaveBeenCalledTimes(2)
      expect(getRunsSpy).toHaveBeenCalledTimes(2)
    } finally {
      vi.useRealTimers()
    }
  })
})
