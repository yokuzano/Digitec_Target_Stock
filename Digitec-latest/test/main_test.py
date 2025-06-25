import requests
import pickle
import os
from bs4 import BeautifulSoup
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By


from typing import List, Dict, Union
import os


# Gets the cookies from a specified path and returns a session with them
def get_cookies(cookiesFilePath: str = "data/cookies_test.pkl", validate: bool = True) -> requests.Session:
    session = requests.Session()

    # Get the cookies (login information) from the cookies.pkl file
    if os.path.exists(cookiesFilePath):
        with open(cookiesFilePath, 'rb') as file:
            cookies = pickle.load(file) # Could not figure out how to authenticate with the ERP (especially because of 2FA), so I just copy the cookies from my browser and keep track of the Auth2.0 behaviour. Defeneteley something to change in the future.
    else:
        print("No cookies found in path: " + cookiesFilePath)
        return None
    
    # Store the cookies in the session
    try:
        session.cookies.update(cookies)
    except Exception as e:
        print("An unknown error occured. Please try again. The cookies are probably not in the right format.")
        print(e)
        return None

    # Check if the cookies are valid
    if validate:
        response = session.get("https://test-erp.digitecgalaxus.ch/de/Welcome")
        if response.url.startswith("https://test-erp.digitecgalaxus.ch/de/Login"): # If im redirected to the login page, the cookies are not valid
            print("Cookies are not valid. Please run the cookiesGrab_test.py.")
            return None
        
    return session

# Function to change the key name of a dictionary. Python should have a built in function for this
def change_key_name(dictionary: dict, old_key: str, new_key: str) -> dict:
    if old_key in dictionary:
        value = dictionary.pop(old_key)
        dictionary[new_key] = value
    return dictionary

# Function to get the availbility of a given product, if no soup is given, the soup will be requested
def getLagerStand(session: requests.Session, productID: str, soup=None) -> Union[Dict[str, int], BeautifulSoup]:
    if soup == None:
        find_product_url = "https://test-erp.digitecgalaxus.ch/de/Product/Availability/"
        r = session.get(find_product_url + productID)
        soup = BeautifulSoup(r.text, 'html.parser')
    else:
        print("Soup given")

    # Find the cursor for the Lagerstand table in the HTML document
    table = soup.select_one("#main_content > div:nth-child(15) > div.content.erpBoxContent > div > table")

    # Parse the table and store the availbility in tr_elements for each filiale
    if table is not None:
        tr_elements = table.find_all("tr")[1:]
    else:
        tr_elements = []

    # Parse the tr_elements and store the availbility in td_elements
    td_elements = [tr_element.find_all("td") for tr_element in tr_elements]

    # Parse the td_elements and store the availbility in td_elements
    td_elements = [[td_element.text.strip() for td_element in td_element] for td_element in td_elements]

    # Store the Lagerstand in a dictionary with the filiale as key and the availbility as value
    lagerstand = {}

    for td_element in td_elements:
        if td_element[2] not in lagerstand:
            lagerstand[td_element[2]] = int(td_element[3])
        else:
            lagerstand[td_element[2]] += int(td_element[3])

        # Some of the filialen have different names in the Lagerstand than in the Zielbestand
    if "StGallen" in lagerstand:
        lagerstand = change_key_name(lagerstand, "StGallen", "St Gallen")
    if "ZÃ¼rich" in lagerstand:
        lagerstand = change_key_name(lagerstand, "ZÃ¼rich", "Zürich")

    return lagerstand, soup

# Function to deleate all the current Zielbestand rules, if no soup is given, the soup will be requested
def deleateZielbestand(session: requests.Session, productID: str, soup=None) -> BeautifulSoup:
    if soup is None:
        find_product_url = "https://test-erp.digitecgalaxus.ch/de/Product/Availability/"
        r = session.get(find_product_url + productID)
        soup = BeautifulSoup(r.text, 'html.parser')
    else:
        print("-- Delete rules started --")

    currentURL = f"https://test-erp.digitecgalaxus.ch/de/Product/Availability/{productID}"

    try:
        rule_table = soup.select_one("#ProductSiteTargetInventoryOverrideTable")
        if not rule_table:
            print("Table not found.")
            return soup

        tbody_elements = rule_table.find_all("tbody")
        if not tbody_elements:
            print("No tbody found in the table.")
            return soup

        tr_elements = tbody_elements[0].find_all("tr")
        if not tr_elements:
            print("No rules found.")
            return soup

        num_requests = 0
        for tr in tr_elements:
            tr_id = tr.get("id")
            if tr_id and "ProductSiteTargetInventoryOverrideTable_row_" in tr_id:
                rule_id = tr_id.split("_")[-1]
                delete_url = f"https://test-erp.digitecgalaxus.ch/de/ProductSiteTargetInventoryOverride/TableDelete/{rule_id}"

                params = {
                    'ajaxerplist': '2'
                }

                delete_body = "------WebKitFormBoundaryIWuxE7cLaZYUNNZO--\r\n"

                headers = {
                    'Accept': '*/*',
                    'Accept-Language': 'fr-FR,fr;q=0.9',
                    'Content-Type': 'multipart/form-data; boundary=----WebKitFormBoundaryIWuxE7cLaZYUNNZO',
                    'Origin': 'https://test-erp.digitecgalaxus.ch',
                    'Referer': currentURL,
                    'Sec-Fetch-Dest': 'empty',
                    'Sec-Fetch-Mode': 'cors',
                    'Sec-Fetch-Site': 'same-origin',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36',
                    'X-Requested-With': 'XMLHttpRequest'
                }

                response = session.post(delete_url, params=params, data=delete_body, headers=headers)
                if response.status_code == 200:
                    num_requests += 1
                else:
                    print(f"Error deleting rule {rule_id}: {response.status_code}")

        print(f"Deleted {num_requests} rules")
        return soup

    except Exception as e:
        print("An error occurred while deleting rules:", e)
        return soup

# Takes in a session, productID and information about the new Zielbestand and adds it to the product for every filiale in the filialen list
def addZielbestand(session: requests.Session, productID: str, from_date: str, to_date: str, product_quantity: int, filialen: List[str], soup=None) -> BeautifulSoup:
    if soup == None:
        find_product_url = "https://test-erp.digitecgalaxus.ch/de/Product/Availability/"
        r = session.get(find_product_url + productID)
        soup = BeautifulSoup(r.text, 'html.parser')
    else:
        print("-- Add rules started --")

    # Values encoded
    values_encoded ={
        'Basel': 246967,
        'Bern': 246970,
        'Dietikon': 246971,
        'Genf': 246975,
        'Kriens': 246968,
        'Lausanne': 246965,
        'St. Gallen': 246977,
        'Winterthur': 246969,
        'Zürich': 246938
    }

    try:
        # Find out the product mandant, necessary for the request
        try:
            data_source_div = soup.find("div", attrs={"data-source": lambda x: x and "ProductTargetInventoryOverride/ErpTable" in x})
            data_source = data_source_div["data-source"]
            mandant = data_source.strip("/").split("/")[-1]
        except Exception as e:
            print("Mandant not found in the HTML document. This might be due to a change in the HTML structure.")
            mandant = None


        # The url on which the post request is made
        if mandant is not None:
            create_url = "https://test-erp.digitecgalaxus.ch/ProductSiteTargetInventoryOverride/TableNewPost/" + mandant
        else:
            print("No mandant found in the HTML document.")
            create_url = None


        currentURL = "https://test-erp.digitecgalaxus.ch/de/Product/Availability/" + productID

        # Make a post request for every filiale
        num_requests = 0
        for filiale in filialen:

            params = {
                    'ajaxerplist': '2'
            }

            data = {
                "ProductSiteTargetInventoryOverride.SiteId": values_encoded[filiale],
                "ProductSiteTargetInventoryOverride.Quantity": product_quantity,
                "ProductSiteTargetInventoryOverride.ValidFrom": from_date,
                "ProductSiteTargetInventoryOverride.ValidTo" : to_date,
                "save" : "",
            }

            headers = {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Referer": currentURL,
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
                "X-Requested-With": "XMLHttpRequest"
            }

            # Make the post request and check if it was successful
            r = session.post(create_url, params=params, data=data, headers=headers)
            if r.status_code == 200:
                num_requests += 1
            else:
                print(f"Error: {r.status_code}")
            
            # Print filiale and the response text
            print(f"Filiale: {filiale}")
        
        print(f"Added {num_requests} rules")
        return soup
    except Exception as e:
        print("An error occured while adding the rules. Product skipped", e)
        return soup

# Higher level function to update the Target stock of a product, returns a dictionary of how many products will be transfered to each filiale in the filialen (except Wohlen and Winterthur)
# def updateZielbestand(session: requests.Session, productID: str, date_start: str, date_end:str, quantity: int, filialen: List[str] = ["Basel", "Bern", "Dietikon", "Kriens", "Lausanne", "St. Gallen", "Zürich"]) -> Dict[str, int]:
def updateZielbestand(session: requests.Session, productID: str, date_start: str, date_end:str, quantity: int, filialen: List[str] = ["St. Gallen"]) -> Dict[str, int]:
    
    # Print the productID we are currently working on
    print("Product : ", productID)
    
    # Get the Lagerstand
    lagerstand, soup = getLagerStand(session, productID)

    # Deleate the current Zielbestand
    deleateZielbestand(session, productID, soup=soup)

    # Add the new Zielbestand except Wohlen and Winterthur
    addZielbestand(session, productID, date_start, date_end, quantity, filialen, soup=soup)

    # Calculate how many products need to be transfered per filiale with the new Zielbestand
    productsForTransfer = {}
    for filiale in filialen:
        if filiale not in lagerstand:
            productsForTransfer[filiale] = quantity
        else:
            productsForTransfer[filiale] = max(0, quantity - lagerstand[filiale])
    return productsForTransfer

def main():
    # Load the cookies pkl file and store them in a session object
    session = get_cookies(validate=True)
    assert session != None, "The cookies are not valid. Please run the cookiesGrab_test.py."

    # Define the date range for the new rules and the start time of the script
    date_start = "24.10.2024"
    date_end = "03.06.2025"
    start_time = pd.Timestamp.now()

    # Load the data from the csv file in ISO-8859-1 encoding
    #df = pd.read_csv("data/data.csv", sep = ";", encoding = "ISO-8859-1")
    # Load the data from the csv file in UTF-8 encoding
    df = pd.read_csv("data/data.csv", sep = ";", encoding = "utf-8")

    ## CHANGE THE VALUE OF  SIZE_OF_UPDATE TO THE LIMIT YOU WOULD LIKE TO HAVE
    # Count the number of updates and limit the number of updates per run to <200>
    update_count = 0
    size_of_update = 2000
    if len(df) < size_of_update:
        size_of_update = len(df)

    # Initialize the bestand dictionary
    bestand = {'Basel': 0, 'Bern': 0, 'Dietikon': 0, 'Kriens': 0, 'Lausanne': 0, 'St. Gallen': 0, 'Zürich': 0}

    # Iterate over the rows of the csv file and update the Zielbestand
    for index, row in df.iterrows():
        try:
            product = str(int(row["Product Id"]))
            zielbestand = int(row["Stück pro Filiale"])
            bemerkungen = row['Bemerkungen']
        except ValueError:
            print(f"Product ID or Zielbestand is not a number in row {index}. Skipping this row.\n")
            update_count += 1
            continue

        # If the count of updates is less than the size of the update, update the Zielbestand
        if index < size_of_update:
            update = updateZielbestand(session, product, date_start, date_end, zielbestand)
            update_count += 1
            # Use pandas lib to delete the line in the csv file when update is done
            df.drop(df[df['Product Id'] == int(product)].index, inplace=True)
            #df.to_csv("data/data_processing.csv", index=False, encoding = "ISO-8859-1", sep = ";")
            df.to_csv("data/data_processing.csv", index=False, encoding = "utf-8", sep = ";")
        if index == size_of_update-1:
            os.remove("data/data.csv")
            os.rename("data/data_processing.csv", "data/data.csv")
            print("The whole list has been processed.\n")
            break

        # Update the bestand dictionary
        for city, value in update.items():
            if city in bestand:
                bestand[city] += value

        # Find the maximum stock
        max_stock = max(bestand.values())

        # Print the progress in percentage and the current index with the index of the update out of the size of the update
        print(f"{(index+1)/size_of_update*100:.2f}% done ({index+1}/{size_of_update})\n")

        # Print the progress every 10 products
        if index % 10 == 0 and index != 0:
            print(bestand, "\n")
            # Calculate the time left based on the current index and the size of the update
            time_left = (pd.Timestamp.now() - start_time) / index * (size_of_update - index)
            print(f"Time left: {time_left.seconds//3600}H {time_left.seconds//60}m\n")

if __name__ == "__main__":
    main()
