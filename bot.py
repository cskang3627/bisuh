import discord
from discord.ext import commands
import json

# config stores prefix, token
with open("config.json") as f:
    data = json.load(f)
TOK = data["token"]
PRE = data["prefix"]

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