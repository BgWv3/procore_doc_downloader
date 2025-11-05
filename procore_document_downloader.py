#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Procore Document Downloader
Downloads all files from a Procore project's documents tool while preserving folder structure.
"""

import os
import sys
import json
import time
import requests
from urllib.parse import urlencode
from pathlib import Path
import webbrowser
from dotenv import load_dotenv
import csv
from datetime import datetime

# Set UTF-8 encoding for stdout to handle special characters
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')


def log_message(message, to_console=True):
    """Write message to log file and optionally to console"""
    global log_file
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] {message}"
    
    if to_console:
        print(message)
    
    if log_file:
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry + '\n')
        except Exception as e:
            print(f"[WARNING] Could not write to log file: {e}")



# Configuration
CLIENT_ID = None
CLIENT_SECRET = None
REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob"
AUTH_URL = "https://login.procore.com/oauth/authorize"
TOKEN_URL = "https://login.procore.com/oauth/token"
API_BASE_URL = "https://api.procore.com/rest/v1.0"

# Global variables for OAuth flow
access_token = None
log_file = None


def get_oauth_token():
    """Handle OAuth 2.0 authentication flow"""
    global access_token
    
    # Step 1: Build authorization URL
    auth_params = {
        'client_id': CLIENT_ID,
        'response_type': 'code',
        'redirect_uri': REDIRECT_URI
    }
    
    auth_url_full = f"{AUTH_URL}?{urlencode(auth_params)}"
    
    print(f"\n{'='*60}")
    print("STEP 1: AUTHENTICATION")
    print(f"{'='*60}")
    print("\nOpening browser for Procore login...")
    print(f"If the browser doesn't open, visit this URL:\n{auth_url_full}\n")
    
    # Open browser
    webbrowser.open(auth_url_full)
    
    # Step 2: Get authorization code from user
    print("After logging in, you'll receive an authorization code.")
    auth_code = input("\nPaste the authorization code here: ").strip()
    
    if not auth_code:
        print("[ERROR] Authorization code is required")
        sys.exit(1)
    
    print("[OK] Authorization code received")
    
    # Step 3: Exchange authorization code for access token
    print("\nExchanging authorization code for access token...")
    
    token_data = {
        'grant_type': 'authorization_code',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'code': auth_code,
        'redirect_uri': REDIRECT_URI
    }
    
    response = requests.post(TOKEN_URL, data=token_data)
    
    if response.status_code == 200:
        token_response = response.json()
        access_token = token_response['access_token']
        print("[OK] Access token obtained successfully\n")
        return access_token
    else:
        print(f"[ERROR] Error obtaining access token: {response.status_code}")
        print(response.text)
        sys.exit(1)


def api_request(endpoint, params=None):
    """Make an API request with rate limiting awareness"""
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    
    url = f"{API_BASE_URL}{endpoint}"
    
    try:
        response = requests.get(url, headers=headers, params=params)
        
        # Handle rate limiting
        if response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 60))
            print(f"[WARNING] Rate limit reached. Waiting {retry_after} seconds...")
            time.sleep(retry_after)
            return api_request(endpoint, params)
        
        response.raise_for_status()
        return response.json()
    
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] API request failed: {e}")
        return None


def select_company():
    """List and select a company"""
    print(f"\n{'='*60}")
    print("STEP 2: SELECT COMPANY")
    print(f"{'='*60}\n")
    
    companies = api_request('/companies')
    
    if not companies:
        print("[ERROR] No companies found or error fetching companies")
        sys.exit(1)
    
    print("Available companies:")
    for idx, company in enumerate(companies, 1):
        print(f"  {idx}. {company['name']} (ID: {company['id']})")
    
    while True:
        try:
            choice = input("\nSelect company number: ")
            company_idx = int(choice) - 1
            if 0 <= company_idx < len(companies):
                selected = companies[company_idx]
                print(f"[OK] Selected: {selected['name']}\n")
                return selected['id']
            else:
                print("Invalid selection. Please try again.")
        except ValueError:
            print("Invalid input. Please enter a number.")


def select_project(company_id):
    """List and select project(s)"""
    print(f"\n{'='*60}")
    print("STEP 3: SELECT PROJECT(S)")
    print(f"{'='*60}\n")
    
    projects = api_request('/projects', params={'company_id': company_id})
    
    if not projects:
        print("[ERROR] No projects found or error fetching projects")
        sys.exit(1)
    
    # Export projects to CSV
    csv_filename = f"procore_projects_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    try:
        with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['Number', 'Project ID', 'Project Name', 'Project Code', 'Address', 'City', 'State']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for idx, project in enumerate(projects, 1):
                writer.writerow({
                    'Number': idx,
                    'Project ID': project.get('id', ''),
                    'Project Name': project.get('name', ''),
                    'Project Code': project.get('project_number', ''),
                    'Address': project.get('address', ''),
                    'City': project.get('city', ''),
                    'State': project.get('state_code', '')
                })
        print(f"[OK] Project list exported to: {csv_filename}\n")
    except Exception as e:
        print(f"[WARNING] Could not export CSV: {e}\n")
    
    print("Available projects:")
    for idx, project in enumerate(projects, 1):
        print(f"  {idx}. {project['name']} (ID: {project['id']})")
    
    print(f"\nSelection options:")
    print(f"  - Enter a single number (e.g., '3')")
    print(f"  - Enter multiple numbers separated by commas (e.g., '1,3,5')")
    print(f"  - Enter a range (e.g., '1-5')")
    print(f"  - Enter 'all' to select all projects")
    
    while True:
        try:
            choice = input("\nSelect project(s): ").strip().lower()
            
            selected_projects = []
            
            if choice == 'all':
                selected_projects = projects
            elif '-' in choice and ',' not in choice:
                # Handle range (e.g., "1-5")
                start, end = choice.split('-')
                start_idx = int(start) - 1
                end_idx = int(end) - 1
                if 0 <= start_idx <= end_idx < len(projects):
                    selected_projects = projects[start_idx:end_idx + 1]
                else:
                    print("Invalid range. Please try again.")
                    continue
            elif ',' in choice:
                # Handle comma-separated values (e.g., "1,3,5")
                indices = [int(x.strip()) - 1 for x in choice.split(',')]
                if all(0 <= idx < len(projects) for idx in indices):
                    selected_projects = [projects[idx] for idx in indices]
                else:
                    print("Invalid selection. Please try again.")
                    continue
            else:
                # Handle single selection
                project_idx = int(choice) - 1
                if 0 <= project_idx < len(projects):
                    selected_projects = [projects[project_idx]]
                else:
                    print("Invalid selection. Please try again.")
                    continue
            
            # Confirm selection
            print(f"\n[OK] Selected {len(selected_projects)} project(s):")
            for proj in selected_projects:
                print(f"  - {proj['name']}")
            
            confirm = input("\nProceed with these projects? (y/n): ").strip().lower()
            if confirm == 'y':
                print("\n[OK] Starting download process...")
                return selected_projects
            else:
                print("\nLet's try again...")
                continue
                
        except ValueError:
            print("Invalid input. Please try again.")
        except Exception as e:
            print(f"Error: {e}. Please try again.")


def download_file(url, local_path):
    """Download a file from URL to local path"""
    try:
        # Create parent directory if it doesn't exist
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        with open(local_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        return True
    except Exception as e:
        print(f"    [ERROR] Error downloading file: {e}")
        return False


def process_folder(folder_id, company_id, project_id, base_path, folder_path=""):
    """
    Recursively process a folder and download all files.
    
    Args:
        folder_id: The folder ID to process (None for root)
        company_id: Company ID
        project_id: Project ID
        base_path: Base download directory
        folder_path: Current folder path for display
    """
    # Get folder contents
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Procore-Company-Id': str(company_id)
    }
    
    params = {
        'project_id': project_id
    }
    
    if folder_id:
        endpoint = f'/folders/{folder_id}'
    else:
        endpoint = '/folders'
    
    try:
        url = f"{API_BASE_URL}{endpoint}"
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 60))
            log_message(f"  [WARNING] Rate limit reached. Waiting {retry_after} seconds...")
            time.sleep(retry_after)
            return process_folder(folder_id, company_id, project_id, base_path, folder_path)
        
        response.raise_for_status()
        data = response.json()
        
    except requests.exceptions.RequestException as e:
        log_message(f"  [ERROR] Error fetching folder: {e}")
        return
    
    # Process files in current folder
    if 'files' in data and data['files']:
        for file in data['files']:
            # Skip deleted files
            if file.get('is_deleted', False):
                continue
            
            file_name = file['name']
            
            # Get the latest file version
            if file.get('file_versions') and len(file['file_versions']) > 0:
                # Sort by version number and get the latest
                latest_version = max(file['file_versions'], key=lambda v: v.get('number', 0))
                
                if 'url' in latest_version and latest_version['url']:
                    download_url = latest_version['url']
                    
                    # Build local path
                    local_file_path = os.path.join(base_path, folder_path, file_name)
                    
                    log_message(f"  -> Downloading: {folder_path}/{file_name}")
                    
                    if download_file(download_url, local_file_path):
                        log_message(f"    [OK] Saved to: {local_file_path}")
                    else:
                        log_message(f"    [ERROR] Failed to download")
    
    # Process subfolders
    if 'folders' in data and data['folders']:
        for subfolder in data['folders']:
            # Skip deleted folders
            if subfolder.get('is_deleted', False) or subfolder.get('is_recycle_bin', False):
                continue
            
            subfolder_name = subfolder['name']
            subfolder_id = subfolder['id']
            
            # Build subfolder path
            new_folder_path = os.path.join(folder_path, subfolder_name) if folder_path else subfolder_name
            
            log_message(f"\n[FOLDER] Processing folder: {new_folder_path}")
            
            # Create local directory
            local_folder_path = os.path.join(base_path, new_folder_path)
            os.makedirs(local_folder_path, exist_ok=True)
            log_message(f"[FOLDER] Created directory: {local_folder_path}")
            
            # Recursively process subfolder
            process_folder(subfolder_id, company_id, project_id, base_path, new_folder_path)


def download_project_documents(company_id, project_id, project_name):
    """Download all documents from a project"""
    global log_file
    
    print(f"\n{'='*60}")
    print("STEP 4: DOWNLOADING DOCUMENTS")
    print(f"{'='*60}\n")
    
    # Create base download directory
    base_path = os.path.join(os.getcwd(), 'procore_downloads', project_name.replace('/', '_'))
    os.makedirs(base_path, exist_ok=True)
    
    # Initialize log file for this project
    log_file = os.path.join(base_path, f"download_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
    
    log_message(f"{'='*60}")
    log_message(f"Download started for project: {project_name}")
    log_message(f"Project ID: {project_id}")
    log_message(f"Company ID: {company_id}")
    log_message(f"Download location: {base_path}")
    log_message(f"{'='*60}\n")
    
    print(f"Download location: {base_path}")
    print(f"Log file: {log_file}\n")
    print("Starting download...\n")
    
    # Start processing from root folder (folder_id = None means root)
    process_folder(None, company_id, project_id, base_path)
    
    log_message(f"\n{'='*60}")
    log_message("[OK] DOWNLOAD COMPLETE")
    log_message(f"{'='*60}")
    log_message(f"All files saved to: {base_path}\n")
    
    print(f"\n{'='*60}")
    print("[OK] DOWNLOAD COMPLETE")
    print(f"{'='*60}")
    print(f"\nAll files saved to: {base_path}")
    print(f"Log saved to: {log_file}\n")


def main():
    """Main execution function"""
    global CLIENT_ID, CLIENT_SECRET
    
    print("""
===============================================================
           PROCORE DOCUMENT DOWNLOADER                       
===============================================================
    """)
    
    # Load environment variables from .env file
    load_dotenv()
    
    # Try to get credentials from environment variables
    CLIENT_ID = os.getenv('PROCORE_CLIENT_ID')
    CLIENT_SECRET = os.getenv('PROCORE_CLIENT_SECRET')
    
    # If not found in .env, prompt user
    if not CLIENT_ID:
        CLIENT_ID = input("Enter your Procore Client ID: ").strip()
    else:
        print(f"[OK] Client ID loaded from .env file")
    
    if not CLIENT_SECRET:
        CLIENT_SECRET = input("Enter your Procore Client Secret: ").strip()
    else:
        print(f"[OK] Client Secret loaded from .env file")
    
    if not CLIENT_ID or not CLIENT_SECRET:
        print("[ERROR] Client ID and Secret are required")
        sys.exit(1)
    
    # Step 1: Authenticate
    get_oauth_token()
    
    # Step 2: Select company
    company_id = select_company()
    
    # Step 3: Select project(s)
    selected_projects = select_project(company_id)
    
    # Step 4: Download documents for each project
    for idx, project in enumerate(selected_projects, 1):
        project_id = project['id']
        project_name = project['name']
        
        print(f"\n{'='*60}")
        print(f"PROJECT {idx}/{len(selected_projects)}: {project_name}")
        print(f"{'='*60}")
        
        download_project_documents(company_id, project_id, project_name)
    
    print(f"\n{'='*60}")
    print("[OK] ALL PROJECTS COMPLETE")
    print(f"{'='*60}")
    print(f"\nProcessed {len(selected_projects)} project(s)\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[ERROR] Download cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        sys.exit(1)
