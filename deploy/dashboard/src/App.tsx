import { useEffect, useState, useCallback } from 'react'
import { insforge } from './insforge'
import SignIn from './SignIn'
import Dashboard from './Dashboard'

type User = { id: string; email: string } | null

function App() {
  const [user, setUser] = useState<User>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    const { data } = await insforge.auth.getCurrentUser()
    setUser(data?.user ? { id: data.user.id, email: data.user.email } : null)
    setLoading(false)
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  if (loading) {
    return (
      <div className="p-6 text-term-dim">$ connecting to insforge…</div>
    )
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-term-border px-6 py-3 flex items-center justify-between">
        <div>
          <span className="text-term-accent">proof-of-action</span>
          <span className="text-term-dim"> // privacy-boundary dashboard</span>
        </div>
        {user && (
          <div className="flex items-center gap-4">
            <span className="text-term-dim">{user.email}</span>
            <button
              className="text-term-dim hover:text-term-fg"
              onClick={async () => {
                await insforge.auth.signOut()
                setUser(null)
              }}
            >
              [sign out]
            </button>
          </div>
        )}
      </header>
      <main className="p-6">
        {user ? (
          <Dashboard user={user} />
        ) : (
          <SignIn onSignedIn={refresh} />
        )}
      </main>
    </div>
  )
}

export default App
