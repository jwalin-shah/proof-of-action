// finalize-action: public-plane handler. Accepts a typed PublicArtifactView
// from the local daemon (with the user's JWT), persists it under RLS, and
// logs the boundary crossing + optional Guild session for external audit.
//
// The private plane never calls this directly — boundary.py projects the
// private draft into the public view, then POSTs only that view here.
// Peppering/hashing happens client-side so the pepper never leaves the
// private plane.

import { createClient } from 'npm:@insforge/sdk';

type PublicArtifactView = {
  action_id: string;
  action_kind: string;
  day: string;
  status: string;
  public_refs: Record<string, unknown> | null;
  cited_md: string;
};

type FinalizeRequest = {
  public_view: PublicArtifactView;
  crossing: {
    projection_type: string;
    private_field_count: number;
    public_field_count: number;
    leak_check_passed: boolean;
  };
  guild?: {
    session_id: string;
    url: string;
  };
};

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

export default async function (req: Request): Promise<Response> {
  if (req.method === 'OPTIONS') {
    return new Response(null, { status: 204, headers: CORS });
  }
  if (req.method !== 'POST') {
    return json({ error: 'method_not_allowed' }, 405);
  }

  const authHeader = req.headers.get('Authorization');
  const userToken = authHeader ? authHeader.replace('Bearer ', '') : null;
  if (!userToken) {
    return json({ error: 'missing_bearer_token' }, 401);
  }

  const client = createClient({
    baseUrl: Deno.env.get('INSFORGE_BASE_URL'),
    edgeFunctionToken: userToken,
  });

  const { data: userData } = await client.auth.getCurrentUser();
  const userId = userData?.user?.id;
  if (!userId) {
    return json({ error: 'unauthorized' }, 401);
  }

  let payload: FinalizeRequest;
  try {
    payload = await req.json();
  } catch {
    return json({ error: 'invalid_json' }, 400);
  }

  const { public_view, crossing, guild } = payload;
  if (!public_view?.action_id || !crossing) {
    return json({ error: 'missing_required_fields' }, 400);
  }
  if (!crossing.leak_check_passed) {
    return json({ error: 'leak_check_failed_refusing_to_publish' }, 422);
  }

  // Insert the action row. RLS enforces user_id = auth.uid().
  const { data: inserted, error: insertErr } = await client.database
    .from('proof_actions')
    .insert([{
      user_id: userId,
      action_id: public_view.action_id,
      action_kind: public_view.action_kind,
      day: public_view.day,
      status: public_view.status,
      public_refs: public_view.public_refs ?? {},
      cited_md: public_view.cited_md,
    }])
    .select()
    .single();

  if (insertErr || !inserted) {
    return json({ error: 'insert_failed', detail: insertErr }, 500);
  }
  const actionRowId = (inserted as { id: string }).id;

  // Log the boundary crossing.
  const { error: crossErr } = await client.database
    .from('boundary_crossings')
    .insert([{
      user_id: userId,
      action_id: actionRowId,
      projection_type: crossing.projection_type,
      private_field_count: crossing.private_field_count,
      public_field_count: crossing.public_field_count,
      leak_check_passed: crossing.leak_check_passed,
    }]);

  if (crossErr) {
    return json({ error: 'crossing_log_failed', detail: crossErr }, 500);
  }

  // Optional Guild session attachment.
  if (guild?.session_id && guild?.url) {
    const { error: guildErr } = await client.database
      .from('guild_sessions')
      .insert([{
        user_id: userId,
        action_id: actionRowId,
        guild_session_id: guild.session_id,
        guild_url: guild.url,
      }]);
    if (guildErr) {
      return json({ error: 'guild_log_failed', detail: guildErr }, 500);
    }
  }

  return json({
    action_row_id: actionRowId,
    action_id: public_view.action_id,
    public: public_view.status === 'published',
  }, 201);
}
