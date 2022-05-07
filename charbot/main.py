# -*- coding: utf-8 -*-
#  ----------------------------------------------------------------------------
#  MIT License
#
# Copyright (c) 2022 Bluesy
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#  ----------------------------------------------------------------------------
"""Charbot discord bot."""
import asyncio
import datetime
import logging
import os
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from logging.handlers import RotatingFileHandler
from zoneinfo import ZoneInfo

import asyncpg
import discord
from discord.ext import commands
from discord.utils import MISSING
from dotenv import load_dotenv


__ZONEINFO__ = ZoneInfo("America/Detroit")
__TIME__ = (
    lambda: datetime.datetime.now(__ZONEINFO__).replace(microsecond=0, second=0, minute=0, hour=9)
    if datetime.datetime.now(__ZONEINFO__).replace(microsecond=0, second=0, minute=0, hour=9)
    <= datetime.datetime.now(__ZONEINFO__)
    else datetime.datetime.now(__ZONEINFO__).replace(microsecond=0, second=0, minute=0, hour=9)
    - datetime.timedelta(days=1)
)  # noqa: E731


class CBot(commands.Bot):
    """Custom bot class. extends discord.ext.commands.Bot.

    This class is used to create the bot instance.

    Attributes
    ----------
    executor : ThreadPoolExecutor
        The executor used to run IO tasks in the background, must be set after opening bot in an async manager,
         before connecting to the websocket.
    process_pool : ProcessPoolExecutor
        The executor used to run CPU tasks in the background, must be set after opening bot in an async manager,
         before connecting to the websocket.
    pool : asyncpg.Pool
        The connection pool to the database.
    program_logs : discord.Webhook
        The webhook to send program logs to.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.executor: ThreadPoolExecutor = MISSING
        self.process_pool: ProcessPoolExecutor = MISSING
        self.pool: asyncpg.Pool = MISSING
        self.program_logs: discord.Webhook = MISSING

    async def setup_hook(self):
        """Initialize hook for the bot.

        This is called when the bot is logged in but before connecting to the websocket.
        It provides an opportunity to perform some initialisation before the websocket is connected.
        Also loads the cogs, and prints who the bot is logged in as
        """
        print("Setup started")
        log_webhook = os.getenv("LOG_WEBHOOK")
        assert isinstance(log_webhook, str)  # skipcq: BAN-B101
        self.program_logs = await self.fetch_webhook(int(log_webhook))
        await self.load_extension("jishaku")
        await self.load_extension("admin")
        await self.load_extension("dice")
        await self.load_extension("events")
        await self.load_extension("gcal")
        await self.load_extension("giveaway")
        await self.load_extension("mod_support")
        await self.load_extension("primary")
        await self.load_extension("query")
        await self.load_extension("shrugman")
        await self.load_extension("sudoku")
        await self.load_extension("tictactoe")
        print("Extensions loaded")
        user = self.user
        assert isinstance(user, discord.ClientUser)  # skipcq: BAN-B101
        print(f"Logged in: {user.name}#{user.discriminator}")

    async def giveaway_user(self, user: int) -> None | asyncpg.Record:
        """Return an asyncpg entry for the user, joined on all 3 tables for tthe giveaway.

        Parameters
        ----------
        user : int
            The user id.

        Returns
        -------
        asyncpg.Record, optional
            The user record, or None if the user isn't in the DB.
        """
        return await self.pool.fetchrow(
            "SELECT users.id as id, points, b.bid as bid, dp.last_claim as daily, dp.last_particip_dt as "
            "particip_dt, dp.particip as particip, dp.won as won "
            "FROM users join bids b on users.id = b.id join daily_points dp on users.id = dp.id WHERE users.id = $1",
            user,
        )

    async def give_game_points(self, member: discord.Member, game: str, points: int, bonus: int = 0) -> int:
        """Give the user points.

        Parameters
        ----------
        member: discord.Member
            The member to give points to.
        game: str
            The game/program that was played.
        points : int
            The amount of points to give.
        bonus : int, optional
            The amount of points to add to the user's total points.

        Returns
        -------
        int
            The points gained
        """
        user_id = member.id
        clientuser = self.user
        assert isinstance(clientuser, discord.ClientUser)  # skipcq: BAN-B101
        user = await self.giveaway_user(user_id)
        if user is None:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO users (id, points) VALUES ($1, $2)",
                    user_id,
                    points + bonus,
                )
                await conn.execute("INSERT INTO bids (id, bid) VALUES ($1, 0)", user_id)
                await conn.execute(
                    "INSERT INTO daily_points (id, last_claim, last_particip_dt, particip, won)"
                    " VALUES ($1, $2, $3, $4, $5)",
                    user_id,
                    __TIME__() - datetime.timedelta(days=1),
                    __TIME__(),
                    points,
                    bonus,
                )
                await conn.execute("INSERT INTO bids (id, bid) VALUES ($1, 0)", user_id)
                await self.program_logs.send(
                    f"[NEW PARTICIPANT] {member.mention} gained {points + bonus} points for"
                    f" {game}, as {points} participated and {bonus} bonus points.",
                    username=clientuser.name,
                    avatar_url=clientuser.display_avatar.url,
                    allowed_mentions=discord.AllowedMentions(users=False, roles=False, everyone=False),
                )
                return points + bonus
        elif user["particip_dt"] < __TIME__():
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE daily_points SET last_particip_dt = $1, particip = $2, won = $3 WHERE id = $4",
                    __TIME__(),
                    points,
                    bonus,
                    user_id,
                )
                await conn.execute("UPDATE users SET points = points + $1 WHERE id = $2", points + bonus, user_id)
                await self.program_logs.send(
                    f"[FIRST OF DAY] {member.mention} gained {points + bonus} points for"
                    f" {game}, as {points} participated and {bonus} bonus points.",
                    username=clientuser.name,
                    avatar_url=clientuser.display_avatar.url,
                    allowed_mentions=discord.AllowedMentions(users=False, roles=False, everyone=False),
                )
        elif user["particip_dt"] == __TIME__():
            _points: int = MISSING
            _bonus: int = MISSING
            if user["particip"] + points > 10:
                real_points = 10 - user["particip"]
                _bonus = bonus
                _points = points
                bonus = -(-(real_points * bonus) // points)
                points = real_points
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE daily_points SET particip = particip + $1, won = won + $2 WHERE id = $3",
                    points,
                    bonus,
                    user_id,
                )
                await conn.execute("UPDATE users SET points = points + $1 WHERE id = $2", points + bonus, user_id)
                extra = (
                    f" out of a possible {_points + _bonus} points as {_points} participation and {_bonus} bonus points"
                    if _points is not MISSING
                    else ""
                )
                await self.program_logs.send(
                    f"{'[HIT CAP] ' if _points is not MISSING else ''}{member.mention} gained {points + bonus} points"
                    f" for {game}, as {points} participated and {bonus} bonus points"
                    f"{extra}.",
                    username=clientuser.name,
                    avatar_url=clientuser.display_avatar.url,
                    allowed_mentions=discord.AllowedMentions(users=False, roles=False, everyone=False),
                )
        else:
            await self.program_logs.send(
                f"[ERROR] {member.mention} gained 0 instead of {points + bonus} points for"
                f" {game}, as {points} participated and {bonus} bonus points because something went wrong.",
                username=clientuser.name,
                avatar_url=clientuser.display_avatar.url,
                allowed_mentions=discord.AllowedMentions(users=False, roles=False, everyone=False),
            )
            return 0
        return points + bonus


# noinspection PyBroadException
async def main():
    """Run charbot."""
    logger = logging.getLogger("discord")
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        filename="../CharBot.log",
        encoding="utf-8",
        mode="w",
        maxBytes=2000000,
        backupCount=10,
    )
    handler.setFormatter(logging.Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s"))
    logger.addHandler(handler)
    # Instantiate a Bot instance
    bot = CBot(
        command_prefix="!",
        owner_ids=[225344348903047168, 363095569515806722],
        case_insensitive=True,
        intents=discord.Intents.all(),
        help_command=None,
        activity=discord.Activity(type=discord.ActivityType.watching, name="over the server"),
    )

    load_dotenv()
    async with bot, asyncpg.create_pool(  # skipcq: PYL-E1701
        min_size=50,
        max_size=100,
        **{
            "host": os.getenv("HOST"),
            "user": os.getenv("DBUSER"),
            "password": os.getenv("PASSWORD"),
            "database": os.getenv("DATABASE"),
        },
    ) as pool:
        with ThreadPoolExecutor(max_workers=25) as executor, ProcessPoolExecutor(max_workers=5) as process_pool:
            bot.executor = executor
            bot.process_pool = process_pool
            bot.pool = pool
            token = os.getenv("TOKEN")
            assert isinstance(token, str)  # skipcq: BAN-B101
            await bot.start(token)


if __name__ == "__main__":
    if os.name != "nt":
        import uvloop

        uvloop.install()

    asyncio.run(main())
