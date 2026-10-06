#!/usr/bin/env python3

import sys
import signal
import logging
import urllib.parse
import csv
import os
import json
import xml.etree.ElementTree as ET
import argparse
import requests
import time
from datetime import datetime, timezone

SN_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

log = logging.getLogger()

class Config:
    def __init__(self):
        self.auth_type = ""
        self.auth_username = ""
        self.auth_password = ""
        self.auth_cookies = ""
        self.instance_url = ""
        self.export_type = "CSV"
        self.page_size = 1000
        self.export_table = ""
        self.export_query = ""
        self.temp_dir = os.path.join(".", "tmp")
        self.export_fields = "*"
        self.out_file = ""
        self.display_values = True
        self.min_rows = 0
        self.delta_timestamp = ""
        self.delta_timestamp_file = ""
        self.output_timestamp = False
        self.work_dir = "./"


config = Config()

def debugConfig():
    log.debug("{0}={1}".format("auth_type", config.auth_type))
    log.debug("{0}={1}".format("auth_username", config.auth_username))
    log.debug("{0}={1}".format("auth_cookies", config.auth_cookies))
    log.debug("{0}={1}".format("instance_url", config.instance_url))
    log.debug("{0}={1}".format("export_type", config.export_type))
    log.debug("{0}={1}".format("page_size", config.page_size))
    log.debug("{0}={1}".format("export_table", config.export_table))
    log.debug("{0}={1}".format("temp_dir", config.temp_dir))
    log.debug("{0}={1}".format("export_fields", config.export_fields))
    log.debug("{0}={1}".format("out_file", config.out_file))
    log.debug("{0}={1}".format("display_values", config.display_values))
    log.debug("{0}={1}".format("min_rows", config.min_rows))
    log.debug("{0}={1}".format("delta_timestamp", config.delta_timestamp))
    log.debug("{0}={1}".format("delta_timestamp_file", config.delta_timestamp_file))
    log.debug("{0}={1}".format("output_timestamp", config.output_timestamp))
    log.debug("{0}={1}".format("work_dir", config.work_dir))


def loadConfigFile(fname: str, config: Config):
    """
    Load a configuration from file.
    """

    log.debug("Loading config file {0}".format(fname))
    with open(fname) as f:
        fData = json.load(f)

        if ("auth_type" in fData): config.auth_type = fData["auth_type"]
        if ("auth_username" in fData): config.auth_username = fData["auth_username"]
        if ("auth_password" in fData): config.auth_password = fData["auth_password"]
        if ("auth_cookies" in fData): config.auth_cookies = fData["auth_cookies"]
        if ("instance_url" in fData): config.instance_url = fData["instance_url"]
        if ("export_type" in fData): config.export_type = fData["export_type"]
        if ("page_size" in fData): config.page_size = int(fData["page_size"])
        if ("export_table" in fData): config.export_table = fData["export_table"]
        if ("export_query" in fData): config.export_query = fData["export_query"]
        if ("export_fields" in fData): config.export_fields = fData["export_fields"]
        if ("out_file" in fData): config.out_file = fData["out_file"]
        if ("display_values" in fData): config.display_values = bool(fData["display_values"])
        if ("min_rows" in fData): config.min_rows = bool(fData["min_rows"])
        if ("delta_timestamp" in fData): config.delta_timestamp = fData["delta_timestamp"]
        if ("delta_timestamp_file" in fData): config.delta_timestamp_file = fData["delta_timestamp_file"]
        if ("output_timestamp" in fData): config.output_timestamp = bool(fData["output_timestamp"])

class ExportResult:
    def __init__(self):
        self.pages = []

def getUrl(root:str, path:str, parms={}) -> str:
    """
    Build a URL from a root, the path, and URL query parameters (optional).
    """

    url = "{0}".format(root)
    if (not url.startswith("http://") or not url.startswith("https://")):
        url = "https://{0}".format(url)

    urlParms = ""
    if len(parms) > 0:
        urlParms = "?"+urllib.parse.urlencode(parms)
    url = "{0}/{1}{2}".format(url, path, urlParms)

    return url



def tryLoginDo(session: requests.Session):
    """
    Try to login using basic auth credentials using login.do.
    """
    #Post to login.do

    # Success: a 302 redirect
    # Fail: a 200 refresh of the login page

    log.debug("Attempting login.do")

    url = getUrl(config.instance_url, "login.do")
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept":"*/*"
    }
    body = {
        "sys_action":"sysverb_login",
        "user_name":config.auth_username,
        "user_password":config.auth_password
    }

    response = session.post(url, headers=headers, data=body, allow_redirects=False)

    sessionCookie = session.cookies.get("JSESSIONID")
    if (response.status_code == 302):
        if (sessionCookie):
            log.debug("Session opened: {0}".format(sessionCookie))
        else:
            raise Exception("Login successful, but didn't get a session cookie")

        # Success
        return
    
    else:
        # Likely a fail
        raise Exception("Login attempt failed {0} {1}".format(response.status_code))

def requestCsv(session: requests.Session, offset=0, last_sysid=None):
    """
    Fetch an export of data from ServiceNow as CSV.
    """

    query = config.export_query
    # TODO detect and throw exception if there's complexities in query that may cause issues 
    # with this script auto-inserting the sys_id query
    # ^NQ for multiple queries in 1
    # ^ORDERBY for setting the order

    if (last_sysid):
        query = "sys_id>{0}^{1}".format(last_sysid, query)



    log.info("Exporting data, table: {0}, offset: {1}, rows: {2}, query: {3}".format(config.export_table, offset, config.page_size, query))

    urlParms = {
        "CSV":"",
        "sysparm_query":query,
        "sysparm_orderby":"sys_id", # always order by sys_id, we use this for fetching in chunks
        "sysparm_record_count":config.page_size,
        "sysparm_display_value": config.display_values
    }
    if config.export_fields == "*":
        urlParms["sysparm_default_export_fields"] = "all"
    else:
        # Always include sys_id
        fieldList = config.export_fields.split(",")
        if not "sys_id" in fieldList: 
            log.debug("Adding sys_id to field list")
            fieldList.append("sys_id")
        urlParms["sysparm_fields"] = ",".join(fieldList)

    url = getUrl(config.instance_url, "{0}_list.do".format(config.export_table), urlParms)
    
    headers = {
        "Accept": "text/csv"
    }
    
    response = session.get(url, headers=headers)
    response.raise_for_status()

    log.debug("Response\n{0}".format(response.text))

    return response.text

def exportCsv(session: requests.Session) -> ExportResult:
    """
    Export and save data from ServiceNow as CSV.
    """

    # Get the export
    pageNum = 0
    lastSysId = ""
    totalRowCount = 0

    exportResult = ExportResult()
    
    while True:
        log.info("Fetching page {0}".format(pageNum))
        csvText = requestCsv(session, offset=pageNum*config.page_size, last_sysid=lastSysId)

        # Check how many rows there are
        # If it's just the header row and nothing else, there's no data.
        # Sadly, can't use python's CSV module for this, it's got issues reading from strings instead of files.
        newLineCount = csvText.count("\n")
        if (newLineCount < 2):
            log.debug("CSV has no rows of data")
            if (config.min_rows > 0):
                _offsetPlus1Page = (pageNum+1) * config.page_size
                log.debug("Attempted export of {0} / min_rows {1}".format(_offsetPlus1Page, config.min_rows))

                if (config.min_rows > 0 and _offsetPlus1Page < config.min_rows):
                    log.debug("Continuing export")
                else:
                    log.debug("Reached end of export")
                    return exportResult
                
            else:
                log.debug("Reached end of export")
                return exportResult

        fname = os.path.join(config.temp_dir, "page_{0}.csv".format(pageNum))
        log.debug("Writing to {0}".format(fname))
        with open(fname, "w") as f:
            f.write(csvText)
        exportResult.pages.append(fname)

        # Read the CSV
        # Try to read to get the last sys_id

        # This is really stupid, but Python CSV works better with files than strings.
        # Otherwise, I was getting issues where the row would only have the 1st cell, not the whole row.
        # Getting the next row would return 2 empty cells, then the next 1 cell. 
        # I suspect it's having issues with every cell in quotation.
        # This feels dumb, needing to save it out of memory, only to read it from the file again, but it works.
        with open(fname, "r", newline="") as f:
            csvReader = csv.reader(f, csv.unix_dialect)
            #csvReader = csv.reader(csvText, csv.unix_dialect)
            
            rowCount = 0

            # Read the 1st row, should be the column headers. Look for "sys_id".
            csvRow1 = next(csvReader)
            log.debug("CSV headers: {0}".format(", ".join(csvRow1)))
            
            sysIdColNum = -1
            try:
                sysIdColNum = csvRow1.index("sys_id")
            except ValueError as ex:
                raise ValueError("CSV header doesn't contain column for sys_id")

            for line in csvReader:
                lastSysId = line[sysIdColNum]
                rowCount = rowCount + 1

            log.debug("Last sys_id: {0}".format(lastSysId))
            log.debug("{0} rows of data in CSV".format(rowCount))
            totalRowCount = totalRowCount + rowCount
        
        # End of page
        pageNum = pageNum + 1
    
def combineCsvFiles(outFileName:str, files:list):
    """
    Combine multiple CSV files into one CSV file.
    """

    log.debug("Writing output to file: {0}".format(outFileName))
    if (len(files) < 1): raise Exception("No files to combine")

    with open(outFileName, "w") as outFile:
        is1stFile=True
        for inFileName in files:
            log.debug("Combining file {0}".format(inFileName))
            with open(inFileName, "r") as inFile:
                if is1stFile:
                    # This is the 1st file.
                    # Copy everything, including the header
                    is1stFile = False
                else:
                    # Not the 1st file
                    # Skip the header
                    inFile.readline() # Read past the 1st line
                
                for data in inFile.read():
                    outFile.write(data)

    log.debug("Finished writing to {0}".format(outFileName))

def getTimestampFromFile():
    """
    Get the delta timestamp from a file, add it to the config.
    """

    fname = config.delta_timestamp_file
    log.debug("Fetching delta timestamp from file {0}".format(fname))
    if not os.path.exists(fname):
        log.warning("Timestamp file doesn't exist: {0}. Ignoring delta timestamp.".format(fname))
        return
    
    with open(config.delta_timestamp_file, "r") as f:
        timestamp = f.readline().strip()
        log.info("Delta timestamp read from file: {0}".format(timestamp))
        if (not timestamp):
            log.info("Delta timestamp is empty, ignoring delta timestamp")
            return

        config.delta_timestamp = timestamp
        return

def outputTimestampToFile():
    """
    Output a delta timestamp to the configured file.
    """

    now = datetime.now(timezone.utc)
    timestamp = now.strftime(SN_DATETIME_FORMAT)
    log.info("Saving timestamp {0} to file: {1}".format(timestamp, config.delta_timestamp_file))
    with open(config.delta_timestamp_file, "w") as f:
        f.write(timestamp)
    
def validateTimestamp(timestamp):
    """
    Validate that the delta timestamp is in the correct SN format.
    """

    #Just try to read the timestamp. It'll either work, or throw a ValueError.
    log.debug("Validating delta timestamp: {0}".format(config.delta_timestamp))
    datetime.strptime(timestamp, SN_DATETIME_FORMAT)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--auth-type", "-a", choices=["none", "basic", "session"], help="Type of authentication to use.")
    parser.add_argument("--auth-username", "-au", help="Username to authenticate with.")
    parser.add_argument("--auth-password", "-ap", help="Password to authenticate with.")
    parser.add_argument("--auth-cookies", "-ac", help="When using session auth, the cookies to use, semi-colon separated key-value.")
    parser.add_argument("--instance-url", "-i", help="Base URL of the SN instance. E.g. myinstance.service-now.com")
    parser.add_argument("--verbose", "-v", action="store_true", default=False, help="Enable verbose logging.")
    parser.add_argument("--config", "-c", help="Load config from config file.")
    parser.add_argument("--export-type", "-e", choices=["csv"], help="Type of export.")
    parser.add_argument("--export-table", "-t", help="Name of the table to export data from.")
    parser.add_argument("--page-size", "-s", type=int, help="How many rows to export per page.")
    parser.add_argument("--export-query", "-q", help="Query to use when exporting data.")
    parser.add_argument("--temp-dir", "-T", help="Directory to save temporary files to.")
    parser.add_argument("--export-fields", "-f", help="List of fields to export, comma-separated, or '*' for all fields.")
    parser.add_argument("--out", "-o", help="File to output the export to.")
    parser.add_argument("--display-values", "-d", help="Enable display values when exporting data.")
    parser.add_argument("--no-display-values", "-D", help="Disable display values when exporting data.")
    parser.add_argument("--min-rows", "-m", type=int, help="The minimum amount of rows to export. Useful when there's lots of data 'hidden for security reasons' and may result in an empty page of data. If not provided, export will end on the 1st empty page of data.")
    parser.add_argument("--delta-timestamp", "-x", help="Add a sys_updated_on query to only export data updated after the given timestamp. Must be correctly formatted UTC timestamp YYYY-MM-DD HH:MM:SS.")
    parser.add_argument("--delta-timestamp-file", "-X", help="Similar to delta-timestamp, but read from a file.")
    parser.add_argument("--output-timestamp", "-XO", action="store_true", help="When the export is completed, a timestamp will be written to the given file.")
    args = parser.parse_args()

    logging.basicConfig(filename=None, level=args.verbose and logging.DEBUG or logging.INFO)

    if (args.config):
        loadConfigFile(args.config, config)

    if (args.auth_type): config.auth_type = args.auth_type
    if (args.auth_username): config.auth_username = args.auth_username
    if (args.auth_password): config.auth_password = args.auth_password 
    if (args.auth_password): config.auth_cookies = args.auth_cookies
    if (args.instance_url): config.instance_url = args.instance_url 
    if (args.export_type): config.export_type = args.export_type 
    if (args.page_size): config.page_size = args.page_size 
    if (args.export_table): config.export_table = args.export_table 
    if (args.export_query): config.export_query = args.export_query
    if (args.temp_dir): config.temp_dir = args.temp_dir
    if (args.export_fields): config.export_fields = args.export_fields
    if (args.out): config.out_file = args.out
    if (args.display_values): config.display_values = True
    if (args.no_display_values): config.display_values = False
    if (args.min_rows): config.min_rows = args.min_rows
    if (args.delta_timestamp): config.delta_timestamp = args.delta_timestamp
    if (args.delta_timestamp_file): config.delta_timestamp_file = args.delta_timestamp_file
    if (args.output_timestamp): config.output_timestamp = args.output_timestamp

    debugConfig()

    # Check the config
    if (not config.instance_url): raise ValueError("instance_url cannot be empty")
    if (not config.export_table): raise ValueError("export_table cannot be empty")
    if (config.page_size < 1): raise ValueError("page_size cannot be less than 1")
    if (not config.export_fields): raise ValueError("export_fields cannot be empty")
    if (not config.out_file): raise ValueError("out_file cannot be empty")
    if (config.min_rows < 0): raise ValueError("min_rows must be a number above zero, or zero to end on the 1st empty page")
    if (config.output_timestamp and not config.delta_timestamp_file): raise ValueError("delta_timestamp_file must be provided when using output_timestamp")

    try:
        startTime = time.time()

        # Read the delta timestamp if needed
        if (config.delta_timestamp_file):
            getTimestampFromFile()

        if (config.delta_timestamp):
            validateTimestamp(config.delta_timestamp)
            config.export_query = "sys_updated_on>={0}".format(config.delta_timestamp) + "^" + config.export_query
            log.debug("Appended delta timestamp to query: {0}".format(config.export_query))
        else:
            log.debug("No delta timestamp")

        # Create temp dir if missing
        if not os.path.exists(config.temp_dir):
            os.makedirs(config.temp_dir, exist_ok=True)

        session = requests.Session()
        log.debug("Auth type: {0}".format(config.auth_type))
        if config.auth_type == "none":
            log.debug("Not trying to authenticate")

        if config.auth_type == "basic":
            # Try to log in to start a session
            if (not config.auth_username): raise ValueError("auth_username cannot be empty in basic auth")
            if (not config.auth_password): raise ValueError("auth_password cannot be empty in basic auth")
            tryLoginDo(session)
        
        if config.auth_type == "session":
            # Just add the session token to the session cookies
            
            if (not config.auth_cookies): raise ValueError("auth_cookies cannot be empty in session auth")

            # WARNING: will encounter issues if cookie contains = or ;. 
            # However, this is a known issue, and it's frowned upon for cookies to have these values anyway.
            log.debug("Adding session token to cookies")
            for cookie in config.auth_cookies.split(";"):
                eqIndex = cookie.find("=") # Find the first = sign
                if eqIndex == -1:
                    # Equals not found. What?
                    logging.warning("Cookie pair doesn't contain equals. Skipping line. Cookie: {0}".format(cookie))

                cookieName = cookie[:eqIndex] # Before the equals
                cookieVal = cookie[eqIndex+1:] # After the equals
                session.cookies.set(name=cookieName, value=cookieVal, domain=config.instance_url)

            """
            #session.cookies.set(name="JSESSIONID", value=config.auth_jsessionid, domain=config.instance_url)
            #session.cookies.set(name="glide_session_store", value=config.auth_glide_session_store, domain=config.instance_url)
            session.cookies.set(name="JSESSIONID", value="A760E6AB7A8663C4C0690DB20B072332", domain=config.instance_url)
            session.cookies.set(name="glide_session_store", value="9729312E4732C3108442B922036D431E", domain=config.instance_url)
            session.cookies.set(name="glide_sso_id", value="b20002151bb250106745fea7dc4bcb24", domain=config.instance_url)
            session.cookies.set(name="glide_returning_auth_user", value="GlideReturningUserAuth:TUNET05BRDN8MTc4NzM5MDM1MTc5NHxIbW1RUExsQ1FzdlhpSVVEZXNYRjFoRWRBN29TbWJ4N25GdVpTZndOOTljPQ==", domain=config.instance_url)
            session.cookies.set(name="glide_user_route", value="glide.8cd13bd9e973bb14ff502ce2ca2c6956", domain=config.instance_url)
            session.cookies.set(name="glide_node_id_for_js", value="96c5c4e40f557b2aca54555caa0ab4ffee876ea37ef324b0ebd5bd02ade35321", domain=config.instance_url)
            session.cookies.set(name="VALK_SESSION_ID", value="44763951EDBC9A5720BDA10C590D0007", domain=config.instance_url)
            session.cookies.set(name="BIGipServerpool_watercorporation", value="7d6bbd00fdc80ae8e657a01b504676df", domain=config.instance_url)
            """
        
        # Do the export
        result = exportCsv(session)
        combineCsvFiles(config.out_file, result.pages)

        # Save the delta timestamp to file, if needed
        if (config.output_timestamp):
            outputTimestampToFile()

    except Exception as ex:
        log.error(ex)
        raise ex
    
    finally:
        stopTime = time.time()
        log.info("Completed in {0}s".format(int(stopTime-startTime)))

def signal_handler(sig, frame):
    log.info("SIGINT, exiting...")
    sys.exit(0)
signal.signal(signal.SIGINT, signal_handler)

if __name__ == "__main__":
    main()