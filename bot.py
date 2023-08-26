import discord
from discord import app_commands
from discord.ext import commands
from dateparser import parse
from datetime import datetime
import json
import psycopg2

# TODO consider .env instead of json
# config stores prefix, token
with open("config.json") as f:
    scrt = json.load(f)

TOK = scrt["token"]
PRE = scrt["prefix"]
PGPW = scrt["pgpw"]

#POSTGRESQL
'''
conn = psycopg2.connect(host="localhost", dbname="postgres", user="postgres", password = PGPW, port=5432)
cur = conn.cursor()

cur.execute(""" CREATE TABLE IF NOT EXISTS person(
            id INT PRIMARY KEY,
            name VARCHAR(255),
            age INT,
            gender CHAR
            
);
 """)

cur.execute(""" INSERT INTO person (id, name, age, gender) VALUES
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
bot = commands.Bot(command_prefix=PRE, intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')
    synched = await bot.tree.sync()

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
** USE server time -> find a way to dynamically display time
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
async def create(interaction: discord.interactions, name:str, date:str, start_time:str, end_time:str, location:str):
    currTime = datetime.now()
    date = parse(date, settings={'STRICT_PARSING': True}).strftime('%Y-%m-%d')
    start_time = parse(start_time).strftime('%H:%M:%S')
    end_time = parse(end_time).strftime('%H:%M:%S')
    print(interaction.created_at)
    await interaction.response.send_message(content = "%s: %s, %s - %s, %s has been created!  %s" %(name,date,start_time, end_time, location, currTime))

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

