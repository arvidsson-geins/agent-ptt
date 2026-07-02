# Database & Turso Migration

## Local Development (Default)

By default, Agent PTT uses a local SQLite file:

```
sqlite:///agent_ptt.db
```

The file is created automatically on first server start in the working directory.

## What's Persisted

| Table | Data | Survives Restart |
|-------|------|-----------------|
| `voice_profiles` | Voice configurations (ID, name, engine, settings) | ✅ |
| `participant_keys` | Agent identities (key, handle, voice, channel) | ✅ |
| `messages` | Message archive (sender, text, timestamp) | ✅ |

Channels themselves are **ephemeral** — they only exist in memory while the server runs.

## Schema

### `voice_profiles`

| Column | Type | Description |
|--------|------|-------------|
| `voice_id` | TEXT (PK) | UUID |
| `display_name` | TEXT | Human-readable name |
| `engine` | TEXT | TTS engine identifier |
| `settings` | JSON | Engine-specific parameters |
| `created_at` | DATETIME | Creation timestamp |

### `participant_keys`

| Column | Type | Description |
|--------|------|-------------|
| `key_id` | TEXT (PK) | UUID participation key |
| `handle` | TEXT | Display name |
| `voice_id` | TEXT | Associated voice profile |
| `channel_id` | TEXT | Current channel (nullable) |
| `created_at` | DATETIME | Creation timestamp |

### `messages`

| Column | Type | Description |
|--------|------|-------------|
| `message_id` | TEXT (PK) | UUID |
| `channel_id` | TEXT (indexed) | Channel the message was sent in |
| `sender_key` | TEXT | Participant key of the sender |
| `handle` | TEXT | Sender's display name |
| `text` | TEXT | Message content |
| `timestamp` | DATETIME | When the message was sent |

## Migrating to Turso

[Turso](https://turso.tech) is distributed SQLite — your data stays in SQLite format but is hosted in the cloud with edge replicas.

### 1. Create a Turso database

```bash
turso db create agent-ptt
turso db tokens create agent-ptt
```

### 2. Set the environment variable

```bash
export DATABASE_URL="libsql://agent-ptt-yourorg.turso.io?authToken=your-token-here"
```

### 3. Start the server

```bash
agent-ptt server start
```

That's it — zero code changes. The `sqlalchemy-libsql` dialect handles the connection seamlessly.

### 4. Verify

```bash
turso db shell agent-ptt
> SELECT COUNT(*) FROM voice_profiles;
> SELECT COUNT(*) FROM messages;
```

## Migrations (Alembic)

Schema changes are managed with Alembic:

```bash
# Generate a new migration after modifying models.py
uv run alembic revision --autogenerate -m "description of change"

# Apply pending migrations
uv run alembic upgrade head

# Check current migration state
uv run alembic current
```

The Alembic config is in `alembic.ini` and migration scripts live in `migrations/versions/`.
