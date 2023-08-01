# Installation
---
## 1. Backend installation (on Raspberry Pi)
### 1.1. Raspberry Pi configuration
#### 1.1.1(a) In case of using Pi-top:
   - Download [Pi-top image](https://www.pi-top.com/resources/download-os) and write image to SD card with [Raspberry Pi Imager](https://www.raspberrypi.com/software/) or 
   [Etcher](https://www.balena.io/etcher/)
   - Switch on pi-top
   - Activate SSH with pi-top screen and buttons
   - Find ip address on pi-top display
   - Now you can connect via ssh, default password is "pi-top": 
   ```
      $ ssh -X pi@{ip_address} 
   ```
#### 1.1.1(b) In case of using standard Raspberry Pi:  
   - Download [Rapberry Pi image](https://downloads.raspberrypi.org/raspios_arm64/images/) 
   for arm64 and write image to SD card with 
   [Raspberry Pi Imager](https://www.raspberrypi.com/software/) or 
   [Etcher](https://www.balena.io/etcher/)
   - For using 7" multitouch display add to /config.txt: 
   ```
      dtparam=i2c_vc_baudrate=50000
   ```
   - Switch on Raspberry Pi, enter locale, password, etc.  
   - Activate SSH via raspi-config:
   ```
      $ sudo raspi-config
   ```
   - To use onscreen keyboard install onboard and activate it with GUI. Also you can add the shortcut to the top pi panel: 
   ```
      $ sudo apt install onboard
   ```
#### 1.1.2. Configuration
   - Connect via ssh:
   ```
   ssh -X pi@{ipaddrress}
   ```
   - Set the static ip address in: 
   ```
   $ sudo nano /etc/dhcpcd.conf
   ```
   - Maybe one needs to change time and date:  
   ```
   $ sudo date -s 'YYYY-MM-DD HH:MM:SS'
   ```
   - Update all the packages:
   ```
   $ sudo apt update  
   $ sudo apt upgrade
   ```
   - Change the password:
   ```
   passwd
   ```
   - Change hostname:
   ```
   sudo nano /etc/hostname
   sudo nano /etc/hosts
   ```
### 1.2. Install MCC Universal Library for Linux (uldaq)
**Author:** Measurement Computing
The **uldaq** package contains programming libraries and components for developing applications using C/C++ on Linux and macOS Operating Systems. An API (Application Programming Interface) for interacting with the library in Python is available as an additional installation. This package was created and is supported by MCC. For more information please refer to [mccdaq github](https://github.com/mccdaq/uldaq)

   - Building the **uldaq** package requires C/C++ compilers, make tool, and the development package for libusb. The following describes how these prerequisites can be installed on different Linux distributions and macOS.

   ```
      $ sudo apt-get install gcc g++ make
      $ sudo apt-get install libusb-1.0-0-dev
   ```

   - Download and extract the latest version of **uldaq**:

   ```
      $ wget -N https://github.com/mccdaq/uldaq/releases/download/v1.2.1/libuldaq-1.2.1.tar.bz2
      $ tar -xvjf libuldaq-1.2.1.tar.bz2
   ``` 
   - Run the following commands to build and install the library:

   ```
      $ cd libuldaq-1.2.1
      $ ./configure && make
      $ sudo make install
   ```
### 1.3. Install uldaq Python interface
   - Install the uldaq Python API with:  
   ```
      $ pip install uldaq
   ```
   - Refer to https://pypi.org/project/uldaq/ for more detailes.  
   **Note:** sometimes one needs to change date on raspberry pi:
   ```
      $ sudo date -s "YYYY-MM-DD HH:MM:SS"
   ```
### 1.4. Installing Pioner libraries
   ```
   $ pip install pioner
   $ pip install pioner[server]
   ```
### 1.5. Installing Tango server
   - The following packages need to be installed for Tango server:
   ```
      $ pip install numpy six Sphinx
      $ sudo apt install g++ mariadb-server libmariadb-dev zlib1g-dev libomniorb4-dev libcos4-dev omniidl libzmq3-dev make
   ```
   - Launch database:  
   ```
      $ sudo service mariadb start
   ```
   - Install [Pi Tango server](https://tango-controls.readthedocs.io/en/latest/installation/tango-on-raspberry-pi.html):
   ``` 
      $ sudo apt install tango-db
   ```
   - enter host and port (raspberrypi:10000); configure db -> Yes; password - empty  
   - Install the following Tango libraries:
   ``` 
      $ sudo apt install tango-starter tango-test liblog4j1.2-java  
   ```
   - Install PyTango. The official [instructions](https://gitlab.com/tango-controls/pytango) does not work correctly. Use:
   ```
      $ sudo apt install libboost-python-dev libtango-dev python3-tango
   ```
   - Graphic tools (Jive, Astor,…) installation. Download the latest version of libtango-java librairies on [picaa](https://people.debian.org/~picca/) and install it:
   ```
      wget -c https://people.debian.org/~picca/libtango-java_XX_version.deb\
      sudo dpkg -i ./libtango-java_XX_version.deb
   ```
   - if there is a problem with the last command, use 
   ```
      sudo apt install tango-starter tango-test liblog4j1.2-java
      sudo apt --fix-broken install
      sudo dpkg -i ./libtango-java_XX_version.deb
   ```  
   - Install java 8 and set is as default java (Tango graphic tools are working only with java 8!!):
   ```
      sudo apt-get install openjdk-8-jdk
      sudo update-alternatives --config java
      java -version
   ```
### 1.6. Configuration of Tango server
   - Install PionerControl server to Tango:
   ```
      jive&
   ```
   - In Jive Tools -> Server wizard -> Server name: PionerControl; Instance name: PionerControl  
   - Run server from /nanical_pi:  
   **!!! Change here!!!!**
   ```
      python nanocontrol_tango.py NanoControl
   ```
   - In Jive Server wizard continue: Declare -> NanoControl/NanoControl/1 
   - Install supervisor for Tango server auto-start:  
   ```
      sudo apt install supervisor
      supervisord --version
   ```
   - Configure Supervisor. Edit /etc/supervisor/supervisord.conf. Add the following:  
   Attention! change TANGO_HOST to connect to another tango database, e.g. ID13 ESRF:  
   ```environment = TANGO_HOST="lid13ctrl1.esrf.fr:20000"``` or remove ths line  
   ```
   [inet_http_server]
   port = <ip>:9001
   username = pi
   password = tonic13

   [program:nanocontrol_tango]
   directory = /home/pi/nanocal_pi
   command = python back/nanocontrol_tango.py NanoControl
   environment = TANGO_HOST="lid13ctrl1.esrf.fr:20000"
   stdout_logfile = /home/pi/nanocal_pi/logs/supervisor_nanocontrol_tango.log
   stderr_logfile= /home/pi/nanocal_pi/logs/supervisor_nanocontrol_tango.err
   autostart = true
   startsecs = 5
   autorestart = true
   user = pi

   [program:nanocontrol_http]
   directory = /home/pi/nanocal_pi
   command = python -m http.server
   stdout_logfile = /home/pi/nanocal_pi/logs/supervisor_nanocontrol_http.log
   stderr_logfile= /home/pi/nanocal_pi/logs/supervisor_nanocontrol_http.err
   autostart = true
   startsecs = 5
   autorestart = true
   user = pi
   ```
   ```
   sudo systemctl enable supervisor --now
   sudo systemctl status supervisor
   sudo systemctl restart supervisor
   sudo supervisorctl reload
   sudo supervisorctl status
   ```
## 2. Frontend installation
### 2.1. Install uldaq Python interface
   - Install the uldaq Python API with:  
   ```
      $ pip install uldaq
   ```
   - Refer to https://pypi.org/project/uldaq/ for more detailes.  
   **Note:** sometimes one needs to change date on raspberry pi:
   ```
      $ sudo date -s "YYYY-MM-DD HH:MM:SS"
   ```
### 2.2. Installing Pioner libraries
   ```
   $ pip install pioner
   ```
   - To use GUI:
   ```
   $ pip install pioner[GUI]
   ```
## 3. Bliss installation
