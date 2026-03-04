import json
import time
import subprocess

def create_tunnel(port, subdomain):
    data_to_send = {"port": port, "subdomain": subdomain}

    tunnel_path = "Server/tunnel.mjs"

    # These files are used to communicate with the Node.js process.
    # This is because the process is meant to run indefinitely, so we cannot use
    # subprocess.communicate() to get the output.
    input_file = f"tunnel_input_{time.time()}.json"
    output_file = f"tunnel_output_{time.time()}.log"

    with open(input_file, 'w') as fp:
        json.dump(data_to_send, fp)

    with open(input_file, 'r') as fp:
        # Spawn the Node.js process
        creation_flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        with open(output_file, 'w') as f:
            process = subprocess.Popen(['node', tunnel_path],
                                    creationflags=creation_flags,
                                    stdin=fp,
                                    stdout=f,
                                    stderr=subprocess.STDOUT, 
                                    shell=False,
                                    start_new_session=True)
    
    # Sleep for a few seconds to allow the tunnel to be created.
    time.sleep(10)

    with open(output_file, 'r') as f:
        output = f.read()
        try:
            result = json.loads(output)
            return True, result['tunnel_url'], process
        except json.JSONDecodeError:
            return False, output, process
    

#if __name__ == "__main__":
def test_app():
    port = 4001
    subdomain = "mogomotsihs"
    status, tunnel_url, process = create_tunnel(port, subdomain)
    if status:
        print(f"Tunnel created successfully! URL: {tunnel_url}")
    else:
        print(f"Failed to create tunnel. Error: {tunnel_url}")

    # Sleep for 30 seconds and the terminate the tunnel
    #time.sleep(30)
    #process.terminate()
    