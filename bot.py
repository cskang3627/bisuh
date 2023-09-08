import discord
from discord import app_commands
from discord.ext import commands
from dateparser import parse
from datetime import datetime
import json
import asyncpg
import asyncio
import pytz

# TODO consider .env instead of json
with open("config.json") as f:
    scrt = json.load(f)

TOK = scrt["token"]
PGPW = scrt["pgpw"]

# TODO: check intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

async def pg_pool():
    bot.pg_conn = await asyncpg.create_pool(host = "localhost", port = 5432, user = "postgres", password = PGPW, database = "postgres")
    await bot.pg_conn.execute(""" CREATE TABLE IF NOT EXISTS events(
            event_id SERIAL PRIMARY KEY,
            event_name VARCHAR(255),
            start_date INTEGER,
            end_date INTEGER,
            event_loc VARCHAR(255),
            event_note VARCHAR(255), 
            guild_id BIGINT,
            creator_id BIGINT); """)
    
# TODO: change db pool creation 
@bot.event
async def on_ready():
    await pg_pool() 
    print('db connected')
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')
    await bot.tree.sync()

@bot.event
async def on_guild_join(guild):
    channels = guild.text_channels
    if 'events-by-bisuh' not in channels:
        await guild.create_text_channel('events-by-bisuh')

@bot.tree.command(name="create", description="Create new event. Timezone is set to server's if not specified.")
async def create(interaction: discord.Interaction, name:str, when:str,
                 duration:str = '0 hour', timezone:str = '', location:str = '', note:str = ''):
    # input length check
    to_check = {'Name': name}
    if location:
        to_check['Location'] = location
    if note:
        to_check['Note'] = note
    for field, value in to_check.items():
        if len(value) > 255:
            embed = discord.Embed(
                title=f'Error: {field} Is Too Long',
                description=f"The {field.lower()} of the event is too long.",
                color=discord.Color.red()
                )
            await interaction.response.send_message(embeds=[embed])
            return
    # input timezone check
    if timezone and timezone not in pytz.all_timezones:
        embed = discord.Embed(
            title = 'Error: Invalid Timezone',
            description='The timezone you have entered is invalid.',
            color=discord.Color.red()
        )
        await interaction.response.send_message(embeds=[embed])
        return
    # same name event is limited to 5 creations
    event_count = await bot.pg_conn.fetchval("""SELECT COUNT(*) FROM events WHERE event_name = $1 AND guild_id = $2""",
                                             name, interaction.guild_id)
    if event_count >= 5:
        embed = discord.Embed(
            title='Error: Event Name Used Too Often',
            description="This event name has been used too many times.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embeds=[embed])
        return
    # parse given event time info
    loc_tz = datetime.now().astimezone().tzinfo.tzname(None)
    timezone = timezone or loc_tz
    try:
        when_parsed = parse(when, settings={'PREFER_DATES_FROM': 'future', 'TIMEZONE': timezone, 'TO_TIMEZONE': loc_tz})
        if when_parsed is None:
            raise ValueError("Failed to parse when.")
        
        end_parsed = parse(duration, settings={'RELATIVE_BASE': when_parsed, 'PREFER_DATES_FROM': 'future'})
        if end_parsed is None:
            raise ValueError("Failed to parse duration.")
    # parse error handle        
    except ValueError as e:
        embed = discord.Embed(
            title='Error: Parsing Failed',
            description=str(e),
            color=discord.Color.red()
        )
        await interaction.response.send_message(embeds=[embed])
        return
    # db insert
    when_unix, end_unix = int(when_parsed.timestamp()), int(end_parsed.timestamp())
    await bot.pg_conn.execute("""INSERT INTO events(event_name, start_date, end_date, event_loc, event_note, guild_id, creator_id)
                                 VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                              name, when_unix, end_unix, location, note, interaction.guild_id, interaction.user.id)

    embed = discord.Embed(
        title='Event Created',
        description=f"Event {name}: <t:{when_unix}:F> ~ <t:{end_unix}:F> has been created!",
        color=discord.Color.green()
    )
    await interaction.response.send_message("creating event...", ephemeral=True)

    msg = await interaction.followup.send(embeds=[embed])
    await msg.add_reaction('👍')
    await msg.add_reaction('👎')

@bot.tree.command(name="delete", description="Delete an existing event by its name.")
async def delete(interaction: discord.Interaction, name: str):
    # db lookup
    records = await bot.pg_conn.fetch("SELECT event_id, start_date, end_date, creator_id FROM events WHERE event_name = $1 AND guild_id = $2",
                                      name, interaction.guild_id)
    # no data
    if len(records) == 0:
        await interaction.response.send_message(content="No events found.")
        return
    # invalid user
    if not (interaction.user.id == records[0]['creator_id'] or interaction.user.guild_permissions.administrator):
        await interaction.response.send_message(content="Only the creator and administrator can delete.")
        return
    # sole data
    if len(records) == 1:
        await bot.pg_conn.execute("DELETE FROM events WHERE event_id = $1", records[0]['event_id'])
        await interaction.response.send_message(content=f"Event {name} has been deleted.")
        return
    
    # multi-name handle
    embed = discord.Embed(title=f"Multiple events found with the name {name}", description="Please choose one to delete:")
    for i, record in enumerate(records):
        embed.add_field(name=f"{i+1}", value=f"Event on <t:{record['start_date']}:F> ~ <t:{record['end_date']}:F>", inline=False)
        
    await interaction.response.send_message("generating delete options...", ephemeral=True)
    message = await interaction.followup.send(embeds=[embed])
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"] 
    for i in range(len(records)):
        await message.add_reaction(emojis[i])
    # check to pass in for wait
    def check(reaction, user):
        return user == interaction.user and str(reaction.emoji) in emojis

    try:
        reaction, user = await bot.wait_for('reaction_add', timeout=60.0, check=check)
    except asyncio.TimeoutError:
        await interaction.followup.send(content='Time ran out. No events were deleted.')
        return
    index_to_delete = emojis.index(str(reaction.emoji))
    await bot.pg_conn.execute("DELETE FROM events WHERE event_id = $1", records[index_to_delete]['event_id'])
    embed = discord.Embed(
        title='Event Deleted',
        description=f"Event {name}: <t:{records[index_to_delete]['start_date']}:F> ~ <t:{records[index_to_delete]['end_date']}:F> has been deleted!",
        color=discord.Color.green()
    )
    await interaction.followup.send(embeds=[embed])

"""
@bot.command()
async def show(ctx, subcom):
    match subcom:
        case today:
        case thisweek:
        case nextweek:
        case thismonth:
        case all:
        case dup:
        case _:
             
"""
bot.run(TOK)

