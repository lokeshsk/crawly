#!/usr/bin/env python
# coding: utf-8

# In[1]:


import webbrowser
import pandas as pd


file_name = input("Enter file name (without csv): ")

df = pd.read_csv(file_name+".csv", sep = ',')


# In[2]:


pid= df['Paper Title'].tolist()


# In[3]:


pid_new =[]
for i in pid:
    x = i.strip()
    x = x.replace('[BOOK]', '')
    x= x.replace('[HTML]','')
    x= x.replace('[PDF]','')
    x= x.replace('[B]','')
    x= x.strip()
    pid_new.append(x)
#pid_new


# In[11]:


from selenium import webdriver
import requests
from scrapy.selector import Selector
import urllib.request
from time import sleep
import os

dir = file_name.replace('.csv','')
try: 
    os.mkdir(dir) 
except OSError as error: 
    print(error)


def connect(host='http://google.com'):
    try:
        urllib.request.urlopen(host) #Python 3.x
        return True
    except:
        return False
# test
print("Checking whether internet is available or not...")
print( "internet connected" if connect() else "no internet! check you internet connection" )

x = 0
for i in pid_new:
    if x % 10 == 0:
        input("Press Enter to continue...")
        
        driver = webdriver.Chrome()

        driver.get("http://sci-hub.se/")

        input_box = driver.find_element("name",'request')
        input_box.send_keys(i)
        driver.find_element("xpath","//button[@type='submit']").click()
        r = requests.get(driver.current_url)
        res= requests.get(driver.current_url)

        selector = Selector(text=res.text)
        try:

            pdf_url = selector.xpath("//embed[@id='pdf']/@src").extract()
            pdf_url = "https://sci-hub.se"+pdf_url[0]
            #r = requests.get(pdf_url).content
            #open(i, 'wb').write(r)
            #print('pdf',pdf_url)
            if('#' in pdf_url):
                head, sep, tail = pdf_url.partition('#')
                #print("ih",head)
                s = head.count("sci-hub.se")
                if(s>1):
                    head = head.replace('sci-hub.se//','')
                    #print("h",head)
                    z = os.path.join(dir+"/", i)
                    urllib.request.urlretrieve(head, z)
                else:
                    z = os.path.join(dir+"/", i)
                    urllib.request.urlretrieve(head, z)   
            else:
                z = os.path.join(dir+"/", i)
                #print('ie',pdf_url)
                urllib.request.urlretrieve(pdf_url, z)
        except:
            print(i)
        sleep(10)
    else:
        
        driver = webdriver.Chrome()

        driver.get("http://sci-hub.se/")

        input_box = driver.find_element('name','request')
        input_box.send_keys(i)
        driver.find_element("xpath","//button[@type='submit']").click()
        r = requests.get(driver.current_url)
        res= requests.get(driver.current_url)

        selector = Selector(text=res.text)
        try:

            pdf_url = selector.xpath("//embed[@id='pdf']/@src").extract()
            pdf_url = "https://sci-hub.se"+pdf_url[0]
            #r = requests.get(pdf_url).content
            #open(i, 'wb').write(r)
            #print('pdf',pdf_url)
            if('#' in pdf_url):
                head, sep, tail = pdf_url.partition('#')
                #print("eh",head)
                s = head.count("sci-hub.se")
                if(s>1):
                    head = head.replace('sci-hub.se//','')
                    #print("h",head)
                    z = os.path.join(dir+"/", i)
                    urllib.request.urlretrieve(head, z)
                else:
                    z = os.path.join(dir+"/", i)
                    urllib.request.urlretrieve(head, z)
            else:
                z = os.path.join(dir+"/", i)
                #print("e",pdf_url)
                urllib.request.urlretrieve(pdf_url, z)
        except:
            print(i)
        #sleep(10)
    x = x+1


# In[ ]:





# In[ ]:




