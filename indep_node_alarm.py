import json
import time
import requests # sudo pip3 install requests
import shutil
import threading
from datetime import datetime

from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from requests import Session
from flask import Flask, jsonify

### Config
### =====
my_validator_address = ""
node_name = "<nodename>"

height_increasing_time_period = 600
missing_block_trigger = 10
### =====

retries = Retry(total=10, connect=8, read=2, backoff_factor=0.2, status_forcelist=[500, 502, 503, 504, 429])
app = Flask(__name__)
q_err = []

def main() :

    node_list = []

    node_list.append(NodeInfo("<chainname>", "http://localhost:26657", my_validator_address))
    
    while True:

        check_freedisk()

        # Last Height Check
        for node in node_list:
            node.get_last_height()

        # ***** Wait *****
        time.sleep(height_increasing_time_period)

        # Check : stuck, block missing
        for node in node_list:
            if node.get_current_height():
                node.check_height_stuck()
                node.check_block_missing()
                node.update_last_height()


class NodeInfo:

    def __init__(self, chain, rpc_url, validator_address):
        self.chain = chain
        self.rpc_url = rpc_url
        self.last_height = 0
        self.current_height = 0
        self.validator_address = validator_address

    def get_last_height(self):
        with Session() as sess:
            try:
                sess.mount('http://',  HTTPAdapter(max_retries=retries))
                sess.mount('https://', HTTPAdapter(max_retries=retries))
                status = json.loads(sess.get(self.rpc_url + "/status").text)
                last_height = int(status["result"]["sync_info"]["latest_block_height"])
                self.last_height = last_height
            except Exception as e:
                alarm_content = f'{node_name} : {self.chain} - get_last_height - Exception: {e}'
                pushErr(alarm_content)

    def get_current_height(self):
        with Session() as sess:
            try:
                sess.mount('http://',  HTTPAdapter(max_retries=retries))
                sess.mount('https://', HTTPAdapter(max_retries=retries))
                status = json.loads(sess.get(self.rpc_url + "/status").text)
                current_height = int(status["result"]["sync_info"]["latest_block_height"])
                self.current_height = current_height
                return True
            
            except Exception as e:
                alarm_content = f'{node_name} : {self.chain} - get_current_height - Exception: {e}'
                pushErr(alarm_content)
                return False
      
    def update_last_height(self):
        self.last_height = self.current_height

    def check_height_stuck(self): 
        current_datetime = datetime.now()
        log_entry = f"{current_datetime} Last: {self.last_height},  Current: {self.current_height}, Diff: {self.current_height-self.last_height}, BlockTime: {height_increasing_time_period/(self.current_height-self.last_height)}"
        with open('/tmp/indep.log', 'a') as log_file:
            log_file.write(log_entry + '\n')

        if self.last_height == self.current_height :
            alarm_content = f'{self.chain}({node_name}) : height stucked!'
            pushErr(alarm_content)


    def check_block_missing(self):

        if self.validator_address == "":
            return

        missing_block_cnt = 0

        for height in range(self.last_height+1, self.current_height+1):
            precommit_match = False
            precommits = json.loads(requests.get(self.rpc_url + "/commit?height=" + str(height), timeout=5).text)["result"]["signed_header"]["commit"]["signatures"]
            
            for precommit in precommits:
                try:
                    validator_address = precommit["validator_address"]
                except:
                    validator_address = ""
                if validator_address == self.validator_address:
                    precommit_match = True
                    break

            if precommit_match == False:
                missing_block_cnt += 1

        current_datetime = datetime.now()
        log_entry = f"{current_datetime} Missed: {missing_block_cnt},  Threshold: {missing_block_trigger}"
        with open('/tmp/indep.log', 'a') as log_file:
            log_file.write(log_entry + '\n')
            
        if missing_block_cnt >= missing_block_trigger:
            
            alarm_content = f'{node_name} : {self.chain} - missing block count({missing_block_cnt}) >=  threshold({missing_block_trigger})'
            pushErr(alarm_content)

## Functions
def check_freedisk():
    try:
        total, used, free = shutil.disk_usage("/")
        free_disk_trigger = 10
        if (free//(2**30)) < free_disk_trigger:
            alarm_content = f'{node_name} (/ disk) : disk free is less than {free_disk_trigger} GB'
            pushErr(alarm_content)
    except Exception as e:
        print(e)

    try:
        total, used, free = shutil.disk_usage("/data")
        free_disk_trigger = 50
        if (free//(2**30)) < free_disk_trigger:
            alarm_content = f'{node_name} (/data disk) : disk free is less than {free_disk_trigger} GB'
            pushErr(alarm_content)
    except Exception as e:
        print(e)

def pushErr(err):
    print("New issue occured in the node:", err)
    q_err.append(err)

@app.route('/', methods=['GET'])
def handler():
    # if len(q_err) == 0 means all fine.
    errs = " %0A".join(q_err)
    resp = newResponse(node_name, len(q_err), errs)
    q_err.clear()
    return resp

def newResponse(target, status, err):
    return jsonify({"target": target,"status": status, "error": err})

if __name__ == "__main__":
    thread = threading.Thread(target=main)
    thread.start()

    app.run(host='0.0.0.0', port=8529, debug=True, use_reloader=False)
