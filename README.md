# flickr_PAD
Flickr personal archive downloader


Flickr.com allows for lots of storage, but downloading your archive is a pain (limited to 500 images in a batch) and useless if you have 10s or 100s of thousands of images.

This python script can be run on your Mac or PC to download all your images and their metadata. 

1. Make sure you have enough local storage.
2. Get your secure keys for API access via https://www.flickr.com/account/sharing  (click "get another key", give your app a name and select "desktop")
3. Configure your settings in the flickr_PAD.py python file
# Configuration
API_KEY = 'your_key'
API_SECRET = 'your_secret'

DOWNLOAD_DIR = Path('/yourFolder/')


## Install notes
# Install Python dependencies (macOS has Python built-in)
pip3 install flickrapi requests


# Run it!
python3 flickr_downloader.py
