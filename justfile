set dotenv-load

default:
  @just --list

list_tags:
	op run ./tags.py

import *FILES:
	op run ./e2p.py {{FILES}}

