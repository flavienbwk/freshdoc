import fnmatch
import glob
import os
import re
import tempfile
import traceback
from multiprocessing import Process, Queue
from typing import List

from fastapi import FastAPI, Form, HTTPException, status
from freshdoc.helpers import (
    check_link_alive,
    clear_git_url_password,
    is_valid_branch_name,
    is_valid_url,
    md5_hash,
)
from freshdoc.RepoItem import RepoItem
from git import Repo as GitRepo


def format_options(
    repos_to_check: str = Form(...),
    ssl_verify: bool = Form(default=True),
    branches_to_check: str = Form(default=""),
    file_extensions: str = Form(default=""),
    excluded_directories: str = Form(default=""),
    check_dead_links: bool = Form(default=True),
    verbose: bool = Form(default=False),
):
    options = {
        "ssl_verify": ssl_verify,
        "verbose": verbose,
        "check_dead_links": check_dead_links,
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
    options["branches_to_check"] = list(set(valid_branches))

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


FD_REFS_PATTERN = r"<(fd:([a-zA-Z0-9_-]+):([0-9]+))>(?:[.\s]*-->)?(?:\s+?)?(.*)(?!</)(?:\s+?)?(?:<!--[.\s]*)</\1>{1}"
LINKS_PATTERN = (
    r"\b((?:https?):\/\/[\w-]+(\.[\w-]+)+([\w.,@?^=%&:/~+#-]*[\w@?^=%&/~+#-])?)"
)


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
        repo.add_comment(
            f"VERB: Processing following files : {str(file_list).replace(repo.work_dir, '')}"
        )
        references = []
        cleared_url = clear_git_url_password(repo.url)
        for file_path in file_list:
            with open(file_path, "r") as file:
                file_content = file.read()
                file_url = file_path.lstrip(repo.work_dir)
                matches_fd_refs = re.findall(FD_REFS_PATTERN, file_content, re.DOTALL)
                for match in matches_fd_refs:
                    reference = {
                        "name": match[1],
                        "version": int(match[2]),
                        "value": match[3],
                        "url": cleared_url,
                        "branch": repo.branch,
                        "file": file_url,
                        "hash": md5_hash(f"{match[3]}+{match[2]}"),
                    }
                    references.append(reference)

                if not repo.check_dead_links:
                    continue
                matches_links = re.findall(LINKS_PATTERN, file_content, re.DOTALL)
                dead_links = []
                for match in matches_links:
                    response_code = check_link_alive(match[0])
                    if response_code < 200 or response_code > 403:
                        dead_links.append(
                            {"link": match[0], "file": file_url, "code": response_code}
                        )
                repo.set_dead_links(dead_links)
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
            item.add_comment(f"ERROR: An error occured processing this repo : {str(e)}")
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
    check_dead_links: bool = Form(default=True),
    verbose: bool = Form(default=False),
):
    kwargs = locals().copy()
    options = format_options(**kwargs)

    # I/O queues for parallel process of repos
    input_queue = Queue()
    output_queue = Queue()

    # Build the multiprocess queue
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
                check_dead_links=options["check_dead_links"],
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
            if options["verbose"]:
                ncomment = f"[{cleared_url} / {item.branch}] {comment}"
                comments.append(ncomment)

    # Process references
    references_last_version = {}
    references_by_file = {}
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
            url_with_file_and_ref = f"{url_with_file}-{reference['hash']}"
            if reference["hash"] == references_by_name[ref_key]["hash"]:
                references_by_name[ref_key]["urls"].append(url_with_file)
            if not url_with_file_and_ref in references_by_file:
                references_by_file[url_with_file_and_ref] = {
                    "version": reference["version"],
                    "name": reference["name"],
                    "file": url_with_file,
                    "value": reference["value"],
                    "hash": reference["hash"],
                }

    # Watching for references with same name but not the latest version (WARN)
    for _, reference in references_by_name.items():
        if reference["version"] < references_last_version[reference["name"]]:
            ref_last_version_key = (
                f"{reference['name']}+{references_last_version[reference['name']]}"
            )
            ref_last_version = references_by_name[ref_last_version_key]
            comments.append(
                f"WARN: Reference \"{reference['name']}\" is outdated for files : {reference['urls']}. Current version is {reference['version']}. Last version is {ref_last_version['version']}, available on files : {ref_last_version['urls']}. Consider updating !"
            )

    # Watching for references with same name and version but different content (ERR)
    for _, reference in references_by_file.items():
        ref_key = f"{reference['name']}+{reference['version']}"
        reference_source = references_by_name[ref_key]
        if reference["hash"] != reference_source["hash"]:
            has_failed = True
            comments.append(
                f"ERROR: Reference mismatch. Reference \"{reference['name']}\" version {reference['version']} does not have the same content in file {reference['file']} and in files {reference_source['urls']}. Adjust references so they have the same content !"
            )

    # Process dead links
    for item in processed_repo_items:
        for link in item.dead_links:
            has_failed = True
            comments.append(
                f"ERROR: Dead link detected in file {link['file']} : {link['link']} responded with code {link['code']}"
            )

    if has_failed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=comments
        )
    return {"details": comments}
