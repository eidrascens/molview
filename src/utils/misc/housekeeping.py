from os import mkdir, remove
from os.path import exists, isdir, isfile
from pathlib import Path
from shutil import rmtree

from src.utils.log.custom_logger import Logger


def remove_file(log_: Logger, FILE_PATH: Path) -> bool:
    try:
        if isfile(FILE_PATH):
            remove(FILE_PATH)
        elif isdir(FILE_PATH):
            rmtree(FILE_PATH)
        else:
            raise OSError
    except FileNotFoundError as _:
        log_.info("%s does not exist." % ( FILE_PATH ))
    except (
        OSError,
        PermissionError,
        SystemError
    ) as err_:
        log_.err(
            "Cannot remove %s" % ( FILE_PATH ), err_
        )
    else:
        return True

    return False


def check_dir(log_: Logger, PATH_ARR: list[Path]) -> list[Path]:
    """_summary_

    Args:
        PATH_ARR (list[Path]): String list of DIR to check.
        log_ (Logger): Logger() instance.

    Returns:
        list[Path] | None: String list of missing dir.
    """

    MISSING_PATHS: list[Path] = []
    for dir_ in PATH_ARR:
        if isdir(dir_):
            log_.info(
                "Skipping: %s, path exists ..." % ( dir_ )
            )
            continue
        log_.info(
            "%s is missing, include to the list ..." % ( dir_ )
        )
        MISSING_PATHS.append(Path(dir_))

    return MISSING_PATHS


def fix_dir(log_: Logger, PATH_ARR: list[Path]) -> None:
    """Create the missing directories returned by check_dir().

    Args:
        PATH_ARR (list[str]): String list of DIR to create.
        log_ (Logger): Logger() instance.
    """

    MISSING_PATHS: list[Path] = check_dir(log_, PATH_ARR)
    if not MISSING_PATHS:
        return None

    created_dir_: list[Path] = []
    for dir_ in MISSING_PATHS:
        try:
            log_.info(
                "Trying to create dir: %s" % ( dir_ )
            )
            mkdir(dir_)
        except OSError as err_:
            log_.crit(
                "Cannot create DIR: %s" % ( dir_ ), err_
            )
        else:
            created_dir_.append(Path(dir_))

    failed_dir_: list[Path] = list(
            set(MISSING_PATHS) ^ set(created_dir_)
        )
    if failed_dir_:
        log_.info(
            "Unable to create the ff. DIR: %s." % (
                failed_dir_
            )
        )
