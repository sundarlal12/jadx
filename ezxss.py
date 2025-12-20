#!/usr/bin/env python3
import requests
import random
import string
import sys

def generate_random_domain(base_length=8, tld=".fun"):
    """Generate a random domain name"""
    letters = string.ascii_lowercase
    random_string = ''.join(random.choice(letters) for _ in range(base_length))
    return random_string + tld

def send_request(target_domain=None):
    """Send the POST request with the specified or random domain"""
    
    # Generate a random domain if none provided
    if target_domain is None:
        target_domain = generate_random_domain()
        print(f"Using random domain: {target_domain}")
    
    # URL for the POST request
    url = 'https://chintu.ezxss.com/callback'
    
    # Headers
    headers = {
        'Host': 'chintu.ezxss.com',
        'User-Agent': 'curl/7.85.0',
        'Accept': '*/*'
    }
    
    # JSON payload with dynamic domain
    json_data = {
        "uri": f"https://{target_domain}/Khatri/x2/users-management.php",
        "cookies": "",
        "referer": f"https://{target_domain}/Khatri/x2/users-management.php",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
        "origin": f"https://{target_domain}",
        "localstorage": {
            "auth_password": "who_are_you",
            "auth_username": "who_are_you",
            "ezXSS": "who_are_you"
        },
        "sessionstorage": {},
        "dom": f"https://{target_domain}/Khatri/x2/users-management.php",
        "payload":"//chintu.ezxss.com/",
       
     
       
    }
    
    # Send the POST request with SSL verification disabled
    try:
        response = requests.post(url, headers=headers, json=json_data, verify=False)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        return response
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        return None

def send_multiple_requests(num_requests=5):
    """Send multiple requests with different random domains"""
    for i in range(num_requests):
        print(f"\n--- Request {i+1}/{num_requests} ---")
        send_request()
        # Add a small delay between requests if needed
        # import time
        # time.sleep(0.5)

def main():
    """Main function with command line options"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Send POST requests with dynamic domains')
    parser.add_argument('--domain', '-d', help='Use specific domain instead of random')
    parser.add_argument('--random', '-r', action='store_true', help='Send multiple random requests')
    parser.add_argument('--count', '-c', type=int, default=5, help='Number of random requests (default: 5)')
    parser.add_argument('--length', '-l', type=int, default=8, help='Length of random domain name (default: 8)')
    
    args = parser.parse_args()
    
    if args.random:
        # Override the generate_random_domain function to use custom length
        global generate_random_domain
        original_generate = generate_random_domain
        generate_random_domain = lambda: original_generate(args.length, ".fun")
        
        send_multiple_requests(args.count)
    elif args.domain:
        print(f"Using specified domain: {args.domain}")
        send_request(args.domain)
    else:
        # Single request with random domain
        send_request()

if __name__ == "__main__":
    # Suppress SSL warnings (not recommended for production)
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    main()