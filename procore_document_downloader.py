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
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.table import Table
from rich.panel import Panel
from rich import box
from rich.live import Live
from rich.layout import Layout

# Set UTF-8 encoding for stdout to handle special characters
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# Initialize Rich console
console = Console()

# Global variables for OAuth flow
access_token = None
log_file = None
current_progress = None
download_stats = {
    'files_downloaded': 0,
    'folders_created': 0,
    'errors': 0
}


def log_message(message, to_console=True, style=None):
    """Write message to log file and optionally to console"""
    global log_file
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] {message}"
    
    if to_console:
        if style:
            console.print(message, style=style)
        else:
            console.print(message)
    
    if log_file:
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry + '\n')
        except Exception as e:
            console.print(f"[WARNING] Could not write to log file: {e}", style="yellow")



# Configuration
CLIENT_ID = None
CLIENT_SECRET = None
REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob"
AUTH_URL = "https://login.procore.com/oauth/authorize"
TOKEN_URL = "https://login.procore.com/oauth/token"
API_BASE_URL = "https://api.procore.com/rest/v1.0"


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
    
    console.print("\n" + "="*60, style="cyan")
    console.print("STEP 1: AUTHENTICATION", style="bold cyan")
    console.print("="*60 + "\n", style="cyan")
    console.print("Opening browser for Procore login...", style="yellow")
    console.print(f"If the browser doesn't open, visit this URL:\n{auth_url_full}\n", style="dim")
    
    # Open browser
    webbrowser.open(auth_url_full)
    
    # Step 2: Get authorization code from user
    console.print("After logging in, you'll receive an authorization code.", style="yellow")
    auth_code = console.input("\n[bold]Paste the authorization code here:[/bold] ").strip()
    
    if not auth_code:
        console.print("[ERROR] Authorization code is required", style="bold red")
        sys.exit(1)
    
    console.print("[OK] Authorization code received", style="bold green")
    
    # Step 3: Exchange authorization code for access token
    console.print("\nExchanging authorization code for access token...", style="yellow")
    
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
        console.print("[OK] Access token obtained successfully\n", style="bold green")
        return access_token
    else:
        console.print(f"[ERROR] Error obtaining access token: {response.status_code}", style="bold red")
        console.print(response.text, style="red")
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
    console.print("\n" + "="*60, style="cyan")
    console.print("STEP 2: SELECT COMPANY", style="bold cyan")
    console.print("="*60 + "\n", style="cyan")
    
    companies = api_request('/companies')
    
    if not companies:
        console.print("[ERROR] No companies found or error fetching companies", style="bold red")
        sys.exit(1)
    
    # Create table
    table = Table(title="Available Companies", box=box.ROUNDED)
    table.add_column("#", style="cyan", justify="right")
    table.add_column("Company Name", style="green")
    table.add_column("ID", style="yellow")
    
    for idx, company in enumerate(companies, 1):
        table.add_row(str(idx), company['name'], str(company['id']))
    
    console.print(table)
    
    while True:
        try:
            choice = console.input("\n[bold]Select company number:[/bold] ")
            company_idx = int(choice) - 1
            if 0 <= company_idx < len(companies):
                selected = companies[company_idx]
                console.print(f"[OK] Selected: {selected['name']}\n", style="bold green")
                return selected['id']
            else:
                console.print("Invalid selection. Please try again.", style="yellow")
        except ValueError:
            console.print("Invalid input. Please enter a number.", style="yellow")


def select_project(company_id):
    """List and select project(s)"""
    console.print("\n" + "="*60, style="cyan")
    console.print("STEP 3: SELECT PROJECT(S)", style="bold cyan")
    console.print("="*60 + "\n", style="cyan")
    
    projects = api_request('/projects', params={'company_id': company_id})
    
    if not projects:
        console.print("[ERROR] No projects found or error fetching projects", style="bold red")
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
        console.print(f"[OK] Project list exported to: {csv_filename}\n", style="bold green")
    except Exception as e:
        console.print(f"[WARNING] Could not export CSV: {e}\n", style="yellow")
    
    # Create table
    table = Table(title="Available Projects", box=box.ROUNDED, show_lines=True)
    table.add_column("#", style="cyan", justify="right")
    table.add_column("Project Name", style="green")
    table.add_column("ID", style="yellow")
    
    for idx, project in enumerate(projects, 1):
        table.add_row(str(idx), project['name'], str(project['id']))
    
    console.print(table)
    
    console.print("\n[bold]Selection options:[/bold]")
    console.print("  - Enter a single number (e.g., '3')")
    console.print("  - Enter multiple numbers separated by commas (e.g., '1,3,5')")
    console.print("  - Enter a range (e.g., '1-5')")
    console.print("  - Enter 'all' to select all projects")
    
    while True:
        try:
            choice = console.input("\n[bold]Select project(s):[/bold] ").strip().lower()
            
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
                    console.print("Invalid range. Please try again.", style="yellow")
                    continue
            elif ',' in choice:
                # Handle comma-separated values (e.g., "1,3,5")
                indices = [int(x.strip()) - 1 for x in choice.split(',')]
                if all(0 <= idx < len(projects) for idx in indices):
                    selected_projects = [projects[idx] for idx in indices]
                else:
                    console.print("Invalid selection. Please try again.", style="yellow")
                    continue
            else:
                # Handle single selection
                project_idx = int(choice) - 1
                if 0 <= project_idx < len(projects):
                    selected_projects = [projects[project_idx]]
                else:
                    console.print("Invalid selection. Please try again.", style="yellow")
                    continue
            
            # Confirm selection
            console.print(f"\n[OK] Selected {len(selected_projects)} project(s):", style="bold green")
            for proj in selected_projects:
                console.print(f"  - {proj['name']}", style="green")
            
            confirm = console.input("\n[bold]Proceed with these projects? (y/n):[/bold] ").strip().lower()
            if confirm == 'y':
                console.print("\n[OK] Starting download process...", style="bold green")
                return selected_projects
            else:
                console.print("\nLet's try again...", style="yellow")
                continue
                
        except ValueError:
            console.print("Invalid input. Please try again.", style="yellow")
        except Exception as e:
            console.print(f"Error: {e}. Please try again.", style="red")


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
    global current_progress
    
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
            if current_progress:
                current_progress.console.print(f"[yellow][WARNING] Rate limit reached. Waiting {retry_after} seconds...[/yellow]")
            log_message(f"  [WARNING] Rate limit reached. Waiting {retry_after} seconds...", to_console=False)
            time.sleep(retry_after)
            return process_folder(folder_id, company_id, project_id, base_path, folder_path)
        
        response.raise_for_status()
        data = response.json()
        
    except requests.exceptions.RequestException as e:
        if current_progress:
            current_progress.console.print(f"[red][ERROR] Error fetching folder: {e}[/red]")
        log_message(f"  [ERROR] Error fetching folder: {e}", to_console=False)
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
                    
                    # Update progress description with current file
                    if current_progress:
                        # Get task ID (should be the first/only task)
                        task_ids = list(current_progress.task_ids)
                        if task_ids:
                            current_progress.update(
                                task_ids[0], 
                                description=f"[cyan]Downloading: {folder_path}/{file_name}[/cyan] | Files: {download_stats['files_downloaded']} | Folders: {download_stats['folders_created']} | Errors: {download_stats['errors']}"
                            )
                    
                    log_message(f"  -> Downloading: {folder_path}/{file_name}", to_console=False)
                    
                    if download_file(download_url, local_file_path):
                        download_stats['files_downloaded'] += 1
                        log_message(f"    [OK] Saved to: {local_file_path}", to_console=False)
                    else:
                        download_stats['errors'] += 1
                        log_message(f"    [ERROR] Failed to download", to_console=False)
                        if current_progress:
                            current_progress.console.print(f"[red]Failed to download: {folder_path}/{file_name}[/red]")
    
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
            
            # Update progress with current folder
            if current_progress:
                task_ids = list(current_progress.task_ids)
                if task_ids:
                    current_progress.update(
                        task_ids[0], 
                        description=f"[yellow]Processing folder: {new_folder_path}[/yellow] | Files: {download_stats['files_downloaded']} | Folders: {download_stats['folders_created']} | Errors: {download_stats['errors']}"
                    )
            
            log_message(f"\n[FOLDER] Processing folder: {new_folder_path}", to_console=False)
            
            # Create local directory
            local_folder_path = os.path.join(base_path, new_folder_path)
            os.makedirs(local_folder_path, exist_ok=True)
            download_stats['folders_created'] += 1
            log_message(f"[FOLDER] Created directory: {local_folder_path}", to_console=False)
            
            # Recursively process subfolder
            process_folder(subfolder_id, company_id, project_id, base_path, new_folder_path)


def download_project_documents(company_id, project_id, project_name):
    """Download all documents from a project"""
    global log_file, download_stats
    
    # Reset stats for this project
    download_stats = {'files_downloaded': 0, 'folders_created': 0, 'errors': 0}
    
    console.print("\n" + "="*60, style="cyan")
    console.print("STEP 4: DOWNLOADING DOCUMENTS", style="bold cyan")
    console.print("="*60 + "\n", style="cyan")
    
    # Create base download directory
    base_path = os.path.join(os.getcwd(), 'procore_downloads', project_name.replace('/', '_'))
    os.makedirs(base_path, exist_ok=True)
    
    # Initialize log file for this project
    log_file = os.path.join(base_path, f"download_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
    
    log_message(f"{'='*60}", to_console=False)
    log_message(f"Download started for project: {project_name}", to_console=False)
    log_message(f"Project ID: {project_id}", to_console=False)
    log_message(f"Company ID: {company_id}", to_console=False)
    log_message(f"Download location: {base_path}", to_console=False)
    log_message(f"{'='*60}\n", to_console=False)
    
    console.print(f"[bold]Download location:[/bold] {base_path}")
    console.print(f"[bold]Log file:[/bold] {log_file}\n")
    
    # Create panel with project info
    info_panel = Panel(
        f"[bold cyan]Project:[/bold cyan] {project_name}\n"
        f"[bold cyan]Project ID:[/bold cyan] {project_id}\n"
        f"[bold cyan]Company ID:[/bold cyan] {company_id}",
        title="[bold]Download Information[/bold]",
        border_style="cyan"
    )
    console.print(info_panel)
    console.print()
    
    # Start time for rate calculation
    start_time = time.time()
    
    # Create progress with live table
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
        transient=False
    ) as progress:
        
        # Add a task for overall progress (indeterminate)
        task = progress.add_task("[cyan]Downloading...", total=None)
        
        # Store progress in global so process_folder can access it
        global current_progress
        current_progress = progress
        
        # Start processing from root folder
        process_folder(None, company_id, project_id, base_path)
        
        # Complete the progress
        progress.update(task, completed=100, total=100)
    
    # Calculate elapsed time
    elapsed_time = time.time() - start_time
    
    log_message(f"\n{'='*60}", to_console=False)
    log_message("[OK] DOWNLOAD COMPLETE", to_console=False)
    log_message(f"{'='*60}", to_console=False)
    log_message(f"Files downloaded: {download_stats['files_downloaded']}", to_console=False)
    log_message(f"Folders created: {download_stats['folders_created']}", to_console=False)
    log_message(f"Errors: {download_stats['errors']}", to_console=False)
    log_message(f"Time elapsed: {elapsed_time:.2f} seconds", to_console=False)
    log_message(f"All files saved to: {base_path}\n", to_console=False)
    
    # Display summary
    console.print()
    
    # Calculate rate
    rate = download_stats['files_downloaded'] / elapsed_time if elapsed_time > 0 else 0
    
    summary_panel = Panel(
        f"[bold green]Files downloaded:[/bold green] {download_stats['files_downloaded']}\n"
        f"[bold yellow]Folders created:[/bold yellow] {download_stats['folders_created']}\n"
        f"[bold red]Errors:[/bold red] {download_stats['errors']}\n"
        f"[bold cyan]Time elapsed:[/bold cyan] {elapsed_time:.2f} seconds\n"
        f"[bold cyan]Download rate:[/bold cyan] {rate:.2f} files/second\n\n"
        f"[bold]Location:[/bold] {base_path}\n"
        f"[bold]Log file:[/bold] {log_file}",
        title="[bold green]Download Complete[/bold green]",
        border_style="green"
    )
    console.print(summary_panel)
    console.print()


def main():
    """Main execution function"""
    global CLIENT_ID, CLIENT_SECRET
    
    # Display banner
    banner = Panel(
        "[bold cyan]PROCORE DOCUMENT DOWNLOADER[/bold cyan]\n"
        "[dim]Download all files from Procore projects while preserving folder structure[/dim]",
        border_style="cyan",
        padding=(1, 2)
    )
    console.print(banner)
    
    # Load environment variables from .env file
    load_dotenv()
    
    # Try to get credentials from environment variables
    CLIENT_ID = os.getenv('PROCORE_CLIENT_ID')
    CLIENT_SECRET = os.getenv('PROCORE_CLIENT_SECRET')
    
    # If not found in .env, prompt user
    if not CLIENT_ID:
        CLIENT_ID = console.input("[bold]Enter your Procore Client ID:[/bold] ").strip()
    else:
        console.print(f"[OK] Client ID loaded from .env file", style="bold green")
    
    if not CLIENT_SECRET:
        CLIENT_SECRET = console.input("[bold]Enter your Procore Client Secret:[/bold] ").strip()
    else:
        console.print(f"[OK] Client Secret loaded from .env file", style="bold green")
    
    if not CLIENT_ID or not CLIENT_SECRET:
        console.print("[ERROR] Client ID and Secret are required", style="bold red")
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
        
        console.print(f"\n{'='*60}", style="magenta")
        console.print(f"PROJECT {idx}/{len(selected_projects)}: {project_name}", style="bold magenta")
        console.print(f"{'='*60}", style="magenta")
        
        download_project_documents(company_id, project_id, project_name)
    
    # Final summary
    console.print(f"\n{'='*60}", style="bold green")
    console.print("ALL PROJECTS COMPLETE", style="bold green")
    console.print(f"{'='*60}", style="bold green")
    console.print(f"\nProcessed {len(selected_projects)} project(s)\n", style="green")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[ERROR] Download cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        sys.exit(1)
