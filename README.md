## Dave's SN Exporter Tool
A tool for exporting data from a ServiceNow instance.

Exporting over 1,000 rows of data out of ServiceNow can be difficult and tedious. This tool follows the method on ServiceNow Docs of exported data in "pages" or "chunks".

Features
* Export unlimited data from ServiceNow from any table your user has access to (default: pages of 1,000 rows).
* Exports data as comma-separated files (CSV).
* Exports using the URL export features, no need for Table API access. Any user can do it!
* Can export display values or system values.
* Authenticate as your browser's session, compatible with SSO authentication.
* Configuration files can be used for regular exports, instead of configuring everything through the command line.
* Resume support, great for resuming an export that was interrupted.
* Delta exports, only exporting data that's changed since the last export.
* Progress animation while exporting data.
* Few dependancies, should run on any computer with Python3.

## Requirements
* Python 3
* `requests`

Required python packages can be installed using the `requirements.txt` file.

```
pip install -r requirements.txt
```

## Usage
Use this tool in the command line.

Using the export tool will export the data into multiple files, each being **pages** of results, into a **temporary directory** which is `./tmp/` by default.

![Exported files](doc/exported-files.png)

![Exported data spreadsheet](doc/exported-data-csv.png)

**Note:** The sys_id column is included in every export due to how the tool exports data.

### Example 1
Exporting all user records with only the fields "name", "email", and "phone number". Show progress animation.

```
python3 ./DavesSnExportTool.py --progress --instance-url "dev123456.service-now.com" --export-table sys_user --export-fields "name,email,department" --out "sys_user" --auth-type cookies --auth-cookies "<browser cookies>"
```

### Example 2
The same, but using shorthand arguments.

```
python3 ./DavesSnExportTool.py -P -i "dev123456.service-now.com" -t sys_user -f "name,email,department" -o "sys_user" -a cookies -ac "<browser cookies>"
```

### Example 3
The same, but using a configuration file.

```
python3 ./DavesSnExportTool.py -c ./tmp/config.json
```

The config file in `./tmp/config.json`
```json
{
    "instance_url": "dev123456.service-now.com",
    "auth_type": "cookies",
    "auth_cookies": "<browser cookies>",
    "export_table": "incident",
    "export_fields": "name,email,department",
    "out_file": "sys_user",
    "progress": "true"
}
```

### Example 5
Export incidents with all fields, but only export incidents that have changed since the last export. A **delta** export.

```
python3 ./DavesSnExportTool.py -i dev123456.service-now.com -t incident -o incident_feed -f "*" --state ./tmp/state.json --delta-export --auth-type cookie --auth-cookies "<browser cookies>"
```

* 1st run: export's everything, saves the date & time to the state file.
* future runs: filters data to only what's changed since the last run.

## Cookie authentication
The export tool can authenticate using your browser's ServiceNow session. To do this, we'll need to get your **cookies** to the tool.

1. In your web browser, open the instance of ServiceNow you'll be exporting data from.
2. Open the **developer tools** (Chrome & Firefox: press F12).
3. Open the **Network** tab. If there are no results, reload the page.
4. Click on any of the results, search for **Request Headers** then **Cookie**. Copy the entire value for Cookie.

![authentication cookies in developer tools](doc/auth-cookies-in-dev-tools.png)

5. Use the export tool and paste in cookie value after `--auth-cookies--`

Example:
```
python3 DavesSnExportTool.py --instance-url dev123456.service-now.com --export-table incident --auth-type cookies --auth-cookies "JSESSIONID=77714E2F7CD182B0062562679A308BDF; glide_node_id_for_js=504f76108a593bd78bf14b6a7cdbf0831845ef9a2376f053b10259ec00f071b8;..."
```

## Combining very large reports
It is possible for this tool to combine lots of rows of data into 1 large CSV file. However, there are limits to what tools like Excel will be able to open.

If you are exporting gigabytes of data, I'd recommend leaving them as separate files, instead of combining them into 1 large file.

## Wish list
### Browser authentication
Support for automatically fetching authentication cookies from your browser may not be possible. The session cookies are tied to the browser's session, and are deleted once the browser is closed.

I may look at this in a future version, but for now, the cookie copy & paste method works.

### Advanced proxies
Like many non-browser tools, this tool is compabile with basic HTTP/HTTPS proxies, however it's not currently compatible with:
* NTLM / kerberos authenticated proxies (Windows-auth)
* SOCKS proxies
* PAC-file configured proxies

Some Windows proxy tools can be used to bridge through to your kerberos-authenticated proxy. Do so at your own risk.
* Px (https://github.com/genotrance/px)
* WinPX (https://apps.microsoft.com/detail/9pk1pt0skm0q)
* Winfoom (https://github.com/ecovaci/winfoom)

To truely overcome all proxy configurations, I feel this tool would need to become a browser plugin and use the browser's proxy functionality. Maybe in a future version.