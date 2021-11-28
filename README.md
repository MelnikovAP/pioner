# Nanocal


## 1. Install MCC Universal Library for Linux (uldaq)

**Author:** Measurement Computing

### About
The **uldaq** package contains programming libraries and components for developing applications using C/C++ on Linux and macOS Operating Systems. For more information please refer to [mccdaq github](https://github.com/mccdaq/uldaq)
  
  - Debian-based Linux distributions such as Ubuntu, Raspbian
  
  ```
     $ sudo apt-get install gcc g++ make
     $ sudo apt-get install libusb-1.0-0-dev
  ```
  - Arch-based Linux distributions such as Manjaro, Antergos
  
  ```
     $ sudo pacman -S gcc make
     $ sudo pacman -S libusb
  ```
  - Red Hat-based Linux distributions such as Fedora, CentOS
  
  ```
     $ sudo yum install gcc gcc-c++ make
     $ sudo yum install libusbx-devel
  ``` 
  - OpenSUSE 
  
  ```
     $ sudo zypper install gcc gcc-c++ make
     $ sudo zypper install libusb-devel
  ```
  - macOS (Version 10.11 or later recommended)
  
  ```
     $ xcode-select --install
     $ ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"
     $ brew install libusb
  ```

## 2. Install the Python interface

Install the uldaq Python API with:  
 ```
   $ pip install uldaq
 ```
**Note:** Installation may need to be run with sudo.  
Refer to https://pypi.org/project/uldaq/ for more detailes.
