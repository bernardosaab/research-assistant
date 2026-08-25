import ReactMarkdown from 'react-markdown'
import type { RunRecord } from './types'

interface BriefViewProps {
  record: RunRecord
}

function BriefView({ record }: BriefViewProps) {
  if (record.status === 'running') {
    return <p>Researching "{record.topic}"…</p>
  }

  if (record.status === 'error') {
    return <p role="alert">Run failed: {record.error}</p>
  }

  if (!record.brief) {
    return null
  }

  return (
    <article>
      <ReactMarkdown>{record.brief.markdown}</ReactMarkdown>
    </article>
  )
}

export default BriefView
