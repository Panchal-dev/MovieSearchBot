import json
import os
import cloudscraper
import requests
from bs4 import BeautifulSoup
import time
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from telegram.error import Conflict, NetworkError, TimedOut
from tornado.web import Application as TornadoApp, RequestHandler

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Constants
ALLOWED_IDS = {5809601894, 1285451259}
CONFIG_FILE = "config.json"
SEARCH, SELECT_MOVIE, UPDATE_URL = range(3)

# Default site configurations
DEFAULT_CONFIG = {
    "sites": {
        "hdmovie2": {"url": "https://hdmovie2.trading", "enabled": True},
        "hdhub4u": {"url": "https://hdhub4u.gratis", "enabled": True},
        "cinevood": {"url": "https://1cinevood.asia", "enabled": True},
    }
}

# Load or initialize config
def load_config():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        with open(CONFIG_FILE, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        return DEFAULT_CONFIG
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return DEFAULT_CONFIG

# Save config
def save_config(config):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving config: {e}")

# Check if user is authorized
def is_authorized(update: Update):
    return update.effective_user.id in ALLOWED_IDS if update.effective_user else False

# Scrape movie titles and links from a site
def get_movie_titles_and_links(movie_name, site_name, site_url):
    search_query = f"{movie_name.replace(' ', '+').lower()}"
    base_url = f"{site_url}/?s={search_query}"
    page = 1
    movie_count = 0
    all_titles = []
    movie_links = []

    if site_name == "hdmovie2":
        scraper = cloudscraper.create_scraper()
        while True:
            url = base_url if page == 1 else f"{site_url}/page/{page}/?s={search_query}"
            try:
                response = scraper.get(url, timeout=10)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                movie_elements = soup.select('div.result-item')
                if not movie_elements:
                    break
                for element in movie_elements:
                    title_tag = element.select_one('div.details div.title a')
                    if title_tag:
                        title = title_tag.text.strip()
                        link = title_tag['href']
                        if title and not any(exclude in title.lower() for exclude in ['©', 'all rights reserved']):
                            movie_count += 1
                            all_titles.append(f"{movie_count}. {title}")
                            movie_links.append(link)
                pagination = soup.find('div', class_='pagination')
                if not pagination or not pagination.find('a', class_='inactive'):
                    break
                page += 1
                time.sleep(3)
            except Exception as e:
                logger.error(f"Error scraping {site_name} page {page}: {e}")
                break

    elif site_name == "hdhub4u":
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive'
        }
        session = requests.Session()
        while True:
            url = base_url if page == 1 else f"{site_url}/page/{page}/?s={search_query}"
            try:
                response = session.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                movie_elements = soup.select('ul.recent-movies li')
                if not movie_elements:
                    break
                for element in movie_elements:
                    title_tag = element.select_one('figcaption p')
                    link_tag = element.select_one('figure a[href]')
                    if title_tag and link_tag:
                        title = title_tag.text.strip()
                        link = link_tag['href']
                        if title and not any(exclude in title.lower() for exclude in ['©', 'all rights reserved']):
                            movie_count += 1
                            all_titles.append(f"{movie_count}. {title}")
                            movie_links.append(link)
                pagination = soup.find('div', class_='pagination-wrap')
                if not pagination or not pagination.find('a', class_='next page-numbers'):
                    break
                page += 1
                time.sleep(3)
            except Exception as e:
                logger.error(f"Error scraping {site_name} page {page}: {e}")
                break

    elif site_name == "cinevood":
        scraper = cloudscraper.create_scraper()
        while True:
            url = base_url if page == 1 else f"{site_url}/page/{page}/?s={search_query}"
            try:
                response = scraper.get(url, timeout=10)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                movie_elements = soup.select('article.latestPost.excerpt')
                if not movie_elements:
                    break
                for element in movie_elements:
                    title_tag = element.select_one('h2.title.front-view-title a')
                    if title_tag:
                        title = title_tag.text.strip()
                        link = title_tag['href']
                        if title and not any(exclude in title.lower() for exclude in ['©', 'all rights reserved']):
                            movie_count += 1
                            all_titles.append(f"{movie_count}. {title}")
                            movie_links.append(link)
                pagination = soup.find('div', class_='pagination')
                if not pagination or not pagination.find('a', class_='next'):
                    break
                page += 1
                time.sleep(3)
            except Exception as e:
                logger.error(f"Error scraping {site_name} page {page}: {e}")
                break

    return all_titles, movie_links

# Scrape download links from a movie URL
def get_download_links(movie_url, site_name):
    download_links = []
    
    if site_name == "hdmovie2":
        scraper = cloudscraper.create_scraper()
        try:
            response = scraper.get(movie_url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            download_link_tags = soup.select('div.wp-content p a[href*="dwo.hair"]')
            if download_link_tags:
                download_page_url = download_link_tags[0]['href']
                response = scraper.get(download_page_url, timeout=10)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                for tag in soup.select('div.download-links-section p a[href]'):
                    link_text = tag.text.strip()
                    link_url = tag['href']
                    if link_text and link_url and not any(exclude in link_text.lower() for exclude in ['watch online', 'trailer']):
                        download_links.append(f"{link_text}: {link_url}")
        except Exception as e:
            logger.error(f"Error fetching download links for {site_name}: {e}")
            pass

    elif site_name == "hdhub4u":
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive'
        }
        try:
            response = requests.get(movie_url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            for tag in soup.select('h3 a[href], h4 a[href]'):
                link_text = tag.find('em').text.strip() if tag.find('em') else tag.text.strip()
                link_url = tag['href']
                if link_text and link_url and not any(exclude in link_text.lower() for exclude in ['watch online', 'trailer']):
                    download_links.append(f"{link_text}: {link_url}")
        except Exception as e:
            logger.error(f"Error fetching download links for {site_name}: {e}")
            pass

    elif site_name == "cinevood":
        scraper = cloudscraper.create_scraper()
        try:
            response = scraper.get(movie_url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            download_sections = soup.select('div.download-btns')
            for section in download_sections:
                description_tag = section.find('h6')
                link_tags = section.select('div.cat-btn-div2 a[href]')
                if description_tag and link_tags:
                    description = description_tag.text.strip()
                    if any(exclude in description.lower() for exclude in ['watch online', 'trailer']):
                        continue
                    for link_tag in link_tags:
                        link_text = link_tag.find('button').text.strip()
                        link_url = link_tag['href']
                        download_links.append(f"{description} [{link_text}]: {link_url}")
        except Exception as e:
            logger.error(f"Error fetching download links for {site_name}: {e}")
            pass

    return download_links

# Telegram bot handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("🚫 Unauthorized access. This bot is restricted.")
        return ConversationHandler.END
    await update.message.reply_text(
        "🎬 Welcome to the Movie Search Bot! 🎥\n"
        "Use /search to find a movie.\n"
        "Use /list_urls to view current site URLs.\n"
        "Use /update_url to change a site URL.\n"
        "Use /cancel to cancel any operation."
    )
    return ConversationHandler.END

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("🚫 Unauthorized access. This bot is restricted.")
        return ConversationHandler.END
    await update.message.reply_text("🎥 Please enter the movie name to search:")
    return SEARCH

async def receive_movie_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("🚫 Unauthorized access. This bot is restricted.")
        return ConversationHandler.END
    movie_name = update.message.text.strip()
    if not movie_name:
        await update.message.reply_text("❌ Please enter a valid movie name.")
        return SEARCH
    context.user_data['movie_name'] = movie_name
    config = load_config()
    all_titles = []
    all_links = []
    movie_count = 0

    for site_name, site_info in config['sites'].items():
        if not site_info['enabled']:
            continue
        try:
            titles, links = get_movie_titles_and_links(movie_name, site_name, site_info['url'])
            for title, link in zip(titles, links):
                movie_count += 1
                all_titles.append(f"{movie_count}. {title} (Source: {site_name})")
                all_links.append((site_name, link))
        except Exception as e:
            logger.error(f"Error processing site {site_name}: {e}")
            continue

    context.user_data['movie_links'] = all_links
    if not all_titles:
        await update.message.reply_text(
            "😔 No movies found. Possible reasons:\n"
            "- Check your movie name.\n"
            "- Websites may have blocked the request (try a VPN).\n"
            "- Site structure may have changed.\n"
            "Try again with /search."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "🎬 Movies found:\n\n" + "\n".join(all_titles) + "\n\nPlease enter the number of the movie to get download links:"
    )
    return SELECT_MOVIE

async def select_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("🚫 Unauthorized access. This bot is restricted.")
        return ConversationHandler.END
    try:
        selection = int(update.message.text.strip())
        movie_links = context.user_data.get('movie_links', [])
        if selection < 1 or selection > len(movie_links):
            await update.message.reply_text(f"❌ Please enter a number between 1 and {len(movie_links)}.")
            return SELECT_MOVIE
        site_name, movie_url = movie_links[selection - 1]
        download_links = get_download_links(movie_url, site_name)
        if download_links:
            await update.message.reply_text(
                f"📥 Download Links:\n\n" + "\n".join(download_links) + "\n\nSearch again with /search or use /cancel."
            )
        else:
            await update.message.reply_text(
                "😔 No download links found for the selected movie.\nSearch again with /search or use /cancel."
            )
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number.")
        return SELECT_MOVIE
    except Exception as e:
        logger.error(f"Error in select_movie: {e}")
        await update.message.reply_text("⚠️ An error occurred while fetching download links. Try again with /search.")
        return ConversationHandler.END

async def list_urls(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("🚫 Unauthorized access. This bot is restricted.")
        return
    config = load_config()
    urls = [f"{i+1}. {site_name}: {site_info['url']} (Enabled: {site_info['enabled']})"
            for i, (site_name, site_info) in enumerate(config['sites'].items())]
    await update.message.reply_text("🌐 Current site URLs:\n\n" + "\n".join(urls) + "\n\nUse /update_url to change a URL.")

async def update_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("🚫 Unauthorized access. This bot is restricted.")
        return ConversationHandler.END
    config = load_config()
    sites = list(config['sites'].keys())
    context.user_data['sites'] = sites
    site_list = [f"{i+1}. {site}" for i, site in enumerate(sites)]
    await update.message.reply_text(
        "🌐 Select the site to update the URL for:\n\n" + "\n".join(site_list) + "\n\nEnter the number:"
    )
    return UPDATE_URL

async def receive_url_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("🚫 Unauthorized access. This bot is restricted.")
        return ConversationHandler.END
    try:
        selection = int(update.message.text.strip())
        sites = context.user_data.get('sites', [])
        if selection < 1 or selection > len(sites):
            await update.message.reply_text(f"❌ Please enter a number between 1 and {len(sites)}.")
            return UPDATE_URL
        context.user_data['selected_site'] = sites[selection - 1]
        await update.message.reply_text(
            f"Enter the new URL for {sites[selection - 1]} (e.g., https://1cinevood.store):"
        )
        return UPDATE_URL
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number.")
        return UPDATE_URL

async def receive_new_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("🚫 Unauthorized access. This bot is restricted.")
        return ConversationHandler.END
    new_url = update.message.text.strip()
    if not new_url.startswith("https://"):
        await update.message.reply_text("❌ Please enter a valid URL starting with 'https://'.")
        return UPDATE_URL
    config = load_config()
    selected_site = context.user_data.get('selected_site')
    config['sites'][selected_site]['url'] = new_url
    save_config(config)
    await update.message.reply_text(
        f"✅ URL for {selected_site} updated to {new_url}.\nUse /list_urls to view URLs or /search to search again."
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("🚫 Unauthorized access. This bot is restricted.")
        return ConversationHandler.END
    await update.message.reply_text("✅ Operation cancelled. Use /search to start a new search or /list_urls to view URLs.")
    return ConversationHandler.END

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.message:
        await update.message.reply_text("⚠️ An error occurred. Please try again with /search or /list_urls.")
    else:
        logger.warning("No message available to reply to in error handler.")

# Health check handler for Railway
class HealthCheckHandler(RequestHandler):
    def get(self):
        self.write("OK")
        self.set_status(200)

def main():
    # Load Telegram bot token and webhook URL from environment variables
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    webhook_url = os.getenv("WEBHOOK_URL")
    
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN environment variable not set.")
        return
    if not webhook_url:
        logger.error("WEBHOOK_URL environment variable not set.")
        return

    # Ensure webhook_url ends with /webhook
    if not webhook_url.endswith("/webhook"):
        webhook_url = f"{webhook_url.rstrip('/')}/webhook"
        logger.info(f"Corrected webhook URL to: {webhook_url}")

    # Initialize Telegram bot with webhook
    try:
        application = (
            Application.builder()
            .token(bot_token)
            .build()
        )

        # Conversation handler for search
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('search', search)],
            states={
                SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_movie_name)],
                SELECT_MOVIE: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_movie)],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
        )

        # Conversation handler for updating URLs
        update_url_handler = ConversationHandler(
            entry_points=[CommandHandler('update_url', update_url)],
            states={
                UPDATE_URL: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, receive_url_selection),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, receive_new_url),
                ],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
        )

        # Add handlers
        application.add_handler(CommandHandler('start', start))
        application.add_handler(conv_handler)
        application.add_handler(CommandHandler('list_urls', list_urls))
        application.add_handler(update_url_handler)
        application.add_error_handler(error_handler)

        # Set up Tornado application for health check
        port = int(os.getenv("PORT", 8443))
        tornado_app = TornadoApp([
            (r"/health", HealthCheckHandler),
        ])

        # Set webhook
        logger.info(f"Setting webhook: {webhook_url}")
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            webhook_url=webhook_url,
            drop_pending_updates=True,
            url_path="/webhook"
        )
    except (Conflict, NetworkError, TimedOut) as e:
        logger.error(f"Webhook setup error: {e}")
        time.sleep(5)  # Wait before retrying
        main()  # Retry setting up webhook
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return

if __name__ == "__main__":
    main()