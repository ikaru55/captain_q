"""
Author: Jinwook Lee (justivita21@gmail.com)

File: main.py
Description: 
    - Slack에서 Bot의 응답을 관리하는 메인 코드입니다.
    - raw_filter의 데이터를 기반으로 관련 페이지를 필터링하고, 필터링한 문서의 내용을 기반으로 검색 결과를 생성합니다.
"""
from atlassian import Confluence
import tiktoken
import openai
import json
import os
import re
import time
from bs4 import BeautifulSoup

from typing import List
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk import WebClient
from slack_bolt import App
from datetime import datetime, timedelta

## Private Section (Need to Fill)

openai.api_type = ""
openai.api_version = ""
openai.api_base = ""
openai.api_key = ""

SLACK_BOT_TOKEN = ""
SLACK_APP_TOKEN = ""
APP_ID = ""

CONFLUENCE_URL = ""
CONFLUENCE_USER = ""
CONFLUENCE_API_TOKEN = ""

####################################################################################
## GPT Request Section
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
      a str of GPT-4-32k's response.
    """
    for i in range(5):
        try:
            completion = openai.ChatCompletion.create(
                engine="gpt-4-32k", messages=messages, temperature=0, top_p=0.1
            )
            return completion["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"Error occurred: {e}")
            if "32768" in str(e):  # Token Limit 넘은 경우
                del messages[-4]
            time.sleep(2**i)
            pass
    return e


def num_tokens_from_messages(messages, model="gpt-4-32k"):
    """Return the number of tokens used by a list of messages."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        print("Warning: model not found. Using cl100k_base encoding.")
        encoding = tiktoken.get_encoding("cl100k_base")
    if model in {
        "gpt-3.5-turbo-0613",
        "gpt-3.5-turbo-16k-0613",
        "gpt-4-0314",
        "gpt-4-32k",
        "gpt-4-0613",
        "gpt-4-32k",
    }:
        tokens_per_message = 3
        tokens_per_name = 1
    elif model == "gpt-3.5-turbo-0301":
        tokens_per_message = (
            4  # every message follows <|start|>{role/name}\n{content}<|end|>\n
        )
        tokens_per_name = -1  # if there's a name, the role is omitted
    elif "gpt-3.5-turbo" in model:
        print(
            "Warning: gpt-3.5-turbo may update over time. Returning num tokens assuming gpt-3.5-turbo-0613."
        )
        return num_tokens_from_messages(messages, model="gpt-3.5-turbo-0613")
    elif "gpt-4" in model:
        print(
            "Warning: gpt-4 may update over time. Returning num tokens assuming gpt-4-0613."
        )
        return num_tokens_from_messages(messages, model="gpt-4-0613")
    else:
        raise NotImplementedError(
            f"""num_tokens_from_messages() is not implemented for model {model}. See https://github.com/openai/openai-python/blob/main/chatml.md for information on how messages are converted to tokens."""
        )
    num_tokens = 0
    for message in messages:
        num_tokens += tokens_per_message
        for key, value in message.items():
            num_tokens += len(encoding.encode(value))
            if key == "name":
                num_tokens += tokens_per_name
    num_tokens += 3  # every reply is primed with <|start|>assistant<|message|>
    return num_tokens


####################################################################################
## Search Section
# 하위 자료 참조 함수 Area
def get_child_list(page_id, config):
    PAGE_ID_TO_CHILD_DICT = config["page_id_to_child_list_dict"]
    child_list = PAGE_ID_TO_CHILD_DICT[page_id]
    return child_list


def parse_html_tag(page_text):
    soup = BeautifulSoup(page_text, "html.parser")
    result_str = ""

    # Handle <h2> tags
    for h2 in soup.find_all("h2"):
        result_str += h2.text.strip() + "\n"

    # Handle <p> tags
    for p in soup.find_all("p"):
        result_str += p.text.strip() + "\n"

    # Handle <table> tags
    table = soup.find("table")
    if table:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["th", "td"])
            cell_data = [cell.text.strip() for cell in cells]
            result_str += "\n".join(cell_data) + "\n"

    return result_str

def get_message_from_page_id(page_id):
    try:
        page_data = confluence.get_page_by_id(
            page_id, expand="body.storage", status=None, version=None
        )
    except Exception as e:  # 예외 유형과 오류 메시지를 출력하도록 개선
        print(f"An error occurred: {e}")
        return None
    title = page_data["title"]
    page_content_string = page_data["body"]["storage"]["value"]
    parsed_page_content_string = parse_html_tag(page_content_string)
    message = {
        "role": "system",
        "content": f"You have to use this information to response for Company Docs Search. \n Document_title:{title} \n Document_id: {page_id} \n Document Inforamation: {parsed_page_content_string}",
    }
    return message


def log_user_term(user, filename="user_term.log", app_name="Wiki_Bot"):
    with open(filename, "a") as f:
        f.write(f"{datetime.now()}\t{app_name}\t{user}\n")
    return


def get_related_page_id_list(user):
    with open("raw_data/raw_filter.txt", "r", encoding="utf-8") as file:
        RAW_DATA_STR = file.read()
    RELATED_PAGE_PROMPT = f"""
    You're the Search application for Document search engine.
    Your task is extract all related Document's ID from provided data as many as possible.
    if over 10 document choose the most relevant 10 Docs among extracted documents.
    Make sure that what is more relevant document for the Search Term.
    Search Terms:
    {user}
    The document number order of the response is based on relevance to the search Terms.
    output sample:
        Related Document's ID:
        |12345668|
        |23124255|
        |8568632524|
        ...
    Make sure that your response's ID is in Provided data.
    if there is no related output:
        Nothing
    """
    messages = [
        {"role": "system", "content": f"{RAW_DATA_STR}"},
        {"role": "system", "content": f"{RELATED_PAGE_PROMPT}"},
    ]
    response = GPT4_request_message(messages)
    raw_related_doc_id_list = response.split("|")[1:]
    related_doc_id_list = [id for id in raw_related_doc_id_list if len(id) >= 4]
    return related_doc_id_list


def get_page_info_messages(page_id_list, config):
    messages = []
    used_page_id_list = []
    for page_id in page_id_list:
        if page_id not in used_page_id_list:
            temp_message = get_message_from_page_id(page_id)
            if not temp_message:
                continue
            messages.append(temp_message)
            used_page_id_list.append(page_id)
            child_list = get_child_list(page_id, config)
            if child_list:
                for child in child_list:
                    if child not in used_page_id_list:
                        temp_sub_message = get_message_from_page_id(child)
                        messages.append(temp_sub_message)
                        used_page_id_list.append(child)
                    else:
                        continue
    if num_tokens_from_messages(messages) > 30000:
        print("Too many tokens. Returning only the first page.")
        messages = []
        for page_id in page_id_list:
            temp_message = get_message_from_page_id(page_id)
            if not temp_message:
                continue
            messages.append(temp_message)
    return messages


def detail_search_response(page_id_list, user, config, user_info):
    messages = get_page_info_messages(page_id_list, config)
    USER_NAME_N_TIME = f"""
    Current Time:{datetime.now()} 
    Current Search User Name:{user_info["user"]["profile"]["display_name"]}
    """
    messages.append({"role": "system", "content": f"{USER_NAME_N_TIME}"})
    SAMPLE = f"""
        이 외의 사항은 <document_title> (Document_id: <document_id>) 문서를 참고해주세요
        {CONFLUENCE_URL}/wiki/spaces/yourspacename/pages/<document_id>
        """
    DETAIL_SEARCH_PROMPT = f"""
    Your task is providing Proper information for Company docs Search.
    You're the bot for Company information QnA.
    You have to find proper information that related to Search Term from provided information and response properly.
    Search Term:
    {user}
    If there is any related link or detail page link please contain it.
    At the end of response add the following response with fill the most relevant <document_id>:
    {SAMPLE}
    if there is no data please return as Below:
    죄송합니다 관련된 내용을 찾을 수 없었습니다.
    다른 검색어로 검색해주세요.
    하지만, 관련된 내용이 있을 것이라고 유추되는 몇가지 문서를 추천해드리겠습니다.
    1. <document_title>
        {CONFLUENCE_URL}/wiki/spaces/yourspacename/pages/<document_id>
    2. <document_title>
        {CONFLUENCE_URL}/wiki/spaces/yourspacename/pages/<document_id>
    ...
    """
    prompt_message = {"role": "system", "content": f"{DETAIL_SEARCH_PROMPT}"}
    messages.append(prompt_message)
    return messages


def update_cache(user, messages):
    try:
        with open("cache.json", "r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError:
        data = {}

    new_data = {}
    for history in data:
        if data[history]["time"]:
            history_date = datetime.strptime(data[history]["time"], "%Y-%m-%dT%H:%M:%S")
            if history_date > datetime.now() - timedelta(days=1):
                new_data[history] = data[history]
    new_data[user] = {
        "time": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "messages": messages,
    }
    with open("cache.json", "w", encoding="utf-8") as file:
        json.dump(new_data, file, indent=4, ensure_ascii=False)
    return


def get_cache(user):
    with open("cache.json", "r") as file:
        data = json.load(file)
    try:
        messages = data[user]["messages"]
        return messages
    except:
        return None


####################################################################################
## Slack Section

app = App(token=SLACK_BOT_TOKEN)
client = WebClient(SLACK_BOT_TOKEN)


def log_event(name):
    print(f"{'=' * 10} {name} {'=' * 10}")


def pack_messages_to_gpt(messages: List[dict]):
    pack_messages = []
    for m in messages:
        content = re.sub("<@[^>]+>", "", m["text"])
        if m["user"] == APP_ID:
            role = "assistant"
        else:
            role = "user"
        pack_messages.append({"role": role, "content": content})
    return pack_messages


def get_config_dict():
    try:
        with open("raw_data/config.json", "r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError:
        print("get_config_dict() : config.json not found")
        data = {}
    return data


def get_user_permission(user_id):
    try:
        user_info = client.users_info(user=user_id)
    except:
        return None
    return user_info


####################################################################################
def send_slack_message(body, user):
    config = get_config_dict()
    channel = body["event"]["channel"]
    USER_ID = body["event"]["user"]
    user_info = get_user_permission(USER_ID)
    if (
        not user_info
        or user_info["is_restricted"]
        or user_info["is_ultra_restricted"]
        or ("is_stranger" in user_info and user_info["is_stranger"])
    ):
        answer = "권한이 없습니다. 관리자에게 문의해주세요."
        response = client.chat_postMessage(
            channel=channel, thread_ts=thread_ts, text=answer
        )
        return
    log_user_term(user)
    is_in_thread = "thread_ts" in body["event"]
    if is_in_thread:
        print(f"(In Thread) Ask Term : {user}")
        thread_ts = body["event"]["thread_ts"]
        a = client.conversations_replies(channel=channel, ts=thread_ts)
        user_key = a.data["messages"][0]["text"].split(">")[-1]
        BASE_MESSAGES = get_cache(user_key)
        if BASE_MESSAGES:
            messages = BASE_MESSAGES + pack_messages_to_gpt(a.data["messages"])
        else:
            rel_page_id_list = get_related_page_id_list(user_key)
            messages = detail_search_response(
                rel_page_id_list, user_key, config, user_info
            ) + pack_messages_to_gpt(a.data["messages"])
            update_cache(user_key, messages)
    else:
        print(f"(Not In Thread) Search Term : {user}")
        thread_ts = body["event"]["event_ts"]
        rel_page_id_list = get_related_page_id_list(user)
        print(f"Related_page_id: {rel_page_id_list}")
        messages = detail_search_response(rel_page_id_list, user, config, user_info)
        update_cache(user, messages)

    answer = GPT4_request_message(messages)
    print(answer)
    response = client.chat_postMessage(
        channel=channel, thread_ts=thread_ts, text=answer
    )


## Confluence Section

confluence = Confluence(
    url=CONFLUENCE_URL,
    username=CONFLUENCE_USER,
    password=CONFLUENCE_API_TOKEN,
    cloud=True,
)


## Sand Box
@app.event("app_mention")
def handle_app_mention_message_events(body, logger):
    log_event("handle_message_events")
    user = str(body["event"]["text"]).split(">")[1]
    send_slack_message(body, user)


@app.event("message")
def handle_message_events(body, logger):
    log_event("handle_message_events")
    user = str(body["event"]["text"]).split(">")[1]
    send_slack_message(body, user)


if __name__ == "__main__":
    SocketModeHandler(app, SLACK_APP_TOKEN).start()
