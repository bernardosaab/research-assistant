import { useEffect, useRef, useState } from 'react'
import { getRun } from './api'
import type { RunRecord } from './types'

const POLL_INTERVAL_MS = 2000

export function useRunPolling(runId: string | null) {
  const [record, setRecord] = useState<RunRecord | null>(null)
  const [error, setError] = useState<string | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    setRecord(null)
    setError(null)
    if (!runId) return

    function poll() {
      getRun(runId!)
        .then((result) => {
          setRecord(result)
          if (result.status !== 'running' && intervalRef.current) {
            clearInterval(intervalRef.current)
            intervalRef.current = null
          }
        })
        .catch(() => {
          setError('Lost contact with the backend while polling this run.')
          if (intervalRef.current) {
            clearInterval(intervalRef.current)
            intervalRef.current = null
          }
        })
    }

    poll()
    intervalRef.current = setInterval(poll, POLL_INTERVAL_MS)

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
  }, [runId])

  return { record, error }
}
