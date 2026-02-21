import subprocess
import json

def join_tables(db_path):
    data_to_send = {"db_path": db_path}

    json_data = json.dumps(data_to_send)

    # Spawn the Node.js process
    process = subprocess.Popen(['node', 'read_db.mjs'], 
                            stdin=subprocess.PIPE, 
                            stdout=subprocess.PIPE, 
                            stderr=subprocess.PIPE, 
                            text=True)

    # Send the JSON data to the Node.js process
    stdout, stderr = process.communicate(input=json_data)

    if stderr:
        return False, stderr
    else:
        result = json.loads(stdout)

        return True, result['result']
