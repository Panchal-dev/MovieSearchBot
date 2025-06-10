import requests
from bs4 import BeautifulSoup
import time
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_movie_titles_and_links(movie_name):
    """Search for movies on HDMovie2 (single page, no pagination)."""
    search_query = f"{movie_name.replace(' ', '+').lower()}"
    base_url = f"https://hdmovie2.trading/?s={search_query}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive'
    }
    session = requests.Session()
    all_titles = []
    movie_links = []

    logger.debug(f"Fetching HDMovie2 search: {base_url}")
    try:
        response = session.get(base_url, headers=headers, timeout=10)
        response.raise_for_status()
        logger.info(f"Status code for search: {response.status_code}")

        soup = BeautifulSoup(response.text, 'html.parser')
        # Target both featured and normal movie items
        movie_elements = soup.select('div.items.featured article.item.movies, div.items.normal article.item.movies')
        logger.info(f"Found {len(movie_elements)} movie elements")

        if not movie_elements:
            logger.warning("No movie elements found on search page")
            with open(f"debug_search_page.html", "w", encoding="utf-8") as f:
                f.write(response.text)
            logger.info("Saved search page HTML to debug_search_page.html")
            return [], []

        movie_count = 0
        for element in movie_elements:
            title_tag = element.select_one('div.data h3 a')
            if title_tag:
                title = title_tag.text.strip()
                link = title_tag['href']
                if title and not any(exclude in title.lower() for exclude in ['©', 'all rights reserved']):
                    movie_count += 1
                    all_titles.append(f"{movie_count}. {title} (hdmovie2)")
                    movie_links.append(link)

        logger.info(f"Fetched {len(all_titles)} titles from HDMovie2 search")
        return all_titles, movie_links

    except requests.RequestException as e:
        logger.error(f"Error fetching search page: {e}")
        return [], []

def get_latest_movies():
    """Fetch latest movies from HDMovie2's main page (single page)."""
    base_url = f"https://hdmovie2.trading/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive'
    }
    session = requests.Session()
    all_titles = []
    movie_links = []

    logger.debug(f"Fetching HDMovie2 latest movies: {base_url}")
    try:
        response = session.get(base_url, headers=headers, timeout=10)
        response.raise_for_status()
        logger.info(f"Status code for latest movies: {response.status_code}")

        soup = BeautifulSoup(response.text, 'html.parser')
        movie_elements = soup.select('div.items.featured article.item.movies, div.items.normal article.item.movies')
        logger.info(f"Found {len(movie_elements)} movie elements")

        if not movie_elements:
            logger.warning("No movie elements found on main page")
            with open(f"debug_latest_page.html", "w", encoding="utf-8") as f:
                f.write(response.text)
            logger.info("Saved main page HTML to debug_latest_page.html")
            return [], []

        movie_count = 0
        for element in movie_elements:
            title_tag = element.select_one('div.data h3 a')
            if title_tag:
                title = title_tag.text.strip()
                link = title_tag['href']
                if title and not any(exclude in title.lower() for exclude in ['©', 'all rights reserved']):
                    movie_count += 1
                    all_titles.append(f"{movie_count}. {title} (hdmovie2)")
                    movie_links.append(link)

        logger.info(f"Fetched {len(all_titles)} latest movies from HDMovie2")
        return all_titles, movie_links

    except requests.RequestException as e:
        logger.error(f"Error fetching latest movies: {e}")
        return [], []

def get_download_links(movie_url):
    """Fetch download links from HDMovie2 movie page."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive'
    }
    session = requests.Session()
    download_links = []

    logger.debug(f"Fetching HDMovie2 movie page: {movie_url}")
    try:
        response = session.get(movie_url, headers=headers, timeout=10)
        response.raise_for_status()
        logger.info(f"Status code for movie page: {response.status_code}")

        soup = BeautifulSoup(response.text, 'html.parser')
        # Broad selector to capture all possible download links
        link_tags = soup.select('div#links a[href], div.download-links a[href], div.entry-content a[href], p a[href]')
        for link_tag in link_tags:
            link_text = link_tag.text.strip()
            link_url = link_tag['href']
            if link_text and link_url and not any(exclude in link_text.lower() for exclude in ['watch online', 'trailer', 'telegram', 'join', 'home']):
                if any(indicator in link_text.lower() for indicator in ['download', 'gdflix', 'filepress', '1080p', '720p', '480p', 'hd']):
                    download_links.append(f"{link_text}: {link_url}")

        if not download_links:
            logger.warning("No download links found on movie page")
            with open("debug_movie_page.html", "w", encoding="utf-8") as f:
                f.write(response.text)
            logger.info("Saved movie page HTML to debug_movie_page.html")

        logger.info(f"Fetched {len(download_links)} download links from HDMovie2")
        return download_links

    except requests.RequestException as e:
        logger.error(f"Error fetching movie page: {e}")
        return []