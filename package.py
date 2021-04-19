# BAPSicle Details
from json import loads
from helpers.os_environment import resolve_local_file_path

with open(resolve_local_file_path("package.json")) as file:
    config = loads(file.read())
    VERSION: str = config["version"]
    NAME: str = config["name"]
    NICE_NAME: str = config["nice_name"]
    DESCRIPTION: str = config["description"]
    AUTHOR: str = config["author"]
    LICENSE: str = config["license"]

    build_commit = "Dev"
    try:
        import build
        build_commit = build.BUILD
    except (ModuleNotFoundError, AttributeError):
        pass
    BUILD: str = build_commit
