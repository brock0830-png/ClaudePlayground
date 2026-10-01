#!/bin/bash
# Public-link downloads of the client's Sharadar export (Drive "anyone with the link: reader").
mkdir -p "$(dirname "$0")/../data/sharadar" && cd "$(dirname "$0")/../data/sharadar"
get() { curl -sS -L --retry 5 -o "$2" "https://drive.usercontent.google.com/download?id=$1&export=download&confirm=t" && echo "$2 $(stat -c %s "$2") bytes"; }
get 1sIoRRtm5vwpGmrNfA_02wVAywNyhIfzm sp500.csv
get 1lMv8guSjB5egcXVPLFYzgAtLnDIdRExJ events.csv.zip
get 1yH3WwyGxB7651cr_rz57SN1UIYXQGGUC tickers.csv.zip
get 18FPvd3VSjFiwBviRY2o1S67eYaCAOppJ stocks.csv.zip
echo done
