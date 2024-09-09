from bs4 import BeautifulSoup
from asyncio import Semaphore
import requests
import json
import os
import time
import random
import asyncio
import aiohttp
import aiofiles


headers = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-U",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 YaBrowser/24.7.0.0 Safari/537.36"
}

def get_categories_hrefs():
    headers = {
        "Accept": "*/*",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 YaBrowser/24.6.0.0 Safari/537.36"
    }
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
                print(f"[INFO] Saved category id - {cat_id}")

    print(f"[INFO] All categories ids for queries collected ({len(categories_ids)})")   
    return categories_ids

categories_ids = get_categories_ids()

# Сбор количества страниц в категории для формирования запроса
pages_for_query = []


async def get_pages(session, id, semaphore, throttler):   
    url = f"https://shop.deere.com/bff/v1/search?categoryId={id}&page=1&size=24&productType=all&countryCode=US"
    async with throttler:
        async with semaphore:
            async with session.post(url=url, headers=headers) as response:
                try:
                    if not response.ok:
                        print("[ASYNC INFO] Waiting for cooldown...")
                        print(f"Content-type: {response.headers.get('Content-Type')}")
                        time.sleep(250)
                        response = await session.post(url=url, headers=headers)

                    data = await response.json()
                    total_items = data.get('totalResults')
                    if total_items:
                        total_pages = int(total_items / 24) + 1
                        pages_for_query.append(total_pages)
                        print(f"[ASYNC INFO] All pages for category - {id} collected")
                    else:
                        print(f"[ASYNC INFO] Empty category - {id}")
                        categories_ids.remove(id)

                except Exception as e:
                    print(response.text)
        
            print(f"[ASYNC INFO] Pagination collected ({len(pages_for_query)})")


async def gather_pages():
    tasks = []
    semaphore = Semaphore(10)
    async with aiohttp.ClientSession() as session:
        for id in categories_ids:
            task = asyncio.create_task(get_pages(session, id, semaphore)) 
            tasks.append(task)

        await asyncio.gather(*tasks)

asyncio.run(gather_pages())
print("[CORO RESULT INFO] All pagination collected") 

# Проверяем предстоящее количество запросов
queries_to_do = []
for pages in pages_for_query:
    total = 24 * pages
    queries_to_do.append(total)

queries_to_do = sum(queries_to_do)
print(f"[INFO] Total queries - {queries_to_do}")

# Сбор артикулов товаров
items_ids = []
queries = 0


async def get_page_data(session, id, page, semaphore):   
    global queries
    url=f"https://shop.deere.com/bff/v1/search?categoryId={id}&page={page}&size=24&productType=all&countryCode=US"
    async with semaphore:
        async with session.post(url=url, headers=headers) as response:
            try:
                if not response.ok:
                    print("[ASYNC INFO] Waiting for cooldown...")
                    print(f"Content-type: {response.headers.get('Content-Type')}")
                    time.sleep(250)
                    response = await session.post(url=url, headers=headers)
                
                data = await response.json()
                items_on_page = data.get('products')
                for item in items_on_page: 
                    if item.get('assets'):
                        art = item.get('code')
                        items_ids.append(art)
                queries += 1
                print(f"[ASYNC INFO] {id}/{page} articles collected (query: {queries}/{queries_to_do} Content-type: {response.headers.get('Content-Type')})")

            except Exception as e:
                print(response.text)
            

async def gather_data():
    tasks = []
    semaphore = Semaphore(10)
    async with aiohttp.ClientSession() as session:
        for id, total_pages in zip(categories_ids, pages_for_query):
            for page in range(1, total_pages + 1):
                task = asyncio.create_task(get_page_data(session, id, page, semaphore))
                tasks.append(task)
        
        await asyncio.gather(*tasks)


asyncio.run(gather_data())
print("[CORO RESULT INFO] All articles collected in list")            

# Сохранение ссылок на изображения
title_imgs_urls = []
other_imgs_urls = []


async def get_img_data(session, id, semaphore):
    url = f"https://shop.deere.com/bff/v1/products/{id}?countryCode=US"
    async with semaphore:
        async with session.get(url=url, headers=headers) as response:
            try:
                if not response.ok:
                    print("[ASYNC INFO] Waiting for cooldown")
                    print(f"Content-type: {response.headers.get('Content-Type')}")
                    time.sleep(250)
                    response = await session.get(url=url, headers=headers)

                data = await response.json()
                if data.get('assets'):
                    item_data = data.get('assets')

                    # Получение главного изображения в лучшем качестве
                    title_img_url = item_data[0].get('mediaUrls').get('bigResolution')
                    title_imgs_urls.append(title_img_url)

                    # Получение остальных изображений товара в лучшем качестве
                    if len(item_data) > 1:
                        other_imgs = item_data[1:]

                        for src in other_imgs:
                            other_img_url = src.get('mediaUrls').get('bigResolution')
                            other_imgs_urls.append(other_img_url)
                
                print(f'[ASYNC INFO] For art - {id} img_urls collected')
            
            except Exception as e:
                print(e)


async def gather_img_data():    
    tasks =[]
    semaphore = Semaphore(8)
    async with aiohttp.ClientSession() as session:
        for id in items_ids:
            task = asyncio.create_task(get_img_data(session, id, semaphore))
            tasks.append(task)

        await asyncio.gather(*tasks)

asyncio.run(gather_img_data())
print("[CORO RESULT INFO] All image urls collected") 


# Сохранение главных изображений товаров
async def save_title_image(session, image_url, semaphore, throttler):
    url = image_url
    art = url.split('/')[6].split('_')[0]
    async with throttler:
        async with semaphore:
            async with session.get(url=url, headers=headers) as response:
                try:
                    if not response.ok:
                        print("[ASYNC INFO] Waiting for cooldown")
                        print(f"Content-type: {response.headers.get('Content-Type')}")
                        time.sleep(250)
                        response = await session.get(url=url, headers=headers)
                    
                    async with aiofiles.open(f"data/title_images/{art}.jpeg", 'wb') as file:
                        await file.write(await response.read())
                        print(f"{art} saved")
                
                except Exception as e:
                    print(e)


async def gather_title_images():
    tasks = []
    semaphore = Semaphore(8)
    async with aiohttp.ClientSession() as session:
        for image_url in title_imgs_urls:
            task = asyncio.create_task(save_title_image(session, image_url, semaphore))
            tasks.append(task)
        
        await asyncio.gather(*tasks)
        
asyncio.run(gather_title_images())
print("[CORO RESULT INFO] Title images are saved")


# Сохранение остальных изображений товара при их наличии
async def save_other_image(session, image_url, semaphore):
    url = image_url
    art = url.split('/')[6].split('.')[0]
    async with semaphore:
        async with session.get(url=url, headers=headers) as response:
            try:
                if not response.ok:
                    print("[ASYNC INFO] Waiting for cooldown")
                    print(f"Content-type: {response.headers.get('Content-Type')}")
                    time.sleep(250)
                    response = await session.get(url=url, headers=headers)

                async with aiofiles.open(f"data/all_images/{art}.jpeg", 'wb') as file:
                    await file.write(await response.read())
                    print(f"{art} saved")
                    
            except Exception as e:
                print(e)


async def gather_other_images():
    tasks = []
    semaphore = Semaphore(8)    
    async with aiohttp.ClientSession() as session:
        for image_url in other_imgs_urls:
            task = asyncio.create_task(save_other_image(session, image_url, semaphore))
            tasks.append(task)
        
        await asyncio.gather(*tasks)


asyncio.run(gather_other_images())
print("[CORO RESULT INFO] Other images are saved")
print("[INFO] All data collected")