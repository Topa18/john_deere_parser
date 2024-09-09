from bs4 import BeautifulSoup
import requests
import json
import os
import time
import random

headers = {
    "Accept": "*/*",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 YaBrowser/24.6.0.0 Safari/537.36"
}


def get_categories_hrefs():
    url = 'https://shop.deere.com/us/ShopAllCategories'

    response = requests.get(url=url, headers=headers)
    soup = BeautifulSoup(response.text, 'lxml')

    all_categories = soup.find_all('div', class_="prod_cat featured_product_cat")
    all_hrefs = []

    for cat in all_categories:
        href = "https://shop.deere.com" + cat.find('a').get('href')
        all_hrefs.append(href)
    
    print('[INFO] All categories urls collected')
    return all_hrefs


def get_categories_ids():
    all_hrefs = get_categories_hrefs()
    categories_ids = []

    for url in all_hrefs:
        response = requests.get(url=url, headers=headers)
        soup = BeautifulSoup(response.text, 'lxml')

        check_for_sib_category = soup.find('div', class_="yCmsContentSlot row category-container")
        
        if check_for_sib_category:
            sib_categories = soup.find('div', class_="yCmsContentSlot row category-container").find_all('div', class_="yCmsComponent component-wrapper")
            
            for cat in sib_categories:
                cat_id = cat.find('div', class_="title justify--between").find('a').get('href')
                cat_id = cat_id.split('/')[-2]

                categories_ids.append(cat_id)

    print("[INFO] All categories ids for queries collected")   
    return categories_ids
        

def get_items_ids():
    categories_ids = get_categories_ids()
    items_ids = []
    
    with requests.Session() as session:
        for id in categories_ids:
            try:
                response = session.post(url=f"https://shop.deere.com/bff/v1/search?categoryId={id}&page=1&size=24&productType=all&countryCode=US",
                                    headers=headers, timeout=60)
            except requests.ConnectionError as e:
                print(e)
                continue

            data = response.json()

            total_items = data.get('totalResults')
            total_pages = int(total_items / 24) + 1
            
            for page in range(1, total_pages + 1):
                time.sleep(random.randint(2,4))

                try:
                    response = session.post(url=f"https://shop.deere.com/bff/v1/search?categoryId={id}&page={page}&size=24&productType=all&countryCode=US",
                                            headers=headers, timeout=60)
                except requests.ConnectionError as e:
                    print(e)
                    continue

                data = response.json()

                items_on_page = data.get('products')
                
                for item in items_on_page:
                    if item.get('assets'):
                        art = item.get('code')

                        with open("articles.txt", 'a') as f:
                            f.write(art + '\n')

                        items_ids.append(art)
                        print(f"{art} - article founded. Cat_id: {id}. Page: {page}")
    
    print(f"[INFO] Total amount of article numbers - {len(items_ids)}")
    return items_ids


def get_images():

# Читаем артикулы из переменной
    #items_ids = get_items_ids()

    items_ids = []
    
    with open('articles.txt') as file:
        while True:
            article = file.readline().strip()
            if not article:
                break
            items_ids.append(article)
    
    with requests.Session() as session:
        try:
            for id in items_ids:
                url = f"https://shop.deere.com/bff/v1/products/{id}?countryCode=US"

                try:
                    response = session.get(url=url, headers=headers, timeout=60)
                except Exception as e:
                    print(e)
                    continue

                data = response.json()

                if data.get('assets'):
                    item_data = data.get('assets')

                    title_img_url = item_data[0].get('mediaUrls').get('bigResolution')
                    # Запись ссылки в txt файл
                    with open("title_urls.txt", 'a') as f:
                        f.write(title_img_url + '\n')

                    # Сохранение главного изображения в лучшем качестве
                    try:
                        title_image = session.get(url=title_img_url, headers=headers, timeout=60).content
                    except Exception as e:
                        print(e)
                        continue
                    
                    if not os.path.exists(f'data/title_images'):
                        os.mkdir(f'data/title_images')
                    with open(f"data/title_images/{id}.jpeg", 'wb') as file:
                        file.write(title_image)
                        
                    print(f"{id} - title img saved")

                    # Сохранение доп.изображений в лучшем качестве, если они есть
                    if len(item_data) > 1:
                        counter = 0
                        other_imgs = item_data[1:]

                        for src in other_imgs:
                            other_img_url = src.get('mediaUrls').get('bigResolution')
                            
                            # Запись ссылки в txt файл
                            with open("other_urls.txt", 'a') as f:
                                f.write(other_img_url + '\n')

                            try:
                                other_img = session.get(url = other_img_url, headers=headers, timeout=60).content
                            except Exception as e:
                                print(e)
                                continue

                            if not os.path.exists(f'data/all_images/{id}'):
                                os.mkdir(f'data/all_images/{id}')
                            with open(f"data/all_images/{id}/{id}_{counter}.jpeg", 'wb') as file:
                                file.write(other_img)

                            counter += 1
                            print(f"{id} - other img saved")

        except Exception as e:
            print(e)
            pass


    
def main():
    if not os.path.exists('data'):
        os.mkdir('data')

    get_items_ids()
    get_images()
    
    print("All data collected")


if __name__=='__main__':
    try: 
        main()
    except Exception as e:
        print(e)