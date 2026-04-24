import { useEffect, useState, useRef } from 'react'
import { insforge } from './insforge'

type Action = {
  id: string
  action_id: string
  action_kind: string
  status: string
  day: string
  created_at: string
}

type Crossing = {
  id: string
  action_id: string | null
  projection_type: string
  private_field_count: number
  public_field_count: number
  leak_check_passed: boolean
  created_at: string
}

type GuildSession = {
  action_id: string | null
  guild_session_id: string
  guild_url: string
}

export default function Dashboard({ user }: { user: { id: string; email: string } }) {
  const [actions, setActions] = useState<Action[]>([])
  const [crossings, setCrossings] = useState<Crossing[]>([])
  const [guilds, setGuilds] = useState<Record<string, string>>({})
  const [liveCount, setLiveCount] = useState(0)
  const [rtStatus, setRtStatus] = useState<'off' | 'connecting' | 'live'>('off')
  const flashRef = useRef<string | null>(null)

  async function loadAll() {
    const [aRes, cRes, gRes] = await Promise.all([
      insforge.database
        .from('proof_actions')
        .select('*')
        .order('created_at', { ascending: false })
        .limit(25),
      insforge.database
        .from('boundary_crossings')
        .select('*')
        .order('created_at', { ascending: false })
        .limit(25),
      insforge.database.from('guild_sessions').select('*').limit(50),
    ])
    if (aRes.data) setActions(aRes.data as Action[])
    if (cRes.data) setCrossings(cRes.data as Crossing[])
    if (gRes.data) {
      const map: Record<string, string> = {}
      for (const row of gRes.data as GuildSession[]) {
        if (row.action_id) map[row.action_id] = row.guild_url
      }
      setGuilds(map)
    }
  }

  useEffect(() => {
    loadAll()
  }, [])

  useEffect(() => {
    let mounted = true
    const channel = `boundary:user:${user.id}`

    async function subscribe() {
      setRtStatus('connecting')
      try {
        await insforge.realtime.connect()
        const { ok } = await insforge.realtime.subscribe(channel)
        if (!ok || !mounted) return
        setRtStatus('live')
        insforge.realtime.on('crossing_logged', (payload: any) => {
          setLiveCount((n) => n + 1)
          flashRef.current = payload?.action_id ?? null
          loadAll()
        })
      } catch {
        setRtStatus('off')
      }
    }
    subscribe()

    return () => {
      mounted = false
      insforge.realtime.unsubscribe(channel)
    }
  }, [user.id])

  const passFail = crossings.every((c) => c.leak_check_passed)

  return (
    <div className="space-y-6">
      <section className="grid grid-cols-4 gap-3">
        <Stat label="actions" value={actions.length} />
        <Stat label="boundary crossings" value={crossings.length} />
        <Stat
          label="leak check"
          value={passFail ? 'PASS' : 'FAIL'}
          color={passFail ? 'text-term-accent' : 'text-term-err'}
        />
        <Stat
          label={`realtime (${rtStatus})`}
          value={liveCount === 0 ? '—' : `+${liveCount}`}
          color={rtStatus === 'live' ? 'text-term-accent' : 'text-term-dim'}
        />
      </section>

      <section>
        <div className="text-term-dim mb-2">$ SELECT * FROM proof_actions</div>
        <div className="border border-term-border">
          <div className="grid grid-cols-[1fr_1fr_1fr_1fr_auto] gap-3 px-3 py-2 border-b border-term-border bg-term-panel text-term-dim text-xs uppercase">
            <div>action_id</div>
            <div>kind</div>
            <div>status</div>
            <div>day</div>
            <div>audit</div>
          </div>
          {actions.length === 0 && (
            <div className="px-3 py-4 text-term-dim">
              No rows yet. Run the agent: <code>make demo</code>
            </div>
          )}
          {actions.map((a) => {
            const fresh = flashRef.current === a.action_id
            return (
              <div
                key={a.id}
                className={`grid grid-cols-[1fr_1fr_1fr_1fr_auto] gap-3 px-3 py-2 border-b border-term-border last:border-b-0 ${
                  fresh ? 'bg-term-accent/10' : ''
                }`}
              >
                <div className="text-term-fg">{a.action_id}</div>
                <div className="text-term-dim">{a.action_kind}</div>
                <div
                  className={
                    a.status === 'published' ? 'text-term-accent' : 'text-term-warn'
                  }
                >
                  {a.status}
                </div>
                <div className="text-term-dim">{a.day}</div>
                <div>
                  {guilds[a.id] ? (
                    <a href={guilds[a.id]} target="_blank" rel="noreferrer">
                      [guild ↗]
                    </a>
                  ) : (
                    <span className="text-term-dim">—</span>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </section>

      <section>
        <div className="text-term-dim mb-2">
          $ SELECT * FROM boundary_crossings
        </div>
        <div className="border border-term-border">
          <div className="grid grid-cols-[1.5fr_1fr_1fr_1fr_1fr] gap-3 px-3 py-2 border-b border-term-border bg-term-panel text-term-dim text-xs uppercase">
            <div>projection</div>
            <div>private fields</div>
            <div>public fields</div>
            <div>leak check</div>
            <div>at</div>
          </div>
          {crossings.length === 0 && (
            <div className="px-3 py-4 text-term-dim">No crossings logged.</div>
          )}
          {crossings.map((c) => (
            <div
              key={c.id}
              className="grid grid-cols-[1.5fr_1fr_1fr_1fr_1fr] gap-3 px-3 py-2 border-b border-term-border last:border-b-0"
            >
              <div className="text-term-fg">{c.projection_type}</div>
              <div className="text-term-dim">{c.private_field_count}</div>
              <div className="text-term-accent">{c.public_field_count}</div>
              <div
                className={c.leak_check_passed ? 'text-term-accent' : 'text-term-err'}
              >
                {c.leak_check_passed ? 'PASS' : 'FAIL'}
              </div>
              <div className="text-term-dim">
                {new Date(c.created_at).toLocaleTimeString()}
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}

function Stat({
  label,
  value,
  color = 'text-term-fg',
}: {
  label: string
  value: string | number
  color?: string
}) {
  return (
    <div className="border border-term-border bg-term-panel px-4 py-3">
      <div className="text-term-dim text-xs uppercase">{label}</div>
      <div className={`text-2xl ${color}`}>{value}</div>
    </div>
  )
}
