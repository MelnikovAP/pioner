1. download rapberry pi image: https://downloads.raspberrypi.org/raspios_arm64/images/raspios_arm64-2021-11-08/
2. write image to SD card with: https://www.raspberrypi.com/software/
3. in the case of using 7" multitouch display add to config.txt: dtparam=i2c_vc_baudrate=50000
4. to use onscreen keyboard: $ sudo apt install onboard
and activate it with GUI. Also you can add the shortcut to the top pi panel
5. switch on raspberry pi, enter locale, password, etc.
6. activate SSH via: $ sudo raspi-config
7. enter the static ip address via: $ sudo nano /etc/dhcpcd.conf
For ESRF the settings will be: 
interface eth0
static ip_address=160.103.33.50/24
static routers=160.103.33.99
static domain_name_servers=160.103.209.9 160.103.208.9
8. $ sudo apt-update
9. $ sudo apt upgrade
10. $ sudo pip install numpy
11. $ sudo pip install six
12. $ sudo pip install Sphinx
13. $ sudo apt install mariadb-server
14. $ sudo apt install tango-db (from https://tango-controls.readthedocs.io/en/latest/installation/tango-on-raspberry-pi.html)
15. $ sudo apt install tango-starter tango-test liblog4j1.2-java
16. here https://gitlab.com/tango-controls/pytango the instructions does not work correctly. Use:
$ sudo apt install libboost-python-dev
$ sudo apt install libtango-dev
$ sudo apt install python3-tango

17. install DAQBoard libs https://github.com/MelnikovAP/nanocal/blob/master/README.md
18. configure git:
$ git config --global user.name "MelnikovAP"
$ git config --global user.email "melnikov.al.pe@gmail.com"
19. Download scripts from repository:
$ git clone https://github.com/MelnikovAP/nanocal.git
18. If mistake with acces to USB:
https://askubuntu.com/questions/978552/how-do-i-make-libusb-work-as-non-root
$ sudo nano /etc/udev/rules.d/90-usbpermission.rules
add there: SUBSYSTEM==“usb”,GROUP=“users”,MODE=“0666”


for nanocalorimetr script:
$ sudo pip install matplotlib
