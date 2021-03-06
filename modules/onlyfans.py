import math
import os
import shutil
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from itertools import chain, groupby, product
from urllib.parse import urlparse
import copy
import timeit
import json


import requests
from requests.adapters import HTTPAdapter

import helpers.main_helper as main_helper
import classes.prepare_download as prepare_download
from types import SimpleNamespace
from multiprocessing import cpu_count

multiprocessing = main_helper.multiprocessing
log_download = main_helper.setup_logger('downloads', 'downloads.log')

json_config = None
max_threads = -1
json_settings = None
auto_choice = None
j_directory = None
file_directory_format = None
file_name_format = None
overwrite_files = None
proxies = None
cert = None
date_format = None
ignored_keywords = None
ignore_type = None
export_metadata = None
delete_legacy_metadata = None
sort_free_paid_posts = None
blacklist_name = None
webhook = None
maximum_length = None
app_token = None


def assign_vars(json_auth, config, site_settings, site_name):
    global json_config, max_threads, proxies, cert, json_settings, auto_choice, j_directory, overwrite_files, date_format, file_directory_format, file_name_format, ignored_keywords, ignore_type, export_metadata, delete_legacy_metadata, sort_free_paid_posts, blacklist_name, webhook, maximum_length, app_token

    json_config = config
    json_global_settings = json_config["settings"]
    max_threads = json_global_settings["max_threads"]
    proxies = json_global_settings["socks5_proxy"]
    cert = json_global_settings["cert"]
    json_settings = site_settings
    auto_choice = json_settings["auto_choice"]
    j_directory = main_helper.get_directory(
        json_settings['download_paths'], site_name)
    file_directory_format = json_settings["file_directory_format"]
    file_name_format = json_settings["file_name_format"]
    overwrite_files = json_settings["overwrite_files"]
    date_format = json_settings["date_format"]
    ignored_keywords = json_settings["ignored_keywords"]
    ignore_type = json_settings["ignore_type"]
    export_metadata = json_settings["export_metadata"]
    delete_legacy_metadata = json_settings["delete_legacy_metadata"]
    sort_free_paid_posts = json_settings["sort_free_paid_posts"]
    blacklist_name = json_settings["blacklist_name"]
    webhook = json_settings["webhook"]
    maximum_length = 255
    maximum_length = int(json_settings["text_length"]
                         ) if json_settings["text_length"] else maximum_length
    app_token = json_auth['app_token']


# The start lol
def start_datascraper(sessions, identifier, site_name, app_token2, choice_type=None):
    global app_token
    print("Scrape Processing")
    app_token = app_token2
    info = link_check(sessions[0], identifier)
    user = info["user"] = json.loads(json.dumps(
        info["user"]), object_hook=lambda d: SimpleNamespace(**d))
    if not info["exists"]:
        return [False, info]
    is_me = user.is_me
    post_counts = info["count"]
    post_count = post_counts[0]
    user_id = str(user.id)
    avatar = user.avatar
    username = user.username
    link = user.link
    info["download"] = prepare_download.start(
        username=username, link=link, image_url=avatar, post_count=post_count, webhook=webhook)
    if not info["subbed"]:
        print(f"You are not subbed to {user.username}")
        return [False, info]
    print("Name: "+username)
    api_array = scrape_choice(user_id, post_counts, is_me)
    api_array = format_options(api_array, "apis")
    apis = api_array[0]
    api_string = api_array[1]
    if not json_settings["auto_scrape_apis"]:
        print("Apis: "+api_string)
        value = int(input().strip())
    else:
        value = 0
    if value:
        apis = [apis[value]]
    else:
        apis.pop(0)
    for item in apis:
        print("Type: "+item["api_type"])
        only_links = item["api_array"]["only_links"]
        post_count = str(item["api_array"]["post_count"])
        item["api_array"]["username"] = username
        api_type = item["api_type"]
        results = prepare_scraper(
            sessions, site_name, item)
        if results:
            for result in results[0]:
                if not only_links:
                    media_set = result
                    if not media_set["valid"]:
                        continue
                    directory = results[1]
                    location = result["type"]
                    info["download"].others.append(
                        [media_set["valid"], sessions, directory, username, post_count, location, api_type])
    print("Scrape Completed"+"\n")
    return [True, info]


# Checks if the model is valid and grabs content count
def link_check(session, identifier):
    link = f'https://onlyfans.com/api2/v2/users/{identifier}?app-token={app_token}'
    y = main_helper.json_request(session, link)
    temp_user_id2 = dict()
    temp_user_id2["exists"] = True
    y["is_me"] = False
    if "error" in y:
        temp_user_id2["subbed"] = False
        y["username"] = identifier
        temp_user_id2["user"] = y
        temp_user_id2["exists"] = False
        return temp_user_id2
    model_link = f"https://onlyfans.com/{y['username']}"
    now = datetime.utcnow().date()
    today = datetime.utcnow().date()
    result_date = today-timedelta(days=1)
    if "email" not in y:
        subscribedByData = y["subscribedByData"]
        if subscribedByData:
            expired_at = subscribedByData["expiredAt"]
            result_date = datetime.fromisoformat(
                expired_at).replace(tzinfo=None).date()
        if y["subscribedBy"]:
            subbed = True
        elif y["subscribedOn"]:
            subbed = True
        elif y["subscribedIsExpiredNow"] == False:
            subbed = True
        elif result_date >= now:
            subbed = True
        else:
            subbed = False
    else:
        subbed = True
        y["is_me"] = True
    if not subbed:
        temp_user_id2["subbed"] = False
    else:
        temp_user_id2["subbed"] = True
    temp_user_id2["user"] = y
    temp_user_id2["count"] = [y["postsCount"], y["archivedPostsCount"], [
        y["photosCount"], y["videosCount"], y["audiosCount"]]]
    temp_user_id2["user"]["link"] = model_link
    return temp_user_id2


# Allows the user to choose which api they want to scrape
def scrape_choice(user_id, post_counts, is_me):
    post_count = post_counts[0]
    archived_count = post_counts[1]
    media_counts = post_counts[2]
    media_types = ["Images", "Videos", "Audios"]
    x = dict(zip(media_types, media_counts))
    x = [k for k, v in x.items() if v != 0]
    if auto_choice:
        input_choice = auto_choice
    else:
        print('Scrape: a = Everything | b = Images | c = Videos | d = Audios')
        input_choice = input().strip()
    user_api_ = f"https://onlyfans.com/api2/v2/users/{user_id}?app-token={app_token}"
    message_api = f"https://onlyfans.com/api2/v2/chats/{user_id}/messages?limit=100&offset=0&order=desc&app-token={app_token}"
    mass_messages_api = f"https://onlyfans.com/api2/v2/messages/queue/stats?offset=0&limit=30&app-token={app_token}"
    stories_api = f"https://onlyfans.com/api2/v2/users/{user_id}/stories?limit=100&offset=0&order=desc&app-token={app_token}"
    hightlights_api = f"https://onlyfans.com/api2/v2/users/{user_id}/stories/highlights?limit=100&offset=0&order=desc&app-token={app_token}"
    post_api = f"https://onlyfans.com/api2/v2/users/{user_id}/posts?limit=0&offset=0&order=publish_date_desc&app-token={app_token}"
    archived_api = f"https://onlyfans.com/api2/v2/users/{user_id}/posts/archived?limit=100&offset=0&order=publish_date_desc&app-token={app_token}"
    # ARGUMENTS
    only_links = False
    if "-l" in input_choice:
        only_links = True
        input_choice = input_choice.replace(" -l", "")
    mandatory = [j_directory, only_links]
    y = ["photo", "video", "stream", "gif", "audio"]
    u_array = ["You have chosen to scrape {}", [
        user_api_, x, *mandatory, post_count], "Profile"]
    s_array = ["You have chosen to scrape {}", [
        stories_api, x, *mandatory, post_count], "Stories"]
    h_array = ["You have chosen to scrape {}", [
        hightlights_api, x, *mandatory, post_count], "Highlights"]
    p_array = ["You have chosen to scrape {}", [
        post_api, x, *mandatory, post_count], "Posts"]
    mm_array = ["You have chosen to scrape {}", [
        mass_messages_api, media_types, *mandatory, post_count], "Mass Messages"]
    m_array = ["You have chosen to scrape {}", [
        message_api, media_types, *mandatory, post_count], "Messages"]
    a_array = ["You have chosen to scrape {}", [
        archived_api, media_types, *mandatory, archived_count], "Archived"]
    array = [u_array, s_array, h_array, p_array, a_array, mm_array, m_array]
    # array = [s_array, h_array, p_array, a_array, m_array]
    # array = [u_array]
    # array = [h_array]
    # array = [p_array]
    # array = [a_array]
    # array = [mm_array]
    # array = [m_array]
    new_array = []
    valid_input = True
    for xxx in array:
        if xxx[2] == "Mass Messages":
            if not is_me:
                continue
        new_item = dict()
        new_item["api_message"] = xxx[0]
        new_item["api_array"] = {}
        new_item["api_array"]["api_link"] = xxx[1][0]
        new_item["api_array"]["media_types"] = xxx[1][1]
        new_item["api_array"]["directory"] = xxx[1][2]
        new_item["api_array"]["only_links"] = xxx[1][3]
        new_item["api_array"]["post_count"] = xxx[1][4]
        if input_choice == "a":
            name = "All"
            a = []
            for z in new_item["api_array"]["media_types"]:
                if z == "Images":
                    a.append([z, [y[0]]])
                if z == "Videos":
                    a.append([z, y[1:4]])
                if z == "Audios":
                    a.append([z, [y[4]]])
            new_item["api_array"]["media_types"] = a
        elif input_choice == "b":
            name = "Images"
            new_item["api_array"]["media_types"] = [[name, [y[0]]]]
        elif input_choice == "c":
            name = "Videos"
            new_item["api_array"]["media_types"] = [[name, y[1:4]]]
        elif input_choice == "d":
            name = "Audios"
            new_item["api_array"]["media_types"] = [[name, [y[4]]]]
        else:
            print("Invalid Choice")
            valid_input = False
            break
        new_item["api_type"] = xxx[2]
        if valid_input:
            new_array.append(new_item)
    return new_array


# Downloads the model's avatar and header
def profile_scraper(link, session, directory, username):
    y = main_helper.json_request(session, link)
    q = []
    avatar = y["avatar"]
    header = y["header"]
    if avatar:
        q.append(["Avatars", avatar])
    if header:
        q.append(["Headers", header])
    for x in q:
        new_dict = dict()
        media_type = x[0]
        media_link = x[1]
        new_dict["links"] = [media_link]
        directory2 = os.path.join(directory, username, "Profile", media_type)
        os.makedirs(directory2, exist_ok=True)
        download_path = os.path.join(
            directory2, media_link.split("/")[-2]+".jpg")
        if not overwrite_files:
            if os.path.isfile(download_path):
                continue
        r = main_helper.json_request(session, media_link, stream=True,
                                     json_format=False, sleep=False)
        if not isinstance(r, requests.Response):
            continue
        while True:
            downloader = main_helper.downloader(r, download_path)
            if not downloader:
                continue
            break


# Prepares the API links to be scraped
def prepare_scraper(sessions, site_name, item):
    api_type = item["api_type"]
    api_array = item["api_array"]
    link = api_array["api_link"]
    locations = api_array["media_types"]
    username = api_array["username"]
    directory = api_array["directory"]
    api_count = api_array["post_count"]
    master_set = []
    media_set = []
    metadata_set = []
    pool = multiprocessing()
    formatted_directories = main_helper.format_directories(
        j_directory, site_name, username, locations, api_type)
    model_directory = formatted_directories["model_directory"]
    api_directory = formatted_directories["api_directory"]
    metadata_directory = formatted_directories["metadata_directory"]
    legacy_metadata_directory = os.path.join(api_directory, "Metadata")
    # legacy_metadata = main_helper.legacy_metadata(legacy_metadata_directory)
    if api_type == "Profile":
        profile_scraper(link, sessions[0], directory, username)
        return
    if api_type == "Posts":
        num = 100
        link = link.replace("limit=0", "limit="+str(num))
        original_link = link
        ceil = math.ceil(api_count / num)
        a = list(range(ceil))
        for b in a:
            b = b * num
            master_set.append(link.replace(
                "offset=0", "offset=" + str(b)))
    if api_type == "Archived":
        ceil = math.ceil(api_count / 100)
        a = list(range(ceil))
        for b in a:
            b = b * 100
            master_set.append(link.replace(
                "offset=0", "offset=" + str(b)))

    def xmessages(link):
        f_offset_count = 0
        while True:
            y = main_helper.json_request(sessions[0], link)
            if not y:
                return
            if "list" in y:
                if y["list"]:
                    master_set.append(link)
                    if y["hasMore"]:
                        f_offset_count2 = f_offset_count+100
                        f_offset_count = f_offset_count2-100
                        link = link.replace(
                            "offset=" + str(f_offset_count), "offset=" + str(f_offset_count2))
                        f_offset_count = f_offset_count2
                    else:
                        break
                else:
                    break
            else:
                break

    def process_chats(subscriber):
        fool = subscriber["withUser"]
        fool_id = str(fool["id"])
        link_2 = f"https://onlyfans.com/api2/v2/chats/{fool_id}/messages?limit=100&offset=0&order=desc&app-token={app_token}"
        xmessages(link_2)
    if api_type == "Messages":
        xmessages(link)
    if api_type == "Mass Messages":
        results = []
        offset_count = 0
        offset_count2 = max_threads
        while True:
            def process_messages(link, session):
                y = main_helper.json_request(session, link)
                if y and "error" not in y:
                    return y
                else:
                    return []
            link_list = [link.replace(
                "offset=0", "offset="+str(i*30)) for i in range(offset_count, offset_count2)]
            link_list = pool.starmap(process_messages, product(
                link_list, [sessions[0]]))
            if all(not result for result in link_list):
                break
            link_list2 = list(chain(*link_list))

            results.append(link_list2)
            offset_count = offset_count2
            offset_count2 = offset_count*2
        unsorted_messages = list(chain(*results))
        unsorted_messages.sort(key=lambda x: x["id"])
        messages = unsorted_messages

        def process_mass_messages(message, limit):
            text = message["textCropped"].replace("&", "")
            link_2 = "https://onlyfans.com/api2/v2/chats?limit="+limit+"&offset=0&filter=&order=activity&query=" + \
                text+"&app-token="+app_token
            y = main_helper.json_request(sessions[0], link_2)
            if None == y or "error" in y:
                return []
            return y
        limit = "10"
        if len(messages) > 99:
            limit = "2"
        subscribers = pool.starmap(process_mass_messages, product(
            messages, [limit]))
        subscribers = filter(None, subscribers)
        subscribers = [
            item for sublist in subscribers for item in sublist["list"]]
        seen = set()
        subscribers = [x for x in subscribers if x["withUser"]
                       ["id"] not in seen and not seen.add(x["withUser"]["id"])]
        x = pool.starmap(process_chats, product(
            subscribers))
    if api_type == "Stories":
        master_set.append(link)
    if api_type == "Highlights":
        r = main_helper.json_request(sessions[0], link)
        if "error" in r:
            return
        for item in r:
            link2 = f"https://onlyfans.com/api2/v2/stories/highlights/{item['id']}?app-token={app_token}"
            master_set.append(link2)
    master_set2 = main_helper.assign_session(master_set, sessions)
    media_set = {}
    media_set["set"] = []
    media_set["found"] = False
    count = len(master_set2)
    max_attempts = 100
    for attempt in list(range(max_attempts)):
        print("Scrape Attempt: "+str(attempt+1)+"/"+str(max_attempts))
        media_set2 = pool.starmap(media_scraper, product(
            master_set2, [sessions], [formatted_directories], [username], [api_type]))
        media_set["set"].extend(media_set2)
        faulty = [x for x in media_set2 if not x]
        if not faulty:
            print("Found: "+api_type)
            media_set["found"] = True
            break
        else:
            if count < 2:
                break
            num = len(faulty)*100
            print("Missing "+str(num)+" Posts... Retrying...")
            master_set2 = main_helper.restore_missing_data(
                master_set2, media_set2)
    if not media_set["found"]:
        print("No "+api_type+" Found.")
    media_set = media_set["set"]
    main_helper.delete_empty_directories(api_directory)
    media_set = [x for x in media_set]
    media_set = main_helper.format_media_set(media_set)

    metadata_set = media_set
    if export_metadata:
        metadata_set = [x for x in metadata_set if x["valid"] or x["invalid"]]
        for item in metadata_set:
            if item["valid"] or item["invalid"]:
                legacy_metadata = formatted_directories["legacy_metadata"]
        if metadata_set:
            os.makedirs(metadata_directory, exist_ok=True)
            archive_directory = os.path.join(metadata_directory, api_type)
            metadata_set_copy = copy.deepcopy(metadata_set)
            metadata_set = main_helper.filter_metadata(metadata_set_copy)
            main_helper.export_archive(
                metadata_set, archive_directory, json_settings)
    return [media_set, directory]


# Scrapes the API for content
def media_scraper(result, sessions, formatted_directories, username, api_type):
    link = result["link"]
    session = sessions[result["count"]]
    media_set = []
    y = main_helper.json_request(session, link)
    if not y or "error" in y:
        return media_set
    x = 0
    if api_type == "Highlights":
        y = y["stories"]
    if api_type == "Messages":
        y = y["list"]
    if api_type == "Mass Messages":
        y = y["list"]
    model_directory = formatted_directories["model_directory"]
    for location in formatted_directories["locations"]:
        sorted_directories = location["sorted_directories"]
        master_date = "01-01-0001 00:00:00"
        media_type = location["media_type"]
        alt_media_type = location["alt_media_type"]
        if result["count"] == 0:
            seperator = " | "
            print("Scraping ["+str(seperator.join(alt_media_type)) +
                  "]. Should take less than a minute.")
        media_set2 = {}
        media_set2["type"] = media_type
        media_set2["valid"] = []
        media_set2["invalid"] = []
        for media_api in y:
            if api_type == "Messages":
                media_api["rawText"] = media_api["text"]
            if api_type == "Mass Messages":
                media_user = media_api["fromUser"]
                media_username = media_user["username"]
                if media_username != username:
                    continue
            for media in media_api["media"]:
                date = "-001-11-30T00:00:00+00:00"
                size = 0
                if "source" in media:
                    source = media["source"]
                    link = source["source"]
                    size = media["info"]["preview"]["size"] if "info" in media_api else 1
                    date = media_api["postedAt"] if "postedAt" in media_api else media_api["createdAt"]
                if "src" in media:
                    link = media["src"]
                    size = media["info"]["preview"]["size"] if "info" in media_api else 1
                    date = media_api["createdAt"]
                if not link:
                    continue
                matches = ["us", "uk", "ca", "ca2", "de"]

                url = urlparse(link)
                subdomain = url.hostname.split('.')[0]
                preview_link = media["preview"]
                if any(subdomain in nm for nm in matches):
                    subdomain = url.hostname.split('.')[1]
                    if "upload" in subdomain:
                        continue
                    if "convert" in subdomain:
                        link = preview_link
                rules = [link == "",
                         preview_link == ""]
                if all(rules):
                    continue
                new_dict = dict()
                new_dict["post_id"] = media_api["id"]
                new_dict["media_id"] = media["id"]
                new_dict["links"] = []
                for xlink in link, preview_link:
                    if xlink:
                        new_dict["links"].append(xlink)
                        break
                new_dict["price"] = media_api["price"]if "price" in media_api else None
                if date == "-001-11-30T00:00:00+00:00":
                    date_string = master_date
                    date_object = datetime.strptime(
                        master_date, "%d-%m-%Y %H:%M:%S")
                else:
                    date_object = datetime.fromisoformat(date)
                    date_string = date_object.replace(tzinfo=None).strftime(
                        "%d-%m-%Y %H:%M:%S")
                    master_date = date_string

                if media["type"] not in alt_media_type:
                    x += 1
                    continue
                if "rawText" not in media_api:
                    media_api["rawText"] = ""
                text = media_api["rawText"] if media_api["rawText"] else ""
                matches = [s for s in ignored_keywords if s in text]
                if matches:
                    print("Matches: ", matches)
                    continue
                text = main_helper.clean_text(text)
                new_dict["postedAt"] = date_string
                post_id = new_dict["post_id"]
                media_id = new_dict["media_id"]
                file_name = link.rsplit('/', 1)[-1]
                file_name, ext = os.path.splitext(file_name)
                ext = ext.__str__().replace(".", "").split('?')[0]
                media_directory = os.path.join(
                    model_directory, sorted_directories["unsorted"])
                new_dict["paid"] = False
                if new_dict["price"]:
                    if api_type in ["Messages", "Mass Messages"]:
                        new_dict["paid"] = True
                    else:
                        if media["id"] not in media_api["preview"] and media["canView"]:
                            new_dict["paid"] = True
                if sort_free_paid_posts:
                    media_directory = os.path.join(
                        model_directory, sorted_directories["free"])
                    if new_dict["paid"]:
                        media_directory = os.path.join(
                            model_directory, sorted_directories["paid"])
                file_path = main_helper.reformat(media_directory, post_id, media_id, file_name,
                                                 text, ext, date_object, username, file_directory_format, file_name_format, date_format, maximum_length)
                new_dict["text"] = text
                file_directory = os.path.dirname(file_path)
                new_dict["directory"] = os.path.join(file_directory)
                new_dict["filename"] = os.path.basename(file_path)
                new_dict["size"] = size
                if size == 0:
                    media_set2["invalid"].append(new_dict)
                    continue
                new_dict["session"] = session
                media_set2["valid"].append(new_dict)
        media_set.append(media_set2)
    return media_set


# Downloads scraped content
def download_media(media_set, session, directory, username, post_count, location, api_type):
    def download(medias, session, directory, username):
        return_bool = True
        for media in medias:
            count = 0
            session = media["session"]
            while count < 11:
                links = media["links"]

                def choose_link(session, links):
                    for link in links:
                        r = main_helper.json_request(session, link, "HEAD",
                                                     stream=True, json_format=False)
                        if not isinstance(r, requests.Response):
                            continue

                        header = r.headers
                        content_length = header.get('content-length')
                        if not content_length:
                            continue
                        content_length = int(content_length)
                        return [link, content_length]
                result = choose_link(session, links)
                if not result:
                    count += 1
                    continue
                link = result[0]
                content_length = result[1]
                date_object = datetime.strptime(
                    media["postedAt"], "%d-%m-%Y %H:%M:%S")
                download_path = os.path.join(
                    media["directory"], media["filename"])
                timestamp = date_object.timestamp()
                if not overwrite_files:
                    if main_helper.check_for_dupe_file(download_path, content_length):
                        main_helper.format_image(download_path, timestamp)
                        return_bool = False
                        break
                r = main_helper.json_request(
                    session, link, stream=True, json_format=False)
                if not isinstance(r, requests.Response):
                    return_bool = False
                    count += 1
                    continue
                downloader = main_helper.downloader(r, download_path, count)
                if not downloader:
                    count += 1
                    continue
                main_helper.format_image(download_path, timestamp)
                log_download.info("Link: {}".format(link))
                log_download.info("Path: {}".format(download_path))
                break
        return return_bool
    string = "Download Processing\n"
    string += "Name: "+username+" | Type: " + \
        api_type+" | Directory: " + directory+"\n"
    string += "Downloading "+str(len(media_set))+" "+location+"\n"
    print(string)
    pool = multiprocessing()
    pool.starmap(download, product(
        media_set, [session], [directory], [username]))


def create_session(custom_proxy="", test_ip=True):
    session = [requests.Session()]
    if not proxies:
        return session

    def set_sessions(proxy):
        session = requests.Session()
        proxy_type = {'http': 'socks5h://'+proxy,
                      'https': 'socks5h://'+proxy}
        if proxy:
            session.proxies = proxy_type
            if cert:
                session.verify = cert
        max_threads2 = cpu_count()
        session.mount(
            'https://', HTTPAdapter(pool_connections=max_threads2, pool_maxsize=max_threads2))
        if test_ip:
            link = 'https://checkip.amazonaws.com'
            r = main_helper.json_request(
                session, link, json_format=False, sleep=False)
            if not isinstance(r, requests.Response):
                print("Proxy Not Set: "+proxy+"\n")
                return
            ip = r.text.strip()
            print("Session IP: "+ip+"\n")
        return session
    pool = multiprocessing()
    sessions = []
    while not sessions:
        proxies2 = [custom_proxy] if custom_proxy else proxies
        sessions = pool.starmap(set_sessions, product(
            proxies2))
        sessions = [x for x in sessions if x]
    return sessions


# Creates an authenticated session
def create_auth(sessions, user_agent, auth_array, max_auth=2):
    me_api = []
    auth_count = 1
    auth_version = "(V1)"
    count = 1
    try:
        auth_id = auth_array["auth_id"]
        auth_cookies = [
            {'name': 'auth_id', 'value': auth_id},
            {'name': 'sess', 'value': auth_array["sess"]},
            {'name': 'auth_hash', 'value': auth_array["auth_hash"]},
            {'name': 'auth_uniq_'+auth_id, 'value': auth_array["auth_uniq_"]},
            {'name': 'auth_uid_'+auth_id, 'value': None},
            {'name': 'fp', 'value': auth_array["fp"]},
        ]
        while auth_count < max_auth+1:
            if auth_count == 2:
                auth_version = "(V2)"
                if auth_array["sess"]:
                    del auth_cookies[2]
                count = 1
            print("Auth "+auth_version)
            sess = auth_array["sess"]
            for session in sessions:
                session.headers = {
                    'user-agent': user_agent, 'referer': 'https://onlyfans.com/'}
                if auth_array["sess"]:
                    found = False
                    for auth_cookie in auth_cookies:
                        if auth_array["sess"] == auth_cookie["value"]:
                            found = True
                            break
                    if not found:
                        auth_cookies.append(
                            {'name': 'sess', 'value': auth_array["sess"], 'domain': '.onlyfans.com'})
                for auth_cookie in auth_cookies:
                    session.cookies.set(**auth_cookie)

            max_count = 10
            while count < 11:
                print("Auth Attempt "+str(count)+"/"+str(max_count))
                link = f"https://onlyfans.com/api2/v2/users/customer?app-token={app_token}"
                for session in sessions:
                    a = [session, link, sess, user_agent]
                    session = main_helper.create_sign(*a)
                session = sessions[0]
                r = main_helper.json_request(session, link, sleep=False)
                count += 1
                if not r:
                    continue
                me_api = r

                def resolve_auth(r):
                    if 'error' in r:
                        error = r["error"]
                        error_message = r["error"]["message"]
                        error_code = error["code"]
                        if error_code == 0:
                            print(error_message)
                        if error_code == 101:
                            error_message = "Blocked by 2FA."
                            print(error_message)
                            if auth_array["support_2fa"]:
                                link = f"https://onlyfans.com/api2/v2/users/otp?app-token={app_token}"
                                count = 1
                                max_count = 3
                                while count < max_count+1:
                                    print("2FA Attempt "+str(count) +
                                          "/"+str(max_count))
                                    code = input("Enter 2FA Code\n")
                                    data = {'code': code, 'rememberMe': True}
                                    r = main_helper.json_request(
                                        session, link, "PUT", data=data)
                                    if "error" in r:
                                        count += 1
                                    else:
                                        print("Success")
                                        return [True, r]
                        return [False, r["error"]["message"]]
                if "name" not in r:
                    result = resolve_auth(r)
                    if not result[0]:
                        error_message = result[1]
                        if "token" in error_message:
                            break
                        if "Code wrong" in error_message:
                            break
                        continue
                    else:
                        continue
                print("Welcome "+r["name"])
                option_string = "username or profile link"
                link = f"https://onlyfans.com/api2/v2/subscriptions/count/all?app-token={app_token}"
                r = main_helper.json_request(session, link, sleep=False)
                if not r:
                    break
                array = dict()
                array["sessions"] = sessions
                array["option_string"] = option_string
                array["subscriber_count"] = r["subscriptions"]["active"]
                array["me_api"] = me_api
                return array
            auth_count += 1
    except Exception as e:
        main_helper.log_error.exception(e)
    array = dict()
    array["sessions"] = None
    array["me_api"] = me_api
    return array


def get_subscriptions(session, subscriber_count, me_api, auth_count=0):
    link = f"https://onlyfans.com/api2/v2/subscriptions/subscribes?offset=0&type=active&limit=99&app-token={app_token}"
    ceil = math.ceil(subscriber_count / 99)
    a = list(range(ceil))
    offset_array = []
    for b in a:
        b = b * 99
        offset_array.append(
            [link.replace("offset=0", "offset=" + str(b)), False])
    if me_api["isPerformer"]:
        link = f"https://onlyfans.com/api2/v2/users/{me_api['id']}?app-token={app_token}"
        offset_array = [[link, True]] + offset_array

    def multi(array, session):
        link = array[0]
        performer = array[1]
        r = main_helper.json_request(session, link)
        # Following logic is unique to creators only
        if performer:
            if isinstance(r, dict):
                if not r["subscribedByData"]:
                    r["subscribedByData"] = dict()
                    start_date = datetime.utcnow()
                    end_date = start_date + relativedelta(years=1)
                    end_date = end_date.isoformat()
                    r["subscribedByData"]["expiredAt"] = end_date
                    r["subscribedByData"]["price"] = r["subscribePrice"]
                    r["subscribedByData"]["subscribePrice"] = 0
            if None != r:
                r = [r]
        return r
    pool = multiprocessing()
    results = pool.starmap(multi, product(
        offset_array, [session]))
    results = [x for x in results if x is not None]
    results = list(chain(*results))
    if blacklist_name:
        link = f"https://onlyfans.com/api2/v2/lists?offset=0&limit=100&app-token={app_token}"
        r = main_helper.json_request(session, link)
        if not r:
            return [False, []]
        x = [c for c in r if blacklist_name == c["name"]]
        if x:
            x = x[0]
            list_users = x["users"]
            if x["usersCount"] > 2:
                list_id = str(x["id"])
                link = f"https://onlyfans.com/api2/v2/lists/{list_id}/users?offset=0&limit=100&query=&app-token={app_token}"
                r = main_helper.json_request(session, link)
                list_users = r
            users = list_users
            bl_ids = [x["username"] for x in users]
            results2 = results.copy()
            for result in results2:
                identifier = result["username"]
                if identifier in bl_ids:
                    print("Blacklisted: "+identifier)
                    results.remove(result)
    if any("error" in result for result in results):
        print("Invalid App Token")
        return []
    else:
        results.sort(key=lambda x: x["subscribedByData"]['expiredAt'])
        results2 = []
        for result in results:
            result["auth_count"] = auth_count
            result["self"] = False
            username = result["username"]
            now = datetime.utcnow().date()
            # subscribedBy = result["subscribedBy"]
            subscribedByData = result["subscribedByData"]
            result_date = subscribedByData["expiredAt"] if subscribedByData else datetime.utcnow(
            ).isoformat()
            price = subscribedByData["price"]
            subscribePrice = subscribedByData["subscribePrice"]
            result_date = datetime.fromisoformat(
                result_date).replace(tzinfo=None).date()
            if ignore_type in ["paid"]:
                if price > 0:
                    continue
            if ignore_type in ["free"]:
                if subscribePrice == 0:
                    continue
            results2.append(result)
        return results2


# Ah yes, the feature that will probably never be done
def get_paid_posts(sessions):
    paid_api = f"https://onlyfans.com/api2/v2/posts/paid?limit=100&offset=0&app-token={app_token}"
    x = main_helper.create_link_group(max_threads)
    print
    result = {}
    result["link"] = paid_api
    directory = []
    print
    x = media_scraper(paid_api, sessions, "a", "a", "a")
    print


def format_options(array, choice_type):
    new_item = {}
    new_item["auth_count"] = -1
    new_item["username"] = "All"
    array = [new_item]+array
    name_count = len(array)

    count = 0
    names = []
    string = ""
    if "usernames" == choice_type:
        for x in array:
            name = x["username"]
            string += str(count)+" = "+name
            names.append([x["auth_count"], name])
            if count+1 != name_count:
                string += " | "
            count += 1
    if "apis" == choice_type:
        names = array
        for api in array:
            if "username" in api:
                name = api["username"]
            else:
                name = api["api_type"]
            string += str(count)+" = "+name
            if count+1 != name_count:
                string += " | "
            count += 1
    return [names, string]
