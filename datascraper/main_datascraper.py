from timeit import main
from classes.prepare_metadata import prepare_metadata
import json
import logging
import os
import time
import timeit
from argparse import ArgumentParser
import helpers.main_helper as main_helper
import modules.bbwchan as bbwchan
import modules.fourchan as fourchan
import modules.onlyfans as onlyfans
import modules.patreon as patreon
import modules.starsavn as starsavn




def start_datascraper():
    parser = ArgumentParser()
    parser.add_argument("-m", "--metadata", action='store_true',
                        help="only exports metadata")
    parser.add_argument("-n", "--number",default=100000)
    args = parser.parse_args()
    number = int(args.number)
    if args.metadata:
        print("Exporting Metadata Only")
    log_error = main_helper.setup_logger('errors', 'errors.log')
    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s %(name)s %(message)s')
    console.setFormatter(formatter)
    logging.getLogger("").addHandler(console)
    # root = os.getcwd()
    config_path = os.path.join('.settings', 'config.json')
    json_config, json_config2 = main_helper.get_config(config_path)
    json_settings = json_config["settings"]
    json_sites = json_config["supported"]
    infinite_loop = json_settings["infinite_loop"]
    global_user_agent = json_settings['global_user_agent']
    domain = json_settings["auto_site_choice"]
    path = os.path.join('.settings', 'extra_auth.json')
    extra_auth_config, extra_auth_config2 = main_helper.get_config(path)
    exit_on_completion = json_settings['exit_on_completion']
    loop_timeout = json_settings['loop_timeout']
    main_helper.assign_vars(json_config)

    string = "Site: "
    site_names = []
    bl = ["patreon"]
    if not domain:
        site_count = len(json_sites)
        count = 0
        for x in json_sites:
            if x in bl:
                continue
            string += str(count)+" = "+x
            site_names.append(x)
            if count+1 != site_count:
                string += " | "

            count += 1
        string += "x = Exit"

    try:
        while True:
            if domain:
                site_name = domain
            else:
                print(string)
                x = input()
                if x == "x":
                    break
                x = int(x)
                site_name = site_names[x]
            site_name_lower = site_name.lower()

            json_auth_array = [json_sites[site_name_lower]
                               ["auth"]]

            json_site_settings = json_sites[site_name_lower]["settings"]
            auto_scrape_names = json_site_settings["auto_scrape_names"]
            extra_auth_settings = json_sites[site_name_lower]["extra_auth_settings"] if "extra_auth_settings" in json_sites[site_name_lower] else {
                "extra_auth": False}
            extra_auth = extra_auth_settings["extra_auth"]
            if extra_auth:
                choose_auth = extra_auth_settings["choose_auth"]
                merge_auth = extra_auth_settings["merge_auth"]
                json_auth_array += extra_auth_config["supported"][site_name_lower]["auths"]
                if choose_auth:
                    json_auth_array = main_helper.choose_auth(json_auth_array)
            session_array = []
            x = onlyfans
            subscription_array = []
            legacy = True
            if site_name_lower == "onlyfans":
                legacy = False
                site_name = "OnlyFans"
                subscription_array = []
                auth_count = -1
                for json_auth in json_auth_array:
                    auth_count += 1
                    user_agent = global_user_agent if not json_auth[
                        'user_agent'] else json_auth['user_agent']

                    x = onlyfans
                    x.assign_vars(json_auth, json_config,
                                  json_site_settings, site_name)
                    sessions = x.create_session()
                    if not sessions:
                        print("Unable to create session")
                        continue
                    session = x.create_auth(sessions,
                                            user_agent, json_auth, max_auth=1)
                    session_array.append(session)
                    if not session["sessions"]:
                        continue
                    # x.get_paid_posts(session["sessions"][0])
                    print
                    cookies = session["sessions"][0].cookies.get_dict()
                    auth_id = cookies["auth_id"]
                    json_auth['auth_id'] = auth_id
                    json_auth['auth_uniq_'] = cookies["auth_uniq_"+auth_id]
                    json_auth['auth_hash'] = cookies["auth_hash"]
                    json_auth['sess'] = cookies["sess"]
                    json_auth['fp'] = cookies["fp"]
                    if json_config != json_config2:
                        main_helper.update_config(json_config)
                    me_api = session["me_api"]
                    array = x.get_subscriptions(
                        session["sessions"][0], session["subscriber_count"], me_api, auth_count)
                    subscription_array += array
                subscription_array = x.format_options(
                    subscription_array, "usernames")
            if site_name_lower == "patreon":
                legacy = False
                site_name = "Patreon"
                subscription_array = []
                auth_count = -1
                x = patreon
                x.assign_vars(json_config, json_site_settings, site_name)
                for json_auth in json_auth_array:
                    auth_count += 1
                    user_agent = global_user_agent if not json_auth[
                        'user_agent'] else json_auth['user_agent']

                    session = x.create_session()
                    session = x.create_auth(session,
                                            user_agent, json_auth)
                    session_array.append(session)
                    if not session["session"]:
                        continue
                    cookies = session["session"].cookies.get_dict()
                    json_auth['session_id'] = cookies["session_id"]
                    if json_config != json_config2:
                        main_helper.update_config(json_config)
                    me_api = session["me_api"]
                    array = x.get_subscriptions(
                        session["session"], auth_count)
                    subscription_array += array
                subscription_array = x.format_options(
                    subscription_array, "usernames")
            elif site_name_lower == "starsavn":
                legacy = False
                site_name = "StarsAVN"
                subscription_array = []
                auth_count = -1
                for json_auth in json_auth_array:
                    auth_count += 1
                    user_agent = global_user_agent if not json_auth[
                        'user_agent'] else json_auth['user_agent']

                    x = starsavn
                    x.assign_vars(json_config, json_site_settings, site_name)
                    sessions = x.create_session()
                    if not sessions:
                        print("Unable to create session")
                        continue
                    session = x.create_auth(sessions,
                                            user_agent, json_auth, max_auth=1)
                    session_array.append(session)
                    if not session["sessions"]:
                        continue

                    me_api = session["me_api"]
                    array = x.get_subscriptions(
                        session["sessions"][0], session["subscriber_count"], me_api, auth_count)
                    subscription_array += array
                subscription_array = x.format_options(
                    subscription_array, "usernames")
            elif site_name == "fourchan":
                x = fourchan
                site_name = "4Chan"
                x.assign_vars(json_config, json_site_settings, site_name)
                session_array = [x.create_session()]
                array = x.get_subscriptions()
                subscription_array = x.format_options(array)
            elif site_name == "bbwchan":
                x = bbwchan
                site_name = "BBWChan"
                x.assign_vars(json_config, json_site_settings, site_name)
                session_array = [x.create_session()]
                array = x.get_subscriptions()
                subscription_array = x.format_options(array)
            names = subscription_array[0]
            if names:
                print("Names: Username = username | "+subscription_array[1])
                length=len(names)-1
                if not auto_scrape_names and number==100000:
                    value = "2"
                    value = input().strip()
                    if value.isdigit():
                        if value == "0":
                            names = names[1:]
                        else:
                            names = [names[int(value)]]
                    else:
                        names = [name for name in names if value in name[1]]
                elif number != 100000 and number-1>length:
                    print("Number out of Range")
                    quit()

                elif number != 100000:
                    value = number
                    names = [names[int(value)]]
                else:
                    value = 0
                    names = names[1:]
            else:
                print("There's nothing to scrape.")
                continue
            archive_time = timeit.default_timer()
            download_list = []
            app_token = ""
            for name in names:
                # Extra Auth Support
                if not legacy:
                    json_auth = json_auth_array[name[0]]
                    app_token = json_auth["app_token"] if "app_token" in json_auth else ""
                    auth_count = name[0]
                    if "session" in session_array[auth_count]:
                        session = session_array[auth_count]["session"]
                    else:
                        session = session_array[auth_count]["sessions"]
                    name = name[-1]
                else:
                    session = session_array[0]["session"]
                main_helper.assign_vars(json_config)
                username = main_helper.parse_links(site_name_lower, name)
                result = x.start_datascraper(
                    session, username, site_name, app_token, choice_type=value)
                if result[0]:
                    download_list.append(result)
            for item in download_list:
                result = item[1]
                if not result["subbed"]:
                    continue
                download = result["download"]
                others = download.others
                if not others:
                    continue
                model_directory = os.path.join(others[0][2], others[0][3])
                if not args.metadata:
                    for arg in others:
                        x.download_media(*arg)
                main_helper.delete_empty_directories(model_directory)
                main_helper.send_webhook(download)
            stop_time = str(
                int(timeit.default_timer() - archive_time) / 60)[:4]
            print('Archive Completed in ' + stop_time + ' Minutes')
            if exit_on_completion:
                print("Now exiting.")
                exit(0)
            elif not infinite_loop:
                print("Input anything to continue")
                input()
            elif loop_timeout:
                print('Pausing scraper for ' + loop_timeout + ' seconds.')
                time.sleep(int(loop_timeout))
    except Exception as e:
        log_error.exception(e)
        input()
