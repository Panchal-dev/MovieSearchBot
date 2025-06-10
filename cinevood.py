import cloudscraper
from bs4 import BeautifulSoup
import time
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_movie_titles_and_links(movie_name):
    """Search for movies on CineVood (up to 10 pages)."""
    search_query = f"{movie_name.replace(' ', '+').lower()}"
    base_url = f"https://1cinevood.asia/?s={search_query}"
    scraper = cloudscraper.create_scraper()
    page = 1
    max_pages = 10
    all_titles = []
    movie_links = []

    while page <= max_pages:
        url = base_url if page == 1 else f"https://1cinevood.asia/page/{page}/?s={search_query}"
        logger.debug(f"Fetching CineVood page {page}: {url}")
        try:
            response = scraper.get(url, timeout=10)
            response.raise_for_status()
            logger.info(f"Status code for page {page}: {response.status_code}")

            soup = BeautifulSoup(response.text, 'html.parser')
            movie_elements = soup.select('article.latestPost.excerpt')
            logger.info(f"Found {len(movie_elements)} movie elements on page {page}")

            if not movie_elements:
                logger.warning(f"No movie elements found on page {page}")
                with open(f"debug_page_{page}.html", "w", encoding="utf-8") as f:
                    f.write(response.text)
                logger.info(f"Saved page HTML to debug_page_{page}.html")
                break

            movie_count = len(all_titles)
            for element in movie_elements:
                title_tag = element.select_one('h2.title.front-view-title a')
                if title_tag:
                    title = title_tag.text.strip()
                    link = title_tag['href']
                    if title and not any(exclude in title.lower() for exclude in ['©', 'all rights reserved']):
                        movie_count += 1
                        all_titles.append(f"{movie_count}. {title} (cinevood)")
                        movie_links.append(link)

            pagination = soup.find('div', class_='pagination')
            next_page = pagination.find('a', class_='next') if pagination else None
            if not next_page or page == max_pages:
                logger.info(f"Stopping at page {page}")
                break

            page += 1
            time.sleep(3)

        except Exception as e:
            logger.error(f"Error fetching page {page}: {e}")
            break

    logger.info(f"Fetched {len(all_titles)} titles from CineVood search")
    return all_titles, movie_links

def get_latest_movies():
    """Fetch latest movies from CineVood's main pages (up to 10 pages)."""
    base_url = f"https://1cinevood.asia/"
    scraper = cloudscraper.create_scraper()
    page = 1
    max_pages = 10
    all_titles = []
    movie_links = []

    while page <= max_pages:
        url = base_url if page == 1 else f"https://1cinevood.asia/page/{page}/"
        logger.debug(f"Fetching CineVood latest movies page {page}: {url}")
        try:
            response = scraper.get(url, timeout=10)
            response.raise_for_status()
            logger.info(f"Status code for page {page}: {response.status_code}")

            soup = BeautifulSoup(response.text, 'html.parser')
            movie_elements = soup.select('article.latestPost.excerpt')
            logger.info(f"Found {len(movie_elements)} movie elements on page {page}")

            if not movie_elements:
                logger.warning(f"No movie elements found on page {page}")
                with open(f"debug_latest_page_{page}.html", "w", encoding="utf-8") as f:
                    f.write(response.text)
                logger.info(f"Saved page HTML to debug_latest_page_{page}.html")
                break

            movie_count = len(all_titles)
            for element in movie_elements:
                title_tag = element.select_one('h2.title.front-view-title a')
                if title_tag:
                    title = title_tag.text.strip()
                    link = title_tag['href']
                    if title and not any(exclude in title.lower() for exclude in ['©', 'all rights reserved']):
                        movie_count += 1
                        all_titles.append(f"{movie_count}. {title} (cinevood)")
                        movie_links.append(link)

            pagination = soup.find('div', class_='pagination')
            next_page = pagination.find('a', class_='next') if pagination else None
            if not next_page or page == max_pages:
                logger.info(f"Stopping at page {page}")
                break

            page += 1
            time.sleep(3)

        except Exception as e:
            logger.error(f"Error fetching latest movies page {page}: {e}")
            break

    logger.info(f"Fetched {len(all_titles)} latest movies from CineVood")
    return all_titles, movie_links

def get_download_links(movie_url):
    """Fetch download links from CineVood movie page."""
    scraper = cloudscraper.create_scraper()
    download_links = []

    logger.debug(f"Fetching CineVood movie page: {movie_url}")
    try:
        response = scraper.get(movie_url, timeout=10)
        response.raise_for_status()
        logger.info(f"Status code for movie page: {response.status_code}")

        soup = BeautifulSoup(response.text, 'html.parser')
        # Multiple selectors to capture all download links
        selectors = [
            'div.download-btns a[href]',
            'div.entry-content a[href]',
            'p a[href]',
            'div.cat-btn-div2 a[href]',
            'a.maxbutton a[href]'
        ]

        for selector in selectors:
            link_tags = soup.select(selector)
            for link_tag in link_tags:
                link_text = link_tag.text.strip()
                link_url = link_tag['href']
                if link_text and link_url and not any(exclude in link_text.lower() for exclude in ['watch online', 'trailer', 'telegram', 'join', 'home']):
                    # Extract description from h6 or parent
                    description = ""
                    parent_h6 = link_tag.find_previous('h6')
                    if parent_h6:
                        description = parent_h6.text.strip()
                    else:
                        description = link_text
                    if any(indicator in description.lower() for indicator in ['download', 'gdflix', 'filepress', '1080p', '720p', '480p', 'hd']):
                        download_links.append(f"{description} [{link_text}]: {link_url}")

        # Remove duplicates
        unique_links = list(dict.fromkeys(download_links))

        if not unique_links:
            logger.warning("No download links found on movie page")
            print.warning("No download page found on this page.")
            with open("debug_movie_page.html", "w", encoding="utf-8") as f:
                try:
                    f.write(response.text)
                    logger.info("Saved movie page HTML to debug_movie_page.html")
                except Exception as e:
                    logger.error(f"Failed to write debug file: {e}")

        logger.info(f"Fetched {len(unique_links)} download links from CineVood")
        return unique_links

    except Exception as e:
        logger.error(f"Error fetching movie page: {e}")
        return []