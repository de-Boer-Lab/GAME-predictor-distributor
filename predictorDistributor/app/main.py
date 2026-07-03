# main.py
import msgpack
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from .config import configuration_settings, DISTRIBUTOR_NAME
from .distributor import run_scatter_gather, client as distributor_http_client

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages the startup and shutdown of the Distributor and its workers.
    (Simplified version: no health checks)
    """
    print(f"Starting {DISTRIBUTOR_NAME}...")

    # No workers get launched. This just waits for requests.
    print("Distributor is ready to accept requests.")
    print("Ensure workers are running and accessible at the URLs in config.")
    
    yield  # --- APPLICATION IS NOW RUNNING ---
    
    # --- SHUTDOWN LOGIC ---
    print(f"Shutting down {DISTRIBUTOR_NAME}... ")
    await distributor_http_client.aclose() # Close the main HTTP client
    print("Shutdown complete.")


# Create the FastAPI app with the new lifespan manager
app = FastAPI(title="PredictorDistributor", lifespan=lifespan)


# --- Endpoints ---

@app.get("/formats")
async def formats():
    """
    Impersonates a Predictor: forwards /formats to the first worker
    """
    
    # If no workers in pool, return server error
    if not configuration_settings.predictor_pool:
        return JSONResponse({"error": [{"server_error": "No predictors in pool"}]}, status_code=500)
    
    first_worker_url = configuration_settings.predictor_pool[0].base_url + "/formats"
    try:
        resp = await distributor_http_client.get(first_worker_url)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return JSONResponse(
            {
                "error": [{"server_error": f"Could not get formats from worker: {e}"}]
            },
            status_code=503)

@app.get("/help")
async def help():
    """
    Impersonates a Predictor: forwards /help to the first worker
    """
    # If no workers in pool, return server error
    if not configuration_settings.predictor_pool:
        return JSONResponse({"error": [{"server_error": "No predictors in pool"}]}, status_code=500)
    
    first_worker_url = configuration_settings.predictor_pool[0].base_url + "/help"
    try:
        resp = await distributor_http_client.get(first_worker_url)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return JSONResponse(
            {
                "error": [{"server_error": f"Could not get help from worker: {e}"}]
            },
            status_code=503)

@app.post("/predict")
async def predict(request: Request):
    """
    The main "Scatter-Gather" endpoint.
    Handles both, JSON and MsgPack, contents.
    Currently, no support for msgpack-numpy or any other serialization types.
    """
    
    # 1. DECODE INCOMING REQUEST
    content_type_header = request.headers.get("Content-Type", "application/json").lower()
    accept_header = request.headers.get("Accept", "application/json").lower()
    
    try:
        if "application/msgpack" in content_type_header:
            payload_bytes = await request.body()
            payload = msgpack.unpackb(payload_bytes, raw=False)
        else: # Default to JSON
            payload = await request.json()
    except Exception as e:
        return JSONResponse(
            {
                "error": [{"bad_prediction_request": f"Failed to decode request body: {e}"}]
            },
            status_code=400
        )
    
    # 2. RUN WORKFLOW
    final_response = await run_scatter_gather(
        payload, 
        content_type_header, 
        accept_header
    )
    
    # 3. HANDLE ERRORS (if any)
    # Errors are always sent as JSON
    if "error" in final_response:
        status_code = 500
        if "bad_prediction_request" in final_response["error"][0]: status_code = 400
        elif "prediction_request_failed" in final_response["error"][0]: status_code = 422
        return JSONResponse(final_response, status_code=status_code)
    
    # 4. ENCODE OUTGOING RESPONSE
    if "application/msgpack" in accept_header:
        # Send MsgPack back
        try:
            body = msgpack.packb(final_response, use_bin_type=True)
            return Response(content=body, media_type="application/msgpack")
        except Exception as e:
            # If encoding fails, fall back to a JSON error
            return JSONResponse(
                {"error": [{"server_error": f"Failed to encode response as MsgPack: {e}"}]},
                status_code=500
            )
    else:
        # Default to JSON
        return final_response