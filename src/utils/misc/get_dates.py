from datetime import datetime, timezone, timedelta
from typing import Optional


def cdate(no_spaces: Optional[bool] = False) -> str:
    """Complete (c) version of date (DD dd/mm/yyyy HH:MM:SS tz TZ)

    Here:
        DD - day
        dd - date
        mm - month
        yy - year
        HH - hour
        MM - minute
        SS - second
        tz - timezone offset
        TZ - timezone
    """

    dt: str = datetime.now(
            tz=datetime.now(
                timezone(timedelta(0))
            ).astimezone().tzinfo
        ).strftime(
            "%A %d/%B/%Y %H:%M:%S %z %Z"
        )
    return dt if not no_spaces else (
            dt
                .replace("/", ".")
                .replace(":", "-")
                .replace(" ", "_")
        )


def mdate(no_spaces: Optional[bool] = False) -> str:
    """Medium-length (m) version of date (dd/mm/yyyy HH:MM:SS TZ)

        Here:
        DD - day
        dd - date
        mm - month
        yy - year
        HH - hour
        MM - minute
        SS - second
        tz - timezone offset
        TZ - timezone
    """

    dt = datetime.now(
            tz=datetime.now(
                timezone(timedelta(0))
            ).astimezone().tzinfo
        ).strftime("%d/%b/%Y %H:%M:%S %Z")
    return dt if not no_spaces else (
            dt
                .replace("/", ".")
                .replace(":", "-")
                .replace(" ", "_")
        )


def sdate(no_spaces: Optional[bool] = False) -> str:
    """Short (s) version of date (dd/mm/yyyy HH:MM:SS)

        Here:
        DD - day
        dd - date
        mm - month
        yy - year
        HH - hour
        MM - minute
        SS - second
        tz - timezone offset
        TZ - timezone
    """

    dt: str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    return dt if not no_spaces else (
            dt
                .replace("/", ".")
                .replace(":", "-")
                .replace(" ", "_")
        )


def vsdate(no_spaces: Optional[bool] = False) -> str:
    """Very short (vs) version of date (dd/mm/yy HH:MM)

        Here:
        DD - day
        dd - date
        mm - month
        yy - year
        HH - hour
        MM - minute
        SS - second
        tz - timezone offset
        TZ - timezone
    """

    dt: str = datetime.now().strftime("%d/%m/%y %H:%M")
    return dt if not no_spaces else (
            dt
                .replace("/", ".")
                .replace(":", "-")
                .replace(" ", "_")
        )
