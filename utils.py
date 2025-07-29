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
from requests.exceptions import SSLError
from pictex import Canvas, LinearGradient
from datetime import datetime, timedelta
from thefuzz import fuzz

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base

def text_to_image(text, alignment="left", line_height=1.1):
    canvas = (
    Canvas()
    .font_family("app/static/Roboto-Regular.ttf")
    .font_size(24)
    .color("white")
    .background_color("black")
    .padding(20)
    .alignment(alignment)
    .line_height(line_height)
    )
    img = canvas.render(text).to_pillow()

    return img

def add_summary_text_image(header, summary, score=None):
    img = header.copy()
    # Create a text image with the summary
    text = create_summary_text(summary, score)
    img_text = create_text_image(text)

    # Resize the header image to match the height of the text image
    img = resize_image(img, img_text.height)

    # Combine the images
    new_img = combine_images(img, img_text)
    return new_img


def create_summary_text(summary, score):
    """Create the summary text."""
    text = (
        f"App ID: {summary['appid']}\n"
        f"Total Reviews: {summary['total_reviews']}\n"
        f"Positive Reviews: {summary['total_positive']}\n"
        f"Negative Reviews: {summary['total_negative']}\n"
        f"Positive Percentage: {summary['total_positive'] / summary['total_reviews']:.2%}\n"
        f"Review Score Desc: {summary['review_score_desc']}\n"
    )
    if score:
        text += f"AI Score: {score!s}\n"
    return text


def create_text_image(text):
    """Create an image from the text."""
    canvas = (
        Canvas()
        .font_family("Roboto-Regular.ttf")
        .font_size(40)
        .color("white")
        .background_color("black")
        .padding(20)
        .line_height(1.5)
    )
    return canvas.render(text).to_pillow()


def resize_image(img, target_height):
    """Resize the image to match the target height."""
    width, height = img.size
    return img.resize(
        (int(width * target_height / height), target_height),
        Image.Resampling.LANCZOS,
    )


def combine_images(img1, img2):
    """Combine two images side by side."""
    total_width = img1.width + img2.width
    new_img = Image.new("RGB", (total_width, img2.height), color=(255, 255, 255))
    new_img.paste(img1, (0, 0))
    new_img.paste(img2, (img1.width, 0))
    return new_img

def get_request(url,parameters=None):
    """Return json-formatted response of a get request using optional parameters.
    
    Parameters
    ----------
    url : string
    parameters : {'parameter': 'value'}
        parameters to pass as part of get request
    
    Returns
    -------
    json_data
        json-formatted response (dict-like)
    """
    try:
        response = requests.get(url=url, params=parameters)
    except SSLError as s:
        print('SSL Error:', s)
        
        for i in range(5, 0, -1):
            print('\rWaiting... ({})'.format(i), end='')
            time.sleep(1)
        print('\rRetrying.' + ' '*10)
        
        # recursively try again
        return get_request(url, parameters)
    
    if response:
        return response.json()
    else:
        # We do not know how many pages steamspy has... and it seems to work well, so we will use no response to stop.
        # response is none usually means too many requests. Wait and try again 
        print('No response, waiting 10 seconds...')
        time.sleep(10)
        print('Retrying.')
        return get_request(url, parameters)
    
def wrap_list_of_strings(strings, width=40, emoji=None):
    """Wrap a list of strings to a specified width."""
    wrapped_strings = []
    for string in strings:
        wrapped_string = textwrap.fill(string, width=width)
        if emoji:
            wrapped_string = f"{emoji} {wrapped_string}"
        wrapped_strings.append(wrapped_string)
    return "\n".join(wrapped_strings)

def get_header_image(appid):
    """Return the header image for a given appid."""
    try:
        response = requests.get(f"http://store.steampowered.com/api/appdetails/?appids={appid}&filters=basic")
        data = response.json()
        if data and str(appid) in data:
            img_url = data[str(appid)]["data"]["header_image"]
            img = Image.open(BytesIO(requests.get(img_url).content))
            return img
    except Exception as e:
        return None
    
def get_capsule_url(appid):
    """Return the capsule image for a given appid."""
    try:
        response = requests.get(f"http://store.steampowered.com/api/appdetails/?appids={appid}&filters=basic")
        data = response.json()
        if data and str(appid) in data:
            img_url = data[str(appid)]["data"]["capsule_image"]
            return img_url
    except Exception as e:
        return None
    
def get_summary(appid):
    """Return summary of reviews for a given appid."""
    url = "https://store.steampowered.com/appreviews/" + str(appid)
    parameters = {"json": 1, "purchase_type": "all", "review_type": "all"}
    json_data = get_request(url, parameters)
    json_data['query_summary']['appid'] = appid  # Add appid to the summary
    return json_data['query_summary']