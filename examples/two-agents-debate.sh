#!/usr/bin/env bash
# Two AI agents talk to each other in an Agent PTT channel — out loud.
#
#   ./examples/two-agents-debate.sh "whether tabs or spaces are better" 10
#
# Each agent is a headless `claude -p` call that reads the channel transcript
# and answers the other one. Neither holds a session: they are just two
# participation keys posting to the same channel over REST, which is all any
# agent needs to join a conversation.
set -euo pipefail

SERVER="${AGENT_PTT_URL:-http://localhost:8770}"
SUBJECT="${1:-whether tabs or spaces are better}"
TURNS="${2:-10}"

for bin in jq claude curl; do
  command -v "$bin" >/dev/null || { echo "missing dependency: $bin" >&2; exit 1; }
done
curl -sf "$SERVER/channels" >/dev/null || {
  echo "no Agent PTT server at $SERVER — start one with: uv run agent-ptt server start" >&2
  exit 1
}

# 1. A channel for them to talk in.
CHANNEL=$(curl -sS -X POST "$SERVER/channels" \
  -H 'content-type: application/json' \
  -d "$(jq -nc --arg n "Debate: $SUBJECT" '{name:$n}')" | jq -r .channel_id)

# 2. Two participants. No --voice, so each handle gets its own designed voice.
join() {
  curl -sS -X POST "$SERVER/channels/$CHANNEL/join" \
    -H 'content-type: application/json' \
    -d "$(jq -nc --arg h "$1" '{handle:$h}')" | jq -r .key_id
}
ADA=$(join "Ada")
GRACE=$(join "Grace")

echo "channel: $CHANNEL"
echo "listen:  agent-ptt listen $CHANNEL   (or open $SERVER/ui/)"
echo

# 3. One turn: read the transcript, think, speak.
turn() { # $1=key  $2=handle  $3=stance
  local transcript reply
  transcript=$(curl -sS "$SERVER/channels/$CHANNEL/history" \
    | jq -r '.[-6:][] | "\(.handle): \(.text)"')

  reply=$(claude -p "You are $2, debating: $SUBJECT
Your stance: $3

Transcript so far:
${transcript:-(nothing yet — you open the debate)}

Reply with ONE spoken sentence of at most 20 words. Answer the previous
speaker directly. Output the sentence only: no quotes, no preamble, no
markdown, nothing that isn't meant to be heard." < /dev/null)

  reply=$(printf '%s' "$reply" | tr '\n' ' ' | tr -s ' ' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
  [ -n "$reply" ] || return 0

  echo "$2: $reply"
  curl -sS -X POST "$SERVER/channels/$CHANNEL/say" \
    -H 'content-type: application/json' \
    -d "$(jq -nc --arg k "$1" --arg t "$reply" '{key_id:$k,text:$t}')" >/dev/null
  sleep 2   # let the speakers finish the line before the next one starts
}

# 4. Alternate for N turns.
for ((i = 1; i <= TURNS; i++)); do
  if ((i % 2)); then turn "$ADA" "Ada" "in favour"; else turn "$GRACE" "Grace" "against"; fi
done

echo
echo "transcript: agent-ptt channel history $CHANNEL"
