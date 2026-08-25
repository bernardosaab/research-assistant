# Web Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the React/Vite frontend at `web/` — a form to pick a topic + variant, a poll-driven view of the resulting brief, and a table comparing `RunRecorder` traces across past runs — talking to the already-merged FastAPI backend via a Vite dev-server proxy.

**Architecture:** A small typed `api.ts` wraps the three backend endpoints; a `useRunPolling` hook drives `GET /api/runs/{id}` every 2s until a run finishes; `RunForm`/`BriefView`/`TraceCompare` are simple, independently-testable components; `App.tsx` wires them together. No state management library, no router — this is a single view.

**Tech Stack:** React 18, TypeScript, Vite 5, Vitest + React Testing Library (this is the first JS/TS code in this repo — Node v24 / npm v11 are already available on this machine).

**Spec:** `docs/superpowers/specs/2026-08-23-web-app-design.md` (this plan implements the frontend half; the backend half is `docs/superpowers/plans/2026-08-23-web-backend-plan.md`, already implemented and merged)

## Global Constraints

- All frontend HTTP calls use `/api/...`-relative paths only — never hardcode `http://127.0.0.1:8000` anywhere in `web/src/`. Vite's dev-server proxy (this plan's Task 2) handles routing `/api/*` to the backend, stripping the prefix.
- The backend's `CORSMiddleware` is now dead code under the proxy decision and gets removed (this plan's Task 1) — every browser request is same-origin (`:5173` only), so no cross-origin request ever happens.
- `variant` is always typed as a plain `string` on the frontend, never a fixed union of known variant names — the backend's `/variants` endpoint is deliberately dynamic (derives from `VARIANT_REGISTRY`, no hardcoded list), and the frontend must honor that: adding a new variant to the backend must require zero frontend code changes.
- No new backend routes or behavior changes beyond the Task 1 CORS removal — this plan is frontend-only otherwise.
- Every Python-side commit in this plan uses `uv run python -m pytest tests/unit -q` to verify, not bare `uv run pytest`. Every frontend commit uses `npm test` (run from inside `web/`) to verify, and the final task also runs `npm run build`.

---

## File Structure

- `src/research_assistant/web/app.py` — **modify.** Remove the now-dead `CORSMiddleware`.
- `web/package.json`, `web/tsconfig.json`, `web/tsconfig.node.json`, `web/vite.config.ts`, `web/index.html` — **create.** Project scaffold.
- `web/src/main.tsx`, `web/src/index.css`, `web/src/setupTests.ts` — **create.** Entry point, minimal styling, test setup.
- `web/src/types.ts` — **create.** TypeScript types mirroring the backend's Pydantic schemas.
- `web/src/api.ts` — **create.** Typed fetch wrapper for the three backend endpoints.
- `web/src/RunForm.tsx` — **create.** Topic input + variant picker.
- `web/src/useRunPolling.ts` — **create.** Polls a run until it finishes.
- `web/src/BriefView.tsx` — **create.** Renders the markdown brief + sources (or a running/error state).
- `web/src/TraceCompare.tsx` — **create.** Table comparing completed runs' traces.
- `web/src/App.tsx` — **create.** Wires everything together (replaces a placeholder from Task 2).

---

### Task 1: Remove the dead CORS middleware

**Files:**
- Modify: `src/research_assistant/web/app.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new — `app.py`'s existing routes (`/variants`, `/runs`, `/runs/{run_id}`) are unchanged, only the middleware is removed.

- [ ] **Step 1: Confirm no test depends on CORS behavior**

Run: `grep -ri cors tests/unit/test_web_app.py`
Expected: no output (no existing test asserts on CORS headers or `CORSMiddleware`). If this grep finds something, stop and report it — that test needs adjusting as part of this task, not silently left broken.

- [ ] **Step 2: Remove the middleware**

Replace the contents of `src/research_assistant/web/app.py`:

```python
from fastapi import BackgroundTasks, FastAPI, HTTPException

from research_assistant.variants import VARIANT_REGISTRY
from research_assistant.web.runs import execute_run, get_run, list_runs, start_run
from research_assistant.web.schemas import RunRecord, RunRequest

app = FastAPI(title="research-assistant")


@app.get("/variants")
def variants() -> list[str]:
    return [v.value for v in VARIANT_REGISTRY]


@app.post("/runs")
def create_run(request: RunRequest, background_tasks: BackgroundTasks) -> dict[str, str]:
    run_id = start_run(request.topic, request.variant)
    background_tasks.add_task(execute_run, run_id, request.topic, request.variant)
    return {"run_id": run_id}


@app.get("/runs/{run_id}")
def read_run(run_id: str) -> RunRecord:
    record = get_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return record


@app.get("/runs")
def read_runs() -> list[RunRecord]:
    return list_runs()
```

- [ ] **Step 3: Run the full unit suite**

Run: `uv run python -m pytest tests/unit -q`
Expected: PASS, 60 tests (unchanged — this removes dead code, no test coverage change)

- [ ] **Step 4: Run ruff**

Run: `uv run ruff check src tests`
Expected: no errors

- [ ] **Step 5: Commit**

```bash
git add src/research_assistant/web/app.py
git commit -m "refactor: remove dead CORSMiddleware

The Vite dev-server proxy decision (docs/superpowers/specs/2026-08-23-web-app-design.md)
means every browser request to the backend is same-origin; CORS never
triggers."
```

---

### Task 2: Project scaffold (Vite + React + TypeScript + Vitest)

**Files:**
- Create: `web/package.json`
- Create: `web/tsconfig.json`
- Create: `web/tsconfig.node.json`
- Create: `web/vite.config.ts`
- Create: `web/index.html`
- Create: `web/src/main.tsx`
- Create: `web/src/App.tsx` (placeholder — Task 8 replaces this)
- Create: `web/src/index.css`
- Create: `web/src/setupTests.ts`
- Test: `web/src/App.test.tsx` (placeholder — Task 8 replaces this)

**Interfaces:**
- Produces: a working `npm run dev` (Vite dev server on `:5173`, proxying `/api` to `:8000`), `npm test` (Vitest), `npm run build` (TypeScript + Vite production build) — all later tasks build on this toolchain.

- [ ] **Step 1: Write `package.json`**

Create `web/package.json`:

```json
{
  "name": "research-assistant-web",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "test": "vitest run"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-markdown": "^9.0.1"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.5.0",
    "@testing-library/react": "^16.0.1",
    "@testing-library/user-event": "^14.5.2",
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.3",
    "jsdom": "^25.0.1",
    "typescript": "^5.6.3",
    "vite": "^5.4.10",
    "vitest": "^2.1.4"
  }
}
```

- [ ] **Step 2: Write the TypeScript configs**

Create `web/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

Create `web/tsconfig.node.json`:

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 3: Write the Vite config with the dev-server proxy**

Create `web/vite.config.ts`:

```typescript
/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/setupTests.ts',
  },
})
```

- [ ] **Step 4: Write the HTML entry point and app shell**

Create `web/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>research-assistant</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

Create `web/src/main.tsx`:

```typescript
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

Create `web/src/App.tsx` (a placeholder — Task 8 replaces this with the real app):

```typescript
function App() {
  return <h1>research-assistant</h1>
}

export default App
```

Create `web/src/index.css`:

```css
:root {
  color-scheme: light dark;
  font-family: system-ui, -apple-system, sans-serif;
}

body {
  margin: 0;
  padding: 2rem;
  max-width: 860px;
  margin-inline: auto;
}

table {
  border-collapse: collapse;
  width: 100%;
}

th,
td {
  text-align: left;
  padding: 0.4rem 0.6rem;
  border-bottom: 1px solid #ccc;
}
```

Create `web/src/setupTests.ts`:

```typescript
import '@testing-library/jest-dom/vitest'
```

- [ ] **Step 5: Write the placeholder smoke test**

Create `web/src/App.test.tsx`:

```typescript
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from './App'

describe('App', () => {
  it('renders without crashing', () => {
    render(<App />)
    expect(screen.getByText('research-assistant')).toBeInTheDocument()
  })
})
```

- [ ] **Step 6: Install dependencies**

Run: `cd web && npm install`
Expected: installs cleanly, creates `web/node_modules/` and `web/package-lock.json`.

- [ ] **Step 7: Run the test to verify it passes**

Run: `cd web && npm test`
Expected: PASS (1 test)

- [ ] **Step 8: Run a production build to verify the toolchain is sound**

Run: `cd web && npm run build`
Expected: succeeds — TypeScript compiles with no errors, Vite produces a `web/dist/` bundle. This is the one point in the plan that validates the whole TS/Vite/React wiring before any real feature code is layered on top.

- [ ] **Step 9: Add a `.gitignore` for the frontend**

Create `web/.gitignore`:

```
node_modules/
dist/
```

- [ ] **Step 10: Commit**

```bash
git add web/package.json web/tsconfig.json web/tsconfig.node.json web/vite.config.ts web/index.html web/src/main.tsx web/src/App.tsx web/src/App.test.tsx web/src/index.css web/src/setupTests.ts web/.gitignore web/package-lock.json
git commit -m "feat: scaffold Vite + React + TypeScript + Vitest frontend

Working npm run dev / npm test / npm run build. Dev-server proxies /api
to the FastAPI backend on :8000. No feature code yet — App.tsx is a
placeholder, replaced in a later task."
```

---

### Task 3: Typed API client

**Files:**
- Create: `web/src/types.ts`
- Create: `web/src/api.ts`
- Test: `web/src/api.test.ts`

**Interfaces:**
- Consumes: nothing (this is the base layer everything else builds on).
- Produces: `Source`, `Brief`, `RunTrace`, `RunStatus`, `RunRecord` types; `getVariants(): Promise<string[]>`, `createRun(topic: string, variant: string): Promise<string>`, `getRun(runId: string): Promise<RunRecord>`, `getRuns(): Promise<RunRecord[]>` — consumed by every later task in this plan.

- [ ] **Step 1: Write the failing tests**

Create `web/src/api.test.ts`:

```typescript
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd web && npm test -- api.test.ts`
Expected: FAIL — `Cannot find module './api'` (or similar resolution error; `types.ts`/`api.ts` don't exist yet)

- [ ] **Step 3: Write the types**

Create `web/src/types.ts`:

```typescript
export interface Source {
  id: number
  url: string
  title: string
}

export interface Brief {
  topic: string
  markdown: string
  sources: Source[]
}

export interface RunTrace {
  variant: string
  topic: string
  duration_seconds: number
  llm_calls: number
  search_calls: number
  input_tokens: number
  output_tokens: number
}

export type RunStatus = 'running' | 'done' | 'error'

export interface RunRecord {
  run_id: string
  status: RunStatus
  topic: string
  variant: string
  created_at: string
  brief: Brief | null
  trace: RunTrace | null
  error: string | null
}
```

- [ ] **Step 4: Write the API client**

Create `web/src/api.ts`:

```typescript
import type { RunRecord } from './types'

const BASE = '/api'

export async function getVariants(): Promise<string[]> {
  const response = await fetch(`${BASE}/variants`)
  if (!response.ok) {
    throw new Error(`Failed to load variants: ${response.status}`)
  }
  return response.json()
}

export async function createRun(topic: string, variant: string): Promise<string> {
  const response = await fetch(`${BASE}/runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topic, variant }),
  })
  if (!response.ok) {
    throw new Error(`Failed to create run: ${response.status}`)
  }
  const data = await response.json()
  return data.run_id
}

export async function getRun(runId: string): Promise<RunRecord> {
  const response = await fetch(`${BASE}/runs/${runId}`)
  if (!response.ok) {
    throw new Error(`Failed to fetch run: ${response.status}`)
  }
  return response.json()
}

export async function getRuns(): Promise<RunRecord[]> {
  const response = await fetch(`${BASE}/runs`)
  if (!response.ok) {
    throw new Error(`Failed to fetch runs: ${response.status}`)
  }
  return response.json()
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd web && npm test -- api.test.ts`
Expected: PASS (5 tests)

- [ ] **Step 6: Run the full frontend suite**

Run: `cd web && npm test`
Expected: PASS (6 tests — 1 existing + 5 new)

- [ ] **Step 7: Commit**

```bash
git add web/src/types.ts web/src/api.ts web/src/api.test.ts
git commit -m "feat: add typed API client for the backend"
```

---

### Task 4: `RunForm` component

**Files:**
- Create: `web/src/RunForm.tsx`
- Test: `web/src/RunForm.test.tsx`

**Interfaces:**
- Consumes: `getVariants`, `createRun` (Task 3).
- Produces: `<RunForm onRunCreated={(runId: string) => void} />` — consumed by Task 8's `App.tsx`.

- [ ] **Step 1: Write the failing tests**

Create `web/src/RunForm.test.tsx`:

```typescript
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd web && npm test -- RunForm.test.tsx`
Expected: FAIL — `Cannot find module './RunForm'`

- [ ] **Step 3: Implement `RunForm`**

Create `web/src/RunForm.tsx`:

```typescript
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd web && npm test -- RunForm.test.tsx`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full frontend suite**

Run: `cd web && npm test`
Expected: PASS (10 tests — 6 existing + 4 new)

- [ ] **Step 6: Commit**

```bash
git add web/src/RunForm.tsx web/src/RunForm.test.tsx
git commit -m "feat: add RunForm component"
```

---

### Task 5: `useRunPolling` hook

**Files:**
- Create: `web/src/useRunPolling.ts`
- Test: `web/src/useRunPolling.test.ts`

**Interfaces:**
- Consumes: `getRun` (Task 3).
- Produces: `useRunPolling(runId: string | null) -> { record: RunRecord | null, error: string | null }` — consumed by Task 8's `App.tsx`.

- [ ] **Step 1: Write the failing tests**

Create `web/src/useRunPolling.test.ts`:

```typescript
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from './api'
import { useRunPolling } from './useRunPolling'
import type { RunRecord } from './types'

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

function record(overrides: Partial<RunRecord>): RunRecord {
  return {
    run_id: 'r1',
    status: 'running',
    topic: 't',
    variant: 'pipeline',
    created_at: '2026-08-25T00:00:00Z',
    brief: null,
    trace: null,
    error: null,
    ...overrides,
  }
}

describe('useRunPolling', () => {
  it('polls immediately and stops once status is done', async () => {
    const getRunSpy = vi
      .spyOn(api, 'getRun')
      .mockResolvedValueOnce(record({ status: 'running' }))
      .mockResolvedValueOnce(record({ status: 'done' }))

    const { result } = renderHook(() => useRunPolling('r1'))

    await waitFor(() => expect(result.current.record?.status).toBe('running'))
    expect(getRunSpy).toHaveBeenCalledTimes(1)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })

    await waitFor(() => expect(result.current.record?.status).toBe('done'))
    expect(getRunSpy).toHaveBeenCalledTimes(2)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000)
    })
    expect(getRunSpy).toHaveBeenCalledTimes(2)
  })

  it('does nothing when runId is null', () => {
    const getRunSpy = vi.spyOn(api, 'getRun')
    const { result } = renderHook(() => useRunPolling(null))
    expect(result.current.record).toBeNull()
    expect(getRunSpy).not.toHaveBeenCalled()
  })

  it('sets an error and stops polling if a request fails', async () => {
    vi.spyOn(api, 'getRun').mockRejectedValue(new Error('network down'))
    const { result } = renderHook(() => useRunPolling('r1'))

    await waitFor(() =>
      expect(result.current.error).toBe('Lost contact with the backend while polling this run.'),
    )
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd web && npm test -- useRunPolling.test.ts`
Expected: FAIL — `Cannot find module './useRunPolling'`

- [ ] **Step 3: Implement `useRunPolling`**

Create `web/src/useRunPolling.ts`:

```typescript
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd web && npm test -- useRunPolling.test.ts`
Expected: PASS (3 tests)

If the timer-advancing assertions are flaky on this machine, adjust `advanceTimersByTimeAsync` amounts or add a small `await Promise.resolve()` flush between steps — the point being verified (poll immediately, poll again after 2s, stop once not-running) should stay the same.

- [ ] **Step 5: Run the full frontend suite**

Run: `cd web && npm test`
Expected: PASS (13 tests — 10 existing + 3 new)

- [ ] **Step 6: Commit**

```bash
git add web/src/useRunPolling.ts web/src/useRunPolling.test.ts
git commit -m "feat: add useRunPolling hook"
```

---

### Task 6: `BriefView` component

**Files:**
- Create: `web/src/BriefView.tsx`
- Test: `web/src/BriefView.test.tsx`

**Interfaces:**
- Consumes: `RunRecord` type (Task 3); `react-markdown` (already in `package.json` from Task 2).
- Produces: `<BriefView record={RunRecord} />` — consumed by Task 8's `App.tsx`.

- [ ] **Step 1: Write the failing tests**

Create `web/src/BriefView.test.tsx`:

```typescript
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd web && npm test -- BriefView.test.tsx`
Expected: FAIL — `Cannot find module './BriefView'`

- [ ] **Step 3: Implement `BriefView`**

Create `web/src/BriefView.tsx`:

```typescript
import ReactMarkdown from 'react-markdown'
import type { RunRecord } from './types'

interface BriefViewProps {
  record: RunRecord
}

function BriefView({ record }: BriefViewProps) {
  if (record.status === 'running') {
    return <p>Researching “{record.topic}”…</p>
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd web && npm test -- BriefView.test.tsx`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full frontend suite**

Run: `cd web && npm test`
Expected: PASS (16 tests — 13 existing + 3 new)

- [ ] **Step 6: Commit**

```bash
git add web/src/BriefView.tsx web/src/BriefView.test.tsx
git commit -m "feat: add BriefView component"
```

---

### Task 7: `TraceCompare` component

**Files:**
- Create: `web/src/TraceCompare.tsx`
- Test: `web/src/TraceCompare.test.tsx`

**Interfaces:**
- Consumes: `getRuns` (Task 3).
- Produces: `<TraceCompare refreshKey={number} />` — consumed by Task 8's `App.tsx`. `refreshKey` is a plain number prop; incrementing it re-triggers the `GET /api/runs` fetch (React's standard "change a dependency to refetch" pattern), so the parent can force a refresh whenever a run completes.

- [ ] **Step 1: Write the failing tests**

Create `web/src/TraceCompare.test.tsx`:

```typescript
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd web && npm test -- TraceCompare.test.tsx`
Expected: FAIL — `Cannot find module './TraceCompare'`

- [ ] **Step 3: Implement `TraceCompare`**

Create `web/src/TraceCompare.tsx`:

```typescript
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd web && npm test -- TraceCompare.test.tsx`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full frontend suite**

Run: `cd web && npm test`
Expected: PASS (19 tests — 16 existing + 3 new)

- [ ] **Step 6: Commit**

```bash
git add web/src/TraceCompare.tsx web/src/TraceCompare.test.tsx
git commit -m "feat: add TraceCompare component"
```

---

### Task 8: Wire up `App`

**Files:**
- Modify: `web/src/App.tsx` (replaces Task 2's placeholder)
- Modify: `web/src/App.test.tsx` (replaces Task 2's placeholder test)

**Interfaces:**
- Consumes: `RunForm` (Task 4), `useRunPolling` (Task 5), `BriefView` (Task 6), `TraceCompare` (Task 7).
- Produces: the finished page — nothing later in this plan consumes `App` (it's the top-level component).

- [ ] **Step 1: Write the failing tests**

Replace the contents of `web/src/App.test.tsx`:

```typescript
import { render, screen, waitFor } from '@testing-library/react'
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
})
```

Note: this test uses `mockResolvedValue` (not `mockResolvedValueOnce`) for `getRun`, so every poll call returns the same "running" record — it verifies the wiring from form submission through to `BriefView` showing the running state, without needing to wait through a real 2-second poll interval to observe a status transition (that transition logic is already thoroughly covered by Task 5's `useRunPolling` tests with fake timers).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd web && npm test -- App.test.tsx`
Expected: FAIL — the placeholder `App` from Task 2 doesn't render a form, `getByLabelText('Topic')` etc. won't be found

- [ ] **Step 3: Implement the real `App`**

Replace the contents of `web/src/App.tsx`:

```typescript
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd web && npm test -- App.test.tsx`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the full frontend suite**

Run: `cd web && npm test`
Expected: PASS (20 tests — 19 existing, minus the 1 placeholder test this task's file replaces, plus 2 new = 19 - 1 + 2 = 20)

- [ ] **Step 6: Commit**

```bash
git add web/src/App.tsx web/src/App.test.tsx
git commit -m "feat: wire up App — form, polling, brief view, trace comparison"
```

---

### Task 9: Full regression check + real smoke test

**Files:** none (verification only)

- [ ] **Step 1: Frontend production build**

Run: `cd web && npm run build`
Expected: succeeds, no TypeScript errors

- [ ] **Step 2: Frontend test suite**

Run: `cd web && npm test`
Expected: PASS, 20 tests

- [ ] **Step 3: Backend regression (confirms Task 1's CORS removal didn't break anything)**

Run: `uv run python -m pytest tests/unit -q`
Expected: PASS, 60 tests

- [ ] **Step 4: Ruff**

Run: `uv run ruff check src tests`
Expected: no errors

- [ ] **Step 5: Real smoke check — start both servers, confirm the proxy actually works end to end**

Start the backend in the background: `uv run research-assistant serve`
Start the frontend dev server in the background: `cd web && npm run dev`

Wait for both to be ready (a couple seconds), then:

```bash
curl http://localhost:5173/api/variants
```

Expected: a JSON array (e.g. `["pipeline","agentic","graphrag"]`) — the exact same response the backend itself would give at `http://127.0.0.1:8000/variants`, proving the Vite proxy correctly rewrites `/api/variants` → `/variants` and forwards it to the real backend. This is the concrete verification that today's CORS-vs-proxy decision (Task 1 + Task 2's `vite.config.ts`) actually works, not just that each piece compiles in isolation.

Also fetch the frontend's own HTML to confirm Vite is serving the app shell:

```bash
curl http://localhost:5173/
```

Expected: HTML containing `<div id="root"></div>` and a `<script type="module" src="/src/main.tsx">` tag.

Stop both servers (kill the background processes) once confirmed — don't leave them running.

- [ ] **Step 6: Commit if anything changed**

If Steps 1-4 required no code changes, there's nothing to commit — this task is verification-only. If ruff's `--fix` (run manually if Step 4 reported anything) changed files, commit with `git add -u && git commit -m "style: ruff fixes"`.
