import fnmatch
import re
from urllib.parse import urlparse

from fastapi import FastAPI, Form, HTTPException, status

app = FastAPI()


def is_valid_url(url: str) -> bool:
    parsed_url = urlparse(url)
    if parsed_url.scheme and parsed_url.netloc:
        return True
    return False


def is_valid_branch_name(name: str) -> bool:
    pattern = r"^[a-zA-Z0-9-_./]+$"
    return re.match(pattern, name)


@app.post("/check")
async def check(
    username: str = Form(...),
    password: str = Form(...),
    repos_to_check: str = Form(...),
    ssl_verify: bool = Form(default=True),
    branches_to_check: str = Form(default=""),
    file_extensions: str = Form(default=""),
    excluded_directories: str = Form(default=""),
):
    options = {
        "username": username,
        "password": password,
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
