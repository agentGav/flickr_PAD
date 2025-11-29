#!/usr/bin/env python3
"""
Flickr Library Downloader
Downloads entire private Flickr library with metadata including tags and comments
Handles 100,000+ photos with resume capability
"""

import os
import sys
import json
import time
import requests
import flickrapi
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
import re

# Configuration
API_KEY = 'YOUR_KEY'
API_SECRET = 'YOUR_SECRET'

DOWNLOAD_DIR = Path('/YOURFOLDERPATH/')
METADATA_DIR = DOWNLOAD_DIR / 'metadata'
PHOTOS_DIR = DOWNLOAD_DIR / 'photos'
LOG_FILE = DOWNLOAD_DIR / 'download.log'
STATE_FILE = DOWNLOAD_DIR / '.download_state.json'

# Create directories
DOWNLOAD_DIR.mkdir(exist_ok=True)
METADATA_DIR.mkdir(exist_ok=True)
PHOTOS_DIR.mkdir(exist_ok=True)


class FlickrDownloader:
    def __init__(self):
        self.flickr = None
        self.user_id = None
        self.stats = {
            'downloaded': 0,
            'failed': 0,
            'skipped': 0,
            'total': 0
        }
        
    def log(self, message):
        """Log message to console and file"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_msg = f"[{timestamp}] {message}"
        print(log_msg)
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_msg + '\n')
    
    def authenticate(self):
        """Authenticate with Flickr using OAuth"""
        self.log("Authenticating with Flickr...")
        
        self.flickr = flickrapi.FlickrAPI(
            API_KEY, 
            API_SECRET, 
            format='parsed-json'
        )
        
        # Check if we have cached credentials
        if not self.flickr.token_valid(perms='read'):
            self.log("No valid token found. Opening browser for authentication...")
            self.flickr.authenticate_via_browser(perms='read')
        
        self.log("Authentication successful!")
        
        # Get user ID
        user_info = self.flickr.test.login()
        self.user_id = user_info['user']['id']
        username = user_info['user']['username']['_content']
        self.log(f"Logged in as: {username} (ID: {self.user_id})")
    
    def sanitize_filename(self, filename):
        """Create safe filename"""
        # Remove or replace invalid characters
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        # Limit length
        filename = filename[:200]
        return filename
    
    def load_state(self):
        """Load download state from file"""
        if STATE_FILE.exists():
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        return {'last_page': 0, 'downloaded': [], 'failed': []}
    
    def save_state(self, state):
        """Save download state to file"""
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
    
    def get_photo_metadata(self, photo_id):
        """Get complete metadata for a photo"""
        metadata = {}
        
        try:
            # Get photo info (includes tags)
            info = self.flickr.photos.getInfo(photo_id=photo_id)
            metadata['info'] = info
            
            # Get EXIF data
            try:
                exif = self.flickr.photos.getExif(photo_id=photo_id)
                metadata['exif'] = exif
            except flickrapi.exceptions.FlickrError as e:
                if 'not found' not in str(e).lower():
                    self.log(f"Warning: Could not get EXIF for {photo_id}: {e}")
                metadata['exif'] = None
            
            # Get comments
            try:
                comments = self.flickr.photos.comments.getList(photo_id=photo_id)
                metadata['comments'] = comments
            except flickrapi.exceptions.FlickrError as e:
                if 'not found' not in str(e).lower():
                    self.log(f"Warning: Could not get comments for {photo_id}: {e}")
                metadata['comments'] = None
            
            return metadata
            
        except Exception as e:
            self.log(f"Error getting metadata for {photo_id}: {e}")
            return None
    
    def save_metadata(self, photo_id, metadata):
        """Save metadata to JSON file"""
        metadata_file = METADATA_DIR / f"{photo_id}.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    def download_photo(self, photo_id, url, filename):
        """Download a photo from URL"""
        filepath = PHOTOS_DIR / filename
        
        # Skip if already exists
        if filepath.exists():
            self.log(f"Skipping existing: {filename}")
            self.stats['skipped'] += 1
            return True
        
        try:
            self.log(f"Downloading: {filename}")
            response = requests.get(url, stream=True, timeout=60)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            self.log(f"Success: {filename}")
            self.stats['downloaded'] += 1
            return True
            
        except Exception as e:
            self.log(f"ERROR: Failed to download {filename}: {e}")
            self.stats['failed'] += 1
            return False
    
    def get_download_url(self, photo_info):
        """Get best available download URL for photo"""
        photo = photo_info['photo']
        
        # Try to get original first, then fall back to large sizes
        url_keys = ['url_o', 'url_k', 'url_h', 'url_l', 'url_c']
        
        for key in url_keys:
            if key in photo:
                return photo[key]
        
        # Fallback: construct URL from photo info
        if 'urls' in photo and 'url' in photo['urls']:
            urls = photo['urls']['url']
            if isinstance(urls, list) and len(urls) > 0:
                return urls[0]['_content']
        
        return None
    
    def get_file_extension(self, photo_info):
        """Get file extension from photo info"""
        photo = photo_info['photo']
        
        # Try original format first
        if 'originalformat' in photo:
            return photo['originalformat']
        
        # Check media type
        if 'media' in photo and photo['media'] == 'video':
            return 'mp4'
        
        # Default to jpg
        return 'jpg'
    
    def download_library(self):
        """Main download function"""
        self.log("=" * 80)
        self.log("Starting Flickr library download")
        self.log(f"Target directory: {DOWNLOAD_DIR}")
        self.log("=" * 80)
        
        # Load previous state
        state = self.load_state()
        start_page = state['last_page'] + 1
        
        if start_page > 1:
            self.log(f"Resuming from page {start_page}")
            self.log(f"Previously downloaded: {len(state['downloaded'])} photos")
        
        # Get total photo count
        self.log("Fetching photo list...")
        
        first_page = self.flickr.people.getPhotos(
            user_id=self.user_id,
            extras='description,license,date_upload,date_taken,owner_name,icon_server,original_format,last_update,geo,tags,machine_tags,o_dims,views,media,path_alias,url_o,url_k,url_h,url_l,url_c',
            per_page=500,
            page=1
        )
        
        total_photos = int(first_page['photos']['total'])
        total_pages = int(first_page['photos']['pages'])
        
        self.log(f"Total photos: {total_photos:,}")
        self.log(f"Total pages: {total_pages:,}")
        self.stats['total'] = total_photos
        
        # Download photos page by page
        for page in range(start_page, total_pages + 1):
            self.log("-" * 80)
            self.log(f"Processing page {page} of {total_pages}")
            
            try:
                # Get photos for this page
                if page == 1 and start_page == 1:
                    page_data = first_page
                else:
                    page_data = self.flickr.people.getPhotos(
                        user_id=self.user_id,
                        extras='description,license,date_upload,date_taken,owner_name,icon_server,original_format,last_update,geo,tags,machine_tags,o_dims,views,media,path_alias,url_o,url_k,url_h,url_l,url_c',
                        per_page=500,
                        page=page
                    )
                
                photos = page_data['photos']['photo']
                self.log(f"Found {len(photos)} photos on this page")
                
                # Process each photo
                for i, photo in enumerate(photos, 1):
                    photo_id = photo['id']
                    title = photo.get('title', 'untitled')
                    
                    # Skip if already processed
                    if photo_id in state['downloaded']:
                        self.log(f"Skipping already processed photo: {photo_id}")
                        continue
                    
                    progress = len(state['downloaded']) + i
                    self.log(f"\nPhoto {progress}/{total_photos}: {photo_id} - {title}")
                    
                    # Get complete metadata
                    metadata = self.get_photo_metadata(photo_id)
                    if metadata:
                        metadata['list_info'] = photo  # Include list data
                        self.save_metadata(photo_id, metadata)
                    else:
                        self.log(f"Warning: Could not get metadata for {photo_id}")
                    
                    # Get download URL
                    url = self.get_download_url({'photo': photo})
                    
                    if url:
                        # Create filename
                        safe_title = self.sanitize_filename(title)
                        extension = self.get_file_extension({'photo': photo})
                        filename = f"{photo_id}_{safe_title}.{extension}"
                        
                        # Download photo
                        success = self.download_photo(photo_id, url, filename)
                        
                        if success or PHOTOS_DIR.joinpath(filename).exists():
                            state['downloaded'].append(photo_id)
                        else:
                            state['failed'].append(photo_id)
                    else:
                        self.log(f"Warning: No download URL found for {photo_id}")
                        state['failed'].append(photo_id)
                    
                    # Save state after each photo
                    state['last_page'] = page
                    self.save_state(state)
                    
                    # Rate limiting
                    time.sleep(0.5)
                
                # Page complete
                self.log(f"\nPage {page} complete")
                self.log(f"Downloaded: {self.stats['downloaded']}, Skipped: {self.stats['skipped']}, Failed: {self.stats['failed']}")
                
            except Exception as e:
                self.log(f"ERROR on page {page}: {e}")
                self.log("Saving state and continuing...")
                state['last_page'] = page - 1
                self.save_state(state)
                time.sleep(5)
                continue
        
        # Final summary
        self.log("\n" + "=" * 80)
        self.log("Download complete!")
        self.log(f"Total photos: {self.stats['total']:,}")
        self.log(f"Successfully downloaded: {self.stats['downloaded']:,}")
        self.log(f"Skipped (already existed): {self.stats['skipped']:,}")
        self.log(f"Failed: {self.stats['failed']:,}")
        self.log(f"Photos saved to: {PHOTOS_DIR}")
        self.log(f"Metadata saved to: {METADATA_DIR}")
        self.log("=" * 80)


def main():
    """Main entry point"""
    # Check API credentials
    if API_KEY == 'YOUR_API_KEY_HERE' or API_SECRET == 'YOUR_API_SECRET_HERE':
        print("ERROR: Please set your API_KEY and API_SECRET in the script")
        print("\nGet your API credentials at:")
        print("https://www.flickr.com/services/apps/create/apply/")
        sys.exit(1)
    
    # Check dependencies
    try:
        import flickrapi
        import requests
    except ImportError as e:
        print(f"ERROR: Missing required library: {e}")
        print("\nInstall dependencies with:")
        print("pip install flickrapi requests")
        sys.exit(1)
    
    # Create downloader and run
    downloader = FlickrDownloader()
    
    try:
        downloader.authenticate()
        downloader.download_library()
    except KeyboardInterrupt:
        downloader.log("\n\nInterrupted by user. Progress has been saved.")
        downloader.log("Run the script again to resume from where you left off.")
        sys.exit(0)
    except Exception as e:
        downloader.log(f"\n\nFATAL ERROR: {e}")
        import traceback
        downloader.log(traceback.format_exc())
        sys.exit(1)


if __name__ == '__main__':
    main()
