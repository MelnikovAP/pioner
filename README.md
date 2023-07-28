# PIONER Lab (Platform for Integrated Operative Nano Experiments and Research)  
*former Nanocal*0.9


## 1. Install MCC Universal Library for Linux (uldaq)

**Author:** Measurement Computing
The **uldaq** package contains programming libraries and components for developing applications using C/C++ on Linux and macOS Operating Systems. For more information please refer to [mccdaq github](https://github.com/mccdaq/uldaq)

## 2. Install the Python interface

Install the uldaq Python API with:  
 ```
   $ pip install uldaq
 ```
Refer to https://pypi.org/project/uldaq/ for more detailes.  
**Note:** sometimes one needs to change date on raspberry pi:
 ```
   $ sudo date -s "YYYY-MM-DD HH:MM:SS"
 ```

## 3. For developers
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

