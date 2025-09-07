#main file
from os import link
import streamlit as st
import json
import time
import requests
import pandas as pd
import numpy as np
import textwrap
import re
import base64
from io import BytesIO
from PIL import Image
from mistralai import Mistral, UserMessage, SystemMessage
from requests.exceptions import SSLError
from pictex import Canvas, LinearGradient
from datetime import datetime, timedelta
from thefuzz import fuzz

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base

from utils import add_summary_text_image, get_request, get_header_image, get_summary
        
@st.cache_data
def get_steam_df():
    """Return a list of all steam games.
    
    Returns
    -------
    
        list of all steam games
    """
    return pd.DataFrame(get_request("https://api.steampowered.com/ISteamApps/GetAppList/v2/?")["applist"]["apps"])

def checks_review_availability(row):
    row["total_reviews"] = get_reviews(row["appid"])
    if row["total_reviews"] > 1000:
        row["fuzzy_score"] += 5 # Boost score for popular games
    elif row["total_reviews"] >= 50:
        row["fuzzy_score"] += 2 # Boost score for games with enough reviews
    return row["total_reviews"] > 0


@st.cache_data
def get_steam_df_search(search_input):
    """Return a DataFrame of steam games matching the search input.
    """
    df = get_steam_df().copy()
    df["fuzzy_score"] = df["name"].apply(lambda x: fuzzy_phrase_match(x, search_input))
    df["len_name"] = df["name"].apply(lambda x: -len(x))
    df = df[df["fuzzy_score"] > 90]  # Filter out low fuzzy scores
    df = df.sort_values(by=["fuzzy_score","len_name"], ascending=False)
    valid_rows = []
    counter = 0
    for idx, row in df.iterrows():
        if checks_review_availability(row):
            valid_rows.append(row)
            counter += 1
        if counter == 30:
            break
    if counter > 0:
        df = pd.DataFrame(valid_rows)
        df = df.sort_values(by=["fuzzy_score","total_reviews"], ascending=False)
        return df
    else:
        return None

def fuzzy_phrase_match(text, target):
    def get_fuzzy_score(text_words, target_words):
        scores = []
        start_word= 0
        for tw in target_words:
            # Calculate the fuzzy score for each word in the target against all words in the text in order
            word_scores = [(fuzz.ratio(tw, word)) for word in text_words[start_word:]]
            best_score = max(word_scores) if word_scores else 0
            if best_score > 0:
                start_word += word_scores.index(best_score) + 1
            scores.append(best_score)
        avg_score = sum(scores) / len(scores)
        return avg_score
    #re.sub('[^\w\s]', '', x).lower(), re.sub('[^\w\s]', '', search_input).lower(), threshold=90)
    target_words = target.lower().split()
    text_words = text.lower().split()
    score_0 = get_fuzzy_score(text_words, target_words)
    score_1 = 0
    if bool(re.search(r'[^a-zA-Z0-9]', text)):
        # If there is punctuation, we will try to match without it
        target_words = re.sub('[^\w\s]', '', target).lower().split()
        text_words = re.sub('[^\w\s]', '', text).lower().split()
        score_1 = get_fuzzy_score(text_words, target_words) - 2
    return max(score_0, score_1)

def get_reviews(appid):
    """Return if there are reviews for a given appid."""
    return get_summary(appid)['total_reviews']

def handle_selection():
    st.session_state.selection_made = True

if 'selection_made' not in st.session_state:
    st.session_state.selection_made = False

def format_string_search(df, appid):
    """Format the string for the selectbox."""
    low_reviews = "❔"
    enough_reviews = "✅"
    popular_game = "🔥"
    if df[df["appid"] == appid]["total_reviews"].values[0] < 50:
        review_emoji = low_reviews
    elif df[df["appid"] == appid]["total_reviews"].values[0] < 1000:
        review_emoji = enough_reviews
    else:
        review_emoji = popular_game
    return review_emoji+" "+df[df["appid"] == appid]["name"].values[0]

cols = st.columns(2)
with cols[0]:
    st.page_link("pages/2-About.py", label=":red-background[**About the app**]")
with cols[1]:
    st.page_link("https://ko-fi.com/duerkos", label=":red-background[**Support me**]")

st.markdown('''
            ##Project Launched elsewhere!
            #Please check https://steambuzz.vercel.app/ or https://duerkos.github.io/landing-page/ to check where the project lives on''')