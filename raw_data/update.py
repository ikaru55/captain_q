"""
Author: Jinwook Lee (justivita21@gmail.com)

File: update.py
Description: 
    - raw_data/config.json, raw_data/raw_filter.txt 파일을 업데이트하는 코드
    - Prod Airflow에서 매일 10:00 AM에 실행됩니다.
"""
from atlassian import Confluence
import openai
import json
import threading
import time
from datetime import datetime, timedelta

############################# Private Section #################################
# You have to Fill below Area

openai.api_type = ""
openai.api_version = ""
openai.api_base = ""
openai.api_key = ""

CONFLUENCE_URL = ""
CONFLUENCE_USER = ""
CONFLUENCE_API_TOKEN = ""

confluence = Confluence(
    url= CONFLUENCE_URL,
    username=CONFLUENCE_USER,
    password=CONFLUENCE_API_TOKEN,
    cloud=True,
)

ROOT_PAGE_ID = ""
# Root Page refers the page which is the highest node page in confluence space (main home page).

##############################################################################################
def GPT4_request_message(messages):
    """
    Given a prompt and a dictionary of GPT parameters, make a request to OpenAI
    server and returns the response.
    ARGS:
      prompt: a str prompt
      gpt_parameter: a python dictionary with the keys indicating the names of
                     the parameter and the values indicating the parameter
                     values.
    RETURNS:
      a str of GPT-3's response.
    """
    try:
        completion = openai.ChatCompletion.create(
            engine="gpt-4-32k-0613", messages=messages, temperature=1, top_p=1
        )
        return completion["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Error occurred: {e}")


def GPT4_summary_request_message(messages):
    """
    Given a prompt and a dictionary of GPT parameters, make a request to OpenAI
    server and returns the response.
    ARGS:
      prompt: a str prompt
      gpt_parameter: a python dictionary with the keys indicating the names of
                     the parameter and the values indicating the parameter
                     values.
    RETURNS:
      a str of GPT-4-32k's response.
    """
    for i in range(100):
        try:
            completion = openai.ChatCompletion.create(
                engine="gpt-4-32k", messages=messages, temperature=0, top_p=0.1
            )
            return completion["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"Error occurred: {e}")
            if "maximum" in str(e):  # Token Limit 넘은 경우
                print(messages)
                return None
            time.sleep(5)
            pass
    return None


def get_child_page_list(parent_page_id):
    children_list = confluence.get_page_child_by_type(
        page_id=parent_page_id, type="page"
    )
    return children_list


def get_new_hiearachy_dict():
    main_page_list = get_child_page_list(ROOT_PAGE_ID)
    main_page_id_list = [page["id"] for page in main_page_list]
    hiearachy_dict = {}
    for main_page_id in main_page_id_list:
        hiearachy_dict[main_page_id] = {}
        sub_1_page_list = get_child_page_list(main_page_id)
        sub_1_page_id_list = [page["id"] for page in sub_1_page_list]
        if sub_1_page_id_list:
            for sub_1_page_id in sub_1_page_id_list:
                hiearachy_dict[main_page_id][sub_1_page_id] = {}
                sub_2_page_list = get_child_page_list(sub_1_page_id)
                sub_2_page_id_list = [page["id"] for page in sub_2_page_list]
                if sub_2_page_id_list:
                    for sub_2_page_id in sub_2_page_id_list:
                        hiearachy_dict[main_page_id][sub_1_page_id][sub_2_page_id] = {}
                        sub_3_page_list = get_child_page_list(sub_2_page_id)
                        sub_3_page_id_list = [page["id"] for page in sub_3_page_list]
                        if sub_3_page_id_list:
                            for sub_3_page_id in sub_3_page_id_list:
                                hiearachy_dict[main_page_id][sub_1_page_id][
                                    sub_2_page_id
                                ][sub_3_page_id] = {}
    return hiearachy_dict


def extract_all_keys_from_dict(d, parent_key=""):
    keys = []
    for k, v in d.items():
        new_key = k
        keys.append(new_key)
        if isinstance(v, dict):
            keys.extend(extract_all_keys_from_dict(v, new_key))
    return keys


def get_ori_config_dict():
    try:
        with open("raw_data/config.json", "r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError:
        print("get_ori_config_dict: config.json file not found.")
        raise
    return data


def page_id_to_title(page_id):
    page_data = confluence.get_page_by_id(
        page_id, expand="body.storage", status=None, version=None
    )
    page_title = page_data["title"]
    return page_title


def page_id_to_str(page_id):
    page_data = confluence.get_page_by_id(
        page_id, expand="body.storage", status=None, version=None
    )
    page_content_string = page_data["body"]["storage"]["value"]
    return page_content_string


def find_key_path(d, target_key, path=[]):
    if target_key in d:
        return path + [target_key]
    for key, value in d.items():
        if isinstance(value, dict):
            new_path = find_key_path(value, target_key, path + [key])
            if new_path:
                return new_path
    return None


def get_new_page_id_to_child_list_dict(new_config_dict):
    page_id_list = new_config_dict["page_id_list"]
    new_page_id_to_child_list_dict = {}
    for id in page_id_list:
        child_list = get_child_page_list(id)
        child_id_list = [page["id"] for page in child_list]
        new_page_id_to_child_list_dict[id] = child_id_list
    return new_page_id_to_child_list_dict


def get_new_page_id_to_title_dict(new_config_dict):
    page_id_list = new_config_dict["page_id_list"]
    new_page_id_to_title_dict = {}
    for id in page_id_list:
        title = page_id_to_title(id)
        new_page_id_to_title_dict[id] = title
    return new_page_id_to_title_dict


def get_new_page_id_to_summary_dict(new_config_dict, ori_config_dict):
    page_id_list = new_config_dict["page_id_list"]
    sum_dict = ori_config_dict["page_id_to_summary_dict"].copy()
    sum_dict_lock = threading.Lock()  # sum_dict의 동시 접근을 방지하기 위한 락

    def process_page(page_id):
        page_data = confluence.get_page_by_id(
            page_id, expand="version", status=None, version=None
        )
        recent_update_date = datetime.strptime(
            page_data["version"]["when"], "%Y-%m-%dT%H:%M:%S.%fZ"
        )
        if (
            datetime.now() - recent_update_date < timedelta(days=1)
            or page_id not in sum_dict
        ):
            summary = get_raw_filter_summary(page_id)
            with sum_dict_lock:  # 동시 접근을 방지하기 위해 락을 사용
                if summary:
                    sum_dict[page_id] = summary

    threads = []
    for page_id in page_id_list:
        thread = threading.Thread(target=process_page, args=(page_id,))
        thread.start()
        threads.append(thread)
    # 모든 쓰레드가 완료될 때까지 기다림
    for thread in threads:
        thread.join()

    for page_id in list(sum_dict.keys()):
        if page_id not in page_id_list:
            del sum_dict[page_id]
    return sum_dict


def get_raw_filter_name(path_list, page_id):
    name = ""
    for path in path_list:
        name += page_id_to_title(path) + "."
    name = name[:-1]
    name = name + "|" + page_id
    return name


def get_raw_filter_summary(page_id):
    page_str_data = page_id_to_str(page_id)
    page_title = page_id_to_title(page_id)
    sample = """
    해당 문서는 이전에 X11 느린 개발 환경을 개선하기 위한 Windows와 Samba 개발 환경 구축 방법을 설명하고 있습니다. 
    """
    prompt = f"""
    You have to use provided data for Summarizing of Document.
    I will use the Summarized data for document search.
    For document searching, please summarize provided data no more than 100 characters.
    Summarized data should contain whole overall content of the documentation, not detail content.
    Output Sample:
    {sample}
    if there is no data to summarize, please write "데이터가 존재하지 않습니다"
    Please summarize as Korean.
    """
    messages = [
        {
            "role": "system",
            "content": f"The following document's title is <{page_title}>. \n Document content : {page_str_data}",
        },
        {"role": "system", "content": f"{prompt}"},
    ]
    sum = GPT4_summary_request_message(messages)
    return sum


###########################################################################################
def update_new_config_dict():
    ori_config_dict = get_ori_config_dict()
    new_config_dict = ori_config_dict.copy()
    print("update_new_config_dict: Hierarchy 1/7")
    new_hiearachy_dict = get_new_hiearachy_dict()
    new_config_dict["page_hierarchy_dict"] = new_hiearachy_dict
    print("update_new_config_dict: page_id 2/7")
    new_page_id_list = extract_all_keys_from_dict(new_hiearachy_dict)
    new_config_dict["page_id_list"] = new_page_id_list
    print("update_new_config_dict: Main page_id 3/7")
    new_main_page_id_list = [id for id in new_hiearachy_dict.keys()]
    new_config_dict["main_page_id_list"] = new_main_page_id_list
    print("update_new_config_dict: Child list 4/7")
    new_page_id_to_child_list_dict = get_new_page_id_to_child_list_dict(new_config_dict)
    new_config_dict["page_id_to_child_list_dict"] = new_page_id_to_child_list_dict
    print("update_new_config_dict: Title 5/7")
    new_page_id_to_title_dict = get_new_page_id_to_title_dict(new_config_dict)
    new_config_dict["page_id_to_title_dict"] = new_page_id_to_title_dict
    print("update_new_config_dict: Summary 6/7")
    new_page_id_to_summary_dict = get_new_page_id_to_summary_dict(
        new_config_dict, ori_config_dict
    )
    new_config_dict["page_id_to_summary_dict"] = new_page_id_to_summary_dict
    print("update_new_config_dict: json Update 7/7")
    with open("raw_data/config.json", "w", encoding="utf-8") as file:
        json.dump(new_config_dict, file, indent=4, ensure_ascii=False)
    return new_config_dict


def update_raw_filter(new_config_dict):
    print("update_raw_filter: data_load 0/2")
    BASE_STR = """
    The Following Text is Summary of Company Documents.
    This Text will be used to search Company Documents for Company Documents User.
    Each document may have subdocuments, hierachy is indicated with dot in title.
    Format of Page information:
        <main-doc_title>.<sub-doc_title>.<sub-sub-doc_title>...|Document_ID
        - <Summary of Document>

    Documents DATA:
    """
    result = BASE_STR
    page_hierarchy_dict = new_config_dict["page_hierarchy_dict"]
    page_id_to_title_dict = new_config_dict["page_id_to_title_dict"]
    sum_page = new_config_dict["page_id_to_summary_dict"]
    print("update_raw_filter: rearrange 1/2")
    for main_page_id in page_hierarchy_dict:
        data_str = f"""
        {page_id_to_title_dict[main_page_id]}|{main_page_id}
        - {sum_page[main_page_id]}
        """
        if page_hierarchy_dict[main_page_id]:
            for sub_1_page_id in page_hierarchy_dict[main_page_id]:
                sub_1_data_str = f"""
                {page_id_to_title_dict[main_page_id]}.{page_id_to_title_dict[sub_1_page_id]}|{sub_1_page_id}
                - {sum_page[sub_1_page_id]}
                """
                data_str += sub_1_data_str
                if page_hierarchy_dict[main_page_id][sub_1_page_id]:
                    for sub_2_page_id in page_hierarchy_dict[main_page_id][
                        sub_1_page_id
                    ]:
                        sub_2_data_str = f"""
                        {page_id_to_title_dict[main_page_id]}.{page_id_to_title_dict[sub_1_page_id]}.{page_id_to_title_dict[sub_2_page_id]}|{sub_2_page_id}
                        - {sum_page[sub_2_page_id]}
                        """
                        data_str += sub_2_data_str
                        if page_hierarchy_dict[main_page_id][sub_1_page_id][
                            sub_2_page_id
                        ]:
                            for sub_3_page_id in page_hierarchy_dict[main_page_id][
                                sub_1_page_id
                            ][sub_2_page_id]:
                                sub_3_data_str = f"""
                                {page_id_to_title_dict[main_page_id]}.{page_id_to_title_dict[sub_1_page_id]}.{page_id_to_title_dict[sub_2_page_id]}.{page_id_to_title_dict[sub_3_page_id]}|{sub_3_page_id}
                                - {sum_page[sub_3_page_id]}
                                """
                                data_str += sub_3_data_str
        result += data_str
    print("update_raw_filter: raw_filter.txt Update 2/2")
    with open("raw_data/raw_filter.txt", "w", encoding="utf-8") as file:
        file.write(result)
    return result


def run():
    new_config_dict = update_new_config_dict()
    new_raw_filter = update_raw_filter(new_config_dict)
    return


if __name__ == "__main__":
    run()
