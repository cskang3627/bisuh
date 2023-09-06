import discord
from discord import app_commands
from discord.ext import commands
from dateparser import parse
from datetime import datetime
import json
import asyncpg
import asyncio

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
            start_date TIMESTAMP,
            end_date TIMESTAMP, 
            guild_id BIGINT,
            creator_id BIGINT); """)

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

'''
-- user READ
!show +
 - today
 - thisweek
 - nextweek
 - thismonth
 - all
 - dup
 - rsvp event_name 
-- user CREAETE UPDATE DELETE
!change name date stime etime location (1 or more)
!delete name 
!describe name
'''



@bot.tree.command(name="create", description="Create new event. Timezone is set to UTC if not specified.")
async def create(interaction: discord.Interaction, name:str, when:str, 
                 duration:str = '0 hour', timezone:str = 'UTC', location:str = '', description:str = ''):
   
    try:
        when_parsed = parse(when, settings = {'PREFER_DATES_FROM':'future', 'TIMEZONE' : timezone})
        end_parsed = parse(duration, settings =  {'RELATIVE_BASE':when_parsed, 'PREFER_DATES_FROM':'future', 'TIMEZONE': timezone})
    except:
        await interaction.response.send_message(content = "Failed to parse when or duration.")
        return

    if when_parsed is None or end_parsed is None: 
        await interaction.response.send_message(content = "Failed to parse when or duration.")
    if len(name) > 255:
        await interaction.response.send_message(content = "Name of the event is too long.")
        return
    
    when_unix = int(when_parsed.timestamp())
    end_unix = int(end_parsed.timestamp())
    await bot.pg_conn.execute(""" INSERT INTO events(event_name, start_date, end_date, guild_id, creator_id ) VALUES ($1,$2,$3,$4,$5)""",
                              name, when_parsed, end_parsed, interaction.guild_id, interaction.user.id)
    await interaction.response.send_message(content = f"Event {name}: <t:{when_unix}:F> ~ <t:{end_unix}:F> has been created!")

# TODO: limit same name up to 5 events, dup delete with 5 number emoji
@bot.tree.command(name="delete", description="Delete an existing event by its name.")
async def delete(interaction: discord.Interaction, name: str):

    records = await bot.pg_conn.fetch("SELECT event_id, start_date, end_date, creator_id FROM events WHERE event_name = $1 AND guild_id = $2",
                                      name, interaction.guild_id)

    if len(records) == 0:
        await interaction.response.send_message(content="No events found.")
        return

    if not (interaction.user.id == records[0]['creator_id'] or interaction.user.guild_permissions.administrator):
        await interaction.response.send_message(content="Only the creator and administrator can delete.")
        return

    if len(records) == 1:
        await bot.pg_conn.execute("DELETE FROM events WHERE event_id = $1", records[0]['event_id'])
        await interaction.response.send_message(content=f"Event {name} has been deleted.")
        return

    # If multiple events, let the user choose
    options = []
    for i, record in enumerate(records):
        options.append(f"{i+1}: {name} on {record['start_date']} ~ {record['end_date']}")

    options_str = "\n".join(options)
    await interaction.response.send_message(content=f"Multiple events found with the name {name}. Please choose one to delete:\n{options_str}")

    def check(m):
        return m.author == interaction.user and m.content.isdigit() and 1 <= int(m.content) <= len(records)

    try:
        msg = await bot.wait_for('message', timeout=60.0, check=check)
    except asyncio.TimeoutError:
        await interaction.followup.send(content='Time ran out. No events were deleted.')
        return

    index_to_delete = int(msg.content) - 1
    await bot.pg_conn.execute("DELETE FROM events WHERE event_id = $1", records[index_to_delete]['event_id'])
    await interaction.followup.send(content=f"Event {name} on {records[index_to_delete]['start_date']} ~ {records[index_to_delete]['end_date']} has been deleted.")

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

