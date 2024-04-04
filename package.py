# BAPSicle Details
from json import loads
from helpers.os_environment import resolve_local_file_path

with open(resolve_local_file_path("package.json")) as file:
    config = loads(file.read())
    NAME: str = config["name"]
    NICE_NAME: str = config["nice_name"]
    DESCRIPTION: str = config["description"]
    AUTHOR: str = config["author"]
    LICENSE: str = config["license"]

    build_commit = "Dev"
    build_branch = "Local"
    build_beta = True
    try:
        import build

        build_commit = build.BUILD
        build_branch = build.BRANCH
        build_beta = build_branch != "release"
    except (ModuleNotFoundError, AttributeError):
        pass
    BUILD: str = build_commit
    BRANCH: str = build_branch
    BETA: bool = build_beta

    VERSION: str = config["version"] + "b" if BETA else config["version"]
