from dataclasses import dataclass, field
from itertools import count
from typing import Union, List
from classes import Profile
from bt_fx import FXMODE
from pandas import DataFrame, to_datetime


@dataclass
class Trade:
    order_id: int = field(default_factory=count(start=1).__next__, init=False)
    open_ctm: int
    symbol: str
    mode: int
    volume: Union[float, int]
    open_price: Union[float, int]
    close_ctm: Union[int, None] = None
    close_price: Union[float, int, None] = None
    profit: Union[float, int] = 0.0
    closed: bool = False


@dataclass
class Orders:
    symbol: str
    digits: int
    volume: Union[float, int]
    records: List[Trade] = field(default_factory=list)
    df: DataFrame = DataFrame()
    performance: dict = field(default_factory=dict)

    def open_trade(self, mode: int, open_ctm: int, open_price: Union[float, int]) -> Trade:
        return Trade(open_ctm, self.symbol, mode, self.volume, open_price)

    def close_trade(self, mode: int, close_ctm: int, close_price: Union[float, int]):
        orders = [tx for tx in self.records if tx.mode == mode and not tx.closed]
        for tx in orders:
            tx.closed = True
            tx.close_ctm = close_ctm
            tx.close_price = close_price
            tx.profit = (close_price - tx.open_price) * (10**self.digits) * tx.volume * mode
        return len(orders)

    def eval_performance(self):
        df = DataFrame([tx.__dict__ for tx in self.records])
        df['cmd'] = df['mode'].apply(lambda mode: FXMODE(mode).name)
        df['cum_profit'] = df['profit'].cumsum()
        # performance
        timespan_day = (df.iloc[-1]['open_ctm'] - df.iloc[0]['open_ctm']) / (1000 * 86400)
        self.performance = {
            "win_rate": sum(df['profit'] > 0) / df.shape[0],
            "n_win_pos": sum(df['profit'] > 0),
            "n_loss_pos": sum(df['profit'] < 0),
            "total_position": df.shape[0],
            "total_pnl": df['profit'].sum(),
            "total_profit": df[df['profit'] > 0]['profit'].sum(),
            "total_loss": df[df['profit'] < 0]['profit'].sum(),
            "max_dd": df['cum_profit'].min(),
            "max_runup": df['cum_profit'].max(),
            "timespan_day": timespan_day,
            "avg_open_per_day": df.shape[0] / timespan_day,
        }
        df['open_utc'] = to_datetime(df['open_ctm'] / 1000, unit='s', utc=True)
        df['close_utc'] = to_datetime(df['close_ctm'] / 1000, unit='s', utc=True)
        df['open_time'] = df['open_utc'].dt.tz_convert('Asia/Bangkok')
        df['close_time'] = df['close_utc'].dt.tz_convert('Asia/Bangkok')
        orders_cols = [
            "order_id", "mode", "cmd", "volume", "open_price", "close_price", "profit", "cum_profit",
            "open_ctm", "close_ctm", "open_utc", "close_utc", "open_time", "close_time",
        ]
        self.df = df[orders_cols]


@dataclass
class Portfolio:
    profile: Profile
    order_group: List[Orders] = field(default_factory=list)
