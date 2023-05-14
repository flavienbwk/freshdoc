from typing import List


class RepoItem:

    error: bool = False  # Did an error occured processing this repo ?
    references: List[object] = []
    dead_links: List[object] = []
    work_dir: str = None  # Where repo is cloned locally
    comments: list = []

    def __init__(
        self,
        url: str,
        branch: str,
        file_extensions: List[str],
        excluded_directories: List[str],
        check_dead_links: bool = True,
        ssl_verify: bool = True,
    ):
        self.url = url
        self.branch = branch
        self.file_extensions = file_extensions
        self.excluded_directories = excluded_directories
        self.ssl_verify = ssl_verify
        self.check_dead_links = check_dead_links

    def set_url(self, url: str):
        self.url = url

    def set_references(self, refs: list):
        self.references = refs

    def set_dead_links(self, dead_links: list):
        self.dead_links = dead_links

    def set_error(self, err: bool):
        self.error = err

    def add_comment(self, msg: str):
        self.comments = self.comments + [msg]

    def __repr__(self) -> str:
        return (
            f"RepoItem: url={self.url}, branch={self.branch}, work_dir={self.work_dir}"
        )
