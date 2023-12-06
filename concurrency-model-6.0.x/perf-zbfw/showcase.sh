#!/bin/sh
GREEN='\033[0;32m'
NC='\033[0m' # No Color

printf "\n\n${GREEN}##### Showcase: Service mapping with 100 zone-pairs in 5 transactions = 500 zone-pairs\n${NC}"
make stop clean NDEVS=1 parallel start; python3 measure.py --ntrans 5 --nzones 100 --cqparam sync

printf "\n\n${GREEN}##### Showcase: Service mapping with a single transaction of 500 zone-pairs\n${NC}"
make stop clean NDEVS=1 parallel start; python3 measure.py --ntrans 0 --nzones 500 --cqparam bypass

printf "\n\n${GREEN}##### Showcase: Service mapping simulating pre-6.0 behavior with 100 zone-pairs in 5 transactions\n${NC}"
make stop clean NDEVS=1 serial start; python3 measure.py --ntrans 5 --nzones 100 --cqparam async

printf "\n\n${GREEN}##### Showcase done\n${NC}"
