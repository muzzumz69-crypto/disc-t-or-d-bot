# bot_web.py
import os
import json
import random
import time
import threading
from pathlib import Path
from datetime import timedelta

from flask import Flask, jsonify, redirect, url_for, request
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

# =========================
# Env / Config
# =========================
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("TOKEN")
CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")  # Required for invite link
PERMISSIONS = os.getenv("DISCORD_PERMISSIONS", "2147485696")  # tweak if you need
PUBLIC_FLAGS = os.getenv("DISCORD_PUBLIC", "true").lower() == "true"  # app is public?
HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", "5000"))

if not TOKEN:
    raise SystemExit("DISCORD_TOKEN not set. Put it in Render env vars or .env")

# =========================
# Data / Files
# =========================
BASE = Path(__file__).parent
QUESTIONS_FILE = BASE / "questions.json"
SETTINGS_FILE  = BASE / "settings.json"

DEFAULT_QUESTIONS = {
    "truth": {"sfw": ["What’s your biggest fear?"], "nsfw": ["What’s your wildest fantasy (PG-13)?"]},
    "dare":  {"sfw": ["Do 10 push-ups"], "nsfw": ["Send a flirty compliment (keep it respectful!)"]},
    "wyr":   {"sfw": ["Would you rather be invisible or fly?"], "nsfw": ["Would you rather kiss or cuddle?"]},
    "ama":   {"sfw": ["Ask me anything!"], "nsfw": ["Ask me anything (spicy but safe)."]},
}
DEFAULT_SETTINGS = {"user_modes": {}}

def load_json(path: Path, default_obj):
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    else:
        with path.open("w", encoding="utf-8") as f:
            json.dump(default_obj, f, ensure_ascii=False, indent=2)
        return default_obj

def save_json(path: Path, data):
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

questions = load_json(QUESTIONS_FILE, DEFAULT_QUESTIONS)
settings  = load_json(SETTINGS_FILE,  DEFAULT_SETTINGS)

# =========================
# Discord Bot
# =========================
intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

start_time = time.time()
synced_once = False

def get_user_mode(user_id: int) -> str:
    return settings.get("user_modes", {}).get(str(user_id), "sfw")

def set_user_mode(user_id: int, mode: str):
    settings.setdefault("user_modes", {})[str(user_id)] = mode
    save_json(SETTINGS_FILE, settings)

def get_question(category: str, user_id: int) -> str:
    mode = get_user_mode(user_id)
    pool = questions.get(category, {}).get(mode, [])
    if not pool:
        return f"No questions found for {category.upper()} ({mode.upper()})."
    return random.choice(pool)

def make_embed(title: str, content: str, mode: str, interaction: discord.Interaction) -> discord.Embed:
    e = discord.Embed(title=title, description=content)
    loc = "DM" if interaction.guild is None else f"#{getattr(interaction.channel, 'name', 'channel')}"
    e.set_footer(text=f"{mode.upper()} • {loc}")
    return e

async def respond(interaction: discord.Interaction, *, content: str | None = None,
                  embed: discord.Embed | None = None, view=None, ephemeral: bool = False):
    # Ephemeral only supported in guilds
    ephemeral = bool(ephemeral and interaction.guild is not None)
    if interaction.response.is_done():
        await interaction.followup.send(content=content, embed=embed, view=view, ephemeral=ephemeral)
    else:
        await interaction.response.send_message(content=content, embed=embed, view=view, ephemeral=ephemeral)

# UI
class QuestionView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="Truth", style=discord.ButtonStyle.success)
    async def truth_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await safe_defer(interaction)
        q = get_question("truth", self.user_id)
        await interaction.channel.send(embed=make_embed("Truth", q, get_user_mode(self.user_id), interaction), view=QuestionView(self.user_id))

    @discord.ui.button(label="Dare", style=discord.ButtonStyle.danger)
    async def dare_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await safe_defer(interaction)
        q = get_question("dare", self.user_id)
        await interaction.channel.send(embed=make_embed("Dare", q, get_user_mode(self.user_id), interaction), view=QuestionView(self.user_id))

    @discord.ui.button(label="Would You Rather", style=discord.ButtonStyle.primary)
    async def wyr_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await safe_defer(interaction)
        q = get_question("wyr", self.user_id)
        await interaction.channel.send(embed=make_embed("Would You Rather", q, get_user_mode(self.user_id), interaction), view=QuestionView(self.user_id))

    @discord.ui.button(label="Ask Me Anything", style=discord.ButtonStyle.secondary)
    async def ama_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await safe_defer(interaction)
        q = get_question("ama", self.user_id)
        await interaction.channel.send(embed=make_embed("Ask Me Anything", q, get_user_mode(self.user_id), interaction), view=QuestionView(self.user_id))

class ModeSelect(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="SFW Mode", style=discord.ButtonStyle.success)
    async def sfw_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        set_user_mode(interaction.user.id, "sfw")
        await interaction.response.send_message("✅ Your mode has been set to **SFW**.", ephemeral=(interaction.guild is not None))

    @discord.ui.button(label="NSFW Mode", style=discord.ButtonStyle.danger)
    async def nsfw_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        set_user_mode(interaction.user.id, "nsfw")
        await interaction.response.send_message("🔞 Your mode has been set to **NSFW** (keep it respectful).", ephemeral=(interaction.guild is not None))

async def safe_defer(interaction: discord.Interaction):
    """Defer but swallow Cloudflare/429 hiccups gracefully."""
    try:
        await interaction.response.defer(thinking=False)
    except discord.HTTPException:
        pass

# Events
@bot.event
async def on_ready():
    global synced_once
    print(f"✅ Logged in as {bot.user} (id: {bot.user.id})")
    # Sync commands once
    if not synced_once:
        try:
            await tree.sync()
            print("Slash commands synced globally.")
            synced_once = True
        except Exception as e:
            print("Failed to sync global commands:", e)

# Slash Commands
@tree.command(name="truth", description="Get a Truth question with buttons.")
async def truth(interaction: discord.Interaction):
    q = get_question("truth", interaction.user.id)
    await respond(interaction, embed=make_embed("Truth", q, get_user_mode(interaction.user.id), interaction), view=QuestionView(interaction.user.id))

@tree.command(name="dare", description="Get a Dare question with buttons.")
async def dare(interaction: discord.Interaction):
    q = get_question("dare", interaction.user.id)
    await respond(interaction, embed=make_embed("Dare", q, get_user_mode(interaction.user.id), interaction), view=QuestionView(interaction.user.id))

@tree.command(name="wyr", description="Get a Would You Rather question with buttons.")
async def wyr(interaction: discord.Interaction):
    q = get_question("wyr", interaction.user.id)
    await respond(interaction, embed=make_embed("Would You Rather", q, get_user_mode(interaction.user.id), interaction), view=QuestionView(interaction.user.id))

@tree.command(name="ama", description="Get an AMA prompt with buttons.")
async def ama(interaction: discord.Interaction):
    q = get_question("ama", interaction.user.id)
    await respond(interaction, embed=make_embed("Ask Me Anything", q, get_user_mode(interaction.user.id), interaction), view=QuestionView(interaction.user.id))

@tree.command(name="mode", description="Choose SFW or NSFW mode (per user).")
async def mode(interaction: discord.Interaction):
    await respond(interaction, content="⚙️ Choose your mode:", view=ModeSelect(), ephemeral=(interaction.guild is not None))

@tree.command(name="help", description="Show available commands and usage.")
async def help_command(interaction: discord.Interaction):
    e = discord.Embed(title="📖 Truth or Dare Bot Help")
    e.add_field(
        name="🎮 Game Commands",
        value="/truth — Get a Truth question\n"
              "/dare — Get a Dare\n"
              "/wyr — Would You Rather\n"
              "/ama — Ask Me Anything\n",
        inline=False
    )
    e.add_field(
        name="⚙️ Settings",
        value="/mode — Choose between **SFW** or **NSFW** mode (per user, works anywhere)",
        inline=False
    )
    e.add_field(
        name="ℹ️ Info",
        value="Works in **servers and DMs**. Your personal mode decides the question pool.",
        inline=False
    )
    await respond(interaction, embed=e, ephemeral=(interaction.guild is not None))

# =========================
# Flask Web (pretty pink site 😏)
# =========================
app = Flask(__name__)

def human_uptime():
    delta = timedelta(seconds=int(time.time() - start_time))
    return str(delta)

def invite_url():
    if not CLIENT_ID:
        return "#"
    base = "https://discord.com/oauth2/authorize"
    scopes = "bot%20applications.commands"
    return f"{base}?client_id={CLIENT_ID}&permissions={PERMISSIONS}&scope={scopes}"

HERO_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="robots" content="noindex,nofollow">
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Truth or Dare Bot • Spicy Edition</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    .bg-horny { background: radial-gradient(1200px 600px at 10% 10%, #ffd1dc 0%, transparent 50%),
                          radial-gradient(1200px 600px at 90% 10%, #ffc0cb 0%, transparent 50%),
                          radial-gradient(1200px 800px at 50% 100%, #ff69b4 0%, #2a0820 70%); }
    .card { backdrop-filter: blur(10px); background-color: rgba(255,255,255,0.08); }
  </style>
</head>
<body class="min-h-screen text-pink-50 bg-horny">
  <div class="max-w-5xl mx-auto px-6 py-16">
    <header class="flex items-center justify-between">
      <h1 class="text-3xl md:text-4xl font-extrabold tracking-tight">💋 Truth or Dare • Spicy</h1>
      <a href="{invite}" class="px-4 py-2 rounded-2xl bg-pink-500 hover:bg-pink-400 transition font-semibold shadow">Invite</a>
    </header>

    <section class="mt-12 grid md:grid-cols-2 gap-6">
      <div class="card rounded-3xl p-6 shadow-xl">
        <h2 class="text-2xl font-bold mb-2">Always-On Status</h2>
        <p class="opacity-90">Uptime: <span class="font-semibold">{uptime}</span></p>
        <p class="opacity-90">Guilds: <span class="font-semibold">{guilds}</span></p>
        <p class="opacity-90">Latency: <span class="font-semibold">{latency} ms</span></p>
        <div class="mt-4 flex gap-3">
          <a class="px-4 py-2 rounded-xl bg-pink-600 hover:bg-pink-500 transition" href="/status">JSON Status</a>
          <a class="px-4 py-2 rounded-xl bg-pink-600 hover:bg-pink-500 transition" href="/commands">Commands</a>
        </div>
      </div>

      <div class="card rounded-3xl p-6 shadow-xl">
        <h2 class="text-2xl font-bold mb-2">How to Play</h2>
        <ul class="list-disc ml-6 space-y-2 opacity-95">
          <li>Use slash commands: <code>/truth</code>, <code>/dare</code>, <code>/wyr</code>, <code>/ama</code></li>
          <li>Pick your vibe with <code>/mode</code> (SFW / NSFW)</li>
          <li>Works in servers and DMs</li>
        </ul>
        <p class="mt-3 text-sm opacity-80">NSFW is playful-spicy only. Keep it respectful.</p>
      </div>
    </section>

    <section class="mt-12 card rounded-3xl p-6 shadow-xl">
      <h2 class="text-2xl font-bold mb-3">Try a Random Prompt</h2>
      <div class="flex flex-wrap gap-3">
        <a class="px-4 py-2 rounded-xl bg-fuchsia-600 hover:bg-fuchsia-500" href="/demo?c=truth">Truth</a>
        <a class="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500" href="/demo?c=dare">Dare</a>
        <a class="px-4 py-2 rounded-xl bg-pink-700 hover:bg-pink-600" href="/demo?c=wyr">Would You Rather</a>
        <a class="px-4 py-2 rounded-xl bg-purple-700 hover:bg-purple-600" href="/demo?c=ama">Ask Me Anything</a>
      </div>
      <p class="mt-4 opacity-95">{sample}</p>
    </section>

    <footer class="mt-16 opacity-70 text-sm">© {year} Spicy T/D Bot • Hosted on Render</footer>
  </div>
</body>
</html>
"""

COMMANDS_HTML = """
<!doctype html>
<html><head>
  <meta charset="utf-8" />
  <meta name="robots" content="noindex,nofollow">
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Commands</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="min-h-screen bg-pink-50 text-pink-950">
  <div class="max-w-3xl mx-auto p-6">
    <h1 class="text-3xl font-extrabold">✨ Commands</h1>
    <ul class="mt-6 space-y-3">
      <li><code class="bg-white px-2 py-1 rounded">/truth</code> — Get a Truth question</li>
      <li><code class="bg-white px-2 py-1 rounded">/dare</code> — Get a Dare</li>
      <li><code class="bg-white px-2 py-1 rounded">/wyr</code> — Would You Rather</li>
      <li><code class="bg-white px-2 py-1 rounded">/ama</code> — Ask Me Anything</li>
      <li><code class="bg-white px-2 py-1 rounded">/mode</code> — Choose SFW / NSFW</li>
    </ul>
    <a class="inline-block mt-8 px-4 py-2 rounded-xl bg-pink-600 text-white" href="/">← Back</a>
  </div>
</body></html>
"""

@app.route("/")
def home():
    # safe numbers if bot not ready
    try:
        guilds = len(bot.guilds)
    except Exception:
        guilds = 0
    try:
        latency_ms = int((bot.latency or 0) * 1000)
    except Exception:
        latency_ms = 0

    sample_pick = random.choice([
        get_question("truth", 0),
        get_question("dare", 0),
        get_question("wyr", 0),
        get_question("ama", 0),
    ])

    html = HERO_HTML.format(
        invite=invite_url(),
        uptime=human_uptime(),
        guilds=guilds,
        latency=latency_ms,
        sample=sample_pick,
        year=time.strftime("%Y"),
    )
    return html

@app.route("/commands")
def commands_page():
    return COMMANDS_HTML

@app.route("/status")
def status():
    try:
        guilds = len(bot.guilds)
    except Exception:
        guilds = 0
    latency = float(getattr(bot, "latency", 0) or 0)
    return jsonify({
        "ok": True,
        "uptime": human_uptime(),
        "uptime_seconds": int(time.time() - start_time),
        "guilds": guilds,
        "latency_ms": int(latency * 1000),
        "invite": invite_url(),
    })

@app.route("/invite")
def invite():
    url = invite_url()
    return redirect(url if url != "#" else url_for("home"))

@app.route("/demo")
def demo():
    c = request.args.get("c", "truth").lower()
    if c not in ("truth", "dare", "wyr", "ama"):
        c = "truth"
    q = get_question(c, 0)
    return f"<pre style='font-family:ui-monospace,monospace'>{c.upper()}: {q}</pre><p><a href='/'>Back</a></p>"

@app.route("/healthz")
def healthz():
    return "ok", 200

# =========================
# Run both (Render: Web Service)
# =========================
def run_web():
    # Flask must bind to 0.0.0.0 and $PORT for Render
    app.run(host=HOST, port=PORT)

def run_bot():
    # Note: If Render’s IP gets a temporary Cloudflare 429 from Discord, it clears by itself.
    # We avoid spamming login attempts.
    bot.run(TOKEN)

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    run_bot()
