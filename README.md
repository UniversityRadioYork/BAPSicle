# BAPSicle
### a.k.a. The Next-Gen BAPS server

!["BAPSicle logo, a pink melting ice lolly."](/dev/logo.png "BAPSicle Logo")

Welcome! This is BAPS. More acurately, this is yet another attempt at a BAPS3 server.

## Installing

Just want to install BAPSicle?

### Windows

Currently there's just a batch script. Simply run ``install.bat`` as administrator. If you've just built BAPSicle yourself, it'll be in the ``/install`` folder.

This will:
* Copy BAPSicle into ``C:\Program Files\BAPSicle``
* Install BAPSicle.exe as a Windows Service with NSSM.
* If all goes well, open [http://localhost:5000](localhost:5000) for the server UI.

### Linux

Installed service for linux is comming soon. Testing is primarily on Ubuntu 20.04. Your milage with other distros will vary.

### MacOS

Support for MacOS will be the last to come, sorry about that.

## Developing

### Requirements

* Python 3.7 (3.8 may also work, 3.9 is unlikely to.)
* Git (Obviously)

### Running
To just run the server standaline without installing, run ``python ./launch_standalone.py``.

### Building

Currently mostly Windows focused.

To build a BAPSicle.exe, run ``build\build-exe.py``. The resulting file will appear in ``build\output``. You can then use the install instructions above to install it, or just run it standalone.

### Other bits

Provided is a VScode debug config to let you debug live, as well as ``dev\install-githook.bat`` that will help git to clean your code up as you're committing!
