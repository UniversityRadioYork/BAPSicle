import json
import os

dir_path = os.path.dirname(os.path.realpath(__file__))
parent_path = os.path.dirname(dir_path)

in_file = open('build-exe-config.template.json', 'r')
config = json.loads(in_file.read())
in_file.close()

for option in config["pyinstallerOptions"]:
    if option["optionDest"] == "icon_file":
        option["value"] = dir_path + option["value"]
    if option["optionDest"] == "datas":
        option["value"] = parent_path + option["value"]

out_file = open('build-exe-config.json', 'w')
out_file.write(json.dumps(config, indent=2))
out_file.close()
