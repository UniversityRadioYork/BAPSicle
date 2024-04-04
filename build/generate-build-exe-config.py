import json
import os
from helpers.os_environment import isWindows

dir_path = os.path.dirname(os.path.realpath(__file__))
parent_path = os.path.dirname(dir_path)

in_file = open('build-exe-config.template.json', 'r')
config = json.loads(in_file.read())
in_file.close()

for option in config["pyinstallerOptions"]:
    if option["optionDest"] in ["datas", "filenames", "icon_file"]:
        # If we wanted a relative output directory, this will go missing in abspath on windows.
        relative_fix = False
        split = option["value"].split(";")
        if len(split) > 1 and split[1] == "./":
            relative_fix = True

        option["value"] = os.path.abspath(parent_path + option["value"])
        if not isWindows():
            option["value"] = option["value"].replace(";", ":")
        elif relative_fix:
            # Add the windows relative path.
            option["value"] += "./"

out_file = open('build-exe-config.json', 'w')
out_file.write(json.dumps(config, indent=2))
out_file.close()
