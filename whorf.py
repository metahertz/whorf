from flask import Flask, request, jsonify
from os import environ, remove 
import logging
import json
import subprocess
import yaml
from datetime import datetime

webhook = Flask(__name__)

webhook.logger.setLevel(logging.INFO)

@webhook.route('/', methods=['GET'])
def hello():
    return "<h1 style='color:blue'>Ready!</h1>"

@webhook.route('/validate', methods=['POST'])
def validating_webhook():
    request_info = request.get_json()
    uid = request_info["request"].get("uid")

    jsonfile = "tmp/" + uid + "-req.json"
    yamlfile = "tmp/" + uid + "-req.yaml"
    configfile = "config/.checkov.yaml"

    ff = open(jsonfile, 'w+')
    yf = open(yamlfile, 'w+')
    json.dump(request_info, ff)
    yaml.dump(todict(request_info["request"]["object"]),yf)

    cp = subprocess.run(["checkov","--config-file",configfile,"-f",yamlfile], universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    checkovresults = json.loads(cp.stdout)

    remove(jsonfile)
    remove(yamlfile)

    if cp.returncode != 0:


        # open configfile to check for hard fail CKVs
        with open(configfile, 'r') as config:
            cf = yaml.safe_load(config)

        response = ""
        if "hard-fail-on" in cf:
            hard_fails = {}
            try:
                for ckv in cf["hard-fail-on"]:
                    for fail in checkovresults["results"]["failed_checks"]:
                        if (ckv == fail["check_id"]):
                            hard_fails[ckv] = f"\n  Description: {fail['check_name']}"
                            if fail['guideline'] != "":
                                hard_fails[ckv] =  hard_fails[ckv] + f"\n  Guidance: {fail['guideline']}"
    
            except:
                print ("hard fail error")
        
            if (len(hard_fails) > 0):
                response = f"\nCheckov found {len(hard_fails)} issues in violation of admission policy.\n"
    
                for ckv in hard_fails:
                    response = response + f"{ckv}:{hard_fails[ckv]}\n"

        response = response + f"Checkov found {checkovresults['summary']['failed']} total issues in this manifest.\n"
        response = response + f"\nFor complete details: {checkovresults['url']}\n"
       
    
        webhook.logger.error(f'Object {request_info["request"]["object"]["kind"]}/{request_info["request"]["object"]["metadata"]["name"]} failed security checks. Request rejected!')
        return admission_response(False, uid, response)

    else:
        webhook.logger.info(f'Object {request_info["request"]["object"]["kind"]}/{request_info["request"]["object"]["metadata"]["name"]} passed security checks. Allowing the request.')
        return admission_response(True, uid, f"Checkov found {checkovresults['summary']['failed']} issues. None in violation of admission policy. {checkovresults['summary']['failed']} issues in this manifest!")


def todict(obj):
    if hasattr(obj, 'attribute_map'):
        result = {}
        for k,v in getattr(obj, 'attribute_map').items():
            val = getattr(obj, k)
            if val is not None:
                result[v] = todict(val)
        return result
    elif type(obj) == list:
        return [todict(x) for x in obj]
    elif type(obj) == datetime:
        return str(obj)
    else:
        return obj


def admission_response(allowed, uid, message):
    return jsonify({"apiVersion": "admission.k8s.io/v1",
                    "kind": "AdmissionReview",
                    "response": {
                         "allowed": allowed,
                         "uid": uid,
                         "status": {
                           "code": 403,
                           "message": message
                         }
                       }
                    })


if __name__ == '__main__':
    webhook.run(host='0.0.0.0', port=1701)
