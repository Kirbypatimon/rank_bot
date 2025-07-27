import discord
from discord.ext import commands
from discord import app_commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import json
import os
from datetime import datetime, timedelta
from collections import defaultdict

# --- Intents設定 ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# --- Bot定義 ---
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree
scheduler = AsyncIOScheduler()

# --- 環境変数 ---
TOKEN = os.environ.get("TOKEN")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "0"))  # 0だと送信エラーで気づける
COUNT_FILE = "count.json"

# --- データロード/保存 ---
def load_data():
    try:
        with open(COUNT_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_data(data):
    with open(COUNT_FILE, "w") as f:
        json.dump(data, f, indent=4)

# --- 範囲別データ取得 ---
def get_range_data(data, mode):
    result = defaultdict(int)
    now = datetime.now()

    for date_str, users in data.items():
        try:
            date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue

        include = (
            (mode == "day" and date.date() == now.date()) or
            (mode == "week" and now - timedelta(days=7) <= date <= now) or
            (mode == "month" and date.month == now.month and date.year == now.year) or
            (mode == "all")
        )

        if include:
            for user_id, count in users.items():
                result[user_id] += count

    return sorted(result.items(), key=lambda x: x[1], reverse=True)

# --- 起動時 ---
@bot.event
async def on_ready():
    await tree.sync()
    print(f"✅ Bot logged in as {bot.user}")
    scheduler.start()

# --- メッセージカウント ---
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    today = datetime.now().strftime("%Y-%m-%d")
    user_id = str(message.author.id)

    data = load_data()
    if today not in data:
        data[today] = {}

    data[today][user_id] = data[today].get(user_id, 0) + 1
    save_data(data)

    await bot.process_commands(message)

# --- 日次自動ランキング投稿（23:59） ---
@scheduler.scheduled_job("cron", hour=23, minute=59)
async def send_daily_ranking():
    data = load_data()
    today = datetime.now().strftime("%Y-%m-%d")
    if today not in data:
        return

    counts = data[today]
    sorted_counts = sorted(counts.items(), key=lambda x: x[1], reverse=True)

    ranking = f"📊 **{today} の発言ランキング** 📊\n"
    for i, (user_id, count) in enumerate(sorted_counts[:10], start=1):
        try:
            user = await bot.fetch_user(int(user_id))
            ranking += f"{i}. {user.display_name} - {count}回\n"
        except:
            ranking += f"{i}. <@{user_id}> - {count}回\n"

    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        await channel.send(ranking)

# --- /rank スラッシュコマンド ---
@tree.command(name="rank", description="発言数ランキングを表示します")
@app_commands.describe(range="表示する期間")
@app_commands.choices(range=[
    app_commands.Choice(name="今日", value="day"),
    app_commands.Choice(name="今週", value="week"),
    app_commands.Choice(name="今月", value="month"),
    app_commands.Choice(name="全期間", value="all")
])
async def rank(interaction: discord.Interaction, range: app_commands.Choice[str]):
    await interaction.response.defer()

    data = load_data()
    results = get_range_data(data, range.value)

    if not results:
        await interaction.followup.send("📭 データがありません。")
        return

    title_map = {
        "day": "📅 今日の発言ランキング",
        "week": "📈 今週の発言ランキング",
        "month": "📆 今月の発言ランキング",
        "all": "🏆 全期間の発言ランキング"
    }

    ranking = f"{title_map[range.value]}\n"
    for i, (user_id, count) in enumerate(results[:10], start=1):
        try:
            user = await bot.fetch_user(int(user_id))
            ranking += f"{i}. {user.display_name} - {count}回\n"
        except:
            ranking += f"{i}. <@{user_id}> - {count}回\n"

    await interaction.followup.send(ranking)

# --- 実行 ---
if __name__ == "__main__":
    if TOKEN is None:
        print("❌ TOKENが設定されていません")
    else:
        bot.run(TOKEN)
