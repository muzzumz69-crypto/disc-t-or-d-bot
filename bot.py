import os
import json
import random
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

# ---------- Setup ----------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True  # ✅ allow bot to handle DMs
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
    e = discord.Embed(title=title, description=content)
    loc = "DM" if interaction.guild is None else f"#{getattr(interaction.channel, 'name', 'channel')}"
    e.set_footer(text=f"{mode.upper()} • {loc}")
    return e


async def respond(interaction: discord.Interaction, *, content: str | None = None,
                  embed: discord.Embed | None = None, view=None, ephemeral: bool = False):
    # ⚡ Ephemeral not supported in DMs, only in guilds
    ephemeral = bool(ephemeral and interaction.guild is not None)

    if interaction.response.is_done():
        await interaction.followup.send(content=content, embed=embed, view=view, ephemeral=ephemeral)
    else:
        await interaction.response.send_message(content=content, embed=embed, view=view, ephemeral=ephemeral)


# ---------- UI (Buttons) ----------
class QuestionView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="Truth", style=discord.ButtonStyle.success)
    async def truth_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        q = get_question("truth", self.user_id)
        await interaction.response.defer()
        await interaction.channel.send(embed=make_embed("Truth", q, get_user_mode(self.user_id), interaction), view=QuestionView(self.user_id))

    @discord.ui.button(label="Dare", style=discord.ButtonStyle.danger)
    async def dare_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        q = get_question("dare", self.user_id)
        await interaction.response.defer()
        await interaction.channel.send(embed=make_embed("Dare", q, get_user_mode(self.user_id), interaction), view=QuestionView(self.user_id))

    @discord.ui.button(label="Would You Rather", style=discord.ButtonStyle.primary)
    async def wyr_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        q = get_question("wyr", self.user_id)
        await interaction.response.defer()
        await interaction.channel.send(embed=make_embed("Would You Rather", q, get_user_mode(self.user_id), interaction), view=QuestionView(self.user_id))

    @discord.ui.button(label="Ask Me Anything", style=discord.ButtonStyle.secondary)
    async def ama_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        q = get_question("ama", self.user_id)
        await interaction.response.defer()
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
        await interaction.response.send_message("🔞 Your mode has been set to **NSFW**.", ephemeral=(interaction.guild is not None))


# ---------- Events ----------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id: {bot.user.id})")
    try:
        await tree.sync()
        print("Slash commands synced globally.")
    except Exception as e:
        print("Failed to sync global commands:", e)


# ---------- Slash Commands ----------
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
        value="Questions depend **only on your personal mode**, not the channel type.\nWorks in **servers and DMs**.",
        inline=False
    )
    await respond(interaction, embed=e, ephemeral=(interaction.guild is not None))


# ---------- Entrypoint ----------
if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN not set. Put it in .env or environment variables.")
    bot.run(TOKEN)
