import redis
from .user_memory import GlobalLocalThreadUserMemory
import numpy as np
from src.llm import OpenRouterEmbeddings
from src.config import OPEN_ROUTER_API_KEY, EMBED_MODEL

np.random.seed(131200)
cache_db = redis.StrictRedis(host='localhost',port=6379,
                             db=7)

embed = OpenRouterEmbeddings(OPEN_ROUTER_API_KEY, EMBED_MODEL)
thread_memory = GlobalLocalThreadUserMemory(cache_db, embed=embed,
                                            ttl=60*60*24*3,criterion_val= 60*30, context_local_window=8)