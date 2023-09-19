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

# helper function
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

async def validate_input_length(interaction, **kwargs):
    for field, value in kwargs.items():
        if value and len(value) > 255:
            embed = discord.Embed(
                title=f'Error: {field} Is Too Long',
                description=f"The {field.lower()} of the event is too long.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embeds=[embed])
            return False
    return True

async def validate_timezone(interaction, timezone):
    if timezone and timezone not in pytz.all_timezones:
        embed = discord.Embed(
            title='Error: Invalid Timezone',
            description='The timezone or abbreviation you have entered is invalid.'
                '\nFor a list of valid timezones, [click here](https://gist.github.com/heyalexej/8bf688fd67d7199be4a1682b3eec7568).',
            color=discord.Color.red()
        )
        await interaction.response.send_message(embeds=[embed])
        return False
    return True

async def parse_datetime(interaction, when, duration, timezone):
    loc_tz = datetime.now().astimezone().tzinfo.tzname(None)
    timezone = timezone or loc_tz
    try:
        when_parsed = parse(when, settings={'PREFER_DATES_FROM': 'future', 'TIMEZONE': timezone, 'TO_TIMEZONE': loc_tz})
        if when_parsed is None:
            raise ValueError("Failed to parse when.")
        
        end_parsed = parse(duration, settings={'RELATIVE_BASE': when_parsed, 'PREFER_DATES_FROM': 'future'})
        if end_parsed is None:
            raise ValueError("Failed to parse duration.")
        
        return when_parsed, end_parsed
    except ValueError as e:
        embed = discord.Embed(
            title='Error: Parsing Failed',
            description=str(e),
            color=discord.Color.red()
        )
        await interaction.response.send_message(embeds=[embed])
        return None, None
def to_string_timedelta(delta):
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    result = ""
    if days:
        result += f"{days} days, "
    if hours:
        result += f"{hours} hours, "
    if minutes:
        result += f"{minutes} minutes, "
    if seconds:
        result += f"{seconds} seconds, "
        
    return result.rstrip(", ")
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

# bot event    
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

# bot command
# TODO: check if dup event has the same start and end info
@bot.tree.command(name="create", description="Create new event. Timezone is set to server's if not specified.")
async def create(interaction: discord.Interaction, name:str, when:str,
                 duration:str = '0 hour', timezone:str = '', location:str = '', note:str = ''):
    # input length checked
    if not await validate_input_length(interaction, Name = name, Location = location, Note = note):
        return
    # input timezone check
    if timezone:
        if not await validate_timezone(interaction, timezone):
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
    when_parsed, end_parsed = await parse_datetime(interaction, when, duration, timezone)
    if when_parsed is None or end_parsed is None:
        return
    # db insert
    event_id = await bot.pg_conn.fetchval("""INSERT INTO events(event_name, start_date, end_date, event_loc, event_note, guild_id, creator_id)
                                        VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING event_id;""",
                                        name, when_parsed, end_parsed, location, note, interaction.guild_id, interaction.user.id)

    when_unix, end_unix = int(when_parsed.timestamp()), int(end_parsed.timestamp())
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

# TODO: multievent case fails to send embed when dateparse fails since it already sent emoji embed, alert rsvper of the editted event
@bot.tree.command(name="edit", description="Edit an event by its name. Please specify appropriate timezone.")
async def edit(interaction: discord.Interaction, name:str, newname:str='', when:str='',
                 duration:str = '', timezone:str = '', location:str = '', note:str = ''):
    # at least one field is needed for edit
    if not any([newname,when, duration, timezone, location, note]):
        embed = discord.Embed(
            title='Error: Nothing To Edit',
            description='Please provide a field to edit.',
            color=discord.Color.red()
        )
        await interaction.response.send_message(embeds=[embed])
        return
    #input checks
    if not await validate_input_length(interaction, Name=name, Location=location, Note=note):
        return
    if timezone:
        if not await validate_timezone(interaction, timezone):
            return    
    # db lookup
    records = await bot.pg_conn.fetch("SELECT event_id, start_date, end_date, event_loc, creator_id FROM events WHERE event_name = $1 AND guild_id = $2",
                                      name, interaction.guild_id)
    # check if event exists
    if len(records) == 0:
        embed = discord.Embed(
            title = 'Error: No events found.',
            description = f"No events with the name {name}.\nPlease check and try again.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embeds=[embed])
        return
    # choose which event
    if len(records) > 1:
        embed = discord.Embed(
            title=f"Multiple events found with the name {name}", 
            description="Please choose one to delete:")
        
        for i, record in enumerate(records):
            embed.add_field(name=f"{i+1}", value=f"<t:{int(record['start_date'].timestamp())}:f> ~ <t:{int(record['end_date'].timestamp())}:f>\n{record['event_loc']}", inline=False)
            
        await interaction.response.send_message("generating edit options...", ephemeral=True)
        message = await interaction.followup.send(embeds=[embed])
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"] 
        for i in range(len(records)):
            await message.add_reaction(emojis[i])
        
        # check to pass in for wait
        def check(reaction, _):
            return str(reaction.emoji) in emojis

        try:
            reaction, _ = await bot.wait_for('reaction_add', timeout=60.0, check=check)
        except asyncio.TimeoutError:
            await interaction.followup.send(content='Time ran out. No events were editted.')
            return
        index_to_edit = emojis.index(str(reaction.emoji))
        to_edit = records[index_to_edit]
    else:
        to_edit = records[0]
    
    # user permission
    if not (interaction.user.id == to_edit['creator_id'] or interaction.user.guild_permissions.administrator):
        embed = discord.Embed(
            title = 'Error: Wrong requester',
            description = f"Only the creator (<@{to_edit['creator_id']}>) and administrator (mod) can edit.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embeds=[embed])
        return        
    
    update_fields = {}
    existing_start = to_edit['start_date']
    existing_end = to_edit['end_date']
    existing_duration = to_string_timedelta(existing_end - existing_start) or '0 hour'

    when_parsed = None
    end_parsed = None

    if when or duration or timezone:
        when_parsed, end_parsed = await parse_datetime(interaction, when or existing_start, duration or existing_duration, timezone)
        if when_parsed is None or end_parsed is None:
            return
        update_fields['start_date'] = when_parsed
        update_fields['end_date'] = end_parsed
    if newname:
        update_fields['event_name'] = newname
    if location:
        update_fields['event_loc'] = location
    if note:
        update_fields['event_note'] = note
    

    update_query = "UPDATE events SET " + ", ".join(f"{key} = ${i+2}" for i, key in enumerate(update_fields.keys())) + " WHERE event_id = $1"

    await bot.pg_conn.execute(update_query, to_edit["event_id"], *update_fields.values())

    when_unix = int((when_parsed or existing_start).timestamp())
    end_unix = int((end_parsed or existing_end).timestamp())
    embed = discord.Embed(
        title= f"Event {newname or name} Editted",
        description=f"<t:{when_unix}:f> ~ <t:{end_unix}:f>\n{location}\n{note}",
        color=discord.Color.green()
    )
    if len(records) == 1:
        await interaction.response.send_message("editting event...", ephemeral=True)

    emojis = ['✅','❓','⏰']
    msg = await interaction.followup.send(embeds=[embed])
    for emoji in emojis:
        await msg.add_reaction(emoji)
    await bot.pg_conn.execute("UPDATE events SET message_id = $1 WHERE event_id = $2", msg.id, to_edit['event_id'])

# TODO: notify event is deleted to those who rsvped
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
    
    if len(records) > 1:
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
        
        def check(reaction, _):
            return str(reaction.emoji) in emojis

        try:
            reaction, _ = await bot.wait_for('reaction_add', timeout=60.0, check=check)
        except asyncio.TimeoutError:
            await interaction.followup.send(content='Time ran out. No events were deleted.')
            return
        
        index_to_delete = emojis.index(str(reaction.emoji))
        to_delete = records[index_to_delete]
    else:
        to_delete = records[0]

    # User permission check
    if not (interaction.user.id == to_delete['creator_id'] or interaction.user.guild_permissions.administrator):
        embed = discord.Embed(
            title='Error: Wrong requester',
            description=f"Only the creator (<@{to_delete['creator_id']}>) and administrator (mod) can delete.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embeds=[embed])
        return
    
    # Delete the event
    await bot.pg_conn.execute("DELETE FROM events WHERE event_id = $1", to_delete['event_id'])
    embed = discord.Embed(
        title=f'Event {name} Deleted',
        description=f"<t:{int(to_delete['start_date'].timestamp())}:f> ~ <t:{int(to_delete['end_date'].timestamp())}:f>"
                    f"\n{to_delete['event_loc']}\n has been deleted!",
        color=discord.Color.green()
    )
    if len(records) == 1:
        await interaction.response.send_message(embeds=[embed])
    else:
        await interaction.followup.send(embeds=[embed])

# TODO: add option for looking up with name
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

