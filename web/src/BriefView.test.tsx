import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import BriefView from './BriefView'
import type { RunRecord } from './types'

function baseRecord(overrides: Partial<RunRecord>): RunRecord {
  return {
    run_id: 'r1',
    status: 'running',
    topic: 'a topic',
    variant: 'pipeline',
    created_at: '2026-08-25T00:00:00Z',
    brief: null,
    trace: null,
    error: null,
    ...overrides,
  }
}

describe('BriefView', () => {
  it('shows a researching message while running', () => {
    render(<BriefView record={baseRecord({ status: 'running' })} />)
    expect(screen.getByText(/Researching/)).toBeInTheDocument()
  })

  it('shows the error message when the run failed', () => {
    render(<BriefView record={baseRecord({ status: 'error', error: 'boom' })} />)
    expect(screen.getByRole('alert')).toHaveTextContent('boom')
  })

  it('renders the brief markdown as formatted content when done', () => {
    render(
      <BriefView
        record={baseRecord({
          status: 'done',
          brief: {
            topic: 'a topic',
            markdown: '# Heading\n\nSome text [1].\n\n## Sources\n1. [A](https://a.com)',
            sources: [{ id: 1, url: 'https://a.com', title: 'A' }],
          },
        })}
      />,
    )
    expect(screen.getByRole('heading', { name: 'Heading' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'A' })).toHaveAttribute('href', 'https://a.com')
  })
})
