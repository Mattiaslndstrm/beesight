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


def get_beeminder_info():
    config = configparser.RawConfigParser()
    config.read(CONFIG_FILE_NAME)

    username = config.get(BEEMINDER_SECTION, "username")
    auth_token = config.get(BEEMINDER_SECTION, "auth_token")
    goal_name = config.get(BEEMINDER_SECTION, "goal_name")

    response = requests.get(GET_DATAPOINTS_URL % (username, goal_name,
                                                  auth_token))
    order = sorted(response.json(), key=lambda d: d['timestamp'], reverse=True)
    return {'timestamp': order[0]['timestamp'],
            'comment': order[0]['comment']}


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

def get_mediation_time(datetime_part, timezone_offset):
    date_part, time_part = datetime_part.split(" ")
    date_parts = date_part.split("/")
    time_parts = time_part.split(":")
    # print(date_parts)
    # print(time_parts)
    m, d, y = map(int, date_parts)
    h, mi, s = map(int, time_parts)
    # Changes the time to of the meditation time in UTC to users's time zone.
    dt = (datetime.datetime(y, m, d, h, mi, s)
          + datetime.timedelta(hours=float(timezone_offset)))
    return dt


def csv_to_entries(csv_lines, bee_info):
    timezone_offset = get_time_zone()
    today = datetime.date.today()
    logger.info("Parsing today's sessions from CSV:")
    try:
        entries = [{
            'comment':
            f'Added with beesight {today}',
            'value':
            l.split(',')[1],
            'timestamp':
            get_mediation_time(l.split(',')[0], timezone_offset).timestamp()
        } for l in csv_lines[2:-1]]
    except IndexError:
        logger.info('Insight data too short')
    else:
        if bee_info['comment'][:24] == 'initial datapoint of 0.0':
            return list(
                filter(
                    lambda x: datetime.datetime.fromtimestamp(int(x['timestamp'])).date() == today,
                    entries))
        else:
            return list(
                filter(lambda x: x['timestamp'] > bee_info['timestamp'],
                       entries))
    # skip first two header lines
    # try to read the last four entries
    # try:
    #     for l in csv_lines[2:]:
    #         session = {}
    #         line = l.split(",")
    #         datetime_part = line[0]
    #         minutes_entry = line[1]
    #         if datetime_part == last_comment:
    #             break
    #         # needs to be the day of meditaiton
    #         # session['timestamp'] = datetime.datetime.today().timestamp()
    #         logger.info("%s : %s minutes", datetime_part, minutes_entry)
    #         dt = get_mediation_time(datetime_part, timezone_offset)
    #         session['comment'] = datetime_part
    #         session['value'] = minutes_entry
    #         session['timestamp'] = dt.timestamp()
    #         if last_comment[:24] == 'initial datapoint of 0.0':
    #             if dt.date() == datetime.date.today():
    #                 if entries:
    #                     print('GRISGRISGRISGRISGRIS')
    #                     if session['comment'] == entries[-1]['comment']:
    #                         return entries
    #                 entries.insert(0, session)
    #             else:
    #                 return entries
    #         entries.insert(0, session)
    # except IndexError:
    #     logger.info(('Insight session data too short: expected at least 4 '
    #                  'entries, retrieved %s minutes from available data'),
    #                 minutes)
    # else:
    #     logger.info("File parsed successfully, %s minutes retrieved.", minutes)
    # return entries


if __name__ == "__main__":
    # get today's minutes from insight
    insight_entries = csv_to_entries(get_insight_data(),
                                     get_beeminder_info())
    # print(insight_entries)

    # if insight_minutes == 0:
    #     logger.info("No minutes logged for today's date on InsightTimer.com")
    #     sys.exit()
    # else:
    #     logger.info("%s minutes meditated today according to InsightTimer.com",
    #                 insight_minutes)

    # get dates of days meditated, from beeminder
    #beeminder_dates = beeminder_to_one_per_day(get_beeminder_info())
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
    # logger.debug("new_datapoint: %s", insight_entries)

    for datapoint in insight_entries:
        post_beeminder_entry(datapoint)
    logger.info("Script complete, exiting.")
    print(get_beeminder_info())
    print(insight_entries)
