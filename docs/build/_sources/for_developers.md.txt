# For developers

## Package structure
```
- package main folder
    - .env                  # python3 environment
    - data                  # folder to save experimental and test data
    - dist                  # buit packages to upload to PyPi.org
    - docs  
        - build
            ...
            index.html      # can be used to view docs locally after building
            ...
        - source            # source documentation
            ...
            - _static       # figures and logos for docs
            - ...           # *.md and *.rst files with documentation code
            conf.py         # Sphinx file with docs build settings
            ... 
        ...
        requirements.txt    # requirements to build documentation
        ...
    - settings  # folder with *.json files - calibrations and settings
    - src                   # source code. refer to API docs
        - pioner
            - assets        # figures and logos for GUI
                __init__.py # points that this folder should be included in build
                ...
            - back          # backend server part
                __init__.py # points that this folder should be included in build
                ...
            - front         # frontend part with GUI
                __init__.py # points that this folder should be included in build
                ...
            - settings      # default settings and calibrations in *.json files
                __init__.py # points that this folder should be included in build
                ...
            - shared        # code shared between front and back
                __init__.py # points that this folder should be included in build
                ...
            __init__.py     # points that this folder should be included in build
            ...
    .readthedocs.yaml       # configuration file to sync with readthedocs
    LICENSE                 # license file, MIT
    pyproject.toml          # configuration file for build
    README.md               # github description page
```


## Build commands 
First install build library to the selected working environment:
```
$ python -m venv .env
$ source .env/bin/activate
$ pip install --upgrade pip
$ pip install build 
```
To build and install current package locally to the selected envirionment, use commands (from the directory with configured `pyproject.toml` file):
```
$ python -m build
$ pip install -e . # in editable mode (develop mode)
$ pip install -e ".[gui]" # if there is subpackage named "gui"
$ pip install -e ".[server]" # if there is subpackage named "server"
```
To upload to PyPi.org:
```
$ pip install twine
$ twine upload dist/*
```

---

## Hybrid documentation build notes
[RST cheatsheet](https://sphinx-tutorial.readthedocs.io/cheatsheet/) & [Markdown cheatsheet](https://www.markdownguide.org/cheat-sheet/)  
To use *.rst and *.md files with autodocumentation function, install:
```
$ pip install sphinx
$ pip install myst-parser
```
To access to package structure during docs building, add to `conf.py` in the beginning:
```
import os
import sys
sys.path.insert(0, os.path.abspath('.'))
sys.path.insert(0, os.path.abspath('../'))
sys.path.insert(0, os.path.abspath('../..'))
sys.path.insert(0, os.path.abspath('../../src/'))
sys.path.insert(0, os.path.abspath('../../src/pioner/'))
```
To activate *.md support and autodocumentation with Numpy/Google style add to `conf.py`:
```
extensions = [ 
    'myst_parser',
    'sphinx.ext.doctest',
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
]
```
To activate readthedocs theme on local docs build add to `conf.py`:
```
html_theme = 'sphinx_rtd_theme'
```
**NOTE**  
For proper integration with readthedocs.io all the dependencies of the package should be included into `docs/requirements.txt file`  


If some packages cannot be installed during readthedocs build add to `conf.py`:
```
autodoc_mock_imports = [
    'uldaq',
    'pytango',
    ...
]
```
To use autodocumentation use docstrings in the code as described [here](https://sphinxcontrib-napoleon.readthedocs.io/en/latest/)  

To build docs locally use the command:
```
$ sphinx-build docs/source docs/build
```
and open `docs/build/index.html` to view documentation.

---


## Optional GIT notes
[Source code on GitHub](https://github.com/MelnikovAP/pioner)  
To configure git use:
```
$ git config --global user.name "username"
$ git config --global user.email "email"
$ git clone https://github.com/MelnikovAP/pioner pioner
```

---

## Tango notes
For testing Tango on Windows:
- Install Java from [here](https://www.java.com/en/download/)  
- Install Tango from [here](https://www.tango-controls.org/downloads/)  
- Set enviroment variable `TANGO_HOST='raspberrypi:10000'`
- Add to path `C:\Program Files\tango\bin`  

For full featured use of Tango on Raspberry Pi (to launch Jive & Astor) install Java 8 on Debian following [procedures](https://linuxize.com/post/install-java-on-debian-10/)
```
$ pip install numpy six Sphinx pytango 
```

---
## Additional hints and notes
If mistake with acces to USB use following [solution](https://askubuntu.com/questions/978552/how-do-i-make-libusb-work-as-non-root):
```
$ sudo nano /etc/udev/rules.d/90-usbpermission.rules
```
add there: 
```
SUBSYSTEM==“usb”,GROUP=“users”,MODE=“0666”
```
---
  
TO DO: think about auto installation on Raspberry using script
or using script & [Anaconda libs](https://anaconda.org/tango-controls/repo)

---
  
There could be a problem with X11 forwarding on VS Code.    
To fix id generate ssh key with: 
```
$ ssh-keygen -p -m PEM 
```
Install vscode extension on pi (from VS Code desktop application after connecting via ssh)  
Add to `~/.bashrc` & `~/.profile` the following: 
```
export DISPLAY="localhost:10.0$DISPLAY"
```
---

For uldaq API refer to the [UL documentation](
https://www.mccdaq.com/PDFs/Manuals/UL-Linux/python/index.html)
