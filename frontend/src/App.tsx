import { useState } from 'react'
import type { FormEvent } from 'react'
import { unitContextFixture } from './api/fixtures'
import './App.css'

function App() {
  const [issue, setIssue] = useState('')
  const [submittedIssue, setSubmittedIssue] = useState<string | null>(null)
  const { property, resident, unit, previous_cases: previousCases } =
    unitContextFixture

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const normalizedIssue = issue.trim()
    if (normalizedIssue) {
      setSubmittedIssue(normalizedIssue)
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="centrix maintenance home">
          centrix
        </a>
        <span className="prototype-badge">Hackathon prototype</span>
      </header>

      <main id="top">
        <section className="hero-copy">
          <p className="eyebrow">Maintenance assistant</p>
          <h1>Tell us what is happening. We already know the property.</h1>
          <p className="lead">
            Report an issue without repeating your address or unit details. We
            will confirm what is shared before contacting a repair partner.
          </p>
        </section>

        <div className="content-grid">
          <section className="card context-card" aria-labelledby="context-title">
            <div className="card-heading">
              <div>
                <p className="eyebrow">Known context</p>
                <h2 id="context-title">Your home</h2>
              </div>
              <span className="verified">Verified</span>
            </div>

            <dl className="context-list">
              <div>
                <dt>Resident</dt>
                <dd>{resident.name}</dd>
              </div>
              <div>
                <dt>Address</dt>
                <dd>{property.address}</dd>
              </div>
              <div>
                <dt>Unit</dt>
                <dd>{unit.label}, floor {unit.floor}</dd>
              </div>
              <div>
                <dt>Heating</dt>
                <dd>{property.heating_type}</dd>
              </div>
            </dl>

            <div className="history-note">
              <strong>Relevant history</strong>
              <span>{previousCases[0]?.summary}</span>
            </div>
          </section>

          <section className="card report-card" aria-labelledby="report-title">
            <p className="eyebrow">Step 1 of 3</p>
            <h2 id="report-title">What needs attention?</h2>
            <p className="supporting-copy">
              Describe the problem in your own words. We will ask only for
              information the repair partner still needs.
            </p>

            <form onSubmit={handleSubmit}>
              <label htmlFor="issue">Issue description</label>
              <textarea
                id="issue"
                name="issue"
                value={issue}
                onChange={(event) => setIssue(event.target.value)}
                placeholder="For example: My heating has stopped working since last night."
                rows={5}
              />
              <button type="submit" disabled={!issue.trim()}>
                Continue
              </button>
            </form>

            {submittedIssue && (
              <div className="next-question" role="status">
                <span className="status-dot" aria-hidden="true" />
                <div>
                  <strong>Report captured</strong>
                  <p>Is your hot water also unavailable?</p>
                </div>
              </div>
            )}
          </section>
        </div>
      </main>

      <footer>
        Synthetic demonstration data. No real contractor is contacted.
      </footer>
    </div>
  )
}

export default App
