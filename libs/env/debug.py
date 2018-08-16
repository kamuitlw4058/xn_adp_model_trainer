from conf import conf

import logging
logger = logging.getLogger(__name__)

def pycharm_skip(fn):
    def wrapper(*args,**kwargs):
        if not conf.PYCHARM:
            logger.info(fn.__name__ +"  is skip")
            fn(*args,**kwargs)

    return wrapper

