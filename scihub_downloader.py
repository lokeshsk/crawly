#!/usr/bin/env python
# coding: utf-8

# In[1]:


#importing packages
import webbrowser
import pandas as pd
from selenium import webdriver
import requests
from scrapy.selector import Selector
import urllib.request
from time import sleep
import os
from fake_useragent import UserAgent


# In[2]:


#checking whether schi-hub is accessible or not
def connect(host='https://google.com/'):
    try:
        urllib.request.urlopen(host) #Python 3.x
        return True
    except:
        return False
# test
print("Checking whether internet is working or not...")
print( "internet connected" if connect() else "No internet! check you internet connection" )


# In[3]:



ua = UserAgent()

#generating fake_useragent randomly
fake_ua = ua.random

headers = {
    "user-agent": fake_ua
}
#print(headers)
url = input("Enter working 'sci-hub' url in your country ( like: https://sci-hub.se ): ")
#"https://sci-hub.se/"
#print("Default url: https://sci-hub.se/")
try:
    r = requests.get(url,timeout=3, headers=headers)
    r.raise_for_status()    
except requests.exceptions.RequestException as err:
    print ("OOps: Something Else",err)
    print("Check whether" + url + "is not blocked by your ISP OR You can try using a proxy server, But if you think if its an error, raise an issue on github with screenshot")
except requests.exceptions.HTTPError as errh:
    print ("Http Error:",errh)
    print("Check whether" + url + "is not blocked by your ISP OR You can try using a proxy server, But if you think if its an error, raise an issue on github with screenshot")
except requests.exceptions.ConnectionError as errc:
    print ("Error Connecting:",errc)
    print("Check whether" + url + "is not blocked by your ISP OR You can try using a proxy server, But if you think if its an error, raise an issue on github with screenshot")
except requests.exceptions.Timeout as errt:
    print ("Timeout Error:",errt)     
    print("Check whether" + url + "is not blocked by your ISP OR You can try using a proxy server, But if you think if its an error, raise an issue on github with screenshot")


# In[4]:


file_name = input("Enter file name (without csv): ")

df = pd.read_csv(file_name+".csv", sep = ',')



# In[6]:


pid= df['Paper Title'].tolist()
p_url = df['Url of paper'].tolist()


# In[7]:


pid_new=[]
def replace_all(text, dic):
    for i, j in dic.items():
        text = text.replace(i, j)
    return text


# In[8]:


to_replace = { "[BOOK]": "", "[HTML]": "", "[B]": "", "[PDF]": ""}

for i in pid:
    i = i.strip()
    pid_new.append(replace_all(i, to_replace))
#pid_new


# In[ ]:



dir = file_name.replace('.csv','')
try: 
    os.mkdir(dir) 
except OSError as error: 
    print("FILE or FOLDER exists", error) 
x = 0
paper_titl =[]
paper_url = []
for i,j in zip(pid_new,p_url):
    driver = webdriver.Chrome()

    driver.get(url)

    input_box = driver.find_element('name','request')
    input_box.send_keys(i)
    driver.find_element('xpath',"//button[@type='submit']").click()
    r = requests.get(driver.current_url)
    res= requests.get(driver.current_url)

    selector = Selector(text=res.text)
    try:

        pdf_url = selector.xpath("//embed[@id='pdf']/@src").extract()
        pdf_url = url+pdf_url[0]
        #r = requests.get(pdf_url).content
        #open(i, 'wb').write(r)
        #print('pdf',pdf_url)
        url1 = url.replace("https://","")
        if('#' in pdf_url):
            head, sep, tail = pdf_url.partition('#')
            #print("ih",head)
            s = head.count(url1)
            if(s>1):
                url1 = url1+"//"
                head = head.replace(url1,'')
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
        #print(i,j)
        #print(e)
        paper_titl.append(i)
        paper_url.append(j)
        #paper_title = i
        #paper_url = j
    finally:
        sleep(10)
        driver.close()
p_not_found = {'Paper Title': paper_titl, 'Paper URL': paper_url}
df1 = pd.DataFrame.from_dict(p_not_found)
df1.to_csv(dir+'/papers_not_found.csv', index=None)
print("Saving list of papers which are not found on sci-hub.")


# In[ ]:


"""
    if x % 10 == 0:
        input("Press Enter to continue...")
        
        driver = webdriver.Chrome()

        driver.get("http://sci-hub.se/")

        input_box = driver.find_element('name','request')
        input_box.send_keys(i)
        driver.find_element('xpath',"//button[@type='submit']").click()
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

        input_box = driver.find_element_by_name('request')
        input_box.send_keys(i)
        driver.find_element_by_xpath("//button[@type='submit']").click()
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
    """


# In[ ]:




