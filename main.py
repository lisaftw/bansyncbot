import discord
from discord.ext import commands
import json
import os
import logging
from datetime import datetime

# Configure logging
# This sets up both file and console logging to track bot operations and errors
# File logs persist across restarts while console logs provide real-time monitoring
logging.basicConfig(
    level=logging.INFO,  # Only log messages with severity INFO or higher
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # Structured format for easier parsing
    handlers=[
        logging.FileHandler("ban_sync.log"),  # Persistent logs for post-mortem analysis
        logging.StreamHandler()  # Console output for real-time monitoring
    ]
)
logger = logging.getLogger("ban_sync")  # Create a named logger for this application

# Bot configuration
# Set up the required Discord permissions (intents) the bot needs to function
intents = discord.Intents.default()
intents.members = True    # Required to track member joins/leaves and access member objects
intents.bans = True       # Required to receive ban events and manage bans
intents.guilds = True     # Required to access guild (server) information
intents.message_content = True  # Required to read command messages

# Initialize the bot with command prefix and permissions
bot = commands.Bot(command_prefix='!', intents=intents)

# Data storage file paths
# These JSON files store persistent data across bot restarts
SYNC_NETWORKS_FILE = "sync_networks.json"  # Stores network configurations and memberships
BAN_LOG_FILE = "ban_log.json"              # Stores history of all synchronized bans

# Define the standard green color for all embeds
# Using a consistent color scheme improves user experience and brand recognition
EMBED_COLOR = discord.Color.green()

# Helper function to create embeds with consistent styling
# This centralizes embed creation to ensure all bot responses have a uniform appearance
def create_embed(title, description=None):
    """
    Create a Discord embed with consistent styling
    
    Parameters:
        title: The title of the embed
        description: Optional description text
        
    Returns:
        discord.Embed: A formatted embed with the standard color
    """
    embed = discord.Embed(
        title=title,
        description=description,
        color=EMBED_COLOR
    )
    return embed

# Initialize data files if they don't exist
# This ensures the bot can start without errors even on first run
def initialize_data_files():
    """
    Create empty data files if they don't exist
    
    This prevents file not found errors when the bot starts for the first time
    and ensures data structures are properly initialized.
    """
    if not os.path.exists(SYNC_NETWORKS_FILE):
        with open(SYNC_NETWORKS_FILE, "w") as f:
            json.dump({}, f)  # Initialize with empty dictionary for networks
    
    if not os.path.exists(BAN_LOG_FILE):
        with open(BAN_LOG_FILE, "w") as f:
            json.dump([], f)  # Initialize with empty list for ban logs

# Load sync networks from file
# This retrieves the current state of all ban sync networks
def load_sync_networks():
    """
    Load the sync networks data from JSON file
    
    Returns:
        dict: A dictionary of all sync networks with their configurations
    """
    with open(SYNC_NETWORKS_FILE, "r") as f:
        return json.load(f)

# Save sync networks to file
# This persists any changes to the network configurations
def save_sync_networks(networks):
    """
    Save the sync networks data to JSON file
    
    Parameters:
        networks: Dictionary of network data to save
    """
    with open(SYNC_NETWORKS_FILE, "w") as f:
        json.dump(networks, f, indent=4)  # Use indentation for human readability

# Load ban log from file
# This retrieves the history of all synchronized bans
def load_ban_log():
    """
    Load the ban history from JSON file
    
    Returns:
        list: A list of all recorded ban events
    """
    with open(BAN_LOG_FILE, "r") as f:
        return json.load(f)

# Save ban to log
# This records each ban action for audit and history purposes
def save_ban_to_log(ban_data):
    """
    Add a new ban record to the ban history log
    
    Parameters:
        ban_data: Dictionary containing details about the ban event
    """
    ban_log = load_ban_log()
    ban_log.append(ban_data)
    with open(BAN_LOG_FILE, "w") as f:
        json.dump(ban_log, f, indent=4)  # Use indentation for human readability

# Check if user has admin permissions
# This is used to restrict sensitive commands to server administrators
def is_admin(ctx):
    """
    Check if a user has administrator permissions in their server
    
    Parameters:
        ctx: The command context containing the author
        
    Returns:
        bool: True if the user has administrator permissions, False otherwise
    """
    return ctx.author.guild_permissions.administrator

# Bot initialization event
@bot.event
async def on_ready():
    """
    Event handler triggered when bot successfully connects to Discord
    
    This method:
    1. Initializes data files
    2. Logs the successful connection
    3. Sets the bot's status message
    """
    initialize_data_files()
    logger.info(f"Bot is ready! Logged in as {bot.user}")
    await bot.change_presence(activity=discord.Game(name="Syncing bans"))

# Create a new sync network
# This establishes a new network that servers can join for ban synchronization
@bot.command(name="create_network")
async def create_network(ctx, network_name: str):
    """
    Create a new ban sync network
    
    This command:
    1. Verifies the user has administrator permissions
    2. Checks if the network name is already in use
    3. Creates a new network with the current server as owner
    4. Saves the network configuration
    
    Parameters:
        ctx: The command context
        network_name: The name for the new network
    """
    # Permission check - only administrators can create networks
    if not is_admin(ctx):
        embed = create_embed("Permission Denied", "You need administrator permissions to use this command.")
        await ctx.send(embed=embed)
        return
    
    networks = load_sync_networks()
    
    # Prevent duplicate network names
    if network_name in networks:
        embed = create_embed("Network Already Exists", f"Network '{network_name}' already exists.")
        await ctx.send(embed=embed)
        return
    
    # Create the network with the current server as both owner and first member
    networks[network_name] = {
        "owner": ctx.guild.id,  # The server that created the network
        "servers": [ctx.guild.id],  # List of servers in the network
        "created_at": datetime.now().isoformat()  # Creation timestamp for auditing
    }
    
    save_sync_networks(networks)
    logger.info(f"Network '{network_name}' created by {ctx.author} in {ctx.guild.name}")
    
    embed = create_embed("Network Created", f"✅ Ban sync network '{network_name}' created successfully!")
    await ctx.send(embed=embed)

# Join an existing sync network
# This adds the current server to an existing ban sync network
@bot.command(name="join_network")
async def join_network(ctx, network_name: str):
    """
    Join an existing ban sync network
    
    This command:
    1. Verifies the user has administrator permissions
    2. Checks if the network exists
    3. Checks if the server is already in the network
    4. Adds the server to the network
    
    Parameters:
        ctx: The command context
        network_name: The name of the network to join
    """
    # Permission check - only administrators can join networks
    if not is_admin(ctx):
        embed = create_embed("Permission Denied", "You need administrator permissions to use this command.")
        await ctx.send(embed=embed)
        return
    
    networks = load_sync_networks()
    
    # Verify the network exists
    if network_name not in networks:
        embed = create_embed("Network Not Found", f"Network '{network_name}' does not exist.")
        await ctx.send(embed=embed)
        return
    
    # Prevent joining a network multiple times
    if ctx.guild.id in networks[network_name]["servers"]:
        embed = create_embed("Already Joined", f"This server is already part of the '{network_name}' network.")
        await ctx.send(embed=embed)
        return
    
    # Add the server to the network
    networks[network_name]["servers"].append(ctx.guild.id)
    save_sync_networks(networks)
    
    logger.info(f"{ctx.guild.name} joined network '{network_name}'")
    embed = create_embed("Network Joined", f"✅ Joined ban sync network '{network_name}' successfully!")
    await ctx.send(embed=embed)

# Leave a sync network
# This removes the current server from a ban sync network
@bot.command(name="leave_network")
async def leave_network(ctx, network_name: str):
    """
    Leave a ban sync network
    
    This command:
    1. Verifies the user has administrator permissions
    2. Checks if the network exists
    3. Checks if the server is in the network
    4. Removes the server from the network
    5. Deletes the network if it becomes empty
    
    Parameters:
        ctx: The command context
        network_name: The name of the network to leave
    """
    # Permission check - only administrators can leave networks
    if not is_admin(ctx):
        embed = create_embed("Permission Denied", "You need administrator permissions to use this command.")
        await ctx.send(embed=embed)
        return
    
    networks = load_sync_networks()
    
    # Verify the network exists
    if network_name not in networks:
        embed = create_embed("Network Not Found", f"Network '{network_name}' does not exist.")
        await ctx.send(embed=embed)
        return
    
    # Verify the server is in the network
    if ctx.guild.id not in networks[network_name]["servers"]:
        embed = create_embed("Not In Network", f"This server is not part of the '{network_name}' network.")
        await ctx.send(embed=embed)
        return
    
    # Remove the server from the network
    networks[network_name]["servers"].remove(ctx.guild.id)
    
    # Clean up empty networks to prevent clutter
    if len(networks[network_name]["servers"]) == 0:
        del networks[network_name]
        embed = create_embed("Network Deleted", f"Network '{network_name}' has been deleted as it has no more servers.")
    else:
        embed = create_embed("Left Network", f"Left ban sync network '{network_name}' successfully.")
    
    save_sync_networks(networks)
    logger.info(f"{ctx.guild.name} left network '{network_name}'")
    await ctx.send(embed=embed)

# List all networks the server is part of
# This shows which ban sync networks the current server has joined
@bot.command(name="list_networks")
async def list_networks(ctx):
    """
    List all networks the server is part of
    
    This command:
    1. Verifies the user has administrator permissions
    2. Finds all networks that include the current server
    3. Displays the list of networks
    
    Parameters:
        ctx: The command context
    """
    # Permission check - only administrators can view network memberships
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
    
    # Handle case where server is not in any networks
    if not server_networks:
        embed = create_embed("No Networks", "This server is not part of any ban sync networks.")
        await ctx.send(embed=embed)
        return
    
    # Format the list of networks for display
    networks_list = "\n".join(f"- {name}" for name in server_networks)
    embed = create_embed("Server Networks", f"This server is part of the following ban sync networks:\n{networks_list}")
    await ctx.send(embed=embed)

# Ban a user and sync the ban across the network
# This is the core functionality - banning a user in all connected servers
@bot.command(name="syncban")
async def syncban(ctx, user_id: int, *, reason="No reason provided"):
    """
    Ban a user and sync the ban across all networks
    
    This command implements the core ban synchronization:
    1. Verifies the user has administrator permissions
    2. Finds all networks the server is part of
    3. Bans the user in the current server
    4. Propagates the ban to all other servers in the networks
    5. Logs the ban action for audit purposes
    
    Parameters:
        ctx: The command context
        user_id: The Discord ID of the user to ban
        reason: Optional justification for the ban
    """
    # Permission check - only administrators can issue bans
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
    
    # Handle case where server is not in any networks
    if not server_networks:
        embed = create_embed("No Networks", "This server is not part of any ban sync networks.")
        await ctx.send(embed=embed)
        return
    
    # Try to get user information for better logging
    # This is a best-effort approach - we can still ban by ID if user info is unavailable
    try:
        user = await bot.fetch_user(user_id)
        # Handle Discord's new username system
        if hasattr(user, 'discriminator') and user.discriminator != '0':
            user_name = f"{user.name}#{user.discriminator}"
        else:
            user_name = user.name
    except:
        user_name = f"Unknown User ({user_id})"
    
    # Ban the user in the current server first
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
    
    # Create comprehensive ban data for logging and auditing
    ban_data = {
        "user_id": user_id,
        "user_name": user_name,
        "reason": reason,
        "initiator_server": ctx.guild.id,
        "initiator_server_name": ctx.guild.name,
        "initiator_user": ctx.author.id,
        "initiator_user_name": f"{ctx.author.name}#{ctx.author.discriminator}" if hasattr(ctx.author, 'discriminator') and ctx.author.discriminator != '0' else ctx.author.name,
        "timestamp": datetime.now().isoformat(),
        "networks": server_networks
    }
    
    # Save to ban log for audit trail
    save_ban_to_log(ban_data)
    
    # Sync the ban to all servers in all networks this server is part of
    # This is the core synchronization functionality
    ban_count = 1  # Start count at 1 for the current server
    for network_name in server_networks:
        for server_id in networks[network_name]["servers"]:
            if server_id != ctx.guild.id:  # Skip the current server (already banned)
                server = bot.get_guild(server_id)
                if server:
                    try:
                        await server.ban(discord.Object(id=user_id), reason=f"[Ban Sync from {ctx.guild.name}] {reason}")
                        ban_count += 1
                        logger.info(f"Synced ban of {user_id} to {server.name}")
                    except Exception as e:
                        logger.error(f"Failed to sync ban to {server.name}: {e}")
    
    # Report the results of the ban synchronization
    embed = create_embed("Ban Synced", f"✅ Ban synced across {ban_count} servers in {len(server_networks)} networks.")
    await ctx.send(embed=embed)
    logger.info(f"Ban of {user_id} initiated by {ctx.author} synced to {ban_count} servers")

# Show recent ban sync activity
# This provides an audit trail of recent ban actions
@bot.command(name="ban_history")
async def ban_history(ctx, limit: int = 5):
    """
    Show recent ban sync activity
    
    This command:
    1. Verifies the user has administrator permissions
    2. Retrieves the ban log
    3. Displays the most recent ban actions
    
    Parameters:
        ctx: The command context
        limit: Optional number of recent bans to show (default: 5)
    """
    # Permission check - only administrators can view ban history
    if not is_admin(ctx):
        embed = create_embed("Permission Denied", "You need administrator permissions to use this command.")
        await ctx.send(embed=embed)
        return
    
    ban_log = load_ban_log()
    
    # Handle case where no bans have been recorded
    if not ban_log:
        embed = create_embed("No History", "No ban sync history found.")
        await ctx.send(embed=embed)
        return
    
    # Sort by timestamp (newest first) and limit to requested number
    recent_bans = sorted(ban_log, key=lambda x: x["timestamp"], reverse=True)[:limit]
    
    embed = create_embed("Recent Ban Sync Activity")
    
    # Add each ban as a field in the embed
    for ban in recent_bans:
        # Format the timestamp for readability
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
# This provides documentation on available commands
@bot.command(name="synchelp")
async def synchelp(ctx):
    """
    Display help information for the Ban Sync Bot
    
    This command creates a comprehensive help embed with all available commands
    and their descriptions to assist users in using the bot correctly.
    
    Parameters:
        ctx: The command context
    """
    embed = create_embed(
        "Ban Sync Bot Help",
        "Commands for managing ban synchronization across servers"
    )
    
    # Add each command with its description
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
# This could be expanded to implement automatic ban synchronization
@bot.event
async def on_member_ban(guild, user):
    """
    Event handler triggered when a member is banned from a guild
    
    This is a placeholder for potential future functionality:
    - Could implement automatic ban synchronization for bans not initiated by the bot
    - Could log all bans regardless of source
    - Could notify administrators of bans from other sources
    
    Parameters:
        guild: The guild where the ban occurred
        user: The user who was banned
    """
    # Currently this is a placeholder
    # Future implementation could check if this ban was initiated by our bot
    # If not, we could implement auto-sync here if desired
    pass

# Run the bot
if __name__ == "__main__":
    print("Starting Ban Sync Bot...")
    print("Make sure to replace 'YOUR_BOT_TOKEN' with your actual Discord bot token")
    # The bot.run() method is blocking and will not return until the bot is shut down
    bot.run("YOUR_BOT_TOKEN")  # Replace with your actual bot token
