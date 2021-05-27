#!/usr/bin/env python3
from plistlib import load, dump
import package
import os
dir_path = os.path.dirname(os.path.realpath(__file__))

with open(dir_path + "/BAPSicle.template.platypus", 'rb') as temp:
    pl = load(temp)
    pl["Version"] = "{}~{}".format(package.VERSION, package.BUILD)
    pl["Name"] = package.NICE_NAME
    pl["StatusItemTitle"] = package.NICE_NAME
    pl["Author"] = package.AUTHOR
    pl["Identifier"] = "org.{}.{}".format(package.AUTHOR.lower().replace(" ", ""), package.NAME)

    with open(dir_path + "/BAPSicle.platypus", 'wb') as out:
        dump(pl, out)
