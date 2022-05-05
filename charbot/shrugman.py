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
"""Shrugman minigame."""
import datetime
import random
from enum import Enum
from typing import Final

import discord
from discord import app_commands, ui
from discord.ext import commands
from discord.utils import utcnow

from main import CBot

ALLOWED_ROLES: Final = (
    337743478190637077,
    685331877057658888,
    969629622453039104,
    969629628249563166,
    969629632028614699,
    969628342733119518,
    969627321239760967,
)

CHANNEL_ID: Final[int] = 969972085445238784

MESSAGE: Final = "You must be at least level 5 to participate in the giveaways system and be in <#969972085445238784>."

FailStates = Enum(
    "FailStates",
    r"<:KHattip:896043110717608009> `¯` `¯\` `¯\_` `¯\_(` `¯\_(ツ` `¯\_(ツ)` `¯\_(ツ)_` `¯\_(ツ)_/` `¯\_(ツ)_/¯`",
    start=0,
)

with open("hangman_words.csv") as f:
    __words__ = [word.replace("\n", "") for word in f.readlines()]

__valid_guesses__ = (
    "a",
    "b",
    "c",
    "d",
    "e",
    "f",
    "g",
    "h",
    "i",
    "j",
    "k",
    "l",
    "m",
    "n",
    "o",
    "p",
    "q",
    "r",
    "s",
    "t",
    "u",
    "v",
    "w",
    "x",
    "y",
    "z",
)


class ShrugmanGame(ui.View):
    """View subclass that represents a game of shrugman.

    Parameters
    ----------
    bot : CBot
        The bot instance.
    author : discord.Member
        The member that invoked the command.
    word : str
        The word to guess.
    fail_enum : enum = FailStates
        The enum to use for the fail state.

    Attributes
    ----------
    bot : CBot
        The bot instance.
    author : discord.Member
        The author of the command.
    word : str
        The word to guess.
    fail_enum : enum = FailStates
        The enum to use for the fail state.
    guess_count : int
        The number of guesses the player has made.
    guesses : list[str]
        The list of guesses the player has made.
    mistakes : int
        The number of mistakes the player has made.
    dead : bool
        Whether the player is dead.
    guess_word_list : list[str]
        The word to guess represented as a list of characters, with hyphens replacing unguessed letters.
    length : int
        The length of the word to guess.
    start_time : datetime.datetime
        The time the game started. Timzone aware.
    """

    def __init__(self, bot: CBot, author: discord.Member, word: str, *, fail_enum=FailStates):
        super().__init__(timeout=600)
        self.bot = bot
        self.author = author
        self.word = word or random.choice(__words__)
        self.fail_enum = fail_enum
        self.guess_count = 0
        self.guesses: list[str] = []
        self.mistakes = 0
        self.dead = False
        self.guess_word_list = ["-" for _ in self.word]
        self.length = len(word)
        self.start_time = utcnow()

    # noinspection PyUnusedLocal
    @ui.button(label="Guess", style=discord.ButtonStyle.success)
    async def guess_button(self, interaction: discord.Interaction, button: ui.Button):  # skipcq: PYL-W0613
        """Guess a letter.

        If the letter is in the word, it will be added to the right spots in the guess word list.

        Parameters
        ----------
        interaction : discord.Interaction
            The interaction object.
        button : ui.Button
            The button that was pressed.
        """
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Only the invoker of the game can guess.", ephemeral=True)
            return
        if self.dead:
            await interaction.response.send_message("You're dead, you can't guess anymore.", ephemeral=True)
            await self.disable()
            message = interaction.message
            assert isinstance(message, discord.Message)  # skipcq: BAN-B101
            await message.edit(view=self)
            return
        await interaction.response.send_modal(GuessModal(self))

    # noinspection PyUnusedLocal,DuplicatedCode
    @ui.button(label="Stop", style=discord.ButtonStyle.danger)
    async def stop_button(self, interaction: discord.Interaction, button: ui.Button):  # skipcq: PYL-W0613
        """Stop the game.

        This will also disable the buttons.

        Parameters
        ----------
        interaction : discord.Interaction
            The interaction object.
        button : ui.Button
            The button that was pressed.
        """
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Only the invoker of the game can stop it.", ephemeral=True)
            return
        await self.disable()
        embed = discord.Embed(
            title="**Cancelled** Shrugman",
            description=f"Guess the word: `{''.join(self.guess_word_list)}`",
            color=discord.Color.dark_purple(),
        )
        embed.set_footer(text="Type /shrugman to play")
        embed.set_author(name=self.author.display_name, icon_url=self.author.display_avatar.url)
        embed.add_field(name="Shrugman", value=self.fail_enum(self.mistakes).name, inline=True)
        embed.add_field(name="Guesses", value=f"{self.guess_count}", inline=True)
        embed.add_field(name="Mistakes", value=f"{self.mistakes}", inline=True)
        embed.add_field(name="Word", value=f"{self.word}", inline=True)
        embed.add_field(name="Guesses", value=f"{', '.join(self.guesses) or 'None'}", inline=True)
        time_taken = utcnow().replace(microsecond=0) - self.start_time.replace(microsecond=0)
        embed.add_field(name="Time Taken", value=f"{time_taken}", inline=True)
        if (utcnow() - self.start_time) > datetime.timedelta(seconds=60) and self.guess_count > 5:
            embed.add_field(name="Time Taken", value=f"{time_taken}", inline=True)
            points = await self.bot.give_game_points(self.author.id, 2, 0)
            embed.add_field(
                name="Reputation gained",
                value="2 Reputation" if points == 2 else f"{points} Reputation (Daily Cap Hit)",
                inline=True,
            )
        else:
            embed.add_field(name="Reputation gained", value="0 Reputation", inline=True)
        await interaction.response.edit_message(embed=embed, view=self)

    # noinspection DuplicatedCode
    async def on_timeout(self) -> None:
        """Call when the view times out.

        This will disable the buttons.
        """
        await self.disable()
        embed = discord.Embed(
            title="**Timed out** Shrugman",
            description=f"Guess the word: `{''.join(self.guess_word_list)}`",
            color=discord.Color.dark_purple(),
        )
        embed.set_footer(text="Type /shrugman to play")
        embed.set_author(name=self.author.display_name, icon_url=self.author.display_avatar.url)
        embed.add_field(name="Shrugman", value=self.fail_enum(self.mistakes).name, inline=True)
        embed.add_field(name="Guesses", value=f"{self.guess_count}", inline=True)
        embed.add_field(name="Mistakes", value=f"{self.mistakes}", inline=True)
        embed.add_field(name="Word", value=f"{self.word}", inline=True)
        embed.add_field(name="Guesses", value=f"{', '.join(self.guesses) or 'None'}", inline=True)
        time_taken = utcnow().replace(microsecond=0) - self.start_time.replace(microsecond=0)
        embed.add_field(name="Time Taken", value=f"{time_taken}", inline=True)
        try:
            await self.author.send("Your game timed out", embed=embed)
        except discord.DiscordException:
            pass

    async def disable(self):
        """Disable the buttons and stop the view."""
        self.guess_button.disabled = True
        self.stop_button.disabled = True
        self.stop()


class GuessModal(ui.Modal, title="Shrugman Guess"):
    """Letter input for shrugman game.

    This modal is used to input a letter for the game.

    Parameters
    ----------
    game : ShrugmanGame
        The game to use for the modal.

    Attributes
    ----------
    game: ShrugmanGame
        The game the modal is used for.
    """

    guess = ui.TextInput(
        label="What letter are you guessing?",
        style=discord.TextStyle.short,
        required=True,
        min_length=0,
        max_length=1,
    )

    def __init__(self, game: ShrugmanGame):
        super().__init__(title="Shrugman Guess")
        self.game = game

    # noinspection DuplicatedCode
    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Invoke when the user submits the modal.

        Parameters
        ----------
        interaction : discord.Interaction
            The interaction object.
        """
        _value = self.guess.value
        assert isinstance(_value, str)  # skipcq: BAN-B101
        value: str = _value.lower()
        if value not in __valid_guesses__:
            await interaction.response.send_message("Invalid guess.", ephemeral=True)
            return
        if value in self.game.guesses:
            await interaction.response.send_message(f"You already guessed {value}.", ephemeral=True)
            return
        await interaction.response.defer()
        self.game.guesses.append(value)
        self.game.guess_count += 1
        if value not in self.game.word:
            self.game.mistakes += 1
        if self.game.mistakes >= len(self.game.fail_enum) - 1:
            self.game.dead = True
            await self.game.disable()
            embed = discord.Embed(
                title="**Failed** Shrugman",
                description=f"You got: `{''.join(self.game.guess_word_list)}`",
                color=discord.Color.red(),
            )
            embed.set_footer(text="Type /shrugman to play")
            embed.set_author(name=self.game.author.display_name, icon_url=self.game.author.display_avatar.url)
            embed.add_field(
                name="Shrugman",
                value=self.game.fail_enum(min(len(self.game.fail_enum) - 1, self.game.mistakes)).name,
                inline=True,
            )
            embed.add_field(name="Guesses", value=f"{self.game.guess_count}", inline=True)
            embed.add_field(name="Mistakes", value=f"{self.game.mistakes}", inline=True)
            embed.add_field(name="Word", value=f"{self.game.word}", inline=True)
            embed.add_field(name="Guesses", value=f"{', '.join(self.game.guesses)}", inline=True)
            time_taken = utcnow().replace(microsecond=0) - self.game.start_time.replace(microsecond=0)
            embed.add_field(name="Time Taken", value=f"{time_taken}", inline=True)
            points = await self.game.bot.give_game_points(self.game.author.id, 2, 0)
            embed.add_field(
                name="Reputation gained",
                value="2 Reputation" if points == 2 else f"{points} Reputation (Daily Cap Hit)",
                inline=True,
            )
            await interaction.edit_original_message(embed=embed, view=self.game)
            return
        for i, letter in enumerate(self.game.word):
            if letter == value:
                self.game.guess_word_list[i] = letter
        embed = discord.Embed(
            title=f"{f'**{self.game.author.display_name} Won!!!**  ' if '-' not in self.game.guess_word_list else ''}"
            f"Shrugman",
            description=f"{'Congrats!' if '-' not in self.game.guess_word_list else 'Guess the word:'}"
            f" `{''.join(self.game.guess_word_list)}`",
            color=discord.Color.green() if "-" not in self.game.guess_word_list else discord.Color.red(),
        )
        embed.set_footer(text=f"Type /shrugman to play {'again' if '-' not in self.game.guess_word_list else ''}")
        embed.set_author(name=self.game.author.display_name, icon_url=self.game.author.display_avatar.url)
        embed.add_field(
            name="Shrugman",
            value=self.game.fail_enum(min(len(self.game.fail_enum) - 1, self.game.mistakes)).name,
            inline=True,
        )
        embed.add_field(name="Guesses", value=f"{self.game.guess_count}", inline=True)
        embed.add_field(name="Mistakes", value=f"{self.game.mistakes}", inline=True)
        embed.add_field(
            name="Word",
            value=f"{self.game.word if '-' not in self.game.guess_word_list else '???'}",
            inline=True,
        )
        embed.add_field(name="Guesses", value=f"{', '.join(self.game.guesses)}", inline=True)
        if "-" not in self.game.guess_word_list:
            await self.game.disable()
            time_taken = utcnow().replace(microsecond=0) - self.game.start_time.replace(microsecond=0)
            embed.add_field(name="Time Taken", value=f"{time_taken}", inline=True)
            bonus = -(-((len(self.game.fail_enum) - 1) - self.game.mistakes) // 2)
            points = await self.game.bot.give_game_points(self.game.author.id, 2, bonus)
            embed.add_field(
                name="Reputation gained",
                value=f"{points} Reputation" if points == (2 + bonus) else f"{points} Reputation (Daily Cap Hit)",
                inline=True,
            )
        await interaction.edit_original_message(embed=embed, view=self.game)


class Shrugman(commands.Cog):
    """Shrugman minigame cog.

    This cog contains the commands for the shrugman minigame.

    Parameters
    ----------
    bot : CBot
        The bot instance.

    Attributes
    ----------
    bot : CBot
        The bot instance.
    """

    def __init__(self, bot: CBot):
        self.bot = bot

    @app_commands.command(name="shrugman", description="Play the shrugman minigame. (Hangman clone)")
    @app_commands.guilds(225345178955808768)
    async def shrugman(self, interaction: discord.Interaction) -> None:
        """Play a game of Shrugman.

        This game is a hangman-like game.

        The game is played by guessing letters.

        The game ends when the word is guessed or the player runs out of guesses.

        The game is won by guessing the word.

        The game is lost by running out of guesses.

        Parameters
        ----------
        interaction: discord.Interaction
            The interaction of the command.
        """
        user = interaction.user
        assert isinstance(user, discord.Member)  # skipcq: BAN-B101
        if not any(role.id in ALLOWED_ROLES for role in user.roles) or interaction.channel_id != CHANNEL_ID:
            await interaction.response.send_message(MESSAGE, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        word = random.choice(__words__)
        embed = discord.Embed(
            title="Shrugman",
            description=f"Guess the word: `{''.join(['-' for _ in word])}`",
            color=discord.Color.dark_purple(),
        )
        embed.set_footer(text="Type /shrugman to play")
        user = interaction.user
        assert isinstance(user, discord.Member)  # skipcq: BAN-B101
        embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
        user = interaction.user
        assert isinstance(user, discord.Member)  # skipcq: BAN-B101
        view = ShrugmanGame(self.bot, user, word)
        await interaction.followup.send(embed=embed, view=view)


async def setup(bot: CBot):
    """Load the shrugman cog.

    Parameters
    ----------
    bot : CBot
        The bot object
    """
    await bot.add_cog(Shrugman(bot), guild=discord.Object(id=225345178955808768), override=True)
