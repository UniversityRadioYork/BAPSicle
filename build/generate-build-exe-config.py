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
        option["value"] = os.path.abspath(parent_path + option["value"])
        if not isWindows():
            option["value"] = option["value"].replace(";",":")

out_file = open('build-exe-config.json', 'w')
out_file.write(json.dumps(config, indent=2))
out_file.close()
