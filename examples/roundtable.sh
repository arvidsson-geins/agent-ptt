#!/usr/bin/env bash
# A panel of AI agents talk to each other in an Agent PTT channel — out loud.
#
#   ./examples/roundtable.sh "who the greatest World Cup player of all time is" 9
#   ./examples/roundtable.sh "whether tabs or spaces are better" 10
#
# Each agent is a headless `claude -p` call that reads the channel transcript
# and answers whoever spoke last. Nobody holds a session: they are just
# participation keys posting to the same channel over REST, which is all any
# agent needs to join a conversation.
#
# Override the panel with PANEL="Name|persona|voice-id;Name|persona|voice-id",
# and the channel with CHANNEL=<existing-channel-id>.
# Drop the voice-id and the handle gets an auto-designed one instead.
set -euo pipefail

SERVER="${AGENT_PTT_URL:-http://localhost:8770}"
SUBJECT="${1:-who the greatest World Cup player of all time is}"
TURNS="${2:-9}"

DEFAULT_PANEL="Pepe|all instinct and passion, argues from feeling, memory and moments of magic|en-AU-WilliamMultilingualNeural;\
Ingrid|a data analyst who answers everything with numbers and evidence|en-GB-SoniaNeural;\
Roy|a grumpy contrarian veteran who is certain everything was better before|en-IE-ConnorNeural"
IFS=';' read -r -a PANEL <<<"${PANEL:-$DEFAULT_PANEL}"

for bin in jq claude curl; do
  command -v "$bin" >/dev/null || { echo "missing dependency: $bin" >&2; exit 1; }
done
curl -sf "$SERVER/channels" >/dev/null || {
  echo "no Agent PTT server at $SERVER — start one with: uv run agent-ptt server start" >&2
  exit 1
}

# 1. A channel for them to talk in. Set CHANNEL=<id> to reuse an existing one
#    (handy when you want the web UI open on it before the panel starts).
CHANNEL="${CHANNEL:-$(curl -sS -X POST "$SERVER/channels" \
  -H 'content-type: application/json' \
  -d "$(jq -nc --arg n "Panel: $SUBJECT" '{name:$n}')" | jq -r .channel_id)}"

# 2. One participant per panelist, each with a clearly different voice. Leave
#    voice_id null and the server designs one from the handle and pins it.
HANDLES=() PERSONAS=() KEYS=()
for member in "${PANEL[@]}"; do
  IFS='|' read -r handle persona voice <<<"$member"
  key=$(curl -sS -X POST "$SERVER/channels/$CHANNEL/join" \
    -H 'content-type: application/json' \
    -d "$(jq -nc --arg h "$handle" --arg v "${voice:-}" \
          '{handle:$h, voice_id:(if $v == "" then null else $v end)}')" | jq -r .key_id)
  HANDLES+=("$handle"); PERSONAS+=("$persona"); KEYS+=("$key")
done

echo "channel: $CHANNEL"
echo "panel:   ${HANDLES[*]}"
echo "listen:  agent-ptt listen $CHANNEL   (or open $SERVER/ui/)"
echo

# 3. One turn: read the transcript, think, speak.
turn() { # $1=key  $2=handle  $3=persona
  local transcript reply
  transcript=$(curl -sS "$SERVER/channels/$CHANNEL/history" \
    | jq -r '.[-6:][] | "\(.handle): \(.text)"')

  reply=$(claude -p "You are $2, on a panel discussing: $SUBJECT
You are $3.

Transcript so far:
${transcript:-(nothing yet — you open the discussion)}

Reply with ONE spoken sentence of at most 25 words, in character. Answer the
previous speaker directly and name them. Output the sentence only: no quotes,
no preamble, no markdown, nothing that isn't meant to be heard." < /dev/null)

  reply=$(printf '%s' "$reply" | tr '\n' ' ' | tr -s ' ' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
  [ -n "$reply" ] || return 0

  echo "$2: $reply"
  curl -sS -X POST "$SERVER/channels/$CHANNEL/say" \
    -H 'content-type: application/json' \
    -d "$(jq -nc --arg k "$1" --arg t "$reply" '{key_id:$k,text:$t}')" >/dev/null
  sleep 2   # let the speakers finish the line before the next one starts
}

# 4. Round-robin for N turns.
n=${#HANDLES[@]}
for ((i = 0; i < TURNS; i++)); do
  s=$((i % n))
  turn "${KEYS[$s]}" "${HANDLES[$s]}" "${PERSONAS[$s]}"
done

echo
echo "transcript: agent-ptt channel history $CHANNEL"
