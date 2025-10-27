#!/usr/bin/env python3
"""
Run the Python scraper bot
"""
import sys
import os
import asyncio

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scraper.scraper_bot import main

if __name__ == "__main__":
    asyncio.run(main())