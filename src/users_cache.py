import redis
from .user_memory import GlobalLocalThreadUserMemory
import numpy as np

np.random.seed(131200)
cache_db = redis.StrictRedis(host='localhost',port=6379,
                             db=7)

thread_memory = GlobalLocalThreadUserMemory(cache_db, criterion_val= 60*60*24 / 10)