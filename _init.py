import os
import json
import logging.config
from datetime import datetime
from redis.client import Redis
from google.cloud import pubsub_v1, storage, exceptions
from XTBApi.exceptions import TransactionRejected
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())


class Config:
    def __init__(self, config):
        self._dict = config
        self.algorithm = str(config.get('algorithm', 'rsi'))
        self.tech = config.get(f'TA_{self.algorithm.upper()}')
        self.period = config.get('timeframe', 15)
        self.symbols = config.get('symbols')
        self.volume = config.get('volume')
        self.rate_tp = config.get('rate_tp')
        self.rate_sl = config.get('rate_sl')
        self.race_name = os.getenv("RACE_NAME")
        self.race_pass = os.getenv("RACE_PASS")
        self.race_mode = os.getenv("RACE_MODE")


class Cache:
    def __init__(self):
        self.ttl_s = 604_800
        self.client = Redis(
            host=os.getenv("REDIS_HOST"),
            port=os.getenv("REDIS_PORT"),
            decode_responses=True
        )

    def set_key(self, key, value):
        self.client.set(key, json.dumps(value), ex=self.ttl_s)

    def get_key(self, key):
        return json.loads(self.client.get(key))

    def get_keys(self, keys):
        return [json.loads(s) for s in self.client.mget(keys)]


class Notify:
    def __init__(self, title=''):
        self.ts = datetime.today().strftime('%Y-%m-%d %H:%M:%S')
        self.title = title
        self.texts = ''

    def setts(self, ts):
        self.ts = ts
        return ts

    def add(self, message):
        self.texts += f'{message}\n'
        return message

    def print_notify(self, message):
        self.add(message)
        LOGGER.info(message.strip())


class Cloud:
    def __init__(self):
        self.client = None

    def pub(self, message):
        self.client = pubsub_v1.PublisherClient()
        topic_path = self.client.topic_path(
            project=os.getenv('GOOGLE_CLOUD_PROJECT'),
            topic=os.getenv('GOOGLE_PUBSUB_TOPIC'),
        )
        future = self.client.publish(topic_path, str(message).encode(), attr='ATTR VALUE')
        future.result()

    def download_setting(self, appname: str) -> dict:
        bucket_name = "xtb-setting"
        blob_name = f"{appname}.json"
        self.client = storage.Client()
        try:
            blob = self.client.bucket(bucket_name).blob(blob_name)
            contents = blob.download_as_string()
            return json.loads(contents.decode())
        except exceptions.NotFound:
            return {}


class Breaker:
    def __init__(self):
        self.url = 'http://localhost'
        self.status = True

    def check(self):
        if not os.getenv("BREAKER_HOST"):
            return self.status
        from requests import get
        self.url = f'{os.getenv("BREAKER_HOST")}?k={os.getenv("BREAKER_TOKEN")}&onlyCheck=y'
        res = get(self.url)
        self.status = res.json().get('checked')
        return self.status


def trigger_open_trade(client, symbol, mode='buy'):
    try:
        return client.open_trade(mode, symbol, conf.volume,
                                 rate_tp=conf.rate_tp, rate_sl=conf.rate_sl)
    except TransactionRejected as e:
        return e


def trigger_close_trade(client, symbol, mode):
    client.update_trades()
    orders = {k: trans.order_id
              for k, trans in client.trade_rec.items() if trans.symbol == symbol and trans.mode == mode}
    LOGGER.debug(f'Order to be closed: {orders}')
    res = {}
    for k, order_id in orders.items():
        try:
            res[k] = client.close_trade_only(order_id)
        except TransactionRejected as e:
            res[k] = f'Exception: {e}'
    return res


def store_trade_rec(client, account):
    client.update_trades()
    if client.trade_rec:
        try:
            cur = {}
            new = {k: v._trans_dict for k, v in client.trade_rec.items()}
            cache = Cache()
            if cache.client.exists(f"trades_cur:{account}"):
                cur = cache.get_key(f"trades_cur:{account}")
            cache.set_key(f"trades_pre:{account}", cur)
            cache.set_key(f"trades_cur:{account}", new)
        except ConnectionError as e:
            LOGGER.error(e)


_logging_json = {
  "version": 1,
  "disable_existing_loggers": False,
  "formatters": {
    "default": {
      "format": "%(asctime)s - %(levelname)s - %(name)s - %(message)s",
      "datefmt": "%Y-%m-%d %H:%M:%S"
    }
  },
  "handlers": {
    "console": {
      "class": "logging.StreamHandler",
      "formatter": "default"
    },
    "rotating": {
      "class": "logging.handlers.TimedRotatingFileHandler",
      "formatter": "default",
      "filename": os.getenv("LOG_PATH", default="logs/app.log"),
      "when": "midnight",
      "backupCount": 3
    }
  },
  "loggers": {
    "": {
      "handlers": ["console"],
      "level": "CRITICAL",
      "propagate": True
    },
    "xtb": {
      "handlers": ["rotating"],
      "level": "DEBUG"
    }
  }
}

conf = Config(json.load(open('settings.json')))
logging.config.dictConfig(_logging_json)
LOGGER = logging.getLogger(f'xtb.{os.path.basename(os.getcwd())}')
