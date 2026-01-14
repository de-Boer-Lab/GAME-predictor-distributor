import asyncio
import httpx
import msgpack
from typing import List, Dict, Any

from .config import configuration_settings
from .utils import create_batches, reassemble_responses, InconsistentMatcherError

# Use a single, persistent async client
# Reuse connection
client = httpx.AsyncClient(timeout=None) # No timeout

async def run_scatter_gather(payload: Dict[str, Any],
                             content_type_header: str,
                             accept_header: str) -> Dict[str, Any]:
    """
    The main Scatter and Gather workflow.
    Handles json/msgpack content negotiation with workers.
    """
    
    # 1. SCATTER: Create batch payloads
    worker_urls = [p.base_url for p in configuration_settings.predictor_pool]
    num_batches = len(worker_urls)
    
    # Get the original sequence order
    original_seq_keys = list(payload.get("sequences", {}).keys())
    
    batches = list(create_batches(payload, num_batches))
    
    # 2. DISTRIBUTE: Create a list of "jobs" to run
    # Map each batch payload to a worker URL
    tasks = []
    
    # Use the headers evaluator sends
    headers = {
        "Content-Type": content_type_header,
        "Accept": accept_header
    }
    
    # Check if request is serialized as msgpack
    is_msgpack_request = "application/msgpack" in content_type_header
    
    for i, batch_payload in enumerate(batches):
        worker_url = worker_urls[i % num_batches] + "/predict"
        
        # Create an async task for this one POST request
        if is_msgpack_request:
            # Send raw msgpack bytes
            body = msgpack.packb(batch_payload, use_bin_type=True)
            tasks.append(
                client.post(worker_url, data=body, headers=headers)
            )
            
        else:
            # Send JSON
            tasks.append(
                client.post(worker_url, json=batch_payload, headers=headers)
            )

    print(f"Distributing {len(payload['sequences'])} sequences into {len(tasks)} batches...")
    
    # 3. GATHER: Run all jobs concurrently and wait for them all
    # This is the magic of asyncio
    try:
        results: List[httpx.Response] = await asyncio.gather(*tasks)
    except httpx.ConnectError as e:
        print(f"FATAL: Connection error to worker.")
        # Return a valid error response
        url = e.request.url if e.request else "Unknown URL"
        return {
            "error": [{"server_error": f"Failed to connect to worker: {url}"}]
        }
    
    # 4. DECODE WORKER RESPONSES (Partial Responses)
    # Check for HTTP errors from workers
    partial_responses = []
    for res in results:
        try:
            res.raise_for_status() # Raise 4xx/5xx errors
            content_type = res.headers.get("Content-Type", "").lower()
            if "application/msgpack" in content_type:
                # Decode MsgPack from worker
                partial_responses.append(msgpack.unpackb(res.content, raw=False))
            else:
                # Default to JSON
                partial_responses.append(res.json())
                
        except httpx.HTTPStatusError as e:
            print(f"Error from worker {e.request.url}")
            # Worker returned an error. We must fail the whole job.
            try:
                # Try to parse the worker's JSON error response
                worker_error_payload = e.response.json()
                return worker_error_payload
            except Exception as json_decode_err:
                # The worker's error response wasn't valid JSON
                # Return any text that the worker responds with. 
                print(f"Could not decode worker's error response as JSON")
                return {
                    "error": [{"prediction_request_failed": f"Worker {e.request.url} failed with non-JSON response: {e.response.text}. {json_decode_err}."}]
                }

    print("All batches complete. Re-assembling response...")
    
    # 4. RE-ASSEMBLE: Merge the partial JSON responses
    try:
        final_response = reassemble_responses(
            partial_responses,
            original_seq_keys)
    except InconsistentMatcherError as e:
        print("The Matcher was inconsistent!")
        
        # Get the predictor_name from the first worker's response
        predictor_name = "UnknownPredictor" # Default
        if partial_responses:
             predictor_name = partial_responses[0].get("predictor_name", "UnknownPredictor")
            
        return {
            "predictor_name": predictor_name,
            "error": [{"prediction_request_failed": str(e)}]
        }
        
    return final_response