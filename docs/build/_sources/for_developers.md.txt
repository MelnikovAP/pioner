
# For developers
Refer to the UL documentation:
https://www.mccdaq.com/PDFs/Manuals/UL-Linux/python/index.html


python -m venv .env
source .env/bin/activate
pip install --upgrade pip
pip install build 

python -m build
pip install -e .
pip install -e ".[gui]"
pip install -e ".[server]"





## Optional

- Configure git:
```
$ git config --global user.name "username"
$ git config --global user.email "email"
```

- If mistake with acces to USB:
https://askubuntu.com/questions/978552/how-do-i-make-libusb-work-as-non-root
$ sudo nano /etc/udev/rules.d/90-usbpermission.rules
add there: SUBSYSTEM==“usb”,GROUP=“users”,MODE=“0666”

## For testing Tango on Windows
- Install Java from [here](https://www.java.com/en/download/)  
- Install Tango from [here](https://www.tango-controls.org/downloads/)  
- Set enviroment variable TANGO_HOST='raspberrypi:10000'  
- Add to path C:\Program Files\tango\bin  
```
pip install numpy six Sphinx pytango 
```



???
https://anaconda.org/tango-controls/repo

think about auto installation on raspberry using script



Installing Java 8 on Debian (to launch jive):
https://linuxize.com/post/install-java-on-debian-10/


There could be a problem with X11 forwarding on VScode.    
To fix id generate ssh key with: ssh-keygen -p -m PEM  
and install vscode extension on pi  
and add to ~/.bashrc & ~/.profile the following: export DISPLAY="localhost:10.0$DISPLAY"
