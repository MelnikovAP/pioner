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
8. 
