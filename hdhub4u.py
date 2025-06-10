import requests
from bs4 import BeautifulSoup
import time
from config import SITE_CONFIG, logger

def get_movie_titles_and_links(movie_name):
    search_query = f"{movie_name.replace(' ', '+').lower()}"
    base_url = f"https://{SITE_CONFIG['hdhub4u']}/?s={search_query}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive'
    }
    session = requests.Session()
    page = 1
    max_pages = 10
    movie_count = 0
    all_titles = []
    movie_links = []

    while page <= max_pages:
        url = base_url if page == 1 else f"https://{SITE_CONFIG['hdhub4u']}/page/{page}/?s={search_query}"
        logger.debug(f"Fetching hdhub4u page {page}: {url}")
        try:
            response = session.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            movie_elements = soup.select('li.thumb')

            if not movie_elements:
                logger.info(f"No movie elements found on hdhub4u page {page}")
                break

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
                logger.info(f"Stopping at page {page} (max_pages reached or no next page)")
                break

            page += 1
            time.sleep(1)

        except Exception as e:
            logger.error(f"Error fetching hdhub4u page {page}: {e}")
            break

    logger.info(f"Fetched {len(all_titles)} titles from hdhub4u search")
    return all_titles, movie_links

def get_latest_movies():
    """Fetch latest movies from hdhub4u's main pages (up to 10 pages)."""
    base_url = f"https://{SITE_CONFIG['hdhub4u']}/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive'
    }
    session = requests.Session()
    page = 1
    max_pages = 10
    movie_count = 0
    all_titles = []
    movie_links = []

    while page <= max_pages:
        url = base_url if page == 1 else f"https://{SITE_CONFIG['hdhub4u']}/page/{page}/"
        logger.debug(f"Fetching hdhub4u latest movies page {page}: {url}")
        try:
            response = session.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            movie_elements = soup.select('li.thumb')

            if not movie_elements:
                logger.info(f"No movie elements found on hdhub4u page {page}")
                break

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
                logger.info("Stopping at page {page} (max_pages reached or no next page)")
                break

            page += 1
            time.sleep(1)

        except Exception as e:
            logger.error(f"Error fetching hdhub4u latest movies page {page}: {e}")
            break

    logger.info(f"Fetched {len(all_titles)} latest movies from hdhub4u")
    return all_titles, movie_links

def get_download_links(movie_url):
    """Fetch download links from HDHub4U movie page."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive'
    }
    session = requests.Session()
    try:
        logger.debug(f"Fetching hdhub4u movie page: {movie_url}")
        response = session.get(movie_url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        download_links = []

        # Target all <a> tags within download content
        download_sections = soup.select('div.entry-content a[href], div.download-links a[href], p a[href]')
        for link_tag in download_sections:
            link_text = link_tag.text.strip()
            link_url = link_tag['href']
            if link_text and link_url and not any(exclude in link_text.lower() for exclude in ['watch online', 'trailer', 'telegram']):
                download_links.append(f"{link_text}: {link_url}")

        logger.info(f"Fetched {len(download_links)} download links from hdhub4u")
        return download_links

    except Exception as e:
        logger.error(f"Error fetching hdhub4u download links: {e}")
        return []