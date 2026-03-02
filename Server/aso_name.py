import json
import time
import subprocess

def get_autonomous_sys_org_name(address):
    data_to_send = {"address": address}
    json_data = json.dumps(data_to_send)

    aso_path = "Server/aso_name.js"

    process = subprocess.Popen(['node', aso_path],
                            stdin=subprocess.PIPE,
                           stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, 
                           text=True)

    stdout, stderr = process.communicate(input=json_data)
    
    if stderr:
        return False, stderr
    else:
        result = json.loads(stdout)

        return True, result['asos']
    

if __name__ == "__main__":
    address = '2a03:2880:f01c:16:face:b00c:0:2'
    status, results = get_autonomous_sys_org_name(address)
    if status:
        print(f"Tunnel created successfully! URL: {results}")
    else:
        print(f"Failed to create tunnel. Error: {results}")

    # Sleep for 30 seconds and the terminate the tunnel
    #time.sleep(30)
    #process.terminate()
    