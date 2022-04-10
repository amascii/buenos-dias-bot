import os
import logging
import sys
from datetime import date

import boto3
import discord
from discord.ext import commands
from unidecode import unidecode
from botocore.exceptions import ClientError

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(
    command_prefix="'", description="Bot para traquear los buenos días", intents=intents
)


# Logging
formatter = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

consoleHandler = logging.StreamHandler(sys.stderr)
consoleHandler.setFormatter(formatter)
logger.addHandler(consoleHandler)

# Table
dynamodb = boto3.resource("dynamodb")
buenos_dias_log_table = dynamodb.Table("buenos_dias_log")
users_table = dynamodb.Table("bros")


@bot.event
async def on_ready():
    logger.info(f"We have logged in as {bot.user}")
    members = [m for g in bot.guilds for m in g.members if not m.bot]

    for m in members:
        try:
            user_id = str(m.id)
            users_table.put_item(
                Item={"user_id": user_id, "display_name": m.display_name, "points": 0},
                ConditionExpression="attribute_not_exists(user_id)",
            )
        # TODO check specific error
        except ClientError:
            logger.info(f"{user_id} already in table")


@bot.event
async def on_message(msg: discord.Message):
    if msg.author == bot.user:
        return

    content = unidecode(msg.content).lower()

    if "good morning" in content:
        await msg.add_reaction("❓")
        return
    elif content == "buenos dias":
        await msg.reply("Faltan bros")
        return
    elif content == "buenos dias bros":
        fecha = date.today().isoformat()
        resp = buenos_dias_log_table.get_item(Key={"fecha": fecha})

        # Initialize today's log
        if not (record := resp.get("Item")):
            record = {"fecha": fecha}
            buenos_dias_log_table.put_item(Item=record)

        user_id = str(msg.author.id)

        # Only count first buenos dias
        if user_id in record:
            await msg.add_reaction("❌")
            return

        # Update log and users table
        record.pop("fecha")
        place = len(record) + 1
        buenos_dias_log_table.update_item(
            Key={"fecha": fecha},
            UpdateExpression="SET #user_id = :place",
            ExpressionAttributeNames={"#user_id": user_id},
            ExpressionAttributeValues={":place": place},
        )
        users_table.update_item(
            Key={"user_id": user_id},
            UpdateExpression="SET #points = #points + :increase",
            ExpressionAttributeNames={"#points": "points"},
            ExpressionAttributeValues={":increase": 5 - place},
        )

        await msg.add_reaction("☀️")

    await bot.process_commands(msg)


@bot.command(description="Return server ranks")
async def rank(ctx):
    members = [m for g in bot.guilds for m in g.members if not m.bot]

    users = []
    for m in members:
        user_id = str(m.id)
        resp = users_table.get_item(Key={"user_id": user_id})
        if user := resp.get("Item"):
            users.append(user)

    sorted(users, key=lambda d: d["points"], reverse=True)

    msg = "`User" + " " * 17 + "Points`\n"
    for user in users:
        msg += f"`{user['display_name']:20}|{user['points']:>6}`\n"

    await ctx.send(msg)


if __name__ == "__main__":

    # Run with token
    bot.run(os.getenv("DISCORD_TOKEN"))
