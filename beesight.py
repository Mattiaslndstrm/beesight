import configparser
import datetime
import urllib
import requests
import sys
import json
import time

#add logging module
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

#create a log file handler
handler = logging.FileHandler('beesight.log')
handler.setLevel(logging.DEBUG)
#logging format
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
#add handler to the logger
logger.addHandler(handler)

# complain on config file issues
# complain on bad login
# don't hardcode timezone to japan

CONFIG_FILE_NAME = 'config.ini'
INSIGHT_SECTION = 'insight'
BEEMINDER_SECTION = 'beeminder'

LOGIN_URL = "https://insighttimer.com/user_session"
INSIGHT_CSV_URL = "https://insighttimer.com/sessions/export"

BASE_URL = "https://www.beeminder.com/api/v1/"
GET_DATAPOINTS_URL = BASE_URL + "users/%s/goals/%s/datapoints.json?auth_token=%s"
POST_MANY_DATAPOINTS_URL = BASE_URL + "users/%s/goals/%s/datapoints/create_all.json?auth_token=%s"
POST_DATAPOINTS_URL = GET_DATAPOINTS_URL + "&timestamp=%s&value=%s&comment=%s"


def get_insight_data():
    config = configparser.RawConfigParser()
    logger.debug("Reading config file %s", CONFIG_FILE_NAME)
    config.read(CONFIG_FILE_NAME)

    username = config.get(INSIGHT_SECTION, "username")
    password = config.get(INSIGHT_SECTION, "password")

    values = {
        'user_session[email]': username,
        'user_session[password]': password
    }
    login_data = urllib.parse.urlencode(values)

    # Start a session so we can have persistent cookies
    session = requests.session()
    logger.debug("Submitting POST request to insighttimer.com...")
    r = session.post(LOGIN_URL, data=login_data)
    logger.debug("Submitting GET request to insighttimer.com...")
    r = session.get(INSIGHT_CSV_URL)
    return r.text.split('\n')


def post_beeminder_entry(entry):
    config = configparser.RawConfigParser()
    config.read(CONFIG_FILE_NAME)

    username = config.get(BEEMINDER_SECTION, "username")
    auth_token = config.get(BEEMINDER_SECTION, "auth_token")
    goal_name = config.get(BEEMINDER_SECTION, "goal_name")

    session = requests.session()
    full_url = POST_DATAPOINTS_URL % (username, goal_name, auth_token,
                                      entry["timestamp"], entry["value"],
                                      entry["comment"])
    logger.debug(
        "Ready to post new datapoints string to beeminder.com. Encoded URL follows:"
    )
    logger.debug(full_url)
    r = session.post(full_url)

    logger.info("Posted entry: %s", r.text)


def get_beeminder_comment():
    config = configparser.RawConfigParser()
    config.read(CONFIG_FILE_NAME)

    username = config.get(BEEMINDER_SECTION, "username")
    auth_token = config.get(BEEMINDER_SECTION, "auth_token")
    goal_name = config.get(BEEMINDER_SECTION, "goal_name")

    response = requests.get(GET_DATAPOINTS_URL % (username, goal_name,
                                                  auth_token))
    # the_page = response.read()
    return response.json()[0]['comment']


def beeminder_to_one_per_day(beeminder_output):
    bm = json.loads(beeminder_output)

    s = {}

    # skip first two header lines
    for entry in bm:
        ts = entry['timestamp']
        dt = datetime.datetime.fromtimestamp(ts)

        # need to move back one dayfrom the beeminder time, because it
        # pushes the day forward to 01:00 on day + 1, at least in JST
        d = dt.date() - datetime.timedelta(days=1)

        if not d in s:
            s[d] = 1

    return s.keys()


def get_time_zone():
    config = configparser.RawConfigParser()
    logger.debug("Reading config file %s", CONFIG_FILE_NAME)
    config.read(CONFIG_FILE_NAME)
    return config.get(INSIGHT_SECTION, "utc_timezone")


# def csv_to_entries_since_last_entry(csv_lines, last_comment):
#     timezone_offset = get_time_zone()
#     entries = []

#     logger.info("Parsing all sessions since last session from CSV:")
#     try:
#         session = {}

def mediation_date(datetime_part, timezone_offset):
    date_part, time_part = datetime_part.split(" ")
    date_parts = date_part.split("/")
    time_parts = time_part.split(":")
    # print(date_parts)
    # print(time_parts)
    m, d, y = map(int, date_parts)
    h, m, s = map(int, time_parts)
    # Changes the time to of the meditation time in UTC to users's time zone.
    dt = (datetime.datetime(y, m, d, h, m, s)
          + datetime.timedelta(hours=timezone_offset))
    return dt


def csv_to_todays_entries(csv_lines, last_comment):
    minutes = int(0)
    entries = []
    # skip first two header lines
    timezone_offset = get_time_zone()
    logger.info("Parsing today's sessions from CSV:")
    # try to read the last four entries
    try:
        for l in csv_lines[2:]:
            session = {}
            line = l.split(",")
            datetime_part = line[0]
            minutes_entry = line[1]
            if datetime_part == last_comment:
                break
            session['comment'] = datetime_part
            session['value'] = minutes_entry
            # needs to be the day of meditaiton
            # session['timestamp'] = datetime.datetime.today().timestamp()
            logger.info("%s : %s minutes", datetime_part, minutes_entry)
            dt = mediation_date(datetime_part, timezone_offset)
            if dt == datetime.date.today():
                entries.append(session)
            else:
                break
    except IndexError:
        logger.info(
            "Insight session data too short: expected at least 4 entries, retrieved %s minutes from available data",
            minutes)
    else:
        logger.info("File parsed successfully, %s minutes retrieved.", minutes)
    return entries


if __name__ == "__main__":
    # get today's minutes from insight
    last_entry_comment = get_beeminder_comment()
    if last_entry_comment[:24] == 'initial datapoint of 0.0':
        insight_entries = csv_to_todays_entries(get_insight_data(),
                                                last_entry_comment)
    else:
        insight_entries = csv_to_entries_since_last_entry(get_insight_data(),
                                                          last_entry_comment)
    # if insight_minutes == 0:
    #     logger.info("No minutes logged for today's date on InsightTimer.com")
    #     sys.exit()
    # else:
    #     logger.info("%s minutes meditated today according to InsightTimer.com",
    #                 insight_minutes)

    # get dates of days meditated, from beeminder
    #beeminder_dates = beeminder_to_one_per_day(get_beeminder_comment())
    #print "%s datapoints in beeminder" % len(beeminder_dates)

    # get today's date
    new_date = datetime.date.today()
    logger.debug("new_date: %s", new_date)

    # create beeminder-friendly datapoints
    timestamp = datetime.datetime.today().timestamp()
    # new_datapoint = {
    #     'timestamp': timestamp,
    #     'value': insight_minutes,
    #     'comment': date_comment
    # }
    logger.debug("new_datapoint: %s", insight_entries)

    for datapoint in insight_entries:
        post_beeminder_entry(datapoint)
    logger.info("Script complete, exiting.")
    print(get_beeminder_comment())
