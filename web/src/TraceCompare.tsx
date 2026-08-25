import { useEffect, useState } from 'react'
import { getRuns } from './api'
import type { RunRecord } from './types'

interface TraceCompareProps {
  refreshKey: number
}

function TraceCompare({ refreshKey }: TraceCompareProps) {
  const [runs, setRuns] = useState<RunRecord[]>([])

  useEffect(() => {
    getRuns()
      .then((all) => setRuns(all.filter((r) => r.status === 'done' && r.trace)))
      .catch(() => setRuns([]))
  }, [refreshKey])

  if (runs.length === 0) {
    return <p>No completed runs yet — finish a run to compare traces.</p>
  }

  const maxDuration = Math.max(...runs.map((r) => r.trace!.duration_seconds))

  return (
    <table>
      <thead>
        <tr>
          <th>Topic</th>
          <th>Variant</th>
          <th>LLM calls</th>
          <th>Search calls</th>
          <th>Tokens</th>
          <th>Duration</th>
        </tr>
      </thead>
      <tbody>
        {runs.map((run) => (
          <tr key={run.run_id}>
            <td>{run.topic}</td>
            <td>{run.variant}</td>
            <td>{run.trace!.llm_calls}</td>
            <td>{run.trace!.search_calls}</td>
            <td>{run.trace!.input_tokens + run.trace!.output_tokens}</td>
            <td>
              <div
                style={{
                  background: '#4a90d9',
                  color: 'white',
                  padding: '0 0.4rem',
                  width: `${(run.trace!.duration_seconds / maxDuration) * 100}%`,
                  minWidth: '2.5rem',
                }}
              >
                {run.trace!.duration_seconds.toFixed(1)}s
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default TraceCompare
