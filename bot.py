import discord
from discord.ext import commands
import json
import psycopg2




# config stores prefix, token
with open("config.json") as f:
    scrt = json.load(f)

TOK = scrt["token"]
PRE = scrt["prefix"]
PGPW = scrt["pgpw"]

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


'''
TO DO:
-- user READ
!today
!thisweek
!nextweek
!thismonth
!nextmonth
-- user CREAETE UPDATE DELETE
!new name date time location
!change name date time location (1 or more)
!delete name 
!rsvp name
!describe name

-- SQL Database
events
- name: str
- date: date
- time: time
- location: ?
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

@bot.command()
async def new(ctx, name, date, time, location):
    await ctx.send("%s: %s, %s, %s has been created!" %(name,date,time,location))
    
'''
#usecase: !cool bot => bot is cool, !cool name => name is not cool
@bot.group()
async def cool(ctx):
    """Says if a user is cool.

    In reality this just checks if a subcommand is being invoked.
    """
    if ctx.invoked_subcommand is None:
        await ctx.send(f'No, {ctx.subcommand_passed} is not cool')


@cool.command(name='bot')
async def _bot(ctx):
    """Is the bot cool?"""
    await ctx.send('Yes, the bot is cool.')
'''

bot.run(TOK)