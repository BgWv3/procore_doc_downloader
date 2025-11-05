# Procore Document Downloader

A simple Python script to download all files from a Procore project's documents tool while preserving the original folder structure.

## Features

- ✓ OAuth 2.0 authentication flow with browser-based login
- ✓ Interactive company and project selection
- ✓ Recursive folder traversal
- ✓ Downloads latest version of each file
- ✓ Preserves original folder structure
- ✓ Automatic rate limiting handling
- ✓ Skips deleted files and recycle bin
- ✓ Progress tracking with clear visual feedback

## Prerequisites

- Python 3.6 or higher
- `requests` library

## Installation

1. Install required dependencies:
```bash
pip install requests
```

2. Make the script executable (optional, Linux/Mac):
```bash
chmod +x procore_document_downloader.py
```

## Usage

1. Run the script:
```bash
python3 procore_document_downloader.py
```

2. When prompted, enter your Procore API credentials:
   - Client ID
   - Client Secret

3. Your default browser will open for Procore authentication. Log in with your Procore credentials.

4. After successful authentication, select:
   - Your company from the list
   - Your project from the list

5. The script will begin downloading all documents, preserving the folder structure.

## How It Works

1. **Authentication**: Opens browser for OAuth 2.0 login, captures the authorization code, and exchanges it for an access token.

2. **Company/Project Selection**: Lists available companies and projects for you to choose from.

3. **Recursive Download**: 
   - Starts at the root folder
   - Downloads all files (latest versions only)
   - Recursively processes subfolders
   - Maintains the original directory structure

4. **Rate Limiting**: Automatically detects rate limiting (429 responses) and waits the appropriate time before retrying.

## Output Structure

Files are downloaded to:
```
./procore_downloads/[PROJECT_NAME]/
  ├── Folder1/
  │   ├── file1.pdf
  │   └── Subfolder1/
  │       └── file2.dwg
  └── Folder2/
      └── file3.xlsx
```

## API Endpoints Used

- `GET /rest/v1.0/companies` - List companies
- `GET /rest/v1.0/projects` - List projects
- `GET /rest/v1.0/folders` - Get root folder contents
- `GET /rest/v1.0/folders/{id}` - Get subfolder contents

## Notes

- Only the **latest version** of each file is downloaded
- **Deleted files** and **recycle bin** contents are skipped
- The script uses the `url` attribute from `file_versions` to download files
- Rate limiting is handled automatically with appropriate retry delays
- Files are downloaded with their original names

## Troubleshooting

**Browser doesn't open for authentication:**
- Copy the URL displayed in the terminal and paste it into your browser manually

**Rate limiting errors:**
- The script handles this automatically, but if you see persistent issues, consider adding delays between requests

**Authentication fails:**
- Verify your Client ID and Client Secret are correct
- Ensure your Procore account has access to the API
- Check that the redirect URI (http://localhost:8080/callback) is configured in your Procore API application

**Connection errors:**
- Check your internet connection
- Verify you have access to the Procore project you're trying to download from

## Security Notes

- Never commit your Client ID and Secret to version control
- The access token is stored only in memory during script execution
- Consider using environment variables for credentials in production use

## Future Enhancements

Potential improvements that could be added:
- Resume capability for interrupted downloads
- Parallel downloads for faster performance
- Download specific folders instead of entire project
- Version history downloads (not just latest)
- Download progress bar with size/count statistics
- Configuration file for default settings
- Filter by file type or date range

## License

This script is provided as-is for use with the Procore API.
