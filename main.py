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
from config import ALLOWED_IDS, TELEGRAM_BOT_TOKEN, SITE_CONFIG, update_site_domain, logger
from hdmovie2 import get_movie_titles_and_links as hdmovie2_titles, get_download_links as hdmovie2_links, get_latest_movies as hdmovie2_latest
from hdhub4u import get_movie_titles_and_links as hdhub4u_titles, get_download_links as hdhub4u_links, get_latest_movies as hdhub4u_latest
from cinevood import get_movie_titles_and_links as cinevood_titles, get_download_links as cinevood_links, get_latest_movies as cinevood_latest

app = Flask(__name__)
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# Store user state with expiration
user_state = {}  # {chat_id: {'step': str, 'username': str, 'selected_site': str, 'site_results': {site: {'titles': [], 'links': []}}, 'last_active': datetime}}
STATE_TIMEOUT = timedelta(minutes=30)
MAX_MESSAGE_LENGTH = 4000
MAX_RETRIES = 3
MAX_RESULTS_PER_SITE = 20  # Limit to avoid Telegram message limits
BUTTON_TEXT_LIMIT = 60  # Telegram button text limit

def cleanup_expired_states():
    """Remove expired user states."""
    while True:
        current_time = datetime.now()
        expired = [chat_id for chat_id, state in user_state.items() if current_time - state['last_active'] > STATE_TIMEOUT]
        for chat_id in expired:
            del user_state[chat_id]
            logger.info(f"Cleaned up expired state for chat_id {chat_id}")
        time.sleep(600)

def send_long_message(chat_id, text, reply_to_message_id=None, reply_markup=None):
    """Send long messages by splitting if necessary."""
    try:
        if len(text) <= MAX_MESSAGE_LENGTH:
            return bot.send_message(chat_id=chat_id, text=text, reply_to_message_id=reply_to_message_id, parse_mode='HTML', reply_markup=reply_markup)
        parts = []
        while text:
            parts.append(text[:MAX_MESSAGE_LENGTH])
            text = text[MAX_MESSAGE_LENGTH:]
        for i, part in enumerate(parts):
            bot.send_message(chat_id=chat_id, text=part, parse_mode='HTML', reply_markup=reply_markup if i == len(parts) - 1 else None)
        return parts[-1]
    except Exception as e:
        logger.error(f"Error sending message to chat_id {chat_id}: {e}")
        return None

def create_site_selection_keyboard():
    """Create inline keyboard for site selection."""
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("🎥 1. Hdmovie2", callback_data="site_hdmovie2"))
    markup.add(InlineKeyboardButton("🎬 2. Hdhub4u", callback_data="site_hdhub4u"))
    markup.add(InlineKeyboardButton("🍿 3. Cinevood", callback_data="site_cinevood"))
    markup.add(InlineKeyboardButton("❌ Cancel", callback_data="cancel"))
    return markup

def create_movie_selection_keyboard(site, titles, offset=0):
    """Create inline keyboard for movie selection."""
    markup = InlineKeyboardMarkup(row_width=1)
    end_index = min(offset + MAX_RESULTS_PER_SITE, len(titles))
    for i in range(offset, end_index):
        title = titles[i][:BUTTON_TEXT_LIMIT] + "..." if len(titles[i]) > BUTTON_TEXT_LIMIT else titles[i]
        markup.add(InlineKeyboardButton(f"{i+1}. {title}", callback_data=f"select_{site}_{i}"))
    if end_index < len(titles):
        markup.add(InlineKeyboardButton("➕ Show More", callback_data=f"more_{site}_{end_index}"))
    markup.row(
        InlineKeyboardButton("🔙 Back to Site Selection", callback_data="back_to_site"),
        InlineKeyboardButton("❌ Cancel", callback_data="cancel")
    )
    return markup

def search_movies_for_site(movie_name, site):
    """Search movies on a specific site."""
    site_functions = {
        'hdmovie2': hdmovie2_titles,
        'hdhub4u': hdhub4u_titles,
        'cinevood': cinevood_titles
    }
    try:
        titles, links = site_functions[site](movie_name)
        if titles:
            logger.info(f"Fetched {len(titles)} titles from {site} for query: {movie_name}")
            return {'titles': titles, 'links': [(link, site) for link in links]}
        return {}
    except Exception as e:
        logger.error(f"Error searching {site} for {movie_name}: {e}")
        return {}

def get_download_links_for_movie(link, site):
    """Get download links based on the site with retries."""
    site_functions = {
        'hdmovie2': hdmovie2_links,
        'hdhub4u': hdhub4u_links,
        'cinevood': cinevood_links
    }
    for attempt in range(MAX_RETRIES):
        try:
            links = site_functions[site](link)
            logger.info(f"Fetched {len(links)} download links from {site}")
            return links
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1} failed for {site}: {e}")
            if attempt == MAX_RETRIES - 1:
                logger.error(f"All retries failed for {site}: {e}")
                return []
            time.sleep(2 * (attempt + 1))

@app.route('/telegram', methods=['POST'])
def telegram_webhook():
    """Handle Telegram webhook requests."""
    try:
        update = request.get_json()
        if not update:
            logger.debug("Invalid update received")
            return '', 400

        if 'message' in update:
            message = update['message']
            chat_id = message['chat']['id']
            message_id = message.get('message_id')
            text = message.get('text', '').strip()

            if chat_id not in ALLOWED_IDS:
                send_long_message(chat_id, "🚫 <strong>Access Denied</strong>\n\nThis bot is restricted to authorized users only. Contact the admin for access.", reply_to_message_id=message_id)
                logger.info(f"Unauthorized access by chat_id {chat_id}")
                return '', 200

            # Update last active time
            if chat_id in user_state:
                user_state[chat_id]['last_active'] = datetime.now()

            # Handle commands and text input
            if text.lower() == '/start':
                user_state[chat_id] = {'step': 'awaiting_username', 'last_active': datetime.now()}
                send_long_message(
                    chat_id,
                    "🌟 <strong>Welcome to Movie Search Bot!</strong>\n\n"
                    "👤 Please enter a <strong>movie name</strong> to start searching.\n"
                    "🎥 After selecting a site, I'll show you movies matching your query.\n\n"
                    "📌 <strong>Commands:</strong>\n"
                    "• /start - Begin a new session\n"
                    "• /cancel - Cancel the current operation\n"
                    "• /update_domain - Update site domains\n\n"
                    "💡 <strong>Example:</strong> <code>Animal 2023</code>",
                    reply_to_message_id=message_id
                )
                logger.info(f"User {chat_id} started bot")

            elif text.lower() == '/cancel':
                if chat_id in user_state:
                    del user_state[chat_id]
                    send_long_message(chat_id, "✅ <strong>Operation Cancelled</strong>\n\nStart a new session with /start.", reply_to_message_id=message_id)
                    logger.info(f"User {chat_id} cancelled operation")
                else:
                    send_long_message(chat_id, "ℹ️ <strong>No Active Session</strong>\n\nNothing to cancel. Start with /start.", reply_to_message_id=message_id)

            elif text.lower() == '/update_domain':
                user_state[chat_id] = {'step': 'awaiting_update_site', 'last_active': datetime.now()}
                sites = "\n".join([f"• {i+1}. {site.capitalize()}: {SITE_CONFIG[site]}" for i, site in enumerate(SITE_CONFIG.keys())])
                send_long_message(
                    chat_id,
                    f"🌐 <strong>Current Site Domains:</strong>\n\n{sites}\n\n"
                    f"Reply with the number (1-{len(SITE_CONFIG)}) to select a site to update its domain.\n"
                    f"💡 Example: Reply '3' to update cinevood, then enter the new domain (e.g., '1cinevood.store').",
                    reply_to_message_id=message_id
                )
                logger.info(f"User {chat_id} initiated domain update")

            elif chat_id in user_state:
                state = user_state[chat_id]

                if state['step'] == 'awaiting_username':
                    if not text:
                        send_long_message(chat_id, "❌ <strong>Please enter a valid movie name!</strong>\n\nTry again or use /cancel' to stop.", reply_to_message_id=message_id)
                        logger.warning(f"User {chat_id} sent empty username")
                        return '', 200
                    user_state[chat_id] = {
                        'step': 'awaiting_site',
                        'username': text,
                        'site_results': {},
                        'last_active': datetime.now()
                    }
                    send_long_message(
                        chat_id,
                        f"👤 <strong>Movie: {text}</strong>\n\n"
                        f"🎬 <strong>Select a site to search for '{text}':</strong>",
                        reply_to_message_id=create_site_selection,
                        reply_markup=keyboard()
                    )
                    logger.info(f"User {chat_id} set username to {text}'")

                elif state['step'] == 'awaiting_update_site':
                    if text.lower() == 'cancel':
                        del user_state[chat_id]
                        send_long_message(
                            chat_id,
                            "✅ <strong>Cancelled</strong>\n\nStart over with /start.",
                            reply_to_message_id=message_id
                        )
                        logger.info(f"User {chat_id} cancelled domain update")
                        return '', 200

                    try:
                        index = int(text) - 1
                        site_keys = list(SITE_CONFIG.keys())
                        if index < 0 or index >= len(site_keys):
                            raise ValueError("Invalid site number")
                        user_state[chat_id] = {'step': 'awaiting_new_domain', 'site_key': site_keys[index], 'last_active': datetime.now()}
                        send_long_message(
                            chat_id,
                            f"🌐 <strong>Enter the new domain for {site_keys[index].capitalize()}</strong>\n\n"
                            f"Current: {SITE_CONFIG[site_keys[index]]}\n"
                            f"Example: <code>{site_keys[index]}.site</code>",
                            reply_to_message_id=message_id
                        )
                        logger.info(f"User {chat_id} selected site {site_keys[index]} for domain update")
                    except ValueError:
                        send_long_message(
                            chat_id,
                            f"❌ <strong>Invalid Input</strong>\n\nPlease enter a number between 1 and {len(SITE_CONFIG)}, or 'cancel'.",
                            reply_to_message_id=message_id
                        )
                        logger.warning(f"User {chat_id} sent invalid site selection: {text}")

                elif state['step'] == 'awaiting_new_domain':
                    if text.lower() == 'cancel':
                        del user_state[chat_id]
                        send_long_message(chat_id, "✅ <strong>Cancelled</strong>\n\nStart over with /start.", reply_to_message_id=message_id)
                        logger.info(f"User {chat_id} cancelled domain update")
                        return '', 200

                    new_domain = text.strip()
                    site_key = state['site_key']
                    if update_site_domain(site_key, new_domain):
                        del user_state[chat_id]
                        sites = "\n".join([f"• {i+1}. {key}: {SITE_CONFIG[key]}" for i, key in enumerate(SITE_CONFIG.keys())])
                        send_long_message(
                            chat_id,
                            f"✅ <strong>Updated {site_key.capitalize()} to '{new_domain}'</strong>\n\n"
                            f"The bot will now use the new domain for searches.\n"
                            f"Start a new session with /start.\n\n"
                            f"🌐 <strong>Current Site Domains:</strong>\n{sites}",
                            reply_to_message_id=message_id
                        )
                        logger.info(f"User {chat_id} updated {site_key} to {new_domain}")
                    else:
                        del user_state[chat_id]
                        send_long_message(
                            chat_id,
                            f"❌ <strong>Failed to Update Domain</strong>\n\n"
                            f"Invalid domain format or prefix for '{site_key}'. The domain must start with '{site_key}' (e.g., '{site_key}.tv').\n\n"
                            f"Start over with /start.",
                            reply_to_message_id=message_id
                        )
                        logger.warning(f"User {chat_id} failed to update domain for {site_key} to {new_domain}")

        elif 'callback_query' in update:
            callback = update['callback_query']
            chat_id = callback['message']['chat']['id']
            message_id = callback['message']['message_id']
            callback_data = callback['data']

            if chat_id not in ALLOWED_IDS:
                bot.answer_callback_query(callback['id'], text="🚫 Unauthorized access!", show_alert=True)
                logger.info(f"Unauthorized callback by chat_id {chat_id}")
                return '', 200

            if chat_id not in user_state:
                bot.answer_callback_query(callback['id'], text="ℹ️ Session expired. Start over with /start.", show_alert=True)
                return '', 200

            user_state[chat_id]['last_active'] = datetime.now()
            state = user_state[chat_id]

            if callback_data == 'cancel':
                del user_state[chat_id]
                send_long_message(chat_id, "✅ <strong>Operation Cancelled</strong>\n\nStart a new session with /start.", reply_to_message_id=message_id)
                bot.answer_callback_query(callback['id'])
                logger.info(f"User {chat_id} cancelled via callback")
                return '', 200

            elif callback_data.startswith('site_'):
                site = callback_data.split('_')[1]
                if state['step'] != 'awaiting_site':
                    bot.answer_callback_query(callback['id'], text="ℹ️ Please start over with /start.", show_alert=True)
                    return '', 200

                user_state[chat_id] = {
                    'step': 'awaiting_movie_selection',
                    'username': state['username'],
                    'selected_site': site,
                    'site_results': {},
                    'last_active': datetime.now()
                }
                send_long_message(
                    chat_id,
                    f"🔍 <strong>Searching for '{state['username']}' on {site.capitalize()}...</strong>\n\nPlease wait a moment.",
                    reply_to_message_id=message_id
                )
                results = search_movies_for_site(state['username'], site)
                user_state[chat_id]['site_results'] = {site: results} if results else {}

                if not results:
                    send_long_message(
                        chat_id,
                        f"😕 <strong>No Movies Found for '{state['username']}' on {site.capitalize()}</strong>\n\n"
                        f"Possible reasons:\n"
                        "• Incorrect movie name or not available.\n"
                        "• Site may be down or blocked.\n\n"
                        f"🔙 Click 'Back' to choose another site or /start to try a new movie name.",
                        reply_to_message_id=message_id,
                        reply_markup=create_site_selection_keyboard()
                    )
                    user_state[chat_id]['step'] = 'awaiting_site'
                    logger.info(f"No movies found for {state['username']} on {site} by user {chat_id}")
                    bot.answer_callback_query(callback['id'])
                    return '', 200

                titles = results['titles']
                titles_text = "\n".join([f"• {title}" for title in titles[:MAX_RESULTS_PER_SITE]])
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=f"🎥 <strong>Results for '{state['username']}' on {site.capitalize()}:</strong>\n\n{titles_text}\n\n"
                         f"📥 Select a movie to get download links.",
                    parse_mode='HTML',
                    reply_markup=create_movie_selection_keyboard(site, titles)
                )
                logger.info(f"User {chat_id} received {len(titles)} titles from {site}")
                bot.answer_callback_query(callback['id'])

            elif callback_data == 'back_to_site':
                if state['step'] != 'awaiting_movie_selection':
                    bot.answer_callback_query(callback['id'], text="ℹ️ Invalid action. Start over with /start.", show_alert=True)
                    return '', 200

                user_state[chat_id] = {
                    'step': 'awaiting_site',
                    'username': state['username'],
                    'site_results': {},
                    'last_active': datetime.now()
                }
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=f"👤 <strong>Movie: {state['username']}</strong>\n\n"
                         f"🎬 <strong>Select a site to search for '{state['username']}':</strong>",
                    parse_mode='HTML',
                    reply_markup=create_site_selection_keyboard()
                )
                bot.answer_callback_query(callback['id'])
                logger.info(f"User {chat_id} returned to site selection")

            elif callback_data.startswith('more_'):
                if state['step'] != 'awaiting_movie_selection':
                    bot.answer_callback_query(callback['id'], text="ℹ️ Session expired. Start over with /start.", show_alert=True)
                    return '', 200

                _, site, offset = callback_data.split('_')
                offset = int(offset)
                if site not in state['site_results']:
                    bot.answer_callback_query(callback['id'], text="❌ Invalid site!", show_alert=True)
                    logger.warning(f"User {chat_id} requested more for invalid site: {site}")
                    return '', 200

                titles = state['site_results'][site]['titles']
                titles_text = "\n".join([f"• {title}" for title in titles[offset:offset+MAX_RESULTS_PER_SITE]])
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=f"🎥 <strong>Results for '{state['username']}' on {site.capitalize()}:</strong>\n\n{titles_text}\n\n"
                         f"📥 Select a movie to get download links.",
                    parse_mode='HTML',
                    reply_markup=create_movie_selection_keyboard(site, titles, offset)
                )
                bot.answer_callback_query(callback['id'])
                logger.info(f"User {chat_id} requested more results for {site}")

            elif callback_data.startswith('select_'):
                if state['step'] != 'awaiting_movie_selection':
                    bot.answer_callback_query(callback['id'], text="ℹ️ Session expired. Start over with /start.", show_alert=True)
                    return '', 200

                try:
                    _, site, index = callback_data.split('_')
                    index = int(index)
                    if site not in state['site_results'] or index >= len(state['site_results'][site]['links']):
                        raise ValueError("Invalid selection")
                except ValueError:
                    bot.answer_callback_query(callback['id'], text="❌ Invalid selection!", show_alert=True)
                    logger.warning(f"User {chat_id} sent invalid callback: {callback_data}")
                    return '', 200

                selected_link, _ = state['site_results'][site]['links'][index]
                selected_title = state['site_results'][site]['titles'][index]
                send_long_message(
                    chat_id,
                    f"📥 <strong>Fetching links for '{selected_title}' from {site.capitalize()}...</strong>\n\nPlease wait.",
                    reply_to_message_id=message_id
                )
                logger.info(f"User {chat_id} selected movie '{selected_title}' from {site}")
                download_links = get_download_links_for_movie(selected_link, site)

                if download_links:
                    links_text = "\n".join([f"• <a href='{link.split(': ')[1]}'>{link.split(': ')[0]}</a>" for link in download_links])
                    send_long_message(
                        chat_id,
                        f"✅ <strong>Download Links for '{selected_title}' ({site.capitalize()}):</strong>\n\n{links_text}\n\n"
                        f"🔙 Click 'Back' to choose another movie or site, or /start for a new search.",
                        reply_to_message_id=message_id,
                        reply_markup=create_movie_selection_keyboard(site, state['site_results'][site]['titles'])
                    )
                    logger.info(f"User {chat_id} received {len(download_links)} download links for '{selected_title}'")
                else:
                    send_long_message(
                        chat_id,
                        f"😕 <strong>No Links Found for '{selected_title}' on {site.capitalize()}</strong>\n\n"
                        f"Possible reasons:\n"
                        "• Links not available.\n"
                        "• Site structure may have changed.\n\n"
                        f"🔙 Click 'Back' to choose another movie or site, or /start for a new search.",
                        reply_to_message_id=message_id,
                        reply_markup=create_movie_selection_keyboard(site, state['site_results'][site]['titles'])
                    )
                    logger.info(f"No download links found for '{selected_title}' by user {chat_id}")

                bot.answer_callback_query(callback['id'])

        return '', 200

    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        if 'chat_id' in locals() and 'message_id' in locals():
            send_long_message(chat_id, f"❌ <strong>Unexpected Error</strong>\n\nSomething went wrong: {str(e)}\n\nTry again with /start.", reply_to_message_id=message_id)
        return '', 500

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

# Start state cleanup thread
state_cleanup_thread = threading.Thread(target=cleanup_expired_states, daemon=True)
state_cleanup_thread.start()

# Start keep_alive thread
keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
keep_alive_thread.start()

# Register cleanup on exit
atexit.register(cleanup)

if __name__ == "__main__":
    set_webhook()
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Starting Flask app on port {port}")
    app.run(host="0.0.0.0", port=port)