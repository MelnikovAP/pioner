1. Download rapberry pi [image](https://downloads.raspberrypi.org/raspios_arm64/images/raspios_arm64-2021-11-08/) for arm64 and write image to SD card with [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
2. In the case of using 7" multitouch display add to /config.txt: 
```
dtparam=i2c_vc_baudrate=50000
```
3. To use onscreen keyboard install onboard: 
```
$ sudo apt install onboard
```
and activate it with GUI. Also you can add the shortcut to the top pi panel  
4. Switch on raspberry pi, enter locale, password, etc.
5. Activate SSH via raspi-config:
```
$ sudo raspi-config
```
6. Set the static ip address via: 
```
$ sudo nano /etc/dhcpcd.conf
```
For ESRF the settings will be: 
```
interface eth0
static ip_address=160.103.33.50/24
static routers=160.103.33.99
static domain_name_servers=160.103.209.9 160.103.208.9
```
7. Update all the packages:
```
$ sudo apt-update  
$ sudo apt upgrade
```
8. The following packages need to be installed for Tango server:
```
$ sudo pip install numpy
$ sudo pip install six
$ sudo pip install Sphinx
$ sudo apt install mariadb-server
```
9. Install [Pi Tango server](https://tango-controls.readthedocs.io/en/latest/installation/tango-on-raspberry-pi.html):
``` 
$ sudo apt install tango-db  
$ sudo apt install tango-starter  
$ sudo apt install tango-test  
$ sudo apt install liblog4j1.2-java  
```
10. Install PyTango. The official [instructions](https://gitlab.com/tango-controls/pytango) does not work correctly. Use:
```
$ sudo apt install libboost-python-dev  
$ sudo apt install libtango-dev  
$ sudo apt install python3-tango  
```
11. install DAQBoard libs, follow the [instructions](https://github.com/MelnikovAP/nanocal/blob/master/README.md)
12. configure git:
```
$ git config --global user.name "MelnikovAP"
$ git config --global user.email "melnikov.al.pe@gmail.com"
```
13. Download scripts from repository:
```
$ git clone https://github.com/MelnikovAP/nanocal.git
```
18. If mistake with acces to USB:
https://askubuntu.com/questions/978552/how-do-i-make-libusb-work-as-non-root
$ sudo nano /etc/udev/rules.d/90-usbpermission.rules
add there: SUBSYSTEM==“usb”,GROUP=“users”,MODE=“0666”


for nanocalorimetr script:
$ sudo pip install matplotlib
