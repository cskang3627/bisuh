import discord
from discord import app_commands
from discord.ext import commands
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
TO DO:
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
!new name date stime etime location
!change name date stime etime location (1 or more)
!delete name 
!rsvp name reminder_time
    - set guide for hour, min
!describe name
!vote eventname 
    - multiple events with same name gets voted depending on rsvp count (by score of yes : 1, maybe : 0.5)
-- SQL Database
events
- name: str
- date: date
- Stime: time
- Etime: time
- location: str
- requester: member id
- description: str
- yes: int
- no: int
- maybe: int

members
- name: str
- yes: array of event id
- no: array of event id 
- maybe: array of event id 
'''

@bot.tree.command(name="create", description="create new event")
async def create(interaction: discord.interactions, name:str, date:str, start_time:str, end_time:str, location:str):
    await interaction.response.send_message(content = "%s: %s, %s - %s, %s has been created!" %(name,date,start_time, end_time, location))

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

