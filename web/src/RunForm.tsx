import { type FormEvent, useEffect, useState } from 'react'
import { createRun, getVariants } from './api'

interface RunFormProps {
  onRunCreated: (runId: string) => void
}

function RunForm({ onRunCreated }: RunFormProps) {
  const [variants, setVariants] = useState<string[]>([])
  const [topic, setTopic] = useState('')
  const [variant, setVariant] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getVariants()
      .then((list) => {
        setVariants(list)
        setVariant((current) => current || list[0] || '')
      })
      .catch(() => setError('Could not load available variants.'))
  }, [])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!topic.trim() || !variant) return
    setSubmitting(true)
    setError(null)
    try {
      const runId = await createRun(topic.trim(), variant)
      onRunCreated(runId)
    } catch {
      setError('Could not start the run. Is the backend running?')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <label>
        Topic
        <input
          value={topic}
          onChange={(event) => setTopic(event.target.value)}
          placeholder="What caused the fall of the Roman Empire?"
        />
      </label>
      <label>
        Variant
        <select value={variant} onChange={(event) => setVariant(event.target.value)}>
          {variants.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </label>
      <button type="submit" disabled={submitting || !topic.trim() || !variant}>
        {submitting ? 'Starting…' : 'Run'}
      </button>
      {error && <p role="alert">{error}</p>}
    </form>
  )
}

export default RunForm
