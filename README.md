# crawly
**Crawly** is a Python tool for downloading scientific papers using Google Scholar, SciHub. The tool is divided into two part (scripts), *crawly.py* tries to download papers list from google scholar and save it in CSV file (Authors, Paper Title, Year, Publication, URL) and *sci-hub_downloader.py* tries to search papers using *Paper Title* on Scihub and downloads pdf on user system. 

## How to use
- Install required packages using *requirements.txt* (I would recommend to create a virtual python/conda environment)

      pip install requirements.txt
- Run *crawly.py* script to crawl(scrape) the google scholar for a given query

      python crawly.py
      
  - The script checks whether internet is connect or not, if connected then asks for user inputs like:
    - Keywords to search on google scholar (example: *object detection using machine learning*)
    - File name by which you want to create CSV file (example: *demo*)
    - Page range you want to scrape like 1-3 or 4-8 (example: *1-5*)*
    - Also asks for *optional input* whether you want to sort the papers year wise (*asc* for ascending order and *desc* for descending order) (example: *asc*)
   - After all inputs, the crawly will start crawling (scraping) through the google scholar pages.
   - Once done, it will save file as "file_name_page_range".csv (for example: demo_1-5.csv, as the file name given was demo)
   
- Run *scihub_downloader.py* to search and download papers from schi-hub using the created CSV file (**NOTE:** This script uses selenium, to automate the download process, However, we take user input after every 10 files).

      python scihub_downloader.py
 
 

#### To do
- Testing
- Code documentation
- General improvements
    - Add other sources for pdf download
    - Add summarization tool(script) for downloaded pdfs
    - Make scripts for robust against request blocks and other errors
    - Create proper pip package for easy use

#### Disclaimer
This application is for educational purposes only. I do not take responsibility for what you choose to do with this application.

#### Credits
- *crawly.py* script is modified version of *https://jovian.ai/saini-9* script for scraping google scholar.

#### Donation
If you like this project, you can give me a cup of tea :)

[![paypal](https://www.paypalobjects.com/en_US/i/btn/btn_donateCC_LG.gif)](paypal.me/lokeshsk755)
