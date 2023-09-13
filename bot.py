import json
import collections
import calendar
import asyncio
from datetime import datetime, timedelta

import discord
from discord.ext import commands
import asyncpg
import pytz
from dateparser import parse


# TODO consider .env instead of json
with open("config.json") as f:
    scrt = json.load(f)
TOK = scrt["token"]
PGPW = scrt["pgpw"]

# timezone data
tzones = collections.defaultdict(set)
abbrevs = collections.defaultdict(set)

for name in pytz.all_timezones:
    tzone = pytz.timezone(name)
    for utcoffset, dstoffset, tzabbrev in getattr(
            tzone, '_transition_info', [[None, None, datetime.now(tzone).tzname()]]):
        tzones[tzabbrev].add(name)
        abbrevs[name].add(tzabbrev)

# TODO: check intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

#db
async def pg_pool():
    bot.pg_conn = await asyncpg.create_pool(host = "localhost", port = 5432, user = "postgres", password = PGPW, database = "postgres")
    async with bot.pg_conn.acquire() as connection:
        async with connection.transaction():
            # events
            await bot.pg_conn.execute(""" 
                CREATE TABLE IF NOT EXISTS events(
                event_id SERIAL PRIMARY KEY,
                event_name VARCHAR(255),
                start_date TIMESTAMP,
                end_date TIMESTAMP,
                event_loc VARCHAR(255),
                event_note VARCHAR(255), 
                guild_id BIGINT,
                creator_id BIGINT,
                message_id BIGINT);""")
            # rsvp
            await bot.pg_conn.execute("""
                CREATE TABLE IF NOT EXISTS rsvp(
                rsvp_id SERIAL PRIMARY KEY,
                event_id INT REFERENCES events(event_id),
                user_id BIGINT,
                attend_confirm BOOLEAN,
                custom_notification INTERVAL,
                UNIQUE(event_id, user_id));""")
            # guild setting
            await bot.pg_conn.execute("""
                CREATE TABLE IF NOT EXISTS guild_settings(
                guild_id BIGINT PRIMARY KEY,
                timezone VARCHAR(50));""")
            # user setting
            await bot.pg_conn.execute("""
                CREATE TABLE IF NOT EXISTS user_settings(
                user_id BIGINT PRIMARY KEY,
                notification INTERVAL);""")
            #notificaiton 
            await bot.pg_conn.execute("""
                CREATE TABLE IF NOT EXISTS notifications(
                notification_id SERIAL PRIMARY KEY,
                event_id INT REFERENCES events(event_id),
                user_id BIGINT REFERENCES user_settings(user_id));""")
    
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

@bot.event
async def on_reaction_add(reaction, user):
    if user == bot.user:
        return

    message = reaction.message
    channel = message.channel
    guild = message.guild

    if not guild:
        return  

    if reaction.emoji not in ['✅', '❓', '⏰']:
        return  

    # Check if this message corresponds to an event (You might need more robust checks here)
    event_record = await bot.pg_conn.fetchrow("SELECT event_id FROM events WHERE guild_id = $1 AND message_id = $2", guild.id, message.id)

    if not event_record:
        return  # This message is not an event
    
    event_id = event_record['event_id']

    # Handle RSVP
    if reaction.emoji in ['✅', '❓']:
        is_confirmed = True if reaction.emoji == '✅' else False
        await bot.pg_conn.execute("""
            INSERT INTO rsvp(event_id, user_id, attend_confirm) VALUES ($1, $2, $3)
            ON CONFLICT (event_id, user_id) DO UPDATE SET attend_confirm = $3""",
            event_id, user.id, is_confirmed)

    # Handle notifications
    elif reaction.emoji == '⏰':
        one_hour = timedelta(hours=1)  
        await bot.pg_conn.execute("""
            INSERT INTO user_settings(user_id, notification)
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO NOTHING""",
            user.id, one_hour)
        
        await bot.pg_conn.execute("""
            INSERT INTO notifications(event_id, user_id) VALUES ($1, $2)
            """,
            event_id, user.id)

@bot.event
async def on_reaction_remove(reaction, user):
    if user == bot.user:
        return

    message = reaction.message
    channel = message.channel
    guild = message.guild

    if not guild:
        return  # Ignore DMs

    if reaction.emoji not in ['✅', '❓', '⏰']:
        return  # Ignore other emojis

    event_record = await bot.pg_conn.fetchrow("""
                                              SELECT event_id FROM events WHERE guild_id = $1 AND message_id = $2"""
                                              , guild.id, message.id)
    
    if not event_record:
        return  # This message is not an event

    event_id = event_record['event_id']

    # Handle RSVP removal
    if reaction.emoji in ['✅', '❓']:
        await bot.pg_conn.execute("""
                                  DELETE FROM rsvp WHERE event_id = $1 AND user_id = $2"""
                                  , event_id, user.id)

    # Handle notification removal
    elif reaction.emoji == '⏰':
        await bot.pg_conn.execute("""
                                  DELETE FROM notifications WHERE event_id = $1 AND user_id = $2"""
                                  , event_id, user.id)

# TODO: check if dup event has the same start and end info
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
    if timezone:
        if timezone not in pytz.all_timezones and timezone not in tzones:
            embed = discord.Embed(
                title='Error: Invalid Timezone',
                description='The timezone or abbreviation you have entered is invalid.'
                '\nFor a list of valid timezones, [click here](https://gist.github.com/heyalexej/8bf688fd67d7199be4a1682b3eec7568).',
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
            description="You've already created 5 events with the same name.\nPlease choose a different name.",
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
    event_id = await bot.pg_conn.fetchval("""INSERT INTO events(event_name, start_date, end_date, event_loc, event_note, guild_id, creator_id)
                                        VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING event_id;""",
                                        name, when_parsed, end_parsed, location, note, interaction.guild_id, interaction.user.id)


    embed = discord.Embed(
        title= f"Event {name} Created",
        description=f"<t:{when_unix}:f> ~ <t:{end_unix}:f>\n{location}\n{note}",
        color=discord.Color.green()
    )
    await interaction.response.send_message("creating event...", ephemeral=True)

    emojis = ['✅','❓','⏰']
    msg = await interaction.followup.send(embeds=[embed])
    for emoji in emojis:
        await msg.add_reaction(emoji)
    await bot.pg_conn.execute("UPDATE events SET message_id = $1 WHERE event_id = $2", msg.id, event_id)


@bot.tree.command(name="delete", description="Delete an existing event by its name.")
async def delete(interaction: discord.Interaction, name: str):
    # db lookup
    records = await bot.pg_conn.fetch("SELECT event_id, start_date, end_date, event_loc, creator_id FROM events WHERE event_name = $1 AND guild_id = $2",
                                      name, interaction.guild_id)
    # no data
    if len(records) == 0:
        embed = discord.Embed(
            title = 'Error: No events found.',
            description = f"No events with the name {name}.\nPlease check and try again.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embeds=[embed])
        return
    # invalid user
    if not (interaction.user.id == records[0]['creator_id'] or interaction.user.guild_permissions.administrator):
        embed = discord.Embed(
            title = 'Error: Wrong requester',
            description = f"Only the creator (<@{records[0]['creator_id']}>) and administrator (mod) can delete.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embeds=[embed])
        return
    # sole data 
    if len(records) == 1:
        await bot.pg_conn.execute("DELETE FROM events WHERE event_id = $1", records[0]['event_id'])
        embed = discord.Embed(
        title=f'Event {name} Deleted',
        description=f"<t:{int(records[0]['start_date'].timestamp())}:f> ~ <t:{int(records[0]['end_date'].timestamp())}:f>"
                    f"\n{records[0]['event_loc']}\n has been deleted!",
        color=discord.Color.green()
        )
        await interaction.response.send_message(embeds=[embed])
        return
    
    # multi-name handle
    embed = discord.Embed(
        title=f"Multiple events found with the name {name}", 
        description="Please choose one to delete:")
    
    for i, record in enumerate(records):
        embed.add_field(name=f"{i+1}", value=f"<t:{int(record['start_date'].timestamp())}:f> ~ <t:{int(record['end_date'].timestamp())}:f>\n{record['event_loc']}", inline=False)
        
    await interaction.response.send_message("generating delete options...", ephemeral=True)
    message = await interaction.followup.send(embeds=[embed])
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"] 
    for i in range(len(records)):
        await message.add_reaction(emojis[i])
    
    # check to pass in for wait
    def check(reaction, user):
        # Check if the reaction emoji is correct
        is_correct_emoji = str(reaction.emoji) in emojis

        # Check if the user is the creator or an admin
        is_creator_or_admin = user.id == records[0]['creator_id'] or user.guild_permissions.administrator

        return is_correct_emoji and is_creator_or_admin

    try:
        reaction, user = await bot.wait_for('reaction_add', timeout=60.0, check=check)
    except asyncio.TimeoutError:
        await interaction.followup.send(content='Time ran out. No events were deleted.')
        return
    index_to_delete = emojis.index(str(reaction.emoji))
    await bot.pg_conn.execute("DELETE FROM events WHERE event_id = $1", records[index_to_delete]['event_id'])
    embed = discord.Embed(
        title=f'Event {name} Deleted',
        description=f"<t:{int(records[index_to_delete]['start_date'].timestamp())}:f> ~ <t:{int(records[index_to_delete]['end_date'].timestamp())}:f>"
                    f"\n{records[index_to_delete]['event_loc']}\nhas been deleted!",
        color=discord.Color.green()
    )
    await interaction.followup.send(embeds=[embed])

def get_date_range(option: str):
    today = datetime.now()
    if option == "this week":
        start = datetime.combine(today.date() - timedelta(days=today.weekday()), datetime.min.time())
        end = datetime.combine(start.date() + timedelta(days=6), datetime.max.time().replace(second=59))
    elif option == "next week":
        start = datetime.combine(today.date() + timedelta(days=(7-today.weekday())), datetime.min.time())
        end = datetime.combine(start.date() + timedelta(days=6), datetime.max.time().replace(second=59))
    elif option == "this month":
        start = datetime.combine(today.replace(day=1).date(), datetime.min.time())
        end = datetime.combine(today.replace(day=calendar.monthrange(today.year, today.month)[1]).date(), datetime.max.time())
    elif option == "next month":
        if today.month == 12:
            start = datetime.combine(today.replace(year=today.year+1, month=1, day=1).date(), datetime.min.time())
        else:
            start = datetime.combine(today.replace(month=today.month+1, day=1).date(), datetime.min.time())
        end = datetime.combine(start.date().replace(day=calendar.monthrange(start.year, start.month)[1]), datetime.max.time())
    elif option == "all":
        start = None
        end = None
    else:
        raise ValueError("Invalid option")

    return start, end


@bot.tree.command(name="show", description="Show events based on time range.")
async def show(interaction: discord.Interaction, option: str):
    if option not in ["this week", "next week", "this month", "next month", "all"]:
        embed = discord.Embed(
            title='Error: Invalid Option',
            description="Please choose one of the options: 'this week', 'next week', 'this month', 'next month', 'all'.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embeds=[embed])
        return
    
    start_date, end_date = get_date_range(option)
    
    if option == "all":
        events = await bot.pg_conn.fetch("""SELECT event_name, start_date, end_date, event_loc, event_note 
                                         FROM events WHERE guild_id = $1 ORDER BY start_date ASC""", interaction.guild_id)
    else:
        events = await bot.pg_conn.fetch("""SELECT event_name, start_date, end_date, event_loc, event_note 
                                         FROM events WHERE guild_id = $1 AND start_date BETWEEN $2 AND $3 ORDER BY start_date ASC""", interaction.guild_id, start_date, end_date)
    
    if not events:
        embed = discord.Embed(
            title='No Events Found',
            description=f"There are no events scheduled for {option}.",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embeds=[embed])
        return

    embed = discord.Embed(
        title=f"Events for {option}",
        color=discord.Color.green()
    )
    for event in events:
        embed.add_field(name=event["event_name"], 
                        value=f"<t:{int(event['start_date'].timestamp())}:f> to <t:{int(event['end_date'].timestamp())}:f>"
                        f"\nLocation: {event['event_loc']}\nNote: {event['event_note']}", inline=False)
    
    await interaction.response.send_message(embeds=[embed])



bot.run(TOK)

