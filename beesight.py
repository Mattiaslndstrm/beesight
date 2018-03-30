import configparser
from datetime import datetime, timedelta, date
import urllib
import requests
import json

# add logging module
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# create a log file handler
handler = logging.FileHandler('beesight.log')
handler.setLevel(logging.DEBUG)
# logging format
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
# add handler to the logger
logger.addHandler(handler)

# complain on config file issues
# complain on bad login
# don't hardcode timezone to japan

CONFIG_FILE_NAME = 'config.ini'
INSIGHT_SECTION = 'insight'
BEEMINDER_SECTION = 'beeminder'

LOGIN_URL = "https://insighttimer.com/user_session"
INSIGHT_CSV_URL = "https://insighttimer.com/sessions/export"
INSIGHT_JSON_URL = 'https://insighttimer.com/sessions/all?p1=1&l1=999999'

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
    r = session.get(INSIGHT_JSON_URL)
    return r.json()['sessions']


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
        "Ready to post new datapoints to beeminder.com. Encoded URL follows:"
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
    sorted_datapoints = sorted(response.json(), key=lambda d: d['timestamp'],
                               reverse=True)
    return {'timestamp': sorted_datapoints[0]['timestamp'],
            'comment': sorted_datapoints[0]['comment']}


def get_time_zone():
    config = configparser.RawConfigParser()
    logger.debug("Reading config file %s", CONFIG_FILE_NAME)
    config.read(CONFIG_FILE_NAME)
    return config.get(INSIGHT_SECTION, "utc_timezone")


def mediation_time(datetime_part, timezone_offset):
    return (datetime.strptime(datetime_part, '%b %d %Y %I:%M %p')
            + timedelta(hours=float(timezone_offset)))


def minutes_to_float(minutes):
    if minutes is not '-':
        m, s = minutes.split(':')
        return round(float(m) + (float(s) / 60), 4)
    return None


def filter_new_goal(entries):
    return [e for e in entries if
            datetime.fromtimestamp(int(e['timestamp'])).date() == date.today()]
    # return list(
    #             filter(
    #                 lambda x: datetime.fromtimestamp(int(x['timestamp'])).date()
    #                 == date.today(), entries))


def filter_update_goal(entries, bee_info):
    return [e for e in entries if e['timestamp'] > bee_info['timestamp']]
    # return list(
    #             filter(lambda x: x['timestamp'] > bee_info['timestamp'],
    #                    entries))


def json_to_entries(insight_json, bee_info):
    timezone_offset = get_time_zone()
    logger.info("Parsing today's sessions from CSV:")

    try:
        entries = [{
            'comment': (f'Added with beesight {date.today()}. Meditation made '
                        f'{mediation_time(l["time"], timezone_offset)}.'),
            'value': minutes_to_float(l['duration']),
            'timestamp': mediation_time(l['time'], timezone_offset).timestamp()
            } for l in insight_json]

    except IndexError:
        logger.info('Insight data too short')

    else:
        if bee_info['comment'][:24] == 'initial datapoint of 0.0':
            return filter_new_goal(entries)
        else:
            return filter_update_goal(entries, bee_info)


if __name__ == "__main__":
    # get today's minutes from insight
    insight_entries = json_to_entries(get_insight_data(),
                                      get_beeminder_info())
    # if insight_minutes == 0:
    #     logger.info("No minutes logged for today's date on InsightTimer.com")
    #     sys.exit()
    # else:
    #     logger.info("%s minutes meditated today according to InsightTimer.com",
    #                 insight_minutes)

    # get today's date
    # new_date = datetime.date.today()
    # logger.debug("new_date: %s", new_date)

    # logger.debug("new_datapoint: %s", insight_entries)

    for datapoint in insight_entries:
        post_beeminder_entry(datapoint)
    logger.info("Script complete, exiting.")
    print(get_beeminder_info())
    print(insight_entries)
