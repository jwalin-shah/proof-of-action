import { useState } from 'react'
import { insforge } from './insforge'

const DEMO_EMAIL = 'demo@proof-of-action.local'
const DEMO_PASSWORD = 'demoPass!ProofOfAction2026'

export default function SignIn({ onSignedIn }: { onSignedIn: () => void }) {
  const [email, setEmail] = useState(DEMO_EMAIL)
  const [password, setPassword] = useState(DEMO_PASSWORD)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setErr(null)
    const { error } = await insforge.auth.signInWithPassword({ email, password })
    setBusy(false)
    if (error) {
      setErr(error.message)
      return
    }
    onSignedIn()
  }

  return (
    <div className="max-w-md">
      <div className="text-term-dim mb-2">$ auth / sign-in</div>
      <p className="text-term-dim mb-4">
        Demo credentials pre-filled. The agent runs locally with these.
      </p>
      <form onSubmit={submit} className="space-y-3">
        <div>
          <label className="block text-term-dim text-xs mb-1">email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full bg-term-panel border border-term-border px-3 py-2 focus:outline-none focus:border-term-accent"
          />
        </div>
        <div>
          <label className="block text-term-dim text-xs mb-1">password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full bg-term-panel border border-term-border px-3 py-2 focus:outline-none focus:border-term-accent"
          />
        </div>
        {err && <div className="text-term-err">error: {err}</div>}
        <button
          type="submit"
          disabled={busy}
          className="border border-term-accent text-term-accent px-4 py-2 hover:bg-term-accent hover:text-term-bg disabled:opacity-50"
        >
          {busy ? '→ authenticating…' : '→ sign in'}
        </button>
      </form>
    </div>
  )
}
