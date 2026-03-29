import os

def validate_input_data(data):
    if isinstance(data, str):
        return data.encode('utf-8')
    elif isinstance(data, bytearray):
        return bytes(data)
    elif isinstance(data, bytes):
        return data
    else:
        raise ValueError("Unsupported data type")

def validate_output_path(path):
    # Just ensure directory exists
    dir_name = os.path.dirname(os.path.abspath(path))
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    return path

def validate_file_path(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")
    return path
