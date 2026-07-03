class RateLimited(Exception):
    """LCU/SGP returned 429. args = (retry_after_seconds,)."""


class SummonerNotFound(Exception):
    pass


class SummonerGamesNotFound(Exception):
    pass


class SummonerRankInfoNotFound(Exception):
    pass


class SummonerNotInGame(Exception):
    pass


class RetryMaximumAttempts(Exception):
    pass
