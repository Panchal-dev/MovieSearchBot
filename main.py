import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading
import time
import os
import requests
import atexit
from flask import Flask, request, jsonify
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from config import ALLOWED_IDS, TELEGRAM_BOT_TOKEN, SITE_CONFIG, update_site_domain, logger
from hdmovie2 import get_movie_titles_and_links as hdmovie2_titles, get_download_links as hdmovie2_links, get_latest_movies as hdmovie2_latest
from hdhub4u import get_movie_titles_and_links as hdhub4u_titles, get_download_links as hdhub4u_links, get_latest_movies as hdhub4u_latest
from cinevood import get_movie_titles_and_links as cinevood_titles, get_download_links as cinevood_links, get_latest_movies as cinevood_latest

app = Flask(__name__)
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# Store user state with expiration
user_state = {}  # {chat_id: {'step': str, 'movie_name': str, 'current_site': str, 'site_results': {site: {'titles': [], 'links': []}}, 'last_active': datetime}}
STATE_TIMEOUT = timedelta(minutes=30)
MAX_MESSAGE_LENGTH = 3500  # Reduced to avoid Telegram limits
MAX_RETRIES = 3
MAX_RESULTS_PER_SITE = 15
BUTTON_TEXT_LIMIT = 50
URL_VALIDATION_KEYWORDS = ['download', 'gdflix', 'filepress', '1080p', '720p', '480p', 'hd']
URL_EXCLUDE_KEYWORDS = ['watch online', 'trailer', 'telegram', 'join', 'home', 'how to download']

# Site configuration with emojis
SITES = {
    'hdmovie2': {'name': 'HDMovie2', 'emoji': '🎬'},
    'hdhub4u': {'name': 'HDHub4U', 'emoji': '🎭'},
    'cinevood': {'name': 'CineVood', 'emoji': '🍿'}
}

def cleanup_expired_states():
    """Remove expired user states."""
    while True:
        current_time = datetime.now()
        expired = [chat_id for chat_id, state in user_state.items() if current_time - state['last_active'] > STATE_TIMEOUT]
        for chat_id in expired:
            del user_state[chat_id]
            logger.info(f"Cleaned up expired state for chat_id {chat_id}")
        time.sleep(600)

def is_valid_url(url, title=""):
    """Validate URL to ensure it's a download link."""
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False
        if any(exclude in title.lower() or exclude in url.lower() for exclude in URL_EXCLUDE_KEYWORDS):
            return False
        if any(keyword in title.lower() or keyword in url.lower() for keyword in URL_VALIDATION_KEYWORDS):
            return True
        return False
    except Exception:
        return False

def send_long_message(chat_id, text, reply_to_message_id=None, reply_markup=None):
    """Send long messages by splitting with HTML integrity."""
    try:
        if len(text) <= MAX_MESSAGE_LENGTH:
            return bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_to_message_id=reply_to_message_id,
                parse_mode='HTML',
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
        parts = []
        current_part = ""
        lines = text.split('\n')
        for line in lines:
            if len(current_part) + len(line) + 1 > MAX_MESSAGE_LENGTH:
                parts.append(current_part)
                current_part = line + '\n'
            else:
                current_part += line + '\n'
        if current_part:
            parts.append(current_part)
        messages = []
        for i, part in enumerate(parts):
            messages.append(
                bot.send_message(
                    chat_id=chat_id,
                    text=part,
                    parse_mode='HTML',
                    reply_markup=reply_markup if i == len(parts) - 1 else None,
                    disable_web_page_preview=True
                )
            )
        return messages[-1]
    except Exception as e:
        logger.error(f"Error sending message to chat_id {chat_id}: {e}")
        return None

def create_site_selection_keyboard(command):
    """Create keyboard for site selection."""
    markup = InlineKeyboardMarkup(row_width=1)
    for i, (site_key, site_info) in enumerate(SITES.items(), 1):
        markup.add(InlineKeyboardButton(
            f"{site_info['emoji']} {i}. {site_info['name']} ({SITE_CONFIG[site_key]})",
            callback_data=f"{command}_site_{site_key}"
        ))
    markup.add(InlineKeyboardButton("❌ Cancel", callback_data="cancel"))
    return markup

def create_movie_selection_keyboard(scroll_id, site, titles, offset=0):
    """Create scrollable inline keyboard for movie selection."""
    markup = InlineKeyboardMarkup(row_width=1)
    site_info = SITES.get(site, {'name': site.capitalize(), 'emoji': '🎬'})
    
    end_index = min(offset + MAX_RESULTS_PER_SITE, len(titles))
    for i in range(offset, end_index):
        title = titles[i]
        display_title = title[:BUTTON_TEXT_LIMIT] + "..." if len(title) > BUTTON_TEXT_LIMIT else title
        markup.add(InlineKeyboardButton(
            f"🎥 {display_title}",
            callback_data=f"select_{scroll_id}_{site}_{i}"
        ))
    
    nav_buttons = []
    if offset > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"prev_{scroll_id}_{site}_{max(0, offset-MAX_RESULTS_PER_SITE)}"))
    if end_index < len(titles):
        nav_buttons.append(InlineKeyboardButton("➡️ Next", callback_data=f"next_{scroll_id}_{site}_{end_index}"))
    
    if nav_buttons:
        markup.row(*nav_buttons)
    
    markup.row(
        InlineKeyboardButton("🔙 Back to Sites", callback_data=f"back_to_sites_{scroll_id}"),
        InlineKeyboardButton("🔍 New Search", callback_data="new_search")
    )
    markup.add(InlineKeyboardButton("❌ Cancel", callback_data="cancel"))
    
    return markup

def create_back_navigation_keyboard(scroll_id):
    """Create navigation keyboard for going back."""
    markup = InlineKeyboardMarkup(row_width=2)
    markup.row(
        InlineKeyboardButton("🔙 Back to Sites", callback_data=f"back_to_sites_{scroll_id}"),
        InlineKeyboardButton("🔍 New Search", callback_data="new_search")
    )
    markup.add(InlineKeyboardButton("❌ Cancel", callback_data="cancel"))
    return markup

def search_movies_single_site(movie_name, site):
    """Search movies on a single site with retry logic."""
    site_functions = {
        'hdmovie2': hdmovie2_titles,
        'hdhub4u': hdhub4u_titles,
        'cinevood': cinevood_titles
    }
    
    for attempt in range(MAX_RETRIES):
        try:
            if site not in site_functions:
                logger.error(f"Invalid site: {site}")
                return [], []
            
            titles, links = site_functions[site](movie_name)
            if not titles:
                logger.warning(f"No titles found for '{movie_name}' on {site} (attempt {attempt + 1})")
            else:
                logger.info(f"Fetched {len(titles)} titles for '{movie_name}' from {site}")
                return titles[:MAX_RESULTS_PER_SITE], links[:MAX_RESULTS_PER_SITE]
        except Exception as e:
            logger.warning(f"Error searching {site} (attempt {attempt + 1}): {e}")
            if attempt == MAX_RETRIES - 1:
                logger.error(f"All retries failed for {site}: {e}")
                return [], []
            time.sleep(2 * (attempt + 1))
    return [], []

def get_latest_movies_all_sites():
    """Fetch latest movies from all sites concurrently."""
    site_results = {}
    site_functions = [
        ('hdmovie2', hdmovie2_latest),
        ('hdhub4u', hdhub4u_latest),
        ('cinevood', cinevood_latest)
    ]

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(func): site for site, func in site_functions}
        for future in futures:
            site = futures[future]
            try:
                titles, links = future.result(timeout=20)
                if titles:
                    site_results[site] = {
                        'titles': titles[:MAX_RESULTS_PER_SITE],
                        'links': links[:MAX_RESULTS_PER_SITE]
                    }
                    logger.info(f"Fetched {len(titles)} latest titles from {site}")
                else:
                    logger.warning(f"No latest titles found for {site}")
            except Exception as e:
                logger.error(f"Error fetching latest from {site}: {e}")

    return site_results

def get_download_links_for_movie(link, site):
    """Get download links with validation and retries."""
    site_functions = {
        'hdmovie2': hdmovie2_links,
        'hdhub4u': hdhub4u_links,
        'cinevood': cinevood_links
    }
    
    for attempt in range(MAX_RETRIES):
        try:
            links = site_functions[site](link)
            valid_links = []
            for link in links:
                parts = link.rsplit(':', 1)
                if len(parts) == 2:
                    title, url = parts
                    title = title.strip()
                    url = url.strip()
                    if is_valid_url(url, title):
                        valid_links.append(f"{title}: {url}")
                elif is_valid_url(link):
                    valid_links.append(f"Link: {link}")
            if valid_links:
                logger.info(f"Fetched {len(valid_links)} valid download links from {site}")
                return valid_links[:10]
            else:
                logger.warning(f"No valid download links found for {link} on {site} (attempt {attempt + 1})")
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1} failed for {site}: {e}")
            if attempt == MAX_RETRIES - 1:
                logger.error(f"All retries failed for {site}: {e}")
                return []
            time.sleep(2 * (attempt + 1))
    return []

@app.route('/telegram', methods=['POST'])
def telegram_webhook():
    """Handle Telegram webhook requests."""
    try:
        update = request.get_json()
        if not update:
            logger.debug("Invalid update received")
            return '', 200

        if 'message' in update:
            message = update['message']
            chat_id = message['chat']['id']
            message_id = message.get('message_id')
            text = message.get('text', '').strip()

            if chat_id not in ALLOWED_IDS:
                send_long_message(chat_id, "🚫 <b>Access Denied</b>\n\n❌ This bot is restricted to authorized users only.", reply_to_message_id=message_id)
                logger.info(f"Unauthorized access by chat_id {chat_id}")
                return '', 200

            if chat_id in user_state:
                user_state[chat_id]['last_active'] = datetime.now()

            if text.lower() == '/start':
                user_state[chat_id] = {'step': 'awaiting_movie_name', 'last_active': datetime.now()}
                welcome_text = (
                    "🎬 <b>Welcome to Advanced Movie Search Bot!</b>\n\n"
                    "✨ <b>How it works:</b>\n"
                    "1️⃣ Enter a movie name to search\n"
                    "2️⃣ Choose a site to search on\n"
                    "3️⃣ Select a movie from results\n"
                    "4️⃣ Get clickable download links!\n\n"
                    "🔍 <b>Enter a movie name:</b>\n"
                    "💡 <i>Example: Animal 2023</i>"
                )
                send_long_message(chat_id, welcome_text, reply_to_message_id=message_id)
                logger.info(f"User {chat_id} started bot")

            elif text.lower() == '/latest':
                user_state[chat_id] = {'step': 'latest_site_selection', 'scroll_id': f"latest_{chat_id}_{int(time.time())}", 'last_active': datetime.now()}
                latest_text = (
                    "🔥 <b>Latest Movies</b>\n\n"
                    "🎬 <b>Choose a site to view the latest movies:</b>\n"
                    f"📍 <i>HDMovie2: Single page; Others: Up to 10 pages</i>"
                )
                send_long_message(
                    chat_id,
                    latest_text,
                    reply_to_message_id=message_id,
                    reply_markup=create_site_selection_keyboard('latest')
                )
                logger.info(f"User {chat_id} requested latest movies")

            elif text.lower() == '/cmd':
                commands_text = (
                    "📋 <b>Available Commands:</b>\n\n"
                    "🔹 <b>/start</b>: Start a new movie search\n"
                    "🔹 <b>/latest</b>: View latest movies\n"
                    "🔹 <b>/cancel</b>: Cancel current operation\n"
                    "🔹 <b>/update_domain</b>: Update site domain\n"
                    "🔹 <b>/cmd</b>: Show this command list\n\n"
                    "💡 <i>Use these to navigate easily!</i>"
                )
                send_long_message(chat_id, commands_text, reply_to_message_id=message_id)
                logger.info(f"User {chat_id} requested command list")

            elif text.lower() == '/cancel':
                if chat_id in user_state:
                    del user_state[chat_id]
                    send_long_message(chat_id, "✅ <b>Operation Cancelled</b>\n\n🔄 Start over with /start or /latest", reply_to_message_id=message_id)
                    logger.info(f"User {chat_id} cancelled operation")
                else:
                    send_long_message(chat_id, "ℹ️ <b>No Active Operation</b>\n\n🚀 Start with /start or /latest", reply_to_message_id=message_id)

            elif text.lower() == '/update_domain':
                user_state[chat_id] = {'step': 'awaiting_site_selection_domain', 'last_active': datetime.now()}
                sites = "\n".join([f"• {i+1}. {key}: {SITE_CONFIG[key]}" for i, key in enumerate(SITE_CONFIG.keys())])
                send_long_message(
                    chat_id,
                    f"🌐 <b>Current Site Domains:</b>\n{sites}\n\n"
                    f"📝 Reply with the number (1-{len(SITE_CONFIG)}) to select a site to update its domain.\n"
                    f"💡 <i>Example: Reply '2' to update hdhub4u</i>",
                    reply_to_message_id=message_id
                )
                logger.info(f"User {chat_id} initiated domain update")

            elif chat_id in user_state:
                state = user_state[chat_id]

                if state['step'] == 'awaiting_movie_name':
                    if not text:
                        send_long_message(chat_id, "❌ <b>Please enter a movie name</b>\n\n💡 <i>Example: In Laws 2020</i>", reply_to_message_id=message_id)
                        return '', 200
                    
                    user_state[chat_id].update({
                        'step': 'site_selection',
                        'movie_name': text,
                        'site_results': {},
                        'scroll_id': f"search_{chat_id}_{int(time.time())}",
                        'last_active': datetime.now()
                    })
                    
                    site_selection_text = (
                        f"🎯 <b>Searching for: '{text}'</b>\n\n"
                        f"🎬 <b>Choose a site to search:</b>\n"
                        f"📍 <i>Each site may have different quality options</i>"
                    )
                    
                    send_long_message(
                        chat_id, 
                        site_selection_text,
                        reply_to_message_id=message_id,
                        reply_markup=create_site_selection_keyboard('search')
                    )
                    logger.info(f"User {chat_id} entered movie name: {text}")

                elif state['step'] == 'awaiting_site_selection_domain':
                    if text.lower() == 'cancel':
                        del user_state[chat_id]
                        send_long_message(chat_id, "✅ <b>Cancelled</b>\n\n🔄 Start over with /start or /latest", reply_to_message_id=message_id)
                        return '', 200

                    try:
                        index = int(text) - 1
                        site_keys = list(SITE_CONFIG.keys())
                        if index < 0 or index >= len(site_keys):
                            raise ValueError("Invalid site number")
                        user_state[chat_id] = {'step': 'awaiting_new_domain', 'site_key': site_keys[index], 'last_active': datetime.now()}
                        send_long_message(
                            chat_id,
                            f"🌐 <b>Enter new domain for {site_keys[index]}</b>\n\n"
                            f"📍 Current: <code>{SITE_CONFIG[site_keys[index]]}</code>\n"
                            f"💡 <i>Example: {site_keys[index]}.new-domain.com</i>",
                            reply_to_message_id=message_id
                        )
                        logger.info(f"User {chat_id} selected site {site_keys[index]} for domain update")
                    except ValueError:
                        send_long_message(
                            chat_id,
                            f"❌ <b>Invalid Input</b>\n\n📝 Please enter a number between 1 and {len(SITE_CONFIG)}, or 'cancel'.",
                            reply_to_message_id=message_id
                        )

                elif state['step'] == 'awaiting_new_domain':
                    if text.lower() == 'cancel':
                        del user_state[chat_id]
                        send_long_message(chat_id, "✅ <b>Cancelled</b>\n\n🔄 Start over with /start or /latest", reply_to_message_id=message_id)
                        return '', 200

                    new_domain = text.strip()
                    site_key = state['site_key']
                    if update_site_domain(site_key, new_domain):
                        del user_state[chat_id]
                        sites = "\n".join([f"• {key}: {SITE_CONFIG[key]}" for key in SITE_CONFIG.keys()])
                        send_long_message(
                            chat_id,
                            f"✅ <b>Domain Updated Successfully!</b>\n\n"
                            f"🎯 {site_key} → <code>{new_domain}</code>\n\n"
                            f"🌐 <b>Current Domains:</b>\n{sites}\n\n"
                            f"🚀 Start a new search with /start or /latest",
                            reply_to_message_id=message_id
                        )
                        logger.info(f"User {chat_id} updated {site_key} to {new_domain}")
                    else:
                        del user_state[chat_id]
                        send_long_message(
                            chat_id,
                            f"❌ <b>Domain Update Failed</b>\n\n"
                            f"🚫 Invalid format for '{site_key}'\n"
                            f"💡 Domain must start with '{site_key}'\n\n"
                            f"🔄 Start over with /start or /latest",
                            reply_to_message_id=message_id
                        )

        elif 'callback_query' in update:
            callback = update['callback_query']
            chat_id = callback['message']['chat']['id']
            message_id = callback['message']['message_id']
            callback_data = callback['data']

            if chat_id not in ALLOWED_IDS:
                bot.answer_callback_query(callback['id'], text="🚫 Unauthorized access!", show_alert=True)
                return '', 200

            if chat_id not in user_state:
                bot.answer_callback_query(callback['id'], text="⏰ Session expired. Start over with /start or /latest.", show_alert=True)
                return '', 200

            user_state[chat_id]['last_active'] = datetime.now()
            state = user_state[chat_id]

            if callback_data == 'cancel':
                del user_state[chat_id]
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text="✅ <b>Operation Cancelled</b>\n\n🔄 Start over with /start or /latest",
                    parse_mode='HTML'
                )
                bot.answer_callback_query(callback['id'])
                return '', 200

            elif callback_data == 'new_search':
                user_state[chat_id] = {'step': 'awaiting_movie_name', 'last_active': datetime.now()}
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text="🔍 <b>Enter a new movie name:</b>\n\n💡 <i>Example: In Laws 2020</i>",
                    parse_mode='HTML'
                )
                bot.answer_callback_query(callback['id'])
                return '', 200

            elif callback_data.startswith('back_to_sites_'):
                scroll_id = callback_data.replace('back_to_sites_', '')
                if state.get('step') == 'latest_selection':
                    user_state[chat_id]['step'] = 'latest_site_selection'
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=(
                            "🔥 <b>Latest Movies</b>\n\n"
                            "🎬 <b>Choose a site to view the latest movies:</b>\n"
                            f"📍 <i>HDMovie2: Single page; Others: Up to 10 pages</i>"
                        ),
                        parse_mode='HTML',
                        reply_markup=create_site_selection_keyboard('latest')
                    )
                else:
                    user_state[chat_id]['step'] = 'site_selection'
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=(
                            f"🎯 <b>Searching for: '{state.get('movie_name', 'Unknown')}'</b>\n\n"
                            f"🎬 <b>Choose a site to search:</b>\n"
                            f"📍 <i>Each site may have different quality options</i>"
                        ),
                        parse_mode='HTML',
                        reply_markup=create_site_selection_keyboard('search')
                    )
                bot.answer_callback_query(callback['id'])
                return '', 200

            elif callback_data.startswith('search_site_'):
                site = callback_data.replace('search_site_', '')
                if 'movie_name' not in state:
                    bot.answer_callback_query(callback['id'], text="❌ No movie name found!", show_alert=True)
                    return '', 200

                movie_name = state['movie_name']
                site_info = SITES.get(site, {'name': site.capitalize(), 'emoji': '🎬'})
                scroll_id = state.get('scroll_id', f"search_{chat_id}_{int(time.time())}")
                
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=f"🔍 <b>Searching '{movie_name}' on {site_info['emoji']} {site_info['name']}...</b>\n\n⏳ <i>Please wait...</i>",
                    parse_mode='HTML'
                )

                titles, links = search_movies_single_site(movie_name, site)
                
                if not titles:
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=(
                            f"😔 <b>No results found for '{movie_name}'</b>\n\n"
                            f"🎬 Site: {site_info['emoji']} {site_info['name']}\n\n"
                            f"💡 <b>Try:</b>\n"
                            f"• Different spelling\n"
                            f"• Another site\n"
                            f"• Different search terms"
                        ),
                        parse_mode='HTML',
                        reply_markup=create_back_navigation_keyboard(scroll_id)
                    )
                    bot.answer_callback_query(callback['id'])
                    return '', 200

                user_state[chat_id].update({
                    'step': 'movie_selection',
                    'current_site': site,
                    'site_results': {site: {'titles': titles, 'links': links}},
                    'scroll_id': scroll_id
                })

                results_text = (
                    f"✨ <b>Found {len(titles)} results for '{movie_name}'</b>\n\n"
                    f"🎬 <b>Site:</b> {site_info['emoji']} {site_info['name']}\n\n"
                    f"📱 <b>Select a movie to get download links:</b>"
                )

                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=results_text,
                    parse_mode='HTML',
                    reply_markup=create_movie_selection_keyboard(scroll_id, site, titles)
                )
                bot.answer_callback_query(callback['id'])
                logger.info(f"User {chat_id} selected site {site} and found {len(titles)} results")

            elif callback_data.startswith('latest_site_'):
                site = callback_data.replace('latest_site_', '')
                site_info = SITES.get(site, {'name': site.capitalize(), 'emoji': '🎬'})
                scroll_id = state.get('scroll_id', f"latest_{chat_id}_{int(time.time())}")

                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=f"🔍 <b>Fetching latest movies from {site_info['emoji']} {site_info['name']}...</b>\n\n⏳ <i>Please wait...</i>",
                    parse_mode='HTML'
                )

                site_results = get_latest_movies_all_sites()
                user_state[chat_id].update({
                    'step': 'latest_selection',
                    'site_results': site_results,
                    'scroll_id': scroll_id
                })

                if site not in site_results or not site_results[site]['titles']:
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=(
                            f"😔 <b>No latest movies found on {site_info['name']}</b>\n\n"
                            f"💡 <b>Try another site or check later</b>"
                        ),
                        parse_mode='HTML',
                        reply_markup=create_back_navigation_keyboard(scroll_id)
                    )
                    bot.answer_callback_query(callback['id'])
                    return '', 200

                titles = site_results[site]['titles']
                results_text = (
                    f"🔥 <b>Latest Movies</b>\n\n"
                    f"🎬 <b>Site:</b> {site_info['emoji']} {site_info['name']}"
                    f"📊 <b>Found:</b> {len(titles)} movies\n\n"
                    f"📱 <b>Select a movie:</b>"
                )

                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=results_text,
                    parse_mode='HTML',
                    reply_markup=create_movie_selection_keyboard(scroll_id, site, titles)
                )
                bot.answer_callback_query(callback['id'])
                logger.info(f"User {chat_id} selected site {site} for latest movies")

            elif callback_data.startswith(('next_', 'prev_')):
                parts = callback_data.split('_')
                action, scroll_id, site, offset = parts[0], parts[1], parts[2], int(parts[3])
                
                if site not in state.get('site_results', {}):
                    bot.answer_callback_query(callback['id'], text="❌ Invalid site!", show_alert=True)
                    return '', 200

                titles = state['site_results'][site]['titles']
                site_info = SITES.get(site, {'name': site.capitalize(), 'emoji': '🎬'})
                
                results_text = (
                    f"✨ <b>{'Latest Movies' if state['step'] == 'latest_selection' else f'Results for {state.get('movie_name', 'Unknown')}'}</b>\n\n"
                    f"🎬 <b>Site:</b> {site_info['emoji']} {site_info['name']}\n"
                    f"📊 <b>Showing:</b> {offset + 1} - {min(offset + MAX_RESULTS_PER_SITE, len(titles))} of {len(titles)}\n\n"
                    f"📱 <b>Select a movie:</b>"
                )

                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=results_text,
                    parse_mode='HTML',
                    reply_markup=create_movie_selection_keyboard(scroll_id, site, titles, offset)
                )
                bot.answer_callback_query(callback['id'])

            elif callback_data.startswith('select_'):
                try:
                    parts = callback_data.split('_')
                    if len(parts) != 4:
                        raise ValueError("Invalid callback data format")
                    _, scroll_id, site, index = parts
                    index = int(index)
                    
                    if site not in state.get('site_results', {}) or index >= len(state['site_results'][site]['links']):
                        raise ValueError("Invalid selection")
                        
                except ValueError as e:
                    bot.answer_callback_query(callback['id'], text=f"❌ Invalid selection: {str(e)}!", show_alert=True)
                    return '', 200

                selected_url = state['site_results'][site]['links'][index]
                selected_title = state['site_results'][site]['titles'][index]
                site_info = SITES.get(site, {'name': site.capitalize(), 'emoji': '🎬'})

                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=(
                        f"📥 <b>Getting download links...</b>\n\n"
                        f"🎬 <b>Movie:</b> {selected_title}\n"
                        f"🌐 <b>Site:</b> {site_info['emoji']} {site_info['name']}\n\n"
                        f"⏳ <i>Please wait...</i>"
                    ),
                    parse_mode='HTML'
                )

                download_links = get_download_links_for_movie(selected_url, site)

                if download_links:
                    links_text = ""
                    for i, link in enumerate(download_links[:10], 1):
                        parts = link.rsplit(':', 1)
                        title = parts[0].strip() if len(parts) == 2 else f"Link {i}"
                        url = parts[1].strip() if len(parts) == 2 else link.strip()
                        links_text += f"<b>{i}) {title}:</b>\n<a href='{url}'>{url}</a>\n\n"
                    
                    final_text = (
                        f"✅ <b>Download Links Ready!</b>\n\n"
                        f"🎬 <b>Movie:</b> {selected_title}\n"
                        f"🌐 <b>Site:</b> {site_info['emoji']} {site_info['name']}\n"
                        f"📋 <b>Found:</b> {len(download_links)} links\n\n"
                        f"📥 <b>Download Links:</b>\n\n{links_text}"
                        f"💡 <i>Click links to open</i>"
                    )
                    
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=final_text,
                        parse_mode='HTML',
                        reply_markup=create_back_navigation_keyboard(scroll_id),
                        disable_web_page_preview=True
                    )
                else:
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=(
                            f"😔 <b>No download links found</b>\n\n"
                            f"🎬 <b>Movie:</b> {selected_title}\n"
                            f"🌐 <b>Site:</b> {site_info['emoji']} {site_info['name']}\n\n"
                            f"💡 <b>Try:</b>\n"
                            f"  • Another movie\n"
                            f"  • A different site\n"
                            f"  • Check debug logs for details"
                        ),
                        parse_mode='HTML',
                        reply_markup=create_back_navigation_keyboard(scroll_id)
                    )

                bot.answer_callback_query(callback['id'])
                logger.info(f"User {chat_id} got {len(download_links)} download links for '{selected_title}' on {site}")

        return '', 200

    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        if 'chat_id' in locals() and 'message_id' in locals():
            send_long_message(chat_id, f"❌ <b>Unexpected Error</b>\n\n🐛 {str(e)}\n\n🔄 Try again with /start or /latest", reply_to_message_id=message_id)
        return '', 200

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    logger.debug("Health check requested")
    return jsonify({"status": "healthy", "time": datetime.now().isoformat(), "active_users": len(user_state)})

def set_webhook():
    """Set Telegram webhook."""
    railway_domain = os.environ.get('RAILWAY_PUBLIC_DOMAIN')
    if not railway_domain:
        logger.error("RAILWAY_PUBLIC_DOMAIN not set")
        raise ValueError("RAILWAY_PUBLIC_DOMAIN environment variable not set")
    webhook_url = f"https://{railway_domain}/telegram"
    for attempt in range(MAX_RETRIES):
        try:
            bot.set_webhook(url=webhook_url)
            logger.info(f"Webhook set to: {webhook_url}")
            return
        except Exception as e:
            logger.warning(f"Webhook set attempt {attempt + 1} failed: {e}")
            if attempt == MAX_RETRIES - 1:
                logger.error(f"Failed to set webhook after {MAX_RETRIES} attempts")
                raise
            time.sleep(2 * (attempt + 1))

def keep_alive():
    """Periodically ping health endpoint to prevent Railway spin-down."""
    railway_domain = os.environ.get('RAILWAY_PUBLIC_DOMAIN')
    if not railway_domain:
        logger.error("RAILWAY_PUBLIC_DOMAIN not set")
        return
    while True:
        try:
            response = requests.get(f"https://{railway_domain}/health", timeout=5)
            logger.debug(f"Keep-alive ping: {response.status_code}")
        except Exception as e:
            logger.warning(f"Keep-alive ping failed: {e}")
        time.sleep(120)

def cleanup():
    """Clean up on shutdown."""
    user_state.clear()
    logger.info("Cleaned up user states on shutdown")

state_cleanup_thread = threading.Thread(target=cleanup_expired_states, daemon=True)
state_cleanup_thread.start()

keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
keep_alive_thread.start()

atexit.register(cleanup)

if __name__ == "__main__":
    set_webhook()
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Starting Flask app on port {port}")
    app.run(host="0.0.0.0", port=port)