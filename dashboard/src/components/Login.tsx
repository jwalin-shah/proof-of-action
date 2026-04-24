import { useEffect, useState } from 'react';
import { insforge } from '../lib/insforge';

type Mode = 'sign-in' | 'sign-up';

export default function Login({ onAuth }: { onAuth: (userId: string) => void }) {
  const [mode, setMode] = useState<Mode>('sign-in');
  const [email, setEmail] = useState('demo@proof-of-action.local');
  const [password, setPassword] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function oauth(provider: 'google' | 'github') {
    setErr(null);
    try {
      await insforge.auth.signInWithOAuth({
        provider,
        redirectTo: window.location.origin,
      });
      // signInWithOAuth auto-redirects; execution continues on return.
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  // Detect return from OAuth callback — SDK auto-exchanges insforge_code.
  useEffect(() => {
    if (window.location.search.includes('insforge_code')) {
      insforge.auth.getCurrentUser().then(({ data }) => {
        const uid = data?.user?.id;
        if (uid) {
          onAuth(uid);
          const u = new URL(window.location.href);
          u.searchParams.delete('insforge_code');
          window.history.replaceState({}, '', u.toString());
        }
      });
    }
  }, [onAuth]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      const resp =
        mode === 'sign-in'
          ? await insforge.auth.signInWithPassword({ email, password })
          : await insforge.auth.signUp({ email, password });
      if (resp.error) throw new Error(resp.error.message ?? 'auth failed');
      const uid = resp.data?.user?.id;
      if (!uid) throw new Error('no user id');
      onAuth(uid);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-sm mx-auto mt-20">
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6">
        <div className="space-y-2 mb-5">
          <button
            onClick={() => oauth('google')}
            className="w-full bg-white text-black rounded px-3 py-2 text-sm font-medium flex items-center justify-center gap-2 hover:bg-zinc-200"
          >
            <svg viewBox="0 0 24 24" width="16" height="16">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.1c-.22-.66-.35-1.36-.35-2.1s.13-1.44.35-2.1V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.83z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84C6.71 7.31 9.14 5.38 12 5.38z"/>
            </svg>
            continue with Google
          </button>
          <button
            onClick={() => oauth('github')}
            className="w-full bg-zinc-800 text-white rounded px-3 py-2 text-sm font-medium flex items-center justify-center gap-2 hover:bg-zinc-700 border border-zinc-700"
          >
            <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
              <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/>
            </svg>
            continue with GitHub
          </button>
        </div>
        <div className="text-[10px] text-zinc-600 uppercase tracking-wider text-center mb-4">
          or email
        </div>
        <div className="flex gap-4 mb-6 text-sm">
          <button
            onClick={() => setMode('sign-in')}
            className={
              mode === 'sign-in'
                ? 'text-emerald-400 border-b border-emerald-400 pb-1'
                : 'text-zinc-500'
            }
          >
            sign in
          </button>
          <button
            onClick={() => setMode('sign-up')}
            className={
              mode === 'sign-up'
                ? 'text-emerald-400 border-b border-emerald-400 pb-1'
                : 'text-zinc-500'
            }
          >
            sign up
          </button>
        </div>
        <form onSubmit={submit} className="space-y-3">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="email"
            className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-sm"
            required
          />
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="password (6+ chars)"
            className="w-full bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-sm"
            required
            minLength={6}
          />
          {err && <div className="text-xs text-red-400">{err}</div>}
          <button
            disabled={busy}
            className="w-full bg-emerald-500 text-black rounded px-3 py-2 text-sm font-medium disabled:opacity-50"
          >
            {busy ? '…' : mode === 'sign-in' ? 'sign in' : 'create account'}
          </button>
        </form>
      </div>
      <div className="text-xs text-zinc-600 mt-4 text-center">
        only your own actions are ever visible — enforced by Postgres RLS.
      </div>
    </div>
  );
}
