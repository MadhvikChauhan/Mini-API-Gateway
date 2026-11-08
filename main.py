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
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    filename="app.log"
                    )

BACKEND_SERVICES = {
    "products": "http://127.0.0.1:10001",
    "users": "http://127.0.0.1:10002",
    "orders": "http://127.0.0.1:10003",
    "payments": "http://127.0.0.1:10004",
    "inventory": "http://127.0.0.1:10005",
}

API_KEYS = {
    "abc123": {
        "client": "dev",
        "role": "admin"
    },
    "xyz456": {
        "client": "user",
        "role": "user"
    }
}

async def verify_api_key(api_key: str = Header(default=None, alias="X-API-Key")):
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API key is missing"
        )

    client_data = next(
        (
            data
            for stored_key, data in API_KEYS.items()
            if secrets.compare_digest(api_key, stored_key)
        ),
        None
    )

    if client_data is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
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

        base_url = get_backend_url(service_name)
        backend_path = url_path[len(service_name):].lstrip("/")
        url = f"{base_url}/{service_name}"

        if backend_path:
            url = f"{url}/{backend_path}"
        method = request.method

        # Reuse the request ID created by middleware
        req_id = request.state.request_id

        # Forward incoming headers and attach the same request ID
        http_data = dict(request.headers)
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