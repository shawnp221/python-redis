import socket  # noqa: F401
import threading
import time

data_store = {}  # In-memory data store for SET and GET commands
data_lock = threading.Lock()  # Lock to ensure thread-safe access to the data store

list_store = {} # In-memory data store for RPUSH command
list_lock = threading.Lock()  # Lock to ensure thread-safe access to the list store


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


def encode_array(data_list):
    # Encode an array in RESP format
    result = f"*{len(data_list)}\r\n".encode()
    for item in data_list:
        result += encode_bulk_string(item)
    return result


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
                if len(command) < 3:
                    connection.sendall(b"-ERR wrong number of arguments for 'set' command\r\n")
                    continue

                key = command[1]
                value = command[2]
                expiry = None

                i = 3
                while i < len(command):
                    expiry_option = command[i].upper()
                    if expiry_option == b"EX" and i + 1 < len(command):
                        try:
                            seconds = int(command[i + 1])
                            expiry = time.monotonic() + seconds
                        except ValueError:
                            connection.sendall(b"-ERR invalid expire time\r\n")
                            break

                        i += 2
                    elif expiry_option == b"PX" and i + 1 < len(command):
                        try:
                            milliseconds = int(command[i + 1])
                            expiry = time.monotonic() + milliseconds / 1000
                        except ValueError:
                            connection.sendall(b"-ERR invalid expire time\r\n")
                            break

                        i += 2
                    else:
                        connection.sendall(b"-ERR syntax error\r\n")
                        break

                else:
                    with data_lock:
                        data_store[key] = (value, expiry)
                    connection.sendall(b"+OK\r\n")
            
            elif command_name == b"GET":
                if len(command) != 2:
                    connection.sendall(b"-ERR wrong number of arguments for 'get' command\r\n")
                    continue

                key = command[1]

                with data_lock:
                    entry = data_store.get(key)

                    if entry is not None:
                        value, expiry = entry

                        if expiry is not None and time.monotonic() >= expiry:
                            del data_store[key]
                            entry = None

                if entry is None:
                    connection.sendall(b"$-1\r\n")
                else:
                    connection.sendall(encode_bulk_string(value))

            elif command_name == b"RPUSH":
                if len(command) < 3:
                    connection.sendall(b"-ERR wrong number of arguments for 'rpush' command\r\n")
                    continue
                
                key = command[1]
                elements = command[2:]

                with list_lock:
                    if key not in list_store:   
                        list_store[key] = []    # create the list if it doesn't exist
                    list_store[key].extend(elements)  # add elements to the list
                    length = len(list_store[key])
                connection.sendall(f":{length}\r\n".encode())

            elif command_name == b"LPUSH":
                if len(command) < 3:
                    connection.sendall(b"-ERR wrong number of arguments for 'lpush' command\r\n")
                    continue
                
                key = command[1]
                elements = command[2:]

                with list_lock:
                    if key not in list_store:   
                        list_store[key] = []    # create the list if it doesn't exist
                    list_store[key] = elements[::-1] + list_store[key]  # add elements to the list
                    length = len(list_store[key])
                connection.sendall(f":{length}\r\n".encode())

            elif command_name == b"LRANGE":
                if len(command) != 4:
                    connection.sendall(b"-ERR wrong number of arguments for 'lrange' command\r\n")
                    continue

                key = command[1]
                try:
                    start = int(command[2])
                    stop = int(command[3])
                except ValueError:
                    connection.sendall(b"-ERR start and stop must be integers\r\n")
                    continue

                with list_lock:
                    items = list_store.get(key, []) # missing list -> empty
                    length = len(items)

                    # Convert negative indexes to offsets from the end
                    if start < 0:
                        start = max(length + start, 0)   # too far back -> clamp to first element
                    if stop < 0:
                        stop = length + stop             # may stay negative -> empty result below

                    if start >= length or start > stop:
                        result = []
                    else:
                        stop = min(stop, length - 1)    # clamp stop to the last element
                        result = items[start:stop + 1]  # +1 because stop is inclusive
                    
                    connection.sendall(encode_array(result))


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
