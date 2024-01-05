#!/usr/bin/env python

import asyncio
import os.path
import sys
import datetime
import time
from base64 import b64decode
import hashlib
from lxml import etree
from io import BytesIO
import os
from time import strptime
from pprint import pprint

from pypaperless import Paperless  # noqa
from pypandoc import convert_text

# Set dry_run to True to skip the actual import
dry_run = False
# Set import_tag to the tag that will be added to all imported documents
import_tag = 'e2p'

# Set paperless_api_token and paperless_api_host to the values for your paperless-ngx instance
paperless_api_token = os.environ.get("PAPERLESS_API_TOKEN", "MISSING API TOKEN")
# PAPERLESS_API_HOST should be the URL of your paperless-ngx instance,
# including the port if needed, eg. myserver.example.com:8000
paperless_api_host = os.environ.get("PAPERLESS_API_HOST", "MISSING API HOST")

def get_paperless(): 
    return Paperless(
        paperless_api_host,
        paperless_api_token,
        request_opts={"ssl": False},
    )

# A pool of colors for making new tags
tag_colors = [
    "#F94144", "#F3722C", "#F8961E", "#F9844A", "#F9C74F", "#90BE6D", "#43AA8B",
    "#4D908E", "#577590", "#277DA1", "#8ecae6", "#219ebc", "#126782", "#023047",
    "#ffb703", "#fd9e02", "#fb8500",
]

# A list of resource types that are not supported by paperless-ngx
unsupported_resources = [
    'application/x-zip-compressed',
    'application/x-iwork-keynote-sffkey',
    'application/x-iwork-pages-sffpages',
    'application/x-iwork-numbers-sffnumbers',
    'application/zip',
    'application/octet-stream',
]

parse_date_format = '%Y-%m-%dT%H:%M:%S.%fZ'
generate_date_format = '%Y-%m-%dT%H:%M:%S.000Z'

# Global list of tags
tags = []

def random_color():
    import random
    return random.choice(tag_colors)    

def check_files(files):
    input_files = []
    for file in files:
        if os.path.isfile(file):
            input_files.append(file)
        else:
            print(f"File {file} does not exist")
    return input_files    

async def get_tags():
    """Get all tags."""
    async with get_paperless() as p:
        global tags
        tags = []
        async for tag in p.tags.iterate():
            tags.append(tag)
        # print("Got tags:", tags)

async def create_tag(tag):
    """Create a tag."""
    from pypaperless.models import TagPost

    tag_names = list(map(lambda x: x.name.lower(), tags))

    # print("Existing tags:", tag_names)
    # print("Checking if tag", tag.lower(), "is in", tag_names)
    if tag.lower() not in tag_names:
        async with get_paperless() as p:
            new_tag = TagPost(name=tag.lower(), color=random_color())
            print("Creating tag with name", tag.lower())
            await p.tags.create(new_tag)
        await get_tags()

async def save_resource_paperless(resource, note):
    """Save resource to paperless-ng."""
    from pypaperless.models import DocumentPost, DocumentNotePost
    from pypaperless.models.shared import TaskStatus

    if resource['mime'] in unsupported_resources:
        print("Skipping unsupported resource type", resource['mime'])
        return

    for tag in note['tags']:
        await create_tag(tag)
    
    tag_ids = []
    for tag in note['tags']:
        for t in tags:
            if t.name.lower() == tag.lower():
                tag_ids.append(t.id)
                break

    async with get_paperless() as p:
        if not dry_run:
            ctime = time.strftime(generate_date_format, note['created'])
            new_document = DocumentPost(
                document=resource['data'], 
                title=note['title'], 
                created=ctime,
                tags=tag_ids 
                )
            task_id = await p.documents.create(new_document)

            task = await p.tasks.one(task_id)

            doc_note = note.get('content', '').strip()
            if doc_note == '':      # bail out if there's no content
                return 

            print("Found document note:", doc_note)

            print("Waiting for document ingestion.", end="", flush=True)
            while task.status != TaskStatus.SUCCESS:
                if task.status == TaskStatus.FAILURE:
                    print("Task failed:", task.result)
                    return
                await asyncio.sleep(1)
                task = await p.tasks.one(task_id)
                print(".", end="", flush=True)

            print("\n", end="", flush=True)

            doc_id = task.related_document
            new_note = DocumentNotePost(
                note = doc_note,
                document = doc_id,
            )
            await p.documents.notes.create(new_note)            

def parse_content(content):
    text = convert_text(content, 'org', format='html')
    return text

def parse_resource(resource):
    rsc_dict = {}
    for elem in resource:
        if elem.tag == 'data':
            # Some times elem.text is None
            rsc_dict[elem.tag] = b64decode(elem.text) if elem.text else b''
            rsc_dict['hash'] = hashlib.md5(rsc_dict[elem.tag]).hexdigest()
        elif elem.tag == 'resource-attributes':
            for attr in elem:
                rsc_dict[attr.tag] = attr.text
        else:
            rsc_dict[elem.tag] = elem.text

    return rsc_dict

async def parse_note(note, file_tag):
    note_dict = {}
    resources = []
    tags = [import_tag, file_tag]
    for elem in note:
        if elem.tag == 'content':
            note_dict[elem.tag] = parse_content(elem.text)
            # A copy of original content
            note_dict['content-raw'] = elem.text
        elif elem.tag == 'resource':
            resources.append(parse_resource(elem))
        elif elem.tag == 'tag':
            tags.append(elem.text)
        elif elem.tag == 'created' or elem.tag == 'updated':
            note_dict[elem.tag] = strptime(elem.text, parse_date_format)
        else:
            note_dict[elem.tag] = elem.text

    note_dict['resource'] = resources
    note_dict['tags'] = tags

    print("-------------")
    print("Note dict:")
    from copy import deepcopy
    printme = deepcopy(note_dict)
    for rsrc in printme['resource']:
        rsrc['data'] = "...data not printed..."
        if 'recognition' in rsrc:
            rsrc['recognition'] = "...recognition not printed..."
    if 'content-raw' in printme:
        printme['content-raw'] = "...raw content not printed..."
    pprint(printme)

    if resources != []:
        for resource in resources:
            await save_resource_paperless(resource, note_dict)
    else:
        print("No resources found, skipping document import.")
        

async def import_file(file):
    print(f"Importing {file}")

    file_tag = os.path.splitext(os.path.basename(file))[0].lower()

    context = etree.iterparse(file, encoding='utf-8', strip_cdata=False, huge_tree=True, recover=True)
    for action, elem in context:
        if elem.tag == "note":
            await parse_note(elem, file_tag)

async def main(argv=None):

    input_files = check_files(argv[1:])

    if len(input_files) == 0:
        print("No files to import")
        return
    
    print("Preparing to import files:")       
    for file in input_files:
        print(file)

    # prime the list of existing tags from paperless
    await get_tags()
    await create_tag(import_tag)

    for file in input_files:
        await import_file(file)    


    # sys.exit(0)

    # names = []
    # async with paperless as p:
    #     async for tag in paperless.tags.iterate():
    #         print("-------------")
    #         print(tag.id)  
    #         print(tag.slug)  
    #         print(tag.name)  
    #         print(tag.color)  
    #         print(tag.text_color)  
    #         print(tag.is_inbox_tag)  
    #         print(tag.document_count)
    #         print(tag.owner)
    #         print(tag.user_can_change)
    #         names.append(tag.name.lower())

    #     for tag in tag_list:
    #         from pypaperless.models import TagPost
    #         if tag.lower() not in names:
    #             print(f"Creating tag {tag}")
    #             new_tag = TagPost(name=tag, color=random_color())
    #             await paperless.tags.create(new_tag)


if __name__ == "__main__":
    asyncio.run(main(sys.argv))