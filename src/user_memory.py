import numpy as np
import json
from datetime import datetime
import redis
import uuid
import redis
from .beautylogger import logger
from typing import TypedDict, List, Optional, Union

class GlobalLocalThreadUserMemory():
    def __init__(self, redis_client: Union[redis.StrictRedis, redis.Redis], 
                 ttl: Union[int, float] = 60 * 60 * 24 * 30,
                 context_local_window: int = 5, 
                 criterion_val: Union[int, float] = 600,):
        
        self.context_local_window = context_local_window 
        self.criterion_val = criterion_val
        self.redis = redis_client
        self.ttl = ttl


    def _get_user_key(self, user_id: str) -> str:
        return f"gum:user:{user_id}:meta"

    def _get_thread_history_key(self, thread_id: str) -> str:
        return f"gum:thread:{thread_id}:history"
    
    def _get_thread_wonder_key(self, thread_id: str) -> str:
        return f"gum:thread:{thread_id}:wonder"
    
    def _get_thread_remember_key(self, thread_id: str) -> str:
        return f"gum:thread:{thread_id}:remember"
    
    def _get_user_thread_summary_key(self, user_id:str, thread_id: str) -> str:
        return f"gum:user_id:{user_id}:thread:{thread_id}:history"
    
    def _get_user_global_summaries_key(self, user_id: str) -> str:
        """Список всех саммари пользователя со всех тредов"""
        return f"gum:user_id:{user_id}:all_summaries"


    def get_local_history(self, thread_id: str, limit: int = 5) -> list[str]:
        msgs = self.redis.lrange(self._get_thread_history_key(thread_id), -limit if limit != 0 else 0, -1)
        if msgs:
            return [m.decode('utf-8') for m in msgs]
        else:
            return []
    
    def get_thread_history(self, thread_id: str) -> list[str]:
        return self.get_local_history(thread_id, 0)
    


    def get_all_user_summaries(self, user_id: str) -> list[dict]:
        """
        Возвращает список всех саммари и тем со всех потоков пользователя.
        """
        key = self._get_user_global_summaries_key(user_id)
        msgs = self.redis.lrange(key, 0, -1)
        
        result = []
        if msgs:
            for m in msgs:
                try:
                    result.append(json.loads(m.decode('utf-8')))
                except json.JSONDecodeError:
                    continue
        return result
    
    def get_wonder_thread_moments(self, thread_id: str):
        
        key = self._get_thread_wonder_key(thread_id)
        msgs = self.redis.lrange(key, 0, -1)
        result = []
        if msgs:
            for m in msgs:
                try:
                    result.append(json.loads(m.decode('utf-8')))
                except json.JSONDecodeError:
                    continue
        return result


    def add_message_to_history(self, thread_id: str, role: str, content: str):
        msg = json.dumps({"role": role, "content": content},ensure_ascii=False)
        self.redis.rpush(self._get_thread_history_key(thread_id), msg)
        self.redis.expire(self._get_thread_history_key(thread_id), self.ttl)

    def add_wonder_to_history(self, thread_id: str, user_message: str, reason: str):
        msg = json.dumps({"role": 'wonder_moment', "content": f'Сообщение пользователя: {user_message}'\
                                                              f'Почему момент удивительный: {reason}'},
                         ensure_ascii=False) 
        
        self.redis.rpush(self._get_thread_wonder_key(thread_id), msg)
        self.redis.expire(self._get_thread_wonder_key(thread_id), self.ttl)
    
    # def add_remember_to_history(self, thread_id: str, user_message: str):
    #     msg = json.dumps({"role": 'remember_moment', "content": f'Сообщение пользователя: {user_message}'}, ensure_ascii=False) 
    #     self.redis.rpush(self._get_thread_remember_key(thread_id), msg)
    #     self.redis.expire(self._get_thread_remember_key(thread_id), self.ttl)
    
    def add_user_thread_summary(self, summary: str, theme: str, user_id: str, thread_id: str):
        """
        Сохраняет саммари в двух местах:
        1. В контексте конкретного треда (для истории треда).
        2. В глобальном списке пользователя (чтобы можно было достать все темы сразу).
        """
        msg_thread = json.dumps({"summary": summary, 'theme': theme}, ensure_ascii=False)
        thread_key = self._get_user_thread_summary_key(user_id, thread_id)
        self.redis.rpush(thread_key, msg_thread)
        self.redis.expire(thread_key, self.ttl)

        # первая нужна, чтоб получать саммари для текущего пользователя по имени потока

        msg_global = json.dumps({
            "summary": summary, 
            "theme": theme, 
            "thread_id": thread_id,
            "created_at": datetime.now().isoformat()
        }, ensure_ascii=False)
        global_key = self._get_user_global_summaries_key(user_id)
        self.redis.rpush(global_key, msg_global)

        self.redis.expire(global_key, self.ttl)
        
    def check_and_init_thread(self, user_id: str, message_datetime: datetime) -> dict:
        """
        Главная логика: проверяет критерии и возвращает ID потока + флаг need_summary.
        """
        key = self._get_user_key(user_id)
        raw_data = self.redis.get(key)
        
        if not raw_data:
            logger.info(f'[NEW THREAD FOR NEW USER]')
            new_thread_id = str(uuid.uuid4())
            meta = {
                "current_thread_id": new_thread_id,
                "last_msg_time": message_datetime.isoformat(),
                "total_pause_sum": 0,
                "msg_count": 0
            }

            self.redis.set(key, json.dumps(meta, ensure_ascii=False))
            return {
                "thread_id": new_thread_id,
                "previous_thread_id": None,
                "make_history_summary": False
            }


        meta = json.loads(raw_data)
        
        last_time = datetime.fromisoformat(meta["last_msg_time"])
        delta = (message_datetime - last_time).total_seconds()
        
        if meta["msg_count"] > 0:
            meta["total_pause_sum"] += delta
        
        meta["msg_count"] += 1

        meta["last_msg_time"] = message_datetime.isoformat()
        
        avg_pause = meta["total_pause_sum"] / meta["msg_count"] if meta["msg_count"] > 0 else 0
        is_avg_high = avg_pause > self.criterion_val

        if is_avg_high:
            logger.info(f'[MAKE NEW THREAD]')
            new_thread_id = str(uuid.uuid4())
            old_thread_id = meta["current_thread_id"]
            
            meta["current_thread_id"] = new_thread_id
            meta["total_pause_sum"] = 0
            meta["msg_count"] = 1
            
            self.redis.set(key, json.dumps(meta, ensure_ascii=False))
            
            return {
                "thread_id": new_thread_id,
                "previous_thread_id": old_thread_id,
                "make_history_summary": True
            }
        else:
            logger.info(f'[IN OLD THREAD]')
            self.redis.set(key, json.dumps(meta, ensure_ascii=False))
            return {
                "thread_id": meta["current_thread_id"],
                "previous_thread_id": None,
                "make_history_summary": False
            }