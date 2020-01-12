import redis
from src.database.singleton import Singleton

@Singleton
class RedisAdapter:
    def __init__(self):
        self._database = redis.StrictRedis(host='localhost',port=6379,db=0)


    def get(self,key):
        result = self._database.get(key)
        return result.decode('UTF-8') if result is not None else result


    def reset(self):
        self._database.flushdb()


    def delete(self,key):
        self._database.delete(key)


    def set(self,key,value=''):
        if type(key) == list:
            pipe = self._database.pipeline()
            for key,value in key:
                pipe.set(key,value)
            pipe.execute()

        elif type(key) == str:
            self._database.set(key,value)
