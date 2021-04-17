#!/bin/bash
if [ "$1" == "" ]
then
    echo "DISABLED|BAPSicle Server"
        echo "----"
        if curl --output /dev/null --silent --head --fail --max-time 1 "http://localhost:13500"
		then
            echo "Presenter"
            echo "Server"
            echo "----"
			echo "Stop Server"
        else
            echo "DISABLED|Presenter"
            echo "DISABLED|Server"
            echo "----"
            echo "Start Server"
		fi
    exit
fi
if [ "$1" == "Stop Server" ]
then
	curl "http://localhost:13500/quit"
else
	./BAPSicle "$1"
fi
