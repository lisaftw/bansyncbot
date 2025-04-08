import discord
from discord.ext import commands
import json
import os
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("ban_sync.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("ban_sync")

# Bot configuration
intents = discord.Intents.default()
intents.members = True
intents.bans = True
intents.guilds = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Data storage
SYNC_NETWORKS_FILE = "sync_networks.json"
BAN_LOG_FILE = "ban_log.json"

# Define the standard green color for all embeds
EMBED_COLOR = discord.Color.green()

# Helper function to create embeds with consistent styling
def create_embed(title, description=None):
    embed = discord.Embed(
        title=title,
        description=description,
        color=EMBED_COLOR
    )
    return embed

# Initialize data files if they don't exist
def initialize_data_files():
    if not os.path.exists(SYNC_NETWORKS_FILE):
        with open(SYNC_NETWORKS_FILE, "w") as f:
            json.dump({}, f)
    
    if not os.path.exists(BAN_LOG_FILE):
        with open(BAN_LOG_FILE, "w") as f:
            json.dump([], f)

# Load sync networks from file
def load_sync_networks():
    with open(SYNC_NETWORKS_FILE, "r") as f:
        return json.load(f)

# Save sync networks to file
def save_sync_networks(networks):
    with open(SYNC_NETWORKS_FILE, "w") as f:
        json.dump(networks, f, indent=4)

# Load ban log from file
def load_ban_log():
    with open(BAN_LOG_FILE, "r") as f:
        return json.load(f)

# Save ban to log
def save_ban_to_log(ban_data):
    ban_log = load_ban_log()
    ban_log.append(ban_data)
    with open(BAN_LOG_FILE, "w") as f:
        json.dump(ban_log, f, indent=4)

# Check if user has admin permissions
def is_admin(ctx):
    return ctx.author.guild_permissions.administrator

@bot.event
async def on_ready():
    initialize_data_files()
    logger.info(f"Bot is ready! Logged in as {bot.user}")
    await bot.change_presence(activity=discord.Game(name="Syncing bans"))

# Create a new sync network
@bot.command(name="create_network")
async def create_network(ctx, network_name: str):
    if not is_admin(ctx):
        embed = create_embed("Permission Denied", "You need administrator permissions to use this command.")
        await ctx.send(embed=embed)
        return
    
    networks = load_sync_networks()
    
    if network_name in networks:
        embed = create_embed("Network Already Exists", f"Network '{network_name}' already exists.")
        await ctx.send(embed=embed)
        return
    
    networks[network_name] = {
        "owner": ctx.guild.id,
        "servers": [ctx.guild.id],
        "created_at": datetime.now().isoformat()
    }
    
    save_sync_networks(networks)
    logger.info(f"Network '{network_name}' created by {ctx.author} in {ctx.guild.name}")
    
    embed = create_embed("Network Created", f"✅ Ban sync network '{network_name}' created successfully!")
    await ctx.send(embed=embed)

# Join an existing sync network
@bot.command(name="join_network")
async def join_network(ctx, network_name: str):
    if not is_admin(ctx):
        embed = create_embed("Permission Denied", "You need administrator permissions to use this command.")
        await ctx.send(embed=embed)
        return
    
    networks = load_sync_networks()
    
    if network_name not in networks:
        embed = create_embed("Network Not Found", f"Network '{network_name}' does not exist.")
        await ctx.send(embed=embed)
        return
    
    if ctx.guild.id in networks[network_name]["servers"]:
        embed = create_embed("Already Joined", f"This server is already part of the '{network_name}' network.")
        await ctx.send(embed=embed)
        return
    
    networks[network_name]["servers"].append(ctx.guild.id)
    save_sync_networks(networks)
    
    logger.info(f"{ctx.guild.name} joined network '{network_name}'")
    embed = create_embed("Network Joined", f"✅ Joined ban sync network '{network_name}' successfully!")
    await ctx.send(embed=embed)

# Leave a sync network
@bot.command(name="leave_network")
async def leave_network(ctx, network_name: str):
    if not is_admin(ctx):
        embed = create_embed("Permission Denied", "You need administrator permissions to use this command.")
        await ctx.send(embed=embed)
        return
    
    networks = load_sync_networks()
    
    if network_name not in networks:
        embed = create_embed("Network Not Found", f"Network '{network_name}' does not exist.")
        await ctx.send(embed=embed)
        return
    
    if ctx.guild.id not in networks[network_name]["servers"]:
        embed = create_embed("Not In Network", f"This server is not part of the '{network_name}' network.")
        await ctx.send(embed=embed)
        return
    
    networks[network_name]["servers"].remove(ctx.guild.id)
    
    # If the network is empty, delete it
    if len(networks[network_name]["servers"]) == 0:
        del networks[network_name]
        embed = create_embed("Network Deleted", f"Network '{network_name}' has been deleted as it has no more servers.")
    else:
        embed = create_embed("Left Network", f"Left ban sync network '{network_name}' successfully.")
    
    save_sync_networks(networks)
    logger.info(f"{ctx.guild.name} left network '{network_name}'")
    await ctx.send(embed=embed)

# List all networks the server is part of
@bot.command(name="list_networks")
async def list_networks(ctx):
    if not is_admin(ctx):
        embed = create_embed("Permission Denied", "You need administrator permissions to use this command.")
        await ctx.send(embed=embed)
        return
    
    networks = load_sync_networks()
    server_networks = []
    
    for name, data in networks.items():
        if ctx.guild.id in data["servers"]:
            server_networks.append(name)
    
    if not server_networks:
        embed = create_embed("No Networks", "This server is not part of any ban sync networks.")
        await ctx.send(embed=embed)
        return
    
    networks_list = "\n".join(f"- {name}" for name in server_networks)
    embed = create_embed("Server Networks", f"This server is part of the following ban sync networks:\n{networks_list}")
    await ctx.send(embed=embed)

# Ban a user and sync the ban across the network
@bot.command(name="syncban")
async def syncban(ctx, user_id: int, *, reason="No reason provided"):
    if not is_admin(ctx):
        embed = create_embed("Permission Denied", "You need administrator permissions to use this command.")
        await ctx.send(embed=embed)
        return
    
    networks = load_sync_networks()
    server_networks = []
    
    # Find all networks this server is part of
    for name, data in networks.items():
        if ctx.guild.id in data["servers"]:
            server_networks.append(name)
    
    if not server_networks:
        embed = create_embed("No Networks", "This server is not part of any ban sync networks.")
        await ctx.send(embed=embed)
        return
    
    # Get user information if possible
    try:
        user = await bot.fetch_user(user_id)
        user_name = f"{user.name}#{user.discriminator}"
    except:
        user_name = f"Unknown User ({user_id})"
    
    # Ban the user in the current server
    try:
        await ctx.guild.ban(discord.Object(id=user_id), reason=f"[Ban Sync] {reason}")
        embed = create_embed("User Banned", f"✅ Banned {user_name} from this server.")
        await ctx.send(embed=embed)
    except discord.Forbidden:
        embed = create_embed("Permission Error", "I don't have permission to ban users in this server.")
        await ctx.send(embed=embed)
        return
    except discord.HTTPException as e:
        embed = create_embed("Ban Failed", f"Failed to ban user: {e}")
        await ctx.send(embed=embed)
        return
    
    # Create ban data for logging
    ban_data = {
        "user_id": user_id,
        "user_name": user_name,
        "reason": reason,
        "initiator_server": ctx.guild.id,
        "initiator_server_name": ctx.guild.name,
        "initiator_user": ctx.author.id,
        "initiator_user_name": f"{ctx.author.name}#{ctx.author.discriminator}",
        "timestamp": datetime.now().isoformat(),
        "networks": server_networks
    }
    
    # Save to ban log
    save_ban_to_log(ban_data)
    
    # Sync the ban to all servers in the networks
    ban_count = 1  # Count the current server
    for network_name in server_networks:
        for server_id in networks[network_name]["servers"]:
            if server_id != ctx.guild.id:  # Skip the current server
                server = bot.get_guild(server_id)
                if server:
                    try:
                        await server.ban(discord.Object(id=user_id), reason=f"[Ban Sync from {ctx.guild.name}] {reason}")
                        ban_count += 1
                        logger.info(f"Synced ban of {user_id} to {server.name}")
                    except Exception as e:
                        logger.error(f"Failed to sync ban to {server.name}: {e}")
    
    embed = create_embed("Ban Synced", f"✅ Ban synced across {ban_count} servers in {len(server_networks)} networks.")
    await ctx.send(embed=embed)
    logger.info(f"Ban of {user_id} initiated by {ctx.author} synced to {ban_count} servers")

# Show recent ban sync activity
@bot.command(name="ban_history")
async def ban_history(ctx, limit: int = 5):
    if not is_admin(ctx):
        embed = create_embed("Permission Denied", "You need administrator permissions to use this command.")
        await ctx.send(embed=embed)
        return
    
    ban_log = load_ban_log()
    
    if not ban_log:
        embed = create_embed("No History", "No ban sync history found.")
        await ctx.send(embed=embed)
        return
    
    # Sort by timestamp (newest first) and limit
    recent_bans = sorted(ban_log, key=lambda x: x["timestamp"], reverse=True)[:limit]
    
    embed = create_embed("Recent Ban Sync Activity")
    
    for ban in recent_bans:
        timestamp = datetime.fromisoformat(ban["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
        embed.add_field(
            name=f"{ban['user_name']} (ID: {ban['user_id']})",
            value=f"**Reason:** {ban['reason']}\n"
                  f"**Initiated by:** {ban['initiator_user_name']} in {ban['initiator_server_name']}\n"
                  f"**Time:** {timestamp}\n"
                  f"**Networks:** {', '.join(ban['networks'])}",
            inline=False
        )
    
    await ctx.send(embed=embed)

# Help command
@bot.command(name="synchelp")
async def synchelp(ctx):
    embed = create_embed(
        "Ban Sync Bot Help",
        "Commands for managing ban synchronization across servers"
    )
    
    embed.add_field(
        name="!create_network <network_name>",
        value="Create a new ban sync network",
        inline=False
    )
    embed.add_field(
        name="!join_network <network_name>",
        value="Join an existing ban sync network",
        inline=False
    )
    embed.add_field(
        name="!leave_network <network_name>",
        value="Leave a ban sync network",
        inline=False
    )
    embed.add_field(
        name="!list_networks",
        value="List all networks this server is part of",
        inline=False
    )
    embed.add_field(
        name="!syncban <user_id> [reason]",
        value="Ban a user and sync the ban across all networks",
        inline=False
    )
    embed.add_field(
        name="!ban_history [limit]",
        value="Show recent ban sync activity (default: 5 most recent)",
        inline=False
    )
    
    await ctx.send(embed=embed)

# Event listener for bans
@bot.event
async def on_member_ban(guild, user):
    # Check if this ban was initiated by our bot
    # If not, we could implement auto-sync here if desired
    pass

# Run the bot (replace TOKEN with your actual bot token)
if __name__ == "__main__":
    print("Starting Ban Sync Bot...")
    print("Make sure to replace 'YOUR_BOT_TOKEN' with your actual Discord bot token")
    bot.run("YOUR_BOT_TOKEN")  # Replace with your bot token
