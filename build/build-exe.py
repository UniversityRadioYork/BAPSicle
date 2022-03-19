import json
from helpers.os_environment import isLinux

file = open('build-exe-config.json', 'r')
config = json.loads(file.read())
file.close()

if isLinux():
    cmd_str = "python3 -m PyInstaller "
else:
    cmd_str = "pyinstaller "

json_dests = ["icon_file", "clean_build"]
pyi_dests = ["icon", "clean"]

filename = ""

for option in config["pyinstallerOptions"]:

    option_dest = option["optionDest"]

    # The json is rather inconsistent :/
    if option_dest in json_dests:
        option_dest = pyi_dests[json_dests.index(option_dest)]

    option_dest = option_dest.replace("_", "-")

    if option_dest == "datas":
        cmd_str += '--add-data "' + option["value"] + '" '
    elif option_dest == "filenames":
        filename = option["value"]
    elif option["value"] is True:
        cmd_str += "--" + str(option_dest) + " "
    elif option["value"] is False:
        pass
    else:
        cmd_str += "--" + str(option_dest) + ' "' + str(option["value"]) + '" '


for format in [".bat", ".sh"]:
    command = open('build-exe-pyinstaller-command'+format, 'w')

    if filename == "":
        print("No filename data was found in json file.")
        command.write("")
    else:
        command.write(cmd_str + ' --distpath "output/" --workpath "build/" "' + filename + '"')

    command.close()
