# #!/usr/bin/env python3
# import subprocess
# import os

# # Run 1.sh 10 times
# for i in range(100000000000000000000000000000000):
#     print(f"Running attempt {i+1}...")
#     # Make sure 1.sh is executable first: chmod +x 1.sh
#     subprocess.run(["./ezxss.sh"], check=True)
    
#     # Or if you want to run it in the background:
#     # subprocess.Popen(["./1.sh"])


#!/usr/bin/env python3
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

def run_ezxss(attempt_number):
    """Function to run the shell script. This will be executed by each thread."""
    print(f"Starting attempt {attempt_number}...")
    try:
        # Run the shell script. Using check=True will raise an error if the script fails.
        result = subprocess.run(["./ezxss.py"], capture_output=True, text=True, check=True)
        print(f"✓ Attempt {attempt_number} completed successfully.")
        # Optional: print or log the command's output/error
        # if result.stdout:
        #     print(f"Output: {result.stdout[:100]}")  # Print first 100 chars
        return (attempt_number, True, result.returncode)
    except subprocess.CalledProcessError as e:
        print(f"✗ Attempt {attempt_number} failed with code {e.returncode}")
        # Optional: print stderr for debugging
        # if e.stderr:
        #     print(f"Error: {e.stderr[:200]}")
        return (attempt_number, False, e.returncode)
    except Exception as e:
        print(f"✗ Attempt {attempt_number} encountered an unexpected error: {e}")
        return (attempt_number, False, None)

def main():
    # Number of times to run the script. Use a reasonable number for testing.
    total_attempts = 100000000000000000000  # You can change this back to a very large number
    # Number of threads to use for parallel execution
    max_workers = 50

    print(f"Starting to run ezxss.sh {total_attempts} times with {max_workers} parallel threads...")

    # Using ThreadPoolExecutor as a context manager ensures threads are cleaned up
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Create a future for each attempt
        # Using executor.submit schedules the function to run in the pool
        future_to_attempt = {executor.submit(run_ezxss, i): i for i in range(1, total_attempts + 1)}

        # As each future completes, you can process its result
        successful = 0
        failed = 0
        for future in as_completed(future_to_attempt):
            attempt_num = future_to_attempt[future]
            try:
                # Get the result from the future (this blocks until the result is ready)
                attempt_num, success, returncode = future.result()
                if success:
                    successful += 1
                else:
                    failed += 1
            except Exception as exc:
                print(f'Attempt {attempt_num} generated an exception: {exc}')
                failed += 1

    print(f"\n--- Execution Summary ---")
    print(f"Total attempts: {total_attempts}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")

if __name__ == "__main__":
    main()