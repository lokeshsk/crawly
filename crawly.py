#!/usr/bin/env python
# coding: utf-8

# In[1]:

"""Need to install packages pandas and tqdm"""

# import the liberary
import requests
from time import sleep
import re
import pandas as pd
from bs4 import BeautifulSoup
from tqdm import tqdm
import urllib.request
from fake_useragent import UserAgent
ua = UserAgent()
# In[2]:
fake_ua = ua.random

"""
headers = {
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36"
}
"""
headers = {
    "user-agent": fake_ua
}
print(headers)

def connect(host='http://google.com'):
    try:
        urllib.request.urlopen(host) #Python 3.x
        return True
    except:
        return False
# test
print("Checking whether internet is available or not...")
print( "internet connected" if connect() else "no internet! check you internet connection" )



# In[3]:


def get_paperinfo(paper_url):

    # download the page
    response = requests.get(url, headers=headers)

    # check successful response

    if(response.status_code == 200):
    # parse using beautiful soup
        paper_doc = BeautifulSoup(response.text, "html.parser")
    else:
        if(response.status_code == 429):
            #raise Exception("Failed to fetch web page ")
            #print("Google Scholar is blocking us, need to cool down")
            return response.status_code
        else:
            print("Status code:", response.status_code)
            return "error"
    return paper_doc


# In[4]:


def get_tags(doc):
    paper_tag = doc.select("[data-lid]")
    cite_tag = doc.select("[title=Cite] + a")
    link_tag = doc.find_all("h3", {"class": "gs_rt"})
    author_tag = doc.find_all("div", {"class": "gs_a"})

    return paper_tag, cite_tag, link_tag, author_tag


# In[5]:


def get_papertitle(paper_tag):

    paper_names = []

    for tag in paper_tag:
        paper_names.append(tag.select("h3")[0].get_text())

    return paper_names


# In[6]:


def get_link(link_tag):

    links = []

    for i in range(len(link_tag)):
        try:
            links.append(link_tag[i].a["href"])
        except:
            links.append('NA')
    return links


# In[7]:


def get_author_year_publi_info(authors_tag):
    years = []
    publication = []
    authors = []
    for i in range(len(authors_tag)):
        authortag_text = (authors_tag[i].text).split()
        try:
            year = int(re.search(r"\d+", authors_tag[i].text).group())
        except:
            year = 0
        years.append(year)
        publication.append(authortag_text[-1])
        author = authortag_text[0] + " " + re.sub(",", "", authortag_text[1])
        authors.append(author)

    return years, publication, authors


# In[8]:


paper_repos_dict = {
    "Paper Title": [],
    "Year": [],
    "Author": [],
    "Publication": [],
    "Url of paper": [],
}

# adding information in repository
def add_in_paper_repo(papername, year, author, publi, link):
    paper_repos_dict["Paper Title"].extend(papername)
    paper_repos_dict["Year"].extend(year)
    paper_repos_dict["Author"].extend(author)
    # paper_repos_dict['Citation'].extend(cite)
    paper_repos_dict["Publication"].extend(publi)
    paper_repos_dict["Url of paper"].extend(link)

    return pd.DataFrame(paper_repos_dict)


# In[9]:


keyword = input("Enter the keyword: ")
file_name = input("Enter file name by which you want to save the file: ")
page = input("Enter page range you want to crawl (ex: 1-2 or 3-5): ")
page_range = page.split("-")

keyword = keyword.replace(" ", "+")
page_start = (int(page_range[0])*10)-10
page_stop = int(page_range[1]) * 10
num = int(page_range[1])-int(page_range[0])
sor = input("How do you want to sort (year wise):-\nType 'ASC' for ascending and 'DESC' for descending order OR 'SKIP' to save without sorting: ")
print("\nPlease wait white we are crawling the webpages "+page+", total: "+str(num+1)+" pages...\n")

for i in tqdm(range(page_start, page_stop, 10)):

    # get url for the each page
    url = (
        "https://scholar.google.com/scholar?start="
        + str(i)
        + "&q="
        + keyword
        + "+&hl=en&as_sdt=0,5"
    )

    # function for the get content of each page
    doc = get_paperinfo(url)
    if doc == 429:
        print("Error:429, Too many request, google scholar is blocking")
        break
    elif doc =="error":
        print("Unable to fetch webpage, raise an issue with status code error message")
        break
    else:
        # function for the collecting tags
        paper_tag, cite_tag, link_tag, author_tag = get_tags(doc)

        # paper title from each page
        papername = get_papertitle(paper_tag)

        # year , author , publication of the paper
        year, publication, author = get_author_year_publi_info(author_tag)

        # url of the paper
        link = get_link(link_tag)

        # add in paper repo dict
        final = add_in_paper_repo(papername, year, author, publication, link)

        # use sleep to avoid status code 429
        sleep(30)
try:
    final
    # Checking for duplicates
    print("\nChecking for duplicates, Please Wait...\n")
    sleep(3)
    final = final.drop_duplicates()

    # Sorting

    if sor == "ASC" or sor == "asc":
        print("Sorting the papers year wise (ascending order)...\n")
        final = final.sort_values(by="Year", ascending=True)
    elif sor == "DESC" or sor == "desc":
        print("Sorting the papers year wise (descending order)...\n")
        final = final.sort_values(by="Year", ascending=False)
    else:
        pass
    # Saving File
    print("Saving the papers list into the file: " + file_name + "_"+page +".csv")
    try:
        final.to_csv(file_name + "_"+page +".csv", sep=",", index=False, header=True)
    except:
        print("Error in saving file")
    sleep(3)
    print("\nDone, Thank You!")
except:
    print("\nPlease try after few hours, as google is currently blocking")
