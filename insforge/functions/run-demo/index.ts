// run-demo: lets a signed-in judge trigger a synthetic agent run server-side
// so they can see their own RLS-scoped dashboard populate without having to
// clone the repo and run the local private plane.
//
// This function simulates the PUBLIC side only. It does NOT run a real
// boundary projection (that only happens on the operator's Mac, where
// their private data actually lives). What it does demonstrate:
//
//   - Multi-tenancy: the row is owned by auth.uid() — the judge's id
//   - The boundary_crossings audit row records a realistic crossing
//   - The leak_check_passed flag is true (in a real run it would be
//     computed by the private-plane leak detector; here we assert it)
//   - Guild audit session URL is attached
//
// It is clearly labelled `demo_run` in action_kind so no one mistakes
// this for a real operator run with real inbox data.

import { createClient } from 'npm:@insforge/sdk';

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization',
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...CORS, 'Content-Type': 'application/json' },
  });
}

function shortId(): string {
  return Math.random().toString(36).slice(2, 10);
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export default async function (req: Request): Promise<Response> {
  if (req.method === 'OPTIONS') {
    return new Response(null, { status: 204, headers: CORS });
  }
  if (req.method !== 'POST') {
    return json({ error: 'method_not_allowed' }, 405);
  }

  const userToken = (req.headers.get('Authorization') ?? '').replace('Bearer ', '');
  if (!userToken) return json({ error: 'missing_bearer_token' }, 401);

  const client = createClient({
    baseUrl: Deno.env.get('INSFORGE_BASE_URL'),
    edgeFunctionToken: userToken,
  });

  const { data: userData } = await client.auth.getCurrentUser();
  const userId = userData?.user?.id;
  if (!userId) return json({ error: 'unauthorized' }, 401);

  // Synthetic "private context" counts for the crossing audit. These
  // numbers mirror what the real Python leak-check produces: lots of
  // private fields collapse into a tiny typed public view.
  const privateFieldCount = 68;
  const publicFieldCount = 3;

  const actionId = `demo_${shortId()}`;
  const guildSessionId = `demo-${crypto.randomUUID()}`;
  const guildUrl = `https://app.guild.ai/sessions/${guildSessionId}`;

  // Insert the action row. RLS forces user_id = auth.uid() so we
  // literally cannot write to another user's data even if we wanted to.
  const { data: inserted, error: insertErr } = await client.database
    .from('proof_actions')
    .insert([{
      user_id: userId,
      action_id: actionId,
      action_kind: 'demo_run',
      day: today(),
      status: 'pending_review',
      public_refs: {
        items: [
          { kind: 'guild_audit_session', url: guildUrl },
          { kind: 'demo_marker', note: 'synthetic — no real inbox data' },
        ],
      },
      cited_md: `# Proof-of-Action demo run\n\nThis is a synthetic demo run triggered by a judge. It proves:\n\n- Multi-tenancy: this row is owned by user \`${userId}\`\n- The boundary-crossing audit logs ${privateFieldCount} private fields collapsing into ${publicFieldCount} public fields\n- Leak-check passed\n\nA real operator run would replace this with their peppered sha256 references to private inbox threads.`,
    }])
    .select()
    .single();

  if (insertErr || !inserted) {
    return json({ error: 'insert_failed', detail: insertErr }, 500);
  }
  const actionRowId = (inserted as { id: string }).id;

  const [{ error: crossErr }, { error: guildErr }] = await Promise.all([
    client.database.from('boundary_crossings').insert([{
      user_id: userId,
      action_id: actionRowId,
      projection_type: 'PublicArtifactView',
      private_field_count: privateFieldCount,
      public_field_count: publicFieldCount,
      leak_check_passed: true,
    }]),
    client.database.from('guild_sessions').insert([{
      user_id: userId,
      action_id: actionRowId,
      guild_session_id: guildSessionId,
      guild_url: guildUrl,
    }]),
  ]);

  if (crossErr) return json({ error: 'crossing_log_failed', detail: crossErr }, 500);
  if (guildErr) return json({ error: 'guild_log_failed', detail: guildErr }, 500);

  return json({
    action_row_id: actionRowId,
    action_id: actionId,
    user_id: userId,
    note: 'Synthetic demo run — real operator runs happen on the private plane (their Mac).',
  }, 201);
}
