import cloudscraper
from bs4 import BeautifulSoup
import time
from config import SITE_CONFIG, logger

def get_movie_titles_and_links(movie_name):
    """Search movies on CineVood (up to 10 pages)."""
    search_query = f"{movie_name.replace(' ', '-')}".lower()
    base_url = f"https://{SITE_CONFIG['cinevood']}/?s={search_query}"
    scraper = cloudscraper.create_scraper()
    page = 1
    max_pages = 10
    movie_count = 0
    all_titles = []
    movie_links = []

    while page <= max_pages:
        url = base_url if page == 1 else f"https://{SITE_CONFIG['cinevood']}/page/{page}/?s={search_query}"
        logger.debug(f"Fetching cinevood page {page}: {url}")
        try:
            response = scraper.get(url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            movie_elements = soup.select('article.latestPost.excerpt')

            if not movie_elements:
                logger.info(f"No movie elements found on cinevood page {page}")
                break

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
                logger.info(f"Stopping at page {page} (max_pages reached or no next page)")
                break

            page += 1
            time.sleep(1)

        except Exception as e:
            logger.error(f"Error fetching cinevood page {page}: {e}")
            break

    logger.info(f"Fetched {len(all_titles)} titles from cinevood search")
    return all_titles, movie_links

def get_latest_movies():
    """Fetch latest movies from CineVood's main pages (up to 10 pages)."""
    base_url = f"https://{SITE_CONFIG['cinevood']}/"
    scraper = cloudscraper.create_scraper()
    page = 1
    max_pages = 10
    movie_count = 0
    all_titles = []
    movie_links = []

    while page <= max_pages:
        url = base_url if page == 1 else f"https://{SITE_CONFIG['cinevood']}/page/{page}/"
        logger.debug(f"Fetching cinevood latest movies page {page}: {url}")
        try:
            response = scraper.get(url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            content_box = soup.find('div', id='content_box')
            if not content_box:
                logger.info(f"No content_box found on cinevood page {page}")
                break

            movie_elements = content_box.select('article.latestPost.excerpt')
            if not movie_elements:
                logger.info(f"No movie elements found on cinevood page {page}")
                break

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
                logger.info(f"Stopping at page {page} (max_pages reached or no next page)")
                break

            page += 1
            time.sleep(1)

        except Exception as e:
            logger.error(f"Error fetching cinevood latest movies page {page}: {e}")
            break

    logger.info(f"Fetched {len(all_titles)} latest movies from cinevood")
    return all_titles, movie_links

def get_download_links(movie_url):
    """Fetch download links from CineVood movie page."""
    scraper = cloudscraper.create_scraper()
    download_links = []  # Initialize the list
    
    try:
        logger.debug(f"Fetching cinevood movie page: {movie_url}")
        response = scraper.get(movie_url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Try multiple selectors for download links
        selectors = [
            'div.download-btns a[href]',  # Primary download buttons
            'div.entry-content a[href]',   # Links in content
            'p a[href]',                   # Links in paragraphs
            'div.cat-btn-div2 a[href]'     # Alternative button divs
        ]

        for selector in selectors:
            link_tags = soup.select(selector)
            for link_tag in link_tags:
                link_text = link_tag.text.strip()
                link_url = link_tag['href']
                if link_text and link_url and not any(exclude in link_text.lower() for exclude in ['watch online', 'trailer', 'telegram']):
                    # Try to find associated description
                    description = ""
                    parent_h6 = link_tag.find_previous('h6')
                    if parent_h6:
                        description = parent_h6.text.strip()
                    elif link_tag.find_parent('div', class_='download-btns'):
                        description_tag = link_tag.find_parent('div').find('h6')
                        description = description_tag.text.strip() if description_tag else link_text
                    else:
                        description = f"{description} [{link_text}]" if description else link_text
                    download_links.append(f"{description}: {link_url}")

        # Also check for maxbutton links
        max_buttons = soup.select('a.maxbutton')
        for button in max_buttons:
            link_text = button.find('span', class_='mb-text').text.strip() if button.find('span', class_='mb-text') else 'Download'
            link_url = button['href']
            description_parent = button.find_previous('h6')
            description = description_parent.text.strip() if description_parent else link_text
            if not any(exclude in description.lower() or exclude in link_text.lower() for exclude in ['watch online', 'trailer', 'telegram']):
                download_links.append(f"{description} [{link_text}]: {link_url}")

        # Remove duplicates while preserving order
        unique_links = []
        seen = set()
        for link in download_links:
            if link not in seen:
                seen.add(link)
                unique_links.append(link)

        logger.info(f"Fetched {len(unique_links)} download links from cinevood")
        return unique_links

    except Exception as e:
        logger.error(f"Error fetching cinevood download links: {e}")
        return []