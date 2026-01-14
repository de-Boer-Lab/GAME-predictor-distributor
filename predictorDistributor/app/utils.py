'''Helper functions to create batches of request based on N workers, and gather N responses to reassemble predictions.'''

from typing import List, Dict, Any, Generator

class InconsistentMatcherError(Exception):
    """
    Raised when workers return inconsistent '_actual' values from Matcher.
    """
    pass

def create_batches(
    data: Dict[str, Any], 
    num_batches: int
    ) -> Generator[Dict[str, Any], None, None]:
    
    """
    Splits the main request payload into N smaller, valid request payloads
    """
    
    # Get all sequence keys to be batched
    all_seq_keys = list(data.get("sequences", {}).keys())
    if not all_seq_keys:
        # No sequences, just yield the original request once
        yield data
        return
        
    # Create N empty batches
    # (Each will be a list of sequence keys)
    batches: List[List[str]] = [[] for _ in range(num_batches)]
    
    # Distribute keys as evenly as possible
    for i, key in enumerate(all_seq_keys):
        batches[i % num_batches].append(key)

    # Create a new payload for each batch
    for batch_keys in batches:
        if not batch_keys:
            continue # Skip empty batches
            
        # Create the new partial 'sequences' dict
        batch_sequences = {key: data["sequences"][key] for key in batch_keys}
        
        # Create the new partial 'prediction_ranges' dict (if provided)
        batch_ranges = {}
        if "prediction_ranges" in data:
            batch_ranges = {
                key: data["prediction_ranges"][key] 
                for key in batch_keys 
                if key in data["prediction_ranges"]
            }

        # Yield a complete, new request payload
        # It has all original metadata, but partial sequences and prediction_ranges
        new_payload = data.copy()
        new_payload["sequences"] = batch_sequences
        
        if "prediction_ranges" in data:
            new_payload["prediction_ranges"] = batch_ranges
            
        yield new_payload


def reassemble_responses(
    responses: List[Dict[str, Any]],
    original_seq_keys: List[str] # To accept the original sequence key order
    ) -> Dict[str, Any]:
    
    """
    Validates Matcher consistency.
    Merges multiple partial responses into one single, valid response.
    It will keep the predictor_name from the first worker,
    and generically merge and sort all sequence-based dictionaries.
    """
    
    # Flag if no response from any worker
    if not responses:
        raise ValueError("Cannot reassemble from zero responses.")
    
    # The responses from workers will come in random order
    KEYS_TO_MERGE_AND_SORT = ["predictions", "trim_upstream"]
    # In order to check that each worker mapped the requests correctly, we need all the actual keys to match
    KEYS_FOR_CONSISTENCY = ["type_actual", "cell_type_actual", "species_actual"]
    # NOTE: Can also add scale_actual in the `KEYS_FOR_CONSISTENCY`
    
    # Validation step for consistency
    # Create a map that will store the first `_actual` values for each task
    task_consistency_map: Dict[str, Dict[str, Any]] = {}
    
    print("Checking for Matcher consistency across all workers...")
    for resp in responses:
        for task in resp.get("prediction_tasks", []):
            task_name = task.get("name")
            
            if task_name not in task_consistency_map:
                # First time seeing this task. Store its 'actual' values
                task_consistency_map[task_name] = {
                    key: task.get(key) for key in KEYS_FOR_CONSISTENCY
                }
            else:
                # We've seen this task. Compare its values to the stored ones
                stored_values = task_consistency_map[task_name]
                for key in KEYS_FOR_CONSISTENCY:
                    current_value = task.get(key)
                    expected_value = stored_values.get(key)
                    
                    if current_value != expected_value:
                        # INCONSISTENCY FOUND! Raise the error
                        raise InconsistentMatcherError(
                            f"Matcher inconsistency for task '{task_name}': "
                            f"Worker returned '{key}: {current_value}' "
                            f"but expected '{key}: {expected_value}'"
                        )
    print("Matcher consistency check passed.")

    # Use the first response as the template
    final_response = responses[0].copy()

    # Create a lookup for tasks in the final response
    # This allows us to merge results efficiently
    final_tasks_map = {
        task["name"]: task for task in final_response.get("prediction_tasks", [])
    }

    # Iterate over the REST of the responses (from index 1 onwards)
    for resp in responses[1:]:
        for task in resp.get("prediction_tasks", []):
            task_name = task.get("name")
            
            # Find the matching task in the final response
            if task_name in final_tasks_map:
                final_task = final_tasks_map[task_name]
                
                # Generic merge logic
                for key in KEYS_TO_MERGE_AND_SORT:
                    if key in task:
                        # Find or create the dictionary in the final response
                        target_dict = final_task.setdefault(key, {}) # gets the keys or creates it, if missing
                        # Merge the new data from the worker
                        target_dict.update(task[key])
            else:
                # This task wasn't in the first response?
                # This is an edge case, but we can just append it
                print(f"Warning: Found new task '{task_name}' in partial response.")
                final_response.get("prediction_tasks", []).append(task)
    
    # ADDITION: Re-sort the predictions dictionaries based on the original key order
    print("Ordering the sequence keys as they were provided...")
    if original_seq_keys:  # Only sort if we have keys to sort by
        for task in final_response.get("prediction_tasks", []):
            
            # Loop over the keys that need sorting
            for key in KEYS_TO_MERGE_AND_SORT:
                merged_dict = task.get(key)
                
                # Check if this task has this key and it's a dictionary
                if not isinstance(merged_dict, dict):
                    continue # Skip if key is missing (for some reason)
            
                # Create a new, ordered dictionary
                ordered_dict = {
                    seq_key: merged_dict[seq_key] 
                    for seq_key in original_seq_keys 
                    if seq_key in merged_dict
                }
                
                # Add any keys that might have been in merged_dict but not
                # in original_seq_keys (this shouldn't happen, but it's safe)
                ordered_dict.update({
                    key: val 
                    for key, val in merged_dict.items() 
                    if key not in ordered_dict
                })

                # Replace the old (unordered) dict with the new (ordered) one
                task[key] = ordered_dict

    return final_response