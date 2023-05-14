import fnmatch
import glob
import hashlib
import os
import re
import tempfile
import traceback
from multiprocessing import Process, Queue
from typing import List
from urllib.parse import urlparse, urlunparse

from fastapi import FastAPI, Form, HTTPException, status
from git import Repo as GitRepo


class RepoItem:

    error: bool = False  # Did an error occured processing this repo ?
    references: List[object] = []
    work_dir: str = None  # Where repo is cloned locally
    comments: list = []

    def __init__(
        self,
        url: str,
        branch: str,
        file_extensions: List[str],
        excluded_directories: List[str],
        ssl_verify: bool = True,
    ):
        self.url = url
        self.branch = branch
        self.file_extensions = file_extensions
        self.excluded_directories = excluded_directories
        self.ssl_verify = ssl_verify

    def set_url(self, url: str):
        self.url = url

    def set_references(self, refs: list):
        self.references = refs

    def set_error(self, err: bool):
        self.error = err

    def add_comment(self, msg: str):
        self.comments = self.comments + [msg]

    def __repr__(self) -> str:
        return f"RepoItem: url={self.url}, branch={self.branch}, nb_references={len(self.references_by_name)}, work_dir={self.work_dir}, nb_comments={len(self.comments)}"


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


def format_options(
    repos_to_check: str = Form(...),
    ssl_verify: bool = Form(default=True),
    branches_to_check: str = Form(default=""),
    file_extensions: str = Form(default=""),
    excluded_directories: str = Form(default=""),
):
    options = {
        "ssl_verify": ssl_verify,
        "repos_to_check": [],
        "branches_to_check": [],
        "file_extensions": [],
        "excluded_directories": [],
        "comments": [],
    }

    if isinstance(repos_to_check, str):
        repos_to_check = repos_to_check.split(",")
    validated_urls = []
    for url in repos_to_check:
        if is_valid_url(url.strip()):
            validated_urls.append(url.strip())
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid option repos_to_check. Invalid repo URL : {url}",
            )
    options["repos_to_check"] = validated_urls

    valid_branches = []
    for branch in branches_to_check.split(","):
        if is_valid_branch_name(branch):
            valid_branches.append(branch)
        else:
            options["comments"].append(
                f'WARN: Invalid branch name "{branch}". Skipped.'
            )
    if not valid_branches:
        valid_branches = ["main", "master", "develop"]
    options["branches_to_check"] = valid_branches

    if excluded_directories:
        excluded_directories = excluded_directories.split(",")
        excluded_directories = [
            directory.strip() for directory in excluded_directories if directory.strip()
        ]
        invalid_directories = [
            directory
            for directory in excluded_directories
            if not fnmatch.translate(directory)
        ]
        if invalid_directories:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"The following excluded directories are not in glob format: {', '.join(invalid_directories)}",
            )
        options["excluded_directories"] = excluded_directories

    options["file_extensions"] = [ext for ext in file_extensions.split(",") if ext]
    if not options["file_extensions"]:
        if file_extensions:
            options["comments"].append(
                f'WARN: No valid file extension to analyze found. Using default ones ("md", "txt").'
            )
        options["file_extensions"] = ["md", "txt"]
    return options


def md5_hash(string):
    hash_object = hashlib.md5()
    hash_object.update(string.encode("utf-8"))
    hash_string = hash_object.hexdigest()
    return hash_string


def list_files_with_extension(path: str, extension: str, excluded_dirs: list = []):
    search_pattern = os.path.join(path, f"*.{extension}")
    file_list = glob.glob(search_pattern)
    excluded_files = []
    for exclude_dir in excluded_dirs:
        excluded_files.extend(glob.glob(os.path.join(path, exclude_dir)))
    file_list = [file for file in file_list if file not in excluded_files]
    return file_list


def git_clone(
    url: str,
    to_path: str,
    ssl_verify: bool = True,
) -> GitRepo:
    os.environ["GIT_SSL_NO_VERIFY"] = "0" if ssl_verify else "1"
    gitrepo = GitRepo.clone_from(url=url, to_path=to_path)
    os.environ["GIT_SSL_NO_VERIFY"] = "0"
    return gitrepo


FD_REFS_PATTERN = r"<(fd:([a-zA-Z0-9_-]+):([0-9]+))>(?:[.\s]*-->)?(?:\s+?)?(.*)(?:\s+?)?(?:<!--[.\s]*)</\1>"


def process_repo(repo: RepoItem) -> RepoItem:
    """Processes the retrieval of Freshdoc references in the provided repo."""
    with tempfile.TemporaryDirectory() as temp_dir_path:
        repo.work_dir = temp_dir_path
        gitrepo = git_clone(
            url=repo.url,
            to_path=repo.work_dir,
            ssl_verify=repo.ssl_verify,
        )
        try:
            gitrepo.git.checkout(repo.branch)
        except:
            repo.add_comment(f"WARN: No branch {repo.branch} found in repo. Skipping.")
            return repo
        file_list = []
        for extension in repo.file_extensions:
            ext_file_list = list_files_with_extension(
                repo.work_dir, extension, repo.excluded_directories
            )
            file_list = file_list + ext_file_list
            if not len(ext_file_list):
                repo.add_comment(
                    f"VERB: No file with extension {extension} found in repo."
                )
        repo.add_comment(f"VERB: Processing following files : {str(file_list)}")
        references = []
        cleared_url = clear_git_url_password(repo.url)
        for file_path in file_list:
            with open(file_path, "r") as file:
                file_content = file.read()
                matches = re.findall(FD_REFS_PATTERN, file_content, re.DOTALL)
                for match in matches:
                    reference = {
                        "name": match[1],
                        "version": int(match[2]),
                        "value": match[3],
                        "url": cleared_url,
                        "branch": repo.branch,
                        "file": file_path.lstrip(repo.work_dir),
                        "hash": md5_hash(f"{match[3]}+{match[2]}"),
                    }
                    references.append(reference)
        repo.set_references(references)
    return repo


def worker(input_queue, output_queue):
    while True:
        item: RepoItem = input_queue.get()
        if item is None:
            break
        try:
            item = process_repo(item)
        except Exception as e:
            item.set_error(True)
            item.add_comment(f"ERR: An error occured processing this repo : {str(e)}")
            traceback.print_exc()
        output_queue.put(item)


app = FastAPI()


@app.post("/check")
async def check(
    repos_to_check: str = Form(...),
    ssl_verify: bool = Form(default=True),
    branches_to_check: str = Form(default=""),
    file_extensions: str = Form(default=""),
    excluded_directories: str = Form(default=""),
):
    kwargs = locals().copy()
    options = format_options(**kwargs)

    # I/O queues for parallel process of repos
    input_queue = Queue()
    output_queue = Queue()

    processes = []
    num_processes = 4
    for _ in range(num_processes):
        p = Process(target=worker, args=(input_queue, output_queue))
        p.start()
        processes.append(p)

    # Cloning each repo and each branch independently
    for repo in options["repos_to_check"]:
        for branch in options["branches_to_check"]:
            item = RepoItem(
                url=repo,
                branch=branch,
                file_extensions=options["file_extensions"],
                excluded_directories=options["excluded_directories"],
                ssl_verify=options["ssl_verify"],
            )
            input_queue.put(item)

    for _ in range(num_processes):
        input_queue.put(None)

    for p in processes:
        p.join()

    processed_repo_items: List[RepoItem] = []
    while not output_queue.empty():
        processed_repo = output_queue.get()
        processed_repo_items.append(processed_repo)

    comments: list = []
    has_failed: bool = False
    for item in processed_repo_items:
        cleared_url = clear_git_url_password(item.url)
        if item.error:
            has_failed = True
        for comment in item.comments:
            ncomment = f"[{cleared_url} / {item.branch}] {comment}"
            comments.append(ncomment)

    # Process references
    references_last_version = {}
    references_by_name = {}
    for item in processed_repo_items:
        if item.error:
            continue
        for reference in item.references:
            if not reference:
                continue
            ref_key = f"{reference['name']}+{reference['version']}"
            if ref_key not in references_by_name:
                references_by_name[ref_key] = {
                    "version": reference["version"],
                    "name": reference["name"],
                    "value": reference["value"],
                    "urls": [],
                    "hash": reference["hash"],
                }
            if (
                reference["name"] not in references_last_version
                or reference["version"] > references_last_version[reference["name"]]
            ):
                references_last_version[reference["name"]] = reference["version"]
            url_with_file = (
                f"{reference['url']}/-/blob/{reference['branch']}/{reference['file']}"
            )
            references_by_name[ref_key]["urls"].append(url_with_file)

    # Watching for references with same name but not the latest version (WARN)
    for reference_name, reference in references_by_name.items():
        if reference["version"] < references_last_version[reference["name"]]:
            ref_last_version_key = (
                f"{reference['name']}+{references_last_version[reference['name']]}"
            )
            ref_last_version = references_by_name[ref_last_version_key]
            comments.append(
                f"WARN: Reference \"{reference['name']}\" is outdated for files : {reference['urls']}. Current version : \"{reference['version']}\". Last version : \"{ref_last_version['version']}\" available on files : {ref_last_version['urls']}. Consider updating !"
            )

    # Watching for references with same name and version but different content (ERR)

    return comments

    return [repo.references for repo in processed_repo_items if repo.references]

    if has_failed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=comments,
        )
    return comments
