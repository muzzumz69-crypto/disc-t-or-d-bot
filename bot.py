import os
import json
import random
import threading

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask

# ---------- Setup ----------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("TOKEN")
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# Your support server log channel ID (replace this!)
LOG_CHANNEL_ID = 123456789012345678  

# ---------- File Helpers ----------
QUESTIONS_FILE = "questions.json"
SETTINGS_FILE = "settings.json"


def load_json(file, default):
    if os.path.exists(file):
        with open(file, "r") as f:
            return json.load(f)
    return default


def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=4)


questions = load_json(QUESTIONS_FILE, {})
settings = load_json(SETTINGS_FILE, {})

# ---------- Context-aware Mode Handling ----------
def get_context_id(interaction: discord.Interaction) -> str:
    """Guild ID if in server, else user ID (for DM context)."""
    return str(interaction.guild.id) if interaction.guild else str(interaction.user.id)


def get_user_mode(user_id: int, context_id: str) -> str:
    """Get mode for a user in a specific context, default = sfw."""
    return settings.get("modes", {}).get(str(user_id), {}).get(context_id, "sfw")


def set_user_mode(user_id: int, context_id: str, mode: str):
    """Set mode for a user in a specific context (server/DM)."""
    settings.setdefault("modes", {}).setdefault(str(user_id), {})[context_id] = mode
    save_json(SETTINGS_FILE, settings)


def get_question(category: str, user_id: int, context_id: str) -> str:
    """Fetch question from correct category and mode."""
    mode = get_user_mode(user_id, context_id)
    pool = questions.get(category, {}).get(mode, [])
    if not pool:
        return f"No questions found for {category.upper()} ({mode.upper()}). Use /add to populate."
    return random.choice(pool)

# ---------- Views ----------
class QuestionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Truth", style=discord.ButtonStyle.success)
    async def truth_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        ctx = get_context_id(interaction)
        q = get_question("truth", interaction.user.id, ctx)
        await interaction.response.send_message(
            embed=make_embed("Truth", q, get_user_mode(interaction.user.id, ctx), interaction),
            view=QuestionView()
        )

    @discord.ui.button(label="Dare", style=discord.ButtonStyle.danger)
    async def dare_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        ctx = get_context_id(interaction)
        q = get_question("dare", interaction.user.id, ctx)
        await interaction.response.send_message(
            embed=make_embed("Dare", q, get_user_mode(interaction.user.id, ctx), interaction),
            view=QuestionView()
        )

    @discord.ui.button(label="Would You Rather", style=discord.ButtonStyle.primary)
    async def wyr_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        ctx = get_context_id(interaction)
        q = get_question("wyr", interaction.user.id, ctx)
        await interaction.response.send_message(
            embed=make_embed("Would You Rather", q, get_user_mode(interaction.user.id, ctx), interaction),
            view=QuestionView()
        )

    @discord.ui.button(label="Ask Me Anything", style=discord.ButtonStyle.secondary)
    async def ama_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        ctx = get_context_id(interaction)
        q = get_question("ama", interaction.user.id, ctx)
        await interaction.response.send_message(
            embed=make_embed("Ask Me Anything", q, get_user_mode(interaction.user.id, ctx), interaction),
            view=QuestionView()
        )


class ModeSelect(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="SFW Mode", style=discord.ButtonStyle.success)
    async def sfw_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        ctx = get_context_id(interaction)
        set_user_mode(interaction.user.id, ctx, "sfw")
        await interaction.response.send_message(
            "✅ Mode set to **SFW** (only in this chat).",
            ephemeral=True
        )

    @discord.ui.button(label="NSFW Mode", style=discord.ButtonStyle.danger)
    async def nsfw_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        ctx = get_context_id(interaction)
        set_user_mode(interaction.user.id, ctx, "nsfw")
        await interaction.response.send_message(
            "🔞 Mode set to **NSFW** (only in this chat).",
            ephemeral=True
        )

# ---------- Embeds ----------
def make_embed(category, question, mode, interaction):
    embed = discord.Embed(
        title=f"{category} ({mode.upper()})",
        description=question,
        color=discord.Color.random()
    )
    embed.set_footer(text=f"Requested by {interaction.user}")
    return embed

# ---------- Respond Helper ----------
async def respond(interaction, *args, **kwargs):
    try:
        await interaction.response.send_message(*args, **kwargs)
    except discord.InteractionResponded:
        await interaction.followup.send(*args, **kwargs)

# ---------- Logging Helper ----------
async def log_to_channel(embed: discord.Embed):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        try:
            await channel.send(embed=embed)
        except Exception as e:
            print(f"❌ Failed to send log: {e}")

@bot.event
async def on_app_command_completion(interaction: discord.Interaction, command):
    server_name = interaction.guild.name if interaction.guild else "DM"
    server_id = interaction.guild.id if interaction.guild else "N/A"

    embed = discord.Embed(
        title="📌 Command Used",
        color=discord.Color.blurple()
    )
    embed.add_field(name="User", value=f"{interaction.user} (ID: {interaction.user.id})", inline=False)
    embed.add_field(name="Command", value=f"`/{command.qualified_name}`", inline=False)
    embed.add_field(name="Server", value=f"{server_name} (ID: {server_id})", inline=False)

    await log_to_channel(embed)

# ---------- Slash Commands ----------
@tree.command(name="truth", description="Get a Truth question with buttons.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def truth(interaction: discord.Interaction):
    ctx = get_context_id(interaction)
    q = get_question("truth", interaction.user.id, ctx)
    await respond(interaction, embed=make_embed("Truth", q, get_user_mode(interaction.user.id, ctx), interaction),
                  view=QuestionView())


@tree.command(name="dare", description="Get a Dare question with buttons.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def dare(interaction: discord.Interaction):
    ctx = get_context_id(interaction)
    q = get_question("dare", interaction.user.id, ctx)
    await respond(interaction, embed=make_embed("Dare", q, get_user_mode(interaction.user.id, ctx), interaction),
                  view=QuestionView())


@tree.command(name="wyr", description="Get a Would You Rather question with buttons.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def wyr(interaction: discord.Interaction):
    ctx = get_context_id(interaction)
    q = get_question("wyr", interaction.user.id, ctx)
    await respond(interaction, embed=make_embed("Would You Rather", q, get_user_mode(interaction.user.id, ctx), interaction),
                  view=QuestionView())


@tree.command(name="ama", description="Get an Ask Me Anything question with buttons.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def ama(interaction: discord.Interaction):
    ctx = get_context_id(interaction)
    q = get_question("ama", interaction.user.id, ctx)
    await respond(interaction, embed=make_embed("Ask Me Anything", q, get_user_mode(interaction.user.id, ctx), interaction),
                  view=QuestionView())


@tree.command(name="mode", description="Switch between SFW and NSFW modes.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def mode(interaction: discord.Interaction):
    await respond(interaction, "⚙️ Select your mode:", view=ModeSelect())

# ---------- Bot Events ----------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (id: {bot.user.id})")
    try:
        await tree.sync()
        print("✅ Slash commands synced globally.")
    except Exception as e:
        print("❌ Failed to sync global commands:", e)

    # Register persistent views
    bot.add_view(QuestionView())
    bot.add_view(ModeSelect())

# ---------- Flask Web ----------
app = Flask(__name__)

@app.route('/')
def home():
    return "<h1>Bot is running!</h1>"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# ---------- Main ----------
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.run(TOKEN)
