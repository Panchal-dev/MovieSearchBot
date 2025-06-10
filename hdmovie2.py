import requests
from bs4 import BeautifulSoup
import time
from config import SITE_CONFIG, logger

def get_movie_titles_and_links(movie_name):
    """Search for movies on HDMovie2 (single page, no pagination)."""
    search_query = f"{movie_name.replace(' ', '+').lower()}"
    base_url = f"https://{SITE_CONFIG['hdmovie2']}/?s={search_query}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive'
    }
    session = requests.Session()
    all_titles = []
    movie_links = []

    logger.debug(f"Fetching hdmovie2 search: {base_url}")
    try:
        response = session.get(base_url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        # Target both featured and normal movie items
        movie_elements = soup.select('div.items.featured article.item.movies, div.items.normal article.item.movies')

        if not movie_elements:
            logger.info("No movie elements found on hdmovie2 search")
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

        logger.info(f"Fetched {len(all_titles)} titles from hdmovie2 search")
        return all_titles, movie_links

    except Exception as e:
        logger.error(f"Error fetching hdmovie2 search: {e}")
        return [], []

def get_latest_movies():
    """Fetch latest movies from HDMovie2's main page (single page, no pagination)."""
    base_url = f"https://{SITE_CONFIG['hdmovie2']}/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,xml/html',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive'
    }
    session = requests.Session()
    all_titles = []
    movie_links = []

    logger.debug(f"Fetching hdmovie2 latest movies: {base_url}")
    try:
        response = session.get(base_url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        # Target both featured and normal movie items
        movie_elements = soup.select('div.items.featured article.item.movies, div.items.normal article.item.movies')

        if not movie_elements:
            logger.info("No movie elements found on hdmovie2 main page")
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

        logger.info(f"Fetched {len(all_titles)} latest movies from hdmovie2")
        return all_titles, movie_links

    except Exception as e:
        logger.error(f"Error fetching hdmovie2 latest movies: {e}")
        return [], []

def get_download_links(movie_url):
    """Fetch download links from HDMovie2 movie page."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive'
    }
    session = requests.Session()
    try:
        logger.debug(f"Fetching hdmovie2 movie page: {movie_url}")
        response = session.get(movie_url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        download_links = []

        # Target all <a> tags within download sections
        download_sections = soup.select('div#links a[href], div.download-links a[href], p a[href]')
        for link_tag in download_sections:
            link_text = link_tag.text.strip()
            link_url = link_tag['href']
            if link_text and link_url and not any(exclude in link_text.lower() for exclude in ['watch online', 'trailer', 'telegram']):
                download_links.append(f"{link_text}: {link_url}")

        logger.info(f"Fetched {len(download_links)} download links from hdmovie2")
        return download_links

    except Exception as e:
        logger.error(f"Error fetching hdmovie2 download links: {e}")
        return []