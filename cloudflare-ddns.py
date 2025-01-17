import argparse, requests, json, sys, signal, os, threading, time

PATH = os.getcwd() + "/"
version = float(str(sys.version_info[0]) + "." + str(sys.version_info[1]))
shown_ipv4_warning = False
shown_ipv6_warning = False

if(version < 3.5):
    raise Exception("This script requires Python 3.5+")

class GracefulExit:
  def __init__(self):
    self.kill_now = threading.Event()
    signal.signal(signal.SIGINT, self.exit_gracefully)
    signal.signal(signal.SIGTERM, self.exit_gracefully)

  def exit_gracefully(self, signum, frame):
    print("🛑 Stopping main thread...")
    self.kill_now.set()

def deleteEntries(type):
    # Helper function for deleting A or AAAA records
    # in the case of no IPv4 or IPv6 connection, yet
    # existing A or AAAA records are found.
    try:
        for c in config["cloudflare"]:
            answer = cf_api(
                "zones/" + c['zone_id'] + "/dns_records?per_page=100&type=" + type, "GET", c)
            for r in answer["result"]:
                identifier = str(r["id"])
                response = cf_api(
                    "zones/" + c['zone_id'] + "/dns_records/" + identifier, "DELETE", c)
                print("🗑️ Deleted stale record " + identifier)
    except Exception:
        print("😡 Error deleting " + type + " record(s)")

def getIPs():
    global shown_ipv4_warning
    global shown_ipv6_warning
    a = None
    aaaa = None
    try:
        a = requests.get("https://1.1.1.1/cdn-cgi/trace").text.split("\n")
        a.pop()
        a = dict(s.split("=") for s in a)["ip"]
    except Exception:
        if not shown_ipv4_warning:
            shown_ipv4_warning = True
            print("😨 Warning: IPv4 not detected")
        deleteEntries("A")
    try:
        aaaa = requests.get("https://[2606:4700:4700::1111]/cdn-cgi/trace").text.split("\n")
        aaaa.pop()
        aaaa = dict(s.split("=") for s in aaaa)["ip"]
    except Exception:
        if not shown_ipv6_warning:
            shown_ipv6_warning = True
            print("😨 Warning: IPv6 not detected")
        deleteEntries("AAAA")
    ips = {}
    if(a is not None):
        ips["ipv4"] = {
            "type": "A",
            "ip": a
        }
    if(aaaa is not None):
        ips["ipv6"] = {
            "type": "AAAA",
            "ip": aaaa
        }
    return ips

def commitRecord(ip, config):
    for c in config["cloudflare"]:
        subdomains = c["subdomains"]
        response = cf_api("zones/" + c['zone_id'], "GET", c)
        base_domain_name = response["result"]["name"]
        ttl = 300 # default Cloudflare TTL
        for subdomain in subdomains:
            subdomain = subdomain.lower().strip()
            record = {
                "type": ip["type"],
                "name": subdomain,
                "content": ip["ip"],
                "proxied": c["proxied"],
                "ttl": ttl
            }
            dns_records = cf_api(
                "zones/" + c['zone_id'] + "/dns_records?per_page=100&type=" + ip["type"], "GET", c)
            fqdn = base_domain_name
            if subdomain:
                fqdn = subdomain + "." + base_domain_name
            identifier = None
            modified = False
            duplicate_ids = []
            for r in dns_records["result"]:
                if (r["name"] == fqdn):
                    if identifier:
                        if r["content"] == ip["ip"]:
                            duplicate_ids.append(identifier)
                            identifier = r["id"]
                        else:
                            duplicate_ids.append(r["id"])
                    else:
                        identifier = r["id"]
                        if r['content'] != record['content'] or r['proxied'] != record['proxied']:
                            modified = True
            if identifier:
                if modified:
                    print("📡 Updating record " + str(record))
                    response = cf_api(
                        "zones/" + c['zone_id'] + "/dns_records/" + identifier, "PUT", c, {}, record)
            else:
                print("➕ Adding new record " + str(record))
                response = cf_api(
                    "zones/" + c['zone_id'] + "/dns_records", "POST", c, {}, record)
            for identifier in duplicate_ids:
                identifier = str(identifier)
                print("🗑️ Deleting stale record " + identifier)
                response = cf_api(
                    "zones/" + c['zone_id'] + "/dns_records/" + identifier, "DELETE", c)
    return True

def cf_api(endpoint, method, config, headers={}, data=False):
    api_token = config['authentication']['api_token']
    if api_token != '' and api_token != 'api_token_here':
        headers = {
            "Authorization": "Bearer " + api_token,
            **headers
        }
    else:
        headers = {
            "X-Auth-Email": config['authentication']['api_key']['account_email'],
            "X-Auth-Key": config['authentication']['api_key']['api_key'],
        }

    if(data == False):
        response = requests.request(
            method, "https://api.cloudflare.com/client/v4/" + endpoint, headers=headers)
    else:
        response = requests.request(
            method, "https://api.cloudflare.com/client/v4/" + endpoint, headers=headers, json=data)

    return response.json()

def updateIPs(ips, config):
    for ip in ips.values():
        commitRecord(ip, config)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", action="store_true")
    parser.add_argument("--config-path", dest="config", type=open, default=os.path.join(PATH, "config.json"))
    args = parser.parse_args()

    config = json.load(args.config)

    if args.repeat:
        delay = 60
        print("⏲️ Updating IPv4 (A) & IPv6 (AAAA) records every 15 minutes")
        next_time = time.time()
        killer = GracefulExit()
        prev_ips = None
        while True:
            if killer.kill_now.wait(delay):
                break
            ips = getIPs()
            if ips != prev_ips:
                updateIPs(ips, config)
    else:
        updateIPs(getIPs, config)
