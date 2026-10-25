from http import HTTPStatus
from http.client import responses
import httpx
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


app = FastAPI()
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




@router.get("/api/products/{product_id}", include_in_schema=False)
async def product_gateway(request: Request, product_id: int):
    try:
        # start = time.perf_counter()
        url = f"http://127.0.0.1:10001/products/{product_id}"

        # Reuse the request ID created by middleware
        req_id = request.state.request_id

        # Forward incoming headers and attach the same request ID
        http_data = dict(request.headers)
        http_data["X-Request-ID"] = req_id

        logging.info(
            "Forwarding request | id=%s | url=%s",
            req_id,
            f"http://127.0.0.1:10001/products/{product_id}",
        )

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=http_data,
                params=request.query_params,
                timeout=10
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