import json

# Mocking the problematic raw data from your DEBUG output
mock_logs = [
    {"input_tokens": 17583, "cached_input_tokens": 14720, "total_tokens": 17688},
    {"input_tokens": 19663, "cached_input_tokens": 18304, "total_tokens": 19994}
]

def calculate_corrected_tokens(logs):
    total_new_input = 0
    total_cache_read = 0
    
    for entry in logs:
        raw_input = entry["input_tokens"]
        cache_read = entry["cached_input_tokens"]
        
        # The logic: New tokens = Total input reported - Cache tokens
        actual_new_input = raw_input - cache_read
        
        total_new_input += actual_new_input
        total_cache_read += cache_read
        
        print(f"Row: Input={raw_input}, Cache={cache_read} | "
              f"Corrected New Input={actual_new_input}")
              
    return total_new_input, total_cache_read

new_input, cache_input = calculate_corrected_tokens(mock_logs)
print(f"\nFinal Aggregates:")
print(f"Total New Input: {new_input}")
print(f"Total Cache Read: {cache_input}")