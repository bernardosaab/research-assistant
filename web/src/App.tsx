import { useEffect, useRef, useState } from 'react'
import BriefView from './BriefView'
import RunForm from './RunForm'
import TraceCompare from './TraceCompare'
import { useRunPolling } from './useRunPolling'

function App() {
  const [currentRunId, setCurrentRunId] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const { record, error } = useRunPolling(currentRunId)
  const notifiedRunId = useRef<string | null>(null)

  useEffect(() => {
    if (record && record.status !== 'running' && notifiedRunId.current !== record.run_id) {
      notifiedRunId.current = record.run_id
      setRefreshKey((key) => key + 1)
    }
  }, [record])

  return (
    <main>
      <h1>research-assistant</h1>
      <RunForm onRunCreated={setCurrentRunId} />
      {error && <p role="alert">{error}</p>}
      {record && <BriefView record={record} />}
      <h2>Past runs</h2>
      <TraceCompare refreshKey={refreshKey} />
    </main>
  )
}

export default App
