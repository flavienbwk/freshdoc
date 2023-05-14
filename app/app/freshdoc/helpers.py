import re
import requests
import traceback
from urllib.parse import urlparse, urlunparse

def check_link_alive(url):
    try:
        response = requests.head(url)
        return response.status_code
    except requests.exceptions.RequestException:
        traceback.print_exc()
    return -1

def is_valid_url(url: str) -> bool:
    pattern = r"^https?://(?:[a-zA-Z0-9]+:[a-zA-Z0-9]+@)?(?:[a-zA-Z0-9-]+\.)*[a-zA-Z0-9-]+(?::\d+)?(?:\/(?:[^\s/]+\/)*[^\s/]+\.git)?"
    return re.match(pattern, url) is not None


def clear_git_url_password(url):
    parsed = urlparse(url)
    new_netloc = parsed.hostname
    if parsed.port:
        new_netloc += f":{parsed.port}"
    if parsed.username:
        new_netloc = f"{parsed.username}@{new_netloc}"
    new_url = urlunparse(
        (
            parsed.scheme,
            new_netloc,
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )

    return new_url


def is_valid_branch_name(name: str) -> bool:
    pattern = r"^[a-zA-Z0-9-_./]+$"
    return re.match(pattern, name)
