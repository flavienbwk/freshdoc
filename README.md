# Freshdoc

<p align="center">
    <img src="./logo.png" width="196px" />
</p>

Keep code and text snippets in sync across your git repos.

Useful to track any evolving info stored in your documentations, such as **team members' names**, **phone numbers**, **e-mail addresses** or **server IPs** across your repos.

## Features

- Check for non-identical markdown snippets accross repos
- Detect dead links
- Integrates with any git repo
- Callable through [curl](https://curl.se/)

## Usage

Wrap text or code to be tracked in a markdown comment including a Freshdoc reference tag.

```markdown
# My incredible documentation

## Support

Current team includes :
<!-- <fd:customer_support_team:1> -->
- Juliet CAPULET
- Antigone THEBAN
- Jean VALJEAN
<!-- </fd:customer_support_team:1> -->

Phone number : <!-- <fd:phone_cs:1> -->+33900000001<!-- </fd:phone_cs:1> -->

```

### For GitLab CI

Now you can use it in your [GitLab CI](https://docs.gitlab.com/ee/ci/variables/predefined_variables.html) with _curl_ :

```yaml
stages:
    - test

freshdoc:
    stage: test
    script: 
        - curl --request POST \
            --header "Content-Type: application/x-www-form-urlencoded" \
            --data-urlencode "username=${GITLAB_USER_LOGIN}" \
            --data-urlencode "password=${CI_JOB_TOKEN}" \
            --data-urlencode "ssl_verify=true" \
            --data-urlencode "repos_to_check=group1,group2" \
            --data-urlencode "branches_to_check=main,master,develop" \
            --data-urlencode "file_extensions=md,txt" \
            --data-urlencode "excluded_directories=node_modules/**" \
            http://localhost:8080/check
```

- A `200` HTTP code will be returned if no problem was encountered, `400` else.
- Body with eventually include a detailed list of problems to solve.

| Key                                                                                                            | Value description                                                                                                               |
| -------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| USERNAME                                                                                                       | Required. Username with which the repo can be cloned (over HTTPS)                                                               |
| PASSWORD                                                                                                       | Required. Password or token with which the repo can be cloned (over HTTPS)                                                      |
| REPOS_TO_CHECK                                                                                                 | Required. List of repo URLs to track references. Delimited by commas.                                                           |
| BRANCHES_TO_CHECK                                                                                              | Default: "main,master,develop". List of branches to track references. Delimited by commas. Unexistant branches will be skipped. |
| [SSL_VERIFY](https://stackoverflow.com/questions/11621768/how-can-i-make-git-accept-a-self-signed-certificate) | "true" (default) or "false". Enable or disable git clone command's SSL verification for provided repos.                         |
| FILE_EXTENSIONS                                                                                                | Default: "md,txt". Commas-delimited list of file extensions in which Freshdoc will check for references.                        |
| EXCLUDED_DIRECTORIES                                                                                           | No default value. Commas-delimited list of glob patterns indicating which directory to ignore for all provided repos.           |

## Start server

Using Docker and docker-compose :

```bash
docker-compose up --build -d
```

API will be available on port `8080` by default.

## Syntax

The Freshdoc tag is composed of 3 items. Let's take an example :

```markdown
<!-- <fd:ref_name:1> -->
text
<!-- </fd:ref_name:1> -->
```

- `fd` is for identifying a Freshdoc tag in a markdown file
- `ref_name` is a small name to identify the snippet to track
- `1` is the version of your snippet to make it upgradable

## Upgrading a reference

Let's say you have two repos A and B to keep in sync. To upgrade a reference, increase its version number in repo A, commit and push.

Now-on, any push in repo B will trigger an error until the value of the reference and its version are upgraded.

Increase this same number to match the same value from repo A in repo B.
