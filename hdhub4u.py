import requests
from bs4 import BeautifulSoup
import time
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_movie_titles_and_links(movie_name):
    """Search for movies on HDHub4U (up to 10 pages)."""
    search_query = f"{movie_name.replace(' ', '+').lower()}"
    base_url = f"https://hdhub4u.gratis/?s={search_query}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive'
    }
    session = requests.Session()
    page = 1
    max_pages = 10
    all_titles = []
    movie_links = []

    while page <= max_pages:
        url = base_url if page == 1 else f"https://hdhub4u.gratis/page/{page}/?s={search_query}"
        logger.debug(f"Fetching HDHub4U page {page}: {url}")
        try:
            response = session.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            logger.info(f"Status code for page {page}: {response.status_code}")

            soup = BeautifulSoup(response.text, 'html.parser')
            # Updated selector to match typical HDHub4U structure
            movie_elements = soup.select('li.thumb')
            logger.info(f"Found {len(movie_elements)} movie elements on page {page}")

            if not movie_elements:
                logger.warning(f"No movie elements found on page {page}")
                with open(f"debug_page_{page}.html", "w", encoding="utf-8") as f:
                    f.write(response.text)
                logger.info(f"Saved page HTML to debug_page_{page}.html")
                break

            movie_count = len(all_titles)
            for element in movie_elements:
                title_tag = element.select_one('figcaption a')
                if title_tag:
                    title = title_tag.text.strip()
                    link = title_tag['href']
                    if title and not any(exclude in title.lower() for exclude in ['©', 'all rights reserved']):
                        movie_count += 1
                        all_titles.append(f"{movie_count}. {title} (hdhub4u)")
                        movie_links.append(link)

            pagination = soup.find('div', class_='pagination')
            next_page = pagination.find('a', class_='next') if pagination else None
            if not next_page or page == max_pages:
                logger.info(f"Stopping at page {page}")
                break

            page += 1
            time.sleep(3)

        except requests.RequestException as e:
            logger.error(f"Error fetching page {page}: {e}")
            break

    logger.info(f"Fetched {len(all_titles)} titles from HDHub4U search")
    return all_titles, movie_links

def get_latest_movies():
    """Fetch latest movies from HDHub4U's main pages (up to 10 pages)."""
    base_url = f"https://hdhub4u.gratis/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive'
    }
    session = requests.Session()
    page = 1
    max_pages = 10
    all_titles = []
    movie_links = []

    while page <= max_pages:
        url = base_url if page == 1 else f"https://hdhub4u.gratis/page/{page}/"
        logger.debug(f"Fetching HDHub4U latest movies page {page}: {url}")
        try:
            response = session.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            logger.info(f"Status code for page {page}: {response.status_code}")

            soup = BeautifulSoup(response.text, 'html.parser')
            movie_elements = soup.select('li.thumb')
            logger.info(f"Found {len(movie_elements)} movie elements on page {page}")

            if not movie_elements:
                logger.warning(f"No movie elements found on page {page}")
                with open(f"debug_latest_page_{page}.html", "w", encoding="utf-8") as f:
                    f.write(response.text)
                logger.info(f"Saved page HTML to debug_latest_page_{page}.html")
                break

            movie_count = len(all_titles)
            for element in movie_elements:
                title_tag = element.select_one('figcaption a')
                if title_tag:
                    title = title_tag.text.strip()
                    link = title_tag['href']
                    if title and not any(exclude in title.lower() for exclude in ['©', 'all rights reserved']):
                        movie_count += 1
                        all_titles.append(f"{movie_count}. {title} (hdhub4u)")
                        movie_links.append(link)

            pagination = soup.find('div', class_='pagination')
            next_page = pagination.find('a', class_='next') if pagination else None
            if not next_page or page == max_pages:
                logger.info(f"Stopping at page {page}")
                break

            page += 1
            time.sleep(3)

        except requests.RequestException as e:
            logger.error(f"Error fetching latest movies page {page}: {e}")
            break

    logger.info(f"Fetched {len(all_titles)} latest movies from HDHub4U")
    return all_titles, movie_links

def get_download_links(movie_url):
    """Fetch download links from HDHub4U movie page."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive'
    }
    session = requests.Session()
    download_links = []

    logger.debug(f"Fetching HDHub4U movie page: {movie_url}")
    try:
        response = session.get(movie_url, headers=headers, timeout=10)
        response.raise_for_status()
        logger.info(f"Status code for movie page: {response.status_code}")

        soup = BeautifulSoup(response.text, 'html.parser')
        # Broad selector to capture download links
        link_tags = soup.select('div.entry-content a[href], div.download-links a[href], p a[href], div.post-content a[href]')
        for link_tag in link_tags:
            link_text = link_tag.text.strip()
            link_url = link_tag['href']
            if link_text and link_url and not any(exclude in link_text.lower() for exclude in ['watch online', 'trailer', 'telegram', 'join', 'home', 'how to download']):
                if any(indicator in link_text.lower() for indicator in ['download', 'gdflix', 'filepress', '1080p', '720p', '480p', 'hd']):
                    download_links.append(f"{link_text}: {link_url}")

        if not download_links:
            logger.warning("No download links found on movie page")
            with open("debug_movie_page.html", "w", encoding="utf-8") as f:
                f.write(response.text)
            logger.info("Saved movie page HTML to debug_movie_page.html")

        logger.info(f"Fetched {len(download_links)} download links from HDHub4U")
        return download_links

    except requests.RequestException as e:
        logger.error(f"Error fetching movie page: {e}")
        return []