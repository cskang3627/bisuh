import discord
from discord import app_commands
from discord.ext import commands
from dateparser import parse
from datetime import datetime
import json
import asyncpg

# TODO consider .env instead of json
# config stores prefix, token
with open("config.json") as f:
    scrt = json.load(f)

TOK = scrt["token"]
PGPW = scrt["pgpw"]

#POSTGRESQL
'''


cur.execute(""" CREATE TABLE IF NOT EXISTS events(
            event_id SERIAL PRIMARY KEY,
            event_name VARCHAR(255),
            date DATE,
            start_time TIME,
            end_time TIME, 
            server_id VARCHAR(255)
            
);
 """)

cur.execute(""" INSERT INTO person (event_id, event_name, date, start_time, end_time, server_id) VALUES
            (1, 'Chance', 26, 'm'),
            (2, 'Wen', 22, 'f')
 """)

conn.commit()
cur.close()
conn.close()
'''

# TO CHANGE: check intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

#bot
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


'''
TODO:
1. check if created event is later than current time
2. check if dup exists (name okay, time not okay)
3. display as embeded prompt for readiblity
4. emoji for rsvp
5. pull data: 
    user ID
    server ID
6. generate eventID (auto incrememt from sql)


'''
@bot.tree.command(name="create", description="create new event")
async def create(interaction: discord.Interaction, name:str, when:str, duration:str = '0 hour', location:str = '' ):
   
    #TODO: try catch for parse returning none
    when_parsed = parse(when, settings = {'PREFER_DATES_FROM':'future'})
    end_parsed = parse(duration, settings =  {'RELATIVE_BASE':when_parsed, 'PREFER_DATES_FROM':'future'})
    when_unix = int(when_parsed.timestamp())
    end_unix = int(end_parsed.timestamp())
    print(when_parsed)
    print(end_parsed)
    '''
    date = parse(date, settings=setting).strftime('%Y-%m-%d')
    start_time = parse(start_time, settings=setting).strftime('%H:%M')
    end_time = parse(end_time, settings=setting).strftime('%H:%M')
    '''
    await bot.pg_conn.execute(""" INSERT INTO events(event_name, start_date, end_date, guild_id, creator_id ) VALUES ($1,$2,$3,$4,$5)""",
                              name, when_parsed, end_parsed, interaction.guild_id, interaction.user.id)
    await interaction.response.send_message(content = f"Event {name}: <t:{when_unix}:F> ~ <t:{end_unix}:F> has been created!")


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

