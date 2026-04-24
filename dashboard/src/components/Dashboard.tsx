import { useEffect, useState } from 'react';
import { insforge } from '../lib/insforge';

type Action = {
  id: string;
  action_id: string;
  action_kind: string;
  day: string;
  status: string;
  cited_md: string | null;
  created_at: string;
};

type Crossing = {
  id: string;
  action_id: string | null;
  projection_type: string;
  private_field_count: number;
  public_field_count: number;
  leak_check_passed: boolean;
  created_at: string;
};

type Guild = {
  id: string;
  action_id: string | null;
  guild_session_id: string;
  guild_url: string;
};

const POLL_MS = 3000;

export default function Dashboard({ userId }: { userId: string }) {
  const [actions, setActions] = useState<Action[]>([]);
  const [crossings, setCrossings] = useState<Crossing[]>([]);
  const [guilds, setGuilds] = useState<Guild[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      const [a, c, g] = await Promise.all([
        insforge.database
          .from('proof_actions')
          .select('*')
          .order('created_at', { ascending: false })
          .limit(20),
        insforge.database
          .from('boundary_crossings')
          .select('*')
          .order('created_at', { ascending: false })
          .limit(50),
        insforge.database.from('guild_sessions').select('*').limit(50),
      ]);
      if (a.error) throw a.error;
      if (c.error) throw c.error;
      if (g.error) throw g.error;
      setActions((a.data ?? []) as Action[]);
      setCrossings((c.data ?? []) as Crossing[]);
      setGuilds((g.data ?? []) as Guild[]);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    refresh();
    // Slow poll as a safety net for actions / guild rows (no realtime wired yet).
    const t = setInterval(refresh, POLL_MS);

    // Live push: boundary_crossings stream in via the per-user realtime channel
    // registered by migrations/20260424210000_realtime-boundary.sql. Pattern is
    // boundary:user:<uid> so the backend can never leak someone else's rows.
    const channel = `boundary:user:${userId}`;
    const onCrossing = (msg: { payload?: Crossing; data?: Crossing }) => {
      const row = msg.payload ?? msg.data;
      if (!row) return;
      setCrossings((prev) => {
        if (prev.some((c) => c.id === row.id)) return prev;
        return [row, ...prev].slice(0, 50);
      });
    };

    let cancelled = false;
    (async () => {
      try {
        await insforge.realtime.connect();
        if (cancelled) return;
        const res = await insforge.realtime.subscribe(channel);
        if (cancelled) return;
        if (!res.ok) {
          setError(`realtime subscribe failed: ${res.error ?? 'unknown'}`);
          return;
        }
        insforge.realtime.on('crossing_logged', onCrossing);
      } catch (e) {
        setError(`realtime: ${(e as Error).message}`);
      }
    })();

    return () => {
      cancelled = true;
      clearInterval(t);
      try {
        insforge.realtime.off('crossing_logged', onCrossing);
        insforge.realtime.unsubscribe(channel);
      } catch {
        /* best-effort cleanup */
      }
    };
  }, [userId]);

  const [demoBusy, setDemoBusy] = useState(false);
  const [demoMsg, setDemoMsg] = useState<string | null>(null);

  async function runDemo() {
    setDemoBusy(true);
    setDemoMsg(null);
    try {
      const { data, error } = await insforge.functions.invoke('run-demo');
      if (error) throw error;
      setDemoMsg(
        `✓ synthetic run landed as ${(data as { action_id: string }).action_id}`,
      );
      refresh();
    } catch (e) {
      setDemoMsg(`✗ ${(e as Error).message}`);
    } finally {
      setDemoBusy(false);
    }
  }

  const totalPrivateFields = crossings.reduce(
    (acc, c) => acc + c.private_field_count,
    0,
  );
  const totalPublicFields = crossings.reduce(
    (acc, c) => acc + c.public_field_count,
    0,
  );
  const leakFails = crossings.filter((c) => !c.leak_check_passed).length;

  const guildByAction = new Map(guilds.map((g) => [g.action_id ?? '', g]));

  return (
    <div className="space-y-10">
      <section className="bg-zinc-900 border border-emerald-500/30 rounded-lg p-5 flex items-center justify-between gap-4">
        <div className="flex-1">
          <div className="text-sm text-emerald-300 font-medium">
            Judges / first-time visitors — click here
          </div>
          <div className="text-xs text-zinc-500 mt-1">
            Triggers a synthetic agent run on the public plane. The row that
            appears below will be owned by <span className="font-mono">{userId.slice(0, 8)}…</span> —
            you. That's RLS working. Real operator runs happen on their Mac;
            this button demonstrates the public-plane audit without needing local setup.
          </div>
          {demoMsg && (
            <div className="text-xs font-mono mt-2 text-zinc-400">{demoMsg}</div>
          )}
        </div>
        <button
          onClick={runDemo}
          disabled={demoBusy}
          className="bg-emerald-500 text-black rounded px-4 py-2 text-sm font-medium hover:bg-emerald-400 disabled:opacity-50 whitespace-nowrap"
        >
          {demoBusy ? 'running…' : 'run demo'}
        </button>
      </section>

      <section className="grid grid-cols-4 gap-4">
        <Stat label="actions" value={actions.length} accent="emerald" />
        <Stat label="boundary crossings" value={crossings.length} accent="sky" />
        <Stat
          label="private → public fields"
          value={`${totalPrivateFields} → ${totalPublicFields}`}
          accent="violet"
        />
        <Stat
          label="leak check failures"
          value={leakFails}
          accent={leakFails === 0 ? 'emerald' : 'red'}
        />
      </section>

      {error && (
        <div className="text-xs text-red-400 font-mono">{error}</div>
      )}

      <section>
        <SectionHeader title="actions" subtitle="every row is RLS-owned by you" />
        {actions.length === 0 ? (
          <Empty>No actions yet. Run the agent — they'll appear here live.</Empty>
        ) : (
          <div className="space-y-3">
            {actions.map((a) => {
              const guild = guildByAction.get(a.id);
              return (
                <div
                  key={a.id}
                  className="bg-zinc-900 border border-zinc-800 rounded-lg p-4"
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="font-mono text-emerald-400 text-sm">
                      {a.action_id}
                    </div>
                    <Badge status={a.status} />
                  </div>
                  <div className="text-xs text-zinc-400 flex gap-4">
                    <span>{a.action_kind}</span>
                    <span>{a.day}</span>
                    <span className="text-zinc-600">
                      {new Date(a.created_at).toLocaleTimeString()}
                    </span>
                  </div>
                  {guild && (
                    <a
                      href={guild.guild_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-block mt-3 text-xs text-sky-400 hover:text-sky-300 underline"
                    >
                      guild audit session ↗
                    </a>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      <section>
        <SectionHeader
          title="live boundary crossings"
          subtitle="every private→public projection is logged here"
        />
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg divide-y divide-zinc-800">
          {crossings.length === 0 ? (
            <Empty>Crossings stream in as the agent runs.</Empty>
          ) : (
            crossings.slice(0, 10).map((c) => (
              <div
                key={c.id}
                className="px-4 py-2 flex items-center gap-4 font-mono text-xs"
              >
                <span className="text-zinc-600 w-24">
                  {new Date(c.created_at).toLocaleTimeString()}
                </span>
                <span className="text-violet-400 w-40">{c.projection_type}</span>
                <span className="text-zinc-400">
                  {c.private_field_count} priv
                </span>
                <span className="text-zinc-600">→</span>
                <span className="text-zinc-400">
                  {c.public_field_count} pub
                </span>
                <span
                  className={
                    c.leak_check_passed
                      ? 'text-emerald-400 ml-auto'
                      : 'text-red-400 ml-auto'
                  }
                >
                  {c.leak_check_passed ? 'leak-check ✓' : 'leak-check ✗'}
                </span>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  );
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: number | string;
  accent: 'emerald' | 'sky' | 'violet' | 'red';
}) {
  const ring =
    accent === 'emerald'
      ? 'border-emerald-500/30'
      : accent === 'sky'
      ? 'border-sky-500/30'
      : accent === 'violet'
      ? 'border-violet-500/30'
      : 'border-red-500/30';
  const text =
    accent === 'emerald'
      ? 'text-emerald-300'
      : accent === 'sky'
      ? 'text-sky-300'
      : accent === 'violet'
      ? 'text-violet-300'
      : 'text-red-300';
  return (
    <div className={`bg-zinc-900 border ${ring} rounded-lg p-4`}>
      <div className="text-xs text-zinc-500 uppercase tracking-wider">
        {label}
      </div>
      <div className={`text-2xl font-mono mt-1 ${text}`}>{value}</div>
    </div>
  );
}

function SectionHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="mb-3">
      <div className="text-sm text-zinc-200">{title}</div>
      <div className="text-xs text-zinc-500">{subtitle}</div>
    </div>
  );
}

function Badge({ status }: { status: string }) {
  const color =
    status === 'published'
      ? 'bg-emerald-500/20 text-emerald-300'
      : status === 'pending_review'
      ? 'bg-amber-500/20 text-amber-300'
      : 'bg-zinc-500/20 text-zinc-300';
  return (
    <span className={`text-[10px] uppercase tracking-wider px-2 py-0.5 rounded ${color}`}>
      {status}
    </span>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 text-center text-xs text-zinc-500">
      {children}
    </div>
  );
}
