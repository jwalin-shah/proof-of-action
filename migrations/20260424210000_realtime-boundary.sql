-- Realtime: stream boundary_crossings inserts to the owning user's channel.
-- Channel pattern is scoped per-user so RLS-equivalent isolation holds on the
-- wire too: users only ever subscribe to boundary:user:<their own uid>.

-- 1. Register the channel pattern so SDK subscriptions are accepted.
INSERT INTO realtime.channels (pattern, description, enabled)
VALUES (
  'boundary:user:%',
  'Per-user stream of boundary_crossings rows as they are inserted.',
  true
)
ON CONFLICT (pattern) DO UPDATE SET enabled = true;

-- 2. Trigger function: publish crossing_logged on each INSERT.
CREATE OR REPLACE FUNCTION notify_boundary_crossing()
RETURNS TRIGGER AS $$
BEGIN
  PERFORM realtime.publish(
    'boundary:user:' || NEW.user_id::text,
    'crossing_logged',
    jsonb_build_object(
      'crossing_id', NEW.id,
      'action_id', NEW.action_id,
      'projection_type', NEW.projection_type,
      'private_field_count', NEW.private_field_count,
      'public_field_count', NEW.public_field_count,
      'leak_check_passed', NEW.leak_check_passed,
      'created_at', NEW.created_at
    )
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 3. Attach trigger to boundary_crossings.
DROP TRIGGER IF EXISTS boundary_crossing_realtime ON boundary_crossings;
CREATE TRIGGER boundary_crossing_realtime
  AFTER INSERT ON boundary_crossings
  FOR EACH ROW
  EXECUTE FUNCTION notify_boundary_crossing();
