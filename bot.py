import os
import json
import random
from pathlib import Path
import threading

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from flask import Flask, render_template_string

# ---------- Setup ----------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

BASE = Path(__file__).parent
QUESTIONS_FILE = BASE / "questions.json"
SETTINGS_FILE = BASE / "settings.json"

DEFAULT_QUESTIONS = {
    "truth": {"sfw": [], "nsfw": []},
    "dare": {"sfw": [], "nsfw": []},
    "wyr": {"sfw": [], "nsfw": []},
    "ama": {"sfw": [], "nsfw": []},
}
DEFAULT_SETTINGS = {"user_modes": {}}


# ---------- JSON Helpers ----------
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
settings = load_json(SETTINGS_FILE, DEFAULT_SETTINGS)


# ---------- Helpers ----------
def get_user_mode(user_id: int) -> str:
    return settings.get("user_modes", {}).get(str(user_id), "sfw")


def set_user_mode(user_id: int, mode: str):
    settings.setdefault("user_modes", {})[str(user_id)] = mode
    save_json(SETTINGS_FILE, settings)


def get_question(category: str, user_id: int) -> str:
    mode = get_user_mode(user_id)
    pool = questions.get(category, {}).get(mode, [])
    if not pool:
        return f"No questions found for {category.upper()} ({mode.upper()}). Use /add to populate."
    return random.choice(pool)


def make_embed(title: str, content: str, mode: str, interaction: discord.Interaction) -> discord.Embed:
    e = discord.Embed(title=title, description=content, color=discord.Color.purple())
    loc = "DM" if interaction.guild is None else f"#{getattr(interaction.channel, 'name', 'channel')}"
    e.set_footer(text=f"{mode.upper()} • {loc}")
    return e


async def respond(interaction: discord.Interaction, *, content: str | None = None,
                  embed: discord.Embed | None = None, view=None, ephemeral: bool = False):
    ephemeral = bool(ephemeral and interaction.guild is not None)

    if interaction.response.is_done():
        await interaction.followup.send(content=content, embed=embed, view=view, ephemeral=ephemeral)
    else:
        await interaction.response.send_message(content=content, embed=embed, view=view, ephemeral=ephemeral)


# ---------- UI ----------
class QuestionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Truth", style=discord.ButtonStyle.success)
    async def truth_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        q = get_question("truth", interaction.user.id)
        await interaction.response.send_message(
            embed=make_embed("Truth", q, get_user_mode(interaction.user.id), interaction),
            view=QuestionView()
        )

    @discord.ui.button(label="Dare", style=discord.ButtonStyle.danger)
    async def dare_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        q = get_question("dare", interaction.user.id)
        await interaction.response.send_message(
            embed=make_embed("Dare", q, get_user_mode(interaction.user.id), interaction),
            view=QuestionView()
        )

    @discord.ui.button(label="Would You Rather", style=discord.ButtonStyle.primary)
    async def wyr_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        q = get_question("wyr", interaction.user.id)
        await interaction.response.send_message(
            embed=make_embed("Would You Rather", q, get_user_mode(interaction.user.id), interaction),
            view=QuestionView()
        )

    @discord.ui.button(label="Ask Me Anything", style=discord.ButtonStyle.secondary)
    async def ama_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        q = get_question("ama", interaction.user.id)
        await interaction.response.send_message(
            embed=make_embed("Ask Me Anything", q, get_user_mode(interaction.user.id), interaction),
            view=QuestionView()
        )


class ModeSelect(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="SFW Mode", style=discord.ButtonStyle.success)
    async def sfw_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        set_user_mode(interaction.user.id, "sfw")
        await interaction.response.send_message("✅ Your mode has been set to **SFW**.",
                                                ephemeral=(interaction.guild is not None))

    @discord.ui.button(label="NSFW Mode", style=discord.ButtonStyle.danger)
    async def nsfw_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        set_user_mode(interaction.user.id, "nsfw")
        await interaction.response.send_message("🔞 Your mode has been set to **NSFW**.",
                                                ephemeral=(interaction.guild is not None))


# ---------- Events ----------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (id: {bot.user.id})")
    try:
        await tree.sync()
        print("✅ Slash commands synced globally.")
    except Exception as e:
        print("❌ Failed to sync global commands:", e)

    # Register persistent views so buttons keep working after restart
    bot.add_view(QuestionView())
    bot.add_view(ModeSelect())


# ---------- Slash Commands ----------
@tree.command(name="truth", description="Get a Truth question with buttons.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def truth(interaction: discord.Interaction):
    q = get_question("truth", interaction.user.id)
    await respond(interaction, embed=make_embed("Truth", q, get_user_mode(interaction.user.id), interaction),
                  view=QuestionView())


@tree.command(name="dare", description="Get a Dare question with buttons.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def dare(interaction: discord.Interaction):
    q = get_question("dare", interaction.user.id)
    await respond(interaction, embed=make_embed("Dare", q, get_user_mode(interaction.user.id), interaction),
                  view=QuestionView())


@tree.command(name="wyr", description="Get a Would You Rather question with buttons.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def wyr(interaction: discord.Interaction):
    q = get_question("wyr", interaction.user.id)
    await respond(interaction, embed=make_embed("Would You Rather", q, get_user_mode(interaction.user.id), interaction),
                  view=QuestionView())


@tree.command(name="ama", description="Get an AMA prompt with buttons.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def ama(interaction: discord.Interaction):
    q = get_question("ama", interaction.user.id)
    await respond(interaction, embed=make_embed("Ask Me Anything", q, get_user_mode(interaction.user.id), interaction),
                  view=QuestionView())


@tree.command(name="mode", description="Choose SFW or NSFW mode (per user).")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def mode(interaction: discord.Interaction):
    await respond(interaction, content="⚙️ Choose your mode:", view=ModeSelect(),
                  ephemeral=(interaction.guild is not None))


@tree.command(name="help", description="Show available commands and usage.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def help_command(interaction: discord.Interaction):
    e = discord.Embed(title="📖 Truth or Dare Bot Help", color=discord.Color.magenta())
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
        value="/mode — Choose between **SFW** or **NSFW** mode (per user, works anywhere)\n"
              "/add — Add a new question (Admin)\n"
              "/remove — Remove a question (Admin)",
        inline=False
    )
    await respond(interaction, embed=e, ephemeral=(interaction.guild is not None))


# ---------- Admin Commands ----------
@tree.command(name="add", description="Add a new question (Admin only).")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def add_question(interaction: discord.Interaction, category: str, mode: str, *, question: str):
    if interaction.user.id != OWNER_ID:
        return await respond(interaction, content="❌ Only the bot owner can add questions.", ephemeral=True)

    if category not in questions or mode not in ["sfw", "nsfw"]:
        return await respond(interaction, content="⚠️ Invalid category or mode.", ephemeral=True)

    questions[category][mode].append(question)
    save_json(QUESTIONS_FILE, questions)
    await respond(interaction, content=f"✅ Added question to **{category.upper()} ({mode.upper()})**.")


@tree.command(name="remove", description="Remove a question (Admin only).")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def remove_question(interaction: discord.Interaction, category: str, mode: str, *, question: str):
    if interaction.user.id != OWNER_ID:
        return await respond(interaction, content="❌ Only the bot owner can remove questions.", ephemeral=True)

    if category not in questions or mode not in ["sfw", "nsfw"]:
        return await respond(interaction, content="⚠️ Invalid category or mode.", ephemeral=True)

    try:
        questions[category][mode].remove(question)
        save_json(QUESTIONS_FILE, questions)
        await respond(interaction, content=f"✅ Removed question from **{category.upper()} ({mode.upper()})**.")
    except ValueError:
        await respond(interaction, content="⚠️ Question not found.", ephemeral=True)


# ---------- Website ----------
app = Flask(__name__)

HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Horny Truth or Dare Bot</title>
    <style>
        body { background: linear-gradient(45deg, #ff1e56, #ffac41); color: white; font-family: Arial, sans-serif; text-align: center; padding: 50px;}
        h1 { font-size: 3em; margin-bottom: 10px; }
        h2 { margin-top: 40px; }
        .card { background: rgba(0,0,0,0.5); border-radius: 15px; padding: 20px; margin: 20px auto; max-width: 600px; }
        a.button { background: #fff; color: #ff1e56; padding: 12px 25px; border-radius: 10px; font-weight: bold; text-decoration: none; }
        a.button:hover { background: #ffac41; color: white; }
    </style>
</head>
<body>
    <h1>🔥 Horny Truth or Dare Bot 🔞</h1>
    <p>Spice up your Discord server with naughty truth, dares, WYR, and AMA!</p>
    
    <div class="card">
        <h2>📊 Status</h2>
        <p>Bot is currently <b>ONLINE ✅</b></p>
    </div>
    
    <div class="card">
        <h2>⚙️ Commands</h2>
        <p>/truth — Get a Truth question<br>
           /dare — Get a Dare<br>
           /wyr — Would You Rather<br>
           /ama — Ask Me Anything<br>
           /mode — Switch between SFW/NSFW<br>
           /add — Add question (Admin)<br>
           /remove — Remove question (Admin)</p>
    </div>
    
    <div class="card">
        <h2>✨ Invite the Bot</h2>
        <p><a class="button" href="https://discord.com/oauth2/authorize?client_id=1407985841963274334&permissions=2147485696&scope=bot%20applications.commands" target="_blank">Invite Now</a></p>
    </div>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_PAGE)

def run_web():
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)


# ---------- Entrypoint ----------
if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN not set. Put it in .env or environment variables.")

    threading.Thread(target=run_web).start()
    bot.run(TOKEN)
