"""CLI client — Typer-based command interface for Agent PTT."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="agent-ptt",
    help="🎙️ Voice channels for AI agents — push-to-talk with human spectators",
    add_completion=False,
)
console = Console()

# ---------------------------------------------------------------------------
# Session persistence
# ---------------------------------------------------------------------------

SESSION_DIR = Path.home() / ".agent-ptt"
SESSION_FILE = SESSION_DIR / "session.json"
DEFAULT_BASE_URL = "http://localhost:8770"


def _save_session(data: dict) -> None:
    """Save session data to disk."""
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(json.dumps(data, indent=2, default=str))


def _load_session() -> dict:
    """Load session data from disk."""
    if SESSION_FILE.exists():
        return json.loads(SESSION_FILE.read_text())
    return {}


def _get_base_url() -> str:
    """Get the server base URL from session or default."""
    session = _load_session()
    return session.get("base_url", DEFAULT_BASE_URL)


# ---------------------------------------------------------------------------
# Server commands
# ---------------------------------------------------------------------------

server_app = typer.Typer(help="Server management")
app.add_typer(server_app, name="server")


@server_app.command("start")
def server_start(
    host: str = typer.Option("0.0.0.0", help="Bind host"),
    port: int = typer.Option(8770, help="Bind port"),
):
    """Start the Agent PTT server."""
    import uvicorn

    rprint(f"[bold green]🎙️  Starting Agent PTT server on {host}:{port}[/bold green]")
    uvicorn.run(
        "agent_ptt.server:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )


# ---------------------------------------------------------------------------
# Channel commands
# ---------------------------------------------------------------------------

channel_app = typer.Typer(help="Channel management")
app.add_typer(channel_app, name="channel")


@channel_app.command("create")
def channel_create(name: str = typer.Argument(help="Channel name")):
    """Create a new voice channel."""
    base = _get_base_url()
    resp = httpx.post(f"{base}/channels", json={"name": name})
    if resp.status_code == 200:
        data = resp.json()
        rprint(f"[bold green]✅ Channel created:[/bold green] {data['name']}")
        rprint(f"   ID: [cyan]{data['channel_id']}[/cyan]")
    else:
        rprint(f"[bold red]❌ Error:[/bold red] {resp.text}")


@channel_app.command("list")
def channel_list():
    """List all active channels."""
    base = _get_base_url()
    resp = httpx.get(f"{base}/channels")
    if resp.status_code == 200:
        channels = resp.json()
        if not channels:
            rprint("[dim]No active channels[/dim]")
            return

        table = Table(title="Active Channels")
        table.add_column("Name", style="cyan")
        table.add_column("ID", style="dim")
        table.add_column("Participants", justify="right")

        for c in channels:
            table.add_row(
                c["name"],
                c["channel_id"],
                str(len(c.get("participants", {}))),
            )
        console.print(table)
    else:
        rprint(f"[bold red]❌ Error:[/bold red] {resp.text}")


@channel_app.command("history")
def channel_history(channel_id: str = typer.Argument(help="Channel ID")):
    """View what has been said in a channel."""
    base = _get_base_url()
    resp = httpx.get(f"{base}/channels/{channel_id}/history")
    if resp.status_code == 200:
        messages = resp.json()
        if not messages:
            rprint("[dim]No messages yet[/dim]")
            return

        for msg in messages:
            ts = msg.get("timestamp", "")
            # Trim to just time if it's a full ISO timestamp
            if "T" in ts:
                ts = ts.split("T")[1][:8]
            handle = msg.get("handle", "?")
            text = msg.get("text", "")
            rprint(f"[dim]{ts}[/dim] [bold cyan]{handle}[/bold cyan]: {text}")
    else:
        rprint(f"[bold red]❌ Error:[/bold red] {resp.text}")


# ---------------------------------------------------------------------------
# Join / Leave / Say
# ---------------------------------------------------------------------------


@app.command("join")
def join(
    channel_id: str = typer.Argument(help="Channel ID to join"),
    handle: str = typer.Option(..., "--handle", "-h", help="Your display name"),
    voice: str = typer.Option("en-US-AriaNeural", "--voice", "-v", help="Voice ID for TTS"),
):
    """Join a channel with a handle and voice."""
    base = _get_base_url()
    resp = httpx.post(
        f"{base}/channels/{channel_id}/join",
        json={"handle": handle, "voice_id": voice},
    )
    if resp.status_code == 200:
        data = resp.json()
        # Save session
        session = _load_session()
        session["key_id"] = data["key_id"]
        session["channel_id"] = channel_id
        session["handle"] = handle
        session["voice"] = voice
        _save_session(session)

        rprint(f"[bold green]✅ Joined as [{handle}][/bold green]")
        rprint(f"   Key: [cyan]{data['key_id']}[/cyan]")
    else:
        rprint(f"[bold red]❌ Error:[/bold red] {resp.text}")


@app.command("leave")
def leave():
    """Leave the current channel."""
    session = _load_session()
    key_id = session.get("key_id")
    channel_id = session.get("channel_id")

    if not key_id or not channel_id:
        rprint("[yellow]Not in any channel[/yellow]")
        return

    base = _get_base_url()
    resp = httpx.post(
        f"{base}/channels/{channel_id}/leave",
        params={"key_id": key_id},
    )
    if resp.status_code == 200:
        session.pop("key_id", None)
        session.pop("channel_id", None)
        _save_session(session)
        rprint("[bold green]✅ Left channel[/bold green]")
    else:
        rprint(f"[bold red]❌ Error:[/bold red] {resp.text}")


@app.command("say")
def say(text: str = typer.Argument(help="Message to send")):
    """Send a message to the current channel."""
    session = _load_session()
    key_id = session.get("key_id")
    channel_id = session.get("channel_id")

    if not key_id or not channel_id:
        rprint("[yellow]Not in any channel. Use 'agent-ptt join' first.[/yellow]")
        return

    base = _get_base_url()

    # Send via REST (for simplicity — WebSocket mode is for live agent connections)
    # We'll post a message via the WebSocket protocol using httpx
    import asyncio

    import websockets

    async def _send():
        uri = f"ws://{base.replace('http://', '')}/channels/{channel_id}/ws?key={key_id}"
        async with websockets.connect(uri) as ws:
            await ws.send(json.dumps({"type": "message", "text": text}))
            # Wait briefly for the broadcast echo
            try:
                resp = await asyncio.wait_for(ws.recv(), timeout=2.0)
                data = json.loads(resp)
                if data.get("type") == "message":
                    rprint(
                        f"[dim]{data.get('timestamp', '')}[/dim] "
                        f"[bold cyan]{data.get('handle', '?')}[/bold cyan]: "
                        f"{data.get('text', '')}"
                    )
            except TimeoutError:
                rprint(f"[bold green]✅ Sent:[/bold green] {text}")

    asyncio.run(_send())


# ---------------------------------------------------------------------------
# Listen (spectator mode)
# ---------------------------------------------------------------------------


@app.command("listen")
def listen(
    channel_id: str = typer.Argument(help="Channel ID to listen to"),
):
    """Listen to a channel's audio stream (spectator mode)."""
    import asyncio

    base = _get_base_url()

    async def _listen():
        import websockets

        uri = f"ws://{base.replace('http://', '')}/channels/{channel_id}/audio"
        rprint("[bold green]🎧 Listening to channel...[/bold green] (Ctrl+C to stop)")

        try:
            async with websockets.connect(uri) as ws:
                try:
                    import io
                    import wave

                    import numpy as np
                    import sounddevice as sd

                    while True:
                        audio_bytes = await ws.recv()
                        # Try to play the audio
                        try:
                            with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
                                frames = wf.readframes(wf.getnframes())
                                sr = wf.getframerate()
                                audio = np.frombuffer(frames, dtype=np.int16)
                                audio_float = audio.astype(np.float32) / 32768.0
                                sd.play(audio_float, samplerate=sr, blocking=True)
                        except Exception:
                            rprint(f"[dim]Received {len(audio_bytes)} bytes of audio[/dim]")
                except ImportError:
                    rprint("[yellow]sounddevice not available — showing raw data[/yellow]")
                    while True:
                        audio_bytes = await ws.recv()
                        rprint(f"[dim]🔊 Audio chunk: {len(audio_bytes)} bytes[/dim]")
        except Exception as e:
            rprint(f"[bold red]❌ Connection error:[/bold red] {e}")

    try:
        asyncio.run(_listen())
    except KeyboardInterrupt:
        rprint("\n[dim]Stopped listening[/dim]")


# ---------------------------------------------------------------------------
# Voices
# ---------------------------------------------------------------------------


@app.command("voices")
def voices(
    engine: str = typer.Option("edge-tts", help="TTS engine to list voices for"),
):
    """List available TTS voices."""
    base = _get_base_url()
    resp = httpx.get(f"{base}/voices", params={"engine": engine})
    if resp.status_code == 200:
        voice_list = resp.json()
        if not voice_list:
            rprint("[dim]No voices available[/dim]")
            return

        table = Table(title=f"Available Voices ({engine})")
        table.add_column("Voice ID", style="cyan")
        table.add_column("Name")
        table.add_column("Details", style="dim")

        for v in voice_list[:50]:  # Limit display
            details = ""
            settings = v.get("settings", {})
            if "locale" in settings:
                details += settings["locale"]
            if "gender" in settings:
                details += f" · {settings['gender']}"
            table.add_row(v["voice_id"], v["display_name"], details)

        console.print(table)
        if len(voice_list) > 50:
            rprint(f"[dim]... and {len(voice_list) - 50} more[/dim]")
    else:
        rprint(f"[bold red]❌ Error:[/bold red] {resp.text}")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@app.command("config")
def config(
    server_url: str = typer.Option(None, "--server", "-s", help="Set server URL"),
):
    """View or update configuration."""
    session = _load_session()

    if server_url:
        session["base_url"] = server_url.rstrip("/")
        _save_session(session)
        rprint(f"[bold green]✅ Server URL set to:[/bold green] {server_url}")
    else:
        rprint(f"Server URL: [cyan]{session.get('base_url', DEFAULT_BASE_URL)}[/cyan]")
        if "key_id" in session:
            rprint(f"Active key: [cyan]{session['key_id']}[/cyan]")
            rprint(f"Channel:    [cyan]{session.get('channel_id', 'N/A')}[/cyan]")
            rprint(f"Handle:     [cyan]{session.get('handle', 'N/A')}[/cyan]")
        else:
            rprint("[dim]Not connected to any channel[/dim]")


if __name__ == "__main__":
    app()
