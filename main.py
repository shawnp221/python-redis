import socket  # noqa: F401
import threading

data_store = {}  # In-memory data store for SET and GET commands
data_lock = threading.Lock()  # Lock to ensure thread-safe access to the data store


def parse_resp(data):
    # Example input: b"*2\r\n$4\r\nECHO\r\n$3\r\nhey"
    lines = data.split(b"\r\n")

    # First line contains the array count, e.g. *2
    count = int(lines[0][1:])

    result = []
    i = 1

    for _ in range(count):
        # Read the bulk string length, e.g. $4
        length = int(lines[i][1:])
        i += 1

        # Read the actual argument
        argument = lines[i]
        i += 1

        if len(argument) != length:
            raise ValueError("Invalid bulk string length")

        result.append(argument)

    return result



def encode_bulk_string(data):
    # Encode a bulk string in RESP format
    # .encode() converts the formatted text string into a byte object (using UTF-8 encoding by default)
    length = len(data)
    return f"${length}\r\n".encode() + data + b"\r\n"

def handle_client(connection):
    try:
        while True:
            data = connection.recv(1024)  # receive data from client
            if not data:
                break
            command = parse_resp(data)
            if not command:
                connection.sendall(b"-Error: Empty command\r\n")
                continue

            command_name = command[0].upper()

            if command_name == b"PING":
                connection.sendall(b"+PONG\r\n")

            elif command_name == b"ECHO":
                if len(command) == 2:
                    response = encode_bulk_string(command[1])
                    connection.sendall(response)
                else:
                    connection.sendall(b"-ERR wrong number of arguments for 'echo' command\r\n")

            elif command_name == b"SET":
                if len(command) == 3:
                    key = command[1]
                    value = command[2]
                    with data_lock:
                        data_store[key] = value
                    connection.sendall(b"+OK\r\n")
                else:
                    connection.sendall(b"-ERR wrong number of arguments for 'set' command\r\n")
            
            elif command_name == b"GET":
                if len(command) == 2:
                    key = command[1]
                    with data_lock:
                        value = data_store.get(key)
                    if value is not None:
                        response = encode_bulk_string(value)
                        connection.sendall(response)
                    else:
                        connection.sendall(b"$-1\r\n")
                else:
                    connection.sendall(b"-ERR wrong number of arguments for 'get' command\r\n")
            else:
                connection.sendall(b"-ERR unknown command\r\n")

    except (ConnectionError, ValueError, IndexError):
        pass
    finally:
        connection.close()


def main():
    # You can use print statements as follows for debugging, they'll be visible when running tests.
    print("Logs from your program will appear here!")
    #line = b"*2\r\n$4\r\nECHO\r\n$3\r\nhey"
    # lines = line.split(b"\r\n")

    # lines[0] is "*2". We slice from index 1 to skip the '*' and convert to int.
    # count = int(lines[0][1:]) 
    # result = lines[1:]  # The rest of the lines are the bulk strings

    # result = parse_resp(line)

    #print(f"Count of elements to read: {result}")
    #print(encode_bulk_string("hey"))  # Example usage of encode_bulk_string

    # Uncomment the code below to pass the first stage
    #
    server_socket = socket.create_server(("localhost", 6379))

    # connection, _ = server_socket.accept() # wait for client
    
    while True:
        connection, _ = server_socket.accept() # wait for client
        
        client_thread = threading.Thread(target=handle_client, args=(connection,))
        client_thread.start()




if __name__ == "__main__":
    main()
