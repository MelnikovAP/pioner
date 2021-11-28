# Nanocal


## MCC Universal Library for Linux (uldaq)
[![Coverity Scan Build Status](https://scan.coverity.com/projects/16116/badge.svg)](https://scan.coverity.com/projects/uldaq)

**Info:** Contains a library to access and control supported Measurement Computing [DAQ devices](https://www.mccdaq.com/PDFs/Manuals/Linux-hw.pdf) over the Linux and macOS platforms. The UL for Linux binary name is libuldaq.

**Author:** Measurement Computing

## About
The **uldaq** package contains programming libraries and components for developing applications using C/C++ on Linux and macOS Operating Systems. An API (Application Programming Interface) for interacting with the library in Python is available as an additional installation. This package was created and is supported by MCC. 

### Prerequisites:
---------------
Building the **uldaq** package requires C/C++ compilers, make tool, and the development package for libusb. The following describes how these prerequisites can be installed on different Linux distributions and macOS.
  
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

### Build Instructions
---------------------

1. Download the latest version of **uldaq**:

```
  Linux
     $ wget -N https://github.com/mccdaq/uldaq/releases/download/v1.2.0/libuldaq-1.2.0.tar.bz2

  macOS
     $ curl -L -O https://github.com/mccdaq/uldaq/releases/download/v1.2.0/libuldaq-1.2.0.tar.bz2
``` 
2. Extract the tar file:
 
```
  $ tar -xvjf libuldaq-1.2.0.tar.bz2
```
  
3. Run the following commands to build and install the library:

```
  $ cd libuldaq-1.2.0
  $ ./configure && make
  $ sudo make install
```

**Note:** To install the Python interface, follow the above [build instructions](#build-instructions) then go to https://pypi.org/project/uldaq/ for further installation.
  
### Examples
The C examples are located in the examples folder. Run the following commands to execute the analog input example: 

```
  $ cd examples
  $ ./AIn
```
Refer to the **uldaq** [PyPI](https://pypi.org/project/uldaq/) page for instructions on installing Python examples.
install
