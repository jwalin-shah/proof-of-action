#!/usr/bin/env bash
# Configure two-user ACL: agent_private can only touch private:*, agent_public only public:*.
# The privacy boundary is enforced at the infra layer — not app logic.
set -euo pipefail
PORT="${REDIS_PORT:-6390}"

redis-cli -p "$PORT" ACL SETUSER agent_private on '>privpw' '~private:*' '+@all' '-@dangerous'
redis-cli -p "$PORT" ACL SETUSER agent_public  on '>pubpw'  '~public:*'  '+@all' '-@dangerous'

echo "ACL users:"
redis-cli -p "$PORT" ACL LIST
