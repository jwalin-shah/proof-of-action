import { useEffect, useState } from 'react';
import { insforge } from './lib/insforge';
import Login from './components/Login';
import Dashboard from './components/Dashboard';

export default function App() {
  const [userId, setUserId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    insforge.auth.getCurrentUser().then(({ data }) => {
      setUserId(data?.user?.id ?? null);
      setLoading(false);
    });
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-zinc-500 text-sm">loading…</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-zinc-800 px-6 py-4 flex items-center justify-between">
        <div>
          <div className="text-sm font-mono text-emerald-400">proof-of-action</div>
          <div className="text-xs text-zinc-500">
            private reasoning · public proof
          </div>
        </div>
        {userId && (
          <button
            onClick={async () => {
              await insforge.auth.signOut();
              setUserId(null);
            }}
            className="text-xs text-zinc-400 hover:text-zinc-200"
          >
            sign out
          </button>
        )}
      </header>
      <main className="max-w-5xl mx-auto px-6 py-10">
        {userId ? (
          <Dashboard userId={userId} />
        ) : (
          <Login onAuth={(id) => setUserId(id)} />
        )}
      </main>
    </div>
  );
}
