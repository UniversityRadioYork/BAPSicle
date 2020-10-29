import sys
import json

file = open('build-exe-config.json', 'r')
config = json.loads(file.read())
file.close()

cmd_str = "pyinstaller "
json_dests = ["icon_file", "clean_build"]
pyi_dests = ["icon", "clean"]

for option in config["pyinstallerOptions"]:

    option_dest = option["optionDest"]

    # The json is rather inconsistent :/
    if option_dest in json_dests:
        print("in")
        option_dest = pyi_dests[json_dests.index(option_dest)]

    option_dest = option_dest.replace("_", "-")

    if option_dest == "datas":
        cmd_str += '--add-data "' + option["value"] + '" '
    elif option_dest == "filenames":
        filename = option["value"]
    elif option["value"] == True:
        cmd_str += "--" + str(option_dest) + " "
    elif option["value"] == False:
        pass
    else:
        cmd_str += "--" + str(option_dest) + ' "' + str(option["value"]) + '" '


command = open('build-exe-pyinstaller-command.bat', 'w')

if filename == "":
    print("No filename data was found in json file.")
    command.write("")
else:
    command.write(cmd_str + ' --distpath "output/" --workpath "build/" "' + filename + '"')

command.close()
