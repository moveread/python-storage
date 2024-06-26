from typing import TypeVar, Sequence, Any, ParamSpec, Callable, Awaitable
from functools import wraps
import inspect
from fastapi import FastAPI, Response, status as st, Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter
from haskellian import either as E, Either, Right, kwargs as kw
from kv.api import KV, ReadError, InvalidData

A = TypeVar('A')
Ps = ParamSpec('Ps')

def status(e: Either[ReadError, Any]):
  if e.tag == 'right':
    return st.HTTP_200_OK
  elif e.value.reason == 'db-error' or e.value.reason == 'invalid-data':
    return st.HTTP_500_INTERNAL_SERVER_ERROR
  else:
    return st.HTTP_404_NOT_FOUND

def with_status(func: Callable[Ps, Awaitable[Either[ReadError, A]]]):
  @wraps(func)
  async def wrapper(response: Response, *args: Ps.args, **kwargs: Ps.kwargs) -> ReadError | A:
    e = await func(*args, **kwargs)
    response.status_code = status(e)
    return e.value
  wrapper.__signature__ = kw.add_kw(inspect.signature(wrapper), 'response', Response) # type: ignore
  return wrapper

def api(
  kv: KV[A], *,
  parse: Callable[[bytes], Either[InvalidData, A]] = Right, # type: ignore
  dump: Callable[[A], bytes|str] = lambda x: x # type: ignore
):

  app = FastAPI()

  @app.post('/insert')
  @with_status
  @E.do[ReadError]()
  async def insert(key: str, req: Request):
    body = await req.body()
    val = parse(body).unsafe()
    return (await kv.insert(key, val)).unsafe()
  
  @app.get('/read')
  async def read(key: str):
    e = await kv.read(key)
    if e.tag == 'right':
      return Response(content=dump(e.value))
    else:
      content = TypeAdapter(ReadError).dump_json(e.value)
      return Response(content, status_code=status(e))
  
  @app.get('/has')
  @with_status
  async def has(key: str):
    return await kv.has(key)
  
  @app.get('/keys')
  @with_status
  async def keys():
    return await kv.keys()
  
  @app.delete('/delete')
  @with_status
  async def delete(key: str):
    return await kv.delete(key)
  

  @app.delete('/clear')
  @with_status
  async def clear():
    return await kv.clear()
  
  return app