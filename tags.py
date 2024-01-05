#!/usr/bin/env python

import asyncio
import logging
import os.path
import sys
import datetime
import os

logging.basicConfig(
    level=logging.DEBUG,
    format="%(levelname)-8s %(name)s - %(message)s",
)

from pypaperless import Paperless  # noqa

tag_list = [
    "tag1",
    "tag2",
    "Larry",
    "new",
    "old",
    "borrowed",
    "blue",
    "this",
    "that",
]

paperless_api_token = os.environ.get("PAPERLESS_API_TOKEN", "MISSING API TOKEN")
paperless_api_host = os.environ.get("PAPERLESS_API_HOST", "MISSING API HOST")

paperless = Paperless(
    paperless_api_host,
    paperless_api_token,
    request_opts={"ssl": False},
)

tag_colors = [
    "#F94144", "#F3722C", "#F8961E", "#F9844A", "#F9C74F", "#90BE6D", "#43AA8B",
    "#4D908E", "#577590", "#277DA1", "#8ecae6", "#219ebc", "#126782", "#023047",
    "#ffb703", "#fd9e02", "#fb8500",
]

def random_color():
    import random
    return random.choice(tag_colors)    

# def get_tags(paperless):
#     """Get all tags."""
#     tags = paperless.tags.iterate()
#     return tags

async def main():
    """Execute main function."""
    names = []
    async with paperless as p:
        async for tag in paperless.tags.iterate():
            print("-------------")
            print(tag.id)  
            print(tag.slug)  
            print(tag.name)  
            print(tag.color)  
            print(tag.text_color)  
            print(tag.is_inbox_tag)  
            print(tag.document_count)
            print(tag.owner)
            print(tag.user_can_change)
            names.append(tag.name.lower())
        
        # for tag in tag_list:
        #     from pypaperless.models import TagPost
        #     if tag.lower() not in names:
        #         print(f"Creating tag {tag}")
        #         new_tag = TagPost(name=tag, color=random_color())
        #         await paperless.tags.create(new_tag)


if __name__ == "__main__":
    asyncio.run(main())