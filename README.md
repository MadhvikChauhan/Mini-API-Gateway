# Mini API Gateway

A lightweight API Gateway built with **FastAPI** that forwards product requests to a downstream API and provides centralized request tracking, logging, response forwarding, and error handling.

## Overview

This project demonstrates the fundamentals of an API Gateway by acting as an intermediary between a client and a downstream Product API.

The gateway receives a product request, forwards it to the downstream service, and returns the downstream response while adding request identification and duration headers.

## Architecture

```text
Client
  |
  | GET /api/products/{product_id}
  v
+--------------------------------+
|       FastAPI API Gateway      |
|                                |
|  Request Middleware            |
|  - Generate Request ID         |
|  - Log Request Lifecycle       |
|  - Measure Request Duration    |
|                                |
|  Product Gateway Endpoint      |
|  - Forward Request             |
|  - Handle Downstream Errors    |
|  - Return Downstream Response  |
+--------------------------------+
  |
  | HTTP Request
  | X-Request-ID
  v
+--------------------------------+
|      Downstream Product API    |
+--------------------------------+
  |
  v
Database

Downstream response
  |
  v
API Gateway
  |
  | Response + Observability Headers
  v
Client
```

## Current Features

- **Request forwarding:** Forwards product requests to the downstream Product API using Python `requests`.
- **Request ID generation:** Generates a unique UUID for every incoming request.
- **Request ID propagation:** Stores the request ID in `request.state` and forwards it using the `X-Request-ID` header.
- **Middleware-based observability:** Logs incoming requests and completed responses.
- **Duration measurement:** Uses `time.perf_counter()` to measure gateway request-processing duration.
- **Query parameter forwarding:** Passes incoming query parameters to the downstream service.
- **Response forwarding:** Preserves the downstream response body, HTTP status code, and content type.
- **Timeout handling:** Returns `504 Gateway Timeout` when the downstream request times out.
- **Connection and transport error handling:** Returns `502 Bad Gateway` for other `requests` transport errors.
- **Exception logging:** Logs unexpected gateway exceptions with traceback information.

## Technology Stack

- Python
- FastAPI
- Uvicorn
- Requests
- HTTP
- REST APIs
- Python logging
- UUID
- `time.perf_counter()`

## API Endpoint

### Get Product

**Method:** `GET`

**Gateway endpoint:**

```http
/api/products/{product_id}
```

**Downstream endpoint:**

```http
/products/{product_id}
```

The gateway currently forwards requests to the configured downstream base URL:

```text
http://127.0.0.1:10001
```

### Example Request

```bash
curl -i http://localhost:10002/api/products/1
```

Replace the product ID with an ID appropriate for your database.

## Response Headers

The gateway middleware adds the following headers to the response:

| Header | Description |
|---|---|
| `X-Request-ID` | Unique identifier used to correlate requests and logs |
| `X-Request-Duration` | Gateway request-processing duration in milliseconds |

Example:

```http
HTTP/1.1 200 OK
X-Request-ID: <request-uuid>
X-Request-Duration: 18.82ms
Content-Type: application/json
```

The response status and body are forwarded from the downstream service.

## Request Lifecycle

1. A client sends a request to the gateway.
2. Middleware generates a UUID and stores it in `request.state.request_id`.
3. Middleware logs the request method, path, and request ID.
4. The gateway endpoint reads the same request ID and forwards it to the downstream Product API.
5. The downstream service processes the request and returns a response.
6. The gateway logs the downstream status code, content type, and response size.
7. The gateway returns the downstream response body and status code.
8. Middleware adds `X-Request-ID` and `X-Request-Duration` to the final response and logs completion.

## Error Handling

| Scenario | Current behavior |
|---|---|
| Downstream request succeeds | Returns the downstream status and body |
| Downstream returns `404` or `500` | Preserves the downstream status and body |
| Downstream request times out | Returns `504 Gateway Timeout` |
| Downstream connection or transport error | Returns `502 Bad Gateway` |
| Gateway route does not match | FastAPI returns `404 Not Found` |
| Unexpected gateway exception | Logs the exception and re-raises it |

A `404` response is determined by the downstream API's response or by FastAPI when the requested gateway route does not exist. An empty response body alone does not imply that a resource is missing.

## Running the Project

### Prerequisites

- Python installed
- Required Python packages installed
- Downstream Product API running at the configured address

### Install Dependencies

```bash
pip install fastapi uvicorn requests
```

### Start the Downstream API

Start the existing Product API on port `10001`, or update the gateway's downstream URL to match your configuration.

### Start the Gateway

Assuming your FastAPI application instance is named `app` in `main.py`:

```bash
uvicorn main:app --host 127.0.0.1 --port 10002 --reload
```

Update `main:app` if your module or application variable has a different name.

### Test the Gateway

```bash
curl -i http://localhost:10002/api/products/1
```

Inspect the response headers and gateway logs to verify request ID generation, request forwarding, response handling, and duration measurement.

## Current Limitations

- The gateway currently uses synchronous `requests` for downstream communication.
- Only the product GET endpoint is implemented.
- The downstream service URL is currently configured directly in the code.
- Authentication and authorization have not been implemented.
- Rate limiting and concurrency controls have not been implemented.
- Automated tests and containerized deployment have not yet been added.

## Project Status

The initial gateway forwarding flow and middleware-based observability have been implemented and tested, including request IDs, duration headers, downstream response forwarding, and error handling.

This project currently focuses on understanding HTTP request lifecycles, FastAPI middleware, service-to-service communication, and gateway error handling.