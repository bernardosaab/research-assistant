import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as api from './api'
import RunForm from './RunForm'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('RunForm', () => {
  it('loads variants on mount and preselects the first one', async () => {
    vi.spyOn(api, 'getVariants').mockResolvedValue(['pipeline', 'agentic'])
    render(<RunForm onRunCreated={() => {}} />)

    await waitFor(() => {
      expect(screen.getByRole('option', { name: 'pipeline' })).toBeInTheDocument()
    })
    expect(screen.getByRole('combobox')).toHaveValue('pipeline')
  })

  it('submits the topic and selected variant, calls onRunCreated with the new run id', async () => {
    vi.spyOn(api, 'getVariants').mockResolvedValue(['pipeline', 'agentic'])
    const createRunSpy = vi.spyOn(api, 'createRun').mockResolvedValue('run-123')
    const onRunCreated = vi.fn()
    const user = userEvent.setup()

    render(<RunForm onRunCreated={onRunCreated} />)
    await waitFor(() => expect(screen.getByRole('combobox')).toHaveValue('pipeline'))

    await user.type(screen.getByLabelText('Topic'), 'a topic')
    await user.selectOptions(screen.getByRole('combobox'), 'agentic')
    await user.click(screen.getByRole('button', { name: 'Run' }))

    await waitFor(() => expect(onRunCreated).toHaveBeenCalledWith('run-123'))
    expect(createRunSpy).toHaveBeenCalledWith('a topic', 'agentic')
  })

  it('disables the submit button while a topic has not been entered', async () => {
    vi.spyOn(api, 'getVariants').mockResolvedValue(['pipeline'])
    render(<RunForm onRunCreated={() => {}} />)
    await waitFor(() => expect(screen.getByRole('combobox')).toHaveValue('pipeline'))
    expect(screen.getByRole('button', { name: 'Run' })).toBeDisabled()
  })

  it('shows an error message if starting the run fails', async () => {
    vi.spyOn(api, 'getVariants').mockResolvedValue(['pipeline'])
    vi.spyOn(api, 'createRun').mockRejectedValue(new Error('boom'))
    const user = userEvent.setup()

    render(<RunForm onRunCreated={() => {}} />)
    await waitFor(() => expect(screen.getByRole('combobox')).toHaveValue('pipeline'))
    await user.type(screen.getByLabelText('Topic'), 'a topic')
    await user.click(screen.getByRole('button', { name: 'Run' }))

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('Could not start the run'),
    )
  })
})
