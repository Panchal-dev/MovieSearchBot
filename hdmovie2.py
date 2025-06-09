import cloudscraper
from bs4 import BeautifulSoup
import time
from config import SITE_CONFIG, logger

def get_movie_titles_and_links(movie_name):
    search_query = f"{movie_name.replace(' ', '+').lower()}"
    base_url = f"https://{SITE_CONFIG['hdmovie2']}/?s={search_query}"
    scraper = cloudscraper.create_scraper()
    page = 1
    movie_count = 0
    all_titles = []
    movie_links = []

    while True:
        url = base_url if page == 1 else f"https://{SITE_CONFIG['hdmovie2']}/page/{page}/?s={search_query}"
        logger.debug(f"Fetching hdmovie2 page {page}: {url}")
        try:
            response = scraper.get(url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            movie_elements = soup.select('div.result-item')

            if not movie_elements:
                logger.info(f"No movie elements found on hdmovie2 page {page}")
                break

            for element in movie_elements:
                title_tag = element.select_one('div.details div.title a')
                if title_tag:
                    title = title_tag.text.strip()
                    link = title_tag['href']
                    if title and not any(exclude in title.lower() for exclude in ['©', 'all rights reserved']):
                        movie_count += 1
                        all_titles.append(f"{movie_count}. {title} (hdmovie2)")
                        movie_links.append(link)

            pagination = soup.find('div', class_='pagination')
            next_page = pagination.find('a', class_='inactive') if pagination else None
            if not next_page:
                break

            page += 1
            time.sleep(1)

        except Exception as e:
            logger.error(f"Error fetching hdmovie2 page {page}: {e}")
            break

    return all_titles, movie_links

def get_latest_movies():
    """Scrape the latest movies from hdmovie2's main page (no pagination)."""
    base_url = f"https://{SITE_CONFIG['hdmovie2']}/"
    scraper = cloudscraper.create_scraper()
    movie_count = 0
    all_titles = []
    movie_links = []

    url = base_url
    logger.debug(f"Fetching hdmovie2 latest movies: {url}")
    try:
        response = scraper.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        movie_elements = soup.select('div.result-item')

        if not movie_elements:
            logger.info(f"No movie elements found on hdmovie2 main page")
            return [], []

        for element in movie_elements:
            title_tag = element.select_one('div.details div.title a')
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
    scraper = cloudscraper.create_scraper()
    try:
        logger.debug(f"Fetching hdmovie2 movie page: {movie_url}")
        response = scraper.get(movie_url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        download_link_tags = soup.select('div.wp-content p a[href*="dwo.hair"]')

        if not download_link_tags:
            logger.info(f"No download page link found on {movie_url}")
            return []

        download_page_url = download_link_tags[0]['href']
        logger.debug(f"Fetching hdmovie2 download page: {download_page_url}")
        response = scraper.get(download_page_url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        download_links = []
        for tag in soup.select('div.download-links-section p a[href]'):
            link_text = tag.text.strip()
            link_url = tag['href']
            if link_text and link_url and not any(exclude in link_text.lower() for exclude in ['watch online', 'trailer']):
                download_links.append(f"{link_text}: {link_url}")

        logger.info(f"Fetched {len(download_links)} download links from hdmovie2")
        return download_links

    except Exception as e:
        logger.error(f"Error fetching hdmovie2 download links: {e}")
        return []