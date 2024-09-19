#!/usr/bin/env python

# Simple ansible-inventory script for Netbox that is compatible with AWX
#
# Adapted from:
# https://github.com/sakbhav/netbox-awx/blob/master/netbox-awx.py

import json
import os
import requests
import urllib3
import argparse


def main(args):
    urllib3.disable_warnings()

    headers = {
        "Accept": "application/json ; indent=4",
        "Authorization": "Token %s" % (TOKEN),
    }

    url_tags = ""
    if FILTER_TAGS:
        c_tags = len(FILTER_TAGS)
        url_tags = "?"
        for t in range(0, c_tags):
            item = FILTER_TAGS[t]
            if t == 0 or t == c_tags:
                url_tags += "tag=" + item
            elif t > 0 and t < c_tags:
                url_tags += "&tag=" + item

    if FILTER_CUSTOM:
        c_custom = len(FILTER_CUSTOM)
        if "?" not in url_tags:
            url_tags = "?"
        else:
            url_tags += "&"
        for t in range(0, c_custom):
            item = FILTER_CUSTOM[t]
            if t == 0 or t == c_custom:
                url_tags += item
            elif t > 0 and t < c_custom:
                url_tags += "&" + item

    api_url = URL + "/api/dcim/devices/" + url_tags
    if NETBOX_VIRTUAL:
        api_url = URL + "/api/virtualization/virtual-machines/" + url_tags

    processed_hosts = {}
    hosts_list = []
    devices = []
    sites = {}
    racks = {}
    platforms = {}
    clusters = {}
    tenants = {}
    tags = {}
    inventory = {}
    hostvars = {}

    # Get data from netbox
    while api_url:
        try:
            api_output = requests.get(api_url, headers=headers, verify=False)
            api_output_data = api_output.json()
        except Exception as error:
            print("ERROR: NETBOX API=>", error)
            exit(-1)

        if api_output_data.get("error"):
            print("ERROR: " + api_output_data["error"])
            exit(-1)
        if api_output.status_code == 400:
            print(
                "BAD REQUEST: "
                + str(api_output.status_code)
                + " => "
                + api_output.text
                + " => URL: "
                + api_url
            )
            exit(-1)
        if api_output.status_code == 401:
            print(
                "UNAUTHORIZED: "
                + str(api_output.status_code)
                + " => "
                + api_output.text
                + " => URL: "
                + api_url
            )
            exit(-1)
        if api_output.status_code == 403:
            print(
                "FORBIDDEN: "
                + str(api_output.status_code)
                + " => "
                + api_output.text
                + " => URL: "
                + api_url
            )
            exit(-1)
        if api_output.status_code == 404:
            print(
                "NOT FOUND: "
                + str(api_output.status_code)
                + " => "
                + api_output.text
                + " => URL: "
                + api_url
            )
            exit(-1)
        if isinstance(api_output_data, dict) and "results" in api_output_data:
            hosts_list += api_output_data["results"]
            api_url = api_output_data["next"]

    # Filter hosts for AWX
    for i in hosts_list:
        primary_ip = i.get("primary_ip")
        if primary_ip:
            if FILTER_TAGS:
                if i.get("tags") is None:
                    continue
                for item in i["tags"]:
                    if item.get("name") in FILTER_TAGS:
                        devices.append(i)
            else:
                devices.append(i)

    # Populate inventory
    for i in devices:
        host = i.get("name")
        if host and host not in processed_hosts:
            site = i.get("site")
            if site:
                sites.setdefault(site["slug"], {"hosts": []})["hosts"].append(
                    host
                )
            if NETBOX_DEVICE:
                rack = i.get("rack")
                if rack:
                    racks.setdefault(rack["name"], {"hosts": []})[
                        "hosts"
                    ].append(host)
            if NETBOX_VIRTUAL:
                cluster = i.get("cluster")
                if cluster:
                    clusters.setdefault(cluster["name"], {"hosts": []})[
                        "hosts"
                    ].append(host)
            platform = i.get("platform")
            if platform:
                platforms.setdefault(platform["slug"], {"hosts": []})[
                    "hosts"
                ].append(host)
            tenant = i.get("tenant")
            if tenant:
                tenants.setdefault(tenant["slug"], {"hosts": []})[
                    "hosts"
                ].append(host)
            tags_result = i.get("tags")
            if tags_result:
                for t in tags_result:
                    tags.setdefault(t.get("name"), {"hosts": []})[
                        "hosts"
                    ].append(host)

            hostvars.setdefault("_meta", {"hostvars": {}})["hostvars"][
                host
            ] = {}
            config_context = i.get("config_context")
            if config_context:
                hostvars["_meta"]["hostvars"][host][
                    "config_context"
                ] = config_context
            primary_ip = i.get("primary_ip")
            if primary_ip:
                if host and ANSIBLE_HOST_DOMAIN:
                    hostvars["_meta"]["hostvars"][host][
                        "ansible_host"
                    ] = host + "." + ANSIBLE_HOST_DOMAIN
                    hostvars["_meta"]["hostvars"][host]["primary_ip"] = primary_ip[
                        "address"
                    ].split("/")[0]
                else:
                    hostvars["_meta"]["hostvars"][host][
                        "ansible_host"
                    ] = primary_ip["address"].split("/")[0]
                    hostvars["_meta"]["hostvars"][host]["primary_ip"] = primary_ip[
                        "address"
                    ].split("/")[0]
            processed_hosts[host] = host

    inventory.update(sites)
    inventory.update(racks)
    inventory.update(platforms)
    inventory.update(clusters)
    inventory.update(tenants)
    inventory.update(tags)
    inventory.update(hostvars)

    print(json.dumps(inventory, indent=4))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        usage="%(prog)s [options]",
        description="Netbox inventory script.",
    )
    parser.add_argument("--list", action="store_true", help="list inventory")
    parser.add_argument(
        "-t", type=str, dest="TOKEN", help="Authentication Token"
    )
    parser.add_argument("-u", type=str, dest="URL", help="URL")
    parser.add_argument(
        "-d", action="store_true", dest="b_device", help="Device list"
    )
    parser.add_argument(
        "-v", action="store_true", dest="b_virtual", help="Virtual-Machine list"
    )
    parser.add_argument(
        "-g", type=str, dest="TAGS", help="List of tags ex: switch,managed"
    )
    parser.add_argument(
        "-c",
        type=str,
        dest="CUSTOM",
        help="List of custom filters ex: role=switch,model=blah",
    )
    parser.add_argument(
        "-n",
        type=str,
        dest="ANSIBLE_HOST_DOMAIN",
        help="Domain to add to 'hostname' for ansible_host values",
    )
    args = parser.parse_args()

    # Netbox URL
    if os.environ.get("NETBOX_URL") is not None:
        URL = os.environ.get("NETBOX_URL")
    else:
        if args.URL is not None:
            URL = args.URL
        else:
            print(
                "ERROR: neither NETBOX_URL or -u option are set. Provide one "
                "to continue..."
            )
            exit(-1)

    # Netbox API Token
    if os.environ.get("NETBOX_TOKEN") is not None:
        TOKEN = os.environ.get("NETBOX_TOKEN")
    else:
        if args.TOKEN is not None:
            TOKEN = args.TOKEN
        else:
            print(
                "ERROR: neither NETBOX_TOKEN or -t option are set. Provide one "
                "to continue..."
            )
            exit(-1)

    # AWX Filter Tags
    # Example: ["switch", "manager"]
    if os.environ.get("NETBOX_FILTER_TAGS") is not None:
        FILTER_TAGS = os.environ.get("NETBOX_FILTER_TAGS").split(",")
    else:
        if args.TAGS is not None:
            FILTER_TAGS = args.TAGS.split(",")
        else:
            FILTER_TAGS = []
    # Example: ["platform.name=Juniper"]
    if os.environ.get("NETBOX_FILTER_CUSTOM") is not None:
        FILTER_CUSTOM = os.environ.get("NETBOX_FILTER_CUSTOM").split(",")
    else:
        if args.CUSTOM is not None:
            FILTER_CUSTOM = args.CUSTOM.split(",")
        else:
            FILTER_CUSTOM = []

    # Device
    if os.environ.get("NETBOX_DEVICE") is not None:
        NETBOX_DEVICE = bool(os.environ.get("NETBOX_DEVICE"))
    else:
        if args.b_device is not None:
            NETBOX_DEVICE = bool(args.b_device)
        else:
            NETBOX_DEVICE = True

    # Virtual
    if os.environ.get("NETBOX_VIRTUAL") is not None:
        NETBOX_VIRTUAL = bool(os.environ.get("NETBOX_VIRTUAL"))
    else:
        if args.b_virtual is not None:
            NETBOX_VIRTUAL = bool(args.b_virtual)
        else:
            NETBOX_VIRTUAL = True
    
    # Domain to add to hostnames for ansible_host values
    # Example: example.com
    if os.environ.get("ANSIBLE_HOST_DOMAIN") is not None:
        ANSIBLE_HOST_DOMAIN = str(os.environ.get("ANSIBLE_HOST_DOMAIN"))
    else:
        if args.ANSIBLE_HOST_DOMAIN is not None:
            ANSIBLE_HOST_DOMAIN = args.ANSIBLE_HOST_DOMAIN
        else:
            ANSIBLE_HOST_DOMAIN = ""

    main(args)
