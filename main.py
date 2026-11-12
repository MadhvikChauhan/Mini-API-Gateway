from http import HTTPStatus
from http.client import responses
from contextlib import asynccontextmanager
import httpx
import secrets
from fastapi import Header, Depends
from fastapi import FastAPI, APIRouter, Request, status, Response, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import logging
import requests
import uuid
import time
import dotenv
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
import json
import hashlib

ENV_FILE = Path(__file__).resolve().parent / "mini_gateway.env"
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    filename="app.log"
                    )
file_path = Path(__file__).resolve().parent / "config.json"

BACKEND_SERVICES = {
    "products": "http://127.0.0.1:10001",
    "users": "http://127.0.0.1:10006",
    "orders": "http://127.0.0.1:10003",
    "payments": "http://127.0.0.1:10004",
    "inventory": "http://127.0.0.1:10005",
}

dotenv.load_dotenv(ENV_FILE)
DEV_API_KEY  = os.getenv('DEV_API_KEY')
QA_API_KEY = os.getenv('QA_API_KEY')


if not DEV_API_KEY or not QA_API_KEY:
    raise RuntimeError("Required API keys are missing from environment")

if DEV_API_KEY == QA_API_KEY:
    raise RuntimeError("API keys must be unique")

def save_api_keys(stats):
    data = {"api_keys":stats}
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)

def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def load_api_keys():
    if file_path.exists():
        with open(file_path, 'r') as f:
            data = json.load(f)
            return data['api_keys']

    else:
        initial_data = initialize_api_keys()
        save_api_keys(initial_data)
        return initial_data

def initialize_api_keys():
    dev_api_key, qa_api_key = DEV_API_KEY, QA_API_KEY
    hashed_dev_key, hashed_qa_key = hash_api_key(dev_api_key), hash_api_key(qa_api_key)
    auth_data = {hashed_dev_key: {
        "client": "dev",
        "role": "admin",
        "expires_at": int(datetime.timestamp(datetime.now(timezone.utc) + timedelta(hours=1)))
        },
    hashed_qa_key: {
        "client": "user",
        "role": "user",
        "expires_at": int(datetime.timestamp(datetime.now(timezone.utc) + timedelta(hours=1)))
    }}
    return auth_data


ACTIVE_API_KEYS = load_api_keys()

ROLE_METHOD_MAP = {
    'admin':{
                "products": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                "users": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                "orders": ["GET", "POST", "PUT", "PATCH", "DELETE"]
            },
    'user':{"products": ["GET", "POST"]}
}


def generate_api_key():
    return secrets.token_urlsafe(32)


def revoke_api_key(api_key: str):
    hashed_key = hash_api_key(api_key)
    if hashed_key not in ACTIVE_API_KEYS:
        return False
    ACTIVE_API_KEYS.pop(hashed_key)
    save_api_keys(ACTIVE_API_KEYS)
    return True

def register_api_key(client: str, role: str, expiry_hours:float=1):
    if role not in ROLE_METHOD_MAP:
        raise ValueError(f"Invalid role: {role}")
    if expiry_hours <= 0:
        raise ValueError(f"Invalid duration: {expiry_hours}")
    new_key = generate_api_key()
    hashed_new_key = hash_api_key(new_key)
    ACTIVE_API_KEYS[hashed_new_key] = {'client':client, 'role':role,
                                "expires_at": int(datetime.timestamp(datetime.now(timezone.utc) + timedelta(hours=expiry_hours)))}

    save_api_keys(ACTIVE_API_KEYS)
    return new_key

async def verify_api_key(api_key: str = Header(default=None, alias="X-API-Key")):
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API key is missing"
        )
    hashed_key = hash_api_key(api_key)
    client_data = next(
        (
            data
            for stored_key, data in ACTIVE_API_KEYS.items()
            if secrets.compare_digest(hashed_key, stored_key)
        ),
        None
    )

    if client_data is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )

    current_time = int(datetime.now(timezone.utc).timestamp())
    expires_at = client_data["expires_at"]

    if current_time >= expires_at:
        raise HTTPException(
            status_code=401,
            detail="Token expired"
        )


    return client_data

# Creating pooled client connection
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient(
        timeout=10.0
    )
    logging.info("Shared HTTPX client initialized")
    try:
        yield
    finally:
        await app.state.http_client.aclose()
        logging.info("Shared HTTPX client closed")


app = FastAPI(lifespan=lifespan)
router = APIRouter()
TIMEOUT = (10,30)

@app.middleware("http")
async def request_observability(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start = time.perf_counter()
    request.state.request_id = request_id  # Add this line

    logging.info(
        "Request started | id=%s | method=%s | path=%s",
        request_id,
        request.method,
        request.url.path,
    )

    try:
        response = await call_next(request)
    except Exception:
        logging.exception(
            "Request failed | id=%s | path=%s",
            request_id,
            request.url.path,
        )
        raise

    duration_ms = (time.perf_counter() - start) * 1000

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Request-Duration"] = f"{duration_ms:.2f}ms"

    logging.info(
        "Request completed | id=%s | status=%s | duration_ms=%.2f",
        request_id,
        response.status_code,
        duration_ms,
    )

    return response

def get_user_data(user_id):
    return 0

def get_product_data(product_id):
    return 0

def get_product_list():
    return 0

def insert_user(user):
    return 0

def get_backend_url(service_name: str) -> str|None:

    if service_name not in BACKEND_SERVICES:
        raise ValueError(f"Backend service '{service_name}' not found")

    return BACKEND_SERVICES[service_name]


def get_service_name(request:Request):

    endpoint_path = request.url.path
    path_segments = endpoint_path.split("/")

    if len(path_segments) < 3 or path_segments[1] != "api":
        raise ValueError("Invalid API path")

    service_name = path_segments[2]

    if service_name not in BACKEND_SERVICES:
        raise ValueError(f"Unknown backend service: {service_name}")

    return service_name


@router.get("/users/{user_id}", include_in_schema=False)
def get_users(user_id):
    try:
        response = get_user_data(user_id)
        return response
    except Exception as e:
        logging.error(e.args)


@router.post("/users")
def create_user(user: dict):
    try:
        response = insert_user(user)
        return response
    except Exception as e:
        logging.error(e.args)


@router.get("/products/{product_id}", include_in_schema=False)
def get_products(product_id):
    try:
        response = get_product_data(product_id)
        return response
    except Exception as e:
        logging.error(e.args)

@router.get("/products")
def list_products():
    try:
        response = get_product_list()
        return response
    except Exception as e:
        logging.error(e.args)



@router.api_route("/api/{url_path:path}", methods=['GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS'])
async def general_gateway(request: Request, url_path, client_data=Depends(verify_api_key)):
    try:
        print(client_data)
        service_name = get_service_name(request)
        method = request.method
        role = client_data.get("role")

        role_permissions = ROLE_METHOD_MAP.get(role)

        if role_permissions is None:
            raise HTTPException(
                status_code=403,
                detail="Invalid or unauthorized role"
            )

        allowed_methods = role_permissions.get(service_name)

        if allowed_methods is None:
            raise HTTPException(
                status_code=403,
                detail="You are not authorized to access this service"
            )

        if method not in allowed_methods:
            raise HTTPException(
                status_code=403,
                detail="You are not authorized to perform this operation"
            )

        base_url = get_backend_url(service_name)
        backend_path = url_path[len(service_name):].lstrip("/")
        url = f"{base_url}/{service_name}"

        if backend_path:
            url = f"{url}/{backend_path}"


        # Reuse the request ID created by middleware
        req_id = request.state.request_id

        # Forward incoming headers and attach the same request ID
        http_data = dict(request.headers)
        http_data.pop("x-api-key", None)
        http_data["X-Request-ID"] = req_id

        logging.info(
            "Forwarding request | id=%s | url=%s",
            req_id,
            f"{url}",
        )

        client = request.app.state.http_client # Use the created connection instance



        response = await client.request(
            method=method,
            url=url,
            headers=http_data,
            params=request.query_params,
            content=await request.body(),
        )

        logging.info(
            "Downstream response | id=%s | status=%s | content_type=%s | bytes=%s",
            req_id,
            response.status_code,
            response.headers.get("content-type"),
            len(response.content),
        )

        # end_time = time.perf_counter()

        # Preserve the downstream response status and body
        return Response(
            content=response.content,
            status_code=response.status_code,
            media_type=response.headers.get("content-type")

        )

    except httpx.TimeoutException:
        logging.exception(
            "Downstream request timed out | id=%s",
            getattr(request.state, "request_id", "unknown"),
        )
        raise HTTPException(
            status_code=504,
            detail="Downstream service timed out",
        )

    except httpx.RequestError:
        logging.exception(
            "Downstream request failed | id=%s",
            getattr(request.state, "request_id", "unknown"),
        )
        raise HTTPException(
            status_code=502,
            detail="Downstream service unavailable",
        )

    except Exception:
        logging.exception("Unexpected error in product gateway")
        raise


@router.get("/api/products", include_in_schema=False)
def products_gateway():
    pass

@router.get("/api/users/{id}", include_in_schema=False)
def user_gateway():
    pass

@router.post("/api/users", include_in_schema=False)
def users_gateway():
    pass





app.include_router(router)


# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Run Application
if __name__ == "__main__":

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=10002
    )
    # curl -i -H "X-API-Key: xGRvh2rqo3aCFVtgzWt8jUaraP0I44ALASXofmtsB-4" -X GET http://127.0.0.1:10002/api/products/1