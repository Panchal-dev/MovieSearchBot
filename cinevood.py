import cloudscraper
from bs4 import BeautifulSoup
import time
from config import SITE_CONFIG, logger

def get_movie_titles_and_links(movie_name):
    search_query = f"{movie_name.replace(' ', '+').lower()}"
    base_url = f"https://{SITE_CONFIG['cinevood']}/?s={search_query}"
    scraper = cloudscraper.create_scraper()
    page = 1
    movie_count = 0
    all_titles = []
    movie_links = []

    while True:
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
            if not next_page:
                break

            page += 1
            time.sleep(1)

        except Exception as e:
            logger.error(f"Error fetching cinevood page {page}: {e}")
            break

    return all_titles, movie_links

def get_download_links(movie_url):
    scraper = cloudscraper.create_scraper()
    try:
        logger.debug(f"Fetching cinevood movie page: {movie_url}")
        response = scraper.get(movie_url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        download_links = []

        # Try existing structure: div.download-btns
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

        # If no links found, try new structure: h6 followed by maxbutton links
        if not download_links:
            h6_tags = soup.select('h6')
            for h6 in h6_tags:
                description = h6.text.strip()
                if any(exclude in description.lower() for exclude in ['watch online', 'trailer']):
                    continue
                # Find the next <a> tag with maxbutton class after the h6
                next_a = h6.find_next('a', class_='maxbutton')
                if next_a and 'href' in next_a.attrs:
                    link_url = next_a['href']
                    link_text = next_a.find('span', class_='mb-text').text.strip() if next_a.find('span', class_='mb-text') else 'Download'
                    download_links.append(f"{description} [{link_text}]: {link_url}")

        logger.info(f"Fetched {len(download_links)} download links from cinevood")
        return download_links

    except Exception as e:
        logger.error(f"Error fetching cinevood download links: {e}")
        return []