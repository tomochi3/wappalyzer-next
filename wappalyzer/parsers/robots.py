from urllib.parse import urlparse

def get_robots(fetcher, url):
    scheme = urlparse(url).scheme
    hostname = urlparse(url).hostname
    robots_url = f'{scheme}://{hostname}/robots.txt'
    r = fetcher.get(robots_url)
    return r.text if r else ''