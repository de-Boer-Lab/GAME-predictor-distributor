import sys
import uvicorn

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print(f"Invalid arguments! Arguments must have: <container image/python script> <ip_address> <port>")
        sys.exit(1)
        
    distributor_ip = sys.argv[1]
    distributor_port = int(sys.argv[2])
    
    uvicorn.run("app.main:app", host=distributor_ip, port=distributor_port)