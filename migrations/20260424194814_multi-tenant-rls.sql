-- Multi-tenant upgrade for Proof-of-Action.
-- Adds user_id to proof_actions, creates audit tables, enables RLS with
-- user-scoped policies so each user only sees their own rows.

-- 1. Drop the single-tenant demo row (pre-migration state, no user_id).
DELETE FROM proof_actions;

-- 2. Add user_id FK to auth.users. NOT NULL because every action must be owned.
ALTER TABLE proof_actions
  ADD COLUMN user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE;

CREATE INDEX proof_actions_user_id_idx ON proof_actions(user_id);

-- 3. Replace the admin-only policy with user-scoped RLS.
ALTER TABLE proof_actions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS project_admin_policy ON proof_actions;

CREATE POLICY proof_actions_owner_select ON proof_actions
  FOR SELECT TO authenticated
  USING (user_id = auth.uid());

CREATE POLICY proof_actions_owner_insert ON proof_actions
  FOR INSERT TO authenticated
  WITH CHECK (user_id = auth.uid());

CREATE POLICY proof_actions_owner_update ON proof_actions
  FOR UPDATE TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- Public read of finalized artifacts (anon role) — needed so judges/verifiers
-- can load cited.md without a JWT. Writes stay locked to the owner.
CREATE POLICY proof_actions_public_read ON proof_actions
  FOR SELECT TO anon
  USING (status = 'published');

-- 4. boundary_crossings: every time a PrivateDraft is projected to a
--    PublicArtifactView, we log a row. Judges can audit the crossing count.
CREATE TABLE boundary_crossings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  action_id uuid REFERENCES proof_actions(id) ON DELETE CASCADE,
  projection_type text NOT NULL,
  private_field_count int NOT NULL,
  public_field_count int NOT NULL,
  leak_check_passed boolean NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX boundary_crossings_user_id_idx ON boundary_crossings(user_id);
CREATE INDEX boundary_crossings_action_id_idx ON boundary_crossings(action_id);

ALTER TABLE boundary_crossings ENABLE ROW LEVEL SECURITY;

CREATE POLICY boundary_crossings_owner_select ON boundary_crossings
  FOR SELECT TO authenticated
  USING (user_id = auth.uid());

CREATE POLICY boundary_crossings_owner_insert ON boundary_crossings
  FOR INSERT TO authenticated
  WITH CHECK (user_id = auth.uid());

-- 5. guild_sessions: per-run external audit session URLs.
CREATE TABLE guild_sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  action_id uuid REFERENCES proof_actions(id) ON DELETE CASCADE,
  guild_session_id text NOT NULL,
  guild_url text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX guild_sessions_user_id_idx ON guild_sessions(user_id);

ALTER TABLE guild_sessions ENABLE ROW LEVEL SECURITY;

CREATE POLICY guild_sessions_owner_select ON guild_sessions
  FOR SELECT TO authenticated
  USING (user_id = auth.uid());

CREATE POLICY guild_sessions_owner_insert ON guild_sessions
  FOR INSERT TO authenticated
  WITH CHECK (user_id = auth.uid());

-- Public read of guild sessions tied to published actions (so cited.md
-- verifiers can load the audit link without a JWT).
CREATE POLICY guild_sessions_public_read ON guild_sessions
  FOR SELECT TO anon
  USING (
    action_id IN (SELECT id FROM proof_actions WHERE status = 'published')
  );
