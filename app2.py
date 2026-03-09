from Server.server import run
from Server import server

import dotenv
dotenv.load_dotenv()

if __name__ == "__main__":
    # Run redis on a docker instance
    # docker run -d --name my-redis -p 6379:6379 redis:latest
    import json
    d = {
        "upload_id":"1234567", 
        "file_path":"data/path.png", 
        "send_retries":0
    }
    print(f"Data: {json.dumps(d)}")
    run(4001)