from os import link
import streamlit as st
import json
import time
import textwrap
import base64
import bbcodepy
from io import BytesIO
from PIL import Image
from mistralai import Mistral, UserMessage, SystemMessage
from pictex import Canvas, LinearGradient
from datetime import datetime, timedelta

from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.orm import declarative_base
from utils import get_header_image, get_summary, wrap_list_of_strings, add_summary_text_image, text_to_image, get_request

Base = declarative_base()

class Summary(Base):
    __tablename__ = "summaries"
    appid = Column(String, primary_key=True)
    summary_date = Column(DateTime)
    total_reviews = Column(Integer)
    json_object = Column(String)
    reviews = Column(String)
    times_consulted = Column(Integer)
    bug = Column(Boolean)

class Report(Base):
    __tablename__ = "summary_bug"
    appid = Column(String, primary_key=True)
    summary_date = Column(DateTime)
    report_date = Column(DateTime)
    json_object_bug = Column(String)
    times_consulted = Column(Integer)
    reason = Column(String)

def check_fresh_summary(result, total_reviews):
    check_summary = result.json_object is not None
    check_date = result.summary_date >= datetime.now()-timedelta(days=30)
    check_reviews = result.total_reviews >= total_reviews*0.9
    return check_date & check_reviews & check_summary

def manage_summary_by_appid(target_appid: str, total_reviews: int, progress_status):
    date_cache = None
    try:
        #st.write("Connecting to database... try 1")
        conn = st.connection("neon", type="sql")
        session = conn.session
        result = session.get(Summary, target_appid)
    except Exception as e:
        time.sleep(5)  # Wait for a while before retrying
        #st.write(f"Retrying connection to database... Error: {e}")
        conn = st.connection("neon", type="sql")
        session = conn.session
        result = session.get(Summary, target_appid)
    json_summary = None
    if result is not None:
        if check_fresh_summary(result, total_reviews) and result.bug is False and result.reviews is not None:
            json_summary = result.json_object
            reviews = json.loads(result.reviews)
            result.times_consulted += 1
            date_cache = result.summary_date
            session.commit()
        else:
            progress_status.write("### Generating summary with AI...")
            json_ai, reviews = get_summary_reviews_ai(target_appid)
            result.json_object = json_ai
            result.total_reviews = total_reviews
            result.reviews = json.dumps(reviews)
            result.times_consulted += 1
            result.summary_date = datetime.now()
            result.bug = False
            session.commit()
            json_summary = json_ai
    else:
        json_ai, reviews = get_summary_reviews_ai(target_appid)
        new_summary = Summary(appid=target_appid, summary_date=datetime.now(), total_reviews=total_reviews, json_object=json_ai, reviews=json.dumps(reviews), times_consulted=1, bug = False)
        session.add(new_summary)
        session.commit()
        json_summary = json_ai
    session.close()
    return json_summary, date_cache, reviews

def write_bug(appid, content, option_bug):
    """Write a bug report to the database."""
    try:
        conn = st.connection("neon", type="sql")
        session = conn.session
        result = session.get(Summary, str(appid))
    except Exception as e:
        time.sleep(5)  # Wait for a while before retrying
        conn = st.connection("neon", type="sql")
        session = conn.session
        result = session.get(Summary, str(appid))
    
    if result is not None:
        result.bug = True
        report = Report(appid=str(appid),
                        summary_date=result.summary_date,
                        report_date=datetime.now(),
                        json_object_bug=json.dumps(content),
                        times_consulted=result.times_consulted,
                        reason=option_bug)
        session.add(report)
        session.commit()
    else:
        st.write("No summary found for this appid.")
    session.close()

@st.cache_data
def parse_steamreviews_request(appid):
    num_per_page = 20
    max_review = 20  # max number of reviews to return
    review_count = 0
    reviews_json = {}
    url = "https://store.steampowered.com/appreviews/" + str(appid)
    print(url)
    parameters = {
        "json": 1,
        "cursor": "*",
        "num_per_page": num_per_page,
        "language": "english",
        "purchase_type": "all",
        "review_type": "all",
        "day_range": "365"
    }
    json_data = get_request(url, parameters)
    summary = json_data['query_summary']
    review_id = 1
    while review_count < max_review:
        if summary["num_reviews"] == 0:
            break
        json_data = get_request(url, parameters)
        for review in json_data["reviews"]:
            review_count += 1
            sentiment = "positive" if review["voted_up"] else "negative"
            reviews_json[str(review_id)] = {
                "review": review["review"],
                "sentiment": sentiment
            }
            review_id += 1
        parameters["cursor"] = json_data["cursor"]
        summary = json_data['query_summary']
    return reviews_json, summary
    
def trim_factors(content, steam_score):
    """Trim the factors based on the steam review score, with a score of 8 two negative factors and 8 positive factors."""
    steam_score = int(steam_score)
    content = content.copy()
    if len(content["positive_factors"]) > steam_score:
        content["positive_factors"] = content["positive_factors"][:steam_score+1]
    if len(content["negative_factors"]) > (10-steam_score):
        content["negative_factors"] = content["negative_factors"][:(10-steam_score+1)]
    content["negative_factors"] = [item["title"] for item in content["negative_factors"]]
    content["positive_factors"] = [item["title"] for item in content["positive_factors"]]    
    return content

def get_json_response(reviews):
    try:
        response = client.agents.complete(
            agent_id=st.secrets["review_agent_cot"],
            messages=reviews,
            stream=False,
            response_format={"type": "json_object"}
            )
        if response is None or not hasattr(response, 'choices') or not response.choices:
            return get_json_response(reviews)  # Retry if no response or empty choices
        return response    
    except Exception as e:
        st.write(f"Error during web search: {str(e)}")
        return 0
    
def water_mark_image(text="Steam Reviews AI", font_size=24):
    """Create a watermark image."""
    canvas = (
        Canvas()
        .font_family("app/static/Roboto-Regular.ttf")
        .font_size(font_size)
        .color("white")
        .background_color(LinearGradient(["#00000000", "#ff8b00"]))
        .padding(10)
        .alignment("right")
    )
    img = canvas.render(text).to_pillow()
    return img

def get_summary_reviews_ai(appid):
    json_reviews, summary = parse_steamreviews_request(appid)
    raw_response = get_json_response([{"content": json.dumps(json_reviews), "role": "user"}])
    
    content_raw = raw_response.choices[0].message.content
    return content_raw, json_reviews

def stack_images_vertically(img_1, img_2):
    # Resize img_1 to match img_2 width
    new_width = img_2.width
    aspect_ratio = img_1.height / img_1.width
    new_height = int(new_width * aspect_ratio)
    img_1_resized = img_1.resize((new_width, new_height), Image.Resampling.LANCZOS)

    # Create new image with enough height to hold both
    total_height = img_1_resized.height + img_2.height
    stacked_img = Image.new("RGB", (new_width, total_height), color=(255, 255, 255))

    # Paste images
    stacked_img.paste(img_1_resized, (0, 0))
    stacked_img.paste(img_2, (0, img_1_resized.height))

    return stacked_img

@st.fragment
def handle_bug_report():
    option_bug = st.text_input("Can you describe the issue?",placeholder="Write a reason or leave it empty")
    if st.button("Report Bug", type="primary"):
        write_bug(app_result, content, option_bug)
        st.rerun()

if "appid" in st.query_params:
    app_result = st.query_params["appid"]
elif "app_result" in st.session_state:
    app_result = st.session_state.app_result
    st.query_params["appid"] = str(app_result)
else:
    st.page_link("Search.py", label=":red-background[**Search a game first**]")
    st.stop()

@st.fragment
def show_related_reviews(content, reviews):
    # Build factor options as dicts: {"title": ..., "list": [...]}
    factor_options = [{"title": "All", "list": [str(i) for i in range(1, len(reviews)+1)]}]
    # Add positive factors
    for factor in content["positive_factors"]:
        factor_options.append({"title": "✅ " + factor["title"], "list": factor["list"]})
    # Add negative factors
    for factor in content["negative_factors"]:
        factor_options.append({"title": "❌ " + factor["title"], "list": factor["list"]})

    factor = st.selectbox(
        "Select a factor to read the related reviews",
        factor_options,
        format_func=lambda x: x["title"]
    )
    if not factor["list"]:
        st.info("No reviews found for this factor.")
    for item in factor["list"]:
        st.write(bbcodepy.Parser().to_html(reviews[item]["review"]), unsafe_allow_html=True)
        st.divider()
        
# Mistral model 
mistral_model = "mistral-small-latest"
client = Mistral(st.secrets["MISTRAL_API_KEY"])
# Agent IDs
review_summary_id = "review_summary_agent"
# Initialize everything
def initialize():
    check_client()
# Check if the client is initialized
def is_client_initialized():
    return client is not None and st.secrets["MISTRAL_API_KEY"] is not None
def check_client():
    if not is_client_initialized():
        st.write("Mistral client is not initialized. Please check your API key.")
        return False
    return True

initialize()

col_banner = st.empty()
col_bug = st.container()
col_back, col_about, col_kofi = st.columns(3, vertical_alignment="center")
generated_review = False
img = get_header_image(app_result)
summary = get_summary(app_result)
with col_banner.container():
    summary_image = add_summary_text_image(img, summary)
    im_file = BytesIO()
    summary_image.save(im_file, format="JPEG")
    im_bytes = im_file.getvalue()
    image_base64 = base64.b64encode(im_bytes).decode()
    link = f"https://store.steampowered.com/app/{app_result}"
    html = f"<a href='{link}'><img src='data:image/png;base64,{image_base64}'></a>"
    first_banner = st.empty()
    first_banner.markdown(html, unsafe_allow_html=True)
with col_back:
    st.page_link("Search.py", label=":red-background[**Search**]")
with col_about:
    st.page_link("pages/2-About.py", label=":red-background[**About**]")
with col_kofi:
    st.page_link("https://ko-fi.com/duerkos", label=":red-background[**Support me**]")
if summary["total_reviews"] == 0:
    st.write("No reviews found for this game.")
    st.stop()
st.markdown('''
            ##Project Launched elsewhere!
            #Please check https://steambuzz.vercel.app/ or https://duerkos.github.io/landing-page/ to check where the project lives on''')