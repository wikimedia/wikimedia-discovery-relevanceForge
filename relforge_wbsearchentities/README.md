Wbsearchentities tuning
=======================

This project implements a tuning process for the wbsearchentities api on www.wikidata.org. It uses historical
click data from WikidataCompletionClicks schema to guide a tuning process that attempts to minimize the
number of characters a user must type to click-through to their desired completion.

Running
=======

# Build the docker container from relforge\_wbsearchentities directory: `docker build -t relforge_wbsearchentities:latest -f Dockerfile ..`

# Connect a tunnel to cloudelastic in a separate shell. Requires wmcloud access.
ssh -N -L 8243:cloudelastic.wikimedia.org:8243 bastion.wmcloud.org

# Run the container for one context. Ssh keys have to be imported to allow connecting to analytics hosts. Host networking is required to connect to the cloudelastic tunnel. In the future the project should likely be re-worked to run from analytics hosts directly instead of this ssh indirection.
```
docker run --rm \
    --network host \
    -v ~/.ssh:/home/wikian/.ssh:ro \
    -v /path/to/store/outputs:/data:rw \
    relforge_wbsearchentities:latest \
    ELASTICSEARCH=https://localhost:8243/ \
    DATASET_YEAR=2022 DATASET_MONTH=3 \
    -j4 report-item_nl
```
